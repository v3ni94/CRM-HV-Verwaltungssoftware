"""Celery task ``mhvp.metering.run_sync_job``: executes one queued, manually requested sync job
(master prompt Messdienstleister section 10). No scheduled fetch exists in stage 1: the per
connection flag ``scheduled_sync_enabled`` is stored but not evaluated by any beat entry."""

import asyncio
import logging
import uuid

from celery import shared_task
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.metering.models import MeteringSyncJob
from mhvp.metering.services import run_sync_job

log = logging.getLogger(__name__)


async def run_sync_job_once(settings: Settings, tenant_id: uuid.UUID, job_id: uuid.UUID) -> str:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            job = await session.get(MeteringSyncJob, job_id)
            if job is None:
                return "missing"
            job = await run_sync_job(session, job)
            return str(job.status)
    finally:
        await engine.dispose()


@shared_task(name="mhvp.metering.run_sync_job")
def run_sync_job_task(tenant_id: str, job_id: str) -> str:
    try:
        return asyncio.run(
            run_sync_job_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(job_id))
        )
    except Exception:
        # No secrets or payloads in logs (section 9); the job row carries the detail.
        log.warning("metering sync job failed", extra={"job_id": job_id})
        raise
