"""S12-05 (Welle 6, U06): POST /tickets/bulk als Sammelaktion für Status, Bearbeiter, Team und
Priorität mit Teilerfolgsbericht; bulk-status bleibt als Alias."""

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


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"u6-{RUN}", name=f"U06 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"u6b-{RUN}", name=f"U06B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("u6admin", "tenant_admin", a),
            ("u6reader", "read_only", a),
            ("u6otherb", "tenant_admin", b),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _tickets(client: TestClient, headers: dict[str, str], n: int) -> list[str]:
    return [
        _ok(client.post("/api/v1/tickets", json={"title": f"U6 {RUN} {i}"}, headers=headers), 201)[
            "id"
        ]
        for i in range(n)
    ]


def test_bulk_priority_team_assignee_with_partial_report(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "u6admin"))
    ids = _tickets(client, admin, 2)
    team = _ok(client.post("/api/v1/teams", json={"name": f"T {RUN}"}, headers=admin), 201)
    missing = "00000000-0000-0000-0000-000000000000"
    report = _ok(
        client.post(
            "/api/v1/tickets/bulk",
            json={
                "ids": [*ids, missing],
                "priority": "urgent",
                "team_id": team["id"],
                "assignee_user_id": str(world.users["u6admin"]),
            },
            headers=admin,
        )
    )
    assert (report["total"], report["succeeded"], report["failed"]) == (3, 2, 1)
    bad = [i for i in report["items"] if not i["ok"]]
    assert bad[0]["id"] == missing
    assert bad[0]["code"]
    for tid in ids:
        t = _ok(client.get(f"/api/v1/tickets/{tid}", headers=admin))
        assert t["priority"] == "urgent"
        assert t["assignee_user_id"] == str(world.users["u6admin"])
        assert t["team_id"] == team["id"]


def test_bulk_status_and_alias_still_work(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "u6admin"))
    ids = _tickets(client, admin, 2)
    report = _ok(
        client.post(
            "/api/v1/tickets/bulk", json={"ids": ids, "status": "in_progress"}, headers=admin
        )
    )
    assert report["succeeded"] == 2
    alias = _ok(
        client.post(
            "/api/v1/tickets/bulk-status",
            json={"ticket_ids": ids, "status": "waiting"},
            headers=admin,
        )
    )
    assert len(alias["changed"]) == 2
    assert alias["failed"] == []


def test_bulk_validation_permission_and_tenant_separation(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "u6admin"))
    reader = bearer(login(client, world, "u6reader"))
    other = bearer(login(client, world, "u6otherb"))
    ids = _tickets(client, admin, 1)
    # no change given
    assert client.post("/api/v1/tickets/bulk", json={"ids": ids}, headers=admin).status_code == 422
    # assignee without membership, unknown team
    stranger = str(world.users["u6otherb"])
    r = client.post(
        "/api/v1/tickets/bulk", json={"ids": ids, "assignee_user_id": stranger}, headers=admin
    )
    assert r.status_code == 422
    r = client.post(
        "/api/v1/tickets/bulk",
        json={"ids": ids, "team_id": "00000000-0000-0000-0000-000000000000"},
        headers=admin,
    )
    assert r.status_code == 422
    # read only user
    assert (
        client.post(
            "/api/v1/tickets/bulk", json={"ids": ids, "priority": "high"}, headers=reader
        ).status_code
        == 403
    )
    # other tenant: ticket is not visible, reported per item, nothing changed
    report = _ok(
        client.post("/api/v1/tickets/bulk", json={"ids": ids, "priority": "high"}, headers=other)
    )
    assert report["failed"] == 1
    assert _ok(client.get(f"/api/v1/tickets/{ids[0]}", headers=admin))["priority"] != "high"
