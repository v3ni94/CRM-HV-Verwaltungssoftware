"""GAE-20: /statements/{id}/deadlines and the beat task ``watch_tenant`` with a real snapshot.

Expected values by hand: rental statement 2025 (period_to 31.12.2025), one let unit, orientation
deadline 31.12.2026 (12 months after the period end, from the calculation module). Today
15.11.2026 -> 46 days left, inside the first warning stage (60 days, default).
"""

import asyncio
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m17_operating_costs import _rental_world, _statement

pytestmark = pytest.mark.integration
S = "/api/v1/statements"
SETTINGS = "/api/v1/billing/deadline-settings"
TODAY = date(2026, 11, 15)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"af14-{RUN}", name=f"AF14 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af14b-{RUN}", name=f"AF14B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("af14admin", a, "tenant_admin"),
            ("af14read", a, "read_only"),
            ("af14other", b, "tenant_admin"),
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


async def _watch(settings: Any, tenant_id: Any) -> dict[str, int]:
    from mhvp.billing.deadline_tasks import watch_tenant
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            return await watch_tenant(session, tenant_id, TODAY)
    finally:
        await engine.dispose()


def test_deadlines_with_snapshot_and_watch_tenant(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "af14admin"))
    read = bearer(login(client, world, "af14read"))
    other = bearer(login(client, world, "af14other"))
    w = _rental_world(client, h, "881")
    st = _statement(client, h, w["ledger"])
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Gartenpflege",
                "amount": "120.00",
                "allocation_key_id": w["keys"]["WFL"],
                "basis": "§ 4 Mietvertrag, Nr. 10 BetrKV",
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{S}/{st['id']}/calculate", headers=h))

    # Overview with the real snapshot: one contract, orientation deadline, no delivery yet.
    url = f"{S}/{st['id']}/deadlines"
    data = _ok(client.get(url, headers=h))
    assert data["deadline_orientation"] == "2026-12-31"
    assert len(data["contracts"]) == 1
    row = data["contracts"][0]
    assert row["delivered_at"] is None
    assert row["balance"] == "120.00"
    assert row["unit_number"]
    assert data["notice"]
    assert client.get(url, headers=read).status_code == 200
    assert client.get(url, headers=other).status_code == 404
    assert client.get(f"{url}?x=1", headers=h).status_code == 422

    settings = _settings(database, redis_url)
    # Switch off (default): nothing is checked.
    assert asyncio.run(_watch(settings, world.tenant_a)) == {"checked": 0, "notified": 0}
    # Switch on: one open statement, one notification for the creator; repeat is idempotent.
    _ok(client.put(SETTINGS, json={"watch_enabled": True}, headers=h))
    try:
        first = asyncio.run(_watch(settings, world.tenant_a))
        assert first["checked"] >= 1
        assert first["notified"] >= 1
        notes = _ok(client.get("/api/v1/workspace/notifications?unread=true", headers=h))
        mine = [n for n in notes if n["kind"] == "statement_deadline"]
        assert len(mine) >= 1
        assert "Ohne erfassten Zugang" in (mine[0].get("body") or "")
        again = asyncio.run(_watch(settings, world.tenant_a))
        assert again["notified"] == 0
        assert len(
            [
                n
                for n in _ok(client.get("/api/v1/workspace/notifications?unread=true", headers=h))
                if n["kind"] == "statement_deadline"
            ]
        ) == len(mine)
    finally:
        client.put(SETTINGS, json={"watch_enabled": False}, headers=h)
