"""Failure protocol of background jobs (GAM-504 to GAM-509, wave 26 AP07).

Two tables, both written outside the failing transaction so a rollback never loses the note:

* ``job_failure`` (tenant scoped, RLS): one row per failed tenant step of a scheduled job
  (automatic posting runner, event consumers, open item refresh, mandate expiry). ``job`` is a
  stable key, ``ref_id`` an optional reference (for example the bank sync run), ``error_type``
  the exception class name only. No message text is stored: messages may carry personal data.
* ``task_failure`` (platform, no tenant column): one row per Celery task that failed for good
  (``celery.signals.task_failure``; retries are not failures). Task name and exception class.

``workspace/ops.py`` counts both for the last 24 hours and alerts on them. Recording never
raises: a broken protocol must not turn a handled tenant error into a failed job.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.pool import NullPool

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin
from mhvp.core.logging import get_logger

log = get_logger(__name__)

# Stable job keys (metric names in workspace/ops.py depend on them).
JOB_AUTO_POST = "banking.auto_post"
JOB_BANKING_EVENTS = "banking.process_events"
JOB_AUTOMATION_EVENTS = "automation.process_events"
JOB_OPEN_ITEM_REFRESH = "accounting.open_item_balance_refresh"
JOB_EXPIRE_MANDATES = "contracts.expire_mandates"
JOB_RECEIVABLE_RUN = "accounting.receivable_run"
EVENT_CONSUMER_JOBS = (JOB_BANKING_EVENTS, JOB_AUTOMATION_EVENTS)


class JobFailure(IdMixin, TenantMixin, Base):
    __tablename__ = "job_failure"
    __table_args__ = (Index("ix_job_failure_tenant_job", "tenant_id", "job", "occurred_at"),)

    job: Mapped[str] = mapped_column(String(120), nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error_type: Mapped[str] = mapped_column(String(200), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TaskFailure(IdMixin, Base):
    __tablename__ = "task_failure"
    __table_args__ = (Index("ix_task_failure_occurred", "occurred_at"),)

    task: Mapped[str] = mapped_column(String(200), nullable=False)
    error_type: Mapped[str] = mapped_column(String(200), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def _error_type(exc: BaseException | None) -> str:
    return type(exc).__name__[:200] if exc is not None else "unknown"


async def record_job_failure(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    job: str,
    exc: BaseException | None,
    *,
    ref_id: uuid.UUID | None = None,
) -> bool:
    """Writes one ``job_failure`` row in its own tenant transaction; never raises."""
    from mhvp.core.db.tenancy import tenant_transaction

    try:
        async with tenant_transaction(factory, tenant_id) as session:
            session.add(
                JobFailure(tenant_id=tenant_id, job=job, ref_id=ref_id, error_type=_error_type(exc))
            )
        return True
    except Exception:
        log.exception("job_failure.record_failed", extra={"job": job, "tenant_id": str(tenant_id)})
        return False


async def _record_task_failure_async(database_url: str, task: str, error_type: str) -> None:
    from mhvp.core.db.engine import create_session_factory
    from mhvp.core.db.tenancy import platform_transaction

    engine = create_async_engine(database_url, poolclass=NullPool, hide_parameters=True)
    try:
        async with platform_transaction(create_session_factory(engine)) as session:
            session.add(TaskFailure(task=task[:200], error_type=error_type))
    finally:
        await engine.dispose()


def record_task_failure(task: str, exc: BaseException | None) -> bool:
    """Synchronous entry for the Celery signal; never raises."""
    try:
        from mhvp.core.config import get_settings

        url = get_settings().database_url.get_secret_value()
        asyncio.run(_record_task_failure_async(url, task, _error_type(exc)))
        return True
    except Exception:
        log.exception("task_failure.record_failed", extra={"task": task})
        return False


def on_task_failure(sender: Any = None, exception: BaseException | None = None, **_: Any) -> None:
    """Handler of ``celery.signals.task_failure`` (connected in ``mhvp.worker``). Fires only
    for a final failure; ``task.retry`` raises ``Retry`` and is not reported here."""
    name = str(getattr(sender, "name", "") or "")
    if not name.startswith("mhvp."):
        return
    log.error("task.failed", extra={"task": name, "error": _error_type(exception)})
    record_task_failure(name, exception)
