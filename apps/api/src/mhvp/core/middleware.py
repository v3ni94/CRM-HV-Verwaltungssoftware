"""Pure ASGI middleware: correlation id, sanitised access log, last resort error handler.

It is the outermost application middleware, so even unhandled exceptions produce an
RFC 9457 problem with ``X-Correlation-ID`` instead of Starlette's plain text 500.
"""

import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mhvp.core.context import reset_correlation_id, set_correlation_id
from mhvp.core.ids import uuid7
from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, problem_response

CORRELATION_HEADER = "X-Correlation-ID"
_log = get_logger("mhvp.access")


def _incoming_correlation_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-correlation-id":
            try:
                return str(uuid.UUID(value.decode("latin-1")))
            except ValueError:
                return None
    return None


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        correlation_id = _incoming_correlation_id(scope) or str(uuid7())
        token = set_correlation_id(correlation_id)
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[CORRELATION_HEADER] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            _log.exception("unhandled_exception", path=scope.get("path"))
            if response_started:
                raise
            response = problem_response(ErrorCodes.INTERNAL, instance=scope.get("path"))
            await response(scope, receive, send_wrapper)
        finally:
            # Path only: query strings may carry personal data (section 16).
            _log.info(
                "http_request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            structlog.contextvars.unbind_contextvars("correlation_id")
            reset_correlation_id(token)
