"""WEG endpoints (/api/v1/hoa, M24): economic plan, resolutions, annual statement with asset
report. Issuing requires the resolution bound to the snapshot; posting results needs G4."""

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import calc_settings
from mhvp.billing.status import StatementStatus, TransitionError, check_transition
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.etag import check_if_match, etag_of
from mhvp.core.events import emit
from mhvp.core.listparams import ListParams, ListSpec, sparse, strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.hoa import calc
from mhvp.hoa.majority import SUBJECT_PATTERN, check_resolution
from mhvp.hoa.models import (
    EconomicPlan,
    HoaCostItem,
    HoaReserve,
    HoaReserveMovement,
    HoaStatement,
    PlanItem,
    Resolution,
)
from mhvp.hoa.property_scope import HOA_GUARD

_log = logging.getLogger(__name__)

# M2-02/S16-02: WEG records outside the property assignment answer 404.
router = APIRouter(prefix="/hoa", tags=["WEG"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
BINDING = {"positive", "final", "legally_binding"}


class HoaBaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HoaPlanIn(HoaBaseIn):
    ledger_id: uuid.UUID
    year: int = Field(ge=2000, le=2100)
    valid_from: date
    # M24-04: master data and comparison basis of the plan.
    title: str | None = Field(default=None, max_length=200)
    as_of_date: date | None = None
    basis_statement_id: uuid.UUID | None = None
    basis_plan_id: uuid.UUID | None = None
    payment_rhythm: str = Field(default="monthly", pattern="^(monthly|quarterly|yearly)$")
    due_day: int = Field(default=1, ge=1, le=28)
    continues_until_new_plan: bool = True


class HoaPlanItemIn(HoaBaseIn):
    label: str = Field(min_length=1, max_length=200)
    component: str = Field(pattern="^(hoa_fee|reserve)$")
    amount: Decimal = Field(gt=0, decimal_places=2)
    allocation_key_id: uuid.UUID
    account_id: uuid.UUID | None = None
    basis_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    reserve_id: uuid.UUID | None = None


class HoaReserveIn(HoaBaseIn):
    """Earmarked reserve of the GdWE (M24-01, W08)."""

    ledger_id: uuid.UUID
    name: str = Field(min_length=2, max_length=200)
    purpose: str | None = Field(default=None, max_length=2000)
    account_id: uuid.UUID | None = None
    resolution_id: uuid.UUID | None = None
    # M24-01 (0294): bank investment of the ledger's legal entity, opening balance and year.
    bank_account_id: uuid.UUID | None = None
    opening_balance: Decimal = Field(default=Decimal("0.00"), decimal_places=2)
    opening_year: int | None = Field(default=None, ge=1990, le=2100)


class HoaReserveMovementIn(HoaBaseIn):
    reserve_id: uuid.UUID
    kind: str = Field(pattern="^(withdrawal|tax|fee|interest)$")
    amount: Decimal = Field(gt=0, decimal_places=2)
    purpose: str = Field(min_length=3, max_length=2000)
    document_id: uuid.UUID | None = None
    journal_entry_id: uuid.UUID | None = None
    resolution_id: uuid.UUID | None = None


class HoaCostsFromLedgerIn(HoaBaseIn):
    """M24-02: take the posted costs of one account in the statement year as positions."""

    account_id: uuid.UUID
    allocation_key_id: uuid.UUID
    basis: str = Field(min_length=3, max_length=2000)
    basis_resolution_id: uuid.UUID | None = None
    basis_document_id: uuid.UUID | None = None


class HoaVotesIn(HoaBaseIn):
    """Recorded tally of an external meeting for the majority check (M25-01)."""

    principle: str = Field(pattern="^(head|mea|unit)$")
    yes: Decimal = Field(ge=0)
    no: Decimal = Field(ge=0)
    abstain: Decimal = Field(default=Decimal("0"), ge=0)
    eligible: Decimal | None = Field(default=None, gt=0)


# GA03-03: deleted and irrelevant are notes in the Beschluss-Sammlung (no physical deletion);
# void stays accepted for existing entries until the operator decides its mapping (AA06-01).
RESOLUTION_STATUS_PATTERN = (
    "^(positive|negative|final|contested|annulled|legally_binding|deleted|irrelevant|void)$"
)


class HoaResolutionIn(HoaBaseIn):
    legal_entity_id: uuid.UUID
    decided_on: date
    subject: str = Field(min_length=3, max_length=2000)
    wording: str = Field(min_length=3, max_length=20000)
    status: str = Field(pattern=RESOLUTION_STATUS_PATTERN)
    kind: str = Field(default="external", pattern="^(meeting|circular|court|external)$")
    snapshot_hash: str | None = Field(default=None, max_length=64)
    subject_type: str | None = Field(
        default=None, pattern="^(economic_plan|hoa_statement|special_levy|other)$"
    )
    subject_id: uuid.UUID | None = None
    majority_basis: str | None = Field(default=None, max_length=4000)
    subject_kind: str | None = Field(default=None, pattern=SUBJECT_PATTERN)
    votes: HoaVotesIn | None = None
    location: str | None = Field(default=None, max_length=300)
    court_notes: str | None = Field(default=None, max_length=20000)


class HoaResolutionPatch(HoaBaseIn):
    status: str | None = Field(default=None, pattern=RESOLUTION_STATUS_PATTERN)
    # GA03-03: court notes (contest, annulment) and place of the decision
    court_notes: str | None = Field(default=None, max_length=20000)
    location: str | None = Field(default=None, max_length=300)


class HoaStatementIn(HoaBaseIn):
    ledger_id: uuid.UUID
    year: int = Field(ge=2000, le=2100)
    reserve_opening: Decimal = Decimal("0.00")
    reserve_withdrawals: Decimal = Field(default=Decimal("0.00"), ge=0)
    reserve_interest: Decimal = Decimal("0.00")


class HoaNewVersionIn(HoaBaseIn):
    """P02 (AE11): why the new version corrects its predecessor (optional)."""

    reason: str | None = None
    basis: str | None = Field(default=None, max_length=2000)
    resolution_id: uuid.UUID | None = None


class HoaCostIn(HoaBaseIn):
    label: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0)
    allocation_key_id: uuid.UUID
    basis: str = Field(min_length=3, max_length=2000)
    account_id: uuid.UUID | None = None
    journal_entry_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    labour_cost_35a: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    basis_resolution_id: uuid.UUID | None = None
    basis_document_id: uuid.UUID | None = None
    # AP21 / GAM-109: sub community of the same property (Mehrhausanlage).
    sub_community_id: uuid.UUID | None = None


class ReconciliationNoteIn(HoaBaseIn):
    """Explained difference of the cash flow reconciliation (W04): signed amount that bridges
    the costs booked in the year to the distributed costs, with the reason."""

    code: str = Field(pattern="^(heating_accrual|creditor_timing|prior_year|other)$")
    amount: Decimal = Field(decimal_places=2)
    note: str = Field(min_length=3, max_length=2000)


class ReconciliationNotesIn(HoaBaseIn):
    notes: list[ReconciliationNoteIn] = Field(default_factory=list, max_length=50)


class HoaTransitionIn(HoaBaseIn):
    target: StatementStatus
    resolution_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


async def _hoa_ledger(session: AsyncSession, ledger_id: uuid.UUID) -> Any:
    from mhvp.accounting.models import Ledger
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    ledger = await session.get(Ledger, ledger_id)
    entity = await session.get(LegalEntity, ledger.legal_entity_id) if ledger else None
    if ledger is None or entity is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if entity.kind is not LegalEntityKind.HOA or ledger.property_id is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Nur für den Buchungskreis einer GdWE (W01)."
        )
    return ledger


def _plan_out(p: EconomicPlan) -> dict[str, Any]:
    return {
        "id": p.id,
        "ledger_id": p.ledger_id,
        "year": p.year,
        "valid_from": p.valid_from,
        "status": p.status.value,
        "version": p.version,
        "snapshot_hash": p.snapshot_hash,
        "snapshot": p.snapshot,
        "resolution_id": p.resolution_id,
        "applied_at": p.applied_at,
        "title": p.title,
        "as_of_date": p.as_of_date,
        "basis_statement_id": p.basis_statement_id,
        "basis_plan_id": p.basis_plan_id,
        "payment_rhythm": p.payment_rhythm,
        "due_day": p.due_day,
        "continues_until_new_plan": p.continues_until_new_plan,
        "obsolete_at": p.obsolete_at,
        "obsolete": p.obsolete_at is not None,
    }


def _cost_out(i: HoaCostItem) -> dict[str, Any]:
    return {
        "id": i.id,
        "label": i.label,
        "amount": i.amount,
        "basis": i.basis,
        "allocation_key_id": i.allocation_key_id,
        "account_id": i.account_id,
        "journal_entry_id": i.journal_entry_id,
        "document_id": i.document_id,
        "labour_cost_35a": i.labour_cost_35a,
        "basis_resolution_id": i.basis_resolution_id,
        "basis_document_id": i.basis_document_id,
        # AP21 / GAM-109: sub community and the check hint "no documented basis".
        "sub_community_id": i.sub_community_id,
        "sub_community_basis_missing": i.sub_community_id is not None
        and i.basis_resolution_id is None
        and i.basis_document_id is None,
    }


async def _same_ledger_entry(
    session: AsyncSession, ledger_id: uuid.UUID, entry_id: uuid.UUID | None
) -> Any:
    """Posted journal entry of the same ledger or 422 (M24-02 drilldown, no foreign entry)."""
    from mhvp.accounting.models import EntryStatus, JournalEntry

    if entry_id is None:
        return None
    entry = await session.get(JournalEntry, entry_id)
    if entry is None or entry.ledger_id != ledger_id or entry.status is not EntryStatus.POSTED:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Buchung nicht gefunden, nicht gebucht oder aus anderem Buchungskreis.",
        )
    return entry


def _st_out(s: HoaStatement) -> dict[str, Any]:
    return {
        "id": s.id,
        "ledger_id": s.ledger_id,
        "year": s.year,
        "status": s.status.value,
        "version": s.version,
        "supersedes_id": s.supersedes_id,
        "snapshot_hash": s.snapshot_hash,
        "snapshot": s.snapshot,
        "resolution_id": s.resolution_id,
        "addressing_rule_version": s.addressing_rule_version,
        "posted_entry_ids": s.posted_entry_ids,
        "reconciliation_notes": s.reconciliation_notes,
        "loan_allocation": s.loan_allocation,
        "correction_reason": s.correction_reason,
        "correction_basis": s.correction_basis,
        "correction_resolution_id": s.correction_resolution_id,
    }


async def _move(
    session: AsyncSession, obj: Any, body: HoaTransitionIn, principal: TenantPrincipal
) -> None:
    resolution = await session.get(Resolution, body.resolution_id) if body.resolution_id else None
    if body.target is StatementStatus.RESOLVED:
        if resolution is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Beschluss fehlt (W06).")
        if resolution.status not in BINDING:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Beschluss ist nicht positiv gefasst.")
    if body.target is StatementStatus.INTERNALLY_APPROVED and obj.created_by == principal.user_id:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Die interne Freigabe muss eine andere Person erteilen.",
        )
    if body.target is StatementStatus.INTERNALLY_APPROVED and isinstance(obj, HoaStatement):
        from mhvp.hoa.package import blocking_checks

        findings = await blocking_checks(session, obj)
        if findings:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Freigabe gesperrt (W12): " + "; ".join(f["detail"] for f in findings),
            )
    if body.target is StatementStatus.POSTED:
        resolution = await session.get(Resolution, obj.resolution_id) if obj.resolution_id else None
    try:
        check_transition(
            obj.status,
            body.target,
            is_hoa=True,
            resolution_status=resolution.status if resolution else None,
            resolution_snapshot_matches=bool(
                resolution and obj.snapshot_hash and resolution.snapshot_hash == obj.snapshot_hash
            ),
        )
    except TransitionError as exc:
        raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from None
    if body.target is StatementStatus.RESOLVED and resolution is not None:
        obj.resolution_id = resolution.id
    obj.status = body.target


# Resolutions -----------------------------------------------------------------------------


@router.post(
    "/resolutions", status_code=201, summary="Beschluss erfassen (auch aus externer Versammlung)"
)
async def create_resolution(
    body: HoaResolutionIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        number = (
            int(
                await session.scalar(
                    select(func.coalesce(func.max(Resolution.number), 0)).where(
                        Resolution.legal_entity_id == body.legal_entity_id
                    )
                )
                or 0
            )
            + 1
        )
        data = body.model_dump(exclude={"votes"})
        votes = body.votes.model_dump(mode="json") if body.votes else {}
        row = Resolution(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            number=number,
            votes=votes,
            **data,
        )
        session.add(row)
        await session.flush()
        check = await check_resolution(session, principal, row) if body.subject_kind else None
        return {"id": row.id, "number": row.number, "status": row.status, "majority_check": check}


@router.patch(
    "/resolutions/{resolution_id}",
    summary="Wirksamkeitsstatus ändern (z. B. bestandskräftig, angefochten)",
)
async def patch_resolution(
    resolution_id: uuid.UUID,
    body: HoaResolutionPatch,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Resolution, resolution_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        check_if_match(if_match, row.updated_at)  # GA04-06
        fields = body.model_dump(exclude_unset=True)
        if not fields or ("status" in fields and fields["status"] is None):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Status oder Vermerk angeben.")
        if "status" in fields:
            old_status = row.status  # AN19 (GAK-204)
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="resolution.status_changed",
                entity_type="resolution",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={"from": row.status, "to": body.status},
            )
            row.status = fields["status"]
            # AN19 (GAK-204): consumer of resolution.status_changed; notifies only, never
            # cancels a dependent plan, levy or statement (D54).
            from mhvp.hoa.resolution_effects import on_status_changed

            await on_status_changed(
                session,
                tenant_id=principal.tenant_id,
                actor_user_id=principal.user_id,
                resolution=row,
                old_status=old_status,
                new_status=row.status,
            )
        notes = {k: fields[k] for k in ("court_notes", "location") if k in fields}
        if notes:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="resolution.notes_changed",
                entity_type="resolution",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={k: {"from": getattr(row, k), "to": v} for k, v in notes.items()},
            )
            for key, value in notes.items():
                setattr(row, key, value)
        await session.flush()
        await session.refresh(row, ["updated_at"])
        response.headers["ETag"] = etag_of(row.updated_at)
        return {
            "id": row.id,
            "status": row.status,
            "court_notes": row.court_notes,
            "location": row.location,
        }


_RESOLUTION_LIST = ListSpec(
    filters={
        "status": Resolution.status,
        "kind": Resolution.kind,
        "meeting_id": Resolution.meeting_id,
        "subject_kind": Resolution.subject_kind,
        "decided_on": Resolution.decided_on,
    },
    sort={
        "number": Resolution.number,
        "decided_on": Resolution.decided_on,
        "status": Resolution.status,
    },
)


@router.get("/resolutions", summary="Beschluss-Sammlung")
async def list_resolutions(
    legal_entity_id: uuid.UUID,
    request: Request,
    params: ListParams = Depends(_RESOLUTION_LIST.dependency),
    principal: TenantPrincipal = Depends(READ),
) -> Any:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            _RESOLUTION_LIST.apply(
                select(Resolution).where(Resolution.legal_entity_id == legal_entity_id),
                params,
                (Resolution.number, Resolution.id),
            )
        )
        return sparse(_resolution_rows(rows.all()), params, None)


def _resolution_rows(rows: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "number": r.number,
            "decided_on": r.decided_on,
            "subject": r.subject,
            "wording": r.wording,
            "status": r.status,
            "kind": r.kind,
            "votes": r.votes,
            "majority_basis": r.majority_basis,
            "subject_kind": r.subject_kind,
            "majority_check": r.majority_check,
            "allowed_majority": r.allowed_majority,
            "enabling_resolution_id": r.enabling_resolution_id,
            "vote_deadline_at": r.vote_deadline_at,
            # GA03-03
            "location": r.location,
            "court_notes": r.court_notes,
            "entered_at": r.entered_at,
        }
        for r in rows
    ]


# Economic plan ---------------------------------------------------------------------------


@router.post("/plans", status_code=201, summary="Wirtschaftsplan (Entwurf)")
async def create_plan(
    body: HoaPlanIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _hoa_ledger(session, body.ledger_id)
        refs: list[tuple[Any, uuid.UUID | None]] = [
            (HoaStatement, body.basis_statement_id),
            (EconomicPlan, body.basis_plan_id),
        ]
        for model, ref in refs:
            row = await session.get(model, ref) if ref else None
            if ref and (row is None or row.ledger_id != body.ledger_id):
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Plangrundlage aus anderem Buchungskreis."
                )
        plan = EconomicPlan(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(plan)
        await session.flush()
        return _plan_out(plan)


@router.post("/plans/{plan_id}/items", status_code=201, summary="Planposition")
async def add_plan_item(
    plan_id: uuid.UUID,
    body: HoaPlanItemIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id, with_for_update=True)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if plan.status is not StatementStatus.DRAFT:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über neue Version."
            )
        if body.reserve_id is not None:
            reserve = await session.get(HoaReserve, body.reserve_id)
            if (
                body.component != "reserve"
                or reserve is None
                or reserve.ledger_id != plan.ledger_id
            ):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Rücklage nur für Rücklagenpositionen desselben Buchungskreises.",
                )
        item = PlanItem(tenant_id=principal.tenant_id, plan_id=plan.id, **body.model_dump())
        session.add(item)
        await session.flush()
        return {"id": item.id}


@router.post("/plans/{plan_id}/calculate", summary="Gesamt- und Einzelwirtschaftsplan berechnen")
async def calculate_plan(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id, with_for_update=True)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if plan.status is not StatementStatus.DRAFT:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits berechnet.")
        ledger = await _hoa_ledger(session, plan.ledger_id)
        items = list(
            (await session.scalars(select(PlanItem).where(PlanItem.plan_id == plan.id))).all()
        )
        if not items:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Planpositionen.")
        result = await calc.plan_results(
            session,
            ledger.property_id,
            items,
            date(plan.year, 1, 1),
            date(plan.year, 12, 31),
            # AK01 (GAI-214): tenant switch, default report_only.
            remainder_mode=(await calc_settings.load(session)).hoa_remainder_mode,
        )
        basis_items = (
            list(
                (
                    await session.scalars(
                        select(PlanItem).where(PlanItem.plan_id == plan.basis_plan_id)
                    )
                ).all()
            )
            if plan.basis_plan_id
            else None
        )
        # M24-04: plan basis and deviation per item (information, part of the snapshot).
        result["comparison"] = calc.plan_comparison(items, basis_items)
        basis_snapshot = None
        if plan.basis_plan_id:
            basis_plan = await session.get(EconomicPlan, plan.basis_plan_id)
            basis_snapshot = basis_plan.snapshot if basis_plan else None
            basis_kind = "plan"
        elif plan.basis_statement_id:
            basis_st = await session.get(HoaStatement, plan.basis_statement_id)
            basis_snapshot = basis_st.snapshot if basis_st else None
            basis_kind = "statement"
        if basis_snapshot is not None:
            result["totals_comparison"] = calc.totals_comparison(
                result["totals"], basis_snapshot, basis_kind
            )
        plan.snapshot, plan.snapshot_hash = result, calc.digest(result)
        plan.status = StatementStatus.CALCULATED
        await session.flush()
        return _plan_out(plan)


@router.post(
    "/plans/{plan_id}/transition", summary="Statuswechsel (Beschluss an Snapshot gebunden)"
)
async def transition_plan(
    plan_id: uuid.UUID,
    body: HoaTransitionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id, with_for_update=True)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _move(session, plan, body, principal)
        await session.flush()
        return _plan_out(plan)


def _bound_reserve(unit: dict[str, Any] | None, component: str) -> uuid.UUID | None:
    """M24-01 (Zweckbindung der Sollstellung): the reserve of a unit's reserve advance when
    the plan directs all of it to exactly one earmarked reserve, otherwise unbound (the
    contract payment has one amount per component)."""
    if component != "reserve" or unit is None:
        return None
    split = unit.get("reserve_split") or {}
    if len(split) == 1:
        only = next(iter(split))
        return uuid.UUID(only) if only != "none" else None
    return None


RHYTHM_INTERVAL = {"quarterly": "quarterly", "yearly": "annual"}


async def _ensure_schedule(
    session: AsyncSession, contract: Any, plan: EconomicPlan, principal: TenantPrincipal
) -> bool:
    """P07-03: non monthly advances become a payment schedule of the contract (interval,
    due in advance, contract amount per month, due day of the plan). The monthly amounts of
    the plan are summed per instalment by the receivable run. Returns True when a schedule
    was created; a schedule with the same interval already standing is left untouched."""
    from mhvp.contracts.models import DueDayRule, PaymentInterval, PaymentSchedule
    from mhvp.contracts.services import add_schedule

    interval = PaymentInterval(RHYTHM_INTERVAL[plan.payment_rhythm])
    current = await session.scalar(
        select(PaymentSchedule).where(
            PaymentSchedule.contract_id == contract.id,
            PaymentSchedule.valid_from <= plan.valid_from,
            (PaymentSchedule.valid_to.is_(None)) | (PaymentSchedule.valid_to >= plan.valid_from),
        )
    )
    if current is not None and current.interval == interval:
        return False
    later = await session.scalar(
        select(func.count())
        .select_from(PaymentSchedule)
        .where(
            PaymentSchedule.contract_id == contract.id,
            PaymentSchedule.valid_from > plan.valid_from,
        )
    )
    if later:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail=f"Vertrag {contract.number} hat einen späteren Zahlungsplan; "
            "bitte zuerst bereinigen (P07-03).",
        )
    await add_schedule(
        session,
        contract,
        PaymentSchedule(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            contract_id=contract.id,
            interval=interval,
            due_day_rule=DueDayRule.DAY,
            due_day=plan.due_day,
            valid_from=plan.valid_from,
            payment_mode="advance",
            amount_basis="per_month",
        ),
    )
    return True


class PlanApplyIn(HoaBaseIn):
    """Confirmation of the preview: ``snapshot_hash`` must be the plan's current hash."""

    confirm: bool = False
    snapshot_hash: str | None = Field(default=None, max_length=64)


APPLY_STATUSES = (StatementStatus.RESOLVED, StatementStatus.ISSUED, StatementStatus.DUE)


async def _plan_apply_preview(session: AsyncSession, plan: EconomicPlan) -> dict[str, Any]:
    """Rows of the takeover (rule W02): per unit and component the ownership contract at
    ``valid_from``, the amount standing on it that day and the resolved monthly amount.
    Action ``create`` (new standing amount from ``valid_from``), ``unchanged`` (the same
    amount already starts on ``valid_from``), ``zero`` (nothing resolved), ``no_contract``
    (no owner at ``valid_from``, the unit is skipped and listed). ``posted_months`` counts
    receivable items already posted for months from ``valid_from`` on: they are never
    charged again by this step (W02, R04); an adjustment is a bookkeeping correction behind
    G1."""
    from mhvp.accounting.models import ItemStatus, ReceivableItem
    from mhvp.contacts.models import Party
    from mhvp.contracts.models import ContractPayment
    from mhvp.hoa.allocation_proposal import (
        allocation_proposal_enabled,
        plan_resolution_day,
        proposal_for,
    )
    from mhvp.hoa.plan_change import compute_differences, plan_change_mode

    rows: list[dict[str, Any]] = []
    posted_months = 0
    # AG20 (GAE-12): proposal of calc.allocation_owner behind a switch, display only.
    with_proposal = await allocation_proposal_enabled(session)
    plan_res_day = await plan_resolution_day(session, plan.resolution_id) if with_proposal else None
    for unit in (plan.snapshot or {}).get("units", []):
        unit_id = uuid.UUID(unit["unit_id"])
        contract = await calc.owner_at(session, unit_id, plan.valid_from)
        proposal = (
            await proposal_for(
                session,
                unit_id,
                contract,
                default_day=plan.valid_from,
                due_day=plan.valid_from,
                resolution_day=plan_res_day,
            )
            if with_proposal
            else None
        )
        party_name = None
        if contract is not None:
            party_name = await session.scalar(
                select(Party.name).where(Party.id == contract.party_id)
            )
        for component, amount in unit["monthly"].items():
            new = Decimal(amount)
            row: dict[str, Any] = {
                "unit_id": str(unit_id),
                "unit_number": unit["unit_number"],
                "component": component,
                "contract_id": contract.id if contract else None,
                "contract_number": contract.number if contract else None,
                "owner": party_name,
                "current": None,
                "new": str(new),
                "valid_from": plan.valid_from,
                "rhythm": plan.payment_rhythm,
                # P07-03: monthly amount times the months of the instalment (information)
                "instalment": str(
                    new * {"monthly": 1, "quarterly": 3, "yearly": 12}[plan.payment_rhythm]
                ),
            }
            if proposal is not None:
                row["allocation_proposal"] = proposal
            if contract is None:
                row["action"] = "no_contract"
            elif new <= 0:
                row["action"] = "zero"
            else:
                current = await session.scalar(
                    select(ContractPayment)
                    .where(
                        ContractPayment.contract_id == contract.id,
                        ContractPayment.payment_type_code == component,
                        ContractPayment.valid_from <= plan.valid_from,
                        (ContractPayment.valid_to.is_(None))
                        | (ContractPayment.valid_to >= plan.valid_from),
                    )
                    .order_by(ContractPayment.valid_from.desc())
                    .limit(1)
                )
                row["current"] = str(current.gross) if current else None
                unchanged = (
                    current is not None
                    and current.valid_from == plan.valid_from
                    and current.gross == new
                )
                row["action"] = "unchanged" if unchanged else "create"
                posted_months += int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ReceivableItem)
                        .where(
                            ReceivableItem.contract_id == contract.id,
                            ReceivableItem.payment_type_code == component,
                            ReceivableItem.status == ItemStatus.POSTED,
                            ReceivableItem.period_month >= plan.valid_from,
                        )
                    )
                    or 0
                )
            rows.append(row)
    counts = {
        k: sum(1 for r in rows if r["action"] == k)
        for k in ("create", "unchanged", "zero", "no_contract")
    }
    return {
        "plan_id": plan.id,
        "status": plan.status.value,
        "valid_from": plan.valid_from,
        "snapshot_hash": plan.snapshot_hash,
        "applied_at": plan.applied_at,
        "can_apply": plan.applied_at is None and plan.status in APPLY_STATUSES,
        "rows": rows,
        "counts": counts,
        "posted_months": posted_months,
        # AE09: variant and difference of posted months (details: /differences)
        "plan_change_mode": await plan_change_mode(session),
        "differences_total": (await compute_differences(session, plan))["total"],
        "gates": {
            "payment_rows": "Stammdaten des Vertrags, keine Freigabestufe (wie Sollbeträge im CRM)",
            "posting": "Sollstellung liest die Zeilen erst mit G1 (Buchhaltung)",
        },
        "hinweis": (
            "Vorschau; die Übernahme legt je Vertrag und Komponente einen Sollbetrag ab "
            "Wirksamkeitsbeginn an und schließt den vorherigen am Vortag. Bestätigung durch "
            "eine zweite Person (nicht der Ersteller des Plans)."
        ),
    }


@router.get(
    "/plans/{plan_id}/apply/preview", summary="Vorschau der Übernahme in die Zahlungspläne (W02)"
)
async def plan_apply_preview(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await _plan_apply_preview(session, plan)


@router.post(
    "/plans/{plan_id}/apply", summary="Beschlossene Vorschüsse als Vertragszahlungen übernehmen"
)
async def apply_plan(
    plan_id: uuid.UUID,
    request: Request,
    body: PlanApplyIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Only after the resolution, only with the confirmed preview (``confirm`` and the
    current ``snapshot_hash``) and only by a second person (not the plan's creator). Creates
    the standing monthly amounts per ownership contract from ``valid_from`` (rule W02: the
    draft changes nothing; months already posted are never charged again). Idempotent: an
    applied plan returns unchanged, rows already standing are skipped."""
    from mhvp.contracts.models import ContractPayment, PaymentReason
    from mhvp.contracts.services import add_payment

    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id, with_for_update=True)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if plan.applied_at is not None:
            return _plan_out(plan) | {"payments_created": 0, "already_applied": True}
        if plan.status not in APPLY_STATUSES:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Vorschüsse erst nach Beschluss (W02, W06)."
            )
        if body is None or not body.confirm:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Die Vorschau der Übernahme ist zu bestätigen (confirm).",
            )
        if plan.payment_rhythm != "monthly" and plan.valid_from.day != 1:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Vierteljährliche oder jährliche Vorschüsse beginnen zum Monatsersten "
                "(Anker des Zahlungsplans, P07-03).",
            )
        if body.snapshot_hash != plan.snapshot_hash:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Die Vorschau gehört zu einem anderen Stand des Plans (snapshot_hash).",
            )
        if plan.created_by == principal.user_id:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES,
                detail="Die Übernahme muss eine andere Person als der Ersteller bestätigen.",
            )
        preview = await _plan_apply_preview(session, plan)
        created = 0
        scheduled: dict[uuid.UUID, bool] = {}
        unit_map = {u["unit_id"]: u for u in (plan.snapshot or {}).get("units", [])}
        for row in preview["rows"]:
            if row["action"] != "create":
                continue
            contract = await calc.owner_at(session, uuid.UUID(row["unit_id"]), plan.valid_from)
            if contract is None:
                continue
            amount = Decimal(row["new"])
            await add_payment(
                session,
                contract,
                ContractPayment(
                    tenant_id=principal.tenant_id,
                    created_by=principal.user_id,
                    contract_id=contract.id,
                    payment_type_code=row["component"],
                    net=amount,
                    gross=amount,
                    valid_from=plan.valid_from,
                    reason=PaymentReason.ADJUSTMENT_FROM_STATEMENT,
                    reserve_id=_bound_reserve(unit_map.get(row["unit_id"]), row["component"]),
                ),
            )
            created += 1
            if plan.payment_rhythm != "monthly" and contract.id not in scheduled:
                changed = await _ensure_schedule(session, contract, plan, principal)
                scheduled[contract.id] = changed
        plan.applied_at = datetime.now(UTC)
        # M24-04: earlier applied plans of the ledger become obsolete (Fortgeltung ends).
        for older in (
            await session.scalars(
                select(EconomicPlan).where(
                    EconomicPlan.ledger_id == plan.ledger_id,
                    EconomicPlan.id != plan.id,
                    EconomicPlan.applied_at.is_not(None),
                    EconomicPlan.obsolete_at.is_(None),
                    EconomicPlan.valid_from <= plan.valid_from,
                )
            )
        ).all():
            older.obsolete_at = plan.applied_at
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="economic_plan.applied",
            entity_type="economic_plan",
            entity_id=plan.id,
            actor_user_id=principal.user_id,
            payload={
                "payments": created,
                "snapshot_hash": plan.snapshot_hash,
                "counts": preview["counts"],
                "posted_months": preview["posted_months"],
            },
        )
        await session.flush()
        return _plan_out(plan) | {
            "payments_created": created,
            "schedules_set": sum(1 for v in scheduled.values() if v),
            "counts": preview["counts"],
            "posted_months": preview["posted_months"],
        }


# Annual statement -----------------------------------------------------------------------


@router.post("/statements", status_code=201, summary="Hausgeldabrechnung (Entwurf)")
async def create_statement(
    body: HoaStatementIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _hoa_ledger(session, body.ledger_id)
        row = HoaStatement(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return _st_out(row)


@router.post(
    "/statements/{statement_id}/costs",
    status_code=201,
    summary="Kostenposition mit Verteilungsgrundlage",
)
async def add_cost(
    statement_id: uuid.UUID,
    body: HoaCostIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.status is not StatementStatus.DRAFT:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über neue Version."
            )
        if body.labour_cost_35a is not None and body.labour_cost_35a > body.amount:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Lohnanteil § 35a größer als der Betrag."
            )
        entry = await _same_ledger_entry(session, st.ledger_id, body.journal_entry_id)
        if body.sub_community_id is not None:
            from mhvp.hoa.levy_cost import check_sub_community

            await check_sub_community(session, st.ledger_id, body.sub_community_id)
        data = body.model_dump()
        if entry is not None and data["document_id"] is None:
            data["document_id"] = entry.document_id
        item = HoaCostItem(tenant_id=principal.tenant_id, statement_id=st.id, **data)
        session.add(item)
        await session.flush()
        return {"id": item.id}


@router.post(
    "/statements/{statement_id}/calculate",
    summary="Berechnen: Spitze, Rückstände, Rücklage, Vermögensbericht",
)
async def calculate_statement(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.status is not StatementStatus.DRAFT:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits berechnet.")
        ledger = await _hoa_ledger(session, st.ledger_id)
        items = list(
            (
                await session.scalars(select(HoaCostItem).where(HoaCostItem.statement_id == st.id))
            ).all()
        )
        if not items:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine Kostenpositionen.")
        result = await calc.statement_results(session, st, ledger, items)
        result["asset_report"] = await calc.asset_report(
            session, ledger, st.year, result["reserve"]["closing"]
        )
        # W04 (A60): Gesamtgeldfluss and Überleitung are part of the statement snapshot.
        result["reconciliation"] = await calc.cash_flow_reconciliation(
            session,
            ledger,
            st.year,
            sum((i.amount for i in items), Decimal("0.00")),
            list(st.reconciliation_notes or []),
        )
        # M24-07, M24-05, M24-01: key figures, § 35a block and reserves per position.
        result["key_figures"] = calc.statement_key_figures(result)
        result["section_35a"] = await calc.section_35a_block(session, st, ledger, items)
        reserves = list(
            (
                await session.scalars(
                    select(HoaReserve)
                    .where(HoaReserve.ledger_id == st.ledger_id)
                    .order_by(HoaReserve.name)
                )
            ).all()
        )
        if reserves:
            plan = await session.scalar(
                select(EconomicPlan)
                .where(
                    EconomicPlan.ledger_id == st.ledger_id,
                    EconomicPlan.year == st.year,
                    EconomicPlan.resolution_id.is_not(None),
                )
                .order_by(EconomicPlan.version.desc())
            )
            plan_items = (
                list(
                    (
                        await session.scalars(select(PlanItem).where(PlanItem.plan_id == plan.id))
                    ).all()
                )
                if plan
                else []
            )
            movements = list(
                (
                    await session.scalars(
                        select(HoaReserveMovement).where(HoaReserveMovement.statement_id == st.id)
                    )
                ).all()
            )
            result["reserve"]["positions"] = calc.reserve_positions(
                reserves,
                plan_items,
                movements,
                {
                    k: Decimal(v)
                    for k, v in result["reserve"]["contributions_paid_by_reserve"].items()
                },
            )
            from mhvp.hoa.reserves import add_opening_closing

            await add_opening_closing(session, reserves, result["reserve"]["positions"], st.year)
            # AE08 (P07-02): split of the unbound rest by plan ratio, proposal behind a switch.
            from mhvp.hoa.reserve_split import add_proposal, split_mode

            if await split_mode(session) == "plan_ratio_proposal":
                add_proposal(
                    result["reserve"]["positions"],
                    Decimal(result["reserve"]["contributions_paid_unassigned"]),
                )
        # M24-03: loans shown per unit only when the manager entered a loan with key and
        # basis; the shares are information and never change the result.
        if st.loan_allocation:
            result["loans"] = await calc.loan_statement_block(
                session, ledger, st.year, list(st.loan_allocation)
            )
            for unit in result["units"]:
                share = result["loans"]["per_unit"].get(unit["unit_id"], {})
                unit["loan_interest_share"] = share.get("interest", "0.00")
                unit["loan_repayment_share"] = share.get("repayment", "0.00")
        st.snapshot, st.snapshot_hash = result, calc.digest(result)
        st.status = StatementStatus.CALCULATED
        await session.flush()
        return _st_out(st)


class LoanAllocationIn(HoaBaseIn):
    """One loan shown in the statement (M24-03): key, components and the documented basis."""

    loan_id: uuid.UUID
    allocation_key_id: uuid.UUID
    components: list[str] = Field(default=["interest", "repayment"], min_length=1)
    basis: str = Field(min_length=5, max_length=500)


class LoanAllocationsIn(HoaBaseIn):
    loans: list[LoanAllocationIn] = Field(max_length=50)


@router.put(
    "/statements/{statement_id}/loan-allocation",
    summary="Darlehen in der Jahresabrechnung ausweisen (M24-03, nur Ausweis)",
)
async def put_loan_allocation(
    statement_id: uuid.UUID,
    body: LoanAllocationsIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """Only while the statement is a draft; the next calculation adds the block `loans` to
    the snapshot (year figures from booked items or the schedule, distribution by the key,
    residual debt at the year end). The shares never enter the result (open decision M24-03).
    Loan and key must belong to the community of the statement."""
    from mhvp.hoa.models import HoaLoan
    from mhvp.properties.models import AllocationKey

    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.status is not StatementStatus.DRAFT:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Darlehensausweis nur im Entwurf.")
        ledger = await _hoa_ledger(session, st.ledger_id)
        seen: set[uuid.UUID] = set()
        rows: list[dict[str, Any]] = []
        for item in body.loans:
            if item.loan_id in seen:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Darlehen doppelt angegeben.")
            seen.add(item.loan_id)
            if any(c not in calc.LOAN_COMPONENTS for c in item.components):
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Bestandteile nur interest oder repayment."
                )
            loan = await session.get(HoaLoan, item.loan_id)
            if loan is None or loan.ledger_id != ledger.id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Darlehen gehört nicht zu dieser GdWE."
                )
            key = await session.get(AllocationKey, item.allocation_key_id)
            if key is None or key.property_id != ledger.property_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Verteilerschlüssel gehört nicht zum Objekt."
                )
            rows.append(
                {
                    "loan_id": str(item.loan_id),
                    "allocation_key_id": str(item.allocation_key_id),
                    "components": sorted(set(item.components)),
                    "basis": item.basis,
                }
            )
        st.loan_allocation = rows
        st.updated_by = principal.user_id
        await session.flush()
        return _st_out(st)


@router.put(
    "/statements/{statement_id}/reconciliation-notes",
    summary="Erklärte Differenzen der Überleitungsrechnung (W04)",
)
async def put_reconciliation_notes(
    statement_id: uuid.UUID,
    body: ReconciliationNotesIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """Only while the statement is a draft or calculated; the calculated snapshot keeps its
    reconciliation, the package always shows the live one with these notes."""
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.status not in (StatementStatus.DRAFT, StatementStatus.CALCULATED):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Erklärungen nur vor der internen Freigabe."
            )
        st.reconciliation_notes = [
            {"code": n.code, "amount": str(n.amount), "note": n.note} for n in body.notes
        ]
        st.updated_by = principal.user_id
        await session.flush()
        return _st_out(st)


async def _file_unit_statements(
    session: AsyncSession, request: Request, st: HoaStatement, principal: TenantPrincipal
) -> None:
    from mhvp.documents.blobs import BlobStore
    from mhvp.hoa import statement_archive, statement_pdf

    ledger = await _hoa_ledger(session, st.ledger_id)
    try:
        blobs = BlobStore(request.app.state.settings)
    except ProblemError as exc:
        # Filing is a convenience copy of the deterministic PDF: without object storage the
        # transition still happens and the PDF is archived on first retrieval.
        _log.warning("hoa statement %s: filing skipped, %s", st.id, exc.detail)
        return
    snapshot, snap_hash = st.snapshot or {}, st.snapshot_hash or ""
    for unit in snapshot.get("units", []):

        def render(u: dict[str, Any] = unit) -> bytes:
            return statement_pdf.render(st.year, snapshot, u, snap_hash)

        await statement_archive.archived_pdf(
            session, blobs, st=st, property_id=ledger.property_id,
            legal_entity_id=ledger.legal_entity_id, unit=unit,
            render=render, created_by=principal.user_id,
        )  # fmt: skip


@router.post("/statements/{statement_id}/transition", summary="Statuswechsel (6.9.3, W06)")
async def transition_statement(
    statement_id: uuid.UUID,
    body: HoaTransitionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    if body.target in (StatementStatus.ISSUED, StatementStatus.DUE):
        await ensure_release_gate_open(
            ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
        )
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.target is StatementStatus.POSTED:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Buchung über den Buchungsendpunkt.")
        if body.target is StatementStatus.INTERNALLY_APPROVED:
            # AP21 / GAM-109: sub community positions without basis, lock only with the switch.
            from mhvp.hoa.levy_cost import ensure_sub_community_basis

            await ensure_sub_community_basis(session, st.id)
        await _move(session, st, body, principal)
        if body.target in (StatementStatus.ISSUED, StatementStatus.DUE) and st.snapshot:
            # GAB-06: at provision every individual statement is filed once (G4 checked above).
            await _file_unit_statements(session, request, st, principal)
        if body.target is StatementStatus.INTERNALLY_APPROVED:
            # Q12 webhook statement.confirmed: a Hausgeldabrechnung counts as confirmed at the
            # internal approval (A-R07-01, docs/ASSUMPTIONS.md); no legal effect, no resolution.
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="statement.confirmed",
                entity_type="hoa_statement",
                entity_id=st.id,
                actor_user_id=principal.user_id,
                payload={"kind": "hoa", "status": body.target.value},
            )
        lock_info: dict[str, Any] = {}
        if body.target is StatementStatus.LOCKED:
            # GAE-02 (AE20): closing the WEG statement locks the object period, only with the
            # tenant switch auto_lock_on_close (default off: proposal only).
            from mhvp.accounting import period_lock
            from mhvp.accounting.models import Ledger as _Ledger

            hoa_ledger = await session.get(_Ledger, st.ledger_id)
            if hoa_ledger is not None and hoa_ledger.property_id is not None:
                lock_info = await period_lock.lock_for_closed_statement(
                    session,
                    tenant_id=principal.tenant_id,
                    user_id=principal.user_id,
                    source="hoa_statement",
                    statement_id=st.id,
                    ledger_id=st.ledger_id,
                    property_id=hoa_ledger.property_id,
                    period_from=date(st.year, 1, 1),
                    period_to=date(st.year, 12, 31),
                )
        await session.flush()
        return {**_st_out(st), **lock_info}


@router.post("/statements/{statement_id}/post", summary="Abrechnungsergebnis buchen (G4)")
async def post_statement(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Only the resolved result per unit (Nachschuss or Anpassung) is posted against the owner at
    the resolution date; arrears are not duplicated (7.3 Abrechnungsergebnis, D01, D02)."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import (
        EntryKind,
        EntrySource,
        JournalEntry,
        Ledger,
        LedgerAccount,
        PaymentTypeAccount,
    )
    from mhvp.contracts.models import DebtorAccountReservation

    await ensure_release_gate_open(
        ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.status is StatementStatus.POSTED:
            return _st_out(st)  # already posted: a later contest never reverses anything (D54)
        resolution = await session.get(Resolution, st.resolution_id) if st.resolution_id else None
        if resolution is not None and resolution.status not in BINDING:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=f"Ergebnisbuchung gesperrt: Beschluss im Status {resolution.status}, "
                "nicht bestandskräftig (D54).",
            )
        await _move(session, st, HoaTransitionIn(target=StatementStatus.POSTED), principal)
        ledger = await session.get(Ledger, st.ledger_id)
        mapping = await session.scalar(
            select(PaymentTypeAccount).where(
                PaymentTypeAccount.ledger_id == st.ledger_id,
                PaymentTypeAccount.payment_type_code == "statement_result",
            )
        )
        if ledger is None or resolution is None or mapping is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Konto für Abrechnungsergebnisse (Zahlungsart statement_result) fehlt.",
            )
        # Debtor accounts reserved after the ledger was created (owner change, D15) are adopted
        # here like in receivable runs and special levies (finding 26.09.2026).
        await acc.sync_debtor_accounts(session, ledger)
        ids = []
        for unit in (st.snapshot or {}).get("units", []):
            amount = Decimal(unit["result"])
            if amount == 0:
                continue
            contract = await calc.owner_at(
                session, uuid.UUID(unit["unit_id"]), resolution.decided_on
            )
            reservation = (
                await session.get(DebtorAccountReservation, contract.debtor_account_id)
                if contract
                else None
            )
            debtor = (
                await session.scalar(
                    select(LedgerAccount).where(
                        LedgerAccount.ledger_id == ledger.id,
                        LedgerAccount.number == reservation.number,
                    )
                )
                if reservation
                else None
            )
            if contract is None or debtor is None:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail=f"Kein Eigentümer oder Debitor für Einheit {unit['unit_number']}.",
                )
            value = abs(amount)
            lines = [
                acc.LineIn(debtor.id, value, Decimal("0")),
                acc.LineIn(mapping.account_id, Decimal("0"), value),
            ]
            if amount < 0:
                lines = [
                    acc.LineIn(debtor.id, Decimal("0"), value),
                    acc.LineIn(mapping.account_id, value, Decimal("0")),
                ]
            entry = JournalEntry(
                tenant_id=st.tenant_id,
                created_by=principal.user_id,
                ledger_id=ledger.id,
                booking_date=resolution.decided_on,
                due_date=resolution.decided_on,
                accrual_date=date(st.year, 12, 31),
                text=f"Abrechnungsergebnis {st.year} Einheit {unit['unit_number']}",
                kind=EntryKind.STATEMENT_RESULT,
                contract_id=contract.id,
                source=EntrySource.STATEMENT,
                idempotency_key=f"hoa-statement:{st.id}:{unit['unit_id']}",
            )
            await acc.write_draft(session, ledger, entry, lines, [])
            await acc.post(session, ledger, entry, principal.user_id)
            ids.append(str(entry.id))
        st.posted_entry_ids = ids
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_statement.posted",
            entity_type="hoa_statement",
            entity_id=st.id,
            actor_user_id=principal.user_id,
            payload={"entries": len(ids)},
        )
        await session.flush()
        return _st_out(st)


@router.post(
    "/statements/{statement_id}/new-version",
    status_code=201,
    summary="Neue Version (Beschluss bleibt an alter Version)",
)
async def new_version(
    statement_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
    body: HoaNewVersionIn | None = None,
) -> dict[str, Any]:
    from mhvp.hoa.correction import CORRECTION_REASONS

    if body is not None and body.reason is not None and body.reason not in CORRECTION_REASONS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannter Korrekturgrund.")
    async with tenant_tx(request, principal) as session:
        old = await session.get(HoaStatement, statement_id)
        if old is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        basis_resolution = (
            await session.get(Resolution, body.resolution_id)
            if body is not None and body.resolution_id is not None
            else None
        )
        if body is not None and body.resolution_id is not None and basis_resolution is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if basis_resolution is not None:
            # GAH-403: the correcting resolution must belong to the GdWE of the ledger.
            from mhvp.accounting.models import Ledger as _NvLedger

            nv_ledger = await session.get(_NvLedger, old.ledger_id)
            if nv_ledger is None or nv_ledger.legal_entity_id != basis_resolution.legal_entity_id:
                raise ProblemError(ErrorCodes.HOA_CORRECTION_RESOLUTION_FOREIGN)
        # GAG-15 (GAF-16): the correcting resolution runs through the majority check of
        # M25-01 (display and protocol note only, no status change, no block).
        majority = (
            await check_resolution(session, principal, basis_resolution)
            if basis_resolution is not None
            else None
        )
        new = HoaStatement(
            tenant_id=old.tenant_id,
            created_by=principal.user_id,
            ledger_id=old.ledger_id,
            year=old.year,
            version=old.version + 1,
            supersedes_id=old.id,
            reserve_opening=old.reserve_opening,
            reserve_withdrawals=old.reserve_withdrawals,
            reserve_interest=old.reserve_interest,
            reconciliation_notes=list(old.reconciliation_notes or []),
            loan_allocation=list(old.loan_allocation or []),
            correction_reason=body.reason if body else None,
            correction_basis=body.basis if body else None,
            correction_resolution_id=body.resolution_id if body else None,
        )
        session.add(new)
        await session.flush()
        from mhvp.hoa.meetings import outdate_audit_items

        await outdate_audit_items(session, old.id)
        for item in (
            await session.scalars(select(HoaCostItem).where(HoaCostItem.statement_id == old.id))
        ).all():
            session.add(
                HoaCostItem(
                    tenant_id=old.tenant_id,
                    statement_id=new.id,
                    label=item.label,
                    amount=item.amount,
                    allocation_key_id=item.allocation_key_id,
                    basis=item.basis,
                    account_id=item.account_id,
                    journal_entry_id=item.journal_entry_id,
                    document_id=item.document_id,
                    labour_cost_35a=item.labour_cost_35a,
                    basis_resolution_id=item.basis_resolution_id,
                    basis_document_id=item.basis_document_id,
                    sub_community_id=item.sub_community_id,
                )
            )
        await session.flush()
        return _st_out(new) | {"correction_majority_check": majority}


# Read endpoints for the CRM screens -------------------------------------------------------


@router.get(
    "/plans", summary="Wirtschaftspläne eines Buchungskreises", dependencies=[Depends(strict_query)]
)
async def list_plans(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(EconomicPlan)
            .where(EconomicPlan.ledger_id == ledger_id)
            .order_by(EconomicPlan.year.desc(), EconomicPlan.version.desc())
        )
        return [_plan_out(p) | {"snapshot": None} for p in rows.all()]


@router.get("/plans/{plan_id}", summary="Wirtschaftsplan mit Positionen")
async def get_plan(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        items = (await session.scalars(select(PlanItem).where(PlanItem.plan_id == plan.id))).all()
        return _plan_out(plan) | {
            "items": [
                {
                    "id": i.id,
                    "label": i.label,
                    "component": i.component,
                    "amount": i.amount,
                    "allocation_key_id": i.allocation_key_id,
                }
                for i in items
            ]
        }


def _snapshot_diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Compare two calculated snapshots per unit and per cost position (D14). Values are
    strings of Decimals; the difference is new minus old."""
    unit_fields = (
        "cost_share",
        "advances_resolved",
        "advances_paid",
        "result",
        "arrears",
        "information_total",
    )

    def triple(a: str | None, b: str | None) -> dict[str, str]:
        da, db = Decimal(a or "0"), Decimal(b or "0")
        return {"old": str(da), "new": str(db), "difference": str(db - da)}

    old_units = {u["unit_number"]: u for u in old.get("units", [])}
    new_units = {u["unit_number"]: u for u in new.get("units", [])}
    units = [
        {
            "unit_number": number,
            "in_old": number in old_units,
            "in_new": number in new_units,
            **{
                f: triple(old_units.get(number, {}).get(f), new_units.get(number, {}).get(f))
                for f in unit_fields
            },
        }
        for number in sorted(set(old_units) | set(new_units))
    ]
    # Position splits are keyed by unit id in the snapshot; shown per unit number here.
    number_of = {u["unit_id"]: u["unit_number"] for u in [*old_units.values(), *new_units.values()]}
    old_pos = {p["label"]: p for p in old.get("positions", [])}
    new_pos = {p["label"]: p for p in new.get("positions", [])}
    positions = []
    for label in sorted(set(old_pos) | set(new_pos)):
        o, n = old_pos.get(label, {}), new_pos.get(label, {})
        o_split = {number_of.get(k, k): v for k, v in o.get("split", {}).items()}
        n_split = {number_of.get(k, k): v for k, v in n.get("split", {}).items()}
        positions.append(
            {
                "label": label,
                "in_old": label in old_pos,
                "in_new": label in new_pos,
                "amount": triple(o.get("amount"), n.get("amount")),
                "split": {
                    number: triple(o_split.get(number), n_split.get(number))
                    for number in sorted(set(o_split) | set(n_split))
                },
            }
        )
    return {
        "total_costs": triple(old.get("total_costs"), new.get("total_costs")),
        "units": units,
        "positions": positions,
    }


@router.get(
    "/statements/{statement_id}/diff",
    summary="Versionsvergleich zweier Hausgeldabrechnungen (D14)",
)
async def diff_hoa_statement(
    statement_id: uuid.UUID,
    against: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """``against`` is the older version (old), ``statement_id`` the newer one (new). Both must
    belong to the same ledger (community) and year, otherwise 422; both need a snapshot."""
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id)
        other = await session.get(HoaStatement, against)
        if st is None or other is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.ledger_id != other.ledger_id or st.year != other.year:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Vergleich nur zwischen Versionen derselben Gemeinschaft und Periode.",
            )
        if st.id == other.id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Eine Version mit sich selbst.")
        if not st.snapshot or not other.snapshot:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Beide Versionen müssen berechnet sein.")
        return {
            "statement_id": st.id,
            "against_id": other.id,
            "year": st.year,
            "old": {"id": other.id, "version": other.version, "snapshot_hash": other.snapshot_hash},
            "new": {"id": st.id, "version": st.version, "snapshot_hash": st.snapshot_hash},
        } | _snapshot_diff(other.snapshot, st.snapshot)


CORRECTION_NOTE = (
    "Korrekturbericht zur Information: keine Buchung, keine Forderung, kein Versand. Die "
    "Rechtsfolge einer Korrektur bleibt offen (P02, Gate G4)."
)


class HoaCorrectionReportSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


async def correction_report_enabled(session: AsyncSession) -> bool:
    """AF08 / GAE-13: tenant switch, default off (no row means off)."""
    from mhvp.hoa.models import HoaCorrectionReportSetting

    return bool(await session.scalar(select(HoaCorrectionReportSetting.enabled)))


@router.get("/correction-report-settings", summary="Korrekturbericht (Schalter)")
async def get_correction_report_setting(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return {"enabled": await correction_report_enabled(session), "note": CORRECTION_NOTE}


class HoaCorrectionReportSettingOut(BaseModel):
    """AK11 (GAI-304): typed response, ``extra="allow"`` keeps later fields."""

    model_config = ConfigDict(extra="allow")
    enabled: bool
    note: str


@router.put(
    "/correction-report-settings",
    summary="Korrekturbericht (Schalter setzen)",
    response_model=HoaCorrectionReportSettingOut,
)
async def put_correction_report_setting(
    body: HoaCorrectionReportSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> dict[str, Any]:
    from mhvp.hoa.models import HoaCorrectionReportSetting

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(HoaCorrectionReportSetting).with_for_update())
        if row is None:
            row = HoaCorrectionReportSetting(tenant_id=principal.tenant_id, enabled=body.enabled)
            session.add(row)
        row.enabled = body.enabled
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_correction_report_setting.updated",
            entity_type="hoa_correction_report_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled},
        )
        return {"enabled": body.enabled, "note": CORRECTION_NOTE}


@router.get(
    "/statements/{statement_id}/correction-report",
    summary="Korrekturbericht je Eigentümer mit Heizkostenüberleitung (P02, D09)",
    dependencies=[Depends(strict_query)],
)
async def hoa_correction_report(
    statement_id: uuid.UUID,
    against: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Display only. `against` is the older version. No posting, no claim, no dispatch."""
    from mhvp.hoa import correction

    async with tenant_tx(request, principal) as session:
        if not await correction_report_enabled(session):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Korrekturbericht ist für diesen Mandanten nicht eingeschaltet.",
            )
        st = await session.get(HoaStatement, statement_id)
        other = await session.get(HoaStatement, against)
        if st is None or other is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.ledger_id != other.ledger_id or st.year != other.year or st.id == other.id:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Vergleich nur zwischen zwei Versionen derselben Gemeinschaft und Periode.",
            )
        if not st.snapshot or not other.snapshot:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Beide Versionen müssen berechnet sein.")
        return (
            {
                "statement_id": st.id,
                "against_id": other.id,
                "year": st.year,
                "old": {"id": other.id, "version": other.version},
                "new": {"id": st.id, "version": st.version},
            }
            | _snapshot_diff(other.snapshot, st.snapshot)
            | correction.owner_diff(other.snapshot, st.snapshot)
            | {
                "heating": correction.heating_block(other.snapshot, st.snapshot),
                "correction": {
                    "reason": st.correction_reason,
                    "basis": st.correction_basis,
                    "resolution_id": st.correction_resolution_id,
                    "legal_note": correction.LEGAL_NOTE,
                },
            }
        )


@router.get(
    "/statements",
    summary="Hausgeldabrechnungen eines Buchungskreises",
    dependencies=[Depends(strict_query)],
)
async def list_hoa_statements(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(HoaStatement)
            .where(HoaStatement.ledger_id == ledger_id)
            .order_by(HoaStatement.year.desc(), HoaStatement.version.desc())
        )
        return [_st_out(s) | {"snapshot": None} for s in rows.all()]


@router.get("/statements/{statement_id}", summary="Hausgeldabrechnung mit Kostenpositionen")
async def get_hoa_statement(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        items = (
            await session.scalars(select(HoaCostItem).where(HoaCostItem.statement_id == st.id))
        ).all()
        return _st_out(st) | {"cost_items": [_cost_out(i) for i in items]}


# Earmarked reserves and ledger costs (M24-01, M24-02) -----------------------------------


def _reserve_out(r: HoaReserve) -> dict[str, Any]:
    from mhvp.hoa.reserves import reserve_out

    return reserve_out(r)


@router.post("/reserves", status_code=201, summary="Zweckgebundene Rücklage anlegen (W08)")
async def create_reserve(
    body: HoaReserveIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        from mhvp.hoa.reserves import check_reserve_refs

        ledger = await _hoa_ledger(session, body.ledger_id)
        await check_reserve_refs(
            session, ledger, account_id=body.account_id, bank_account_id=body.bank_account_id
        )
        row = HoaReserve(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return _reserve_out(row)


@router.get(
    "/reserves", summary="Rücklagen eines Buchungskreises", dependencies=[Depends(strict_query)]
)
async def list_reserves(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(HoaReserve).where(HoaReserve.ledger_id == ledger_id).order_by(HoaReserve.name)
        )
        return [_reserve_out(r) for r in rows.all()]


@router.post(
    "/statements/{statement_id}/reserve-movements",
    status_code=201,
    summary="Mittelverwendung, Steuern, Gebühren oder Zinsen je Rücklage",
)
async def add_reserve_movement(
    statement_id: uuid.UUID,
    body: HoaReserveMovementIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.status is not StatementStatus.DRAFT:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über neue Version."
            )
        reserve = await session.get(HoaReserve, body.reserve_id)
        if reserve is None or reserve.ledger_id != st.ledger_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Rücklage aus anderem Buchungskreis.")
        await _same_ledger_entry(session, st.ledger_id, body.journal_entry_id)
        row = HoaReserveMovement(
            tenant_id=principal.tenant_id,
            statement_id=st.id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return {"id": row.id}


@router.post(
    "/statements/{statement_id}/costs/from-ledger",
    status_code=201,
    summary="Kostenpositionen aus gebuchten Belegen eines Kontos übernehmen (W12)",
)
async def costs_from_ledger(
    statement_id: uuid.UUID,
    body: HoaCostsFromLedgerIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """One position per posted entry on the account in the statement year (debit minus credit
    of the account lines), linked to entry and receipt. Entries already taken are skipped;
    a net credit is not taken and listed (correction by reversal stays in accounting)."""
    from mhvp.accounting.models import EntryStatus, JournalEntry, JournalLine, LedgerAccount

    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id, with_for_update=True)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.status is not StatementStatus.DRAFT:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über neue Version."
            )
        account = await session.get(LedgerAccount, body.account_id)
        if account is None or account.ledger_id != st.ledger_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Konto aus anderem Buchungskreis.")
        taken = set(
            (
                await session.scalars(
                    select(HoaCostItem.journal_entry_id).where(
                        HoaCostItem.statement_id == st.id,
                        HoaCostItem.journal_entry_id.is_not(None),
                    )
                )
            ).all()
        )
        rows = (
            await session.execute(
                select(
                    JournalEntry,
                    func.sum(JournalLine.debit - JournalLine.credit),
                )
                .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
                .where(
                    JournalLine.account_id == account.id,
                    JournalEntry.status == EntryStatus.POSTED,
                    JournalEntry.booking_date.between(date(st.year, 1, 1), date(st.year, 12, 31)),
                )
                .group_by(JournalEntry.id)
                .order_by(JournalEntry.booking_date, JournalEntry.number)
            )
        ).all()
        created, skipped = [], []
        # An entry and its reversal inside the statement year cancel out (B03): neither is
        # taken, otherwise the reversed cost would count while its reversal is a net credit.
        in_year = {entry.id for entry, _net in rows}
        for entry, net in rows:
            amount = Decimal(net)
            if entry.id in taken:
                skipped.append({"journal_entry_id": entry.id, "reason": "already_taken"})
                continue
            if entry.reverses_id is not None and entry.reverses_id in taken:
                # The taken cost was reversed later: the position must be removed by a person.
                skipped.append({"journal_entry_id": entry.id, "reason": "reverses_taken_entry"})
                continue
            if (entry.reversed_by_id is not None and entry.reversed_by_id in in_year) or (
                entry.reverses_id is not None and entry.reverses_id in in_year
            ):
                skipped.append({"journal_entry_id": entry.id, "reason": "reversed"})
                continue
            if amount <= 0:
                skipped.append({"journal_entry_id": entry.id, "reason": "net_credit"})
                continue
            item = HoaCostItem(
                tenant_id=principal.tenant_id,
                statement_id=st.id,
                label=f"{account.number} {entry.text}"[:200],
                amount=amount,
                allocation_key_id=body.allocation_key_id,
                basis=body.basis,
                account_id=account.id,
                journal_entry_id=entry.id,
                document_id=entry.document_id,
                basis_resolution_id=body.basis_resolution_id,
                basis_document_id=body.basis_document_id,
            )
            session.add(item)
            await session.flush()
            created.append(_cost_out(item))
        return {"created": created, "skipped": skipped}


@router.get(
    "/statements/{statement_id}/units/{unit_id}/pdf",
    summary="Einzelabrechnung als PDF (Entwurf, nur mit Freigabestufe G4)",
)
async def unit_statement_pdf(
    statement_id: uuid.UUID,
    unit_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    from mhvp.documents.blobs import BlobStore
    from mhvp.hoa import statement_archive, statement_pdf

    await ensure_release_gate_open(
        ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.snapshot is None or st.status in (StatementStatus.DRAFT, StatementStatus.CALCULATED):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ausgabe nur nach interner Freigabe.")
        unit = next((u for u in st.snapshot.get("units", []) if u["unit_id"] == str(unit_id)), None)
        if unit is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        snapshot, snap_hash = st.snapshot, st.snapshot_hash or ""
        ledger = await _hoa_ledger(session, st.ledger_id)
        # GAB-06: filed once in the DMS, every later output returns the filed bytes.
        content, _doc = await statement_archive.archived_pdf(
            session,
            BlobStore(request.app.state.settings),
            st=st,
            property_id=ledger.property_id,
            legal_entity_id=ledger.legal_entity_id,
            unit=unit,
            render=lambda: statement_pdf.render(st.year, snapshot, unit, snap_hash),
            created_by=principal.user_id,
        )
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="hausgeldabrechnung-{st.year}-{unit["unit_number"]}.pdf"'
                )
            },
        )


@router.get(
    "/statements/{statement_id}/pdf",
    summary="Gesamtabrechnung als PDF auf dem Briefbogen des Mandanten (Entwurf, G4)",
)
async def statement_total_pdf(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    """M24-03 (7.8 W12): all values from the stored snapshot, nothing recalculated. Needs an
    open G4 and the internal approval; the tenant's letterhead is required (no invented
    company data): an incomplete letterhead is a conflict, not a silent plain document."""
    from mhvp.documents import letters as letter_blocks
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.hoa import statement_archive, statement_pdf
    from mhvp.properties.models import LegalEntity, Property
    from mhvp.workspace.services import local_today

    await ensure_release_gate_open(
        ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if st.snapshot is None or st.status in (StatementStatus.DRAFT, StatementStatus.CALCULATED):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ausgabe nur nach interner Freigabe.")
        ledger = await _hoa_ledger(session, st.ledger_id)
        blobs = BlobStore(request.app.state.settings)
        # GAB-06: an already filed total statement is returned unchanged (letter date included).
        filed = await statement_archive.find_archived(
            session, st, statement_archive.archive_filename(st, None)
        )
        if filed is not None:
            content, _doc = await statement_archive.archived_pdf(
                session, blobs, st=st, property_id=ledger.property_id,
                legal_entity_id=ledger.legal_entity_id, unit=None,
                render=lambda: b"", created_by=principal.user_id,
            )  # fmt: skip
            return Response(
                content=content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="gesamtabrechnung-{st.year}.pdf"'
                },
            )
        prop = await session.get(Property, ledger.property_id)
        entity = await session.get(LegalEntity, ledger.legal_entity_id)
        head = await doc_services.letterhead(session, blobs)
        property_line = (
            f"{prop.number} {prop.name}, {prop.street or ''} {prop.house_number or ''}, "
            f"{prop.postal_code or ''} {prop.city or ''}".replace("  ", " ").strip(" ,")
            if prop
            else str(ledger.property_id)
        )
        letter = statement_pdf.build_total_letter(
            st.year,
            st.snapshot,
            st.snapshot_hash or "",
            recipient_lines=[entity.name] if entity else [],
            property_line=property_line,
            letter_date=local_today(),
            signatory=[s for s in (str(head.company.get("name", "")),) if s],
        )
        content, _doc = await statement_archive.archived_pdf(
            session, blobs, st=st, property_id=ledger.property_id,
            legal_entity_id=ledger.legal_entity_id, unit=None,
            render=lambda: letter_blocks.render_pdf(head, letter), created_by=principal.user_id,
        )  # fmt: skip
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="gesamtabrechnung-{st.year}.pdf"'},
    )
