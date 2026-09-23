"""Celery job: delete prospect records after their deletion date (M26, data minimisation)."""

import asyncio
import uuid
from datetime import date

from celery import shared_task
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.letting.models import Prospect
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today


async def purge_prospects_once(settings: Settings, today: date | None = None) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    deleted = 0
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                result = await session.execute(
                    delete(Prospect).where(Prospect.delete_after < (today or local_today()))
                )
                deleted += int(getattr(result, "rowcount", 0) or 0)
    finally:
        await engine.dispose()
    return {"deleted": deleted}


@shared_task(name="mhvp.letting.purge_prospects")
def purge_prospects() -> dict[str, int]:
    return asyncio.run(purge_prospects_once(get_settings()))
