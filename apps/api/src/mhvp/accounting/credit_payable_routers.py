"""Payables from statement credits (/api/v1/accounting/credit-payables, AE22, rule AE22).

Rights: ``accounting:read`` to look, ``accounting:create`` to propose and to create a draft
payment order, ``accounting:approve`` to release and to withdraw, ``tenant_settings:update``
for the switch. Release needs G3, the payment order G2 and G3, the reversal of a posted
reclass entry G1. Nothing here posts on its own, approves an order or produces a payment file.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import credit_payables as cp
from mhvp.accounting import services as acc_services
from mhvp.accounting.credit_payable_models import MODES, SOURCE_TYPES, STATUSES, CreditPayable
from mhvp.accounting.models import Ledger
from mhvp.banking.routers import OrderOut, _order_out
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open_for
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/accounting/credit-payables", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
SETTINGS = require_permission("tenant_settings:update")
ACCOUNT_NUMBER = r"^[0-9]{6}$"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreditPayableSettingIn(_In):
    mode: str | None = Field(default=None, pattern="^(" + "|".join(MODES) + ")$")
    four_eyes_required: bool | None = None
    creditor_account_number: str | None = Field(default=None, pattern=ACCOUNT_NUMBER)
    owner_debit_account_number: str | None = Field(default=None, pattern=ACCOUNT_NUMBER)
    deposit_debit_account_number: str | None = Field(default=None, pattern=ACCOUNT_NUMBER)


class CreditPayableSettingOut(BaseModel):
    mode: str
    four_eyes_required: bool
    creditor_account_number: str | None
    owner_debit_account_number: str | None
    deposit_debit_account_number: str | None
    modes: list[str]
    decision_ref: str
    note: str


class CreditPayableCandidateOut(BaseModel):
    source_type: str
    source_id: uuid.UUID
    contract_id: uuid.UUID | None
    ledger_id: uuid.UUID
    amount: Decimal
    label: str
    reference_date: date | None
    source_entry_id: uuid.UUID | None
    payout_reason: str


class CreditPayableIn(_In):
    source_type: str = Field(pattern="^(" + "|".join(SOURCE_TYPES) + ")$")
    source_id: uuid.UUID
    contract_id: uuid.UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    note: str | None = Field(default=None, max_length=2000)


class CreditPayableReleaseIn(_In):
    booking_date: date | None = None


class CreditPayableWithdrawIn(_In):
    reason: str = Field(min_length=3, max_length=500)
    booking_date: date | None = None


class CreditPayableOrderIn(_In):
    contact_bank_account_id: uuid.UUID
    property_bank_account_id: uuid.UUID
    execution_date: date
    purpose: str | None = Field(default=None, min_length=1, max_length=140)


class CreditPayableOut(BaseModel):
    id: uuid.UUID
    ledger_id: uuid.UUID
    source_type: str
    source_id: uuid.UUID
    contract_id: uuid.UUID | None
    source_entry_id: uuid.UUID | None
    amount: Decimal
    variant: str
    status: str
    state: str
    payout_reason: str
    open_item_id: uuid.UUID | None
    remaining: Decimal | None
    reclass_entry_id: uuid.UUID | None
    reclass_entry_status: str | None
    reversal_entry_id: uuid.UUID | None
    payment_order_id: uuid.UUID | None
    payment_order_status: str | None
    proposed_by: uuid.UUID | None
    released_by: uuid.UUID | None
    released_at: datetime | None
    withdrawn_by: uuid.UUID | None
    withdrawn_at: datetime | None
    withdraw_reason: str | None
    note: str | None
    warnings: list[dict[str, Any]]
    created_at: datetime


async def _out(session: Any, row: CreditPayable) -> CreditPayableOut:
    current = await cp.state(session, row)
    return CreditPayableOut(
        id=row.id,
        ledger_id=row.ledger_id,
        source_type=row.source_type,
        source_id=row.source_id,
        contract_id=row.contract_id,
        source_entry_id=row.source_entry_id,
        amount=row.amount,
        variant=row.variant,
        status=row.status,
        state=current["state"],
        payout_reason=row.payout_reason,
        open_item_id=current["open_item_id"],
        remaining=current["remaining"],
        reclass_entry_id=row.reclass_entry_id,
        reclass_entry_status=current["reclass_entry_status"],
        reversal_entry_id=row.reversal_entry_id,
        payment_order_id=current["payment_order_id"],
        payment_order_status=current["payment_order_status"],
        proposed_by=row.created_by,
        released_by=row.released_by,
        released_at=row.released_at,
        withdrawn_by=row.withdrawn_by,
        withdrawn_at=row.withdrawn_at,
        withdraw_reason=row.withdraw_reason,
        note=row.note,
        warnings=list(row.warnings or []),
        created_at=row.created_at,
    )


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID) -> Ledger:
    ledger = await session.get(Ledger, ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return ledger


async def _row(session: AsyncSession, row_id: uuid.UUID, *, lock: bool = False) -> CreditPayable:
    query = select(CreditPayable).where(CreditPayable.id == row_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    await _ledger(session, row.ledger_id)
    return row


async def _gate(
    request: Request, principal: TenantPrincipal, gate: ReleaseGate, ledger: Ledger
) -> None:
    await ensure_release_gate_open_for(
        gate,
        principal.tenant_id,
        request.app.state.release_gate_resolver,
        property_id=ledger.property_id,
        legal_entity_id=ledger.legal_entity_id,
    )


async def _event(
    session: Any, principal: TenantPrincipal, row: CreditPayable, kind: str, **payload: Any
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=f"credit_payable.{kind}",
        entity_type="credit_payable",
        entity_id=row.id,
        actor_user_id=principal.user_id,
        payload={"source_type": row.source_type, "amount": str(row.amount), **payload},
    )


@router.get(
    "/settings",
    summary="Schalter Verbindlichkeitsposten aus Guthaben (Q01-01)",
    dependencies=[Depends(strict_query)],
)
async def get_settings(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> CreditPayableSettingOut:
    async with tenant_tx(request, principal) as session:
        return CreditPayableSettingOut(**cp.setting_out(await cp.get_setting(session)))


@router.put("/settings", summary="Schalter Verbindlichkeitsposten aus Guthaben ändern")
async def put_settings(
    body: CreditPayableSettingIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> CreditPayableSettingOut:
    changes = body.model_dump(exclude_unset=True)
    if changes.get("mode") is None:
        changes.pop("mode", None)
    if changes.get("four_eyes_required") is None:
        changes.pop("four_eyes_required", None)
    async with tenant_tx(request, principal) as session:
        row = await cp.update_setting(session, principal.tenant_id, principal.user_id, changes)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="credit_payable.settings_changed",
            entity_type="tenant",
            entity_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            changes=dict(changes),
        )
        return CreditPayableSettingOut(**cp.setting_out(row))


@router.get(
    "/candidates",
    summary="Auszahlbare Guthaben aus Abrechnungen (nur Anzeige)",
    dependencies=[Depends(strict_query)],
)
async def list_candidates(
    request: Request,
    ledger_id: uuid.UUID | None = Query(default=None),
    source_type: str | None = Query(default=None, pattern="^(" + "|".join(SOURCE_TYPES) + ")$"),
    principal: TenantPrincipal = Depends(READ),
) -> list[CreditPayableCandidateOut]:
    async with tenant_tx(request, principal) as session:
        if ledger_id is not None:
            await _ledger(session, ledger_id)
        found = await cp.candidates(session, ledger_id=ledger_id, source_type=source_type)
        out = []
        for cand in found:
            ledger = await session.get(Ledger, cand.ledger_id)
            if ledger is None:  # pragma: no cover - FK
                continue
            try:
                ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
            except ProblemError:
                continue
            out.append(CreditPayableCandidateOut(**cand.as_json()))
        return out


@router.get("", summary="Verbindlichkeitsposten aus Guthaben", dependencies=[Depends(strict_query)])
async def list_rows(
    request: Request,
    ledger_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(" + "|".join(STATUSES) + ")$"),
    principal: TenantPrincipal = Depends(READ),
) -> list[CreditPayableOut]:
    async with tenant_tx(request, principal) as session:
        query = select(CreditPayable).order_by(CreditPayable.created_at.desc()).limit(500)
        if ledger_id is not None:
            await _ledger(session, ledger_id)
            query = query.where(CreditPayable.ledger_id == ledger_id)
        if status is not None:
            query = query.where(CreditPayable.status == status)
        out = []
        for row in await session.scalars(query):
            ledger = await session.get(Ledger, row.ledger_id)
            if ledger is None:  # pragma: no cover - FK
                continue
            try:
                ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
            except ProblemError:
                continue
            out.append(await _out(session, row))
        return out


@router.post("", status_code=201, summary="Verbindlichkeitsposten aus Guthaben vorschlagen")
async def create_row(
    body: CreditPayableIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> CreditPayableOut:
    async with tenant_tx(request, principal) as session:
        row = await cp.propose(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            source_type=body.source_type,
            source_id=body.source_id,
            contract_id=body.contract_id,
            amount=body.amount,
            note=body.note,
        )
        await _ledger(session, row.ledger_id)
        await _event(session, principal, row, "proposed", variant=row.variant)
        return await _out(session, row)


@router.get("/{row_id}", summary="Verbindlichkeitsposten aus Guthaben")
async def get_row(
    row_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> CreditPayableOut:
    async with tenant_tx(request, principal) as session:
        return await _out(session, await _row(session, row_id))


class CreditPayableAccountOptionOut(BaseModel):
    id: uuid.UUID
    holder: str | None
    iban_suffix: str


class CreditPayableOptionsOut(BaseModel):
    payees: list[CreditPayableAccountOptionOut]
    bank_accounts: list[CreditPayableAccountOptionOut]


@router.get(
    "/{row_id}/payout-options",
    summary="Auswahl Empfänger- und Auftraggeberkonto",
    dependencies=[Depends(strict_query)],
)
async def payout_options(
    row_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> CreditPayableOptionsOut:
    async with tenant_tx(request, principal) as session:
        return CreditPayableOptionsOut(
            **await cp.payout_options(session, await _row(session, row_id))
        )


@router.post("/{row_id}/release", summary="Freigeben (Vier Augen, G3)")
async def release_row(
    row_id: uuid.UUID,
    body: CreditPayableReleaseIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> CreditPayableOut:
    async with tenant_tx(request, principal) as session:
        row = await _row(session, row_id, lock=True)
        await _gate(request, principal, ReleaseGate.G3, await _ledger(session, row.ledger_id))
        row = await cp.release(
            session, row, user_id=principal.user_id, booking_date=body.booking_date or local_today()
        )
        await _event(session, principal, row, "released", variant=row.variant)
        return await _out(session, row)


@router.post(
    "/{row_id}/payment-order",
    status_code=201,
    summary="Zahlungsauftrag ohne Rechnung aus dem Posten (Entwurf, G2 und G3)",
)
async def create_order(
    row_id: uuid.UUID,
    body: CreditPayableOrderIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> OrderOut:
    async with tenant_tx(request, principal) as session:
        row = await _row(session, row_id, lock=True)
        ledger = await _ledger(session, row.ledger_id)
        await _gate(request, principal, ReleaseGate.G3, ledger)
        await _gate(request, principal, ReleaseGate.G2, ledger)
        order = await cp.payout_order(
            session,
            row,
            contact_bank_account_id=body.contact_bank_account_id,
            bank_account_id=body.property_bank_account_id,
            execution_date=body.execution_date,
            purpose=body.purpose,
            user_id=principal.user_id,
        )
        await _event(session, principal, row, "order_created", payment_order_id=str(order.id))
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="payment_order.payout_created",
            entity_type="payment_order",
            entity_id=order.id,
            actor_user_id=principal.user_id,
            payload={"reason": row.payout_reason, "amount": str(order.amount)},
        )
        return await _order_out(session, order)


@router.post("/{row_id}/withdraw", summary="Zurücknehmen oder stornieren (Storno-Pfad)")
async def withdraw_row(
    row_id: uuid.UUID,
    body: CreditPayableWithdrawIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> CreditPayableOut:
    async with tenant_tx(request, principal) as session:
        row = await _row(session, row_id, lock=True)
        ledger = await _ledger(session, row.ledger_id)

        async def ensure_g1() -> None:
            await _gate(request, principal, ReleaseGate.G1, ledger)

        row = await cp.withdraw(
            session,
            row,
            user_id=principal.user_id,
            reason=body.reason,
            booking_date=body.booking_date
            or acc_services.default_reversal_date(ledger, local_today()),
            ensure_g1=ensure_g1,
        )
        await _event(
            session,
            principal,
            row,
            "withdrawn",
            reason=body.reason,
            reversal_entry_id=str(row.reversal_entry_id) if row.reversal_entry_id else None,
        )
        return await _out(session, row)
