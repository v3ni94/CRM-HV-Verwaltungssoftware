"""Creditors and recurring invoice plans (M14 Kreditoren, M14-01, M14-08).

Creditor accounts (7.2: 070000 to 079999) are still created on demand by the first posting
(``mhvp.accounting.invoices.creditor_account``); these endpoints read them: list with balance
and open payables, open items and the account statement per creditor. Recurring plans get
list, read, change, end and delete; generating a plan invoice stays a draft (no posting).
Mounted under ``/accounting`` by ``mhvp.accounting.routers``.
"""

import calendar
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as svc
from mhvp.accounting.models import (
    AccountCategory,
    EntryStatus,
    Invoice,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
    RecurringInvoicePlan,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.pagination import PAGE_HEADERS, paginate
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

router = APIRouter(tags=["Buchhaltung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
UPDATE = require_permission("accounting:update")
CENT = Decimal("0.01")
ZERO = Decimal("0.00")


# Helpers -------------------------------------------------------------------------------------


def add_months(day: date, months: int, anchor_day: int) -> date:
    """Month arithmetic with month end handling: day 31 becomes the last day of a short
    month and returns to 31 in the next long month (anchor day of the plan)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def next_due(plan: RecurringInvoicePlan) -> date:
    return add_months(plan.next_due, plan.interval_months, plan.anchor_day or plan.start_date.day)


def split_gross(gross: Decimal, vat_percent: Decimal) -> tuple[Decimal, Decimal]:
    """Net and VAT of a plan amount entered as gross; VAT is net times rate, rounded half up,
    and the net is the rest so that net plus VAT is exactly the gross (B06)."""
    if not vat_percent:
        return gross, ZERO
    net = (gross * 100 / (100 + vat_percent)).quantize(CENT, rounding=ROUND_HALF_UP)
    return net, gross - net


async def check_auto_post(session: AsyncSession, requested: bool) -> None:
    """GA03-07: ``auto_post`` may only be set while the tenant released automatic posting
    (6.9.4, 7.4). The flag is a request: postings still need released G1 and an active rule,
    and plan generation keeps creating drafts (OPEN_QUESTIONS AA10-01)."""
    if not requested:
        return
    from mhvp.platform.models import TenantSettings

    enabled = await session.scalar(select(TenantSettings.auto_posting_enabled))
    if not enabled:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Automatische Buchung ist für den Mandanten nicht freigeschaltet.",
        )


async def auto_post_state(
    session: AsyncSession, request: Request, principal: TenantPrincipal, requested: bool
) -> str:
    """GA03-07: effect of the plan flag in a generation run. ``draft_only`` (flag off),
    ``locked_g1`` (G1 closed), ``locked_switch`` (automatic switch off) or
    ``draft_pending_rule`` (both open: still a draft, a posting needs an active 7.4 rule)."""
    if not requested:
        return "draft_only"
    from mhvp.core.release_gates import (
        ClosedReleaseGateResolver,
        ReleaseGate,
        ReleaseGateClosedError,
        ensure_release_gate_open,
    )
    from mhvp.platform.models import TenantSettings

    resolver = getattr(request.app.state, "release_gate_resolver", ClosedReleaseGateResolver())
    try:
        await ensure_release_gate_open(ReleaseGate.G1, principal.tenant_id, resolver)
    except ReleaseGateClosedError:
        return "locked_g1"
    if not await session.scalar(select(TenantSettings.auto_posting_enabled)):
        return "locked_switch"
    return "draft_pending_rule"


async def check_contract(
    session: AsyncSession, contract_id: uuid.UUID | None, provider: uuid.UUID | None
) -> None:
    """The linked service contract belongs to the provider of the plan (M14-01)."""
    if contract_id is None:
        return
    from mhvp.contracts.service_contracts import ServiceContract

    contract = await session.get(ServiceContract, contract_id)
    if contract is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vertrag nicht gefunden.")
    if provider is not None and contract.provider_contact_id != provider:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Der Vertrag gehört zu einem anderen Dienstleister."
        )


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID) -> Ledger:
    ledger = await session.get(Ledger, ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return ledger


async def _creditor(session: AsyncSession, ledger: Ledger, account_id: uuid.UUID) -> LedgerAccount:
    account = await session.get(LedgerAccount, account_id)
    if (
        account is None
        or account.ledger_id != ledger.id
        or account.category is not AccountCategory.CREDITOR
    ):
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return account


# Creditors -----------------------------------------------------------------------------------


class CreditorOut(BaseModel):
    account_id: uuid.UUID
    number: str
    name: str
    contact_id: uuid.UUID | None
    balance: Decimal = Field(description="Haben minus Soll: Verbindlichkeit gegenüber dem Kreditor")
    open_items: int
    open_amount: Decimal
    invoices: int


@router.get(
    "/ledgers/{ledger_id}/creditors",
    summary="Kreditoren des Buchungskreises mit Saldo und offenen Posten",
    dependencies=[Depends(strict_query)],
)
async def list_creditors(
    ledger_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[CreditorOut]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        day = as_of or local_today()
        accounts = (
            await session.scalars(
                select(LedgerAccount)
                .where(
                    LedgerAccount.ledger_id == ledger.id,
                    LedgerAccount.category == AccountCategory.CREDITOR,
                )
                .order_by(LedgerAccount.number)
            )
        ).all()
        sums = {
            row[0]: (Decimal(row[1]), Decimal(row[2]))
            for row in (
                await session.execute(
                    select(
                        JournalLine.account_id,
                        func.coalesce(func.sum(JournalLine.debit), 0),
                        func.coalesce(func.sum(JournalLine.credit), 0),
                    )
                    .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                    .where(
                        JournalEntry.ledger_id == ledger.id,
                        JournalEntry.status == EntryStatus.POSTED,
                        JournalEntry.booking_date <= day,
                        JournalLine.account_id.in_([a.id for a in accounts]),
                    )
                    .group_by(JournalLine.account_id)
                )
            ).all()
        }
        items: dict[uuid.UUID, list[Decimal]] = {}
        for item in await svc.open_items(session, ledger, day):
            items.setdefault(item["account_id"], []).append(item["remaining"])
        counts: dict[uuid.UUID | None, int] = {
            row[0]: int(row[1])
            for row in (
                await session.execute(
                    select(Invoice.creditor_account_id, func.count())
                    .where(Invoice.ledger_id == ledger.id, Invoice.creditor_account_id.is_not(None))
                    .group_by(Invoice.creditor_account_id)
                )
            ).all()
        }
        out = []
        for a in accounts:
            debit, credit = sums.get(a.id, (ZERO, ZERO))
            rest = items.get(a.id, [])
            out.append(
                CreditorOut(
                    account_id=a.id,
                    number=a.number,
                    name=a.name,
                    contact_id=a.contact_id,
                    balance=credit - debit,
                    open_items=len(rest),
                    open_amount=sum(rest, ZERO),
                    invoices=int(counts.get(a.id, 0)),
                )
            )
        return out


@router.get(
    "/ledgers/{ledger_id}/creditors/{account_id}/open-items",
    summary="Offene Posten eines Kreditors",
    dependencies=[Depends(strict_query)],
)
async def creditor_open_items(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        account = await _creditor(session, ledger, account_id)
        return await svc.open_items(session, ledger, as_of or local_today(), account.id)


@router.get(
    "/ledgers/{ledger_id}/creditors/{account_id}/statement",
    summary="Kreditorenkonto-Auszug (Kontenblatt)",
)
async def creditor_statement(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    start: date | None = None,
    end: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        account = await _creditor(session, ledger, account_id)
        until = end or local_today()
        since = start or date(until.year, 1, 1)
        if since > until:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Beginn liegt nach dem Ende.")
        return await svc.account_sheet(session, account, since, until)


# Recurring invoice plans ---------------------------------------------------------------------


class RecurringPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ledger_id: uuid.UUID
    provider_contact_id: uuid.UUID
    account_id: uuid.UUID
    gross: Decimal
    vat_percent: Decimal
    interval_months: int
    start_date: date
    end_date: date | None
    next_due: date
    anchor_day: int | None
    text: str
    order_reference: str | None
    service_contract_id: uuid.UUID | None
    ended_at: date | None
    auto_post: bool = False


class RecurringPlanPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID | None = None
    gross: Decimal | None = Field(default=None, gt=0)
    vat_percent: Decimal | None = Field(default=None, ge=0, le=100)
    interval_months: int | None = Field(default=None, ge=1, le=12)
    end_date: date | None = None
    text: str | None = Field(default=None, min_length=1, max_length=300)
    order_reference: str | None = Field(default=None, max_length=100)
    service_contract_id: uuid.UUID | None = None
    auto_post: bool | None = None


class RecurringPlanEndIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ended_at: date
    reason: str = Field(min_length=3, max_length=1000)


async def _plan(session: AsyncSession, plan_id: uuid.UUID) -> RecurringInvoicePlan:
    plan = await session.get(RecurringInvoicePlan, plan_id, with_for_update=True)
    if plan is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    await _ledger(session, plan.ledger_id)
    return plan


async def _generated(session: AsyncSession, plan: RecurringInvoicePlan) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(Invoice).where(Invoice.recurring_plan_id == plan.id)
        )
        or 0
    )


@router.get(
    "/recurring-invoices",
    summary="Rechnungspläne",
    responses=PAGE_HEADERS,
    dependencies=[Depends(strict_query)],
)
async def list_plans(
    request: Request,
    response: Response,
    ledger_id: uuid.UUID | None = None,
    active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=500),
    principal: TenantPrincipal = Depends(READ),
) -> list[RecurringPlanOut]:
    async with tenant_tx(request, principal) as session:
        query = select(RecurringInvoicePlan).order_by(
            RecurringInvoicePlan.next_due, RecurringInvoicePlan.id
        )
        if ledger_id is not None:
            await _ledger(session, ledger_id)
            query = query.where(RecurringInvoicePlan.ledger_id == ledger_id)
        if active is True:
            query = query.where(RecurringInvoicePlan.ended_at.is_(None))
        elif active is False:
            query = query.where(RecurringInvoicePlan.ended_at.is_not(None))
        rows = await paginate(session, query, response, page=page, page_size=page_size, limit=500)
        return [RecurringPlanOut.model_validate(r) for r in rows]


@router.get("/recurring-invoices/{plan_id}", summary="Rechnungsplan lesen")
async def get_plan(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> RecurringPlanOut:
    async with tenant_tx(request, principal) as session:
        plan = await session.get(RecurringInvoicePlan, plan_id)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _ledger(session, plan.ledger_id)
        return RecurringPlanOut.model_validate(plan)


@router.patch("/recurring-invoices/{plan_id}", summary="Rechnungsplan ändern")
async def update_plan(
    plan_id: uuid.UUID,
    body: RecurringPlanPatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> RecurringPlanOut:
    """Changes apply to invoices generated afterwards; generated drafts stay as they are."""
    async with tenant_tx(request, principal) as session:
        plan = await _plan(session, plan_id)
        if plan.ended_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Rechnungsplan ist beendet.")
        changes = body.model_dump(exclude_unset=True)
        if "account_id" in changes and changes["account_id"] is not None:
            account = await session.get(LedgerAccount, changes["account_id"])
            if account is None or account.ledger_id != plan.ledger_id:
                raise ProblemError(ErrorCodes.ACC_WRONG_ENTITY)
        if changes.get("service_contract_id") is not None:
            await check_contract(session, changes["service_contract_id"], plan.provider_contact_id)
        if "auto_post" in changes:
            await check_auto_post(session, bool(changes["auto_post"]))
        if changes.get("end_date") is not None and changes["end_date"] < plan.start_date:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ende liegt vor dem Beginn.")
        for key, value in changes.items():
            if key in (
                "account_id",
                "gross",
                "vat_percent",
                "interval_months",
                "text",
                "auto_post",
            ) and (value is None):
                continue
            setattr(plan, key, value)
        plan.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="recurring_invoice_plan.updated",
            entity_type="recurring_invoice_plan",
            entity_id=plan.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(changes)},
        )
        await session.flush()
        return RecurringPlanOut.model_validate(plan)


@router.post("/recurring-invoices/{plan_id}/end", summary="Rechnungsplan beenden")
async def end_plan(
    plan_id: uuid.UUID,
    body: RecurringPlanEndIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> RecurringPlanOut:
    async with tenant_tx(request, principal) as session:
        plan = await _plan(session, plan_id)
        if plan.ended_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Rechnungsplan ist bereits beendet.")
        if body.ended_at < plan.start_date:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ende liegt vor dem Beginn.")
        plan.ended_at = body.ended_at
        if plan.end_date is None or plan.end_date > body.ended_at:
            plan.end_date = body.ended_at
        plan.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="recurring_invoice_plan.ended",
            entity_type="recurring_invoice_plan",
            entity_id=plan.id,
            actor_user_id=principal.user_id,
            payload={"ended_at": body.ended_at.isoformat(), "reason": body.reason},
        )
        await session.flush()
        return RecurringPlanOut.model_validate(plan)


@router.delete(
    "/recurring-invoices/{plan_id}", status_code=204, summary="Rechnungsplan löschen (unbenutzt)"
)
async def delete_plan(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> Response:
    """Only a plan that never generated an invoice is deleted; otherwise it is ended."""
    async with tenant_tx(request, principal) as session:
        plan = await _plan(session, plan_id)
        if await _generated(session, plan):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Aus dem Plan wurden Rechnungen erzeugt: Plan beenden statt löschen.",
            )
        await session.delete(plan)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="recurring_invoice_plan.deleted",
            entity_type="recurring_invoice_plan",
            entity_id=plan_id,
            actor_user_id=principal.user_id,
            payload={},
        )
        await session.flush()
    return Response(status_code=204)
