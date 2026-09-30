"""Celery job of the monthly consumption information (rule H03, section 15.1
``heating.consumption_info``): monthly on the 3rd (S15-05) for the previous
month, per active tenant with the tenant switch on, idempotent per unit and month."""

import asyncio
import uuid
from datetime import date
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.billing import consumption_info
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today


async def _active_tenants(factory: Any) -> list[uuid.UUID]:
    async with platform_transaction(factory) as session:
        return list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )


async def run_once(
    settings: Settings, today: date | None = None, *, force: bool = False
) -> dict[str, int]:
    """Previous month for every active tenant. Without ``force`` only on the 3rd of the
    month; another day reports ``not_due`` and changes nothing."""
    from mhvp.documents.blobs import BlobStore

    today = today or local_today()
    totals = {
        "tenants": 0,
        "properties": 0,
        "created": 0,
        "skipped": 0,
        "incomplete": 0,
        "notified": 0,
        "not_due": 0,
    }
    # S15-05: due on the 3rd of the month as in 15.1 (was: first working day, see
    # docs/ASSUMPTIONS.md); a later day reports ``not_due`` and changes nothing.
    if not force and today.day != 3:
        totals["not_due"] = 1
        return totals
    month = consumption_info.previous_month(today)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    blobs = BlobStore(settings)
    try:
        for tenant_id in await _active_tenants(factory):
            totals["tenants"] += 1
            async with tenant_transaction(factory, tenant_id) as session:
                counts = await consumption_info.run_tenant(
                    session, blobs, tenant_id=tenant_id, month=month, actor=None, trigger="job"
                )
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.billing.consumption_info")
def consumption_info_job() -> dict[str, int]:
    return asyncio.run(run_once(get_settings()))
