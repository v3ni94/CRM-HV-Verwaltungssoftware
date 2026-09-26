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
"""

import time

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mhvp.core.config import Settings
from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, problem_response
from mhvp.core.request_identity import client_ip, identify

WINDOW_SECONDS = 60
EXEMPT_PREFIXES = ("/api/v1/health",)

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
        if identity is not None:
            limit = settings.rate_limit_per_minute_user
            subject = identity.scope_key
        else:
            limit = settings.rate_limit_per_minute_anonymous
            subject = "ip:" + client_ip(
                scope, trust_forwarded_for=settings.rate_limit_trust_forwarded_for
            )

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
            await self.app(scope, receive, send)
            return

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
