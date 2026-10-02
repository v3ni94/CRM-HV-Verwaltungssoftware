"""AG03 (GAC-07): the system role insurance_broker holds insurance:read and claims:read only
while the tenant switch insurance_broker_access is on (default off)."""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
URL = "/api/v1/tenant/settings"


async def _world(settings: object) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)  # type: ignore[arg-type]
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag03-{RUN}", name=f"AG03 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())  # type: ignore[attr-defined]
        for name, role in (("ag03admin", "tenant_admin"), ("ag03broker", "insurance_broker")):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as c:
        yield c


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(base_settings(database, redis_url)))


def _perms(client: TestClient, world: World, name: str) -> set[str]:
    tokens = login(client, world, name)
    me = client.get("/api/v1/auth/me", headers=bearer(tokens))
    assert me.status_code == 200, me.text
    return set(me.json()["permissions"])


def test_broker_has_no_rights_by_default(client: TestClient, world: World) -> None:
    assert _perms(client, world, "ag03broker") == set()
    admin = login(client, world, "ag03admin")
    got = client.get(URL, headers=bearer(admin))
    assert got.json()["insurance_broker_access"] is False


def test_switch_grants_and_withdraws_broker_rights(client: TestClient, world: World) -> None:
    admin = login(client, world, "ag03admin")
    on = client.patch(URL, json={"insurance_broker_access": True}, headers=bearer(admin))
    assert on.status_code == 200, on.text
    assert on.json()["insurance_broker_access"] is True
    assert _perms(client, world, "ag03broker") == {"insurance:read", "claims:read"}
    off = client.patch(URL, json={"insurance_broker_access": False}, headers=bearer(admin))
    assert off.json()["insurance_broker_access"] is False
    assert _perms(client, world, "ag03broker") == set()


def test_broker_cannot_change_switch_and_value_is_validated(
    client: TestClient, world: World
) -> None:
    broker = login(client, world, "ag03broker")
    assert (
        client.patch(
            URL, json={"insurance_broker_access": True}, headers=bearer(broker)
        ).status_code
        == 403
    )
    admin = login(client, world, "ag03admin")
    bad = client.patch(URL, json={"insurance_broker_access": "vielleicht"}, headers=bearer(admin))
    assert bad.status_code == 422
