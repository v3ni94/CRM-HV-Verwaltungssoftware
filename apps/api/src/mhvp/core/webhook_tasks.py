"""Celery job: enqueue and deliver webhooks for every tenant (runs every minute)."""

import asyncio

import httpx
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.webhooks import DELIVERY_TIMEOUT_SECONDS, deliver_due, enqueue_deliveries
from mhvp.platform.models import Tenant, TenantStatus


async def dispatch_once(
    settings: Settings, client: httpx.AsyncClient | None = None
) -> dict[str, int]:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS)
    totals = {"enqueued": 0, "attempted": 0}
    try:
        async with platform_transaction(factory) as session:
            tenant_ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenant_ids:
            async with tenant_transaction(factory, tenant_id) as session:
                totals["enqueued"] += await enqueue_deliveries(session, tenant_id)
            async with tenant_transaction(factory, tenant_id) as session:
                totals["attempted"] += await deliver_due(
                    session,
                    tenant_id,
                    client=http,
                    allow_private=settings.webhook_allow_private_targets,
                )
    finally:
        if own_client:
            await http.aclose()
        await engine.dispose()
    return totals


@shared_task(name="mhvp.core.webhooks.dispatch")
def dispatch() -> dict[str, int]:
    return asyncio.run(dispatch_once(get_settings()))
