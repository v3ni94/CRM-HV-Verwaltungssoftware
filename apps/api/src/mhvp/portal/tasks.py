"""Celery job: persist due portal account status transitions for every active tenant (AB08)."""

import asyncio
from datetime import datetime

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.portal.status import sync_statuses


async def sync_all(factory: async_sessionmaker, now: datetime | None = None) -> dict[str, int]:  # type: ignore[type-arg]
    totals = {"expired": 0, "locked": 0, "unlocked": 0}
    async with platform_transaction(factory) as session:
        tenant_ids = list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )
    for tenant_id in tenant_ids:
        async with tenant_transaction(factory, tenant_id) as session:
            for key, n in (await sync_statuses(session, tenant_id, now)).items():
                totals[key] += n
    return totals


async def _run() -> dict[str, int]:
    engine = create_async_engine(
        get_settings().database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        return await sync_all(create_session_factory(engine))
    finally:
        await engine.dispose()


@shared_task(name="mhvp.portal.sync_account_status")
def sync_account_status() -> dict[str, int]:
    return asyncio.run(_run())
