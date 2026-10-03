"""AP17 (welle 26): GAM-108 source and confirmation per allocation key with the tenant switch,
GAM-111 kind and reading date per consumption value. Issuing stays behind G3 (GAM-107 is a
CRM change, the API already requires ``delivered_at``; see test_m17_operating_costs)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m17_heating import _setup

pytestmark = pytest.mark.integration
SETTING = "/api/v1/billing/allocation-key-confirmation-setting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ap17-{RUN}", name=f"AP17 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ap17b-{RUN}", name=f"AP17B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("p17admin", a, "tenant_admin"),
            ("p17read", a, "read_only"),
            ("p17other", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_key_source_confirmation_and_switch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p17admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "917", "name": "Quellenhaus", "management_type": "rental"},
            headers=h,
        ),
        201,
    )["id"]
    keys = _ok(client.get(f"/api/v1/properties/{prop}/allocation-keys", headers=h))
    key = next(k for k in keys if k["code"] == "WFL")
    assert key["confirmed_at"] is None
    assert key["source_kind"] is None
    url = f"/api/v1/properties/{prop}/allocation-keys/{key['id']}"

    # Confirmation needs kind, start of validity and a reference or a document.
    r = client.put(f"{url}/confirmation", json={"confirmed": True}, headers=h)
    assert r.status_code == 422, r.text
    assert client.patch(url, json={"source_kind": "lease"}, headers=h).status_code == 422
    missing_doc = "0192abcd-0000-7000-8000-00000000ffff"
    assert client.patch(url, json={"source_document_id": missing_doc}, headers=h).status_code == 422
    _ok(
        client.patch(
            url,
            json={"source_kind": "declaration_of_division", "source_valid_from": "2020-01-01"},
            headers=h,
        )
    )
    assert client.put(f"{url}/confirmation", json={"confirmed": True}, headers=h).status_code == 422
    _ok(client.patch(url, json={"source_reference": "TE § 7 Abs. 2"}, headers=h))
    confirmed = _ok(client.put(f"{url}/confirmation", json={"confirmed": True}, headers=h))
    assert confirmed["confirmed_at"] is not None
    assert confirmed["confirmed_by"] == str(world.users["p17admin"])

    # Unchanged source keeps the confirmation, a changed source drops it.
    assert _ok(client.patch(url, json={"name": "Wohnfläche"}, headers=h))["confirmed_at"]
    changed = _ok(client.patch(url, json={"source_reference": "TE § 8"}, headers=h))
    assert changed["confirmed_at"] is None
    _ok(client.put(f"{url}/confirmation", json={"confirmed": True}, headers=h))
    withdrawn = _ok(client.put(f"{url}/confirmation", json={"confirmed": False}, headers=h))
    assert withdrawn["confirmed_at"] is None
    assert withdrawn["confirmed_by"] is None

    # Authorization and tenant separation.
    hr = bearer(login(client, world, "p17read"))
    assert (
        client.put(f"{url}/confirmation", json={"confirmed": True}, headers=hr).status_code == 403
    )
    ho = bearer(login(client, world, "p17other"))
    assert (
        client.put(f"{url}/confirmation", json={"confirmed": True}, headers=ho).status_code == 404
    )

    # Tenant switch: default off (behaviour before AP17), read only users cannot change it.
    assert _ok(client.get(SETTING, headers=h)) == {"required": False}
    assert client.put(SETTING, json={"required": True}, headers=hr).status_code == 403
    assert client.put(SETTING, json={"required": "x"}, headers=h).status_code == 422
    assert _ok(client.put(SETTING, json={"required": True}, headers=h)) == {"required": True}
    assert _ok(client.get(SETTING, headers=ho)) == {"required": False}
    assert _ok(client.put(SETTING, json={"required": False}, headers=h)) == {"required": False}


def test_consumption_kind_and_reading_date(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p17admin"))
    st, _ = _setup(client, h)
    hp = f"/api/v1/statements/{st}/heating"
    occ = _ok(client.get(hp, headers=h))["occupants"]
    keys = {o["unit_number"] + o["from"]: o["key"] for o in occ}
    kb = keys["022025-01-01"]
    r = client.put(
        f"{hp}/consumptions",
        json={"consumptions": {kb: {"heating": "600", "heating_kind": "interim"}}},
        headers=h,
    )
    assert r.status_code == 422, r.text
    _ok(
        client.put(
            f"{hp}/consumptions",
            json={
                "consumptions": {
                    kb: {
                        "heating": "600",
                        "heating_kind": "interim",
                        "hot_water": "10",
                        "hot_water_kind": "estimated",
                        "reading_date": "2025-03-31",
                    }
                }
            },
            headers=h,
        )
    )
    row = next(o for o in _ok(client.get(hp, headers=h))["occupants"] if o["key"] == kb)
    assert row["heating_kind"] == "interim"
    assert row["hot_water_kind"] == "estimated"
    assert row["reading_date"] == "2025-03-31"
