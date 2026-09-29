"""Celery jobs of the Lexware Office extension (rule INT-LEXO-01).

* ``mhvp.integrations.lexoffice.process`` (beat every 60 s, kicked after user actions):
  outbound queue per enabled config.
* ``mhvp.integrations.lexoffice.match_contacts``: one matching run per config.
* ``mhvp.integrations.lexoffice.purge`` (daily 03:20 Europe/Berlin): retention of queue rows.

The worker uses the master key and a NullPool engine as ``schadenstool/tasks.py`` does; every
config is processed inside its tenant transaction (RLS).
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
from mhvp.integrations.lexoffice_ext import matching, services
from mhvp.integrations.models import LexofficeSyncRun, LexofficeTenantConfig
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)

PROCESS_TASK = "mhvp.integrations.lexoffice.process"
MATCH_TASK = "mhvp.integrations.lexoffice.match_contacts"
PURGE_TASK = "mhvp.integrations.lexoffice.purge"
RETENTION_DAYS = 90


def _send(name: str, args: list[Any], queue: str = "io") -> None:
    try:
        from mhvp.worker import get_celery

        get_celery().send_task(name, args=args, queue=queue)
    except Exception:
        # The beat job picks the work up within a minute; the user action is already stored.
        log.warning("lexoffice: could not enqueue", extra={"task": name})


def enqueue_process(tenant_id: uuid.UUID, config_id: uuid.UUID | None = None) -> None:
    _send(PROCESS_TASK, [str(tenant_id), str(config_id) if config_id else None])


def enqueue_match(
    tenant_id: uuid.UUID, config_id: uuid.UUID, run_id: uuid.UUID, scope: str
) -> None:
    _send(MATCH_TASK, [str(tenant_id), str(config_id), str(run_id), scope])


async def enabled_configs(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID | None = None
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    if tenant_id is not None:
        tenant_ids = [tenant_id]
    else:
        async with platform_transaction(factory) as session:
            tenant_ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
    found: list[tuple[uuid.UUID, uuid.UUID]] = []
    for tid in tenant_ids:
        async with tenant_transaction(factory, tid) as session:
            ids = list(
                await session.scalars(
                    select(LexofficeTenantConfig.id).where(
                        LexofficeTenantConfig.tenant_id == tid,
                        LexofficeTenantConfig.enabled.is_(True),
                    )
                )
            )
        found.extend((tid, cid) for cid in ids)
    return found


def _redis(settings: Settings) -> Any | None:
    try:
        from redis.asyncio import Redis

        return Redis.from_url(settings.redis_url.get_secret_value())
    except Exception:  # pragma: no cover - limiter falls back to in process spacing
        return None


async def process_config(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    tenant_id: uuid.UUID,
    config_id: uuid.UUID,
    *,
    redis: Any | None = None,
) -> dict[str, int]:
    from mhvp.documents.blobs import BlobStore

    async with tenant_transaction(factory, tenant_id) as session:
        config = await session.get(LexofficeTenantConfig, config_id)
        if config is None:
            return {}
        return await services.process_outbox(
            session, tenant_id, config, settings, blobs=BlobStore(settings), redis=redis
        )


async def match_config(
    factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    tenant_id: uuid.UUID,
    config_id: uuid.UUID,
    run_id: uuid.UUID,
    scope: str,
    *,
    redis: Any | None = None,
) -> dict[str, int]:
    async with tenant_transaction(factory, tenant_id) as session:
        config = await session.get(LexofficeTenantConfig, config_id)
        run = await session.get(LexofficeSyncRun, run_id)
        if config is None or run is None:
            return {}
        client = services.client_for(config, settings, redis=redis)
        return await matching.run_match(session, tenant_id, config, client, run, scope=scope)


async def _with_engine(
    settings: Settings,
    work: Callable[[async_sessionmaker[AsyncSession]], Awaitable[Any]],
) -> Any:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        return await work(create_session_factory(engine))
    finally:
        await engine.dispose()


async def _process_all(settings: Settings, tenant_id: str | None, config_id: str | None) -> int:
    async def work(factory: async_sessionmaker[AsyncSession]) -> int:
        redis = _redis(settings)
        try:
            if tenant_id and config_id:
                targets = [(uuid.UUID(tenant_id), uuid.UUID(config_id))]
            else:
                targets = await enabled_configs(
                    factory, uuid.UUID(tenant_id) if tenant_id else None
                )
            for tid, cid in targets:
                try:
                    await process_config(factory, settings, tid, cid, redis=redis)
                except Exception:
                    log.warning(
                        "lexoffice job failed", extra={"tenant_id": str(tid), "config_id": str(cid)}
                    )
            return len(targets)
        finally:
            if redis is not None:
                await redis.aclose()

    result: int = await _with_engine(settings, work)
    return result


async def _match(
    settings: Settings, tenant_id: str, config_id: str, run_id: str, scope: str
) -> dict[str, int]:
    async def work(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
        redis = _redis(settings)
        try:
            return await match_config(
                factory,
                settings,
                uuid.UUID(tenant_id),
                uuid.UUID(config_id),
                uuid.UUID(run_id),
                scope,
                redis=redis,
            )
        finally:
            if redis is not None:
                await redis.aclose()

    result: dict[str, int] = await _with_engine(settings, work)
    return result


async def _purge_all(settings: Settings) -> int:
    async def work(factory: async_sessionmaker[AsyncSession]) -> int:
        async with platform_transaction(factory) as session:
            tenant_ids = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        removed = 0
        for tid in tenant_ids:
            async with tenant_transaction(factory, tid) as session:
                removed += await services.purge(session, tid, retention_days=RETENTION_DAYS)
        return removed

    result: int = await _with_engine(settings, work)
    return result


@shared_task(name=PROCESS_TASK)
def process(tenant_id: str | None = None, config_id: str | None = None) -> int:
    return asyncio.run(_process_all(get_settings(), tenant_id, config_id))


@shared_task(name=MATCH_TASK)
def match_contacts(
    tenant_id: str, config_id: str, run_id: str, scope: str = "customers_and_vendors"
) -> dict[str, int]:
    return asyncio.run(_match(get_settings(), tenant_id, config_id, run_id, scope))


@shared_task(name=PURGE_TASK)
def purge() -> int:
    return asyncio.run(_purge_all(get_settings()))
