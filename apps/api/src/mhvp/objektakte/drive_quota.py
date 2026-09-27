"""Google Drive API quota protection for the parallel operation (M35 Stufe 5, open question
M35-06): rate limiting and backoff at the HTTP transport level.

During the parallel operation objektakte and the CRM both call the Drive API of
``ablage@muellerhv.de``; Google enforces per project and per user quotas (the exact figures are
read from the Google Cloud console, none are hard coded here as a fact). The existing
``mhvp.documents.dms.GoogleDriveStore`` had no retry at all: a ``429`` or a ``403`` with
``userRateLimitExceeded``/``rateLimitExceeded`` surfaced as a failed mirror job.

``DriveQuotaTransport`` wraps any ``httpx.AsyncBaseTransport`` and adds, for requests to the
Google API hosts only:

- a minimum spacing between requests per process (token bucket, ``min_interval_seconds``),
- exponential backoff with jitter on ``429``, on ``403``/``5xx`` whose body names a rate or
  quota reason, and on connection errors, honouring ``Retry-After`` when present,
- a hard cap on attempts; the last response (or error) is handed back unchanged so the caller's
  own error mapping (`_raise_for`) still applies.

Only reads of the response body decide on a retry; the transport never logs URLs with
tokens, never the body. Use ``drive_http_client()`` to get an ``httpx.AsyncClient`` with this
transport; existing call sites keep working when they do not.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

GOOGLE_HOSTS = frozenset({"www.googleapis.com", "oauth2.googleapis.com", "googleapis.com"})
RATE_REASONS = (
    "userratelimitexceeded",
    "ratelimitexceeded",
    "dailylimitexceeded",
    "quotaexceeded",
    "backenderror",
)
DEFAULT_MIN_INTERVAL_SECONDS = 0.12  # about 8 requests per second per process
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_BASE_DELAY_SECONDS = 1.0
DEFAULT_MAX_DELAY_SECONDS = 64.0

SleepFn = Callable[[float], Awaitable[None]]


def is_rate_limited(response: httpx.Response) -> bool:
    """True for a response the Drive API sends when a quota or rate limit is hit."""
    if response.status_code == 429:
        return True
    if response.status_code == 403 or response.status_code >= 500:
        try:
            text = response.text.lower()
        except Exception:  # streamed or unreadable body
            return response.status_code >= 500
        return any(reason in text for reason in RATE_REASONS) or response.status_code >= 500
    return False


def retry_delay(
    attempt: int,
    *,
    retry_after: str | None = None,
    base: float = DEFAULT_BASE_DELAY_SECONDS,
    cap: float = DEFAULT_MAX_DELAY_SECONDS,
    rng: random.Random | None = None,
) -> float:
    """Seconds to wait before attempt ``attempt + 1`` (attempt counts from 1): ``Retry-After``
    in seconds when Google sends one, otherwise ``base * 2**(attempt-1)`` plus up to one second
    of jitter, capped at ``cap``."""
    if retry_after:
        try:
            return min(cap, max(0.0, float(retry_after)))
        except ValueError:
            pass
    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    jitter: float = (rng or random).random()
    return float(min(cap, delay + jitter))


class _Bucket:
    """Minimum spacing between two requests, shared by all coroutines of one process."""

    def __init__(self, min_interval: float) -> None:
        self._interval = min_interval
        self._next_at = 0.0
        self._lock = asyncio.Lock()

    async def wait(self, sleep: SleepFn, clock: Callable[[], float]) -> None:
        async with self._lock:
            now = clock()
            if now < self._next_at:
                await sleep(self._next_at - now)
                now = clock()
            self._next_at = max(now, self._next_at) + self._interval


class DriveQuotaTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        wrapped: httpx.AsyncBaseTransport | None = None,
        *,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
        max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
        sleep: SleepFn | None = None,
        clock: Callable[[], float] | None = None,
        hosts: frozenset[str] = GOOGLE_HOSTS,
    ) -> None:
        self._wrapped = wrapped or httpx.AsyncHTTPTransport()
        self._bucket = _Bucket(min_interval_seconds)
        self._max_attempts = max(1, max_attempts)
        self._base = base_delay_seconds
        self._cap = max_delay_seconds
        self._sleep: SleepFn = sleep or asyncio.sleep
        self._clock = clock or time.monotonic
        self._hosts = hosts
        self.retries = 0  # observable for tests and metrics

    def _applies(self, request: httpx.Request) -> bool:
        host = request.url.host.lower()
        return host in self._hosts or host.endswith(".googleapis.com")

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if not self._applies(request):
            return await self._wrapped.handle_async_request(request)
        attempt = 0
        while True:
            attempt += 1
            await self._bucket.wait(self._sleep, self._clock)
            try:
                response = await self._wrapped.handle_async_request(request)
            except httpx.TransportError as exc:
                if attempt >= self._max_attempts:
                    raise
                self.retries += 1
                log.warning("drive request failed (%s), retry %d", type(exc).__name__, attempt)
                await self._sleep(retry_delay(attempt, base=self._base, cap=self._cap))
                continue
            if attempt >= self._max_attempts:
                return response
            await response.aread()
            if not is_rate_limited(response):
                return response
            self.retries += 1
            await response.aclose()
            log.warning(
                "drive quota or rate limit (%d), retry %d of %d",
                response.status_code,
                attempt,
                self._max_attempts,
            )
            await self._sleep(
                retry_delay(
                    attempt,
                    retry_after=response.headers.get("Retry-After"),
                    base=self._base,
                    cap=self._cap,
                )
            )

    async def aclose(self) -> None:
        await self._wrapped.aclose()


def drive_http_client(timeout: float = 60.0, **kwargs: object) -> httpx.AsyncClient:
    """``httpx.AsyncClient`` with the quota transport; drop-in for the plain client the Drive
    call sites build (``mhvp.documents.tasks``, ``services.download_from_drive``)."""
    return httpx.AsyncClient(timeout=timeout, transport=DriveQuotaTransport(**kwargs))  # type: ignore[arg-type]
