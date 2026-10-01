"""Deletion checklist per target with follow up job (AC07, GA08-08, 7.11 S05, 6.9.5).

A lawful document deletion (released, expired retention profile, no hold; checked by
``services.deletion_blocker`` before anything here runs) must be consistent in every place the
document lives. The checklist is derived from the current rows and the append only events, so
it needs no own table:

========================  =============================================================
target                    done when
========================  =============================================================
``trash``                 AE33: the document left the trash (final deletion); open while
                          it waits in the trash, ``not_applicable`` when the tenant
                          deletes without a trash
``index``                 the ``document`` row is gone (full text ``search_vector`` and
                          the trigram indexes on title and filename live on that row)
``original``              the object store key of the original no longer exists
``mirror_paperless``      the journaled Paperless step is done (tag ``gelöscht``, M6-03)
``mirror_google_drive``   the journaled Drive step is done (deleted or trashed, M6-03)
``embeddings``            no ``ai_embedding`` row with this document as source is left
``ai_extracts``           the stored AI extraction of the intake (``ai_task_run.output``,
                          ``ai_proposal.proposed/final``, learning example) is replaced by
                          a placeholder; ids, decision and actor stay for traceability
``thumbnails``            not applicable: previews are rendered from the original on
                          request and never stored
``backup``                out of scope: backups are not edited; they expire with the
                          rolling backup period, and a restore replays the deletion
                          journal (runbook, ``replay_deletions``)
========================  =============================================================

``purge_derivatives`` runs inside the deleting transaction (API deletion, proposal run and
journal replay all go through ``retention.delete_now``; with the trash on (AE33) the final
deletion by ``trash.purge`` does the same). A document that waits in the trash has the overall
status ``in_trash`` (``held`` when a hold keeps it there); its other targets are ``pending``
until the final deletion, and the follow up leaves it alone. ``follow_up`` is the "Nachlauf": it
repeats every step that is still open (blob still present, derivatives created by a late job,
open mirror steps) and is run daily for recent deletions and on demand. A document that exists
again (restore without replay) is never deleted by the follow up: the replay with its hold and
hash checks is the only path for that, and a retention hold always wins.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import DomainEvent, emit
from mhvp.documents import mirror_deletion, trash
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    Document,
    DocumentMirrorDeletion,
    MirrorDeletionStatus,
    StorageKind,
)

log = logging.getLogger(__name__)

EVENT_DELETED = "document.deleted"
EVENT_FOLLOW_UP = "document.deletion_follow_up"
TASK_NAME = "mhvp.documents.deletion_follow_up"
FOLLOW_UP_DAYS = 30  # recent deletions checked by the daily job
INTAKE_ENTITY_TYPE = "document_intake"
PLACEHOLDER: dict[str, Any] = {"deleted_with_document": True}

TARGET_TRASH = "trash"
TARGET_INDEX = "index"
TARGET_ORIGINAL = "original"
TARGET_PAPERLESS = "mirror_paperless"
TARGET_DRIVE = "mirror_google_drive"
TARGET_EMBEDDINGS = "embeddings"
TARGET_AI_EXTRACTS = "ai_extracts"
TARGET_THUMBNAILS = "thumbnails"
TARGET_BACKUP = "backup"

DONE = "done"
OPEN = "open"
HELD = "held"
PENDING = "pending"
IN_TRASH = "in_trash"
NOT_APPLICABLE = "not_applicable"
OUT_OF_SCOPE = "out_of_scope"

_MIRROR_TARGET = {StorageKind.PAPERLESS: TARGET_PAPERLESS, StorageKind.GOOGLE_DRIVE: TARGET_DRIVE}


@dataclass
class ChecklistItem:
    target: str
    status: str
    detail: str | None = None


@dataclass
class Checklist:
    document_id: uuid.UUID
    deleted_at: datetime
    status: str  # done, open, held, in_trash
    items: list[ChecklistItem] = field(default_factory=list)
    jobs: list[mirror_deletion.MirrorDeletionJob] = field(default_factory=list)
    purge_at: datetime | None = None  # AE33: earliest final deletion while in the trash


def _ai_models() -> tuple[Any, Any, Any, Any, Any]:
    from mhvp.ai.models import (  # local: ai imports the documents models
        AiEmbedding,
        AiExample,
        AiProposal,
        AiTaskRun,
        EmbeddingSourceKind,
    )

    return AiEmbedding, AiExample, AiProposal, AiTaskRun, EmbeddingSourceKind


def _proposals_query(document_id: uuid.UUID) -> Any:
    _, _, proposal, _, _ = _ai_models()
    return select(proposal).where(
        proposal.context_id == document_id, proposal.entity_type == INTAKE_ENTITY_TYPE
    )


async def _embedding_count(session: AsyncSession, document_id: uuid.UUID) -> int:
    embedding, _, _, _, kind = _ai_models()
    rows = await session.scalars(
        select(embedding.id).where(
            embedding.source_kind == kind.DOCUMENT, embedding.source_id == document_id
        )
    )
    return len(rows.all())


async def _extract_count(session: AsyncSession, document_id: uuid.UUID) -> int:
    _, _, _, run, _ = _ai_models()
    proposals = (await session.scalars(_proposals_query(document_id))).all()
    open_count = sum(1 for p in proposals if p.proposed != PLACEHOLDER)
    runs = (
        await session.scalars(
            select(run).where(
                run.input_ref["document_id"].astext == str(document_id),
                run.output.is_not(None),
            )
        )
    ).all()
    return open_count + sum(1 for r in runs if r.output != PLACEHOLDER)


async def purge_derivatives(session: AsyncSession, document_id: uuid.UUID) -> dict[str, int]:
    """Embeddings removed, AI extraction content replaced; metadata stays (rule 0.1.7)."""
    embedding, example, _, run, kind = _ai_models()
    removed = await session.execute(
        delete(embedding).where(
            embedding.source_kind == kind.DOCUMENT, embedding.source_id == document_id
        )
    )
    proposals = (await session.scalars(_proposals_query(document_id))).all()
    proposal_ids = [p.id for p in proposals]
    scrubbed = 0
    for item in proposals:
        if item.proposed != PLACEHOLDER or item.final is not None:
            item.proposed, item.final = dict(PLACEHOLDER), None
            scrubbed += 1
    if proposal_ids:
        await session.execute(
            update(example)
            .where(example.proposal_id.in_(proposal_ids))
            .values(features=dict(PLACEHOLDER), result=dict(PLACEHOLDER))
        )
    runs = (
        await session.scalars(
            select(run).where(run.input_ref["document_id"].astext == str(document_id))
        )
    ).all()
    for item in runs:
        if item.output is not None and item.output != PLACEHOLDER:
            item.output = dict(PLACEHOLDER)
            scrubbed += 1
    await session.flush()
    return {"embeddings": int(getattr(removed, "rowcount", 0) or 0), "ai_extracts": scrubbed}


async def _deleted_event(session: AsyncSession, document_id: uuid.UUID) -> DomainEvent | None:
    event: DomainEvent | None = await session.scalar(
        select(DomainEvent)
        .where(DomainEvent.type == EVENT_DELETED, DomainEvent.entity_id == document_id)
        .order_by(DomainEvent.occurred_at.desc())
        .limit(1)
    )
    return event


async def build(
    session: AsyncSession,
    document_id: uuid.UUID,
    blobs: BlobStore | None,
    today: date | None = None,
) -> Checklist | None:
    """Checklist of a deleted document, or None when no deletion was ever recorded."""
    from mhvp.documents import services  # local: services imports retention

    with trash.trashed_visible(session):
        document = await session.get(Document, document_id)
    if document is not None and document.deleted_at is not None:
        return await _trash_checklist(session, document, today or datetime.now(UTC).date())
    event = await _deleted_event(session, document_id)
    if event is None:
        return None
    items: list[ChecklistItem] = []
    held = False
    if document is None:
        items.append(ChecklistItem(TARGET_INDEX, DONE))
    else:
        blocker = await services.deletion_blocker(
            session, document, today or datetime.now(UTC).date()
        )
        held = blocker is not None
        items.append(
            ChecklistItem(
                TARGET_INDEX,
                HELD if held else OPEN,
                blocker
                or "Dokument ist nach einer Wiederherstellung wieder vorhanden; "
                "Löschjournal erneut anwenden (replay_deletions).",
            )
        )
    ref = event.payload.get("storage_ref") or (document.storage_ref if document else None)
    if document is not None and document.storage is not StorageKind.MINIO:
        items.append(ChecklistItem(TARGET_ORIGINAL, NOT_APPLICABLE, "Original extern abgelegt."))
    elif ref and blobs is not None and blobs.exists(ref):
        items.append(ChecklistItem(TARGET_ORIGINAL, HELD if held else OPEN))
    else:
        detail = None if ref else "Speicherort im Löschereignis nicht vermerkt (Altbestand)."
        items.append(ChecklistItem(TARGET_ORIGINAL, DONE, detail))
    steps = {
        s.kind: s
        for s in (
            await session.scalars(
                select(DocumentMirrorDeletion).where(
                    DocumentMirrorDeletion.document_id == document_id
                )
            )
        ).all()
    }
    for kind, target in _MIRROR_TARGET.items():
        step = steps.get(kind)
        if step is None:
            items.append(ChecklistItem(target, NOT_APPLICABLE, "Keine Spiegelkopie vorhanden."))
        elif step.status is MirrorDeletionStatus.DONE:
            items.append(ChecklistItem(target, DONE, step.result))
        else:
            items.append(ChecklistItem(target, OPEN, step.last_error))
    embeddings = await _embedding_count(session, document_id)
    items.append(
        ChecklistItem(
            TARGET_EMBEDDINGS,
            DONE if embeddings == 0 else (HELD if held else OPEN),
            f"{embeddings} Abschnitte vorhanden" if embeddings else None,
        )
    )
    extracts = await _extract_count(session, document_id)
    items.append(
        ChecklistItem(
            TARGET_AI_EXTRACTS,
            DONE if extracts == 0 else (HELD if held else OPEN),
            f"{extracts} KI-Auszüge mit Inhalt" if extracts else None,
        )
    )
    items.append(
        ChecklistItem(
            TARGET_THUMBNAILS,
            NOT_APPLICABLE,
            "Vorschaubilder werden beim Abruf aus dem Original erzeugt und nicht gespeichert.",
        )
    )
    items.append(
        ChecklistItem(
            TARGET_BACKUP,
            OUT_OF_SCOPE,
            "Backups werden nicht bearbeitet; sie laufen mit der rollierenden Backupfrist ab. "
            "Nach einer Wiederherstellung wird das Löschjournal erneut angewendet.",
        )
    )
    items.insert(0, _trash_item(event))
    if held:
        status = HELD
    elif any(i.status == OPEN for i in items):
        status = OPEN
    else:
        status = DONE
    return Checklist(
        document_id=document_id, deleted_at=event.occurred_at, status=status, items=items
    )


def _trash_item(event: DomainEvent) -> ChecklistItem:
    """The trash step of a finished deletion (AE33)."""
    if event.payload.get("from_trash"):
        trashed_at = event.payload.get("trashed_at")
        detail = "Aus dem Papierkorb endgültig gelöscht."
        if trashed_at:
            detail += f" Im Papierkorb seit {str(trashed_at)[:10]}."
        if event.payload.get("early"):
            detail += " Vor Ablauf der Frist auf Anweisung."
        return ChecklistItem(TARGET_TRASH, DONE, detail)
    return ChecklistItem(TARGET_TRASH, NOT_APPLICABLE, "Löschung ohne Papierkorb.")


async def _trash_checklist(session: AsyncSession, document: Document, today: date) -> Checklist:
    """A document in the trash: nothing is deleted yet, every target waits for the final
    deletion; a hold set meanwhile keeps it there (status ``held``, the hold wins)."""
    from mhvp.documents import services  # local: services imports retention

    with trash.trashed_visible(session):
        blocker = await services.deletion_blocker(session, document, today)
    purge_at = document.purge_at
    when = purge_at.strftime("%d.%m.%Y") if purge_at else "unbekannt"
    waiting = "Wird mit der endgültigen Löschung ausgeführt."
    held = blocker is not None
    items = [
        ChecklistItem(
            TARGET_TRASH,
            HELD if held else OPEN,
            blocker or f"Im Papierkorb, endgültige Löschung frühestens am {when}.",
        )
    ]
    for target in (
        TARGET_INDEX,
        TARGET_ORIGINAL,
        TARGET_PAPERLESS,
        TARGET_DRIVE,
        TARGET_EMBEDDINGS,
        TARGET_AI_EXTRACTS,
    ):
        items.append(ChecklistItem(target, PENDING, waiting))
    items.append(
        ChecklistItem(
            TARGET_THUMBNAILS,
            NOT_APPLICABLE,
            "Vorschaubilder werden beim Abruf aus dem Original erzeugt und nicht gespeichert.",
        )
    )
    items.append(
        ChecklistItem(
            TARGET_BACKUP,
            OUT_OF_SCOPE,
            "Backups werden nicht bearbeitet; sie laufen mit der rollierenden Backupfrist ab. "
            "Nach einer Wiederherstellung wird das Löschjournal erneut angewendet.",
        )
    )
    return Checklist(
        document_id=document.id,
        deleted_at=document.deleted_at or datetime.now(UTC),
        status=HELD if held else IN_TRASH,
        items=items,
        purge_at=purge_at,
    )


async def follow_up(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    blobs: BlobStore,
    actor_user_id: uuid.UUID | None,
) -> Checklist | None:
    """Repeat the open steps (Nachlauf). Returns the checklist after the run with the mirror
    jobs to enqueue after the commit. A restored document is left alone (replay path)."""
    before = await build(session, document_id, blobs)
    if before is None:
        return None
    with trash.trashed_visible(session):
        present = await session.get(Document, document_id)
    if present is not None:
        return before  # in the trash, restored or held: only the purge or the replay deletes it
    actions: dict[str, Any] = {}
    event = await _deleted_event(session, document_id)
    ref = event.payload.get("storage_ref") if event else None
    if ref and blobs.exists(ref):
        blobs.delete(ref)
        actions["original"] = "deleted"
    purged = await purge_derivatives(session, document_id)
    actions.update({k: v for k, v in purged.items() if v})
    jobs = [
        mirror_deletion.MirrorDeletionJob.from_step(x)
        for x in (
            await session.scalars(
                select(DocumentMirrorDeletion).where(
                    DocumentMirrorDeletion.document_id == document_id,
                    DocumentMirrorDeletion.status == MirrorDeletionStatus.OPEN,
                )
            )
        ).all()
    ]
    if jobs:
        actions["mirror_steps_queued"] = len(jobs)
    after = await build(session, document_id, blobs)
    if after is None:  # pragma: no cover - the deletion event cannot vanish
        return before
    await emit(
        session,
        tenant_id=tenant_id,
        type=EVENT_FOLLOW_UP,
        entity_type="document",
        entity_id=document_id,
        actor_user_id=actor_user_id,
        payload={
            "actions": actions,
            "status": after.status,
            "open_targets": [i.target for i in after.items if i.status == OPEN],
        },
    )
    after.jobs = jobs
    return after


async def recent_deletions(session: AsyncSession, since: datetime) -> list[uuid.UUID]:
    rows = (
        await session.scalars(
            select(DomainEvent.entity_id)
            .where(DomainEvent.type == EVENT_DELETED, DomainEvent.occurred_at >= since)
            .distinct()
        )
    ).all()
    return [r for r in rows if r is not None]


async def follow_up_all_tenants_once(
    settings: Settings, *, blobs: BlobStore | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Daily run: every recent deletion with an open target gets a follow up."""
    from mhvp.platform.models import Tenant, TenantStatus

    since = (now or datetime.now(UTC)) - timedelta(days=FOLLOW_UP_DAYS)
    store = blobs or BlobStore(settings)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    report: dict[str, Any] = {"checked": 0, "followed_up": 0, "open": 0, "errors": []}
    jobs: list[mirror_deletion.MirrorDeletionJob] = []
    try:
        async with platform_transaction(factory) as session:
            tenants = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenants:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    for document_id in await recent_deletions(session, since):
                        report["checked"] += 1
                        current = await build(session, document_id, store)
                        if current is None or current.status != OPEN:
                            continue
                        after = await follow_up(
                            session,
                            tenant_id=tenant_id,
                            document_id=document_id,
                            blobs=store,
                            actor_user_id=None,
                        )
                        report["followed_up"] += 1
                        if after is not None:
                            jobs.extend(after.jobs)
                            if after.status == OPEN:
                                report["open"] += 1
            except Exception as exc:  # the other tenants must still run
                log.exception("deletion follow up failed for %s", tenant_id)
                report["errors"].append(f"{tenant_id}: {exc.__class__.__name__}")
    finally:
        await engine.dispose()
    report["mirror_jobs"] = mirror_deletion.enqueue(jobs)
    return report


@shared_task(name=TASK_NAME, acks_late=True)
def deletion_follow_up() -> dict[str, Any]:
    return asyncio.run(follow_up_all_tenants_once(get_settings()))
