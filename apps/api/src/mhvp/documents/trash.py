"""Document trash with logged restore and final deletion (AE33, AC07-03, 6.9.5, 7.11 S05).

A lawful deletion (released retention profile, expired period, no hold; checked by
``services.deletion_blocker``) can first move a document to the trash instead of removing it at
once. The trash is a tenant switch (``document_trash_setting``), off by default; with the
switch off nothing changes. The period (``retention_days``, default 30) is a proposal: 6.9.5
names 30 days for the rolling backup, not for a trash, and whether personal data may stay that
long is open (OPEN_QUESTIONS AE33-01).

State lives on the document row (``deleted_at``, ``deleted_by``, ``purge_at``). The session
filter at the end of ``mhvp.documents.models`` hides a trashed document from every ORM query,
so lists, search, links, letters and downloads behave as if it were gone; the trash views and
the purge opt in with :func:`trashed_visible`. Nothing is removed from the object store or the
DMS mirrors while the document is in the trash, so a restore returns it unchanged.

Audit trail (append only domain events, rule 0.1.7):

``document.trashed``    moved to the trash (actor, purge date, proposal reference)
``document.restored``   restored from the trash (actor, reason)
``document.deleted``    final deletion, with ``from_trash`` and the trash data; this is the
                        event the deletion journal and the deletion checklist already use
``document.deletion_refused``  the final deletion was stopped by a hold or a rule

Retention holds win at every step. The final deletion (daily job, or earlier by an authorised
person) runs ``deletion_blocker`` again; a hold set meanwhile (ticket hold, procedure hold,
hold on a related document) keeps the document in the trash, the checklist shows ``held`` and
nothing is deleted. A hold on the document itself is set after a restore, because a trashed
document is not reachable through the normal routes.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import DomainEvent, emit
from mhvp.core.logging import get_logger
from mhvp.documents import mirror_deletion
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentTrashSetting

log = get_logger(__name__)

EVENT_TRASHED = "document.trashed"
EVENT_RESTORED = "document.restored"
EVENT_DELETED = "document.deleted"
EVENT_REFUSED = "document.deletion_refused"
TASK_NAME = "mhvp.documents.trash_purge"
PROPOSED_DAYS = 30  # proposal only (OPEN_QUESTIONS AE33-01)
STATUS_IN_TRASH = "in_trash"
STATUS_HELD = "held"
STATUS_DUE = "due"


@contextlib.contextmanager
def trashed_visible(session: AsyncSession) -> Iterator[None]:
    """Lets ORM queries of this session see trashed documents (trash views, purge, replay)."""
    info = session.sync_session.info
    previous = info.get("include_trashed", False)
    info["include_trashed"] = True
    try:
        yield
    finally:
        info["include_trashed"] = previous


# Settings ---------------------------------------------------------------------------------


async def current(session: AsyncSession) -> tuple[bool, int]:
    """(enabled, days) of the tenant; no row means off with the proposed period."""
    row = await session.scalar(select(DocumentTrashSetting))
    if row is None:
        return False, PROPOSED_DAYS
    return bool(row.enabled), int(row.retention_days)


async def setting_of(session: AsyncSession, tenant_id: uuid.UUID) -> DocumentTrashSetting:
    row = await session.scalar(select(DocumentTrashSetting))
    if row is None:
        row = DocumentTrashSetting(tenant_id=tenant_id, enabled=False, retention_days=PROPOSED_DAYS)
        session.add(row)
        await session.flush()
    return row


# Trash and restore ------------------------------------------------------------------------


async def move_to_trash(
    session: AsyncSession,
    document: Document,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    days: int,
    extra: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> datetime:
    """Moves a document to the trash. The caller has checked ``deletion_blocker`` in this
    transaction. Returns the earliest date of the automatic final deletion."""
    moment = now or datetime.now(UTC)
    purge_at = moment + timedelta(days=days)
    document.deleted_at, document.deleted_by, document.purge_at = moment, actor_user_id, purge_at
    payload: dict[str, Any] = {
        "sha256": document.sha256,
        "purge_at": purge_at.isoformat(),
        "retention_days": days,
        "storage_ref": document.storage_ref,
    }
    payload.update(extra or {})
    await emit(
        session,
        tenant_id=tenant_id,
        type=EVENT_TRASHED,
        entity_type="document",
        entity_id=document.id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    await session.flush()
    return purge_at


async def restore(
    session: AsyncSession,
    document: Document,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Takes a document out of the trash. Always allowed (keeping data is never unlawful), but
    always logged; the monthly proposal run may propose the document again."""
    if document.deleted_at is None:
        return
    payload: dict[str, Any] = {
        "reason": reason,
        "trashed_at": document.deleted_at.isoformat(),
        "trashed_by": str(document.deleted_by) if document.deleted_by else None,
        "purge_at": document.purge_at.isoformat() if document.purge_at else None,
    }
    payload.update(extra or {})
    document.deleted_at, document.deleted_by, document.purge_at = None, None, None
    await emit(
        session,
        tenant_id=tenant_id,
        type=EVENT_RESTORED,
        entity_type="document",
        entity_id=document.id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    await session.flush()


# Listing ----------------------------------------------------------------------------------


@dataclass
class TrashEntry:
    document: Document
    status: str  # in_trash, due, held
    blocker: str | None
    days_left: int


async def entries(
    session: AsyncSession,
    *,
    today: date,
    now: datetime | None = None,
    scope_filters: list[Any] | None = None,
    limit: int = 200,
) -> list[TrashEntry]:
    """Documents in the trash, oldest purge date first, with the current blocker (a hold set
    meanwhile) and the days left."""
    from mhvp.documents import services  # local: services imports retention

    moment = now or datetime.now(UTC)
    query = (
        select(Document)
        .where(Document.deleted_at.is_not(None))
        .order_by(Document.purge_at, Document.id)
        .limit(limit)
    )
    for condition in scope_filters or []:
        query = query.where(condition)
    out: list[TrashEntry] = []
    with trashed_visible(session):
        for document in (await session.scalars(query)).all():
            blocker = await services.deletion_blocker(session, document, today)
            purge_at = document.purge_at or moment
            days_left = max((purge_at - moment).days, 0)
            if blocker is not None:
                status = STATUS_HELD
            elif purge_at <= moment:
                status = STATUS_DUE
            else:
                status = STATUS_IN_TRASH
            out.append(TrashEntry(document, status, blocker, days_left))
    return out


# Final deletion ---------------------------------------------------------------------------


@dataclass
class PurgeResult:
    document_id: uuid.UUID
    deleted: bool
    reason: str | None = None
    jobs: list[mirror_deletion.MirrorDeletionJob] = field(default_factory=list)


async def _last_refusal_reason(session: AsyncSession, document_id: uuid.UUID) -> str | None:
    event: DomainEvent | None = await session.scalar(
        select(DomainEvent)
        .where(DomainEvent.type == EVENT_REFUSED, DomainEvent.entity_id == document_id)
        .order_by(DomainEvent.occurred_at.desc())
        .limit(1)
    )
    if event is None or not event.payload.get("from_trash"):
        return None
    reason = event.payload.get("reason")
    return str(reason) if reason is not None else None


async def purge(
    session: AsyncSession,
    blobs: BlobStore,
    document: Document,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    today: date,
    reason: str | None = None,
    early: bool = False,
) -> PurgeResult:
    """Final deletion of a trashed document. Every retention check runs again; a blocker keeps
    the document in the trash and is logged once per distinct reason. The mirror jobs of the
    result are enqueued after the commit."""
    from mhvp.documents import retention, services  # local: both import this package

    with trashed_visible(session):
        blocker = await services.deletion_blocker(session, document, today)
        if blocker is not None:
            if await _last_refusal_reason(session, document.id) != blocker:
                await emit(
                    session,
                    tenant_id=tenant_id,
                    type=EVENT_REFUSED,
                    entity_type="document",
                    entity_id=document.id,
                    actor_user_id=actor_user_id,
                    payload={"reason": blocker, "from_trash": True, "early": early},
                )
            return PurgeResult(document.id, False, blocker)
        extra: dict[str, Any] = {
            "from_trash": True,
            "trashed_at": document.deleted_at.isoformat() if document.deleted_at else None,
            "trashed_by": str(document.deleted_by) if document.deleted_by else None,
            "early": early,
        }
        if reason:
            extra["reason"] = reason
        deleted = await retention.delete_now(
            session,
            blobs,
            document,
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            extra=extra,
        )
        return PurgeResult(document.id, True, jobs=deleted.jobs)


async def due_ids(session: AsyncSession, now: datetime) -> list[uuid.UUID]:
    with trashed_visible(session):
        return list(
            await session.scalars(
                select(Document.id)
                .where(Document.deleted_at.is_not(None), Document.purge_at <= now)
                .order_by(Document.purge_at, Document.id)
            )
        )


async def purge_due_all_tenants_once(
    settings: Settings, *, blobs: BlobStore | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Daily run: every trashed document whose purge date passed is deleted for good unless a
    hold or a rule keeps it. One transaction per document, so one failure never rolls back the
    others; mirror steps are queued after each commit."""
    from mhvp.platform.models import Tenant, TenantStatus

    moment = now or datetime.now(UTC)
    store = blobs or BlobStore(settings)
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    report: dict[str, Any] = {"checked": 0, "deleted": 0, "held": 0, "errors": []}
    jobs: list[mirror_deletion.MirrorDeletionJob] = []
    try:
        async with platform_transaction(factory) as session:
            tenants = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenants:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    ids = await due_ids(session, moment)
            except Exception as exc:  # the other tenants must still run
                log.exception("trash purge failed", tenant_id=str(tenant_id))
                report["errors"].append(f"{tenant_id}: {exc.__class__.__name__}")
                continue
            for document_id in ids:
                report["checked"] += 1
                try:
                    async with tenant_transaction(factory, tenant_id) as session:
                        with trashed_visible(session):
                            document = await session.get(Document, document_id)
                        if document is None or document.deleted_at is None:
                            continue
                        result = await purge(
                            session,
                            store,
                            document,
                            tenant_id=tenant_id,
                            actor_user_id=None,
                            today=moment.date(),
                        )
                except Exception as exc:  # one document never stops the run
                    log.exception("trash purge failed", document_id=str(document_id))
                    report["errors"].append(f"{document_id}: {exc.__class__.__name__}")
                    continue
                if result.deleted:
                    report["deleted"] += 1
                    jobs.extend(result.jobs)
                else:
                    report["held"] += 1
    finally:
        await engine.dispose()
    report["mirror_jobs"] = mirror_deletion.enqueue(jobs)
    return report


@shared_task(name=TASK_NAME, acks_late=True)
def trash_purge() -> dict[str, Any]:
    return asyncio.run(purge_due_all_tenants_once(get_settings()))
