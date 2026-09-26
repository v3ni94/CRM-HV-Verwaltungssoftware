"""Celery job accounting.dunning_run (15.1: monthly on the 5th): preview runs only, never sent."""

import asyncio
import uuid

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.accounting import dunning
from mhvp.accounting.models import Ledger
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
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                if await session.scalar(select(Ledger.id).limit(1)) is None:
                    continue
                await dunning.preview(
                    session, tenant_id=tenant_id, user_id=None, run_date=local_today()
                )
                runs += 1
    finally:
        await engine.dispose()
    return {"runs": runs}


@shared_task(name="mhvp.accounting.dunning_run")
def dunning_run() -> dict[str, int]:
    return asyncio.run(dunning_previews(get_settings()))


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
