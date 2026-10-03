"""AJ07: trust boundary of X-Forwarded-For (GAI-311), emergency counter for token routes on
Redis failure (GAI-312) and limits of the anonymous self disclosure payload (GAI-309)."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from mhvp.core import ratelimit
from mhvp.core.request_identity import client_ip
from mhvp.letting.routers import SelfDisclosureSubmitIn

PROXIES = ["10.0.0.0/8"]


def _scope(peer: str, xff: str | None = None, path: str = "/api/v1/auth/login") -> dict[str, Any]:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return {"type": "http", "path": path, "client": (peer, 1234), "headers": headers}


def test_forwarded_for_ignored_without_trusted_proxies() -> None:
    scope = _scope("203.0.113.9", "198.51.100.1")
    assert client_ip(scope, trust_forwarded_for=False) == "203.0.113.9"


def test_forwarded_for_trusted_only_from_listed_peer() -> None:
    # Direct peer is not a trusted proxy: header ignored, even if spoofed.
    spoofed = _scope("203.0.113.9", "198.51.100.1")
    assert client_ip(spoofed, trust_forwarded_for=False, trusted_proxies=PROXIES) == "203.0.113.9"
    # Peer is the BFF/Traefik: rightmost untrusted hop wins, a prepended value is ignored.
    via = _scope("10.1.2.3", "1.1.1.1, 198.51.100.7, 10.0.0.5")
    assert client_ip(via, trust_forwarded_for=False, trusted_proxies=PROXIES) == "198.51.100.7"
    # Trusted peer without header: the peer itself.
    assert client_ip(_scope("10.1.2.3"), trust_forwarded_for=False, trusted_proxies=PROXIES) == (
        "10.1.2.3"
    )


class _BrokenRedis:
    def pipeline(self, transaction: bool = True) -> Any:
        raise RedisConnectionError("down")


def _run(settings: Any, path: str, n: int) -> list[int]:
    statuses: list[int] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ratelimit.RateLimitMiddleware(app)
    state = SimpleNamespace(settings=settings, resources=SimpleNamespace(redis=_BrokenRedis()))

    async def go() -> None:
        for _ in range(n):
            scope = _scope("192.0.2.44", path=path)
            scope["app"] = SimpleNamespace(state=state)

            async def receive() -> dict[str, Any]:
                return {"type": "http.request", "body": b""}

            async def send(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    statuses.append(int(message["status"]))

            await middleware(scope, receive, send)

    asyncio.run(go())
    return statuses


def _settings(fail_closed: bool) -> Any:
    return SimpleNamespace(
        rate_limit_enabled=True,
        rate_limit_per_minute_anonymous=3,
        rate_limit_per_minute_user=600,
        rate_limit_trust_forwarded_for=False,
        rate_limit_trusted_proxies=[],
        rate_limit_token_routes_fail_closed=fail_closed,
    )


def test_redis_failure_fails_open_by_default() -> None:
    ratelimit._local_counts.clear()
    assert _run(_settings(False), "/api/v1/portal/magic-link/verify-code", 6) == [200] * 6


def test_redis_failure_token_route_counted_locally_when_switched_on() -> None:
    ratelimit._local_counts.clear()
    statuses = _run(_settings(True), "/api/v1/portal/magic-link/verify-code", 5)
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3:] == [429, 429]
    # Other routes stay fail open even with the switch on.
    ratelimit._local_counts.clear()
    assert _run(_settings(True), "/api/v1/contacts", 5) == [200] * 5


def test_self_disclosure_payload_limits() -> None:
    ok = SelfDisclosureSubmitIn(consent_privacy=True, payload={"name": "A", "kinder": [1, 2]})
    assert ok.payload["name"] == "A"
    bad = [
        {f"k{i}": i for i in range(201)},
        {"a": {"b": {"c": {"d": 1}}}},
        {"x" * 101: 1},
        {"note": "x" * 5001},
        {f"k{i}": "y" * 4000 for i in range(20)},
    ]
    for payload in bad:
        with pytest.raises(ValidationError):
            SelfDisclosureSubmitIn(consent_privacy=True, payload=payload)


class _MemRedis:
    """Minimal pipeline fake: INCR and EXPIRE in memory (AK04)."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def pipeline(self, transaction: bool = True) -> Any:
        outer = self

        class _Pipe:
            def __init__(self) -> None:
                self.ops: list[tuple[str, str]] = []

            async def __aenter__(self) -> "_Pipe":
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            def incr(self, key: str) -> None:
                self.ops.append(("incr", key))

            def expire(self, key: str, seconds: int) -> None:
                self.ops.append(("expire", key))

            async def execute(self) -> list[Any]:
                out: list[Any] = []
                for op, key in self.ops:
                    if op == "incr":
                        outer.counts[key] = outer.counts.get(key, 0) + 1
                        out.append(outer.counts[key])
                    else:
                        out.append(True)
                return out

        return _Pipe()


def _run_from(settings: Any, redis: Any, calls: list[tuple[str, str]]) -> list[int]:
    statuses: list[int] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = ratelimit.RateLimitMiddleware(app)
    state = SimpleNamespace(settings=settings, resources=SimpleNamespace(redis=redis))

    async def go() -> None:
        for peer, path in calls:
            scope = _scope(peer, path=path)
            scope["app"] = SimpleNamespace(state=state)

            async def receive() -> dict[str, Any]:
                return {"type": "http.request", "body": b""}

            async def send(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    statuses.append(int(message["status"]))

            await middleware(scope, receive, send)

    asyncio.run(go())
    return statuses


def _token_settings(fail_closed: bool = False) -> Any:
    s = _settings(fail_closed)
    s.rate_limit_per_minute_anonymous = 100
    s.rate_limit_per_minute_token_path = 2
    return s


def test_token_path_limited_across_client_addresses() -> None:
    path = "/api/v1/letting/self-disclosure/ak04abc.tok"
    redis = _MemRedis()
    calls = [(f"192.0.2.{i}", path) for i in range(1, 5)]
    assert _run_from(_token_settings(), redis, calls) == [200, 200, 429, 429]
    # Another token has its own counter; the token is never part of a Redis key.
    other = "/api/v1/letting/self-disclosure/ak04other.tok"
    assert _run_from(_token_settings(), redis, [("192.0.2.9", other)]) == [200]
    assert not any("ak04" in key for key in redis.counts)


def test_token_path_limit_not_applied_to_other_routes() -> None:
    redis = _MemRedis()
    calls = [(f"192.0.2.{i}", "/api/v1/workspace/calendar-feed/token") for i in range(1, 5)]
    assert _run_from(_token_settings(), redis, calls) == [200] * 4
    calls = [(f"192.0.2.{i}", "/api/v1/auth/login") for i in range(1, 5)]
    assert _run_from(_token_settings(), redis, calls) == [200] * 4


def test_token_path_emergency_counter_on_redis_failure() -> None:
    ratelimit._local_counts.clear()
    path = "/api/v1/workspace/calendar-feed/ak04feed.ics"
    calls = [(f"192.0.2.{i}", path) for i in range(1, 5)]
    assert _run_from(_token_settings(True), _BrokenRedis(), calls) == [200, 200, 429, 429]
    ratelimit._local_counts.clear()
