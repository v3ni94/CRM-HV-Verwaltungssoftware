from datetime import date
from pathlib import Path
from typing import Any

import pytest

from mhvp.openapi import breaking_removals, build_openapi, check_committed, render_openapi


def test_contains_m1_paths_and_problem_free_health() -> None:
    spec = build_openapi()
    assert spec["info"]["title"] == "MH Verwaltungsplattform API"
    assert {"/api/v1/health/live", "/api/v1/health/ready"} <= set(spec["paths"])
    ready = spec["paths"]["/api/v1/health/ready"]["get"]["responses"]
    assert {"200", "503"} <= set(ready)


def test_render_is_deterministic() -> None:
    assert render_openapi() == render_openapi()


def test_committed_spec_is_current() -> None:
    committed = Path("openapi.json")
    if not committed.exists():
        pytest.fail("apps/api/openapi.json missing: run make openapi")
    assert committed.read_text() == render_openapi(), "run make openapi"


def test_main_module_exposes_app_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    import mhvp.main

    with pytest.raises(AttributeError):
        _ = mhvp.main.does_not_exist


# Drift check against the versioning rule (ADR 0009, A50) --------------------------------


def _spec(paths: dict[str, Any], schemas: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"openapi": "3.1.0", "paths": paths, "components": {"schemas": schemas or {}}}


def test_drift_removed_path_without_deprecation_fails() -> None:
    old = _spec({"/api/v1/things": {"get": {"responses": {"200": {}}}}})
    new = _spec({})
    problems = breaking_removals(old, new, today=date(2026, 9, 26))
    assert problems == [
        "GET /api/v1/things removed without deprecation mark and passed sunset (ADR 0009)"
    ]


def test_drift_removed_path_before_sunset_fails_and_after_sunset_passes() -> None:
    marked = {
        "get": {
            "responses": {"200": {}},
            "deprecated": True,
            "x-deprecated-on": "2026-03-01",
            "x-sunset": "2026-09-01",
            "x-successor": "/api/v2/things",
        }
    }
    old = _spec({"/api/v1/things": marked})
    assert breaking_removals(old, _spec({}), today=date(2026, 8, 31))
    assert breaking_removals(old, _spec({}), today=date(2026, 9, 1)) == []


def test_drift_removed_method_is_reported_per_method() -> None:
    old = _spec({"/api/v1/things": {"get": {"responses": {}}, "delete": {"responses": {}}}})
    new = _spec({"/api/v1/things": {"get": {"responses": {}}}})
    problems = breaking_removals(old, new, today=date(2026, 9, 26))
    assert len(problems) == 1
    assert problems[0].startswith("DELETE /api/v1/things")


def test_drift_removed_property_fails_unless_deprecated() -> None:
    old = _spec(
        {},
        {
            "ThingOut": {
                "properties": {
                    "id": {"type": "string"},
                    "legacy": {"type": "string", "deprecated": True},
                    "name": {"type": "string"},
                }
            }
        },
    )
    new = _spec({}, {"ThingOut": {"properties": {"id": {"type": "string"}}}})
    assert breaking_removals(old, new, today=date(2026, 9, 26)) == [
        "schema ThingOut: property name removed without deprecation mark"
    ]


def test_drift_additive_changes_and_unreferenced_schema_removal_pass() -> None:
    old = _spec(
        {"/api/v1/things": {"get": {"responses": {}}}},
        {"Gone": {"properties": {"x": {}}}, "ThingOut": {"properties": {"id": {}}}},
    )
    new = _spec(
        {
            "/api/v1/things": {"get": {"responses": {}}, "post": {"responses": {}}},
            "/api/v1/others": {"get": {"responses": {}}},
        },
        {"ThingOut": {"properties": {"id": {}, "name": {}}}, "NewOut": {"properties": {}}},
    )
    assert breaking_removals(old, new, today=date(2026, 9, 26)) == []


def test_drift_removed_schema_still_referenced_fails() -> None:
    old = _spec({}, {"Gone": {"properties": {}}})
    new = _spec(
        {"/api/v1/x": {"get": {"responses": {"200": {"$ref": "#/components/schemas/Gone"}}}}},
        {},
    )
    assert breaking_removals(old, new, today=date(2026, 9, 26)) == [
        "schema Gone removed but still referenced"
    ]


def test_committed_spec_has_no_undeclared_removals() -> None:
    """The committed document may only lose paths and fields that were deprecated with a
    passed sunset date (ADR 0009). Also run by ``make openapi-check``."""
    assert check_committed(Path("openapi.json")) == []
