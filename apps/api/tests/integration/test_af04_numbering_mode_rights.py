"""GAE-10 (AE04, AE40-02): the tenant wide numbering mode of rent invoice drafts is a tenant
setting. ``contracts:update`` alone (role ``standard``) may read but not change it (403);
``tenant_settings:update`` (tenant admin) changes it, every reader sees the new mode."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
URL = "/api/v1/accounting/rent-invoices/numbering-mode"


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"af04-{RUN}", name=f"AF04 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af04b-{RUN}", name=f"AF04b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("af04admin", a, "tenant_admin"),
            ("af04clerk", a, "standard"),
            ("af04reader", a, "read_only"),
            ("af04other", b, "tenant_admin"),
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


def test_numbering_mode_rights_and_display(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "af04admin"))
    clerk = bearer(login(client, world, "af04clerk"))
    reader = bearer(login(client, world, "af04reader"))
    other = bearer(login(client, world, "af04other"))
    for h in (admin, clerk, reader):
        got = client.get(URL, headers=h)
        assert got.status_code == 200, got.text
        assert got.json()["mode"] == "draft_numbers"
        assert "regular_numbers" in got.json()["modes"]
    body = {"mode": "regular_numbers"}
    for h in (clerk, reader):  # contracts:update is no tenant setting right
        denied = client.put(URL, json=body, headers=h)
        assert denied.status_code == 403, denied.text
    assert client.put(URL, json={"mode": "x"}, headers=admin).status_code == 422
    assert client.put(URL, json=body).status_code == 401
    changed = client.put(URL, json=body, headers=admin)
    assert changed.status_code == 200, changed.text
    assert changed.json()["mode"] == "regular_numbers"
    assert client.get(URL, headers=clerk).json()["mode"] == "regular_numbers"
    assert client.get(URL, headers=other).json()["mode"] == "draft_numbers"  # tenant separation
