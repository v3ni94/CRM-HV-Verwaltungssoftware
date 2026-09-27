"""Celery task ``mhvp.metering.run_sync_job``: executes one queued, manually requested sync job
(master prompt Messdienstleister section 10). No scheduled fetch exists: the per connection
flag ``scheduled_sync_enabled`` is stored but not evaluated by any beat entry.

Execution guarantees:

* Lock against double starts: the job row is taken with ``FOR UPDATE SKIP LOCKED``; a second
  worker that gets no row (or finds the job no longer queued) returns ``skipped`` without
  touching the provider. Idempotent re runs: identical values are never stored twice.
* The fetch and its results are committed in one transaction; only afterwards, in a second
  transaction, the provider receipts for stored documents are sent (section 11: receipt
  only after safe storage). A failed receipt stays pending on the document.
* No secrets or payloads in logs; the job row carries the detail.
"""

import asyncio
import logging
import uuid

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.metering.models import DataKind, MeteringSyncJob, SyncStatus
from mhvp.metering.services import acknowledge_documents, run_sync_job

log = logging.getLogger(__name__)


async def run_sync_job_once(settings: Settings, tenant_id: uuid.UUID, job_id: uuid.UUID) -> str:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        connection_id: uuid.UUID | None = None
        async with tenant_transaction(factory, tenant_id) as session:
            job = await session.scalar(
                select(MeteringSyncJob)
                .where(MeteringSyncJob.id == job_id)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                exists = await session.get(MeteringSyncJob, job_id)
                return "missing" if exists is None else "skipped"
            if job.status != SyncStatus.QUEUED:
                return "skipped"
            blobs = None
            if job.data_kind == DataKind.DOCUMENTS:
                from mhvp.documents.blobs import BlobStore

                blobs = BlobStore(settings)
            job = await run_sync_job(
                session, job, blobs=blobs, max_document_bytes=settings.document_max_bytes
            )
            status = str(job.status)
            if job.data_kind == DataKind.DOCUMENTS and job.status in {
                SyncStatus.SUCCEEDED,
                SyncStatus.PARTIAL,
            }:
                connection_id = job.connection_id
        if connection_id is not None:
            # Separate transaction: the documents are committed before any receipt leaves.
            async with tenant_transaction(factory, tenant_id) as session:
                await acknowledge_documents(session, connection_id)
        return status
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
