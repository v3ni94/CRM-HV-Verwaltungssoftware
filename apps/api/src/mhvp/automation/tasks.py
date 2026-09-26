"""Celery beat job ``mhvp.automation.process_events``: every minute, per active tenant, new
domain events since the watermark are matched against the active rules (section 15.2, A38).
The event system itself is untouched (no hook in ``emit``)."""

import asyncio
import logging
import uuid
from datetime import datetime

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.automation.services import process_tenant
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)


async def process_events_once(settings: Settings, *, now: datetime | None = None) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    totals = {"tenants": 0, "events": 0, "runs": 0, "failed": 0}
    try:
        factory = create_session_factory(engine)
        async with platform_transaction(factory) as session:
            tenant_ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenant_ids:
            totals["tenants"] += 1
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    result = await process_tenant(session, tenant_id, now=now)
                for key in ("events", "runs", "failed"):
                    totals[key] += result[key]
            except Exception:
                log.warning("automation process_events failed", extra={"tenant_id": str(tenant_id)})
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.automation.process_events")
def process_events() -> dict[str, int]:
    return asyncio.run(process_events_once(get_settings()))
