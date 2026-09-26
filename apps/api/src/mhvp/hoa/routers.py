"""WEG endpoints (/api/v1/hoa, M24): economic plan, resolutions, annual statement with asset
report. Issuing requires the resolution bound to the snapshot; posting results needs G4."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.status import StatementStatus, TransitionError, check_transition
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.hoa import calc
from mhvp.hoa.majority import SUBJECT_PATTERN, check_resolution
from mhvp.hoa.models import EconomicPlan, HoaCostItem, HoaStatement, PlanItem, Resolution

router = APIRouter(prefix="/hoa", tags=["WEG"])
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


class HoaPlanItemIn(HoaBaseIn):
    label: str = Field(min_length=1, max_length=200)
    component: str = Field(pattern="^(hoa_fee|reserve)$")
    amount: Decimal = Field(gt=0)
    allocation_key_id: uuid.UUID
    account_id: uuid.UUID | None = None


class HoaVotesIn(HoaBaseIn):
    """Recorded tally of an external meeting for the majority check (M25-01)."""

    principle: str = Field(pattern="^(head|mea|unit)$")
    yes: Decimal = Field(ge=0)
    no: Decimal = Field(ge=0)
    abstain: Decimal = Field(default=Decimal("0"), ge=0)
    eligible: Decimal | None = Field(default=None, gt=0)


class HoaResolutionIn(HoaBaseIn):
    legal_entity_id: uuid.UUID
    decided_on: date
    subject: str = Field(min_length=3, max_length=2000)
    wording: str = Field(min_length=3, max_length=20000)
    status: str = Field(
        pattern="^(positive|negative|final|contested|annulled|legally_binding|void)$"
    )
    kind: str = Field(default="external", pattern="^(meeting|circular|court|external)$")
    snapshot_hash: str | None = Field(default=None, max_length=64)
    subject_type: str | None = Field(
        default=None, pattern="^(economic_plan|hoa_statement|special_levy|other)$"
    )
    subject_id: uuid.UUID | None = None
    majority_basis: str | None = Field(default=None, max_length=4000)
    subject_kind: str | None = Field(default=None, pattern=SUBJECT_PATTERN)
    votes: HoaVotesIn | None = None


class HoaResolutionPatch(HoaBaseIn):
    status: str = Field(
        pattern="^(positive|negative|final|contested|annulled|legally_binding|void)$"
    )


class HoaStatementIn(HoaBaseIn):
    ledger_id: uuid.UUID
    year: int = Field(ge=2000, le=2100)
    reserve_opening: Decimal = Decimal("0.00")
    reserve_withdrawals: Decimal = Field(default=Decimal("0.00"), ge=0)
    reserve_interest: Decimal = Decimal("0.00")


class HoaCostIn(HoaBaseIn):
    label: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0)
    allocation_key_id: uuid.UUID
    basis: str = Field(min_length=3, max_length=2000)
    account_id: uuid.UUID | None = None


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
    }


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
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Resolution, resolution_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="resolution.status_changed",
            entity_type="resolution",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"from": row.status, "to": body.status},
        )
        row.status = body.status
        await session.flush()
        return {"id": row.id, "status": row.status}


@router.get("/resolutions", summary="Beschluss-Sammlung")
async def list_resolutions(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(Resolution)
            .where(Resolution.legal_entity_id == legal_entity_id)
            .order_by(Resolution.number)
        )
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
            }
            for r in rows.all()
        ]


# Economic plan ---------------------------------------------------------------------------


@router.post("/plans", status_code=201, summary="Wirtschaftsplan (Entwurf)")
async def create_plan(
    body: HoaPlanIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _hoa_ledger(session, body.ledger_id)
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
            session, ledger.property_id, items, date(plan.year, 1, 1), date(plan.year, 12, 31)
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


@router.post(
    "/plans/{plan_id}/apply", summary="Beschlossene Vorschüsse als Vertragszahlungen übernehmen"
)
async def apply_plan(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Only after the resolution; creates monthly payments per ownership contract from valid_from
    (W02: the draft changes nothing; no double charge of months already posted)."""
    from mhvp.contracts.models import ContractPayment, PaymentReason
    from mhvp.contracts.services import add_payment

    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id, with_for_update=True)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if plan.applied_at is not None:
            return _plan_out(plan)
        if plan.status not in (
            StatementStatus.RESOLVED,
            StatementStatus.ISSUED,
            StatementStatus.DUE,
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Vorschüsse erst nach Beschluss (W02, W06)."
            )
        created = 0
        for unit in (plan.snapshot or {}).get("units", []):
            contract = await calc.owner_at(session, uuid.UUID(unit["unit_id"]), plan.valid_from)
            if contract is None:
                continue
            for component, amount in unit["monthly"].items():
                if Decimal(amount) <= 0:
                    continue
                await add_payment(
                    session,
                    contract,
                    ContractPayment(
                        tenant_id=principal.tenant_id,
                        contract_id=contract.id,
                        payment_type_code=component,
                        net=Decimal(amount),
                        gross=Decimal(amount),
                        valid_from=plan.valid_from,
                        reason=PaymentReason.ADJUSTMENT_FROM_STATEMENT,
                    ),
                )
                created += 1
        plan.applied_at = datetime.now(UTC)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="economic_plan.applied",
            entity_type="economic_plan",
            entity_id=plan.id,
            actor_user_id=principal.user_id,
            payload={"payments": created},
        )
        await session.flush()
        return _plan_out(plan) | {"payments_created": created}


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
        item = HoaCostItem(tenant_id=principal.tenant_id, statement_id=st.id, **body.model_dump())
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
        st.snapshot, st.snapshot_hash = result, calc.digest(result)
        st.status = StatementStatus.CALCULATED
        await session.flush()
        return _st_out(st)


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
        await _move(session, st, body, principal)
        await session.flush()
        return _st_out(st)


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
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        old = await session.get(HoaStatement, statement_id)
        if old is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
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
                )
            )
        await session.flush()
        return _st_out(new)


# Read endpoints for the CRM screens -------------------------------------------------------


@router.get("/plans", summary="Wirtschaftspläne eines Buchungskreises")
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


@router.get("/statements", summary="Hausgeldabrechnungen eines Buchungskreises")
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
        return _st_out(st) | {
            "cost_items": [
                {
                    "id": i.id,
                    "label": i.label,
                    "amount": i.amount,
                    "basis": i.basis,
                    "allocation_key_id": i.allocation_key_id,
                }
                for i in items
            ]
        }
