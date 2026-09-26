"""API versioning rule (ADR 0009, A50): API-Version on every response, Deprecation, Sunset
and Link headers on deprecated routes, six months minimum notice, OpenAPI marks."""

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from mhvp.core.config import Settings
from mhvp.core.versioning import (
    API_VERSION_HEADER,
    Deprecation,
    add_months,
    clear_registry,
    deprecated,
    http_date,
    mark_deprecated_routes,
    register_deprecation,
)
from tests.unit.helpers import app_with_checks

DEPRECATED_ON = date(2026, 10, 1)
SUNSET_ON = date(2027, 4, 1)


# Unit ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 8, 31), 6, date(2027, 2, 28)),
        (date(2026, 10, 1), 6, date(2027, 4, 1)),
        (date(2026, 12, 15), 12, date(2027, 12, 15)),
        (date(2028, 2, 29), 12, date(2029, 2, 28)),
    ],
)
def test_add_months_clamps_to_month_end(day: date, months: int, expected: date) -> None:
    assert add_months(day, months) == expected


def test_http_date_is_imf_fixdate_at_midnight_utc() -> None:
    assert http_date(date(2026, 10, 1)) == "Thu, 01 Oct 2026 00:00:00 GMT"


def test_deprecation_requires_six_months_notice() -> None:
    with pytest.raises(ValueError, match="6 months"):
        Deprecation(deprecated_on=DEPRECATED_ON, sunset_on=date(2027, 3, 31))
    mark = Deprecation(deprecated_on=DEPRECATED_ON, sunset_on=SUNSET_ON)
    assert mark.headers() == {
        "Deprecation": "Thu, 01 Oct 2026 00:00:00 GMT",
        "Sunset": "Thu, 01 Apr 2027 00:00:00 GMT",
    }
    assert mark.openapi_extra() == {"x-deprecated-on": "2026-10-01", "x-sunset": "2027-04-01"}


def test_deprecation_successor_must_be_absolute_path() -> None:
    with pytest.raises(ValueError, match="absolute API path"):
        Deprecation(deprecated_on=DEPRECATED_ON, sunset_on=SUNSET_ON, successor="v2/things")
    mark = Deprecation(deprecated_on=DEPRECATED_ON, sunset_on=SUNSET_ON, successor="/api/v2/things")
    assert mark.headers()["Link"] == '</api/v2/things>; rel="successor-version"'
    assert mark.openapi_extra()["x-successor"] == "/api/v2/things"


# Integration with the application ------------------------------------------------------


def _router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/versioning-test")

    @router.get("/old")
    @deprecated(deprecated_on=DEPRECATED_ON, sunset_on=SUNSET_ON, successor="/api/v2/new")
    async def old() -> dict[str, str]:
        return {"status": "old"}

    @router.get("/current")
    async def current() -> dict[str, str]:
        return {"status": "current"}

    @router.get("/registered")
    async def registered() -> dict[str, str]:
        return {"status": "registered"}

    return router


@pytest.fixture
def registry() -> Iterator[None]:
    clear_registry()
    yield
    clear_registry()


def test_every_response_carries_api_version(settings: Settings) -> None:
    with TestClient(app_with_checks(settings)) as client:
        live = client.get("/api/v1/health/live")
        missing = client.get("/api/v1/does-not-exist")
    assert live.headers[API_VERSION_HEADER] == settings.app_version
    assert missing.status_code == 404
    assert missing.headers[API_VERSION_HEADER] == settings.app_version
    assert "Deprecation" not in live.headers
    assert "Sunset" not in live.headers


def test_deprecated_route_carries_headers_and_openapi_marks(
    settings: Settings, registry: None
) -> None:
    app = app_with_checks(settings)
    app.include_router(_router())
    register_deprecation(
        "GET",
        "/api/v1/versioning-test/registered",
        Deprecation(deprecated_on=DEPRECATED_ON, sunset_on=SUNSET_ON),
    )
    found = mark_deprecated_routes(app)
    assert set(found) == {
        ("GET", "/api/v1/versioning-test/old"),
        ("GET", "/api/v1/versioning-test/registered"),
    }
    with TestClient(app) as client:
        old = client.get("/api/v1/versioning-test/old")
        current = client.get("/api/v1/versioning-test/current")
        registered = client.get("/api/v1/versioning-test/registered")
        spec = client.get("/api/v1/openapi.json").json()
    assert old.status_code == 200
    assert old.headers["Deprecation"] == "Thu, 01 Oct 2026 00:00:00 GMT"
    assert old.headers["Sunset"] == "Thu, 01 Apr 2027 00:00:00 GMT"
    assert old.headers["Link"] == '</api/v2/new>; rel="successor-version"'
    assert old.headers[API_VERSION_HEADER] == settings.app_version
    assert "Deprecation" not in current.headers
    assert registered.headers["Sunset"] == "Thu, 01 Apr 2027 00:00:00 GMT"
    assert "Link" not in registered.headers
    operation = spec["paths"]["/api/v1/versioning-test/old"]["get"]
    assert operation["deprecated"] is True
    assert operation["x-deprecated-on"] == "2026-10-01"
    assert operation["x-sunset"] == "2027-04-01"
    assert operation["x-successor"] == "/api/v2/new"
    assert "deprecated" not in spec["paths"]["/api/v1/versioning-test/current"]["get"]
    assert spec["paths"]["/api/v1/versioning-test/registered"]["get"]["deprecated"] is True


def test_committed_document_has_no_deprecations_without_sunset() -> None:
    """Every deprecated operation in the running application carries its dates."""
    from mhvp.openapi import build_openapi

    for path, item in build_openapi()["paths"].items():
        for method, operation in item.items():
            if isinstance(operation, dict) and operation.get("deprecated"):
                assert "x-sunset" in operation, f"{method.upper()} {path}"
                assert "x-deprecated-on" in operation, f"{method.upper()} {path}"
