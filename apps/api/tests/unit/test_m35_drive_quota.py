"""M35-06: Drive quota transport (rate limiting, backoff on 429/403 rate reasons, Retry-After,
no retry for other hosts or other errors)."""

from __future__ import annotations

import asyncio
import random

import httpx
import pytest

from mhvp.objektakte import drive_quota


def _client(handler: object, **kwargs: object) -> tuple[httpx.AsyncClient, list[float]]:
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    clock = {"t": 0.0}

    def now() -> float:
        return clock["t"]

    transport = drive_quota.DriveQuotaTransport(
        httpx.MockTransport(handler),  # type: ignore[arg-type]
        sleep=sleep,
        clock=now,
        min_interval_seconds=0.0,
        **kwargs,  # type: ignore[arg-type]
    )
    return httpx.AsyncClient(transport=transport), sleeps


def test_retries_on_429_then_succeeds() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"error": "x"})
        return httpx.Response(200, json={"ok": True})

    client, sleeps = _client(handler)

    async def run() -> httpx.Response:
        async with client:
            return await client.get("https://www.googleapis.com/drive/v3/files/abc")

    response = asyncio.run(run())
    assert response.status_code == 200
    assert len(calls) == 3
    assert sleeps == [2.0, 2.0]  # Retry-After honoured


def test_403_with_rate_reason_backs_off_exponentially_and_gives_up() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"error": {"errors": [{"reason": "userRateLimitExceeded"}]}}
        )

    client, sleeps = _client(handler, max_attempts=3, base_delay_seconds=1.0)

    async def run() -> httpx.Response:
        async with client:
            return await client.get("https://www.googleapis.com/drive/v3/files")

    response = asyncio.run(run())
    assert response.status_code == 403  # last response handed back unchanged
    assert len(sleeps) == 2
    assert 1.0 <= sleeps[0] < 2.0
    assert 2.0 <= sleeps[1] < 3.0


def test_plain_403_and_other_hosts_are_not_retried() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return httpx.Response(403 if "google" in request.url.host else 429, text="forbidden")

    client, sleeps = _client(handler)

    async def run() -> None:
        async with client:
            assert (
                await client.get("https://www.googleapis.com/drive/v3/files")
            ).status_code == 403
            assert (await client.get("https://paperless.example.test/api/")).status_code == 429

    asyncio.run(run())
    assert calls == ["www.googleapis.com", "paperless.example.test"]
    assert sleeps == []


def test_min_interval_spaces_requests() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    sleeps: list[float] = []
    clock = {"t": 0.0}

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["t"] += seconds

    transport = drive_quota.DriveQuotaTransport(
        httpx.MockTransport(handler),
        sleep=sleep,
        clock=lambda: clock["t"],
        min_interval_seconds=0.5,
    )

    async def run() -> None:
        async with httpx.AsyncClient(transport=transport) as client:
            for _ in range(3):
                await client.get("https://www.googleapis.com/drive/v3/files")

    asyncio.run(run())
    assert sleeps == [0.5, 0.5]


def test_retry_delay_shape() -> None:
    rng = random.Random(1)  # noqa: S311 - deterministic jitter for the test
    assert drive_quota.retry_delay(1, retry_after="7") == 7.0
    assert drive_quota.retry_delay(1, retry_after="nicht-zahl", rng=rng) < 2.0
    assert drive_quota.retry_delay(10, rng=rng) == drive_quota.DEFAULT_MAX_DELAY_SECONDS


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (429, "", True),
        (403, '{"reason":"rateLimitExceeded"}', True),
        (403, "forbidden", False),
        (503, "backendError", True),
        (500, "", True),
        (200, "", False),
    ],
)
def test_is_rate_limited(status: int, body: str, expected: bool) -> None:
    response = httpx.Response(status, text=body)
    assert drive_quota.is_rate_limited(response) is expected
