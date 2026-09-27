"""Logged handling of mirrored copies after a lawful platform deletion (A43, 6.9.5, M6-03).

Operator decision 26.09.2026 (M6-03):

* Google Drive: the mirror copy is deleted. The permanent delete is preferred; when Drive
  refuses it (for example a shared drive without the delete right) the copy is moved to the
  trash instead and the journal says which of the two happened (``result`` ``deleted`` or
  ``trashed``).
* Paperless-ngx: the document is kept and receives the tag ``gelöscht`` (created per tenant
  token when missing), so staff see in Paperless that the document is deleted in the CRM.
* Both steps are journaled with success or failure. The platform deletion counts as "offen"
  until every mirror step succeeded; the existing Celery task retries with the standard
  ladder and open steps can be re-queued (``POST /documents/deletions/{id}/retry``).

Order of events for one document:

1. ``DELETE /documents/{id}`` (``mhvp.documents.routers.delete_document``) checks the released
   retention profile, the expired retention date and the absence of a hold (the existing lock,
   rule 0.1.7). Until that check passes nothing here is ever called. Mirrored documents are no
   longer blocked by their mirrors (the block of M6-03 is lifted by the decision above).
2. In the same transaction that removes the index row and the S3 original, ``request`` writes
   one ``document_mirror_deletion`` step row (status ``open``) and one
   ``document.mirror_delete_requested`` event per mirror that holds an external reference and
   returns the jobs. The mirror rows themselves are removed with the document (cascade); the
   step rows and the event log are the deletion journal (append only, 6.8).
3. After the commit ``enqueue`` hands each job to the Celery task ``mhvp.documents.delete_mirror``
   (queue ``io``). The task performs the step through the DMS client, marks the row ``done``
   and writes ``document.mirror_deleted`` (Drive: result ``deleted``, ``trashed`` or
   ``already_gone``) or ``document.mirror_marked_deleted`` (Paperless: ``tagged`` or
   ``already_gone``). A failure keeps the row ``open``, counts the attempt, writes
   ``document.mirror_delete_failed`` with the error and retries with backoff; after the last
   attempt the open step stays visible for the operator (no silent drop, D46).

The document id is kept on every row and event although the document row is gone, so the
journal of a deleted document can be reassembled from ``domain_event`` alone (restore
runbook, A44).
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
from mhvp.documents.dms import DmsError, GoogleDriveStore, PaperlessStore
from mhvp.documents.models import (
    DmsConnection,
    DocumentMirror,
    DocumentMirrorDeletion,
    MirrorDeletionAction,
    MirrorDeletionStatus,
    MirrorStatus,
    StorageKind,
)

log = logging.getLogger(__name__)

EVENT_REQUESTED = "document.mirror_delete_requested"
EVENT_DELETED = "document.mirror_deleted"
EVENT_MARKED = "document.mirror_marked_deleted"
EVENT_FAILED = "document.mirror_delete_failed"
TASK_NAME = "mhvp.documents.delete_mirror"
PAPERLESS_DELETED_TAG = "gelöscht"
# Same ladder as the mirror job: 1 min, 5 min, 30 min, 2 h, 6 h, 24 h.
BACKOFF_SECONDS = (60, 300, 1800, 7200, 21600, 86400)
TIMEOUT_SECONDS = 60.0

RESULT_DELETED = "deleted"
RESULT_TRASHED = "trashed"
RESULT_TAGGED = "tagged"
RESULT_ALREADY_GONE = "already_gone"
RESULT_FAILED = "failed"


def action_for(kind: StorageKind) -> MirrorDeletionAction:
    if kind is StorageKind.PAPERLESS:
        return MirrorDeletionAction.TAG
    return MirrorDeletionAction.DELETE


@dataclass(frozen=True)
class MirrorDeletionJob:
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    kind: str  # StorageKind value
    external_ref: str

    def as_args(self) -> tuple[str, str, str, str]:
        return (str(self.tenant_id), str(self.document_id), self.kind, self.external_ref)

    @classmethod
    def from_step(cls, step: DocumentMirrorDeletion) -> MirrorDeletionJob:
        return cls(
            tenant_id=step.tenant_id,
            document_id=step.document_id,
            kind=step.kind.value,
            external_ref=step.external_ref,
        )


class MirrorDeletionError(Exception):
    """The step could not be completed now; the failure is already logged as an event."""


async def request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    mirrors: list[DocumentMirror],
    actor_user_id: uuid.UUID | None,
) -> list[MirrorDeletionJob]:
    """Log the requested mirror steps inside the platform deletion transaction."""
    jobs: list[MirrorDeletionJob] = []
    now = datetime.now(UTC)
    for mirror in mirrors:
        if mirror.status is MirrorStatus.PENDING or not mirror.external_ref:
            continue  # nothing exists in the mirror yet
        action = action_for(mirror.kind)
        session.add(
            DocumentMirrorDeletion(
                tenant_id=tenant_id,
                document_id=document_id,
                kind=mirror.kind,
                action=action,
                external_ref=mirror.external_ref,
                status=MirrorDeletionStatus.OPEN,
                attempts=0,
                requested_at=now,
                requested_by=actor_user_id,
            )
        )
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
                "action": action.value,
                "external_ref": job.external_ref,
                "mirror_status": mirror.status.value,
                "requested_at": now.isoformat(),
            },
        )
        jobs.append(job)
    await session.flush()
    return jobs


def enqueue(jobs: list[MirrorDeletionJob]) -> int:
    """Hand the jobs to Celery; called after the deleting transaction committed."""
    for job in jobs:
        delete_mirror.apply_async(args=job.as_args(), queue="io")
    return len(jobs)


def _paperless(connection: DmsConnection, client: httpx.AsyncClient) -> PaperlessStore:
    if not connection.base_url or not connection.secret:
        raise DmsError("Paperless: base_url or token missing")
    return PaperlessStore(connection.base_url, connection.secret, client)


def _drive(connection: DmsConnection, client: httpx.AsyncClient) -> GoogleDriveStore:
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
    result: str  # deleted, trashed, tagged, already_gone, failed
    error: str | None = None
    note: str | None = None  # why the fallback (trash) was used


async def _perform(
    connection: DmsConnection, job: MirrorDeletionJob, client: httpx.AsyncClient
) -> MirrorDeletionOutcome:
    kind = StorageKind(job.kind)
    if kind is StorageKind.PAPERLESS:
        store = _paperless(connection, client)
        ref = await store.resolve(job.external_ref)
        if ref is None:
            raise DmsError("Die Kopie ist im Spiegel noch nicht abgelegt (Verarbeitung offen).")
        tagged = await store.add_tag(ref, PAPERLESS_DELETED_TAG)
        return MirrorDeletionOutcome(RESULT_TAGGED if tagged else RESULT_ALREADY_GONE)
    if kind is StorageKind.GOOGLE_DRIVE:
        drive = _drive(connection, client)
        try:
            deleted = await drive.delete(job.external_ref)
        except DmsError as exc:
            # Permanent delete refused: fall back to the trash and say so in the journal.
            trashed = await drive.trash(job.external_ref)
            return MirrorDeletionOutcome(
                RESULT_TRASHED if trashed else RESULT_ALREADY_GONE,
                note=f"Endgültiges Löschen abgelehnt ({exc}), in den Papierkorb verschoben.",
            )
        return MirrorDeletionOutcome(RESULT_DELETED if deleted else RESULT_ALREADY_GONE)
    raise DmsError(f"Kein Spiegelschritt für {job.kind} definiert.")


async def _step(session: AsyncSession, job: MirrorDeletionJob) -> DocumentMirrorDeletion | None:
    step: DocumentMirrorDeletion | None = await session.scalar(
        select(DocumentMirrorDeletion).where(
            DocumentMirrorDeletion.document_id == job.document_id,
            DocumentMirrorDeletion.kind == StorageKind(job.kind),
        )
    )
    return step


async def delete_in_mirror(
    session: AsyncSession, job: MirrorDeletionJob, client: httpx.AsyncClient, attempt: int
) -> MirrorDeletionOutcome:
    """Perform one mirror step, update its row and write the journal entry
    (``document.mirror_deleted``, ``document.mirror_marked_deleted`` or
    ``document.mirror_delete_failed``). Never raises inside the transaction, so the failure
    event is committed (D46 pattern); the caller raises ``MirrorDeletionError`` afterwards."""
    kind = StorageKind(job.kind)
    step = await _step(session, job)
    if step is not None and step.status is MirrorDeletionStatus.DONE:
        return MirrorDeletionOutcome(step.result or RESULT_ALREADY_GONE)  # idempotent retry
    connection = await session.scalar(select(DmsConnection).where(DmsConnection.kind == kind))
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "mirror": job.kind,
        "action": action_for(kind).value,
        "external_ref": job.external_ref,
        "attempt": attempt,
    }
    try:
        if connection is None or not connection.enabled:
            raise DmsError("Anbindung ist nicht aktiv, der Spiegelschritt wurde nicht ausgeführt.")
        outcome = await _perform(connection, job, client)
    except (DmsError, httpx.HTTPError, ValueError, KeyError) as exc:
        message = str(exc) if isinstance(exc, DmsError) else type(exc).__name__
        if step is not None:
            step.attempts = attempt
            step.last_error = message[:500]
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
        return MirrorDeletionOutcome(result=RESULT_FAILED, error=message)
    if step is not None:
        step.attempts = attempt
        step.last_error = None
        step.status = MirrorDeletionStatus.DONE
        step.result = outcome.result
        step.completed_at = now
    payload = {**base, "completed_at": now.isoformat(), "result": outcome.result}
    if outcome.note:
        payload["note"] = outcome.note
    if kind is StorageKind.PAPERLESS:
        payload["tag"] = PAPERLESS_DELETED_TAG
    await emit(
        session,
        tenant_id=job.tenant_id,
        type=EVENT_MARKED if kind is StorageKind.PAPERLESS else EVENT_DELETED,
        entity_type="document",
        entity_id=job.document_id,
        actor_user_id=None,
        payload=payload,
    )
    return outcome


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
