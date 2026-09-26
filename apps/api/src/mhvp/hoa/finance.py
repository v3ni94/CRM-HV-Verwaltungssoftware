"""WEG loans, insurance claims and larger measures (7.8 W10, A59).

Disbursement, repayment, interest and fees of a loan are separate items; damage cost, benefit,
deductible, recourse and payments to single owners of a claim are separate items. An item
carries an amount only as a description: it becomes a financial fact through the journal entry
it references (same ledger). Balances are derived from the referenced posted entries, never
from the items alone. The tax and allocation treatment of every case stays a release decision
(W10, M24-03); this module records and reports, it posts nothing.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_session_legal_entity_allowed,
    session_allowed_legal_entity_ids,
)
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import (
    HoaInsuranceClaim,
    HoaInsuranceClaimItem,
    HoaLoan,
    HoaLoanItem,
    HoaMeasure,
    HoaMeasureFinancing,
    Resolution,
    SpecialLevy,
)

router = APIRouter(prefix="/hoa", tags=["WEG"])
# Same permission family as the other WEG endpoints (plans, statements, levies): reading needs
# accounting:read, recording needs accounting:create. No separate hoa:* permission exists in
# the permission catalogue (mhvp.core.auth.permissions).
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
ZERO = Decimal("0.00")

LOAN_ITEM_KINDS = ("disbursement", "repayment", "interest", "fee")
CLAIM_ITEM_KINDS = ("damage_cost", "benefit", "deductible", "regress", "owner_payment")
FINANCING_SOURCES = ("reserve", "special_levy", "loan", "other")
NOTE = (
    "Erfassung und Nachweis. Beträge gelten nur mit Bezug auf eine gebuchte Journalbuchung; "
    "Steuer- und Umlagebehandlung sowie Beschlussgrundlage werden je Fall freigegeben (W10)."
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeasureIn(_In):
    ledger_id: uuid.UUID
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    kind: str = Field(default="undecided", pattern="^(maintenance|structural_change|undecided)$")
    kind_basis: str | None = Field(default=None, max_length=4000)
    cost_frame: Decimal = Field(ge=0, decimal_places=2)
    resolution_id: uuid.UUID | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    account_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=4000)


class MeasurePatch(_In):
    status: str | None = Field(
        default=None, pattern="^(planned|resolved|in_progress|completed|cancelled)$"
    )
    kind: str | None = Field(default=None, pattern="^(maintenance|structural_change)$")
    kind_basis: str | None = Field(default=None, min_length=3, max_length=4000)
    resolution_id: uuid.UUID | None = None
    cost_frame: Decimal | None = Field(default=None, ge=0, decimal_places=2)


class FinancingIn(_In):
    source: str = Field(pattern="^(reserve|special_levy|loan|other)$")
    amount: Decimal = Field(gt=0, decimal_places=2)
    special_levy_id: uuid.UUID | None = None
    loan_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class LoanIn(_In):
    ledger_id: uuid.UUID
    lender: str = Field(min_length=2, max_length=200)
    reference: str | None = Field(default=None, max_length=100)
    principal: Decimal = Field(gt=0, decimal_places=2)
    interest_rate_percent: Decimal = Field(ge=0, le=100, decimal_places=8)
    term_months: int | None = Field(default=None, ge=1, le=600)
    instalment: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    start_date: date
    end_date: date | None = None
    purpose: str = Field(min_length=3, max_length=4000)
    resolution_id: uuid.UUID | None = None
    measure_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=4000)


class LoanItemIn(_In):
    kind: str = Field(pattern="^(disbursement|repayment|interest|fee)$")
    booking_date: date
    amount: Decimal = Field(gt=0, decimal_places=2)
    journal_entry_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class ClaimIn(_In):
    ledger_id: uuid.UUID
    title: str = Field(min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=8000)
    damage_date: date
    reported_on: date | None = None
    insurer: str | None = Field(default=None, max_length=200)
    policy_reference: str | None = Field(default=None, max_length=100)
    claim_number: str | None = Field(default=None, max_length=100)
    deductible: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    regress_party: str | None = Field(default=None, max_length=200)
    measure_id: uuid.UUID | None = None
    resolution_id: uuid.UUID | None = None  # A79: resolution of the same community
    note: str | None = Field(default=None, max_length=4000)


class ClaimPatch(_In):
    status: str | None = Field(
        default=None, pattern="^(reported|accepted|rejected|settled|closed)$"
    )
    claim_number: str | None = Field(default=None, max_length=100)
    resolution_id: uuid.UUID | None = None


class ClaimItemIn(_In):
    kind: str = Field(pattern="^(damage_cost|benefit|deductible|regress|owner_payment)$")
    booking_date: date
    amount: Decimal = Field(gt=0, decimal_places=2)
    journal_entry_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


# Helpers ----------------------------------------------------------------------------------


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID) -> Any:
    from mhvp.hoa.routers import _hoa_ledger

    ledger = await _hoa_ledger(session, ledger_id)
    # A37: a membership scoped to legal entities (tax advisor) records nothing for a foreign
    # community; answered as not found (Sicherheitsreview 1.22, Befund 4).
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return ledger


async def _get(session: AsyncSession, model: Any, row_id: uuid.UUID) -> Any:
    row = await session.get(model, row_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, row.legal_entity_id)
    return row


def _entity_visible(session: AsyncSession, legal_entity_id: uuid.UUID) -> bool:
    """List filter of A37: a scoped membership sees only its own legal entities."""
    allowed = session_allowed_legal_entity_ids(session)
    return allowed is None or legal_entity_id in allowed


async def _check_resolution(
    session: AsyncSession, resolution_id: uuid.UUID | None, legal_entity_id: uuid.UUID
) -> None:
    if resolution_id is None:
        return
    res = await session.get(Resolution, resolution_id)
    if res is None or res.legal_entity_id != legal_entity_id:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Beschluss gehört nicht zu dieser Gemeinschaft."
        )


async def _check_measure(
    session: AsyncSession, measure_id: uuid.UUID | None, ledger_id: uuid.UUID
) -> None:
    if measure_id is None:
        return
    m = await session.get(HoaMeasure, measure_id)
    if m is None or m.ledger_id != ledger_id:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Maßnahme gehört nicht zu diesem Buchungskreis."
        )


async def _check_account(
    session: AsyncSession, account_id: uuid.UUID | None, ledger_id: uuid.UUID, category: str
) -> None:
    from mhvp.accounting.models import LedgerAccount

    if account_id is None:
        return
    acc = await session.get(LedgerAccount, account_id)
    if acc is None or acc.ledger_id != ledger_id:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Konto gehört nicht zum Buchungskreis.")
    if acc.category.value != category:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Konto {acc.number} hat nicht die Kategorie {category}."
        )


async def _entry_state(
    session: AsyncSession, journal_entry_id: uuid.UUID | None, ledger_id: uuid.UUID
) -> tuple[str | None, date | None]:
    """Validates the journal entry reference (same ledger) and returns (status, booking date)."""
    from mhvp.accounting.models import JournalEntry

    if journal_entry_id is None:
        return None, None
    entry = await session.get(JournalEntry, journal_entry_id)
    if entry is None or entry.ledger_id != ledger_id:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Journalbuchung gehört nicht zum Buchungskreis."
        )
    return entry.status.value, entry.booking_date


async def _documents(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> list[str]:
    from mhvp.documents.models import DocumentLink

    return [
        str(d)
        for d in (
            await session.scalars(
                select(DocumentLink.document_id).where(
                    DocumentLink.entity_type == entity_type, DocumentLink.entity_id == entity_id
                )
            )
        ).all()
    ]


async def _items_out(
    session: AsyncSession, rows: list[Any], ledger_id: uuid.UUID
) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        status, _ = await _entry_state(session, r.journal_entry_id, ledger_id)
        out.append(
            {
                "id": r.id,
                "kind": r.kind,
                "booking_date": r.booking_date,
                "amount": str(r.amount),
                "journal_entry_id": r.journal_entry_id,
                "entry_status": status,  # None: planned, no financial fact yet
                "booked": status == "posted",
                "note": r.note,
                **({"contract_id": r.contract_id} if hasattr(r, "contract_id") else {}),
            }
        )
    return out


def _sums(items: list[dict[str, Any]], kinds: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Per kind: booked (posted entry) and planned (no posted entry) totals."""
    result = {}
    for kind in kinds:
        booked = sum(
            (Decimal(i["amount"]) for i in items if i["kind"] == kind and i["booked"]), ZERO
        )
        planned = sum(
            (Decimal(i["amount"]) for i in items if i["kind"] == kind and not i["booked"]), ZERO
        )
        result[kind] = {"booked": str(booked), "planned": str(planned)}
    return result


# Measures ---------------------------------------------------------------------------------


def _measure_out(m: HoaMeasure) -> dict[str, Any]:
    return {
        "id": m.id,
        "legal_entity_id": m.legal_entity_id,
        "ledger_id": m.ledger_id,
        "title": m.title,
        "description": m.description,
        "kind": m.kind,
        "kind_basis": m.kind_basis,
        "cost_frame": str(m.cost_frame),
        "resolution_id": m.resolution_id,
        "status": m.status,
        "planned_start": m.planned_start,
        "planned_end": m.planned_end,
        "account_id": m.account_id,
        "note": m.note,
    }


@router.post("/measures", status_code=201, summary="Größere Maßnahme anlegen (W10)")
async def create_measure(
    body: MeasureIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    if body.kind != "undecided" and not (body.kind_basis or "").strip():
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Einordnung als Erhaltung oder bauliche Veränderung nur mit Sachverhalt und "
            "Rechtsgrund (kind_basis), nicht allein aus einer Kontierung (W10).",
        )
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, body.ledger_id)
        await _check_resolution(session, body.resolution_id, ledger.legal_entity_id)
        await _check_account(session, body.account_id, ledger.id, "cost")
        row = HoaMeasure(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            legal_entity_id=ledger.legal_entity_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return _measure_out(row)


@router.get("/measures", summary="Maßnahmen einer GdWE")
async def list_measures(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if not _entity_visible(session, legal_entity_id):
            return []
        rows = await session.scalars(
            select(HoaMeasure)
            .where(HoaMeasure.legal_entity_id == legal_entity_id)
            .order_by(HoaMeasure.created_at.desc())
        )
        return [_measure_out(r) for r in rows.all()]


@router.get("/measures/{measure_id}", summary="Maßnahme mit Finanzierung und Belegen")
async def get_measure(
    measure_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        m = await _get(session, HoaMeasure, measure_id)
        financing = (
            await session.scalars(
                select(HoaMeasureFinancing).where(HoaMeasureFinancing.measure_id == m.id)
            )
        ).all()
        loans = (await session.scalars(select(HoaLoan).where(HoaLoan.measure_id == m.id))).all()
        claims = (
            await session.scalars(
                select(HoaInsuranceClaim).where(HoaInsuranceClaim.measure_id == m.id)
            )
        ).all()
        financed = sum((f.amount for f in financing), ZERO)
        return _measure_out(m) | {
            "financing": [
                {
                    "id": f.id,
                    "source": f.source,
                    "amount": str(f.amount),
                    "special_levy_id": f.special_levy_id,
                    "loan_id": f.loan_id,
                    "note": f.note,
                }
                for f in financing
            ],
            "financed_total": str(financed),
            "financing_gap": str(m.cost_frame - financed),
            "loan_ids": [loan.id for loan in loans],
            "claim_ids": [c.id for c in claims],
            "document_ids": await _documents(session, "hoa_measure", m.id),
            "note_text": NOTE,
        }


@router.patch("/measures/{measure_id}", summary="Status, Einordnung oder Beschluss ändern")
async def patch_measure(
    measure_id: uuid.UUID,
    body: MeasurePatch,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        m = await _get(session, HoaMeasure, measure_id)
        if body.kind is not None and not (body.kind_basis or m.kind_basis or "").strip():
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Einordnung nur mit Sachverhalt und Rechtsgrund (kind_basis), W10.",
            )
        if body.status == "resolved" and (body.resolution_id or m.resolution_id) is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Status beschlossen braucht einen Beschluss (W06)."
            )
        await _check_resolution(session, body.resolution_id, m.legal_entity_id)
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(m, field, value)
        m.updated_by = principal.user_id
        await session.flush()
        return _measure_out(m)


@router.post(
    "/measures/{measure_id}/financing", status_code=201, summary="Finanzierungsanteil erfassen"
)
async def add_financing(
    measure_id: uuid.UUID,
    body: FinancingIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        m = await _get(session, HoaMeasure, measure_id)
        if body.source == "special_levy":
            if body.special_levy_id is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Sonderumlage fehlt.")
            levy = await session.get(SpecialLevy, body.special_levy_id)
            if levy is None or levy.ledger_id != m.ledger_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Sonderumlage gehört nicht zum Buchungskreis."
                )
        if body.source == "loan":
            if body.loan_id is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Darlehen fehlt.")
            loan = await session.get(HoaLoan, body.loan_id)
            if loan is None or loan.ledger_id != m.ledger_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Darlehen gehört nicht zum Buchungskreis."
                )
        row = HoaMeasureFinancing(
            tenant_id=principal.tenant_id, measure_id=m.id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return {"id": row.id, "measure_id": m.id, "source": row.source, "amount": str(row.amount)}


# Loans ------------------------------------------------------------------------------------


def _loan_out(loan: HoaLoan) -> dict[str, Any]:
    return {
        "id": loan.id,
        "legal_entity_id": loan.legal_entity_id,
        "ledger_id": loan.ledger_id,
        "lender": loan.lender,
        "reference": loan.reference,
        "principal": str(loan.principal),
        "interest_rate_percent": str(loan.interest_rate_percent),
        "term_months": loan.term_months,
        "instalment": str(loan.instalment) if loan.instalment is not None else None,
        "start_date": loan.start_date,
        "end_date": loan.end_date,
        "purpose": loan.purpose,
        "resolution_id": loan.resolution_id,
        "measure_id": loan.measure_id,
        "account_id": loan.account_id,
        "status": loan.status,
        "note": loan.note,
    }


@router.post("/loans", status_code=201, summary="Darlehen anlegen (W10)")
async def create_loan(
    body: LoanIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    if body.end_date is not None and body.end_date < body.start_date:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Laufzeitende vor Beginn.")
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, body.ledger_id)
        await _check_resolution(session, body.resolution_id, ledger.legal_entity_id)
        await _check_measure(session, body.measure_id, ledger.id)
        await _check_account(session, body.account_id, ledger.id, "loan")
        row = HoaLoan(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            legal_entity_id=ledger.legal_entity_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return _loan_out(row)


@router.get("/loans", summary="Darlehen einer GdWE")
async def list_loans(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if not _entity_visible(session, legal_entity_id):
            return []
        rows = await session.scalars(
            select(HoaLoan)
            .where(HoaLoan.legal_entity_id == legal_entity_id)
            .order_by(HoaLoan.start_date.desc())
        )
        return [_loan_out(r) for r in rows.all()]


@router.get("/loans/{loan_id}", summary="Darlehen mit Positionen und Stand")
async def get_loan(
    loan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        loan = await _get(session, HoaLoan, loan_id)
        return await loan_report(session, loan)


async def loan_report(session: AsyncSession, loan: HoaLoan) -> dict[str, Any]:
    """Loan with its items; the balance counts only items with a posted journal entry
    (disbursed minus repaid). Interest and fees are shown apart and never reduce the balance.
    If a loan account is linked, its ledger balance is shown next to it (difference explained,
    never settled here)."""
    from mhvp.accounting.reports import _balance

    rows = (
        await session.scalars(
            select(HoaLoanItem)
            .where(HoaLoanItem.loan_id == loan.id)
            .order_by(HoaLoanItem.booking_date, HoaLoanItem.created_at)
        )
    ).all()
    items = await _items_out(session, list(rows), loan.ledger_id)
    sums = _sums(items, LOAN_ITEM_KINDS)
    balance = Decimal(sums["disbursement"]["booked"]) - Decimal(sums["repayment"]["booked"])
    account_balance = None
    if loan.account_id is not None:
        # liability account: credit balance is shown positive
        account_balance = ZERO - await _balance(session, loan.account_id, date.max)
    return _loan_out(loan) | {
        "items": items,
        "totals": sums,
        "balance_booked": str(balance),
        "account_balance": str(account_balance) if account_balance is not None else None,
        "account_difference": str(account_balance - balance)
        if account_balance is not None
        else None,
        "document_ids": await _documents(session, "hoa_loan", loan.id),
        "note_text": NOTE,
    }


@router.get("/loans/{loan_id}/schedule", summary="Ratenplan als Orientierung (W10, A78)")
async def get_loan_schedule(
    loan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Annuity plan (instalment given) or linear plan (term given) from principal, rate, term,
    instalment and start (`calc.loan_schedule`), plus the comparison of the planned repayment
    and interest per month with the booked items. Nothing is posted; the loan contract
    prevails (note_text)."""
    from mhvp.hoa.calc import loan_schedule, schedule_comparison

    async with tenant_tx(request, principal) as session:
        loan = await _get(session, HoaLoan, loan_id)
        plan = loan_schedule(
            loan.principal,
            loan.interest_rate_percent,
            loan.term_months,
            loan.instalment,
            loan.start_date,
        )
        rows = (
            await session.scalars(select(HoaLoanItem).where(HoaLoanItem.loan_id == loan.id))
        ).all()
        items = await _items_out(session, list(rows), loan.ledger_id)
        return {
            "loan_id": loan.id,
            "principal": str(loan.principal),
            "interest_rate_percent": str(loan.interest_rate_percent),
            "term_months": loan.term_months,
            "instalment": str(loan.instalment) if loan.instalment is not None else None,
            "start_date": loan.start_date,
            **plan,
            "comparison": schedule_comparison(plan["rows"], items),
        }


@router.post("/loans/{loan_id}/items", status_code=201, summary="Darlehensposition erfassen")
async def add_loan_item(
    loan_id: uuid.UUID,
    body: LoanItemIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        loan = await _get(session, HoaLoan, loan_id)
        status, _ = await _entry_state(session, body.journal_entry_id, loan.ledger_id)
        if body.kind == "disbursement":
            booked = sum(
                (
                    i.amount
                    for i in (
                        await session.scalars(
                            select(HoaLoanItem).where(
                                HoaLoanItem.loan_id == loan.id, HoaLoanItem.kind == "disbursement"
                            )
                        )
                    ).all()
                ),
                ZERO,
            )
            if booked + body.amount > loan.principal:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Auszahlungen übersteigen den Darlehensbetrag.",
                )
        row = HoaLoanItem(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            loan_id=loan.id,
            **body.model_dump(),
        )
        session.add(row)
        if status == "posted" and loan.status == "draft" and body.kind == "disbursement":
            loan.status = "active"
        await session.flush()
        return (await _items_out(session, [row], loan.ledger_id))[0]


# Insurance claims -------------------------------------------------------------------------


def _claim_out(c: HoaInsuranceClaim) -> dict[str, Any]:
    return {
        "id": c.id,
        "legal_entity_id": c.legal_entity_id,
        "ledger_id": c.ledger_id,
        "title": c.title,
        "description": c.description,
        "damage_date": c.damage_date,
        "reported_on": c.reported_on,
        "insurer": c.insurer,
        "policy_reference": c.policy_reference,
        "claim_number": c.claim_number,
        "deductible": str(c.deductible),
        "status": c.status,
        "regress_party": c.regress_party,
        "measure_id": c.measure_id,
        "resolution_id": c.resolution_id,
        "note": c.note,
    }


@router.post("/insurance-claims", status_code=201, summary="Versicherungsfall anlegen (W10)")
async def create_claim(
    body: ClaimIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, body.ledger_id)
        await _check_measure(session, body.measure_id, ledger.id)
        await _check_resolution(session, body.resolution_id, ledger.legal_entity_id)
        row = HoaInsuranceClaim(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            legal_entity_id=ledger.legal_entity_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return _claim_out(row)


@router.get("/insurance-claims", summary="Versicherungsfälle einer GdWE")
async def list_claims(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if not _entity_visible(session, legal_entity_id):
            return []
        rows = await session.scalars(
            select(HoaInsuranceClaim)
            .where(HoaInsuranceClaim.legal_entity_id == legal_entity_id)
            .order_by(HoaInsuranceClaim.damage_date.desc())
        )
        return [_claim_out(r) for r in rows.all()]


@router.get("/insurance-claims/{claim_id}", summary="Versicherungsfall mit Positionen")
async def get_claim(
    claim_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        c = await _get(session, HoaInsuranceClaim, claim_id)
        rows = (
            await session.scalars(
                select(HoaInsuranceClaimItem)
                .where(HoaInsuranceClaimItem.claim_id == c.id)
                .order_by(HoaInsuranceClaimItem.booking_date, HoaInsuranceClaimItem.created_at)
            )
        ).all()
        items = await _items_out(session, list(rows), c.ledger_id)
        sums = _sums(items, CLAIM_ITEM_KINDS)
        booked = {k: Decimal(v["booked"]) for k, v in sums.items()}
        # Net burden of the community from booked items: damage cost minus benefit and recourse
        # received; the deductible is part of the damage cost that no benefit covers and is
        # shown apart, never netted invisibly (W10).
        net = booked["damage_cost"] - booked["benefit"] - booked["regress"]
        return _claim_out(c) | {
            "items": items,
            "totals": sums,
            "net_burden_booked": str(net),
            "owner_payments_booked": str(booked["owner_payment"]),
            "document_ids": await _documents(session, "hoa_insurance_claim", c.id),
            "note_text": NOTE,
        }


@router.patch(
    "/insurance-claims/{claim_id}", summary="Status oder Beschluss des Versicherungsfalls"
)
async def patch_claim(
    claim_id: uuid.UUID,
    body: ClaimPatch,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        c = await _get(session, HoaInsuranceClaim, claim_id)
        await _check_resolution(session, body.resolution_id, c.legal_entity_id)
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(c, field, value)
        c.updated_by = principal.user_id
        await session.flush()
        return _claim_out(c)


@router.post(
    "/insurance-claims/{claim_id}/items", status_code=201, summary="Position zum Versicherungsfall"
)
async def add_claim_item(
    claim_id: uuid.UUID,
    body: ClaimItemIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from mhvp.contracts.models import Contract, ContractKind

    async with tenant_tx(request, principal) as session:
        c = await _get(session, HoaInsuranceClaim, claim_id)
        await _entry_state(session, body.journal_entry_id, c.ledger_id)
        if body.kind == "owner_payment":
            contract = await session.get(Contract, body.contract_id) if body.contract_id else None
            if contract is None or contract.kind is not ContractKind.OWNERSHIP:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Zahlung an einen Eigentümer braucht den Eigentumsvertrag (W10).",
                )
            if contract.legal_entity_id != c.legal_entity_id:
                # 6.9.1: the owner must belong to the community of the claim
                # (Sicherheitsreview 1.22, Befund 7).
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Der Eigentumsvertrag gehört nicht zur Gemeinschaft des Schadensfalls.",
                )
        row = HoaInsuranceClaimItem(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            claim_id=c.id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return (await _items_out(session, [row], c.ledger_id))[0]
