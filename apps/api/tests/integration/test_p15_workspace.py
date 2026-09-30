"""M9-03, M9-04: saved filters for tickets and the bulk assignment of tickets. Expected
values: two tickets assigned to a colleague -> changed 2, repeating -> 0 (idempotent); an
unknown id aborts everything (404), another tenant sees nothing (404), a non member as
assignee is rejected (422), a role without ``tickets:update`` gets 403."""

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
W = "/api/v1/workspace"


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pw-{RUN}", name=f"PW {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pw2-{RUN}", name=f"PW2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("w15admin", a, "tenant_admin"),
            ("w15colleague", a, "standard"),
            ("w15caretaker", a, "read_only"),
            ("w15other", b, "tenant_admin"),
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
    return response.json() if response.content else None


def test_saved_filter_for_tickets(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "w15admin"))
    body = {
        "resource": "tickets",
        "name": "Offen Hans",
        "params": {"status": "new", "q": "Heizung"},
    }
    saved = _ok(client.put(f"{W}/filters", json=body, headers=h))
    assert saved["resource"] == "tickets"
    listed = _ok(client.get(f"{W}/filters", params={"resource": "tickets"}, headers=h))
    assert [f["name"] for f in listed] == ["Offen Hans"]
    assert (
        client.put(f"{W}/filters", json=body | {"resource": "bank"}, headers=h).status_code == 422
    )


def test_bulk_assign_tickets(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "w15admin"))
    caretaker = bearer(login(client, world, "w15caretaker"))
    other = bearer(login(client, world, "w15other"))
    colleague_id = str(world.users["w15colleague"])
    ids = [
        _ok(client.post("/api/v1/tickets", json={"title": f"Sammel {n} {RUN}"}, headers=h), 201)[
            "id"
        ]
        for n in (1, 2)
    ]
    action = {"action": "tickets.assign", "ids": ids, "assignee_user_id": colleague_id}
    assert _ok(client.post(f"{W}/bulk", json=action, headers=h))["changed"] == 2
    assert _ok(client.post(f"{W}/bulk", json=action, headers=h))["changed"] == 0
    for ticket_id in ids:
        ticket = _ok(client.get(f"/api/v1/tickets/{ticket_id}", headers=h))
        assert ticket["assignee_user_id"] == colleague_id
    unknown = action | {"ids": [*ids, str(uuid.uuid4())]}
    assert client.post(f"{W}/bulk", json=unknown, headers=h).status_code == 404
    assert client.post(f"{W}/bulk", json=action, headers=other).status_code == 404
    assert client.post(f"{W}/bulk", json=action, headers=caretaker).status_code == 403
    missing = action | {"assignee_user_id": None}
    assert client.post(f"{W}/bulk", json=missing, headers=h).status_code == 422
    outsider = action | {"assignee_user_id": str(world.users["w15other"])}
    assert client.post(f"{W}/bulk", json=outsider, headers=h).status_code == 422
    assert (
        client.post(
            f"{W}/bulk", json={"action": "tickets.assign", "ids": []}, headers=h
        ).status_code
        == 422
    )
