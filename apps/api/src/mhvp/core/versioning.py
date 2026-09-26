"""API versioning rule as a middleware building block (MASTER-PROMPT 12, ADR 0009, A50).

Every response carries ``API-Version`` (the running application version). Endpoints that are
marked deprecated additionally carry ``Deprecation`` (RFC 9745, the date the endpoint was
deprecated), ``Sunset`` (RFC 8594, the earliest removal date, at least six months later) and a
``Link`` header with ``rel="successor-version"`` when a successor exists. The same marks are
written into the OpenAPI document (``deprecated: true`` plus ``x-deprecated-on``, ``x-sunset``
and ``x-successor``), so the drift check in ``tests/unit/test_openapi.py`` can tell an allowed
removal from a breaking one.

Rule: additive changes never change the version. A path or a required field is removed only
under ``/api/v2`` and after the sunset date, which lies at least ``MIN_NOTICE_MONTHS`` months
after the deprecation date.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from email.utils import format_datetime
from typing import Any, TypeVar

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_VERSION_HEADER = "API-Version"
DEPRECATION_HEADER = "Deprecation"
SUNSET_HEADER = "Sunset"
LINK_HEADER = "Link"
MIN_NOTICE_MONTHS = 6
DEPRECATION_ATTR = "__mhvp_deprecation__"

F = TypeVar("F", bound=Callable[..., Any])


def add_months(day: date, months: int) -> date:
    """Calendar month arithmetic without external dependencies; clamps to the month end."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = (date(year + (month == 12), month % 12 + 1, 1) - date(year, month, 1)).days
    return date(year, month, min(day.day, last_day))


def http_date(day: date) -> str:
    """IMF-fixdate (RFC 9110) at midnight UTC, as required by Deprecation and Sunset."""
    return format_datetime(datetime.combine(day, time.min, tzinfo=UTC), usegmt=True)


@dataclass(frozen=True, slots=True)
class Deprecation:
    """Deprecation mark of one endpoint. ``sunset_on`` must lie at least six months after
    ``deprecated_on`` (MASTER-PROMPT 12: Deprecation-Header mindestens 6 Monate)."""

    deprecated_on: date
    sunset_on: date
    successor: str | None = None

    def __post_init__(self) -> None:
        earliest = add_months(self.deprecated_on, MIN_NOTICE_MONTHS)
        if self.sunset_on < earliest:
            raise ValueError(
                f"sunset_on {self.sunset_on.isoformat()} lies before the earliest allowed "
                f"date {earliest.isoformat()} ({MIN_NOTICE_MONTHS} months after deprecation)"
            )
        if self.successor is not None and not self.successor.startswith("/"):
            raise ValueError("successor must be an absolute API path such as /api/v2/...")

    def headers(self) -> dict[str, str]:
        out = {
            DEPRECATION_HEADER: http_date(self.deprecated_on),
            SUNSET_HEADER: http_date(self.sunset_on),
        }
        if self.successor:
            out[LINK_HEADER] = f'<{self.successor}>; rel="successor-version"'
        return out

    def openapi_extra(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "x-deprecated-on": self.deprecated_on.isoformat(),
            "x-sunset": self.sunset_on.isoformat(),
        }
        if self.successor:
            out["x-successor"] = self.successor
        return out


def deprecated(
    *, deprecated_on: date, sunset_on: date, successor: str | None = None
) -> Callable[[F], F]:
    """Marks an endpoint function as deprecated. Apply below the router decorator::

    @router.get("/old")
    @deprecated(deprecated_on=date(2026, 10, 1), sunset_on=date(2027, 4, 1),
                successor="/api/v2/new")
    async def old(...): ...
    """
    mark = Deprecation(deprecated_on=deprecated_on, sunset_on=sunset_on, successor=successor)

    def decorate(func: F) -> F:
        setattr(func, DEPRECATION_ATTR, mark)
        return func

    return decorate


# Registry for endpoints that cannot carry the decorator (e.g. routes from third party
# routers): key is (METHOD, full path template).
_REGISTRY: dict[tuple[str, str], Deprecation] = {}


def register_deprecation(method: str, path: str, mark: Deprecation) -> None:
    _REGISTRY[(method.upper(), path)] = mark


def clear_registry() -> None:
    _REGISTRY.clear()


def deprecation_for(route: Any, method: str) -> Deprecation | None:
    """Mark of a route: set directly on the route (by ``mark_deprecated_routes`` from the
    registry), on its endpoint function (decorator) or registered under the route's own path."""
    mark = getattr(route, DEPRECATION_ATTR, None)
    if isinstance(mark, Deprecation):
        return mark
    endpoint = getattr(route, "endpoint", None)
    mark = getattr(endpoint, DEPRECATION_ATTR, None)
    if isinstance(mark, Deprecation):
        return mark
    return _REGISTRY.get((method.upper(), str(getattr(route, "path", ""))))


def _route_contexts(app: FastAPI) -> list[Any]:
    """Routes with their full path (include prefixes applied). FastAPI 0.141 keeps included
    routers as nested objects; ``iter_route_contexts`` flattens them. Older versions expose the
    APIRoutes directly in ``app.routes``."""
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # pragma: no cover - FastAPI < 0.141
        return list(app.routes)
    return list(iter_route_contexts(app.routes))


def mark_deprecated_routes(app: FastAPI) -> dict[tuple[str, str], Deprecation]:
    """Writes the deprecation marks of all registered routes into the OpenAPI document and
    stores the mark on the route for the middleware. Call after every ``include_router``.
    Returns the marks found, keyed by (METHOD, full path)."""
    found: dict[tuple[str, str], Deprecation] = {}
    for context in _route_contexts(app):
        original = getattr(context, "original_route", context)
        if not isinstance(original, APIRoute):
            continue
        full_path = str(getattr(context, "path", None) or original.path)
        effective = getattr(context, "_effective_route", original)
        for method in original.methods or ():
            mark = deprecation_for(original, method) or _REGISTRY.get((method.upper(), full_path))
            if mark is None:
                continue
            setattr(original, DEPRECATION_ATTR, mark)
            for target in {id(original): original, id(effective): effective}.values():
                target.deprecated = True
                extra = dict(getattr(target, "openapi_extra", None) or {})
                extra.update(mark.openapi_extra())
                target.openapi_extra = extra
            found[(method, full_path)] = mark
    return found


class ApiVersionMiddleware:
    """Pure ASGI middleware: ``API-Version`` on every HTTP response, deprecation headers on
    responses of deprecated routes. The matched route is read from the scope after routing."""

    def __init__(self, app: ASGIApp, version: str) -> None:
        self.app = app
        self.version = version

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[API_VERSION_HEADER] = self.version
                route = scope.get("route")
                if route is not None:
                    mark = deprecation_for(route, str(scope.get("method", "")))
                    if mark is not None:
                        for name, value in mark.headers().items():
                            headers[name] = value
            await send(message)

        await self.app(scope, receive, send_wrapper)
