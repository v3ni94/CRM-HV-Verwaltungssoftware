"""Rate limiting per token and API key with Redis counters (A49, section 12).

Fixed window of one minute per identity: authenticated requests are counted per tenant and
actor (user or API key), unauthenticated requests (login, MFA, webhooks) per client IP. The
limits are operator configuration (``Settings.rate_limit_*``), not a legal rule. Every
answer carries ``X-RateLimit-Limit``, ``X-RateLimit-Remaining`` and ``X-RateLimit-Reset``
(seconds until the window ends); exceeding the limit yields 429 with ``Retry-After`` and
the problem code ``MHVP-CORE-0006``. Health endpoints are exempt.

The middleware fails open: if Redis is unavailable the request passes without headers and a
warning is logged, because availability of the platform ranks above the limit and the edge
proxy keeps its own limit (section 3, Traefik).

GAI-312: with ``rate_limit_token_routes_fail_closed`` (default off) anonymous requests to the
token and code routes (``TOKEN_ROUTE_PREFIXES``) are counted by an in-process emergency
counter while Redis is unavailable, so a Redis outage does not lift the limit for routes that
check secrets. The counter is per worker process (with n workers the effective limit is up to
n times the configured one); it is a fallback, not a replacement of the Redis counter.
"""

import time

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mhvp.core.config import Settings
from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, problem_response
from mhvp.core.request_identity import identify, settings_client_ip

WINDOW_SECONDS = 60
EXEMPT_PREFIXES = ("/api/v1/health",)
# GAI-312: anonymous routes that check a token or code (login, MFA, magic link, invitation,
# self disclosure, calendar feed).
TOKEN_ROUTE_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/portal/magic-link/",
    "/api/v1/portal/invitations/",
    "/api/v1/portal/terms/accept",
    "/api/v1/letting/self-disclosure/",
    "/api/v1/workspace/calendar-feed/",
)
_LOCAL_MAX_KEYS = 10_000
_local_window = [0]
_local_counts: dict[str, int] = {}


def _local_incr(key: str, window: int) -> int:
    """In-process emergency counter (GAI-312); reset per window, size bounded."""
    if _local_window[0] != window or len(_local_counts) >= _LOCAL_MAX_KEYS:
        _local_counts.clear()
        _local_window[0] = window
    _local_counts[key] = _local_counts.get(key, 0) + 1
    return _local_counts[key]


_log = get_logger("mhvp.ratelimit")


def _headers(limit: int, remaining: int, reset: int) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(max(remaining, 0)),
        "X-RateLimit-Reset": str(reset),
    }


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        app = scope["app"]
        settings: Settings = app.state.settings
        path = str(scope.get("path", ""))
        if not settings.rate_limit_enabled or path.startswith(EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return

        identity = identify(scope, settings)
        address = settings_client_ip(scope, settings)
        if identity is None:
            limit = settings.rate_limit_per_minute_anonymous
            subject = "ip:" + address
        elif identity.actor.startswith("apikey:"):
            # An API key is only parsed here, never verified (see request_identity): a forged
            # key must not open a fresh counter per prefix, so the key path is counted per
            # client address (Sicherheitsreview 1.22, Befund 1). The user limit still applies
            # to genuine API clients.
            limit = settings.rate_limit_per_minute_user
            subject = f"ip:{address}:apikey"
        else:
            limit = settings.rate_limit_per_minute_user
            subject = identity.scope_key

        now = int(time.time())
        window = now - now % WINDOW_SECONDS
        reset = window + WINDOW_SECONDS - now
        redis: Redis = app.state.resources.redis
        try:
            async with redis.pipeline(transaction=True) as pipe:
                pipe.incr(f"rl:{subject}:{window}")
                pipe.expire(f"rl:{subject}:{window}", WINDOW_SECONDS * 2)
                count = int((await pipe.execute())[0])
        except (RedisError, OSError):
            _log.warning("ratelimit_unavailable", path=path)
            if not (
                settings.rate_limit_token_routes_fail_closed
                and identity is None
                and path.startswith(TOKEN_ROUTE_PREFIXES)
            ):
                await self.app(scope, receive, send)
                return
            count = _local_incr(f"rl:{subject}:{window}", window)

        headers = _headers(limit, limit - count, reset)
        if count > limit:
            headers["Retry-After"] = str(reset)
            response = problem_response(
                ErrorCodes.RATE_LIMITED,
                instance=path,
                detail=f"Zu viele Anfragen. Bitte in {reset} Sekunden erneut versuchen.",
                headers=headers,
            )
            await response(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                mutable = MutableHeaders(scope=message)
                for name, value in headers.items():
                    mutable[name] = value
            await send(message)

        await self.app(scope, receive, send_wrapper)
