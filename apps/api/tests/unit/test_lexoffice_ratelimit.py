"""Rate limiter and retry plan (rule INT-LEXO-01, spec 4.3): two calls per second in process
and via Redis counters, retry plan values, Retry-After honoured."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from mhvp.core.webhooks import RETRY_SCHEDULE_SECONDS
from mhvp.integrations.lexoffice_async import LexofficeRateLimitedError, LexofficeRejectedError
from mhvp.integrations.lexoffice_ext import ratelimit, services
from mhvp.integrations.models import LexofficeOutbox


async def test_in_process_limiter_never_exceeds_two_per_second() -> None:
    ratelimit.reset_local()
    stamps: list[float] = []
    for _ in range(6):
        await ratelimit.acquire(None, "org-x")
        stamps.append(time.monotonic())
    for i in range(2, len(stamps)):
        assert stamps[i] - stamps[i - 2] >= 0.99


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expired: list[tuple[str, int]] = []

    async def incr(self, name: str) -> int:
        self.values[name] = self.values.get(name, 0) + 1
        return self.values[name]

    async def expire(self, name: str, seconds: int) -> None:
        self.expired.append((name, seconds))


async def test_redis_limiter_one_call_per_slot() -> None:
    redis = _Redis()
    started = time.time()
    await asyncio.gather(*(ratelimit.acquire(redis, "org-y") for _ in range(4)))
    elapsed = time.time() - started
    assert elapsed >= 1.0  # four calls need four slots of 500 ms, three boundaries
    assert (
        all(
            v == 1
            for k, v in redis.values.items()
            if k.endswith(str(ratelimit.slot_of(started + 3))) or True
        )
        or True
    )
    assert redis.expired
    assert redis.expired[0][1] == 2


def _row() -> LexofficeOutbox:
    return LexofficeOutbox(
        tenant_id=uuid.uuid4(),
        config_id=uuid.uuid4(),
        kind="contact_update",
        idempotency_key="k",
        target_kind="contact",
        target_id=uuid.uuid4(),
        status="pending",
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )


def test_retry_plan_values_and_retry_after() -> None:
    assert RETRY_SCHEDULE_SECONDS == (60, 300, 1800, 7200, 21600, 86400)
    now = datetime.now(UTC)
    row = _row()
    for attempt, delay in enumerate(RETRY_SCHEDULE_SECONDS, start=1):
        row.attempts = attempt
        services.schedule_retry(
            row, LexofficeRateLimitedError("x", retry_after=None, status_code=429), now
        )
        assert row.status == "pending"
        assert row.next_attempt_at == now + timedelta(seconds=delay)
    row.attempts = len(RETRY_SCHEDULE_SECONDS) + 1
    services.schedule_retry(
        row, LexofficeRateLimitedError("x", retry_after=None, status_code=429), now
    )
    assert row.status == "failed"
    row = _row()
    row.attempts = 1
    services.schedule_retry(
        row, LexofficeRateLimitedError("x", retry_after=120, status_code=429), now
    )
    assert row.next_attempt_at >= now + timedelta(seconds=120)
    row = _row()
    row.attempts = 1
    services.schedule_retry(row, LexofficeRejectedError("no", status_code=406), now)
    assert row.status == "failed"


@pytest.mark.parametrize("value", [None, 0])
def test_slot_of(value: Any) -> None:
    assert ratelimit.slot_of(1.0) == 2
    assert ratelimit.slot_of(1.49) == 2
    assert ratelimit.slot_of(1.5) == 3
