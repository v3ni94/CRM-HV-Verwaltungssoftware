"""A62: minutes draft of an owners' meeting as PDF on the tenant letterhead. Expected values
by hand: owner A holds units 01 and 02 (MEA 400 + 300), owner B unit 03 (MEA 300), MEA
principle -> 1000 votes in total; A present, B represented by proxy -> 1000 of 1000 votes,
3 of 3 units. TOP 1 votes yes, yes, no -> 700 : 300, announced positive as resolution no. 1.
The draft is a document with source "generated", linked to the meeting through
minutes_draft_document_id; the signed minutes (minutes_document_id) stay untouched."""

import asyncio
import io
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pd25-{RUN}", name=f"Protokoll {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pe25-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("pd25admin", a, "tenant_admin"),
            ("pd25reader", a, "read_only"),
            ("pd25other", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _doc(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, b"%PDF-1.4 test", "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def _pdf_text(content: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(content)).pages)


def test_protocol_draft_pdf_permissions_and_tenant_separation(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "pd25admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "752",
                "name": "WEG Protokoll",
                "management_type": "hoa",
                "street": "Beschlussweg",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    keys = {
        k["code"]: k["id"]
        for k in _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    }
    party_a, _ = _party(client, h, "Protokollant")
    party_b, _ = _party(client, h, "Miteigentuemer")
    _, proxy = _party(client, h, "Bevollmaechtigter")
    contracts = {}
    for no, mea, party in [("01", "400", party_a), ("02", "300", party_a), ("03", "300", party_b)]:
        unit = _unit(client, h, prop["id"], no)
        _ok(
            client.post(
                f"/api/v1/units/{unit}/allocation-values",
                json={"allocation_key_id": keys["MEA"], "value": mea, "valid_from": "2020-01-01"},
                headers=h,
            ),
            201,
        )
        contracts[no] = _ok(
            client.post(
                "/api/v1/contracts",
                json={
                    "kind": "ownership",
                    "unit_id": unit,
                    "party_id": party,
                    "start_date": "2020-01-01",
                    "title_transfer_date": "2020-01-01",
                    "acquisition_kind": "first_acquisition",
                },
                headers=h,
            ),
            201,
        )["id"]
    meeting = _ok(
        client.post(
            f"{H}/meetings",
            json={
                "legal_entity_id": hoa,
                "scheduled_at": "2026-06-20T10:00:00+02:00",
                "location": "Gemeinschaftsraum",
                "voting_principle": "mea",
                "voting_principle_basis": "Teilungserklärung § 10 (Testannahme)",
            },
            headers=h,
        ),
        201,
    )
    mid = meeting["id"]
    assert meeting["minutes_draft_document_id"] is None

    # Without company data no letterhead, hence no draft (nothing is invented).
    assert client.post(f"{H}/meetings/{mid}/protocol-draft", headers=h).status_code == 422
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))

    item = _ok(
        client.post(
            f"{H}/meetings/{mid}/agenda",
            json={"title": "Sanierung Dach", "proposal": "Das Dach wird 2027 saniert."},
            headers=h,
        ),
        201,
    )
    open_item = _ok(
        client.post(f"{H}/meetings/{mid}/agenda", json={"title": "Verschiedenes"}, headers=h), 201
    )
    _ok(client.post(f"{H}/meetings/{mid}/invite", json={"invited_at": "2026-05-29"}, headers=h))
    for no in ("01", "02"):
        _ok(
            client.post(
                f"{H}/meetings/{mid}/attendance",
                json={"contract_id": contracts[no], "present": True},
                headers=h,
            ),
            201,
        )
    _ok(
        client.post(
            f"{H}/meetings/{mid}/attendance",
            json={
                "contract_id": contracts["03"],
                "proxy_contact_id": proxy["id"],
                "proxy_document_id": _doc(client, h, "vollmacht.pdf"),
            },
            headers=h,
        ),
        201,
    )
    for no, choice in [("01", "yes"), ("02", "yes"), ("03", "no")]:
        _ok(
            client.post(
                f"{H}/agenda/{item['id']}/votes",
                json={"contract_id": contracts[no], "choice": choice},
                headers=h,
            ),
            201,
        )
    res = _ok(
        client.post(
            f"{H}/agenda/{item['id']}/announce",
            json={"outcome": "positive", "majority_basis": "einfache Mehrheit der Stimmen"},
            headers=h,
        ),
        201,
    )
    assert res["number"] == 1

    # read only role: no draft; foreign tenant: meeting not visible (RLS)
    reader = bearer(login(client, world, "pd25reader"))
    assert client.post(f"{H}/meetings/{mid}/protocol-draft", headers=reader).status_code == 403
    other = bearer(login(client, world, "pd25other"))
    assert client.post(f"{H}/meetings/{mid}/protocol-draft", headers=other).status_code == 404

    draft = _ok(client.post(f"{H}/meetings/{mid}/protocol-draft", headers=h), 201)
    assert draft["status"] == "draft"
    assert draft["minutes_document_id"] is None
    assert "Versammlungsleitung" in draft["missing"]  # no chair recorded
    assert f"Beschlusstext TOP {open_item['position']}" in draft["missing"]
    assert "Entwurf" in draft["title"]
    document = _ok(client.get(f"/api/v1/documents/{draft['document_id']}", headers=h))
    assert document["mime_type"] == "application/pdf"
    assert document["source"] == "generated"
    pdf = client.get(f"/api/v1/documents/{draft['document_id']}/content", headers=h)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    text = _pdf_text(pdf.content)
    assert "Hausverwaltung Müller GmbH" in text  # tenant letterhead
    assert "Entwurf des Protokolls" in text
    assert "Keine Rechtsfolge" in text
    assert "Protokoll der ordentlichen Eigentümerversammlung" in text
    assert "752 WEG Protokoll" in text
    assert "Datum und Uhrzeit: 20.06.2026, 10:00 Uhr" in text  # Europe/Berlin, not UTC
    assert "Gemeinschaftsraum" in text
    assert "Einladung vom: 29.05.2026" in text
    assert "Wertprinzip" in text
    assert "TOP 1: Sanierung Dach" in text
    assert "Das Dach wird 2027 saniert." in text
    assert "Ja 700, Nein 300, Enthaltung 0" in text
    assert "Abstimmungsergebnis nach Wertprinzip" in text
    assert "Beschluss Nr. 1: angenommen (einfache Mehrheit der Stimmen)" in text
    assert "TOP 2: Verschiedenes" in text
    assert "Ergebnis noch nicht verkündet" in text
    assert "nicht erfasst" in text  # missing proposal and chair are placeholders
    assert "1000 von 1000 Stimmen, 3 von 3 Einheiten" in text
    assert f"Test{RUN}, Protokollant" in text
    assert f"vertreten durch Test{RUN}," in text  # proxy name wraps in the table cell
    assert "Vorsitz des Verwaltungsbeirats" in text

    detail = _ok(client.get(f"{H}/meetings/{mid}", headers=h))
    assert detail["minutes_draft_document_id"] == draft["document_id"]
    assert detail["minutes_document_id"] is None
    # foreign tenant cannot read the draft document
    assert client.get(f"/api/v1/documents/{draft['document_id']}", headers=other).status_code == 404

    # a second draft replaces the draft link only; a signed minutes link is never touched
    again = _ok(client.post(f"{H}/meetings/{mid}/protocol-draft", headers=h), 201)
    assert again["document_id"] != draft["document_id"]
    assert (
        _ok(client.get(f"{H}/meetings/{mid}", headers=h))["minutes_draft_document_id"]
        == (again["document_id"])
    )
