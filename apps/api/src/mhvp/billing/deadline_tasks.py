"""Daily warning before the statement deadline (M17-04): notification only, no dispatch,
no posting. Idempotent through the unread check of ``notify``."""

import asyncio
import uuid
from datetime import date
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.automation.job_schedule import job_allowed, lock_job
from mhvp.billing import calc, deadline
from mhvp.billing.models import Statement, StatementResult, StatementSnapshot
from mhvp.billing.status import StatementStatus
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.services import local_today, notify

JOB_KEY = "billing-deadline-watch"
OPEN_STATUSES = (
    StatementStatus.CALCULATED.value,
    StatementStatus.INTERNALLY_APPROVED.value,
    StatementStatus.BOARD_REVIEWED.value,
    StatementStatus.RESOLVED.value,
)


async def watch_tenant(session: Any, tenant_id: uuid.UUID, today: date) -> dict[str, int]:
    counts = {"checked": 0, "notified": 0}
    cfg = await deadline.setting(session, tenant_id)
    if not cfg.watch_enabled:
        return counts
    horizon = max(cfg.warn_days_first, cfg.warn_days_second)
    statements = (
        await session.scalars(select(Statement).where(Statement.status.in_(OPEN_STATUSES)))
    ).all()
    for st in statements:
        end = calc.deadline(st.period_to)
        left = (end - today).days
        if left > horizon or st.created_by is None:
            continue
        snap = await session.scalar(
            select(StatementSnapshot)
            .where(StatementSnapshot.statement_id == st.id)
            .order_by(StatementSnapshot.created_at.desc())
        )
        if snap is None:
            continue
        delivered = {
            str(r.contract_id)
            for r in await session.scalars(
                select(StatementResult).where(
                    StatementResult.statement_id == st.id, StatementResult.delivered_at.isnot(None)
                )
            )
        }
        open_units = [
            r["unit_number"] for r in snap.results["results"] if r["contract_id"] not in delivered
        ]
        counts["checked"] += 1
        if not open_units:
            continue
        stage = cfg.warn_days_second if left <= cfg.warn_days_second else cfg.warn_days_first
        title = (
            f"Abrechnungsfrist abgelaufen (Orientierung {end.strftime('%d.%m.%Y')})"
            if left < 0
            else f"Abrechnungsfrist endet voraussichtlich in {left} Tagen (Stufe {stage})"
        )
        created = await notify(
            session,
            tenant_id=tenant_id,
            user_id=st.created_by,
            kind="statement_deadline",
            title=title,
            body=f"Ohne erfassten Zugang: {', '.join(open_units)}. {deadline.NOTICE_TEXT}",
            target_type="statement",
            target_id=st.id,
        )
        counts["notified"] += int(created is not None)
    return counts


async def run_once(settings: Settings, today: date | None = None) -> dict[str, int]:
    today = today or local_today()
    totals = {"tenants": 0, "checked": 0, "notified": 0}
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            async with tenant_transaction(factory, tenant_id) as session:
                if not await job_allowed(session, tenant_id, JOB_KEY):
                    continue
                await lock_job(session, tenant_id, JOB_KEY)
                totals["tenants"] += 1
                for key, value in (await watch_tenant(session, tenant_id, today)).items():
                    totals[key] += value
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.billing.deadline_watch")
def deadline_watch_job() -> dict[str, int]:
    return asyncio.run(run_once(get_settings()))
