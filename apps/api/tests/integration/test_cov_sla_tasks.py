"""Coverage: SLA clock job ``mhvp.sla.check_clocks`` (M21): counts running clocks per active
tenant, backfills clocks of tickets without one, escalates breached clocks with a due step,
and a failing tenant is logged and skipped without stopping the run (per tenant transaction,
rollback only for that tenant)."""

import asyncio
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.sla import tasks as sla_tasks
from mhvp.sla.models import ClockState, SlaClock, SlaClockLog
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"covsla-{RUN}", name=f"CovSLA {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("covslaadmin"), display_name="covslaadmin", password=PASSWORD
        )
        world.users["covslaadmin"] = uid
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _run(database: Database, redis_url: str, tenant_id: uuid.UUID, fn: Any) -> Any:
    async def go() -> Any:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, tenant_id) as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_check_clocks_counts_backfills_and_escalates(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "covslaadmin"))
    settings = _settings(database, redis_url)
    rule = _ok(
        client.post(
            "/api/v1/sla/rules",
            json={
                "name": "Cov Dringend",
                "priority": "urgent",
                "response_minutes": 60,
                "resolution_minutes": 240,
                "clock_type": "calendar",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/sla/rules/{rule['id']}/steps",
            json={
                "step_no": 1,
                "after_minutes": 0,
                "notify_user_ids": [str(world.users["covslaadmin"])],
                "channel": "internal",
            },
            headers=h,
        ),
        201,
    )
    ticket = _ok(
        client.post(
            "/api/v1/tickets", json={"title": "Cov Rohrbruch", "priority": "urgent"}, headers=h
        ),
        201,
    )
    ticket_id = uuid.UUID(ticket["id"])

    # 1. Running clock: counted, not escalated (no breach yet).
    totals = asyncio.run(sla_tasks.check_clocks_once(settings))
    assert totals["tenants"] >= 1
    assert totals["clocks"] >= 1

    async def clock_state(session: Any) -> tuple[str, list[int]]:
        clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket_id))
        assert clock is not None
        return clock.state.value, list(clock.escalated_steps)

    assert _run(database, redis_url, world.tenant_a, clock_state) == ("running", [])

    # 2. Breach: due dates in the past -> breached, step 1 escalated exactly once.
    async def breach(session: Any) -> None:
        clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket_id))
        assert clock is not None
        past = datetime.now(UTC) - timedelta(hours=3)
        clock.started_at = past
        clock.due_response_at = past + timedelta(minutes=1)
        clock.due_resolution_at = past + timedelta(minutes=2)

    _run(database, redis_url, world.tenant_a, breach)
    escalated = asyncio.run(sla_tasks.check_clocks_once(settings))
    assert escalated["escalated"] >= 1
    assert _run(database, redis_url, world.tenant_a, clock_state) == ("breached", [1])
    again = asyncio.run(sla_tasks.check_clocks_once(settings))
    assert _run(database, redis_url, world.tenant_a, clock_state) == ("breached", [1])
    assert again["clocks"] >= 1  # breached clocks stay under observation

    # 3. Backfill: a ticket that lost its clock gets one, started at ticket creation.
    async def drop_clock(session: Any) -> None:
        clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket_id))
        assert clock is not None
        await session.execute(delete(SlaClockLog).where(SlaClockLog.clock_id == clock.id))
        await session.delete(clock)

    _run(database, redis_url, world.tenant_a, drop_clock)
    backfilled = asyncio.run(sla_tasks.check_clocks_once(settings))
    assert backfilled["backfilled"] >= 1

    async def restored(session: Any) -> ClockState:
        clock = await session.scalar(select(SlaClock).where(SlaClock.ticket_id == ticket_id))
        assert clock is not None
        assert clock.rule_id == uuid.UUID(rule["id"])
        state: ClockState = clock.state
        return state

    assert _run(database, redis_url, world.tenant_a, restored) in (
        ClockState.RUNNING,
        ClockState.BREACHED,
    )


def test_check_clocks_skips_failing_tenant_and_logs(
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = _settings(database, redis_url)
    calls: list[uuid.UUID] = []

    async def boom(session: Any, clock: Any, settings_: Any) -> None:
        calls.append(clock.tenant_id)
        raise RuntimeError("cov: escalation exploded")

    monkeypatch.setattr(sla_tasks, "check_and_escalate", boom)
    with caplog.at_level(logging.WARNING, logger="mhvp.sla.tasks"):
        totals = asyncio.run(sla_tasks.check_clocks_once(settings))
    assert totals["tenants"] >= 1
    assert totals["escalated"] == 0
    assert world.tenant_a in calls  # the clock of the previous test was visited
    messages = [r.getMessage() for r in caplog.records if r.name == "mhvp.sla.tasks"]
    assert "sla check_clocks failed" in messages
    assert any(getattr(r, "tenant_id", None) == str(world.tenant_a) for r in caplog.records)
