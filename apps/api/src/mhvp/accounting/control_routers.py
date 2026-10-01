"""Approval decisions and maintained open item remainders (S69-02, S69-04).

Mounted under ``/accounting`` by ``mhvp.accounting.routers``. Read endpoints plus a manual
refresh of the read copy; nothing here posts, pays or approves.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import approval_decisions, open_item_balances
from mhvp.accounting.models import Invoice, Ledger
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

router = APIRouter(tags=["Buchhaltung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")


class AccApprovalDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    subject_type: str
    subject_id: uuid.UUID
    step: str
    user_id: uuid.UUID
    subject_snapshot_hash: str
    status: str
    decided_at: datetime
    invalidated_at: datetime | None
    invalidation_reason: str | None
    legacy_ref_id: uuid.UUID | None
    warnings: list[str]


class AccOpenItemBalanceRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    open_item_id: uuid.UUID
    account_id: uuid.UUID
    kind: str
    due_date: date | None
    amount: Decimal
    remaining: Decimal
    contract_id: uuid.UUID | None
    source: str
    refreshed_at: datetime


class AccOpenItemBalanceOut(BaseModel):
    ledger_id: uuid.UUID
    as_of: date | None
    items: list[AccOpenItemBalanceRow]
    total_receivable: Decimal
    total_payable: Decimal


class AccOpenItemBalanceRefreshIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: date | None = None


async def _subject(session: AsyncSession, subject_type: str, subject_id: uuid.UUID) -> None:
    """The subject must be visible in the tenant (RLS) and legal entity scope."""
    if subject_type == "invoice":
        invoice = await session.get(Invoice, subject_id)
        ledger_id = invoice.ledger_id if invoice else None
    else:
        from mhvp.banking.models import PaymentOrder

        order = await session.get(PaymentOrder, subject_id)
        ledger_id = order.ledger_id if order else None
    ledger = await session.get(Ledger, ledger_id) if ledger_id else None
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)


@router.get(
    "/approval-decisions",
    summary="Freigabeentscheidungen eines Vorgangs (Zahlung, Rechnung)",
    dependencies=[Depends(strict_query)],
)
async def list_approval_decisions(
    request: Request,
    subject_type: str = Query(pattern="^(payment_order|invoice)$"),
    subject_id: uuid.UUID = Query(),
    principal: TenantPrincipal = Depends(READ),
) -> list[AccApprovalDecisionOut]:
    async with tenant_tx(request, principal) as session:
        await _subject(session, subject_type, subject_id)
        rows = await approval_decisions.decisions(session, subject_type, subject_id)
        return [AccApprovalDecisionOut.model_validate(r) for r in rows]


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID) -> Ledger:
    ledger = await session.get(Ledger, ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return ledger


def _out(ledger_id: uuid.UUID, as_of: date | None, rows: list) -> AccOpenItemBalanceOut:  # type: ignore[type-arg]
    items = [AccOpenItemBalanceRow.model_validate(r) for r in rows]
    return AccOpenItemBalanceOut(
        ledger_id=ledger_id,
        as_of=as_of,
        items=items,
        total_receivable=sum(
            (i.remaining for i in items if i.kind == "receivable"), Decimal("0.00")
        ),
        total_payable=sum((i.remaining for i in items if i.kind == "payable"), Decimal("0.00")),
    )


@router.get(
    "/ledgers/{ledger_id}/open-item-balances",
    summary="Offene Posten zum Stichtag (gepflegte Lesekopie)",
    dependencies=[Depends(strict_query)],
)
async def get_open_item_balances(
    ledger_id: uuid.UUID,
    request: Request,
    as_of: date | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> AccOpenItemBalanceOut:
    async with tenant_tx(request, principal) as session:
        await _ledger(session, ledger_id)
        day, rows = await open_item_balances.rows_of(session, ledger_id, as_of)
        return _out(ledger_id, day, rows)


@router.post(
    "/ledgers/{ledger_id}/open-item-balances/refresh",
    summary="Offene Posten zum Stichtag neu berechnen",
)
async def refresh_open_item_balances(
    ledger_id: uuid.UUID,
    body: AccOpenItemBalanceRefreshIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> AccOpenItemBalanceOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        day = body.as_of or local_today()
        await open_item_balances.refresh(session, ledger, day, source="manual")
        _, rows = await open_item_balances.rows_of(session, ledger_id, day)
        return _out(ledger_id, day, rows)
