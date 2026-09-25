"""Celery-Tasks fuer die drei DAV-Abholungen (M32). Beat feuert alle 15 Minuten fest; jede
Aufgabe prueft selbst, ob ``poll_minutes`` seit dem letzten Lauf vergangen sind, und haelt
ausserdem eine Sperre je Tenant und Art, damit kein Doppellauf entsteht (Redis, Fallback: DB)."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import redis as redis_lib
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.immoware.models import ImmowareConnection, ImmowareSyncRun, SyncKind
from mhvp.immoware.service import run_sync
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)
_LOCK_TTL_SECONDS = 900


async def _due(session: AsyncSession, connection: ImmowareConnection, kind: SyncKind) -> bool:
    last = await session.scalar(
        select(ImmowareSyncRun.started_at)
        .where(ImmowareSyncRun.kind == kind)
        .order_by(ImmowareSyncRun.started_at.desc())
        .limit(1)
    )
    if last is None:
        return True
    return datetime.now(UTC) - last >= timedelta(minutes=connection.poll_minutes)


def _try_lock(redis_client: redis_lib.Redis | None, key: str) -> bool:
    if redis_client is None:
        return True
    return bool(redis_client.set(key, "1", nx=True, ex=_LOCK_TTL_SECONDS))


def _release_lock(redis_client: redis_lib.Redis | None, key: str) -> None:
    if redis_client is not None:
        redis_client.delete(key)


async def _sync_all(settings: Settings, kind: SyncKind) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    totals = {"tenants": 0, "ran": 0, "skipped": 0, "failed": 0}
    redis_client: redis_lib.Redis | None = None
    try:
        redis_client = redis_lib.Redis.from_url(settings.celery_broker_url.get_secret_value())
    except Exception:
        redis_client = None
    try:
        factory = create_session_factory(engine)
        async with platform_transaction(factory) as session:
            tenant_ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenant_ids:
            totals["tenants"] += 1
            lock_key = f"immoware:sync:{kind.value}:{tenant_id}"
            if not _try_lock(redis_client, lock_key):
                totals["skipped"] += 1
                continue
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    connection = await session.scalar(select(ImmowareConnection))
                    if connection is None or not connection.enabled:
                        totals["skipped"] += 1
                        continue
                    if not await _due(session, connection, kind):
                        totals["skipped"] += 1
                        continue
                    run = await run_sync(session, connection, kind)
                    if run.status.value == "failed":
                        totals["failed"] += 1
                    else:
                        totals["ran"] += 1
            except Exception:
                log.exception(
                    "immoware sync failed",
                    extra={"tenant_id": str(tenant_id), "kind": kind.value},
                )
                totals["failed"] += 1
            finally:
                _release_lock(redis_client, lock_key)
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.immoware.sync_webdav", queue="default")
def immoware_sync_webdav() -> dict[str, int]:
    return asyncio.run(_sync_all(get_settings(), SyncKind.WEBDAV))


@shared_task(name="mhvp.immoware.sync_carddav", queue="default")
def immoware_sync_carddav() -> dict[str, int]:
    return asyncio.run(_sync_all(get_settings(), SyncKind.CARDDAV))


@shared_task(name="mhvp.immoware.sync_caldav", queue="default")
def immoware_sync_caldav() -> dict[str, int]:
    return asyncio.run(_sync_all(get_settings(), SyncKind.CALDAV))
