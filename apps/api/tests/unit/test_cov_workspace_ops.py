"""Coverage: operations metrics helpers (M9, A67) without database: job protocol view from
Redis (missing, error, stored), gauges derived from it, and the alert list of the JSON view."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Request

from mhvp.workspace import backup_verify, ops


def _request(resources: Any) -> Request:
    app = SimpleNamespace(state=SimpleNamespace(resources=resources))
    return SimpleNamespace(app=app)  # type: ignore[return-value]


class _Redis:
    def __init__(self, raw: bytes | None = None, error: bool = False) -> None:
        self._raw = raw
        self._error = error

    async def get(self, key: str) -> bytes | None:
        if self._error:
            raise ConnectionError("redis down")
        assert key == backup_verify.RESULT_KEY
        return self._raw


def test_job_results_without_resources_is_missing() -> None:
    jobs = asyncio.run(ops.job_results(_request(None)))
    assert jobs["backup_verify"]["status"] == "missing"
    assert jobs["backup_verify"]["stale"] is True


def test_job_results_swallows_redis_errors() -> None:
    jobs = asyncio.run(ops.job_results(_request(SimpleNamespace(redis=_Redis(error=True)))))
    assert jobs["backup_verify"]["status"] == "missing"


def test_job_results_reads_stored_record() -> None:
    started = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    raw = (
        f'{{"status": "ok", "started_at": "{started}", "duration_seconds": 12.5, '
        '"checked_file": "/backups/x.dump", "exit_code": 0, "error": null}'
    ).encode()
    jobs = asyncio.run(ops.job_results(_request(SimpleNamespace(redis=_Redis(raw)))))
    result = jobs["backup_verify"]
    assert result["status"] == "ok"
    assert result["checked_file"] == "/backups/x.dump"
    assert result["stale"] is False
    assert result["age_seconds"] is not None
    assert 290 <= result["age_seconds"] <= 400


@pytest.mark.parametrize(
    ("status", "stale", "expected"),
    [
        (backup_verify.STATUS_OK, False, {"ok": 1, "failed": 0, "not_configured": 0, "stale": 0}),
        (
            backup_verify.STATUS_FAILED,
            True,
            {"ok": 0, "failed": 1, "not_configured": 0, "stale": 1},
        ),
        (
            backup_verify.STATUS_NOT_CONFIGURED,
            True,
            {"ok": 0, "failed": 0, "not_configured": 1, "stale": 1},
        ),
        ("missing", True, {"ok": 0, "failed": 0, "not_configured": 0, "stale": 1}),
    ],
)
def test_job_gauges_map_status_to_flags(status: str, stale: bool, expected: dict[str, int]) -> None:
    jobs = {
        "backup_verify": {
            "status": status,
            "stale": stale,
            "duration_seconds": 3.9,
            "age_seconds": None,
        }
    }
    gauges = ops.job_gauges(jobs)
    assert gauges["backup_verify_ok"] == expected["ok"]
    assert gauges["backup_verify_failed"] == expected["failed"]
    assert gauges["backup_verify_not_configured"] == expected["not_configured"]
    assert gauges["backup_verify_stale"] == expected["stale"]
    assert gauges["backup_verify_duration_seconds"] == 3
    assert gauges["backup_verify_age_seconds"] == 0


def test_alerting_set_lists_failure_metrics_only() -> None:
    assert "backup_verify_failed" in ops.ALERTING
    assert "backup_verify_stale" in ops.ALERTING
    assert "tenants_active" not in ops.ALERTING
    assert "backup_verify_ok" not in ops.ALERTING
