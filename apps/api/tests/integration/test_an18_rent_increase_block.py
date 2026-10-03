"""AN18 (GAK-202): payment reason from the basis, blocking date only as proposal from the
tenant switch and set only after confirmation. Expected values by hand: graduated step
650,00 from 01.12.2026 -> new rent line reason ``graduated``; switch graduated = 12 months ->
proposal 01.12.2027; without switch no proposal. The 12 months are a test input, not law."""

import asyncio
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
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
L = "/api/v1/letting"


class OpenG3:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"an18a-{RUN}", name=f"AN18 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"an18b-{RUN}", name=f"AN18b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, roles in (
            ("an18admin", a, ["tenant_admin"]),
            ("an18second", a, ["tenant_admin"]),
            ("an18reader", a, ["read_only"]),
            ("an18other", b, ["tenant_admin"]),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=roles, actor_user_id=None
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
            TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _doc(c: TestClient, h: dict[str, str], name: str) -> str:
    files = {"file": (name, b"%PDF-1.4 test", "application/pdf")}
    return str(_ok(c.post("/api/v1/documents", files=files, headers=h), 201)["id"])


def _contract(client: TestClient, h: dict[str, str], no: str) -> tuple[str, str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": no, "name": "AN18", "management_type": "rental", "city": "Teststadt"},
            headers=h,
        ),
        201,
    )
    landlord, _ = _party(client, h, f"Vermieter{no}", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    unit = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building,
                "number": "01",
                "unit_type": "apartment",
                "living_area_sqm": "60",
                "rooms": "2",
            },
            headers=h,
        ),
        201,
    )["id"]
    tenant, tenant_contact = _party(client, h, f"Mieter{no}")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant,
                "start_date": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"/api/v1/contracts/{contract}/payments",
            json={
                "payment_type_code": "rent",
                "net": "600.00",
                "gross": "600.00",
                "valid_from": "2023-01-01",
            },
            headers=h,
        ),
        201,
    )
    return str(contract), str(unit), str(tenant_contact["id"])


def test_settings_permissions_and_validation(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "an18admin"))
    hr = bearer(login(client, world, "an18reader"))
    assert _ok(client.get(f"{L}/rent-increase-settings", headers=h)) == {
        "block_months": {},
        "proposals": "off",
    }
    body = {"block_months": {"graduated": 12}, "proposals": "off"}
    assert client.put(f"{L}/rent-increase-settings", json=body, headers=hr).status_code == 403
    bad = {"block_months": {"foo": 12}}
    assert client.put(f"{L}/rent-increase-settings", json=bad, headers=h).status_code == 422
    assert (
        client.put(f"{L}/rent-increase-settings", json={"proposals": "auto"}, headers=h).status_code
        == 422
    )
    _ok(client.put(f"{L}/rent-increase-settings", json=body, headers=h))
    ho = bearer(login(client, world, "an18other"))
    assert _ok(client.get(f"{L}/rent-increase-settings", headers=ho))["block_months"] == {}


def test_apply_sets_reason_and_block_proposal(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "an18admin"))
    h2 = bearer(login(client, world, "an18second"))
    gh = bearer(login(gated, world, "an18second"))
    _ok(
        client.put(
            f"{L}/rent-increase-settings",
            json={"block_months": {"graduated": 12}, "proposals": "off"},
            headers=h,
        )
    )
    contract, _, _ = _contract(client, h, "181")
    case = _ok(
        client.post(
            f"{L}/rent-increases",
            json={
                "contract_id": contract,
                "basis": "graduated",
                "effective_date": "2026-12-01",
                "target_rent": "650.00",
                "source_note": "Staffel laut Vertrag (Test)",
                "source_document_id": _doc(client, h, "staffel.pdf"),
                "basis_data": {"steps": [{"valid_from": "2026-12-01", "rent": "650.00"}]},
            },
            headers=h,
        ),
        201,
    )
    assert case["check"]["ok"] is True, case["check"]
    act = f"{L}/rent-increases/{case['id']}/actions"
    assert (
        client.post(
            act, json={"action": "set_block", "block_until": "2027-12-01"}, headers=h
        ).status_code
        == 409
    )
    _ok(client.post(act, json={"action": "approve"}, headers=h2))
    _ok(
        gated.post(
            act, json={"action": "send", "document_id": _doc(client, h, "p.pdf")}, headers=gh
        )
    )
    _ok(
        client.post(
            act, json={"action": "consent", "document_id": _doc(client, h, "z.pdf")}, headers=h
        )
    )
    applied = _ok(client.post(act, json={"action": "apply"}, headers=h))
    assert applied["check"]["block_proposal"] == "2027-12-01"
    pays = _ok(client.get(f"/api/v1/contracts/{contract}/payments", headers=h))
    new = [p for p in pays if p["valid_from"] == "2026-12-01"]
    assert [p["reason"] for p in new] == ["graduated"]
    # Not set automatically; only the confirmation writes the contract.
    assert (
        _ok(client.get(f"/api/v1/contracts/{contract}", headers=h))["rent_increase_block_until"]
        is None
    )
    assert client.post(act, json={"action": "set_block"}, headers=h).status_code == 422
    early = {"action": "set_block", "block_until": "2026-11-30"}
    assert client.post(act, json=early, headers=h).status_code == 422
    ho = bearer(login(client, world, "an18other"))
    assert (
        client.post(
            act, json={"action": "set_block", "block_until": "2027-12-01"}, headers=ho
        ).status_code
        == 404
    )
    done = _ok(
        client.post(act, json={"action": "set_block", "block_until": "2027-12-01"}, headers=h)
    )
    assert done["status"] == "applied"
    assert done["check"]["block_set"] == "2027-12-01"
    got = _ok(client.get(f"/api/v1/contracts/{contract}", headers=h))
    assert got["rent_increase_block_until"] == "2027-12-01"


def test_prospect_delete_creates_erasure_proposal(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """GAK-201: the contact of a deleted prospect is only proposed for erasure, with the
    linked documents named; a contact with a further role (tenant) gets no proposal."""
    client, _ = clients
    h = bearer(login(client, world, "an18admin"))
    _, unit, tenant_contact = _contract(client, h, "182")
    _, lone = _party(client, h, "Interessent18")
    ids = []
    for contact in (lone["id"], tenant_contact):
        body = {"unit_id": unit, "contact_id": contact, "delete_after": "2027-03-31"}
        ids.append(_ok(client.post(f"{L}/prospects", json=body, headers=h), 201)["id"])
    ho = bearer(login(client, world, "an18other"))
    assert client.delete(f"{L}/prospects/{ids[0]}", headers=ho).status_code == 404
    hr = bearer(login(client, world, "an18reader"))
    assert client.delete(f"{L}/prospects/{ids[0]}", headers=hr).status_code == 403
    for pid in ids:
        assert client.delete(f"{L}/prospects/{pid}", headers=h).status_code == 204
    requests = _ok(client.get("/api/v1/privacy/erasure-requests", headers=h))
    mine = [r for r in requests if r["contact_id"] in (lone["id"], tenant_contact)]
    assert [(r["contact_id"], r["status"]) for r in mine] == [(lone["id"], "proposed")]
    assert "GAK-201" in mine[0]["reason"]
    assert "Verknüpfte Dokumente: 0" in mine[0]["reason"]
    contact = _ok(client.get(f"/api/v1/contacts/{lone['id']}", headers=h))
    assert contact["id"] == lone["id"]  # not deleted
