"""Job ``ops.backup_verify`` (A67, M9, MASTER-PROMPT 15.1, 16 Beobachtbarkeit).

Runs the restore test ``scripts/backup-verify.sh`` (newest dump into a throwaway database,
checksum, schema revision and row counts) and records the result for the operating metrics
(``GET /api/v1/platform/ops/metrics``): status, start time, duration, checked backup file,
exit code, error text. The record lives in Redis (no table, no personal data); one record,
overwritten per run, so the metrics always show the latest restore test. Without
``Settings.backup_verify_enabled`` or without the script the job records ``not_configured``
instead of failing: a missing restore test is visible, never silent (rule 0.1.3, M9-02).
"""

import asyncio
import json
import os
import shutil
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from celery import shared_task
from redis.asyncio import Redis

from mhvp.core.config import Settings, get_settings
from mhvp.core.logging import get_logger

log = get_logger(__name__)

RESULT_KEY = "mhvp:ops:backup_verify:last"
# Result stays readable for a week; a job that stopped running becomes visible as "missing".
RESULT_TTL_SECONDS = 7 * 86400
STALE_AFTER_SECONDS = 36 * 3600
STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_NOT_CONFIGURED = "not_configured"
OUTPUT_TAIL_CHARS = 2000
FILE_MARKER = "backup-verify: file "

Runner = Callable[[list[str], int], Awaitable[tuple[int, str, str]]]


async def run_script(command: list[str], timeout_seconds: int) -> tuple[int, str, str]:
    """Runs the script; returns exit code, stdout and stderr. A timeout yields exit code
    124 like ``timeout(1)`` so the record can tell it from a script failure."""
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=dict(os.environ),
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        await process.wait()
        return 124, "", f"timeout after {timeout_seconds} s"
    return process.returncode or 0, out.decode(errors="replace"), err.decode(errors="replace")


def checked_file(stdout: str) -> str | None:
    """The backup file named by the script (``backup-verify: file <path>``)."""
    for line in stdout.splitlines():
        if line.startswith(FILE_MARKER):
            return line[len(FILE_MARKER) :].strip() or None
    return None


def resolve_script(settings: Settings) -> Path | None:
    """The script path when it exists and is executable; relative paths are resolved from the
    working directory and from the repository root above ``apps/api``."""
    raw = settings.backup_verify_script
    candidates = [Path(raw)]
    if not Path(raw).is_absolute():
        here = Path(__file__).resolve()
        candidates.append(here.parents[4] / raw if len(here.parents) > 4 else Path(raw))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


async def verify_once(
    settings: Settings, *, runner: Runner | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """One restore test. Never raises: every outcome is a record for the metrics."""
    started = now or datetime.now(UTC)
    record: dict[str, Any] = {
        "status": STATUS_NOT_CONFIGURED,
        "started_at": started.isoformat(),
        "duration_seconds": 0.0,
        "checked_file": None,
        "exit_code": None,
        "error": None,
        "script": None,
    }
    if not settings.backup_verify_enabled:
        record["error"] = "MHVP_BACKUP_VERIFY_ENABLED is false"
        return record
    script = resolve_script(settings)
    if script is None:
        record["error"] = f"script not found or not executable: {settings.backup_verify_script}"
        return record
    record["script"] = str(script)
    command = [str(script)]
    if shutil.which("bash") and script.suffix == ".sh":
        command = ["bash", str(script)]
    clock = time.monotonic()
    try:
        code, out, err = await (runner or run_script)(
            command, settings.backup_verify_timeout_seconds
        )
    except OSError as exc:  # script vanished, permission denied, ...
        code, out, err = 127, "", f"{type(exc).__name__}: {exc}"
    record["duration_seconds"] = round(time.monotonic() - clock, 3)
    record["exit_code"] = code
    record["checked_file"] = checked_file(out)
    if code == 0:
        record["status"] = STATUS_OK
    else:
        record["status"] = STATUS_FAILED
        tail = (err.strip() or out.strip())[-OUTPUT_TAIL_CHARS:]
        record["error"] = tail or f"exit code {code}"
    return record


async def store_result(redis: Redis, record: dict[str, Any]) -> None:
    await redis.set(RESULT_KEY, json.dumps(record, sort_keys=True), ex=RESULT_TTL_SECONDS)


async def load_result(redis: Redis) -> dict[str, Any] | None:
    raw = await redis.get(RESULT_KEY)
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def summarize(record: dict[str, Any] | None, *, now: datetime | None = None) -> dict[str, Any]:
    """Metrics view of the last run: the record plus ``age_seconds`` and ``stale``. Without a
    record the job has not run within the result TTL (or never)."""
    current = now or datetime.now(UTC)
    if record is None:
        return {
            "status": "missing",
            "started_at": None,
            "duration_seconds": None,
            "checked_file": None,
            "exit_code": None,
            "error": "no run recorded",
            "age_seconds": None,
            "stale": True,
        }
    age: float | None = None
    try:
        started = datetime.fromisoformat(str(record.get("started_at")))
        age = round((current - started).total_seconds(), 3)
    except (TypeError, ValueError):
        age = None
    out = {
        key: record.get(key)
        for key in (
            "status",
            "started_at",
            "duration_seconds",
            "checked_file",
            "exit_code",
            "error",
        )
    }
    out["age_seconds"] = age
    out["stale"] = age is None or age > STALE_AFTER_SECONDS
    return out


async def backup_verify_once(settings: Settings, *, runner: Runner | None = None) -> dict[str, Any]:
    record = await verify_once(settings, runner=runner)
    redis = Redis.from_url(settings.redis_url.get_secret_value())
    try:
        await store_result(redis, record)
    finally:
        await redis.aclose()
    log.info(
        "backup_verify",
        status=record["status"],
        duration_seconds=record["duration_seconds"],
        checked_file=record["checked_file"],
        error=record["error"],
    )
    return record


@shared_task(name="mhvp.ops.backup_verify")
def backup_verify() -> dict[str, Any]:
    return asyncio.run(backup_verify_once(get_settings()))
