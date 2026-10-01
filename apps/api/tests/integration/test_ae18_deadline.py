"""M17-04 deadline settings and overview (API): defaults, validation, permission, 404."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
S = "/api/v1/billing/deadline-settings"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae18-{RUN}", name=f"AE18 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("ae18admin", "tenant_admin"), ("ae18read", "read_only")]:
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


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def test_settings_default_update_validation_permission(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae18admin"))
    r = bearer(login(client, world, "ae18read"))
    cur = client.get(S, headers=h).json()
    assert cur["policy"] == "block_claims"
    assert cur["watch_enabled"] is False
    assert (cur["warn_days_first"], cur["warn_days_second"]) == (60, 30)
    assert client.put(S, json={"policy": "ignore"}, headers=h).status_code == 422
    assert client.put(S, json={"warn_days_first": 0}, headers=h).status_code == 422
    assert client.put(S, json={"policy": "notice"}, headers=r).status_code == 403
    assert client.get(f"{S}?x=1", headers=h).status_code == 422
    out = client.put(S, json={"policy": "notice", "watch_enabled": True}, headers=h).json()
    assert out["policy"] == "notice"
    assert out["watch_enabled"] is True
    client.put(S, json={"policy": "block_claims", "watch_enabled": False}, headers=h)


def test_deadlines_unknown_statement_404(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae18admin"))
    url = f"/api/v1/statements/{uuid.uuid4()}/deadlines"
    assert client.get(url, headers=h).status_code == 404
