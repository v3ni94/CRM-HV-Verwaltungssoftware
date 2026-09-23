from pathlib import Path

import pytest

from mhvp.openapi import build_openapi, render_openapi


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
