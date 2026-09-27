"""Beat job for the postal status poll (M23-01): every open job of a tenant with an enabled
external provider is asked for its state; the answer is recorded on the job, the dispatch and
the dunning case (``mhvp.communication.postal.poll_open_jobs``). Manual jobs never poll."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from celery import shared_task

from mhvp.communication import postal
from mhvp.communication.tasks import _active_tenant_ids, _engine, _ensure_crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction

log = logging.getLogger(__name__)


async def poll_once(settings: Settings, tenant_id: uuid.UUID) -> dict[str, int]:
    _ensure_crypto(settings)
    engine = _engine(settings)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            return await postal.poll_open_jobs(session, tenant_id)
    finally:
        await engine.dispose()


async def poll_all_once(settings: Settings) -> dict[str, int]:
    _ensure_crypto(settings)
    engine = _engine(settings)
    totals = {"polled": 0, "changed": 0, "skipped": 0, "tenants": 0}
    try:
        tenant_ids = await _active_tenant_ids(create_session_factory(engine))
    finally:
        await engine.dispose()
    for tenant_id in tenant_ids:
        try:
            counts = await poll_once(settings, tenant_id)
        except Exception:
            log.exception("postal status poll failed", extra={"tenant_id": str(tenant_id)})
            continue
        totals["tenants"] += 1
        for key in ("polled", "changed", "skipped"):
            totals[key] += counts[key]
    return totals


@shared_task(name="mhvp.communication.postal_status_poll", bind=True)
def postal_status_poll(self: Any, tenant_id: str) -> dict[str, int]:
    try:
        return asyncio.run(poll_once(get_settings(), uuid.UUID(tenant_id)))
    except Exception as exc:
        log.exception("postal status poll task failed")
        raise self.retry(exc=exc, countdown=60, max_retries=3) from exc


@shared_task(name="mhvp.communication.postal_status_poll_all")
def postal_status_poll_all() -> dict[str, int]:
    return asyncio.run(poll_all_once(get_settings()))
