"""Liveness and readiness (M1 acceptance: health endpoints).

Readiness also enforces ADR 0002 at runtime: it fails if the API connects with a role that
could bypass row level security, and if the database is not at the Alembic head.
Failure details are fixed short strings; hosts, credentials and exceptions are only logged.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from alembic.config import Config
from alembic.script import ScriptDirectory
from botocore.exceptions import ClientError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from mhvp.core.config import Settings
from mhvp.core.logging import get_logger

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

SERVICE_NAME = "api"
_log = get_logger("mhvp.health")


class CheckStatus(StrEnum):
    OK = "ok"
    FAIL = "fail"


class CheckResult(BaseModel):
    status: CheckStatus
    latency_ms: float
    detail: str | None = None


class LiveReport(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class HealthReport(BaseModel):
    status: CheckStatus
    service: str
    version: str
    checks: dict[str, CheckResult]


class HealthCheckFailedError(Exception):
    """Raised by a check with a short, non-sensitive reason."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


ReadinessCheck = Callable[[], Awaitable[None]]


async def run_check(name: str, check: ReadinessCheck, limit_seconds: float) -> CheckResult:
    started = time.perf_counter()
    detail: str | None = None
    status = CheckStatus.OK
    try:
        await asyncio.wait_for(check(), timeout=limit_seconds)
    except HealthCheckFailedError as exc:
        status, detail = CheckStatus.FAIL, exc.detail
    except TimeoutError:
        status, detail = CheckStatus.FAIL, "timeout"
    except Exception as exc:
        _log.warning("readiness_check_error", check=name, error_type=type(exc).__name__)
        status, detail = CheckStatus.FAIL, "unavailable"
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return CheckResult(status=status, latency_ms=latency_ms, detail=detail)


async def run_readiness(
    checks: dict[str, ReadinessCheck], *, version: str, limit_seconds: float
) -> HealthReport:
    names = sorted(checks)
    results = await asyncio.gather(
        *(run_check(name, checks[name], limit_seconds) for name in names)
    )
    by_name = dict(zip(names, results, strict=True))
    overall = (
        CheckStatus.OK
        if by_name and all(r.status is CheckStatus.OK for r in results)
        else CheckStatus.FAIL
    )
    return HealthReport(status=overall, service=SERVICE_NAME, version=version, checks=by_name)


# Concrete checks -----------------------------------------------------------------------

_ROLE_QUERY = text(
    """
    SELECT r.rolsuper,
           r.rolbypassrls,
           (SELECT count(*) FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relowner = r.oid
               AND n.nspname NOT IN ('pg_catalog', 'information_schema')
               AND n.nspname NOT LIKE 'pg_toast%%') AS owned_relations,
           (SELECT count(*) FROM pg_namespace WHERE nspowner = r.oid) AS owned_schemas
      FROM pg_roles r
     WHERE r.rolname = current_user
    """
)


def database_check(engine: AsyncEngine) -> ReadinessCheck:
    async def check() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    return check


def database_role_check(engine: AsyncEngine) -> ReadinessCheck:
    async def check() -> None:
        async with engine.connect() as conn:
            row = (await conn.execute(_ROLE_QUERY)).one()
        if row.rolsuper:
            raise HealthCheckFailedError("runtime role is superuser")
        if row.rolbypassrls:
            raise HealthCheckFailedError("runtime role bypasses row level security")
        if row.owned_relations or row.owned_schemas:
            raise HealthCheckFailedError("runtime role owns database objects")

    return check


@lru_cache(maxsize=4)
def _alembic_heads(config_path: Path) -> frozenset[str]:
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise HealthCheckFailedError("migration scripts not found")
    config = Config(str(config_path))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def migrations_check(engine: AsyncEngine, config_path: Path) -> ReadinessCheck:
    async def check() -> None:
        heads = await asyncio.to_thread(_alembic_heads, config_path)
        try:
            async with engine.connect() as conn:
                rows = (await conn.execute(text("SELECT version_num FROM alembic_version"))).all()
        except ProgrammingError:
            raise HealthCheckFailedError("database not migrated") from None
        if frozenset(row.version_num for row in rows) != heads:
            raise HealthCheckFailedError("database revision is not the migration head")

    return check


def redis_check(client: Redis) -> ReadinessCheck:
    async def check() -> None:
        if not await client.ping():
            raise HealthCheckFailedError("no ping response")

    return check


def object_storage_check(settings: Settings, client: "S3Client | None") -> ReadinessCheck:
    async def check() -> None:
        if client is None:
            raise HealthCheckFailedError("not configured")
        try:
            await asyncio.to_thread(client.head_bucket, Bucket=settings.s3_bucket)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchBucket", "NotFound"}:
                raise HealthCheckFailedError("bucket missing") from None
            raise HealthCheckFailedError("unavailable") from None

    return check


# Router --------------------------------------------------------------------------------

router = APIRouter(prefix="/health", tags=["Betrieb"])


@router.get("/live", summary="Prozess läuft (Liveness)")
async def live(request: Request) -> LiveReport:
    settings: Settings = request.app.state.settings
    return LiveReport(service=SERVICE_NAME, version=settings.app_version)


@router.get(
    "/ready",
    summary="Abhängigkeiten erreichbar (Readiness)",
    response_model=HealthReport,
    responses={
        503: {"model": HealthReport, "description": "Mindestens eine Prüfung ist fehlgeschlagen."}
    },
)
async def ready(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    checks: dict[str, ReadinessCheck] = getattr(request.app.state, "readiness_checks", {})
    report = await run_readiness(
        checks, version=settings.app_version, limit_seconds=settings.health_check_timeout_seconds
    )
    status_code = 200 if report.status is CheckStatus.OK else 503
    return JSONResponse(report.model_dump(mode="json"), status_code=status_code)
