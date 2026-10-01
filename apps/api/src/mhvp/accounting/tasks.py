"""Celery job accounting.dunning_run (15.1: monthly on the 5th): preview runs only, never sent."""

import asyncio
import uuid
from datetime import date

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.accounting import dunning
from mhvp.accounting.models import DunningRun, Ledger
from mhvp.automation.job_schedule import job_allowed
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today


async def dunning_previews(settings: Settings) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    runs = 0
    failed = 0
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    if not await job_allowed(session, tenant_id, "accounting-dunning-run"):
                        continue
                    if await session.scalar(select(Ledger.id).limit(1)) is None:
                        continue
                    await dunning.preview(
                        session, tenant_id=tenant_id, user_id=None, run_date=local_today()
                    )
                    runs += 1
            except Exception as exc:
                # M9-01: the failed preview rolled back; keep a failed run as visible evidence
                # (alert metric dunning_runs_failed_24h) and continue with the next tenant.
                failed += 1
                async with tenant_transaction(factory, tenant_id) as session:
                    session.add(
                        DunningRun(
                            tenant_id=tenant_id,
                            run_date=local_today(),
                            status="failed",
                            error=f"{type(exc).__name__}: {exc}"[:2000],
                        )
                    )
    finally:
        await engine.dispose()
    return {"runs": runs, "failed": failed}


@shared_task(name="mhvp.accounting.dunning_run")
def dunning_run() -> dict[str, int]:
    return asyncio.run(dunning_previews(get_settings()))


# Monthly receivable run (15.1 accounting.receivable_run, S15-01) ----------------------------


async def receivable_previews(settings: Settings, today: date | None = None) -> dict[str, int]:
    """Preview run for the current month per tenant that switched it on
    (``TenantSettings.receivable_rules.monthly_preview_enabled``, default off). Only previews
    are written; posting stays a manual action behind the existing gate checks (G1).
    Idempotent: a tenant with a run for the month (any status, scope ``all``) is skipped."""
    from mhvp.accounting import receivables
    from mhvp.accounting.models import ReceivableRun
    from mhvp.platform.models import TenantSettings

    month = (today or local_today()).replace(day=1)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    totals = {"tenants": 0, "runs": 0, "skipped": 0}
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                row = await session.scalar(select(TenantSettings))
                rules = dict(row.receivable_rules or {}) if row is not None else {}
                if not rules.get("monthly_preview_enabled"):
                    continue
                if not await job_allowed(session, tenant_id, "accounting-receivable-run"):
                    continue
                totals["tenants"] += 1
                existing = await session.scalar(
                    select(ReceivableRun.id).where(
                        ReceivableRun.period_month == month, ReceivableRun.scope == "all"
                    )
                )
                if existing is not None:
                    totals["skipped"] += 1
                    continue
                await receivables.create_preview(
                    session,
                    tenant_id=tenant_id,
                    user_id=None,
                    period=month,
                    scope="all",
                    scope_id=None,
                )
                totals["runs"] += 1
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.accounting.receivable_run")
def receivable_run() -> dict[str, int]:
    return asyncio.run(receivable_previews(get_settings()))


# Audit export (A26, 7.7, D55) ----------------------------------------------------------------


async def run_audit_export(settings: Settings, run_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    """Builds a queued audit export on the worker. Each step runs in the tenant transaction
    (RLS); a failure is recorded on the run instead of leaving it queued forever."""
    from mhvp.accounting import audit_export
    from mhvp.accounting.models import ExportRun
    from mhvp.documents.blobs import BlobStore

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                run = await session.scalar(select(ExportRun).where(ExportRun.id == run_id))
                if run is None or run.status == audit_export.ExportStatus.DONE.value:
                    return "skipped"
                ledger = await session.scalar(select(Ledger).where(Ledger.id == run.ledger_id))
                if ledger is None:
                    raise RuntimeError("ledger missing")
                await audit_export.execute(session, BlobStore(settings), run, ledger)
                return run.status
        except Exception as exc:
            async with tenant_transaction(factory, tenant_id) as session:
                run = await session.scalar(select(ExportRun).where(ExportRun.id == run_id))
                if run is not None:
                    run.status = audit_export.ExportStatus.FAILED.value
                    run.error = f"{type(exc).__name__}: {exc}"[:2000]
            raise
    finally:
        await engine.dispose()


@shared_task(name="mhvp.accounting.audit_export_run")
def audit_export_run(run_id: str, tenant_id: str) -> str:
    return asyncio.run(run_audit_export(get_settings(), uuid.UUID(run_id), uuid.UUID(tenant_id)))


# Open item balances (S69-04, 6.9.13) ---------------------------------------------------------


async def open_item_balance_refresh_all(
    settings: Settings, today: date | None = None
) -> dict[str, int]:
    """Nightly refresh of the maintained open item remainders per ledger (read copy only)."""
    from mhvp.accounting import open_item_balances

    day = today or local_today()
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    totals = {"ledgers": 0, "items": 0, "failed": 0}
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    if not await job_allowed(session, tenant_id, "accounting-open-item-balance"):
                        continue
                    for ledger in (await session.scalars(select(Ledger))).all():
                        totals["items"] += await open_item_balances.refresh(
                            session, ledger, day, source="job"
                        )
                        totals["ledgers"] += 1
            except Exception:  # next tenant; the copy is no source of truth
                totals["failed"] += 1
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.accounting.open_item_balance_refresh")
def open_item_balance_refresh() -> dict[str, int]:
    return asyncio.run(open_item_balance_refresh_all(get_settings()))
