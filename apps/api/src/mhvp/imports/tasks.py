"""Celery jobs of the import assistant: the daily reconciliation report of the parallel
operation (13.1, A68). Read and compare only; per tenant in its own transaction, a tenant
without staged journal or bank rows is skipped, a failure is logged and the next tenant runs
(same engine and transaction pattern as ``mhvp.objektakte.tasks``).

The time of day comes from ``Settings.import_reconciliation_time`` (default 05:30, Europe/Berlin
as the Celery timezone); the beat entry lives in ``mhvp.worker``.
"""

import asyncio
import logging
import uuid

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.problems import ProblemError
from mhvp.imports import reconciliation as rec
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)


def beat_time(settings: Settings) -> tuple[int, int]:
    """``"05:30"`` -> ``(5, 30)``; validated by the settings pattern."""
    hour, minute = settings.import_reconciliation_time.split(":")
    return int(hour), int(minute)


async def report_tenant_once(
    settings: Settings, tenant_id: uuid.UUID, *, trigger: str
) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    counts = {"ran": 0, "skipped": 0, "failed": 0}
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            if not await rec.latest_sources(session):
                counts["skipped"] += 1
                return counts
            try:
                await rec.create_report(session, tenant_id, None, trigger=trigger)
            except ProblemError as exc:
                log.warning("reconciliation report failed for tenant %s: %s", tenant_id, exc)
                counts["failed"] += 1
                return counts
        counts["ran"] += 1
    except Exception as exc:  # recorded per tenant, other tenants continue
        log.warning("reconciliation report failed for tenant %s: %s", tenant_id, exc)
        counts["failed"] += 1
    finally:
        await engine.dispose()
    return counts


async def report_all_once(settings: Settings) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with platform_transaction(factory) as session:
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
    finally:
        await engine.dispose()
    totals = {"tenants": len(ids), "ran": 0, "skipped": 0, "failed": 0}
    for tenant_id in ids:
        for key, value in (await report_tenant_once(settings, tenant_id, trigger="beat")).items():
            totals[key] += value
    return totals


@shared_task(name="mhvp.imports.reconciliation_all")
def reconciliation_all() -> dict[str, int]:
    """Celery beat entry (daily, `mhvp.worker`): one report per active tenant with staged rows."""
    return asyncio.run(report_all_once(get_settings()))


@shared_task(name="mhvp.imports.reconciliation_tenant")
def reconciliation_tenant(tenant_id: str) -> dict[str, int]:
    return asyncio.run(report_tenant_once(get_settings(), uuid.UUID(tenant_id), trigger="manual"))
