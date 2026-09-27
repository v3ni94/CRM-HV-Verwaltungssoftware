"""Retention matrix in operation (M6-04, V17, 6.9.5, chapter 11): period computation, category
to profile mapping, holds per ticket, the monthly deletion proposal run with four eyes approval
and the deletion log.

Legal basis: the periods are the operator's draft of 26.09.2026 and stay "zu prüfen durch
Steuerberater" (rule ``docs/rules/M6-04-aufbewahrungsprofile.md``). Nothing here decides a
legal question; a document is only ever proposed for deletion when its profile was released
in the four eyes procedure, its computed period ended before the reference date and no hold
(document or ticket) exists. The same check runs again at execution time.

Period start (``RetentionStart``), a labelled assumption (docs/ASSUMPTIONS.md):

* ``end_of_year_created``: 31.12. of the year the document was created, plus the period.
* ``end_of_year_last_entry``, ``contract_end``, ``statement_issued``: 31.12. of the year of
  ``Document.retention_base_on`` (last entry, contract end, issue date), plus the period. The
  year end is used for all three because it never shortens the period.
* ``purpose_end``: ``retention_base_on`` plus the period, day exact (portal and applicant data
  are deleted as soon as the purpose ended, no year end extension).
* ``permanent``: no date, never deleted.

Without the needed base date the period cannot be computed; ``retention_until`` stays empty
and the document stays locked (``deletion_blocker``).
"""

from __future__ import annotations

import asyncio
import calendar
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.logging import get_logger
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import mirror_deletion
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    DeletionItemStatus,
    DeletionProposal,
    DeletionProposalItem,
    DeletionProposalStatus,
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentMirror,
    MirrorStatus,
    RetentionProfile,
    RetentionStart,
)
from mhvp.tickets.models import Ticket

log = get_logger(__name__)

_YEAR_END_RULES = frozenset(
    {
        RetentionStart.END_OF_YEAR_LAST_ENTRY,
        RetentionStart.CONTRACT_END,
        RetentionStart.STATEMENT_ISSUED,
    }
)


# Period computation ----------------------------------------------------------------------


def add_period(start: date, years: int, months: int) -> date:
    """``start`` plus years and months; the day is clamped to the target month's length."""
    total = start.month - 1 + months + 12 * years
    year, month = start.year + total // 12, total % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def compute_retention_until(
    profile: RetentionProfile, *, created_on: date, base_on: date | None
) -> date | None:
    """End of the retention period, or None (permanent, or base date missing)."""
    if profile.permanent:
        return None
    rule = profile.start_rule
    if rule is RetentionStart.END_OF_YEAR_CREATED:
        start = date(created_on.year, 12, 31)
    elif rule in _YEAR_END_RULES:
        if base_on is None:
            return None
        start = date(base_on.year, 12, 31)
    elif rule is RetentionStart.PURPOSE_END:
        if base_on is None:
            return None
        start = base_on
    else:  # pragma: no cover - every member is handled above
        raise ValueError(f"unknown start rule {rule}")
    return add_period(start, profile.retention_years, profile.retention_months)


def needs_base_date(profile: RetentionProfile) -> bool:
    return not profile.permanent and profile.start_rule is not RetentionStart.END_OF_YEAR_CREATED


async def assign_profile(
    session: AsyncSession, document: Document, profile: RetentionProfile | None
) -> None:
    """Sets the profile and recomputes ``retention_until`` from the document's dates."""
    if profile is None:
        document.retention_profile_id = None
        document.retention_until = None
        return
    document.retention_profile_id = profile.id
    document.retention_until = compute_retention_until(
        profile, created_on=document.created_at.date(), base_on=document.retention_base_on
    )


async def profile_for_category(
    session: AsyncSession, category_id: uuid.UUID | None
) -> RetentionProfile | None:
    if category_id is None:
        return None
    category = await session.get(DocumentCategory, category_id)
    if category is None or category.retention_profile_id is None:
        return None
    return await session.get(RetentionProfile, category.retention_profile_id)


async def apply_category_mapping(session: AsyncSession, *, only_unassigned: bool = True) -> int:
    """Assigns the mapped profile of the category to every document of the tenant that has
    none yet (or to all categorised documents with ``only_unassigned=False``)."""
    categories = {
        c.id: c
        for c in (
            await session.scalars(
                select(DocumentCategory).where(DocumentCategory.retention_profile_id.is_not(None))
            )
        ).all()
    }
    if not categories:
        return 0
    profiles = {
        p.id: p
        for p in (
            await session.scalars(
                select(RetentionProfile).where(
                    RetentionProfile.id.in_([c.retention_profile_id for c in categories.values()])
                )
            )
        ).all()
    }
    query = select(Document).where(Document.category_id.in_(list(categories)))
    if only_unassigned:
        query = query.where(Document.retention_profile_id.is_(None))
    count = 0
    for document in (await session.scalars(query)).all():
        if document.category_id is None:
            continue
        mapped = categories[document.category_id].retention_profile_id
        profile = profiles.get(mapped) if mapped is not None else None
        if profile is None:
            continue
        await assign_profile(session, document, profile)
        count += 1
    await session.flush()
    return count


# Holds -----------------------------------------------------------------------------------


async def ticket_hold(session: AsyncSession, document_id: uuid.UUID) -> str | None:
    """Reason of a hold on a ticket the document is linked to, or None."""
    ticket_ids = (
        await session.scalars(
            select(DocumentLink.entity_id).where(
                DocumentLink.document_id == document_id, DocumentLink.entity_type == "ticket"
            )
        )
    ).all()
    if not ticket_ids:
        return None
    ticket = await session.scalar(
        select(Ticket)
        .where(Ticket.id.in_(ticket_ids), Ticket.retention_hold_reason.is_not(None))
        .order_by(Ticket.number)
        .limit(1)
    )
    if ticket is None:
        return None
    return f"Vorgang TNR#{ticket.number}: {ticket.retention_hold_reason}"


# Deletion (shared by DELETE /documents/{id} and the proposal execution) -------------------


@dataclass(frozen=True)
class Deleted:
    document_id: uuid.UUID
    sha256: str
    jobs: list[mirror_deletion.MirrorDeletionJob]


async def delete_now(
    session: AsyncSession,
    blobs: BlobStore,
    document: Document,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    extra: dict[str, Any] | None = None,
) -> Deleted:
    """Removes index row and S3 original and journals the mirror steps (A43, M6-03). The
    caller has checked ``deletion_blocker`` in this transaction; ``enqueue`` the jobs after
    the commit."""
    mirrors = (
        await session.scalars(
            select(DocumentMirror).where(
                DocumentMirror.document_id == document.id,
                DocumentMirror.status != MirrorStatus.PENDING,
            )
        )
    ).all()
    jobs = await mirror_deletion.request(
        session,
        tenant_id=tenant_id,
        document_id=document.id,
        mirrors=list(mirrors),
        actor_user_id=actor_user_id,
    )
    blobs.delete(document.storage_ref)
    payload: dict[str, Any] = {
        "sha256": document.sha256,
        "profile": str(document.retention_profile_id),
        "mirror_deletions": len(jobs),
    }
    payload.update(extra or {})
    await emit(
        session,
        tenant_id=tenant_id,
        type="document.deleted",
        entity_type="document",
        entity_id=document.id,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    result = Deleted(document_id=document.id, sha256=document.sha256, jobs=jobs)
    await session.delete(document)
    return result


# Proposals -------------------------------------------------------------------------------


async def _deletion_blocker(session: AsyncSession, document: Document, today: date) -> str | None:
    from mhvp.documents import services  # local: services imports this module

    return await services.deletion_blocker(session, document, today)


async def due_documents(session: AsyncSession, today: date) -> list[Document]:
    """Documents whose computed period ended before ``today`` and which no blocker keeps."""
    rows = (
        await session.scalars(
            select(Document)
            .where(
                Document.retention_until.is_not(None),
                Document.retention_until < today,
                Document.retention_hold_reason.is_(None),
                Document.retention_profile_id.is_not(None),
            )
            .order_by(Document.retention_until, Document.created_at)
        )
    ).all()
    due: list[Document] = []
    for document in rows:
        if await _deletion_blocker(session, document, today) is None:
            due.append(document)
    return due


async def _open_proposal_document_ids(session: AsyncSession) -> set[uuid.UUID]:
    return set(
        (
            await session.scalars(
                select(DeletionProposalItem.document_id)
                .join(DeletionProposal, DeletionProposal.id == DeletionProposalItem.proposal_id)
                .where(
                    DeletionProposal.status.in_(
                        [DeletionProposalStatus.OPEN, DeletionProposalStatus.APPROVED]
                    )
                )
            )
        ).all()
    )


async def propose(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    today: date,
    created_by: uuid.UUID | None,
) -> DeletionProposal | None:
    """Creates a proposal with every due document not already in an open proposal; returns
    None when nothing is due (no empty proposals)."""
    already = await _open_proposal_document_ids(session)
    documents = [d for d in await due_documents(session, today) if d.id not in already]
    if not documents:
        return None
    profiles = {
        p.id: p
        for p in (
            await session.scalars(
                select(RetentionProfile).where(
                    RetentionProfile.id.in_({d.retention_profile_id for d in documents})
                )
            )
        ).all()
    }
    categories = {
        c.id: c.code
        for c in (
            await session.scalars(
                select(DocumentCategory).where(
                    DocumentCategory.id.in_({d.category_id for d in documents if d.category_id})
                )
            )
        ).all()
    }
    proposal = DeletionProposal(tenant_id=tenant_id, reference_date=today, created_by=created_by)
    session.add(proposal)
    await session.flush()
    for document in documents:
        if document.retention_profile_id is None or document.retention_until is None:
            continue  # excluded by due_documents already; keeps the types exact
        session.add(
            DeletionProposalItem(
                tenant_id=tenant_id,
                proposal_id=proposal.id,
                document_id=document.id,
                title=document.title,
                sha256=document.sha256,
                category_code=(
                    categories.get(document.category_id) if document.category_id else None
                ),
                document_class=profiles[document.retention_profile_id].document_class,
                retention_until=document.retention_until,
            )
        )
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="deletion_proposal.created",
        entity_type="deletion_proposal",
        entity_id=proposal.id,
        actor_user_id=created_by,
        payload={"documents": len(documents), "reference_date": today.isoformat()},
    )
    return proposal


def _require_status(proposal: DeletionProposal, *expected: DeletionProposalStatus) -> None:
    if proposal.status not in expected:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail=f"Der Löschvorschlag ist im Zustand {proposal.status.value}.",
        )


async def approve(
    session: AsyncSession, proposal: DeletionProposal, *, user_id: uuid.UUID | None
) -> None:
    """Four eyes: the approver is neither the person who started the proposal nor absent."""
    _require_status(proposal, DeletionProposalStatus.OPEN)
    if user_id is None or proposal.created_by == user_id:
        raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
    proposal.status = DeletionProposalStatus.APPROVED
    proposal.approved_by, proposal.approved_at = user_id, datetime.now(UTC)
    await emit(
        session,
        tenant_id=proposal.tenant_id,
        type="deletion_proposal.approved",
        entity_type="deletion_proposal",
        entity_id=proposal.id,
        actor_user_id=user_id,
        payload={"created_by": str(proposal.created_by)},
    )


async def reject(
    session: AsyncSession,
    proposal: DeletionProposal,
    *,
    user_id: uuid.UUID | None,
    note: str | None,
) -> None:
    _require_status(proposal, DeletionProposalStatus.OPEN, DeletionProposalStatus.APPROVED)
    proposal.status = DeletionProposalStatus.REJECTED
    proposal.rejected_by, proposal.rejected_at, proposal.note = user_id, datetime.now(UTC), note
    await emit(
        session,
        tenant_id=proposal.tenant_id,
        type="deletion_proposal.rejected",
        entity_type="deletion_proposal",
        entity_id=proposal.id,
        actor_user_id=user_id,
        payload={"note": note},
    )


@dataclass
class Execution:
    deleted: int = 0
    skipped: int = 0
    jobs: list[mirror_deletion.MirrorDeletionJob] = field(default_factory=list)


async def execute(
    session: AsyncSession,
    proposal: DeletionProposal,
    *,
    blobs: BlobStore,
    user_id: uuid.UUID | None,
    today: date,
) -> Execution:
    """Deletes the approved documents. Four eyes again: the executor is not the approver.
    Every document is re-checked on the day of execution (hold, period, profile); a document
    that must be kept is logged as skipped with the reason and stays."""
    _require_status(proposal, DeletionProposalStatus.APPROVED)
    if user_id is None or proposal.approved_by == user_id:
        raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
    items = (
        await session.scalars(
            select(DeletionProposalItem)
            .where(DeletionProposalItem.proposal_id == proposal.id)
            .order_by(DeletionProposalItem.created_at)
        )
    ).all()
    result = Execution()
    now = datetime.now(UTC)
    for item in items:
        if item.status is not DeletionItemStatus.PROPOSED:
            continue
        document = await session.get(Document, item.document_id)
        if document is None:
            item.status, item.skip_reason = DeletionItemStatus.SKIPPED, "Dokument bereits gelöscht."
            result.skipped += 1
            continue
        blocker = await _deletion_blocker(session, document, today)
        if blocker is None and document.sha256 != item.sha256:
            blocker = "Der Inhalt des Dokuments hat sich seit dem Vorschlag geändert."
        if blocker is not None:
            item.status, item.skip_reason = DeletionItemStatus.SKIPPED, blocker
            result.skipped += 1
            await emit(
                session,
                tenant_id=proposal.tenant_id,
                type="document.deletion_refused",
                entity_type="document",
                entity_id=document.id,
                actor_user_id=user_id,
                payload={"reason": blocker, "proposal_id": str(proposal.id)},
            )
            continue
        deleted = await delete_now(
            session,
            blobs,
            document,
            tenant_id=proposal.tenant_id,
            actor_user_id=user_id,
            extra={
                "proposal_id": str(proposal.id),
                "approved_by": str(proposal.approved_by),
                "document_class": item.document_class,
                "category": item.category_code,
            },
        )
        item.status, item.deleted_at, item.deleted_by = DeletionItemStatus.DELETED, now, user_id
        item.mirror_deletions = len(deleted.jobs)
        result.jobs.extend(deleted.jobs)
        result.deleted += 1
    proposal.status = DeletionProposalStatus.EXECUTED
    proposal.executed_by, proposal.executed_at = user_id, now
    await emit(
        session,
        tenant_id=proposal.tenant_id,
        type="deletion_proposal.executed",
        entity_type="deletion_proposal",
        entity_id=proposal.id,
        actor_user_id=user_id,
        payload={
            "deleted": result.deleted,
            "skipped": result.skipped,
            "approved_by": str(proposal.approved_by),
        },
    )
    return result


# Monthly job -----------------------------------------------------------------------------


async def propose_all_tenants_once(
    settings: Settings, *, today: date | None = None
) -> dict[str, Any]:
    """Monthly run over all active tenants: one proposal per tenant with due documents. The
    job never deletes anything; approval and execution stay with two persons."""
    from mhvp.platform.models import Tenant, TenantStatus

    reference = today or datetime.now(UTC).date()
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    report: dict[str, Any] = {"tenants": 0, "proposals": 0, "documents": 0, "errors": []}
    try:
        async with platform_transaction(factory) as session:
            ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in ids:
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    proposal = await propose(
                        session, tenant_id=tenant_id, today=reference, created_by=None
                    )
                    count = 0
                    if proposal is not None:
                        count = len(
                            (
                                await session.scalars(
                                    select(DeletionProposalItem.id).where(
                                        DeletionProposalItem.proposal_id == proposal.id
                                    )
                                )
                            ).all()
                        )
            except Exception as exc:  # the other tenants must still run
                log.exception("deletion proposal run failed", tenant_id=str(tenant_id))
                report["errors"].append(f"{tenant_id}: {exc.__class__.__name__}")
                continue
            report["tenants"] += 1
            if proposal is not None:
                report["proposals"] += 1
                report["documents"] += count
    finally:
        await engine.dispose()
    return report


@shared_task(name="mhvp.documents.deletion_proposals", acks_late=True)
def deletion_proposals() -> dict[str, Any]:
    return asyncio.run(propose_all_tenants_once(get_settings()))
