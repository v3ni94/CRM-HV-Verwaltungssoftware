"""AJ32: contract creation with contact_id instead of party_id (production bug of the CRM
contract form, which sends the contact id) and GET /sepa-mandates?contact_id=. Expected
values fixed by hand; rows are invented."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
IBAN_A = "DE02120300000000202051"
IBAN_B = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aj32-{RUN}", name=f"AJ32 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aj32b-{RUN}", name=f"AJ32b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("aj32admin", a, "tenant_admin"),
            ("aj32approver", a, "tenant_admin"),
            ("aj32other", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _contact(
    c: TestClient, h: dict[str, str], name: str, kind: str = "person", iban: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = (
        {"kind": "company", "company_name": f"{name} {RUN} GmbH"}
        if kind == "company"
        else {"kind": "person", "first_name": name, "last_name": f"Test{RUN}"}
    )
    if iban:
        body["bank_accounts"] = [{"iban": iban, "valid_from": "2020-01-01"}]
    return _ok(c.post("/api/v1/contacts", json=body, headers=h))  # type: ignore[no-any-return]


def _party(c: TestClient, h: dict[str, str], contact_id: str) -> str:
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": contact_id}]}, headers=h)
    )
    return str(party["id"])


def _rental_unit(c: TestClient, h: dict[str, str], number: str) -> tuple[str, str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"Objekt {number}",
                "management_type": "rental",
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    building = _ok(
        c.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h)
    )
    unit = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": building["id"],
                "number": "01",
                "label": "WE 01",
                "unit_type": "apartment",
            },
            headers=h,
        )
    )
    owner = _contact(c, h, f"Vermieter{number}", "company")
    entity = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": _party(c, h, owner["id"]), "valid_from": "2020-01-01"},
            headers=h,
        )
    )["legal_entity_id"]
    return str(unit["id"]), str(entity)


def test_contract_by_contact_id_and_validation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "aj32admin"))
    unit, _ = _rental_unit(client, h, "321")
    tenant = _contact(client, h, "Mieter")
    body = {"kind": "tenancy", "unit_id": unit, "start_date": "2026-01-01"}

    created = _ok(
        client.post("/api/v1/contracts", json={**body, "contact_id": tenant["id"]}, headers=h)
    )
    party = _ok(client.get(f"/api/v1/parties/{created['party_id']}", headers=h), 200)
    assert [m["contact_id"] for m in party["members"]] == [tenant["id"]]

    both = client.post(
        "/api/v1/contracts",
        json={**body, "contact_id": tenant["id"], "party_id": created["party_id"]},
        headers=h,
    )
    assert both.status_code == 422, both.text
    neither = client.post("/api/v1/contracts", json=body, headers=h)
    assert neither.status_code == 422, neither.text
    unknown = client.post(
        "/api/v1/contracts",
        json={**body, "contact_id": "0190a000-0000-7000-8000-000000000032"},
        headers=h,
    )
    assert unknown.status_code == 404, unknown.text
    # Tenant separation: the contact of tenant A is unknown in tenant B.
    other = bearer(login(client, world, "aj32other"))
    foreign = client.post(
        "/api/v1/contracts", json={**body, "contact_id": tenant["id"]}, headers=other
    )
    assert foreign.status_code == 404, foreign.text


def test_mandates_filtered_by_contact(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "aj32admin"))
    _, entity = _rental_unit(client, h, "322")
    a = _contact(client, h, "Zahlera", iban=IBAN_A)
    b = _contact(client, h, "Zahlerb", iban=IBAN_B)
    third = _contact(client, h, "Dritter")
    approver = bearer(login(client, world, "aj32approver"))
    approve_bank_accounts(client, approver, a["id"])
    approve_bank_accounts(client, approver, b["id"])
    ids = {}
    for key, contact in (("a", a), ("b", b)):
        mandate = _ok(
            client.post(
                "/api/v1/sepa-mandates",
                json={
                    "party_id": _party(client, h, contact["id"]),
                    "legal_entity_id": entity,
                    "contact_bank_account_id": contact["bank_accounts"][0]["id"],
                    "reference": f"AJ32{key}{RUN}"[:35],
                    "creditor_id": "DE98ZZZ09999999999",
                    "signed_at": "2026-01-01",
                    "document_id": "0190a000-0000-7000-8000-000000000001",
                },
                headers=h,
            )
        )
        ids[key] = mandate["id"]
    rows = _ok(client.get(f"/api/v1/sepa-mandates?contact_id={a['id']}", headers=h), 200)
    assert [r["id"] for r in rows] == [ids["a"]]
    rows = _ok(client.get(f"/api/v1/sepa-mandates?contact_id={b['id']}", headers=h), 200)
    assert [r["id"] for r in rows] == [ids["b"]]
    assert _ok(client.get(f"/api/v1/sepa-mandates?contact_id={third['id']}", headers=h), 200) == []
