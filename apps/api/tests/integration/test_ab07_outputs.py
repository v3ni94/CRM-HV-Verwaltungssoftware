"""AB07: letter dispatch of the asset report (GA07-02 rest), special acquisition cases with
release step (GA07-03) and filed outputs of statements (GA06-02, GA06-03).

Expected values (hand derived):
* Asset report of an empty WEG ledger, issued. Unit 01 owner retrieved the report in the
  portal, unit 02 owner did not. The dispatch with default settings creates exactly one letter
  (unit 02, channel from the tenant default ``post``) and skips unit 01
  (``retrieved_in_portal``); a second call skips unit 02 as ``already_dispatched``. The
  provision log shows the dispatch at unit 02 and none at unit 01. G4 closed: 403.
* Statement year 2026: first acquisition (unit 01), forced sale (unit 02) and a purchase with
  special succession liability (unit 03) each produce one ``acquisition_unreleased`` finding
  (3 in total) until requested by one and released by a second person; a plain purchase
  (unit 04) produces none.
* Owner statement and operating cost statement of an empty rental ledger: previews carry the
  marking "Text nicht freigegeben"; filing needs G3 (403 closed) and links the documents to
  the run (letter and § 35a proof: 2 documents, info sheet: 1 document).
"""

import asyncio
import io
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m17_operating_costs import _rental_world
from tests.integration.test_m21_portal_owner import _ok, _portal_user
from tests.integration.test_m24_hoa import _hoa_ledger

pytestmark = pytest.mark.integration
H = "/api/v1/hoa"
P = "/api/v1/portal"
O = "/api/v1/billing/owner-statements"  # noqa: E741
S = "/api/v1/statements"
ADDRESS = {
    "street": "Rheinpromenade",
    "house_number": "13",
    "postal_code": "40789",
    "city": "Monheim",
}


class OpenGates:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G3, ReleaseGate.G4)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ab07a-{RUN}", name=f"AB07 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ab07b-{RUN}", name=f"AB07 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ab07first", a, "tenant_admin"),
            ("ab07second", a, "tenant_admin"),
            ("ab07reader", a, "read_only"),
            ("ab07other", b, "tenant_admin"),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenGates())) as open_,
        ):
            yield closed, open_


def _owner(c: TestClient, h: dict[str, str], name: str) -> tuple[str, str]:
    contact = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": name,
                "last_name": f"Test{RUN}",
                "addresses": [ADDRESS],
            },
            headers=h,
        ),
        201,
    )
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h),
        201,
    )
    return str(party["id"]), str(contact["id"])


def _ownership(
    c: TestClient, h: dict[str, str], unit: str, party: str, start: str, kind: str, **extra: Any
) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": start,
                "title_transfer_date": start,
                "acquisition_kind": kind,
                **extra,
            },
            headers=h,
        ),
        201,
    )


def _text(pdf: bytes) -> str:
    from pypdf import PdfReader

    return " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def test_asset_report_letter_dispatch_and_provision_log(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    closed, gated = clients
    h = bearer(login(closed, world, "ab07first"))
    hr = bearer(login(closed, world, "ab07reader"))
    ho = bearer(login(closed, world, "ab07other"))
    _ok(closed.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    w = _hoa_ledger(closed, h, "981")
    u1, u2 = _unit(closed, h, w["property"], "01"), _unit(closed, h, w["property"], "02")
    p1, c1 = _owner(closed, h, "AB07Portal")
    p2, c2 = _owner(closed, h, "AB07Brief")
    k1 = _ownership(closed, h, u1, p1, "2020-01-01", "purchase")
    k2 = _ownership(closed, h, u2, p2, "2020-01-01", "purchase")
    owner = _portal_user(closed, h, world, "ab07owner", c1)

    rid = _ok(
        closed.post(
            f"{H}/asset-reports", json={"ledger_id": w["ledger"], "as_of": "2025-12-31"}, headers=h
        ),
        201,
    )["id"]
    _ok(closed.post(f"{H}/asset-reports/{rid}/calculate", headers=h))
    # not issued yet: conflict (gate open), gate closed: 403 first
    assert gated.post(f"{H}/asset-reports/{rid}/dispatch", json={}, headers=h).status_code == 409
    assert closed.post(f"{H}/asset-reports/{rid}/dispatch", json={}, headers=h).status_code == 403
    _ok(gated.post(f"{H}/asset-reports/{rid}/transition", json={"target": "issued"}, headers=h))
    assert gated.get(f"{P}/owner/asset-reports/{rid}/pdf", headers=owner).status_code == 200

    # authorization, validation, tenant separation
    assert gated.post(f"{H}/asset-reports/{rid}/dispatch", json={}, headers=hr).status_code == 403
    assert gated.post(f"{H}/asset-reports/{rid}/dispatch", json={}, headers=ho).status_code == 404
    bad = gated.post(f"{H}/asset-reports/{rid}/dispatch", json={"channel": "fax"}, headers=h)
    assert bad.status_code == 422

    done = _ok(gated.post(f"{H}/asset-reports/{rid}/dispatch", json={}, headers=h), 201)
    assert [(i["unit_number"], i["contact_id"], i["channel"]) for i in done["created"]] == [
        ("02", c2, "post")
    ]
    assert [(s["unit_number"], s["reason"]) for s in done["skipped"]] == [
        ("01", "retrieved_in_portal")
    ]
    again = _ok(gated.post(f"{H}/asset-reports/{rid}/dispatch", json={}, headers=h), 201)
    assert again["created"] == []
    assert {(s["unit_number"], s["reason"]) for s in again["skipped"]} == {
        ("01", "retrieved_in_portal"),
        ("02", "already_dispatched"),
    }

    log = _ok(closed.get(f"{H}/asset-reports/{rid}/provisions", headers=h))
    by_unit = {i["unit_number"]: i for i in log["items"]}
    assert by_unit["01"]["contract_id"] == k1["id"]
    assert by_unit["01"]["dispatches"] == []
    assert by_unit["01"]["retrievals"] == 1
    assert by_unit["02"]["contract_id"] == k2["id"]
    assert by_unit["02"]["retrievals"] == 0
    assert [(d["contact_id"], d["channel"]) for d in by_unit["02"]["dispatches"]] == [(c2, "post")]
    assert log["dispatch_note"]
    pdf = closed.get(
        f"/api/v1/documents/{by_unit['02']['dispatches'][0]['document_id']}/download", headers=h
    )
    if pdf.status_code == 200:
        assert "Vermögensbericht" in _text(pdf.content)


def test_special_cases_first_acquisition_foreclosure_succession(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    c, _ = clients
    h1 = bearer(login(c, world, "ab07first"))
    h2 = bearer(login(c, world, "ab07second"))
    w = _hoa_ledger(c, h1, "982")
    units = {n: _unit(c, h1, w["property"], n) for n in ("01", "02", "03", "04")}
    cases = {
        "01": ("first_acquisition", {}),
        "02": ("foreclosure", {}),
        "03": ("purchase", {"special_succession_liability": True}),
        "04": ("purchase", {}),
    }
    contracts = {}
    for number, (kind, extra) in cases.items():
        party, _ = _party(c, h1, f"AB07Fall{number}")
        contracts[number] = _ownership(c, h1, units[number], party, "2026-04-01", kind, **extra)
    sid = _ok(
        c.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2026}, headers=h1), 201
    )["id"]

    def blocking() -> list[str]:
        pkg = _ok(c.get(f"{H}/statements/{sid}/package", headers=h1))
        return [f["detail"] for f in pkg["blocking"] if f["code"] == "acquisition_unreleased"]

    details = blocking()
    assert len(details) == 3
    assert any("Ersterwerb" in d for d in details)
    assert any("Zwangsversteigerung" in d for d in details)
    assert any("Sonderrechtsnachfolge" in d for d in details)
    items = {
        i["unit_number"]: i
        for i in _ok(c.get(f"{H}/statements/{sid}/acquisitions", headers=h1))["items"]
    }
    assert set(items) == {"01", "02", "03"}
    assert items["01"]["case_label"] == "Ersterwerb"
    assert items["02"]["case_label"] == "Zwangsversteigerung"
    assert items["03"]["case_label"] == "Sonderrechtsnachfolge"
    assert "Zuschlagsbeschluss" in items["02"]["allocation_proposal"]
    assert items["03"]["special_succession_liability"] is True

    for number in ("01", "02", "03"):
        base = f"{H}/statements/{sid}/acquisitions/{contracts[number]['id']}"
        _ok(c.post(f"{base}/request", json={"note": "Unterlagen liegen vor"}, headers=h1), 201)
        assert c.post(f"{base}/release", json={"note": "geprüft"}, headers=h1).status_code == 409
        assert _ok(c.post(f"{base}/release", json={"note": "geprüft"}, headers=h2))["status"] == (
            "released"
        )
    assert blocking() == []
    base4 = f"{H}/statements/{sid}/acquisitions/{contracts['04']['id']}"
    assert c.post(f"{base4}/request", json={}, headers=h1).status_code == 404


def test_owner_statement_and_info_sheet_outputs(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    closed, gated = clients
    h1 = bearer(login(closed, world, "ab07first"))
    h2 = bearer(login(closed, world, "ab07second"))
    hr = bearer(login(closed, world, "ab07reader"))
    ho = bearer(login(closed, world, "ab07other"))
    _ok(closed.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h1))
    w = _rental_world(closed, h1, "983")

    # owner statement: preview of letter and § 35a proof, filing behind G3
    st = _ok(
        closed.post(
            O,
            json={"ledger_id": w["ledger"], "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h1,
        ),
        201,
    )
    oid = st["id"]
    assert closed.get(f"{O}/{oid}/preview/letter", headers=h1).status_code == 409
    _ok(closed.post(f"{O}/{oid}/calculate", headers=h1))
    for part in ("letter", "s35a"):
        res = closed.get(f"{O}/{oid}/preview/{part}", headers=hr)
        assert res.status_code == 200, res.text
        assert "Text nicht freigegeben" in _text(res.content)
    assert closed.get(f"{O}/{oid}/preview/other", headers=h1).status_code == 422
    assert closed.get(f"{O}/{oid}/preview/letter", headers=ho).status_code == 404
    assert closed.post(f"{O}/{oid}/outputs", headers=h1).status_code == 403  # G3 closed
    assert gated.post(f"{O}/{oid}/outputs", headers=h1).status_code == 409  # not approved
    _ok(closed.post(f"{O}/{oid}/approve", headers=h2))
    assert gated.post(f"{O}/{oid}/outputs", headers=hr).status_code == 403
    filed = _ok(gated.post(f"{O}/{oid}/outputs", headers=h1), 201)
    assert [i["part"] for i in filed["items"]] == ["letter", "s35a"]
    assert filed["text_status"] == "Text nicht freigegeben"
    listed = _ok(closed.get(f"{O}/{oid}/outputs", headers=hr))["items"]
    assert [i["origin"] for i in listed] == ["owner_statement_letter", "owner_statement_s35a"]
    assert closed.get(f"{O}/{oid}/outputs", headers=ho).status_code == 404

    # operating cost statement: info sheet filed and linked to the run
    sid = _ok(
        closed.post(
            S,
            json={"ledger_id": w["ledger"], "period_from": "2025-01-01", "period_to": "2025-12-31"},
            headers=h1,
        ),
        201,
    )["id"]
    item = {
        "label": "Gartenpflege",
        "amount": "120.00",
        "allocation_key_id": w["keys"]["WFL"],
        "basis": "Mietvertrag",
    }
    _ok(closed.post(f"{S}/{sid}/cost-items", json=item, headers=h1), 201)
    _ok(closed.post(f"{S}/{sid}/calculate", headers=h1))
    preview = closed.post(f"{S}/{sid}/info-sheet/preview", headers=h1)
    assert preview.status_code == 200, preview.text
    assert "Text nicht freigegeben" in _text(preview.content)
    assert closed.post(f"{S}/{sid}/info-sheet", headers=h1).status_code == 403
    assert gated.post(f"{S}/{sid}/info-sheet", headers=hr).status_code == 403
    assert gated.post(f"{S}/{sid}/info-sheet", headers=ho).status_code == 404
    sheet = _ok(gated.post(f"{S}/{sid}/info-sheet", headers=h1), 201)
    items = _ok(closed.get(f"{S}/{sid}/outputs", headers=hr))["items"]
    assert [(i["document_id"], i["origin"]) for i in items] == [
        (sheet["document_id"], "billing_info_sheet")
    ]
    assert closed.get(f"{S}/{sid}/outputs", headers=ho).status_code == 404
