"""Celery job: daily reminders for maintenance items (M9 notifications)."""

import asyncio
import uuid
from datetime import date

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today, maintenance_reminders


async def reminders_once(settings: Settings, today: date | None = None) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    created = 0
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                created += await maintenance_reminders(session, today or local_today())
    finally:
        await engine.dispose()
    return {"created": created}


@shared_task(name="mhvp.workspace.reminders")
def reminders() -> dict[str, int]:
    return asyncio.run(reminders_once(get_settings()))
