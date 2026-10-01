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

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.imports import w3_reports
from mhvp.imports.history_models import MigratedBankLink, MigratedOpenItem, MigratedTicket

router = APIRouter(prefix="/imports/immoware24/history", tags=["Import Immoware24"])
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


@router.get("/tickets", summary="Historische Tickets (nur lesend)")
async def history_tickets(
    request: Request,
    property_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ_TICKETS),
) -> list[HistoryTicketOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MigratedTicket)
        if property_id:
            query = query.where(MigratedTicket.property_id == property_id)
        rows = await session.scalars(
            query.order_by(MigratedTicket.created_on.desc(), MigratedTicket.source_ticket_id)
            .offset(offset)
            .limit(limit)
        )
        return [HistoryTicketOut.model_validate(r) for r in rows.all()]


@router.get("/open-items", summary="Übernommene Einzelposten der Altdaten")
async def history_open_items(
    request: Request,
    ledger_id: uuid.UUID | None = None,
    kind: str | None = Query(
        default=None, pattern="^(receivable|credit|deposit|reserve|loan|special_levy)$"
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> list[HistoryOpenItemOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MigratedOpenItem)
        if ledger_id:
            query = query.where(MigratedOpenItem.ledger_id == ledger_id)
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


@router.get("/bank-links", summary="Zuordnung historischer Bankumsätze zum Journal")
async def history_bank_links(
    request: Request,
    open_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ_ACCOUNTING),
) -> list[HistoryBankLinkOut]:
    async with tenant_tx(request, principal) as session:
        query = select(MigratedBankLink)
        if open_only:
            query = query.where(MigratedBankLink.journal_entry_id.is_(None))
        rows = await session.scalars(
            query.order_by(MigratedBankLink.created_at, MigratedBankLink.id)
            .offset(offset)
            .limit(limit)
        )
        return [HistoryBankLinkOut.model_validate(r) for r in rows.all()]
