"""Logged deletion of mirrored copies in Paperless-ngx and Google Drive (A43, 6.9.5, M6-03).

Order of events for one document:

1. ``DELETE /documents/{id}`` (``mhvp.documents.routers.delete_document``) checks the released
   retention profile, the expired retention date and the absence of a hold (the existing lock,
   rule 0.1.7). Until that check passes nothing here is ever called.
2. In the same transaction that removes the index row and the S3 original, ``request`` writes
   one ``document.mirror_delete_requested`` event per mirror that holds an external reference
   and returns the jobs. The mirror rows themselves are removed with the document (cascade),
   so the event log is the deletion journal (append only, 6.8).
3. After the commit ``enqueue`` hands each job to the Celery task ``mhvp.documents.delete_mirror``
   (queue ``io``). The task deletes the copy through ``DocumentStore.delete`` and writes
   ``document.mirror_deleted`` (mirror, external id, time, result ``deleted`` or
   ``already_gone``). A failure writes ``document.mirror_delete_failed`` with the attempt and
   the error and retries with backoff; after the last attempt the failure stays in the log for
   the operator (no silent drop, D46).

The document id is kept on every event although the row is gone, so the journal of a deleted
document can be reassembled from ``domain_event`` alone (restore runbook, A44).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core import crypto
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import emit
from mhvp.documents.dms import DmsError, DocumentStore, GoogleDriveStore, PaperlessStore
from mhvp.documents.models import DmsConnection, DocumentMirror, MirrorStatus, StorageKind

log = logging.getLogger(__name__)

EVENT_REQUESTED = "document.mirror_delete_requested"
EVENT_DELETED = "document.mirror_deleted"
EVENT_FAILED = "document.mirror_delete_failed"
TASK_NAME = "mhvp.documents.delete_mirror"
# Same ladder as the mirror job: 1 min, 5 min, 30 min, 2 h, 6 h, 24 h.
BACKOFF_SECONDS = (60, 300, 1800, 7200, 21600, 86400)
TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class MirrorDeletionJob:
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    kind: str  # StorageKind value
    external_ref: str

    def as_args(self) -> tuple[str, str, str, str]:
        return (str(self.tenant_id), str(self.document_id), self.kind, self.external_ref)


class MirrorDeletionError(Exception):
    """The copy could not be removed now; the failure is already logged as an event."""


async def request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    mirrors: list[DocumentMirror],
    actor_user_id: uuid.UUID | None,
) -> list[MirrorDeletionJob]:
    """Log the requested mirror deletions inside the platform deletion transaction."""
    jobs: list[MirrorDeletionJob] = []
    for mirror in mirrors:
        if mirror.status is MirrorStatus.PENDING or not mirror.external_ref:
            continue  # nothing exists in the mirror yet
        job = MirrorDeletionJob(
            tenant_id=tenant_id,
            document_id=document_id,
            kind=mirror.kind.value,
            external_ref=mirror.external_ref,
        )
        await emit(
            session,
            tenant_id=tenant_id,
            type=EVENT_REQUESTED,
            entity_type="document",
            entity_id=document_id,
            actor_user_id=actor_user_id,
            payload={
                "mirror": job.kind,
                "external_ref": job.external_ref,
                "mirror_status": mirror.status.value,
                "requested_at": datetime.now(UTC).isoformat(),
            },
        )
        jobs.append(job)
    return jobs


def enqueue(jobs: list[MirrorDeletionJob]) -> int:
    """Hand the jobs to Celery; called after the deleting transaction committed."""
    for job in jobs:
        delete_mirror.apply_async(args=job.as_args(), queue="io")
    return len(jobs)


def _store(connection: DmsConnection, client: httpx.AsyncClient) -> DocumentStore:
    if connection.kind is StorageKind.PAPERLESS:
        if not connection.base_url or not connection.secret:
            raise DmsError("Paperless: base_url or token missing")
        return PaperlessStore(connection.base_url, connection.secret, client)
    secret = json.loads(connection.secret or "{}")
    options = connection.options or {}
    return GoogleDriveStore(
        root_folder_id=str(options.get("root_folder_id", "")),
        client_id=str(options.get("client_id", "")),
        client_secret=str(secret.get("client_secret", "")),
        refresh_token=str(secret.get("refresh_token", "")),
        client=client,
    )


@dataclass(frozen=True)
class MirrorDeletionOutcome:
    result: str  # deleted, already_gone, failed
    error: str | None = None


async def delete_in_mirror(
    session: AsyncSession, job: MirrorDeletionJob, client: httpx.AsyncClient, attempt: int
) -> MirrorDeletionOutcome:
    """Delete one copy and write the journal entry (``document.mirror_deleted`` or
    ``document.mirror_delete_failed``). Never raises inside the transaction, so the failure
    event is committed (D46 pattern); the caller raises ``MirrorDeletionError`` afterwards."""
    kind = StorageKind(job.kind)
    connection = await session.scalar(select(DmsConnection).where(DmsConnection.kind == kind))
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "mirror": job.kind,
        "external_ref": job.external_ref,
        "attempt": attempt,
    }
    try:
        if connection is None or not connection.enabled:
            raise DmsError("Anbindung ist nicht aktiv, die Kopie konnte nicht gelöscht werden.")
        store = _store(connection, client)
        ref = await store.resolve(job.external_ref)
        if ref is None:
            raise DmsError("Die Kopie ist im Spiegel noch nicht abgelegt (Verarbeitung offen).")
        deleted = await store.delete(ref)
    except (DmsError, httpx.HTTPError, ValueError, KeyError) as exc:
        message = str(exc) if isinstance(exc, DmsError) else type(exc).__name__
        await emit(
            session,
            tenant_id=job.tenant_id,
            type=EVENT_FAILED,
            entity_type="document",
            entity_id=job.document_id,
            actor_user_id=None,
            payload={**base, "failed_at": now.isoformat(), "error": message[:500]},
        )
        log.warning("document_mirror_delete_failed: %s (%s)", message, job.kind)
        return MirrorDeletionOutcome(result="failed", error=message)
    result = "deleted" if deleted else "already_gone"
    await emit(
        session,
        tenant_id=job.tenant_id,
        type=EVENT_DELETED,
        entity_type="document",
        entity_id=job.document_id,
        actor_user_id=None,
        payload={**base, "resolved_ref": ref, "deleted_at": now.isoformat(), "result": result},
    )
    return MirrorDeletionOutcome(result=result)


async def delete_mirror_once(
    settings: Settings,
    job: MirrorDeletionJob,
    client: httpx.AsyncClient | None = None,
    attempt: int = 1,
) -> str:
    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    http = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    try:
        async with tenant_transaction(factory, job.tenant_id) as session:
            outcome = await delete_in_mirror(session, job, http, attempt)
    finally:
        if client is None:
            await http.aclose()
        await engine.dispose()
    if outcome.error is not None:
        raise MirrorDeletionError(outcome.error)
    return outcome.result


@shared_task(name=TASK_NAME, bind=True, max_retries=len(BACKOFF_SECONDS))
def delete_mirror(
    self: Any, tenant_id: str, document_id: str, kind: str, external_ref: str
) -> dict[str, Any]:
    job = MirrorDeletionJob(
        tenant_id=uuid.UUID(tenant_id),
        document_id=uuid.UUID(document_id),
        kind=kind,
        external_ref=external_ref,
    )
    attempt = int(self.request.retries) + 1
    try:
        result = asyncio.run(delete_mirror_once(get_settings(), job, attempt=attempt))
    except MirrorDeletionError as exc:
        index = min(attempt - 1, len(BACKOFF_SECONDS) - 1)
        raise self.retry(exc=exc, countdown=BACKOFF_SECONDS[index]) from exc
    return {**asdict(job), "tenant_id": tenant_id, "document_id": document_id, "result": result}
