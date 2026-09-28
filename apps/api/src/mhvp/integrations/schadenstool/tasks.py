"""Celery jobs of the claims adjuster link (rule INT-SDT-01).

* ``mhvp.integrations.schadenstool.process`` (beat every minute, and kicked after a user
  action or a webhook): outbound queue and received webhook events, per enabled tenant.
* ``mhvp.integrations.schadenstool.pull`` (beat every 15 minutes): reconciliation with
  ``updatedSince`` and cursor, per enabled tenant.

A tenant whose connection is disabled is skipped entirely (no call to the adjuster); the
service functions check the flag again inside the tenant transaction.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.integrations.schadenstool import services as svc
from mhvp.integrations.schadenstool.models import SchadenstoolTenantConfig
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)

PROCESS_TASK = "mhvp.integrations.schadenstool.process"
PULL_TASK = "mhvp.integrations.schadenstool.pull"


def _send(name: str, settings: Settings, tenant_id: uuid.UUID) -> None:
    try:
        from mhvp.worker import get_celery

        get_celery().send_task(name, args=[str(tenant_id)], queue="io")
    except Exception:
        # The beat job picks the work up within a minute; the user action is already stored.
        log.warning("schadenstool: could not enqueue", extra={"task": name})


def enqueue_process(settings: Settings, tenant_id: uuid.UUID) -> None:
    _send(PROCESS_TASK, settings, tenant_id)


def enqueue_pull(settings: Settings, tenant_id: uuid.UUID) -> None:
    _send(PULL_TASK, settings, tenant_id)


async def enabled_tenants(factory: async_sessionmaker[AsyncSession]) -> list[uuid.UUID]:
    async with platform_transaction(factory) as session:
        tenant_ids = list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )
    found: list[uuid.UUID] = []
    for tenant_id in tenant_ids:
        async with tenant_transaction(factory, tenant_id) as session:
            enabled = await session.scalar(
                select(SchadenstoolTenantConfig.enabled).where(
                    SchadenstoolTenantConfig.tenant_id == tenant_id
                )
            )
        if enabled:
            found.append(tenant_id)
    return found


async def process_tenant(
    factory: async_sessionmaker[AsyncSession], settings: Settings, tenant_id: uuid.UUID
) -> dict[str, int]:
    from mhvp.documents.blobs import BlobStore

    blobs = BlobStore(settings)
    async with tenant_transaction(factory, tenant_id) as session:
        sent = await svc.process_outbox(session, tenant_id, blobs=blobs)
    async with tenant_transaction(factory, tenant_id) as session:
        events = await svc.process_events(session, tenant_id, blobs=blobs, settings=settings)
    return {**sent, **{f"events_{k}": v for k, v in events.items()}}


async def pull_tenant(
    factory: async_sessionmaker[AsyncSession], settings: Settings, tenant_id: uuid.UUID
) -> dict[str, int]:
    from mhvp.documents.blobs import BlobStore

    async with tenant_transaction(factory, tenant_id) as session:
        return await svc.pull(session, tenant_id, blobs=BlobStore(settings), settings=settings)


async def _run(
    settings: Settings,
    tenant_id: str | None,
    work: Callable[[async_sessionmaker[AsyncSession], Settings, uuid.UUID], Awaitable[Any]],
) -> int:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        tenants = [uuid.UUID(tenant_id)] if tenant_id else await enabled_tenants(factory)
        for tid in tenants:
            try:
                await work(factory, settings, tid)
            except Exception:
                log.warning("schadenstool job failed", extra={"tenant_id": str(tid)})
        return len(tenants)
    finally:
        await engine.dispose()


@shared_task(name=PROCESS_TASK)
def process(tenant_id: str | None = None) -> int:
    return asyncio.run(_run(get_settings(), tenant_id, process_tenant))


@shared_task(name=PULL_TASK)
def pull(tenant_id: str | None = None) -> int:
    return asyncio.run(_run(get_settings(), tenant_id, pull_tenant))
