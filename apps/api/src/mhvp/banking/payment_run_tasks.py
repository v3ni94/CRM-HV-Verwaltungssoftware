"""Celery job payments.payment_run (15.1, S15-02): weekly Monday 08:00, preview only.

Only tenants that switched on ``payment_run_setting.weekly_preview_enabled`` (default off) get
a stored preview of payable invoices, due direct debit runs and missing pre-notifications. The
job creates no payment order, no file and no posting; payment initiation stays behind G2.
"""

import asyncio
import uuid
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.accounting.direct_debit_models import PaymentRunPreview, PaymentRunSetting
from mhvp.banking import payment_run
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today


async def store_preview(
    session: AsyncSession, tenant_id: uuid.UUID, *, trigger: str, user_id: uuid.UUID | None
) -> PaymentRunPreview:
    today = local_today()
    summary: dict[str, Any] = await payment_run.preview(session, as_of=today)
    row = PaymentRunPreview(
        tenant_id=tenant_id, created_by=user_id, as_of=today, trigger=trigger, summary=summary
    )
    session.add(row)
    await session.flush()
    return row


async def weekly_previews(settings: Settings) -> dict[str, int]:
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
                enabled = await session.scalar(
                    select(PaymentRunSetting.weekly_preview_enabled).where(
                        PaymentRunSetting.tenant_id == tenant_id
                    )
                )
                if not enabled:
                    continue
                await store_preview(session, tenant_id, trigger="schedule", user_id=None)
                runs += 1
    finally:
        await engine.dispose()
    return {"runs": runs}


@shared_task(name="mhvp.payments.payment_run")
def payment_run_preview() -> dict[str, int]:
    return asyncio.run(weekly_previews(get_settings()))
