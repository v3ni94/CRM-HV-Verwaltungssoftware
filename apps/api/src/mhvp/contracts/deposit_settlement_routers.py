"""Deposit settlement endpoints (rule M5-02, operator decision 26.09.2026).

- ``/deposit-interest-rates``: reference interest rate per year, maintained by the tenant
  (read with contracts:read, write with tenant_settings:update). No rate is fetched or invented.
- ``/deposits/{id}/settlements``: preview, create and list settlement drafts (records only).
- ``/deposit-settlements/{id}/release``: behind release gate G3; the gate is closed by default
  for every tenant, so the settlement stays a draft (no receivable, no payment).
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Self

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from mhvp.contracts import deposit_settlement as ds
from mhvp.contracts.models import Contract, Deposit, DepositMovement, DepositMovementKind
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open

router = APIRouter(tags=["Verträge"])
READ = require_permission("contracts:read")
UPDATE = require_permission("contracts:update")
SETTINGS = require_permission("tenant_settings:update")

Money = Decimal


def _nf() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


def _invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


# Schemas ---------------------------------------------------------------------------------


class ReferenceRateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rate: Decimal = Field(ge=0, le=100, max_digits=8, decimal_places=5)
    note: str | None = Field(default=None, max_length=500)


class ReferenceRateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    year: int
    rate: Decimal
    note: str | None


class InterestYearIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int = Field(ge=1900, le=2200)
    amount: Money = Field(ge=0, max_digits=14, decimal_places=2)


class DeductionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=300)
    amount: Money = Field(gt=0, max_digits=14, decimal_places=2)


class DepositSettlementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    settlement_date: date
    interest_mode: ds.DepositInterestMode
    interest_years: list[InterestYearIn] = Field(default_factory=list, max_length=100)
    deductions: list[DeductionIn] = Field(default_factory=list, max_length=100)
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _check(self) -> Self:
        years = [y.year for y in self.interest_years]
        if len(years) != len(set(years)):
            raise ValueError("Jedes Jahr darf nur einmal angegeben werden.")
        if self.interest_years and self.interest_mode is not ds.DepositInterestMode.INDIVIDUAL:
            raise ValueError("Einzelzinsen je Jahr gibt es nur bei der Zinsart individuell.")
        return self


class InterestYearOut(BaseModel):
    year: int
    rate: Decimal | None
    days: int
    amount: Money


class DeductionOut(BaseModel):
    label: str
    amount: Money


class DepositSettlementOut(BaseModel):
    id: uuid.UUID | None = None
    deposit_id: uuid.UUID
    status: ds.DepositSettlementStatus = ds.DepositSettlementStatus.DRAFT
    settlement_date: date
    interest_mode: ds.DepositInterestMode
    interest_years: list[InterestYearOut]
    deductions: list[DeductionOut]
    principal_paid: Money
    offsets_recorded: Money
    payouts_recorded: Money
    interest_recorded: Money
    balance_before_interest: Money
    interest_total: Money
    deductions_total: Money
    payout_amount: Money
    note: str | None = None
    draft_only: bool = True


# Helpers ---------------------------------------------------------------------------------


async def _rates(session: Any) -> dict[int, Decimal]:
    rows = (await session.execute(select(ds.DepositInterestReferenceRate))).scalars().all()
    return {r.year: r.rate for r in rows}


async def _compute(
    session: Any, deposit: Deposit, body: DepositSettlementIn
) -> ds.SettlementResult:
    movements = (
        (
            await session.execute(
                select(DepositMovement)
                .where(DepositMovement.deposit_id == deposit.id)
                .order_by(DepositMovement.date)
            )
        )
        .scalars()
        .all()
    )

    def of(kind: DepositMovementKind) -> list[tuple[date, Decimal]]:
        return [(m.date, m.amount) for m in movements if m.kind is kind]

    interest_recorded = sum(
        (m.amount for m in movements if m.kind is DepositMovementKind.INTEREST), ds.ZERO
    )
    rates = (
        await _rates(session)
        if body.interest_mode is ds.DepositInterestMode.REFERENCE_RATE
        else None
    )
    try:
        return ds.compute_settlement(
            settlement_date=body.settlement_date,
            interest_mode=body.interest_mode,
            payments=of(DepositMovementKind.PAYMENT),
            offsets=of(DepositMovementKind.OFFSET),
            payouts=of(DepositMovementKind.PAYOUT),
            interest_recorded=interest_recorded,
            deductions=[ds.Deduction(d.label, d.amount) for d in body.deductions],
            rates=rates,
            entered_interest={y.year: y.amount for y in body.interest_years},
        )
    except ds.SettlementError as exc:
        raise _invalid(str(exc)) from None


def _result_out(
    deposit_id: uuid.UUID, result: ds.SettlementResult, note: str | None
) -> DepositSettlementOut:
    return DepositSettlementOut(
        deposit_id=deposit_id,
        settlement_date=result.settlement_date,
        interest_mode=result.interest_mode,
        interest_years=[
            InterestYearOut(year=y.year, rate=y.rate, days=y.days, amount=y.amount)
            for y in result.years
        ],
        deductions=[DeductionOut(label=d.label, amount=d.amount) for d in result.deductions],
        principal_paid=result.principal_paid,
        offsets_recorded=result.offsets_recorded,
        payouts_recorded=result.payouts_recorded,
        interest_recorded=result.interest_recorded,
        balance_before_interest=result.balance_before_interest,
        interest_total=result.interest_total,
        deductions_total=result.deductions_total,
        payout_amount=result.payout_amount,
        note=note,
    )


def _row_out(row: ds.DepositSettlement) -> DepositSettlementOut:
    return DepositSettlementOut(
        id=row.id,
        deposit_id=row.deposit_id,
        status=row.status,
        settlement_date=row.settlement_date,
        interest_mode=row.interest_mode,
        interest_years=[
            InterestYearOut(
                year=int(y["year"]),
                rate=None if y.get("rate") is None else Decimal(str(y["rate"])),
                days=int(y["days"]),
                amount=Decimal(str(y["amount"])),
            )
            for y in row.interest_years
        ],
        deductions=[
            DeductionOut(label=str(d["label"]), amount=Decimal(str(d["amount"])))
            for d in row.deductions
        ],
        principal_paid=row.principal_paid,
        offsets_recorded=row.offsets_recorded,
        payouts_recorded=row.payouts_recorded,
        interest_recorded=row.interest_recorded,
        balance_before_interest=row.principal_paid - row.offsets_recorded - row.payouts_recorded,
        interest_total=row.interest_total,
        deductions_total=row.deductions_total,
        payout_amount=row.payout_amount,
        note=row.note,
        draft_only=row.status is ds.DepositSettlementStatus.DRAFT,
    )


async def _deposit(session: Any, deposit_id: uuid.UUID) -> Deposit:
    deposit: Deposit | None = await session.get(Deposit, deposit_id)
    if deposit is None:
        raise _nf()
    return deposit


# Reference rates -------------------------------------------------------------------------


@router.get("/deposit-interest-rates", summary="Referenzzinssatz je Jahr")
async def list_reference_rates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[ReferenceRateOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            (
                await session.execute(
                    select(ds.DepositInterestReferenceRate).order_by(
                        ds.DepositInterestReferenceRate.year
                    )
                )
            )
            .scalars()
            .all()
        )
        return [ReferenceRateOut.model_validate(r) for r in rows]


@router.put("/deposit-interest-rates/{year}", summary="Referenzzinssatz für ein Jahr setzen")
async def put_reference_rate(
    year: int,
    body: ReferenceRateIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> ReferenceRateOut:
    if year < 1900 or year > 2200:
        raise _invalid("Das Jahr ist ungültig.")
    rate = body.rate.quantize(Decimal("0.00001"))
    async with tenant_tx(request, principal) as session:
        row = (
            await session.execute(
                select(ds.DepositInterestReferenceRate).where(
                    ds.DepositInterestReferenceRate.year == year
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = ds.DepositInterestReferenceRate(
                tenant_id=principal.tenant_id, year=year, rate=rate, note=body.note
            )
            session.add(row)
        else:
            row.rate = rate
            row.note = body.note
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="deposit_interest_rate.set",
            entity_type="deposit_interest_rate",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"year": str(year), "rate": str(rate)},
        )
        return ReferenceRateOut.model_validate(row)


@router.delete(
    "/deposit-interest-rates/{year}", status_code=204, summary="Referenzzinssatz entfernen"
)
async def delete_reference_rate(
    year: int, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = (
            await session.execute(
                select(ds.DepositInterestReferenceRate).where(
                    ds.DepositInterestReferenceRate.year == year
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise _nf()
        await session.delete(row)
        return Response(status_code=204)


# Settlements -----------------------------------------------------------------------------


@router.post("/deposits/{deposit_id}/settlements/preview", summary="Kautionsabrechnung berechnen")
async def preview_settlement(
    deposit_id: uuid.UUID,
    body: DepositSettlementIn,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> DepositSettlementOut:
    async with tenant_tx(request, principal) as session:
        deposit = await _deposit(session, deposit_id)
        result = await _compute(session, deposit, body)
        return _result_out(deposit.id, result, body.note)


@router.post(
    "/deposits/{deposit_id}/settlements",
    status_code=201,
    summary="Kautionsabrechnung als Entwurf speichern",
)
async def create_settlement(
    deposit_id: uuid.UUID,
    body: DepositSettlementIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> DepositSettlementOut:
    async with tenant_tx(request, principal) as session:
        deposit = await _deposit(session, deposit_id)
        contract = await session.get(Contract, deposit.contract_id)
        if contract is not None and contract.end_date and body.settlement_date < contract.end_date:
            raise _invalid("Das Abrechnungsdatum liegt vor dem Vertragsende.")
        result = await _compute(session, deposit, body)
        row = ds.DepositSettlement(
            tenant_id=principal.tenant_id,
            deposit_id=deposit.id,
            settlement_date=result.settlement_date,
            interest_mode=result.interest_mode,
            interest_years=[y.as_json() for y in result.years],
            deductions=[d.as_json() for d in result.deductions],
            principal_paid=result.principal_paid,
            offsets_recorded=result.offsets_recorded,
            payouts_recorded=result.payouts_recorded,
            interest_recorded=result.interest_recorded,
            interest_total=result.interest_total,
            deductions_total=result.deductions_total,
            payout_amount=result.payout_amount,
            note=body.note,
            created_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="deposit_settlement.drafted",
            entity_type="deposit_settlement",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "deposit_id": str(deposit.id),
                "interest_mode": result.interest_mode.value,
                "payout_amount": str(result.payout_amount),
            },
        )
        return _row_out(row)


@router.get("/deposits/{deposit_id}/settlements", summary="Kautionsabrechnungen (Entwürfe)")
async def list_settlements(
    deposit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[DepositSettlementOut]:
    async with tenant_tx(request, principal) as session:
        await _deposit(session, deposit_id)
        rows = (
            (
                await session.execute(
                    select(ds.DepositSettlement)
                    .where(ds.DepositSettlement.deposit_id == deposit_id)
                    .order_by(ds.DepositSettlement.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [_row_out(r) for r in rows]


@router.post(
    "/deposit-settlements/{settlement_id}/release",
    summary="Kautionsabrechnung freigeben (hinter G3)",
)
async def release_settlement(
    settlement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> DepositSettlementOut:
    """Releasing a settlement would settle the deposit (payout record, claim against the
    tenant). That is a rental statement effect and stays behind release gate G3 (18.0)."""
    await ensure_release_gate_open(
        ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        row = await session.get(ds.DepositSettlement, settlement_id)
        if row is None:
            raise _nf()
        if row.status is not ds.DepositSettlementStatus.DRAFT:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Entwurf ist bereits freigegeben.")
        row.status = ds.DepositSettlementStatus.RELEASED
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="deposit_settlement.released",
            entity_type="deposit_settlement",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"payout_amount": str(row.payout_amount)},
        )
        return _row_out(row)
