"""Units: natural order of numbers and current owner/tenant per unit (Betreiberauftrag 26.09.2026)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _ok, _party, _payment, _property

pytestmark = pytest.mark.integration
DAY = "2026-09-26"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"uo-{RUN}", name=f"Einheiten {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("uoadmin"), display_name="uoadmin", password=PASSWORD
        )
        world.users["uoadmin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def test_units_natural_order_and_occupants(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "uoadmin"))
    prop = _property(client, h, "591", "hoa_with_sev")
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h)
    )
    ids: dict[str, str] = {}
    for number in ["10", "2", "1", "WE10", "WE2"]:
        ids[number] = _ok(
            client.post(
                f"/api/v1/properties/{prop['id']}/units",
                json={"building_id": building["id"], "number": number, "unit_type": "apartment"},
                headers=h,
            )
        )["id"]

    listing = _ok(client.get(f"/api/v1/properties/{prop['id']}/units", headers=h), 200)
    assert [u["number"] for u in listing] == ["1", "2", "10", "WE2", "WE10"]
    assert all(u["owner"] is None and u["tenant"] is None for u in listing)

    seller, _ = _party(client, h, "Verkaeuferin")
    buyer, buyer_contact = _party(client, h, "Kaeufer")
    tenant, tenant_contact = _party(client, h, "Mieterin")
    ownership = {
        "kind": "ownership",
        "unit_id": ids["1"],
        "party_id": seller,
        "start_date": "2020-01-01",
        "title_transfer_date": "2020-01-01",
        "acquisition_kind": "first_acquisition",
        "sev_enabled": True,
    }
    first = _ok(client.post("/api/v1/contracts", json=ownership, headers=h))
    _ok(
        client.post(
            f"/api/v1/contracts/{first['id']}/ownership-transfer",
            json={
                "new_party_id": buyer,
                "title_transfer_date": "2026-04-01",
                "acquisition_kind": "purchase",
            },
            headers=h,
        )
    )
    _ok(client.post("/api/v1/contracts", json={**ownership, "unit_id": ids["2"]}, headers=h))
    lease = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": ids["1"],
                "party_id": tenant,
                "start_date": "2024-01-01",
            },
            headers=h,
        )
    )
    pay = f"/api/v1/contracts/{lease['id']}/payments"
    _ok(client.post(pay, json=_payment("800.00", "800.00", "2024-01-01"), headers=h))
    _ok(
        client.post(
            pay,
            json=_payment("150.00", "150.00", "2024-01-01", "operating_cost_advance"),
            headers=h,
        )
    )

    rows = _ok(
        client.get(
            f"/api/v1/properties/{prop['id']}/units",
            params={"with_occupants": "true", "as_of": DAY},
            headers=h,
        ),
        200,
    )
    by_number = {u["number"]: u for u in rows}
    one = by_number["1"]
    assert one["owner"]["party_id"] == buyer
    assert one["owner"]["members"][0]["contact_id"] == buyer_contact["id"]
    assert one["tenant"]["party_id"] == tenant
    assert one["tenant"]["members"][0]["display_name"] == tenant_contact["display_name"]
    assert float(one["tenant"]["rent_gross"]) == 950.0
    assert by_number["2"]["owner"]["party_id"] == seller
    assert by_number["2"]["tenant"] is None
    assert by_number["10"]["owner"] is None

    occ = _ok(
        client.get(f"/api/v1/units/{ids['1']}/occupants", params={"as_of": DAY}, headers=h), 200
    )
    assert occ["owner"]["party_id"] == buyer
    assert occ["tenant"]["contract_id"] == lease["id"]
    assert [o["party_id"] for o in occ["history"]] == [seller]
    assert occ["history"][0]["end_date"] == "2026-03-31"
    empty = _ok(client.get(f"/api/v1/units/{ids['10']}/occupants", headers=h), 200)
    assert empty == {"owner": None, "tenant": None, "history": []}
