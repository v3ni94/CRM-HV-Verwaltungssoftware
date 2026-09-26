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
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.attributes import flag_modified

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.escaping import content_disposition
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import AuditEngagement, AuditItem, AuditReport, HoaCostItem
from mhvp.portal import read_receipts
from mhvp.portal.models import PortalAccount

BOARD_ROLE = "board"
BOARD_LEGAL_BASIS = "board_audit"
# Receipt types the board may open inline; everything else is served as a download.
INLINE_MIME_TYPES = frozenset({"application/pdf", "image/jpeg", "image/png", "image/tiff"})
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


# Filter helpers for the audit room (A77) --------------------------------------------------


async def _position_meta(
    session: AsyncSession, items: list[AuditItem]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Accounts (from the journal lines), vendor (from the booked or attached invoice), booking
    date and text per audit item. Only entries of the positions themselves are read (PÜ07)."""
    from mhvp.accounting.models import Invoice, JournalEntry, JournalLine, LedgerAccount
    from mhvp.contacts.models import Contact

    entry_ids = [i.journal_entry_id for i in items if i.journal_entry_id is not None]
    doc_ids = [i.document_id for i in items if i.document_id is not None]
    entries: dict[uuid.UUID, JournalEntry] = {}
    accounts: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if entry_ids:
        for e in await session.scalars(select(JournalEntry).where(JournalEntry.id.in_(entry_ids))):
            entries[e.id] = e
        rows = await session.execute(
            select(
                JournalLine.journal_entry_id,
                LedgerAccount.id,
                LedgerAccount.number,
                LedgerAccount.name,
            )
            .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
            .where(JournalLine.journal_entry_id.in_(entry_ids))
            .order_by(LedgerAccount.number)
        )
        for entry_id, acc_id, number, acc_name in rows.all():
            bucket = accounts.setdefault(entry_id, [])
            if all(a["id"] != acc_id for a in bucket):
                bucket.append({"id": acc_id, "number": number, "name": acc_name})
    entry_docs = [e.document_id for e in entries.values() if e.document_id is not None]
    vendor_by_entry: dict[uuid.UUID, uuid.UUID] = {}
    vendor_by_document: dict[uuid.UUID, uuid.UUID] = {}
    if entry_ids or doc_ids or entry_docs:
        conditions: list[Any] = []
        if entry_ids:
            conditions.append(Invoice.journal_entry_id.in_(entry_ids))
        if doc_ids or entry_docs:
            conditions.append(Invoice.document_id.in_(doc_ids + entry_docs))
        invoices = await session.execute(
            select(
                Invoice.journal_entry_id, Invoice.document_id, Invoice.provider_contact_id
            ).where(or_(*conditions))
        )
        for je_id, doc_id, provider in invoices.all():
            if provider is None:
                continue
            if je_id is not None:
                vendor_by_entry[je_id] = provider
            if doc_id is not None:
                vendor_by_document[doc_id] = provider
    vendor_ids = set(vendor_by_entry.values()) | set(vendor_by_document.values())
    names: dict[uuid.UUID, str] = {}
    if vendor_ids:
        for contact in await session.scalars(select(Contact).where(Contact.id.in_(vendor_ids))):
            names[contact.id] = contact.display_name
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for i in items:
        entry = entries.get(i.journal_entry_id) if i.journal_entry_id is not None else None
        vendor = None
        if entry is not None:
            vendor = vendor_by_entry.get(entry.id) or (
                vendor_by_document.get(entry.document_id) if entry.document_id else None
            )
        if vendor is None and i.document_id is not None:
            vendor = vendor_by_document.get(i.document_id)
        out[i.id] = {
            "accounts": accounts.get(entry.id, []) if entry is not None else [],
            "vendor_id": vendor,
            "vendor_name": names.get(vendor) if vendor is not None else None,
            "booking_date": entry.booking_date if entry is not None else None,
            "text": entry.text if entry is not None else None,
        }
    return out


def _filter_options(meta: dict[uuid.UUID, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    accounts: dict[uuid.UUID, dict[str, Any]] = {}
    vendors: dict[uuid.UUID, dict[str, Any]] = {}
    for m in meta.values():
        for a in m.get("accounts", []):
            accounts.setdefault(a["id"], a)
        if m.get("vendor_id") is not None:
            vendors.setdefault(
                m["vendor_id"], {"id": m["vendor_id"], "name": m.get("vendor_name") or ""}
            )
    return {
        "accounts": sorted(accounts.values(), key=lambda a: (a["number"], str(a["id"]))),
        "vendors": sorted(vendors.values(), key=lambda v: (v["name"], str(v["id"]))),
    }


def _matches(
    m: dict[str, Any],
    *,
    account_id: uuid.UUID | None,
    vendor_contact_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    q: str | None,
) -> bool:
    if account_id is not None and all(a["id"] != account_id for a in m.get("accounts", [])):
        return False
    if vendor_contact_id is not None and m.get("vendor_id") != vendor_contact_id:
        return False
    booking_date = m.get("booking_date")
    if date_from is not None and (booking_date is None or booking_date < date_from):
        return False
    if date_to is not None and (booking_date is None or booking_date > date_to):
        return False
    if q and q.strip():
        text = (m.get("text") or "").lower()
        if q.strip().lower() not in text:
            return False
    return True


# Portal ------------------------------------------------------------------------------------

router = APIRouter(prefix="/portal/board", tags=["Portal Beirat"])


class BoardNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="note", pattern="^(note|question)$")
    text: str = Field(min_length=1, max_length=4000)
    audit_item_id: uuid.UUID | None = None
    cost_item_id: uuid.UUID | None = None


class BoardStatementIn(BaseModel):
    """Statement of the board on one report version (A76, PÜ09): text only, no release."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=8000)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Die Stellungnahme darf nicht leer sein.")
        return value


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
    engagement_id: uuid.UUID,
    request: Request,
    account_id: uuid.UUID | None = None,
    vendor_contact_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, max_length=200),
    ctx: Any = Depends(_board_user),
) -> dict[str, Any]:
    """Engagement with positions, released receipts and notes. The optional filters (A77,
    PÜ08) narrow the positions and their receipts by account, vendor, booking date or text
    server side; ``filter_options`` lists the accounts and vendors of all positions so the
    portal offers only values that occur. Notes and cost items are never filtered."""
    from mhvp.accounting.models import JournalEntry
    from mhvp.documents.models import Document
    from mhvp.hoa.meetings import _overall_status, refresh_audit_items
    from mhvp.properties.models import LegalEntity

    if date_from is not None and date_to is not None and date_to < date_from:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig.")
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, eng = await _own_access(session, account, engagement_id)
        name = await session.scalar(
            select(LegalEntity.name).where(LegalEntity.id == eng.legal_entity_id)
        )
        # D33: positions changed after the check are shown outdated to the board as well.
        outdated_reasons = await refresh_audit_items(session, eng)
        all_items = list(
            (
                await session.scalars(
                    select(AuditItem)
                    .where(AuditItem.engagement_id == eng.id)
                    .order_by(AuditItem.created_at, AuditItem.id)
                )
            ).all()
        )
        meta = await _position_meta(session, all_items)
        filter_options = _filter_options(meta)
        items = [
            i
            for i in all_items
            if _matches(
                meta.get(i.id, {}),
                account_id=account_id,
                vendor_contact_id=vendor_contact_id,
                date_from=date_from,
                date_to=date_to,
                q=q,
            )
        ]
        positions = []
        for i in items:
            entry = (
                await session.get(JournalEntry, i.journal_entry_id)
                if i.journal_entry_id is not None
                else None
            )
            m = meta.get(i.id, {})
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
                    "accounts": m.get("accounts", []),
                    "vendor_contact_id": m.get("vendor_id"),
                    "vendor_name": m.get("vendor_name"),
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
            "overall_status": _overall_status(all_items),
            "population": eng.population,
            "positions": positions,
            "positions_total": len(all_items),
            "filter": {
                "account_id": account_id,
                "vendor_contact_id": vendor_contact_id,
                "date_from": date_from,
                "date_to": date_to,
                "q": q,
            },
            "filter_options": filter_options,
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
        # Only PDF and images open in the browser; every other type is offered as a download so
        # that no text or markup renders inside the portal (Sicherheitsreview 1.22, Befund 9).
        kind = "inline" if document.mime_type in INLINE_MIME_TYPES else "attachment"
        return Response(
            content=data,
            media_type=document.mime_type,
            headers={
                "Content-Disposition": content_disposition(kind, document.filename),
                "X-Content-Type-Options": "nosniff",
            },
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


# Reports and board statement (A76, PÜ09) ----------------------------------------------------

# Only these report fields leave the CRM towards the board; internal ids of positions and the
# snapshot hash stay in the CRM view.
REPORT_FIELDS = (
    "date",
    "sampling",
    "scope_note",
    "overall_status",
    "selected",
    "checked_count",
    "checked_value",
    "unchecked_count",
    "unchecked_value",
    "findings",
    "recommendation",
)


def _statement_out(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "text": value.get("text"),
        "recorded_at": value.get("recorded_at"),
        "recorded_by_account": value.get("recorded_by_account"),
        "source": value.get("source", "crm"),
    }


def _report_out(r: AuditReport) -> dict[str, Any]:
    content = r.content or {}
    return {
        "id": r.id,
        "engagement_id": r.engagement_id,
        "version": r.version,
        "created_at": r.created_at,
        "content": {k: content.get(k) for k in REPORT_FIELDS},
        "board_statement": _statement_out(content.get("board_statement")),
        "board_statement_history": [
            s
            for s in (_statement_out(v) for v in content.get("board_statement_history") or [])
            if s is not None
        ],
    }


@router.get("/engagements/{engagement_id}/reports", summary="Prüfberichte des Prüfauftrags (PÜ09)")
async def list_reports(
    engagement_id: uuid.UUID, request: Request, ctx: Any = Depends(_board_user)
) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, eng = await _own_access(session, account, engagement_id)
        rows = await session.scalars(
            select(AuditReport)
            .where(AuditReport.engagement_id == eng.id)
            .order_by(AuditReport.version.desc())
        )
        return [_report_out(r) for r in rows]


@router.post(
    "/engagements/{engagement_id}/reports/{report_id}/statement",
    summary="Stellungnahme des Beirats zum Prüfbericht (A76, PÜ09, nur Text)",
)
async def set_report_statement(
    engagement_id: uuid.UUID,
    report_id: uuid.UUID,
    body: BoardStatementIn,
    request: Request,
    ctx: Any = Depends(_board_user),
) -> dict[str, Any]:
    """Records the board statement on one report version as text, stored like the CRM entry in
    ``audit_report.content.board_statement`` with the recording portal account and the history
    of earlier texts. No release effect: neither the report nor the statement (Abrechnung)
    changes status; the report figures stay untouched. A report of another engagement answers
    404 without a hint."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, eng = await _own_access(session, account, engagement_id)
        report = await session.get(AuditReport, report_id)
        if report is None or report.engagement_id != eng.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
        now = datetime.now(UTC)
        content = dict(report.content or {})
        history = list(content.get("board_statement_history") or [])
        if content.get("board_statement"):
            history.append(content["board_statement"])
        content["board_statement"] = {
            "text": body.text.strip(),
            "recorded_by": str(principal.user_id) if principal.user_id else None,
            "recorded_by_account": str(account.id),
            "recorded_at": now.isoformat(),
            "source": "portal",
        }
        content["board_statement_history"] = history
        report.content = content
        flag_modified(report, "content")
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="audit_report.board_statement",
            entity_type="audit_engagement",
            entity_id=eng.id,
            actor_user_id=principal.user_id,
            payload={
                "report_id": str(report.id),
                "version": report.version,
                "account_id": str(account.id),
            },
        )
        return _report_out(report)


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
