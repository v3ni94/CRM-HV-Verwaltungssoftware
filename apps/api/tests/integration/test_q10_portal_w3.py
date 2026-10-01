"""Q10 portal wave 3: document search, sort and bundle download (M25-06), portal_roles
(S16-10). Other tenant: 404, staff account without portal role: 403, bad body: 422."""

import asyncio
import io
import zipfile
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q10a-{RUN}", name=f"Q10 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q10b-{RUN}", name=f"Q10 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("q10admin", a), ("q10adminb", b)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
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


def _released_doc(
    c: TestClient, h: dict[str, str], title: str, entity_id: str, visibility: list[str]
) -> str:
    from tests.integration.test_m21_portal import _doc

    return _doc(c, h, title, "contract", entity_id, visibility)


def _tenant_setup(
    c: TestClient, h: dict[str, str], world: World, no: str
) -> tuple[str, dict[str, str]]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"Q10-Haus {no}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(c, h, f"Vermieter{no}", "company")
    _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    unit = _unit(c, h, prop["id"], "A")
    party, _ = _party(c, h, f"Mieter{no}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    return str(contract["id"]), {"party": party}


def test_documents_search_sort_bundle(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "q10admin"))
    hb = bearer(login(client, world, "q10adminb"))
    contract, meta = _tenant_setup(client, ha, world, "911")
    d1 = _released_doc(client, ha, "Zeta Vertrag", contract, ["tenant"])
    d2 = _released_doc(client, ha, "Alpha Nachweis", contract, ["tenant"])
    hidden = _released_doc(client, ha, "Nur Eigentuemer", contract, ["owner"])
    portal = _portal_user(client, ha, world, "q10res", _contact_of(client, ha, meta["party"]))

    listed = _ok(client.get(f"{P}/documents?sort=title_asc", headers=portal))
    assert [d["title"] for d in listed] == ["Alpha Nachweis", "Zeta Vertrag"]
    assert [d["title"] for d in _ok(client.get(f"{P}/documents?q=zeta", headers=portal))] == [
        "Zeta Vertrag"
    ]
    assert client.get(f"{P}/documents?sort=bogus", headers=portal).status_code == 422

    res = client.post(f"{P}/documents/bundle", json={"document_ids": [d1, d2]}, headers=portal)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        names = archive.namelist()
        assert "INDEX.csv" in names
        assert len(names) == 3
        assert "Zeta Vertrag" in archive.read("INDEX.csv").decode("utf-8-sig")

    # not released, unknown and foreign ids all answer 404 without a hint
    for bad in (hidden, "00000000-0000-7000-8000-000000000000"):
        assert (
            client.post(
                f"{P}/documents/bundle", json={"document_ids": [d1, bad]}, headers=portal
            ).status_code
            == 404
        )
    assert (
        client.post(f"{P}/documents/bundle", json={"document_ids": []}, headers=portal).status_code
        == 422
    )
    assert (
        client.post(
            f"{P}/documents/bundle", json={"document_ids": ["x"]}, headers=portal
        ).status_code
        == 422
    )

    # other tenant's portal user never reaches tenant A documents
    contract_b, meta_b = _tenant_setup(client, hb, world, "912")
    _released_doc(client, hb, "B Dokument", contract_b, ["tenant"])
    portal_b = _portal_user(client, hb, world, "q10resb", _contact_of(client, hb, meta_b["party"]))
    assert (
        client.post(
            f"{P}/documents/bundle", json={"document_ids": [d1]}, headers=portal_b
        ).status_code
        == 404
    )
    assert [d["title"] for d in _ok(client.get(f"{P}/documents", headers=portal_b))] == [
        "B Dokument"
    ]

    # staff account without any portal grant: no documents, bundle refused
    assert client.post(
        f"{P}/documents/bundle", json={"document_ids": [d1]}, headers=ha
    ).status_code in (
        401,
        403,
        404,
    )

    me = _ok(client.get(f"{P}/me", headers=portal))
    assert me["portal_roles"] == ["tenant_resident"]


def test_ticket_external_comments_enforced(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "q10admin"))
    contract, meta = _tenant_setup(client, ha, world, "913")
    portal = _portal_user(client, ha, world, "q10res3", _contact_of(client, ha, meta["party"]))
    unit = _ok(client.get(f"/api/v1/contracts/{contract}", headers=ha))["unit_id"]
    made = _ok(
        client.post(
            f"{P}/tickets",
            json={"title": "Wasserschaden", "description": "Decke feucht", "unit_id": unit},
            headers=portal,
        ),
        201,
    )
    assert (
        client.post(
            f"{P}/tickets/{made['id']}/comments", json={"body": "Hallo"}, headers=portal
        ).status_code
        == 201
    )
    assert [t["comments"] for t in _ok(client.get(f"{P}/tickets", headers=portal))] == [["Hallo"]]
    _ok(
        client.patch(
            f"/api/v1/tickets/{made['id']}", json={"external_comments": "none"}, headers=ha
        )
    )
    assert (
        client.post(
            f"{P}/tickets/{made['id']}/comments", json={"body": "Nochmal"}, headers=portal
        ).status_code
        == 403
    )
    assert [t["comments"] for t in _ok(client.get(f"{P}/tickets", headers=portal))] == [[]]


def _owner_setup(c: TestClient, h: dict[str, str], no: str) -> dict[str, str]:
    weg = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": no, "name": f"Q10-WEG {no}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    unit = _unit(c, h, weg["id"], "01")
    party, _ = _party(c, h, f"Eigentuemer{no}")
    _ok(
        c.post(
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
    )
    return {"party": party, "unit": unit}


def test_owner_statements_scope(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "q10admin"))
    _contract, meta = _tenant_setup(client, ha, world, "914")
    resident = _portal_user(client, ha, world, "q10res4", _contact_of(client, ha, meta["party"]))
    owner_meta = _owner_setup(client, ha, "915")
    owner = _portal_user(client, ha, world, "q10own", _contact_of(client, ha, owner_meta["party"]))
    some = "00000000-0000-7000-8000-000000000001"

    assert client.get(f"{P}/owner/statements", headers=resident).status_code == 403
    assert client.get(
        f"{P}/owner/statements/{some}/units/{some}/pdf", headers=resident
    ).status_code in (
        403,
        404,
    )
    listed = _ok(client.get(f"{P}/owner/statements", headers=owner))
    assert listed["items"] == []
    # own unit unknown statement, foreign unit: never a PDF
    for unit in (owner_meta["unit"], some):
        res = client.get(f"{P}/owner/statements/{some}/units/{unit}/pdf", headers=owner)
        assert res.status_code in (403, 404)
    assert client.get(f"{P}/owner/statements/x/units/{some}/pdf", headers=owner).status_code == 422
    assert _ok(client.get(f"{P}/me", headers=owner))["portal_roles"] == ["owner"]


def test_owner_overview_scope(client: TestClient, world: World) -> None:
    ha = bearer(login(client, world, "q10admin"))
    _contract, meta = _tenant_setup(client, ha, world, "916")
    resident = _portal_user(client, ha, world, "q10res5", _contact_of(client, ha, meta["party"]))
    owner_meta = _owner_setup(client, ha, "917")
    owner = _portal_user(client, ha, world, "q10own2", _contact_of(client, ha, owner_meta["party"]))
    for path in ("allocation-properties", "rental-income", "payment-resolutions"):
        assert client.get(f"{P}/owner/{path}", headers=resident).status_code == 403
    alloc = _ok(client.get(f"{P}/owner/allocation-properties", headers=owner))
    assert [i["unit_id"] for i in alloc["items"]] == [owner_meta["unit"]]
    income = _ok(client.get(f"{P}/owner/rental-income", headers=owner))
    assert income["items"] == []  # no special property administration enabled
    assert _ok(client.get(f"{P}/owner/payment-resolutions", headers=owner))["items"] == []
