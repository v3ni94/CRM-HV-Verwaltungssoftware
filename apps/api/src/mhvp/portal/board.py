"""Digitaler Prüfungsraum für den Verwaltungsbeirat (7.9.2 PÜ07, PÜ08, 14, A52).

A board member gets a portal account with the role ``board`` bound to one audit engagement
(``board_access``). Through the portal the board reads the engagement, its positions and the
released receipts and records notes and questions per position (``board_audit_note``). The
management answers in the CRM. The board role never posts, releases or changes a statement:
the portal endpoints here are read only except for the note itself (PÜ08, Produktschutz, see
docs/rules/M21-07.md). The board sees only engagements of its own community; a board access
of another engagement or another tenant answers 404 without a hint whether it exists.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import AuditEngagement, AuditItem, HoaCostItem
from mhvp.portal import read_receipts
from mhvp.portal.models import PortalAccount

BOARD_ROLE = "board"
BOARD_LEGAL_BASIS = "board_audit"
NOTE_KINDS = ("note", "question", "answered")


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class BoardAccess(IdMixin, TimestampMixin, TenantMixin, Base):
    """Portal access of one board member (portal account) to one audit engagement."""

    __tablename__ = "board_access"
    __table_args__ = (
        UniqueConstraint("engagement_id", "account_id", name="uq_board_access_engagement_account"),
        Index("ix_board_access_account", "tenant_id", "account_id"),
    )

    engagement_id: Mapped[uuid.UUID] = _fk("audit_engagement.id", ondelete="CASCADE")
    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class BoardAuditNote(IdMixin, TimestampMixin, TenantMixin, Base):
    """Note or question of the board per position (audit item, statement cost item or the
    engagement as a whole). ``kind`` is note, question or answered; the answer of the
    management stays on the same row with author and time (PÜ08)."""

    __tablename__ = "board_audit_note"
    __table_args__ = (
        Index("ix_board_audit_note_engagement", "tenant_id", "engagement_id"),
        CheckConstraint(
            "kind IN ('note', 'question', 'answered')", name="ck_board_audit_note_kind"
        ),
    )

    engagement_id: Mapped[uuid.UUID] = _fk("audit_engagement.id", ondelete="CASCADE")
    audit_item_id: Mapped[uuid.UUID | None] = _fk(
        "audit_item.id", nullable=True, ondelete="SET NULL"
    )
    cost_item_id: Mapped[uuid.UUID | None] = _fk(
        "hoa_cost_item.id", nullable=True, ondelete="SET NULL"
    )
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="note", server_default="note"
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    created_by_account_id: Mapped[uuid.UUID] = _fk("portal_account.id")
    answered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Shared output helpers (used by the portal and the CRM section) ---------------------------


def note_out(n: BoardAuditNote) -> dict[str, Any]:
    return {
        "id": n.id,
        "engagement_id": n.engagement_id,
        "audit_item_id": n.audit_item_id,
        "cost_item_id": n.cost_item_id,
        "kind": n.kind,
        "text": n.text,
        "answer": n.answer,
        "created_at": n.created_at,
        "answered_at": n.answered_at,
    }


async def engagement_notes(session: AsyncSession, engagement_id: uuid.UUID) -> list[BoardAuditNote]:
    return list(
        (
            await session.scalars(
                select(BoardAuditNote)
                .where(BoardAuditNote.engagement_id == engagement_id)
                .order_by(BoardAuditNote.created_at, BoardAuditNote.id)
            )
        ).all()
    )


async def released_document_ids(
    session: AsyncSession, items: list[AuditItem]
) -> dict[uuid.UUID, uuid.UUID | None]:
    """Receipts released to the board: the document of every audit item plus the invoice or
    booking document behind the item's journal entry. Nothing else of the community, never a
    document of another engagement (PÜ07). Maps document id to the audit item it belongs to."""
    from mhvp.accounting.models import Invoice, JournalEntry

    out: dict[uuid.UUID, uuid.UUID | None] = {}
    for item in items:
        if item.document_id is not None:
            out.setdefault(item.document_id, item.id)
        if item.journal_entry_id is not None:
            entry_doc = await session.scalar(
                select(JournalEntry.document_id).where(JournalEntry.id == item.journal_entry_id)
            )
            if entry_doc is not None:
                out.setdefault(entry_doc, item.id)
            for invoice_doc in await session.scalars(
                select(Invoice.document_id).where(
                    Invoice.journal_entry_id == item.journal_entry_id,
                    Invoice.document_id.is_not(None),
                )
            ):
                if invoice_doc is not None:
                    out.setdefault(invoice_doc, item.id)
    return out


# Portal ------------------------------------------------------------------------------------

router = APIRouter(prefix="/portal/board", tags=["Portal Beirat"])


class BoardNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="note", pattern="^(note|question)$")
    text: str = Field(min_length=1, max_length=4000)
    audit_item_id: uuid.UUID | None = None
    cost_item_id: uuid.UUID | None = None


async def _board_user(request: Request) -> Any:
    from mhvp.portal.routers import portal_user

    return await portal_user(request)


async def _own_access(
    session: AsyncSession, account: PortalAccount, engagement_id: uuid.UUID
) -> tuple[BoardAccess, AuditEngagement]:
    row = await session.scalar(
        select(BoardAccess).where(
            BoardAccess.account_id == account.id,
            BoardAccess.engagement_id == engagement_id,
            BoardAccess.revoked_at.is_(None),
        )
    )
    eng = await session.get(AuditEngagement, engagement_id) if row is not None else None
    if row is None or eng is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
    return row, eng


def _engagement_out(eng: AuditEngagement, name: str | None) -> dict[str, Any]:
    return {
        "id": eng.id,
        "legal_entity_id": eng.legal_entity_id,
        "legal_entity_name": name,
        "statement_id": eng.statement_id,
        "period_from": eng.period_from,
        "period_to": eng.period_to,
        "purpose": eng.purpose,
        "sampling": eng.sampling,
        "status": eng.status,
        "snapshot_hash": eng.snapshot_hash,
    }


@router.get("/engagements", summary="Eigene Prüfaufträge (Beirat)")
async def list_engagements(
    request: Request, ctx: Any = Depends(_board_user)
) -> list[dict[str, Any]]:
    from mhvp.properties.models import LegalEntity

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(AuditEngagement, LegalEntity.name, BoardAccess.created_at)
                .join(BoardAccess, BoardAccess.engagement_id == AuditEngagement.id)
                .join(LegalEntity, LegalEntity.id == AuditEngagement.legal_entity_id)
                .where(BoardAccess.account_id == account.id, BoardAccess.revoked_at.is_(None))
                .order_by(AuditEngagement.period_from.desc(), AuditEngagement.id)
            )
        ).all()
        out = []
        for eng, name, granted_at in rows:
            notes = await engagement_notes(session, eng.id)
            out.append(
                _engagement_out(eng, name)
                | {
                    "granted_at": granted_at,
                    "open_questions": sum(1 for n in notes if n.kind == "question"),
                }
            )
        return out


@router.get(
    "/engagements/{engagement_id}", summary="Prüfauftrag mit Positionen, Belegen und Vermerken"
)
async def get_engagement(
    engagement_id: uuid.UUID, request: Request, ctx: Any = Depends(_board_user)
) -> dict[str, Any]:
    from mhvp.accounting.models import JournalEntry
    from mhvp.documents.models import Document
    from mhvp.hoa.meetings import _overall_status, refresh_audit_items
    from mhvp.properties.models import LegalEntity

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, eng = await _own_access(session, account, engagement_id)
        name = await session.scalar(
            select(LegalEntity.name).where(LegalEntity.id == eng.legal_entity_id)
        )
        # D33: positions changed after the check are shown outdated to the board as well.
        outdated_reasons = await refresh_audit_items(session, eng)
        items = list(
            (
                await session.scalars(
                    select(AuditItem)
                    .where(AuditItem.engagement_id == eng.id)
                    .order_by(AuditItem.created_at, AuditItem.id)
                )
            ).all()
        )
        positions = []
        for i in items:
            entry = (
                await session.get(JournalEntry, i.journal_entry_id)
                if i.journal_entry_id is not None
                else None
            )
            positions.append(
                {
                    "id": i.id,
                    "journal_entry_id": i.journal_entry_id,
                    "document_id": i.document_id,
                    "amount": i.amount,
                    "status": i.status,
                    "note": i.note,
                    "question": i.question,
                    "answer": i.answer,
                    "outdated_reason": outdated_reasons.get(str(i.id)),
                    "booking_date": entry.booking_date if entry else None,
                    "booking_text": entry.text if entry else None,
                    "booking_reference": entry.reference if entry else None,
                }
            )
        cost_items = (
            (
                await session.scalars(
                    select(HoaCostItem)
                    .where(HoaCostItem.statement_id == eng.statement_id)
                    .order_by(HoaCostItem.label, HoaCostItem.id)
                )
            ).all()
            if eng.statement_id is not None
            else []
        )
        released = await released_document_ids(session, items)
        documents = []
        if released:
            for d in await session.scalars(
                select(Document).where(Document.id.in_(released)).order_by(Document.created_at)
            ):
                documents.append(
                    {
                        "id": d.id,
                        "title": d.title,
                        "filename": d.filename,
                        "mime_type": d.mime_type,
                        "created_at": d.created_at,
                        "audit_item_id": released.get(d.id),
                    }
                )
        notes = await engagement_notes(session, eng.id)
        return _engagement_out(eng, name) | {
            "overall_status": _overall_status(items),
            "population": eng.population,
            "positions": positions,
            "cost_items": [
                {"id": c.id, "label": c.label, "amount": c.amount, "basis": c.basis}
                for c in cost_items
            ],
            "documents": documents,
            "notes": [note_out(n) for n in notes],
            "read_receipt_note": read_receipts.LEGAL_NOTE,
        }


@router.get(
    "/engagements/{engagement_id}/documents/{document_id}",
    summary="Beleg des Prüfauftrags öffnen (Abruf wird als Indiz vermerkt)",
)
async def open_document(
    engagement_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    ctx: Any = Depends(_board_user),
) -> Response:
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, eng = await _own_access(session, account, engagement_id)
        items = list(
            (
                await session.scalars(select(AuditItem).where(AuditItem.engagement_id == eng.id))
            ).all()
        )
        released = await released_document_ids(session, items)
        document = await session.get(Document, document_id) if document_id in released else None
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        # D34, PÜ13: the retrieval is an indication only, no acknowledgement of the statement.
        await read_receipts.record(session, account, document.id, "opened")
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="board_audit.document_opened",
            entity_type="audit_engagement",
            entity_id=eng.id,
            actor_user_id=principal.user_id,
            payload={"document_id": str(document.id), "account_id": str(account.id)},
        )
        return Response(
            content=data,
            media_type=document.mime_type,
            headers={"Content-Disposition": f'inline; filename="{document.filename}"'},
        )


@router.post(
    "/engagements/{engagement_id}/notes", status_code=201, summary="Vermerk oder Rückfrage (PÜ08)"
)
async def create_note(
    engagement_id: uuid.UUID,
    body: BoardNoteIn,
    request: Request,
    ctx: Any = Depends(_board_user),
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, eng = await _own_access(session, account, engagement_id)
        if body.audit_item_id is not None:
            item = await session.get(AuditItem, body.audit_item_id)
            if item is None or item.engagement_id != eng.id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Position gehört nicht zum Prüfauftrag."
                )
        if body.cost_item_id is not None:
            cost = await session.get(HoaCostItem, body.cost_item_id)
            if cost is None or eng.statement_id is None or cost.statement_id != eng.statement_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Abrechnungsposition gehört nicht zum Prüfauftrag.",
                )
        row = BoardAuditNote(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            engagement_id=eng.id,
            audit_item_id=body.audit_item_id,
            cost_item_id=body.cost_item_id,
            kind=body.kind,
            text=body.text.strip(),
            created_by_account_id=account.id,
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="board_audit_note.created",
            entity_type="audit_engagement",
            entity_id=eng.id,
            actor_user_id=principal.user_id,
            payload={"note_id": str(row.id), "kind": row.kind},
        )
        return note_out(row)


async def answer_note(
    session: AsyncSession,
    *,
    note: BoardAuditNote,
    answer: str,
    user_id: uuid.UUID | None,
    tenant_id: uuid.UUID,
) -> BoardAuditNote:
    """Management answer (PÜ08): traceable on the note itself, never overwriting the question."""
    note.answer = answer.strip()
    note.kind = "answered"
    note.answered_by = user_id
    note.answered_at = datetime.now(UTC)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="board_audit_note.answered",
        entity_type="audit_engagement",
        entity_id=note.engagement_id,
        actor_user_id=user_id,
        payload={"note_id": str(note.id)},
    )
    return note
