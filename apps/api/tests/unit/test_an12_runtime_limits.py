"""AN12: runtime limits scale with load but never below the base limit."""

from __future__ import annotations

from tests import runtime_limits


def test_factor_bounds_and_scaling() -> None:
    factor = runtime_limits.load_factor()
    assert 1.0 <= factor <= runtime_limits.MAX_FACTOR
    assert runtime_limits.scaled_limit(10.0) >= 10.0
    assert runtime_limits.scaled_limit(10.0) == 10.0 * factor


def test_override(monkeypatch: object) -> None:
    import pytest

    mp = pytest.MonkeyPatch()
    mp.setattr(runtime_limits, "_factor", None)
    mp.setenv("MHVP_PERF_FACTOR", "3")
    try:
        assert runtime_limits.scaled_limit(2.0) == 6.0
    finally:
        mp.undo()
        runtime_limits._factor = None
