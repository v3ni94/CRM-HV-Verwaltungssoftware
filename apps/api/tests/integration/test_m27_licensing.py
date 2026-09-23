"""M27 licence model, usage counters, price list, onboarding and G5 readiness. Expected
values: tenant with 3 units (one fictional helper unit not counted) -> units 2, one active
member -> users 1; quota 2 fits, a later count with quota 1 does not. Prices are test inputs,
no real price list. G5 evidence stays open and the gate stays closed."""

import asyncio
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
P = "/api/v1/platform"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"lic-{RUN}", name=f"Lizenz {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, admin in [("m27admin", False), ("m27padmin", True)]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=admin,
            )
            world.users[name] = uid
            if not admin:
                await services.add_member(
                    factory,
                    tenant_id=a,
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_license_usage_readiness(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "m27admin"))
    ph = bearer(login(client, world, "m27padmin"))
    tenant = str(world.tenant_a)
    assert client.get(f"{P}/price-list", headers=h).status_code == 403  # tenant admin
    lic = {"tenant_id": tenant, "module": "core", "unit_quota": 2, "valid_from": "2031-01-01"}
    early = lic | {"module": "portal", "valid_from": "2000-01-01", "valid_until": "2000-12-31"}
    assert client.post(f"{P}/licenses", json=early, headers=ph).status_code == 422  # no price
    day = (date(2031, 1, 1) + timedelta(days=int(RUN, 36) % 20000)).isoformat()
    _ok(
        client.post(
            f"{P}/price-list",
            json={"module": "core", "price_per_unit": "1.50", "valid_from": day},
            headers=ph,
        ),
        201,
    )
    assert (
        client.post(
            f"{P}/price-list",
            json={"module": "core", "price_per_unit": "2.00", "valid_from": day},
            headers=ph,
        ).status_code
        == 409
    )
    lic["valid_from"] = day
    created = _ok(client.post(f"{P}/licenses", json=lic, headers=ph), 201)
    assert created["price_per_unit"] == "1.50"
    assert client.post(f"{P}/licenses", json=lic, headers=ph).status_code == 409  # overlap

    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "771", "name": "Lizenzhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )["id"]
    for no, fictional in [("01", False), ("02", False), ("99", True)]:
        _ok(
            client.post(
                f"/api/v1/properties/{prop['id']}/units",
                json={
                    "building_id": building,
                    "number": no,
                    "unit_type": "other" if fictional else "apartment",
                    "is_fictional": fictional,
                },
                headers=h,
            ),
            201,
        )
    usage = _ok(client.post(f"{P}/tenants/{tenant}/usage", json={"month": day}, headers=ph))
    assert (usage["month"], usage["units"], usage["users"]) == (day[:8] + "01", 2, 1)
    again = _ok(client.post(f"{P}/tenants/{tenant}/usage", json={"month": day}, headers=ph))
    assert again["units"] == 2  # upsert, one row per month

    ready = _ok(client.get(f"{P}/tenants/{tenant}/readiness", params={"as_of": day}, headers=ph))
    done = {c["item"]: c["done"] for c in ready["checklist"]}
    assert done == {
        "Lizenz Kernmodul gültig": True,
        "Einheiten im Kontingent": True,
        "Benutzer angelegt": True,
        "Objekte erfasst": True,
    }
    assert ready["gates"]["G5"] is False
    assert ready["g5_ready"] is False
    assert all(not e["done"] for e in ready["g5_evidence"])
    before = _ok(
        client.get(f"{P}/tenants/{tenant}/readiness", params={"as_of": "2030-12-31"}, headers=ph)
    )
    assert {c["item"]: c["done"] for c in before["checklist"]}["Lizenz Kernmodul gültig"] is False
    assert client.get(f"{P}/tenants/{tenant}/readiness", headers=h).status_code == 403

    from mhvp.platform.licensing import usage_all_once

    assert asyncio.run(usage_all_once(_settings(database, redis_url)))["counted"] >= 1
