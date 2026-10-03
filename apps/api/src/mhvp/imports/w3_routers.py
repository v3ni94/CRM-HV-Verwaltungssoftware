"""Read endpoints of the imported history (/api/v1/imports/immoware24/history, M8-04, M8-06,
M8-07): historical tickets, open items with sums and the bank transaction to journal
assignment. Read only: no write, no posting."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from mhvp.accounting.models import Ledger
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard, session_allowed_property_ids
from mhvp.core.listparams import MAX_PAGE_SIZE, strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.imports import statement_reports, w3_reports
from mhvp.imports.history_models import (
    MigratedBankLink,
    MigratedOpenItem,
    MigratedResolution,
    MigratedStatement,
    MigratedTicket,
)
from mhvp.properties.models import Property

# M2-02, R08-01: property and ledger query parameters outside the assignment answer 404.
HISTORY_GUARD = property_column_guard({"property_id": Property.id, "ledger_id": Ledger.property_id})
router = APIRouter(
    prefix="/imports/immoware24/history",
    tags=["Import Immoware24"],
    dependencies=[
        Depends(
            property_column_guard({"property_id": Property.id, "ledger_id": Ledger.property_id})
        )
    ],
)
READ_TICKETS = require_permission("tickets:read")
READ_ACCOUNTING = require_permission("accounting:read")


class HistoryTicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    source_ticket_id: str
    property_id: uuid.UUID
    unit_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    title: str
    status_text: str | None
    created_on: date
    closed_on: date | None
    description: str | None


class HistoryOpenItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ledger_id: uuid.UUID
    kind: str
    source_item_id: str
    property_id: uuid.UUID
    unit_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    original_due_date: date | None
    original_amount: Decimal
    paid_amount: Decimal
    open_amount: Decimal
    description: str | None
    resolution_ref: str | None
    cutoff_date: date | None


class HistoryBankLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    bank_transaction_id: uuid.UUID
    journal_entry_id: uuid.UUID | None
    source_entry_id: str | None


@router.get(
    "/tickets", summary="Historische Tickets (nur lesend)", dependencies=[Depends(strict_query)]
)
async def history_tickets(
    request: Request,
    property_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ_TICKETS),
) -> list[HistoryTicketOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MigratedTicket)
        if property_id:
            query = query.where(MigratedTicket.property_id == property_id)
        allowed = session_allowed_property_ids(session)  # M2-02, R08-01
        if allowed is not None:
            query = query.where(MigratedTicket.property_id.in_(allowed))
        rows = await session.scalars(
            query.order_by(MigratedTicket.created_on.desc(), MigratedTicket.source_ticket_id)
            .offset(offset)
            .limit(limit)
        )
        return [HistoryTicketOut.model_validate(r) for r in rows.all()]


@router.get(
    "/open-items",
    summary="Übernommene Einzelposten der Altdaten",
    dependencies=[Depends(strict_query)],
)
async def history_open_items(
    request: Request,
    ledger_id: uuid.UUID | None = None,
    kind: str | None = Query(
        default=None, pattern="^(receivable|credit|deposit|reserve|loan|special_levy)$"
    ),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> list[HistoryOpenItemOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MigratedOpenItem)
        if ledger_id:
            query = query.where(MigratedOpenItem.ledger_id == ledger_id)
        allowed = session_allowed_property_ids(session)  # M2-02, R08-01
        if allowed is not None:
            query = query.where(MigratedOpenItem.property_id.in_(allowed))
        if kind:
            query = query.where(MigratedOpenItem.kind == kind)
        rows = await session.scalars(
            query.order_by(MigratedOpenItem.original_due_date, MigratedOpenItem.source_item_id)
            .offset(offset)
            .limit(limit)
        )
        return [HistoryOpenItemOut.model_validate(r) for r in rows.all()]


@router.get("/open-items/summary", summary="Summen der Einzelposten je Art (Abgleich)")
async def history_open_item_summary(
    request: Request,
    ledger_id: uuid.UUID,
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        total = await session.scalar(
            select(func.count())
            .select_from(MigratedOpenItem)
            .where(MigratedOpenItem.ledger_id == ledger_id)
        )
        if not total:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return {
            "ledger_id": str(ledger_id),
            "kinds": await w3_reports.open_item_summary(session, ledger_id),
        }


@router.get(
    "/bank-links",
    summary="Zuordnung historischer Bankumsätze zum Journal",
    dependencies=[Depends(strict_query)],
)
async def history_bank_links(
    request: Request,
    open_only: bool = False,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> list[HistoryBankLinkOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MigratedBankLink)
        if open_only:
            query = query.where(MigratedBankLink.journal_entry_id.is_(None))
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            # Y01 (M2-02): only links whose bank transaction belongs to a visible account.
            from mhvp.banking.property_scope import transaction_account_filter

            query = query.where(
                transaction_account_filter(allowed, MigratedBankLink.bank_transaction_id)
            )
        rows = await session.scalars(
            query.order_by(MigratedBankLink.created_at, MigratedBankLink.id)
            .offset(offset)
            .limit(limit)
        )
        return [HistoryBankLinkOut.model_validate(r) for r in rows.all()]


@router.get(
    "/open-items/balance-check",
    summary="Prüfbericht: Einzelposten gegen Eröffnungsbilanz (ohne Korrektur)",
)
async def history_open_item_balance_check(
    request: Request,
    ledger_id: uuid.UUID,
    opening_balance_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> dict[str, Any]:
    """Compares item sums with the opening balance per group (sign rule: A-Q08-01). Report
    only: nothing is corrected, posted or released."""
    async with tenant_tx(request, principal) as session:
        report = await w3_reports.open_item_balance_check(session, ledger_id, opening_balance_id)
        if report is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return report


class HistoryJournalCandidateOut(BaseModel):
    journal_entry_id: uuid.UUID
    source_entry_id: str
    booking_date: date
    day_difference: int
    amount: Decimal
    text: str | None


@router.get(
    "/bank-links/{bank_transaction_id}/candidates",
    summary="Vorschlag: Journalbuchungen zu einem historischen Bankumsatz (Kandidatenliste)",
    dependencies=[Depends(strict_query)],
)
async def history_bank_link_candidates(
    request: Request,
    bank_transaction_id: uuid.UUID,
    tolerance_days: int = Query(default=3, ge=0, le=10),
    limit: int = Query(default=10, ge=1, le=50),
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> list[HistoryJournalCandidateOut]:
    """Candidates by date and amount; nothing is assigned automatically."""
    from mhvp.banking.models import BankTransaction

    async with tenant_tx(request, principal) as session:
        tx = await session.get(BankTransaction, bank_transaction_id)
        if tx is None or not (tx.raw or {}).get("migration", {}).get("history"):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        from mhvp.banking.property_scope import ensure_account_visible

        await ensure_account_visible(session, tx.property_bank_account_id)  # Y01, M2-02
        rows = await w3_reports.journal_candidates(session, tx, tolerance_days, limit)
        return [HistoryJournalCandidateOut.model_validate(r) for r in rows]


# GAJ-501 (AM09): filed historical statements and resolutions with check report. Read only.


class HistoryStatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    property_id: uuid.UUID
    kind: str
    period_start: date
    period_end: date
    version: int
    unit_number: str
    unit_id: uuid.UUID | None
    recipient: str | None
    result_amount: Decimal | None
    sent_on: date | None
    resolution_ref: str | None
    document_ref: str | None
    note: str | None


class HistoryResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    property_id: uuid.UUID
    resolved_on: date
    item_number: str
    reference: str | None
    title: str
    wording: str | None
    result: str
    form: str
    note: str | None


class HistoryCheckFindingOut(BaseModel):
    property_id: uuid.UUID
    property_number: str
    entity: str
    entity_id: uuid.UUID
    code: str
    message: str


class HistoryCheckPropertyOut(BaseModel):
    property_id: uuid.UUID
    property_number: str
    statements: int
    resolutions: int
    findings: int


class HistoryCheckTotalsOut(BaseModel):
    statements: int
    resolutions: int
    findings: int


class HistoryCheckOut(BaseModel):
    totals: HistoryCheckTotalsOut
    properties: list[HistoryCheckPropertyOut]
    findings: list[HistoryCheckFindingOut]


@router.get(
    "/statements",
    summary="Übernommene Altabrechnungen je Version (nur Ablage)",
    dependencies=[Depends(strict_query)],
    response_model=list[HistoryStatementOut],
)
async def history_statements(
    request: Request,
    property_id: uuid.UUID | None = None,
    kind: str | None = Query(
        default=None, pattern="^(hoa_annual|hoa_budget|operating_costs|heating_costs|other)$"
    ),
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> list[HistoryStatementOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MigratedStatement)
        if property_id:
            query = query.where(MigratedStatement.property_id == property_id)
        if kind:
            query = query.where(MigratedStatement.kind == kind)
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            query = query.where(MigratedStatement.property_id.in_(allowed))
        rows = await session.scalars(
            query.order_by(
                MigratedStatement.period_end.desc(),
                MigratedStatement.kind,
                MigratedStatement.unit_number,
                MigratedStatement.version,
            )
            .offset(offset)
            .limit(limit)
        )
        return [HistoryStatementOut.model_validate(r) for r in rows.all()]


@router.get(
    "/resolutions",
    summary="Übernommene Beschlusssammlung (nur Ablage)",
    dependencies=[Depends(strict_query)],
    response_model=list[HistoryResolutionOut],
)
async def history_resolutions(
    request: Request,
    property_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> list[HistoryResolutionOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MigratedResolution)
        if property_id:
            query = query.where(MigratedResolution.property_id == property_id)
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            query = query.where(MigratedResolution.property_id.in_(allowed))
        rows = await session.scalars(
            query.order_by(MigratedResolution.resolved_on.desc(), MigratedResolution.item_number)
            .offset(offset)
            .limit(limit)
        )
        return [HistoryResolutionOut.model_validate(r) for r in rows.all()]


@router.get(
    "/statements/check",
    summary="Prüfbericht Altabrechnungen und Beschlüsse (ohne Korrektur)",
    dependencies=[Depends(strict_query)],
    response_model=HistoryCheckOut,
)
async def history_statement_check(
    request: Request,
    property_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> HistoryCheckOut:
    async with tenant_tx(request, principal) as session:
        report = await statement_reports.check_report(
            session, property_id, session_allowed_property_ids(session)
        )
        return HistoryCheckOut.model_validate(report)
