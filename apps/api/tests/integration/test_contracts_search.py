"""Contract list context and free text search (operator feedback 28.09.2026): each row of
``GET /contracts`` carries property number, name and address, unit and the contacts behind the
party (tenants, owners); ``q`` searches contact and party names, property number, name and
address, unit and contract number. Word order does not matter, every word must match.

Expected values are fixed here: tenant "Anna Kowalczyk" rents unit 01 of property 811
(Rheinpromenade 13, Monheim am Rhein), owner company "Eigentum Brandt" holds unit 02 of WEG
property 812; the foreign tenant has a tenant of the same surname that must never appear."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _property, _unit

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"csa-{RUN}", name=f"Suche A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"csb-{RUN}", name=f"Suche B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("csadmin", a, "tenant_admin"),
            ("cscaretaker", a, "caretaker"),
            ("csother", b, "tenant_admin"),
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


def _party(c: TestClient, h: dict[str, str], contact: dict[str, Any]) -> tuple[str, str]:
    created = _ok(c.post("/api/v1/contacts", json=contact, headers=h))
    party = _ok(
        c.post("/api/v1/parties", json={"members": [{"contact_id": created["id"]}]}, headers=h)
    )
    return str(party["id"]), str(created["id"])


def _owner(c: TestClient, h: dict[str, str], prop_id: str) -> None:
    owner, _ = _party(c, h, {"kind": "company", "company_name": f"Vermieter {RUN} GmbH"})
    _ok(
        c.post(
            f"/api/v1/properties/{prop_id}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        )
    )


def _contract(c: TestClient, h: dict[str, str], kind: str, unit: str, party: str) -> str:
    body = {"kind": kind, "unit_id": unit, "party_id": party, "start_date": "2026-01-01"}
    if kind == "ownership":
        body |= {"title_transfer_date": "2026-01-01", "acquisition_kind": "first_acquisition"}
    return str(_ok(c.post("/api/v1/contracts", json=body, headers=h))["id"])


def _ids(c: TestClient, h: dict[str, str], q: str, **extra: str) -> set[str]:
    rows = _ok(c.get("/api/v1/contracts", params={"q": q, **extra}, headers=h), 200)
    return {r["id"] for r in rows}


def test_contract_list_context_and_search(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "csadmin"))
    rental = _property(client, h, "811", "rental")
    _owner(client, h, rental["id"])
    weg = _property(client, h, "812", "hoa")
    unit_a = _unit(client, h, rental["id"], "01")
    unit_b = _unit(client, h, weg["id"], "02")
    surname = f"Kowalczyk{RUN}"
    tenant, tenant_contact = _party(
        client, h, {"kind": "person", "first_name": "Anna", "last_name": surname}
    )
    owner, owner_contact = _party(
        client, h, {"kind": "company", "company_name": f"Eigentum Brandt {RUN}"}
    )
    tenancy = _contract(client, h, "tenancy", unit_a, tenant)
    ownership = _contract(client, h, "ownership", unit_b, owner)

    # Other tenant: same surname, never visible to tenant A.
    ho = bearer(login(client, world, "csother"))
    foreign_prop = _property(client, ho, "811", "rental")
    _owner(client, ho, foreign_prop["id"])
    foreign_unit = _unit(client, ho, foreign_prop["id"], "01")
    foreign_party, _ = _party(
        client, ho, {"kind": "person", "first_name": "Anna", "last_name": surname}
    )
    foreign = _contract(client, ho, "tenancy", foreign_unit, foreign_party)

    # Row context: property, unit and the contact behind the party.
    rows = {r["id"]: r for r in _ok(client.get("/api/v1/contracts", headers=h), 200)}
    row = rows[tenancy]
    assert row["property_number"] == "811"
    assert row["property_name"] == "Objekt 811"
    assert row["property_address"] == "Rheinpromenade 13, 40789 Monheim am Rhein"
    assert row["unit_number"] == "01"
    assert row["unit_label"] == "WE 01"
    assert [m["contact_id"] for m in row["members"]] == [tenant_contact]
    assert row["members"][0]["name"] == f"{surname}, Anna"
    assert rows[ownership]["members"][0]["contact_id"] == owner_contact
    assert foreign not in rows

    # Search by tenant name (case insensitive, several words in any order), owner name,
    # property number, address and unit.
    assert _ids(client, h, surname.lower()) == {tenancy}
    assert _ids(client, h, f"anna {surname.upper()}") == {tenancy}
    assert _ids(client, h, f"brandt {RUN}") == {ownership}
    assert _ids(client, h, "811") == {tenancy}
    assert _ids(client, h, "812") == {ownership}
    assert _ids(client, h, "rheinpromenade") >= {tenancy, ownership}
    assert _ids(client, h, "WE 02") >= {ownership}
    # Words match in any order and in every field: when the run id itself contains "02"
    # (surname ``Kowalczyk<RUN>``), the tenancy legitimately matches too, so the negative
    # check only holds for run ids without that digit pair.
    if "02" not in RUN:
        assert tenancy not in _ids(client, h, "WE 02")
    assert _ids(client, h, "keintreffer%_") == set()
    # Existing filters still combine with the search.
    assert _ids(client, h, "rheinpromenade", kind="tenancy") >= {tenancy}
    assert ownership not in _ids(client, h, "rheinpromenade", kind="tenancy")
    assert _ids(client, h, surname, property_id=weg["id"]) == set()
    # Pagination headers unchanged.
    paged = client.get("/api/v1/contracts", params={"q": surname, "page_size": 1}, headers=h)
    assert paged.status_code == 200
    assert paged.headers["X-Total-Count"] == "1"

    # Tenant separation: B finds only its own contract with the same surname.
    assert _ids(client, ho, surname) == {foreign}
    assert _ids(client, ho, "brandt") == set()

    # Authorization: caretaker has no contracts:read; overlong search is a validation error.
    hc = bearer(login(client, world, "cscaretaker"))
    assert client.get("/api/v1/contracts", params={"q": surname}, headers=hc).status_code == 403
    assert client.get("/api/v1/contracts", params={"q": "x" * 201}, headers=h).status_code == 422
