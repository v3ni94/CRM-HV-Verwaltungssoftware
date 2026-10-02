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
from mhvp.automation.job_schedule import job_allowed, lock_job
from mhvp.banking import payment_run
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today

# Trigger of a stored failed scheduled run (GAC-06); never a preview.
FAILED_TRIGGER = "failed"


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
    failed = 0
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    enabled = await session.scalar(
                        select(PaymentRunSetting.weekly_preview_enabled).where(
                            PaymentRunSetting.tenant_id == tenant_id
                        )
                    )
                    if not enabled:
                        continue
                    # GA12-01: per tenant job setting (switch and start time).
                    if not await job_allowed(session, tenant_id, "payments-payment-run-preview"):
                        continue
                    # GA12-06: one scheduled preview per tenant and day, also against a
                    # parallel run.
                    await lock_job(session, tenant_id, "payments-payment-run-preview")
                    if await session.scalar(
                        select(PaymentRunPreview.id).where(
                            PaymentRunPreview.trigger == "schedule",
                            PaymentRunPreview.as_of == local_today(),
                        )
                    ):
                        continue
                    await store_preview(session, tenant_id, trigger="schedule", user_id=None)
                    runs += 1
            except Exception as exc:
                # GAC-06: the failed preview rolled back; keep a failed row as evidence (alert
                # metric payment_run_failed_24h) and continue with the next tenant.
                failed += 1
                async with tenant_transaction(factory, tenant_id) as session:
                    session.add(
                        PaymentRunPreview(
                            tenant_id=tenant_id,
                            as_of=local_today(),
                            trigger=FAILED_TRIGGER,
                            summary={"error": f"{type(exc).__name__}: {exc}"[:2000]},
                        )
                    )
    finally:
        await engine.dispose()
    return {"runs": runs, "failed": failed}


@shared_task(name="mhvp.payments.payment_run")
def payment_run_preview() -> dict[str, int]:
    return asyncio.run(weekly_previews(get_settings()))
