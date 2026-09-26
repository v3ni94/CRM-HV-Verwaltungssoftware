"""Celery jobs of the workspace (M9, section 15.1): maintenance reminders, the daily digest
``tasks.digest`` (A40, 07:00) and the deadline list ``compliance.deadlines`` (A41, 20:00)."""

import asyncio
import uuid
from datetime import date
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.workspace.jobs import deadlines_tenant, digest_tenant
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


async def _active_tenants(factory: Any) -> list[uuid.UUID]:
    async with platform_transaction(factory) as session:
        return list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )


async def digest_once(settings: Settings, today: date | None = None) -> dict[str, int]:
    """One digest per tenant, user and day (idempotent via ``digest_run``)."""
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    totals = {"tenants": 0, "users": 0, "notified": 0, "empty": 0, "skipped": 0, "mails": 0}
    try:
        for tenant_id in await _active_tenants(factory):
            totals["tenants"] += 1
            async with tenant_transaction(factory, tenant_id) as session:
                counts = await digest_tenant(session, settings, tenant_id, today or local_today())
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
    finally:
        await engine.dispose()
    return totals


async def deadlines_once(settings: Settings, today: date | None = None) -> dict[str, int]:
    """Refresh the deadline list per tenant and notify once per row at its lead time."""
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    totals = {"tenants": 0, "created": 0, "updated": 0, "closed": 0, "notified": 0}
    try:
        for tenant_id in await _active_tenants(factory):
            totals["tenants"] += 1
            async with tenant_transaction(factory, tenant_id) as session:
                counts = await deadlines_tenant(session, tenant_id, today or local_today())
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.workspace.digest")
def digest() -> dict[str, int]:
    return asyncio.run(digest_once(get_settings()))


@shared_task(name="mhvp.workspace.compliance_deadlines")
def compliance_deadlines() -> dict[str, int]:
    return asyncio.run(deadlines_once(get_settings()))
