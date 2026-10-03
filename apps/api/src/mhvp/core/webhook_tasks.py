"""Celery job: enqueue and deliver webhooks for every tenant (runs every minute).

GAM-501: no HTTP call runs inside an open database transaction; every delivery is claimed,
sent and closed in its own short transactions (``mhvp.core.webhooks``), and the run stops
claiming once its time budget (below the soft limit of the class "short") is used.
GAM-502: an error of one tenant is logged and counted (``failed``) and never stops the
following tenants. The budget is shared fairly: each tenant gets at most its share of the
remaining time, so a hanging target of tenant A cannot starve tenant B.
"""

import asyncio
import logging
import time
import uuid

import httpx
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.webhooks import (
    DELIVERY_DEADLINE_SECONDS,
    DELIVERY_TIMEOUT_SECONDS,
    apply_outcome,
    claim_delivery,
    enqueue_deliveries,
    send_claimed,
)
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)

# Upper bound of claimed deliveries per tenant and run.
PER_TENANT_LIMIT = 100
# Seconds kept free below the soft limit for the last call and the outcome write.
BUDGET_RESERVE_SECONDS = DELIVERY_DEADLINE_SECONDS + 25.0


def time_budget(settings: Settings) -> float:
    """Run budget in seconds: soft limit of the class "short" minus the reserve (200 s at
    the defaults of 240 s), never below one delivery deadline."""
    return max(
        DELIVERY_DEADLINE_SECONDS, float(settings.celery_limit_short_soft) - BUDGET_RESERVE_SECONDS
    )


async def _deliver_tenant(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    *,
    http: httpx.AsyncClient,
    allow_private: bool,
    deadline: float,
) -> int:
    attempted = 0
    while attempted < PER_TENANT_LIMIT and time.monotonic() < deadline:
        async with tenant_transaction(factory, tenant_id) as session:
            found, claim = await claim_delivery(session, tenant_id)
        if not found:
            break
        if claim is None:
            continue  # closed without a call (inactive subscription, schedule used up)
        attempted += 1
        outcome = await send_claimed(claim, client=http, allow_private=allow_private)
        async with tenant_transaction(factory, tenant_id) as session:
            await apply_outcome(session, claim, outcome)
    return attempted


async def dispatch_once(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    *,
    budget_seconds: float | None = None,
) -> dict[str, int]:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS)
    totals = {"enqueued": 0, "attempted": 0, "failed": 0, "tenants_skipped": 0}
    end = time.monotonic() + (
        budget_seconds if budget_seconds is not None else time_budget(settings)
    )
    try:
        async with platform_transaction(factory) as session:
            tenant_ids = list(
                await session.scalars(
                    select(Tenant.id)
                    .where(Tenant.status == TenantStatus.ACTIVE)
                    .order_by(Tenant.id)
                )
            )
        for index, tenant_id in enumerate(tenant_ids):
            remaining = end - time.monotonic()
            if remaining <= 0:
                totals["tenants_skipped"] += len(tenant_ids) - index
                break
            share = remaining / (len(tenant_ids) - index)
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    totals["enqueued"] += await enqueue_deliveries(session, tenant_id)
                totals["attempted"] += await _deliver_tenant(
                    factory,
                    tenant_id,
                    http=http,
                    allow_private=settings.webhook_allow_private_targets,
                    deadline=time.monotonic() + share,
                )
            except Exception:
                totals["failed"] += 1
                log.exception(
                    "webhook dispatch failed for tenant", extra={"tenant_id": str(tenant_id)}
                )
    finally:
        if own_client:
            await http.aclose()
        await engine.dispose()
    if totals["tenants_skipped"]:
        log.warning("webhook dispatch: time budget used up", extra=totals)
    return totals


@shared_task(name="mhvp.core.webhooks.dispatch")
def dispatch() -> dict[str, int]:
    return asyncio.run(dispatch_once(get_settings()))
