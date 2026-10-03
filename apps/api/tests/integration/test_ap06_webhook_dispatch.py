"""AP06 (GAM-501 to GAM-503): webhook dispatch without HTTP inside an open transaction,
timeout handling up to ``failed``, error isolation per tenant and watermark per subscription.

Expected results are fixed in advance: one claimed attempt is committed before the call
(``attempts`` 1, row not locked during the call); a timeout of the target counts as a failed
attempt with the next retry after 60 s; after the last scheduled attempt the delivery is
``failed`` and the alarm (notification plus counter ``webhook_deliveries_failed``) fires; an
exception of tenant A leaves the delivery of tenant B untouched.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core import crypto, webhook_tasks, webhooks
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import DomainEvent
from mhvp.core.webhooks import (
    CLAIM_MARKER,
    RETRY_SCHEDULE_SECONDS,
    DeliveryStatus,
    WebhookDelivery,
    WebhookSubscription,
    claim_delivery,
    enqueue_deliveries,
)
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, _settings

pytestmark = pytest.mark.integration


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _factory(settings: Any) -> tuple[Any, async_sessionmaker[AsyncSession]]:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    return engine, create_session_factory(engine)


async def _tenant_with_event(settings: Any, slug: str, url: str) -> tuple[uuid.UUID, uuid.UUID]:
    engine, factory = await _factory(settings)
    try:
        tenant, _ = await services.provision_tenant(factory, slug=slug, name=f"AP06 {slug}")
        async with tenant_transaction(factory, tenant) as session:
            hook = WebhookSubscription(
                tenant_id=tenant, url=url, event_types=["ap06.*"], secret="s3cret", active=True
            )
            session.add(hook)
            await session.flush()
        async with tenant_transaction(factory, tenant) as session:
            event = DomainEvent(
                tenant_id=tenant, type="ap06.happened", entity_type="ap06", payload={}
            )
            session.add(event)
            await session.flush()
            return tenant, event.id
    finally:
        await engine.dispose()


async def _deliveries(settings: Any, tenant: uuid.UUID) -> list[WebhookDelivery]:
    engine, factory = await _factory(settings)
    try:
        async with tenant_transaction(factory, tenant) as session:
            rows = list(
                await session.scalars(
                    select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows
    finally:
        await engine.dispose()


async def _set(settings: Any, tenant: uuid.UUID, **values: Any) -> None:
    engine, factory = await _factory(settings)
    try:
        async with tenant_transaction(factory, tenant) as session:
            for row in await session.scalars(
                select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant)
            ):
                for key, value in values.items():
                    setattr(row, key, value)
    finally:
        await engine.dispose()


def test_claim_is_committed_and_row_unlocked_during_http(
    database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    tenant, _ = _run(_tenant_with_event(settings, f"ap06a-{RUN}", "http://hook.example/a"))
    seen: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/a":
            return httpx.Response(204)  # deliveries of other tenants in the shared database
        # A second connection sees the committed claim and can lock the row: no transaction
        # of the job is open while the call runs (GAM-501).
        engine, factory = await _factory(settings)
        try:
            async with tenant_transaction(factory, tenant) as session:
                await session.execute(text("SET LOCAL lock_timeout = '500ms'"))
                row = await session.scalar(
                    select(WebhookDelivery)
                    .where(WebhookDelivery.id == uuid.UUID(request.headers["X-MHVP-Delivery"]))
                    .with_for_update(nowait=True)
                )
                assert row is not None
                seen["attempts"] = row.attempts
                seen["marker"] = row.last_error
        finally:
            await engine.dispose()
        return httpx.Response(204)

    async def go() -> dict[str, int]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await webhook_tasks.dispatch_once(settings, http)

    _run(go())
    assert seen == {"attempts": 1, "marker": CLAIM_MARKER}
    (row,) = _run(_deliveries(settings, tenant))
    assert row.status == DeliveryStatus.SUCCEEDED
    assert row.attempts == 1
    assert row.last_error is None


def test_timeout_counts_attempt_and_ends_failed_with_alarm(
    database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(database, redis_url)
    tenant, _ = _run(_tenant_with_event(settings, f"ap06t-{RUN}", "http://hook.example/t"))
    monkeypatch.setattr(webhooks, "DELIVERY_DEADLINE_SECONDS", 0.2)

    async def hanging(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(204)

    async def go() -> dict[str, int]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(hanging)) as http:
            return await webhook_tasks.dispatch_once(settings, http)

    before = datetime.now(UTC)
    _run(go())
    (row,) = _run(_deliveries(settings, tenant))
    assert row.status == DeliveryStatus.PENDING
    assert row.attempts == 1
    assert row.last_error == "Timeout"
    assert row.next_attempt_at is not None
    assert row.next_attempt_at >= before + timedelta(seconds=RETRY_SCHEDULE_SECONDS[0])

    # Second run within the retry delay: not due, no further attempt.
    _run(go())
    assert _run(_deliveries(settings, tenant))[0].attempts == 1

    # Last scheduled attempt also times out: failed, alarm counter and notification.
    _run(
        _set(
            settings,
            tenant,
            attempts=len(RETRY_SCHEDULE_SECONDS),
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    _run(go())
    (row,) = _run(_deliveries(settings, tenant))
    assert row.status == DeliveryStatus.FAILED
    assert row.attempts == len(RETRY_SCHEDULE_SECONDS) + 1
    assert row.next_attempt_at is None

    async def failed_count() -> tuple[int, int]:
        engine, factory = await _factory(settings)
        try:
            async with tenant_transaction(factory, tenant) as session:
                count = await session.scalar(
                    select(func.count())
                    .select_from(WebhookDelivery)
                    .where(WebhookDelivery.status == DeliveryStatus.FAILED)
                )
                hook = await session.scalar(select(WebhookSubscription))
                assert hook is not None
                return int(count or 0), hook.consecutive_failures
        finally:
            await engine.dispose()

    assert _run(failed_count()) == (1, 1)


def test_lost_worker_after_claim_counts_and_ends_failed(database: Database, redis_url: str) -> None:
    settings = _settings(database, redis_url)
    tenant, _ = _run(_tenant_with_event(settings, f"ap06l-{RUN}", "http://hook.example/l"))

    async def claim_only() -> None:
        engine, factory = await _factory(settings)
        try:
            async with tenant_transaction(factory, tenant) as session:
                await enqueue_deliveries(session, tenant)
            async with tenant_transaction(factory, tenant) as session:
                found, claim = await claim_delivery(session, tenant)
                assert found
                assert claim is not None
            # The worker is lost here: no call, no outcome.
        finally:
            await engine.dispose()

    _run(claim_only())
    (row,) = _run(_deliveries(settings, tenant))
    assert (row.attempts, row.last_error, row.status) == (1, CLAIM_MARKER, DeliveryStatus.PENDING)
    assert row.next_attempt_at is not None
    assert row.next_attempt_at > datetime.now(UTC)

    _run(
        _set(
            settings,
            tenant,
            attempts=len(RETRY_SCHEDULE_SECONDS) + 1,
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        )
    )
    calls: list[str] = []

    async def go() -> None:
        transport = httpx.MockTransport(lambda r: calls.append(str(r.url)) or httpx.Response(204))
        async with httpx.AsyncClient(transport=transport) as http:
            await webhook_tasks.dispatch_once(settings, http)

    _run(go())
    (row,) = _run(_deliveries(settings, tenant))
    assert row.status == DeliveryStatus.FAILED
    assert row.last_error == "outcome unknown"
    assert not [c for c in calls if "hook.example/l" in c]


def test_error_of_tenant_a_does_not_block_tenant_b(
    database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(database, redis_url)
    tenant_a, _ = _run(_tenant_with_event(settings, f"ap06x-{RUN}", "http://hook.example/xa"))
    tenant_b, _ = _run(_tenant_with_event(settings, f"ap06y-{RUN}", "http://hook.example/xb"))
    original = webhook_tasks.enqueue_deliveries

    async def broken(session: AsyncSession, tenant_id: uuid.UUID) -> int:
        if tenant_id == tenant_a:
            raise RuntimeError("poisoned row of tenant A")
        return await original(session, tenant_id)

    monkeypatch.setattr(webhook_tasks, "enqueue_deliveries", broken)
    received: list[str] = []

    async def go() -> dict[str, int]:
        transport = httpx.MockTransport(
            lambda r: received.append(r.url.path) or httpx.Response(204)
        )
        async with httpx.AsyncClient(transport=transport) as http:
            return await webhook_tasks.dispatch_once(settings, http)

    totals = _run(go())
    assert totals["failed"] >= 1
    assert "/xb" in received
    assert "/xa" not in received
    assert _run(_deliveries(settings, tenant_a)) == []
    (row_b,) = _run(_deliveries(settings, tenant_b))
    assert row_b.status == DeliveryStatus.SUCCEEDED


def test_budget_used_up_skips_tenants_without_claims(database: Database, redis_url: str) -> None:
    settings = _settings(database, redis_url)
    tenant, _ = _run(_tenant_with_event(settings, f"ap06b-{RUN}", "http://hook.example/b"))

    async def go() -> dict[str, int]:
        transport = httpx.MockTransport(lambda r: httpx.Response(204))
        async with httpx.AsyncClient(transport=transport) as http:
            return await webhook_tasks.dispatch_once(settings, http, budget_seconds=0)

    totals = _run(go())
    assert totals["attempted"] == 0
    assert totals["tenants_skipped"] >= 1
    assert _run(_deliveries(settings, tenant)) == []
    assert webhook_tasks.time_budget(settings) == 200.0


def test_watermark_limits_the_event_lookup(database: Database, redis_url: str) -> None:
    settings = _settings(database, redis_url)
    tenant, first = _run(_tenant_with_event(settings, f"ap06w-{RUN}", "http://hook.example/w"))

    async def scenario() -> tuple[int, int, int, datetime | None]:
        engine, factory = await _factory(settings)
        try:
            async with tenant_transaction(factory, tenant) as session:
                created_first = await enqueue_deliveries(session, tenant)
                hook = await session.scalar(select(WebhookSubscription))
                assert hook is not None
                mark = hook.watermark_occurred_at
            async with tenant_transaction(factory, tenant) as session:
                # New event far behind the watermark minus overlap: not looked up any more.
                session.add(
                    DomainEvent(
                        tenant_id=tenant,
                        type="ap06.late",
                        entity_type="ap06",
                        payload={},
                    )
                )
                await session.execute(
                    text(
                        "UPDATE webhook_subscription SET watermark_occurred_at = now() "
                        "+ interval '1 hour'"
                    )
                )
            async with tenant_transaction(factory, tenant) as session:
                created_far = await enqueue_deliveries(session, tenant)
            async with tenant_transaction(factory, tenant) as session:
                # Within the overlap window: found, and the first event is not doubled.
                await session.execute(
                    text("UPDATE webhook_subscription SET watermark_occurred_at = now()")
                )
            async with tenant_transaction(factory, tenant) as session:
                created_overlap = await enqueue_deliveries(session, tenant)
            return created_first, created_far, created_overlap, mark
        finally:
            await engine.dispose()

    created_first, created_far, created_overlap, mark = _run(scenario())
    assert (created_first, created_far, created_overlap) == (1, 0, 1)
    assert mark is not None
    rows = _run(_deliveries(settings, tenant))
    assert len(rows) == 2
    assert len({r.event_id for r in rows}) == 2
    assert first in {r.event_id for r in rows}
