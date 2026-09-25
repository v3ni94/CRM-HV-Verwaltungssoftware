"""Celery-Task ``mhvp.sla.check_clocks``: Ampel neu berechnen und fällige Eskalationen auslösen
(alle 5 Minuten, Queue ``default``, M21 Übernahme aus dem Immoware Hub)."""

import asyncio
import logging
import uuid

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.sla.escalation import check_and_escalate
from mhvp.sla.models import ClockState, SlaClock

log = logging.getLogger(__name__)


async def check_clocks_once(settings: Settings) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    totals = {"tenants": 0, "clocks": 0, "escalated": 0}
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
                    clocks = list(
                        await session.scalars(
                            select(SlaClock).where(
                                SlaClock.state.in_([ClockState.RUNNING, ClockState.BREACHED])
                            )
                        )
                    )
                    for clock in clocks:
                        totals["clocks"] += 1
                        before = list(clock.escalated_steps)
                        await check_and_escalate(session, clock, settings)
                        if clock.escalated_steps != before:
                            totals["escalated"] += 1
            except Exception:
                log.warning("sla check_clocks failed", extra={"tenant_id": str(tenant_id)})
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.sla.check_clocks")
def check_clocks() -> dict[str, int]:
    return asyncio.run(check_clocks_once(get_settings()))
