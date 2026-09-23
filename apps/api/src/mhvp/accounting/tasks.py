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
