"""CRM side of the board audit room (7.9.2 PÜ06 to PÜ09, A52, A72): list of engagements,
candidate bookings for audit items (filter by account, vendor and date), board portal access
per engagement (invitation like an owner, role ``board``), the management answer to a board
question and the board statement on a report (text only, no release effect). The board itself
acts only through ``mhvp.portal.board``."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_session_legal_entity_allowed,
    session_allowed_legal_entity_ids,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import AuditEngagement, AuditItem, AuditReport
from mhvp.portal.board import (
    BOARD_LEGAL_BASIS,
    BOARD_ROLE,
    BoardAccess,
    BoardAuditNote,
    answer_note,
    engagement_notes,
    note_out,
)
from mhvp.portal.models import AccessGrant, PortalAccount
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/hoa", tags=["hoa"])
READ = require_permission("accounting:read")
ANSWER = require_permission("accounting:create")
# Creating a portal account is contact management (same right as the owner invitation).
GRANT = require_permission("contacts:update")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoardAccessIn(_In):
    contact_id: uuid.UUID
    # Needed only when the contact has no portal account yet (invitation like an owner).
    email: str | None = Field(default=None, min_length=3, max_length=320)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)


class BoardAnswerIn(_In):
    answer: str = Field(min_length=1, max_length=4000)


class BoardStatementIn(_In):
    statement: str = Field(min_length=1, max_length=8000)

    @field_validator("statement")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Die Stellungnahme darf nicht leer sein.")
        return value.strip()


MAX_CANDIDATES = 200


async def _engagement(session: AsyncSession, engagement_id: uuid.UUID) -> AuditEngagement:
    eng = await session.get(AuditEngagement, engagement_id)
    if eng is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    # Legal entity scope of the membership (A37): a foreign community answers 404.
    ensure_session_legal_entity_allowed(session, eng.legal_entity_id)
    return eng


def _access_out(a: BoardAccess, account: PortalAccount | None) -> dict[str, Any]:
    return {
        "id": a.id,
        "account_id": a.account_id,
        "contact_id": a.contact_id,
        "account_status": account.status if account else None,
        "created_at": a.created_at,
        "revoked_at": a.revoked_at,
    }


@router.get("/audits", summary="Prüfaufträge einer GdWE")
async def list_audits(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        allowed = session_allowed_legal_entity_ids(session)
        if allowed is not None and legal_entity_id not in allowed:
            return []
        rows = await session.scalars(
            select(AuditEngagement)
            .where(AuditEngagement.legal_entity_id == legal_entity_id)
            .order_by(AuditEngagement.period_from.desc(), AuditEngagement.id)
        )
        return [
            {
                "id": e.id,
                "legal_entity_id": e.legal_entity_id,
                "statement_id": e.statement_id,
                "period_from": e.period_from,
                "period_to": e.period_to,
                "purpose": e.purpose,
                "sampling": e.sampling,
                "status": e.status,
            }
            for e in rows
        ]


@router.get("/audit-engagements/{engagement_id}/board", summary="Beiratszugänge und Rückfragen")
async def board_section(
    engagement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        eng = await _engagement(session, engagement_id)
        accesses = (
            await session.scalars(
                select(BoardAccess)
                .where(BoardAccess.engagement_id == eng.id)
                .order_by(BoardAccess.created_at)
            )
        ).all()
        out = []
        for a in accesses:
            out.append(_access_out(a, await session.get(PortalAccount, a.account_id)))
        notes = await engagement_notes(session, eng.id)
        return {
            "engagement_id": eng.id,
            "auditor_contact_ids": eng.auditor_contact_ids,
            "access": out,
            "notes": [note_out(n) for n in notes],
        }


@router.post(
    "/audit-engagements/{engagement_id}/board-access",
    status_code=201,
    summary="Beiratszugang zum Prüfauftrag anlegen (Einladung wie bei Eigentümern)",
)
async def create_board_access(
    engagement_id: uuid.UUID,
    body: BoardAccessIn,
    request: Request,
    principal: TenantPrincipal = Depends(GRANT),
) -> dict[str, Any]:
    from mhvp.portal.routers import provision_account

    async with tenant_tx(request, principal) as session:
        eng = await _engagement(session, engagement_id)
        if str(body.contact_id) not in eng.auditor_contact_ids:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Der Kontakt ist nicht als Prüfer des Prüfauftrags eingetragen.",
            )
        account = await session.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == body.contact_id)
        )
        if account is not None and await _is_staff(session, account.id):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Ein interner Mitarbeiterzugang erhält keinen Beiratszugang.",
            )
        existing = (
            await session.scalar(
                select(BoardAccess.id).where(
                    BoardAccess.engagement_id == eng.id,
                    BoardAccess.account_id == account.id,
                    BoardAccess.revoked_at.is_(None),
                )
            )
            if account is not None
            else None
        )
        if existing is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Beiratszugang besteht bereits.")
        existing_account_id = account.id if account is not None else None
    invitation_token: str | None = None
    if existing_account_id is None:
        if not body.email or not body.display_name:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Für einen neuen Portalzugang sind E-Mail und Anzeigename erforderlich.",
            )
        created = await provision_account(
            request,
            principal,
            contact_id=body.contact_id,
            email=body.email,
            display_name=body.display_name,
        )
        invitation_token = str(created["invitation_token"])
        account_id = uuid.UUID(str(created["id"]))
    else:
        account_id = existing_account_id
    async with tenant_tx(request, principal) as session:
        eng = await _engagement(session, engagement_id)
        row = BoardAccess(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            engagement_id=eng.id,
            account_id=account_id,
            contact_id=body.contact_id,
            legal_entity_id=eng.legal_entity_id,
        )
        session.add(row)
        # Role board in the access matrix (6.9.6): scope is the engagement only, right comment
        # (notes and questions); survives a resync (MANUAL_BASES in mhvp.portal.access).
        session.add(
            AccessGrant(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                account_id=account_id,
                scope_type="audit_engagement",
                scope_id=eng.id,
                right="comment",
                legal_basis=BOARD_LEGAL_BASIS,
                role=BOARD_ROLE,
                valid_from=local_today(),
                valid_to=None,
            )
        )
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="board_access.created",
            entity_type="audit_engagement",
            entity_id=eng.id,
            actor_user_id=principal.user_id,
            payload={"account_id": str(account_id), "contact_id": str(body.contact_id)},
        )
        return {
            "id": row.id,
            "account_id": account_id,
            "contact_id": body.contact_id,
            "invitation_token": invitation_token,
        }


async def _is_staff(session: AsyncSession, account_id: uuid.UUID) -> bool:
    from mhvp.portal import access

    return await access.has_staff_grant(session, account_id)


@router.post(
    "/audit-engagements/{engagement_id}/board-access/{access_id}/revoke",
    summary="Beiratszugang beenden",
)
async def revoke_board_access(
    engagement_id: uuid.UUID,
    access_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(GRANT),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _engagement(session, engagement_id)
        row = await session.get(BoardAccess, access_id)
        if row is None or row.engagement_id != engagement_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.revoked_at is None:
            row.revoked_at = datetime.now(UTC)
            row.revoked_by = principal.user_id
            grants = await session.scalars(
                select(AccessGrant).where(
                    AccessGrant.account_id == row.account_id,
                    AccessGrant.legal_basis == BOARD_LEGAL_BASIS,
                    AccessGrant.scope_id == engagement_id,
                    AccessGrant.valid_to.is_(None),
                )
            )
            for g in grants:
                g.valid_to = local_today()
            await session.flush()
        return _access_out(row, await session.get(PortalAccount, row.account_id))


@router.post(
    "/audit-engagements/{engagement_id}/notes/{note_id}/answer",
    summary="Rückfrage des Beirats beantworten (PÜ08)",
)
async def answer_board_note(
    engagement_id: uuid.UUID,
    note_id: uuid.UUID,
    body: BoardAnswerIn,
    request: Request,
    principal: TenantPrincipal = Depends(ANSWER),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _engagement(session, engagement_id)
        note = await session.get(BoardAuditNote, note_id)
        if note is None or note.engagement_id != engagement_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if note.kind == "answered":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Rückfrage ist bereits beantwortet.")
        await answer_note(
            session,
            note=note,
            answer=body.answer,
            user_id=principal.user_id,
            tenant_id=principal.tenant_id,
        )
        return note_out(note)


# Candidate bookings for audit items (PÜ07, PÜ08; A72) --------------------------------------


@router.get(
    "/audits/{audit_id}/candidates",
    summary="Gebuchte Positionen zur Auswahl als Prüfposition (Filter Konto, Lieferant, Datum)",
)
async def audit_candidates(
    audit_id: uuid.UUID,
    request: Request,
    account_id: uuid.UUID | None = None,
    vendor_contact_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, max_length=200),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Posted journal entries of the community in the engagement period (or a narrower date
    range inside it) with their accounts and, where an invoice is booked, the vendor. Read
    only: the selection itself is ``POST /hoa/audits/{id}/items``; already selected entries are
    flagged. At most ``MAX_CANDIDATES`` rows, ordered by booking date."""
    from mhvp.accounting.models import (
        EntryStatus,
        Invoice,
        JournalEntry,
        JournalLine,
        Ledger,
        LedgerAccount,
    )

    async with tenant_tx(request, principal) as session:
        eng = await _engagement(session, audit_id)
        start = max(date_from, eng.period_from) if date_from else eng.period_from
        end = min(date_to, eng.period_to) if date_to else eng.period_to
        if end < start:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig.")
        query = (
            select(JournalEntry)
            .join(Ledger, Ledger.id == JournalEntry.ledger_id)
            .where(
                Ledger.legal_entity_id == eng.legal_entity_id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date.between(start, end),
            )
        )
        if account_id is not None:
            query = query.where(
                JournalEntry.id.in_(
                    select(JournalLine.journal_entry_id).where(JournalLine.account_id == account_id)
                )
            )
        if vendor_contact_id is not None:
            by_vendor = select(Invoice).where(Invoice.provider_contact_id == vendor_contact_id)
            query = query.where(
                JournalEntry.id.in_(
                    by_vendor.with_only_columns(Invoice.journal_entry_id).where(
                        Invoice.journal_entry_id.is_not(None)
                    )
                )
                | JournalEntry.document_id.in_(
                    by_vendor.with_only_columns(Invoice.document_id).where(
                        Invoice.document_id.is_not(None)
                    )
                )
            )
        if q:
            query = query.where(JournalEntry.text.ilike(f"%{q.strip()}%"))
        total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        entries = (
            await session.scalars(
                query.order_by(JournalEntry.booking_date, JournalEntry.number).limit(MAX_CANDIDATES)
            )
        ).all()
        entry_ids = [e.id for e in entries]
        lines = (
            (
                await session.execute(
                    select(
                        JournalLine.journal_entry_id,
                        LedgerAccount.id,
                        LedgerAccount.number,
                        LedgerAccount.name,
                        JournalLine.debit,
                    )
                    .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
                    .where(JournalLine.journal_entry_id.in_(entry_ids))
                )
            ).all()
            if entry_ids
            else []
        )
        accounts: dict[uuid.UUID, list[dict[str, Any]]] = {}
        amounts: dict[uuid.UUID, Decimal] = {}
        for entry_id, acc_id, number, name, debit in lines:
            accounts.setdefault(entry_id, []).append({"id": acc_id, "number": number, "name": name})
            amounts[entry_id] = amounts.get(entry_id, Decimal("0")) + Decimal(debit)
        invoices = (
            (
                await session.execute(
                    select(
                        Invoice.journal_entry_id,
                        Invoice.document_id,
                        Invoice.provider_contact_id,
                        Invoice.number,
                    ).where(
                        Invoice.journal_entry_id.in_(entry_ids)
                        | Invoice.document_id.in_([e.document_id for e in entries if e.document_id])
                    )
                )
            ).all()
            if entry_ids
            else []
        )
        vendor_by_entry: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
        vendor_by_document: dict[uuid.UUID, tuple[uuid.UUID, str]] = {}
        for je_id, doc_id, provider, number in invoices:
            if je_id is not None:
                vendor_by_entry[je_id] = (provider, number)
            if doc_id is not None:
                vendor_by_document[doc_id] = (provider, number)
        selected = set(
            (
                await session.scalars(
                    select(AuditItem.journal_entry_id).where(
                        AuditItem.engagement_id == eng.id, AuditItem.journal_entry_id.is_not(None)
                    )
                )
            ).all()
        )
        rows = []
        for e in entries:
            vendor = vendor_by_entry.get(e.id) or (
                vendor_by_document.get(e.document_id) if e.document_id else None
            )
            rows.append(
                {
                    "journal_entry_id": e.id,
                    "booking_date": e.booking_date,
                    "number": e.number,
                    "text": e.text,
                    "amount": amounts.get(e.id, Decimal("0")),
                    "document_id": e.document_id,
                    "accounts": accounts.get(e.id, []),
                    "vendor_contact_id": vendor[0] if vendor else None,
                    "invoice_number": vendor[1] if vendor else None,
                    "selected": e.id in selected,
                }
            )
        return {
            "period_from": start,
            "period_to": end,
            "total": total,
            "truncated": total > len(rows),
            "items": rows,
        }


# Reports and board statement (PÜ09; A72) ----------------------------------------------------


def _report_out(r: AuditReport) -> dict[str, Any]:
    return {
        "id": r.id,
        "engagement_id": r.engagement_id,
        "version": r.version,
        "content": r.content,
        "board_statement": r.content.get("board_statement"),
        "created_at": r.created_at,
    }


@router.get("/audits/{audit_id}/reports", summary="Prüfberichte eines Prüfauftrags (PÜ09)")
async def list_reports(
    audit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        eng = await _engagement(session, audit_id)
        rows = await session.scalars(
            select(AuditReport)
            .where(AuditReport.engagement_id == eng.id)
            .order_by(AuditReport.version.desc())
        )
        return [_report_out(r) for r in rows]


@router.post(
    "/audit-reports/{report_id}/board-statement",
    summary="Beiratsstellungnahme zum Prüfbericht erfassen (PÜ09, nur Text)",
)
async def set_board_statement(
    report_id: uuid.UUID,
    body: BoardStatementIn,
    request: Request,
    principal: TenantPrincipal = Depends(ANSWER),
) -> dict[str, Any]:
    """Records the statement of the board on a report version as text. It has no release
    effect: neither the report nor the statement (Abrechnung) changes status, and the report
    figures stay untouched. A later statement replaces the text; the previous one is kept in
    the history of the report content."""
    async with tenant_tx(request, principal) as session:
        report = await session.get(AuditReport, report_id)
        if report is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _engagement(session, report.engagement_id)
        now = datetime.now(UTC)
        content = dict(report.content)
        history = list(content.get("board_statement_history") or [])
        if content.get("board_statement"):
            history.append(content["board_statement"])
        content["board_statement"] = {
            "text": body.statement.strip(),
            "recorded_by": str(principal.user_id),
            "recorded_at": now.isoformat(),
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
            entity_id=report.engagement_id,
            actor_user_id=principal.user_id,
            payload={"report_id": str(report.id), "version": report.version},
        )
        return _report_out(report)
