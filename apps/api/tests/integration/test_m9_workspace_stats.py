"""M9 dashboard analytics (/api/v1/workspace/dashboard/stats): tickets open, in progress,
created and done inside the range, per-bucket counts and per-assignee resolution, tenant
separation, hand computed expected numbers."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from mhvp.main import create_app
from mhvp.platform import services
from mhvp.tickets.models import Ticket
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
W = "/api/v1/workspace"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ws-{RUN}", name=f"Stats {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ws2-{RUN}", name=f"Stats2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("wsadmin", a, "tenant_admin"),
            ("wsagent1", a, "standard"),
            ("wsagent2", a, "standard"),
            ("wsother", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=False,
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


def _create_ticket(client: TestClient, headers: dict[str, str], title: str) -> dict[str, Any]:
    result: dict[str, Any] = _ok(
        client.post("/api/v1/tickets", json={"title": title}, headers=headers),
        201,
    )
    return result


def _force_dates(
    settings: Any,
    tenant_id: uuid.UUID,
    ticket_id: str,
    *,
    created_at: datetime | None = None,
    resolved_at: datetime | None = None,
) -> None:
    """Backdate created_at/resolved_at directly (the API never lets a user set these). Goes
    through the same RLS tenant scope as a request, otherwise the update silently matches no
    rows."""
    import asyncio as _asyncio

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    async def _run() -> None:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                values: dict[str, Any] = {}
                if created_at is not None:
                    values["created_at"] = created_at
                if resolved_at is not None:
                    values["resolved_at"] = resolved_at
                result = await session.execute(
                    update(Ticket).where(Ticket.id == uuid.UUID(ticket_id)).values(**values)
                )
                assert result.rowcount == 1, "backdating matched no row (RLS scope?)"  # type: ignore[attr-defined]
        finally:
            await engine.dispose()

    _asyncio.run(_run())


def test_dashboard_stats(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "wsadmin"))
    agent1 = world.users["wsagent1"]
    agent2 = world.users["wsagent2"]
    other = bearer(login(client, world, "wsother"))
    today = local_today()
    now = datetime.combine(today, datetime.min.time(), tzinfo=UTC)

    # Two tickets created today, assigned to agent1 and agent2.
    t1 = _create_ticket(client, h, f"Heizung {RUN}")
    t2 = _create_ticket(client, h, f"Aufzug {RUN}")
    _ok(
        client.patch(
            f"/api/v1/tickets/{t1['id']}", json={"assignee_user_id": str(agent1)}, headers=h
        )
    )
    _ok(
        client.patch(
            f"/api/v1/tickets/{t2['id']}", json={"assignee_user_id": str(agent2)}, headers=h
        )
    )

    # t1: resolved today after 5 hours -> counted in "done_in_range" and average resolution.
    _force_dates(settings, world.tenant_a, t1["id"], created_at=now)
    _ok(client.patch(f"/api/v1/tickets/{t1['id']}", json={"status": "in_progress"}, headers=h))
    _ok(client.patch(f"/api/v1/tickets/{t1['id']}", json={"status": "done"}, headers=h))
    _force_dates(settings, world.tenant_a, t1["id"], resolved_at=now.replace(hour=5))

    # t2: stays open, in progress.
    _ok(client.patch(f"/api/v1/tickets/{t2['id']}", json={"status": "in_progress"}, headers=h))

    # A third ticket, unassigned, created and left new (open, not in progress).
    t3 = _create_ticket(client, h, f"Klingel {RUN}")

    # A ticket in the other tenant must never leak into these numbers.
    other_t = _create_ticket(client, other, f"Fremd {RUN}")
    _ok(
        client.patch(
            f"/api/v1/tickets/{other_t['id']}", json={"status": "in_progress"}, headers=other
        )
    )

    stats = _ok(client.get(f"{W}/dashboard/stats", params={"range": "week"}, headers=h))
    assert stats["range"] == "week"
    # Hand computed: t2 (in_progress) and t3 (new) are open; only t2 is in_progress.
    assert stats["totals"]["open"] == 2
    assert stats["totals"]["in_progress"] == 1
    assert stats["totals"]["created_in_range"] == 3
    assert stats["totals"]["done_in_range"] == 1

    today_key = today.isoformat()
    bucket = next(b for b in stats["buckets"] if b["key"] == today_key)
    assert bucket["created"] == 3
    assert bucket["resolved"] == 1

    by_user = {a["user_id"]: a for a in stats["assignees"]}
    assert by_user[str(agent1)]["open"] == 0
    assert by_user[str(agent1)]["resolved_in_range"] == 1
    assert by_user[str(agent1)]["average_resolution_hours"] == 5.0
    assert by_user[str(agent2)]["open"] == 1
    assert by_user[str(agent2)]["resolved_in_range"] == 0
    assert by_user[str(agent2)]["average_resolution_hours"] is None

    # Filtered by user: only that assignee's ticket is counted.
    filtered = _ok(
        client.get(
            f"{W}/dashboard/stats",
            params={"range": "week", "user_id": str(agent2)},
            headers=h,
        )
    )
    assert filtered["totals"]["open"] == 1
    assert filtered["totals"]["created_in_range"] == 1

    # Tenant separation: the other tenant sees only its own ticket.
    other_stats = _ok(client.get(f"{W}/dashboard/stats", params={"range": "week"}, headers=other))
    assert other_stats["totals"]["created_in_range"] == 1
    assert other_stats["totals"]["in_progress"] == 1

    assert (
        client.get(f"{W}/dashboard/stats", params={"range": "century"}, headers=h).status_code
        == 422
    )

    # Caretaker without tickets:read has no access; a caretaker here is not seeded, so check
    # the permission dependency directly via a role with tickets:read removed is out of scope
    # for this integration test (covered by the permission matrix tests).
    ids_seen = {r["id"] for r in _ok(client.get("/api/v1/tickets", headers=h))}
    assert {t1["id"], t2["id"], t3["id"]} <= ids_seen
