"""Reserve plan per reserve and year and the opening change switch (AE07, M24-01, V01-01).

* ``hoa_reserve_plan`` carries the planned contribution (Soll) of one reserve and year with
  economic plan and resolution reference. The development (``reserves.reserve_development``)
  takes a resolved row as Soll; without one it keeps the economic plan items. The Ist stays
  the paid amount from the statement (P07-02 open, no split is invented).
* ``derive`` creates draft rows from the reserve items of an economic plan.
* A resolved row is frozen; a change is a new row that supersedes the old one on resolve.
* The tax classification is a placeholder with release status ``not_released``; the system
  decides no tax treatment (AE07-01).
* The opening switch (V01-01) per tenant: ``locked`` (default, unchanged rule U15-03),
  ``logged`` (change applied with log row) or ``four_eyes`` (pending until a second person
  approves). Nothing is posted in any mode.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from fastapi import Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import (
    EconomicPlan,
    HoaReserve,
    HoaReserveOpeningChange,
    HoaReservePlan,
    HoaReservePolicy,
    PlanItem,
    Resolution,
)
from mhvp.hoa.reserves import CREATE, READ, ZERO, _reserve_with_ledger, router

APPROVE = require_permission("accounting:approve")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")

LOCK_MODES = ("locked", "logged", "four_eyes")
REFUSED_RESOLUTION = ("negative", "annulled", "void")
TAX_NOTE = (
    "Steuerliche Einordnung nur als Platzhalter, nicht freigegeben; Festlegung durch "
    "Steuerberatung (AE07-01)."
)
POLICY_NOTE = (
    "Standard gesperrt (Produktschutz U15-03). Protokollierte Änderung oder Vier Augen nur nach "
    "Entscheidung des Betreibers (V01-01 offen). Keine Buchung in keiner Variante."
)


class HoaReservePlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=1990, le=2100)
    planned_contribution: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    economic_plan_id: uuid.UUID | None = None
    resolution_id: uuid.UUID | None = None
    tax_classification: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class HoaReservePlanPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned_contribution: Decimal | None = Field(
        default=None, ge=0, max_digits=14, decimal_places=2
    )
    economic_plan_id: uuid.UUID | None = None
    resolution_id: uuid.UUID | None = None
    tax_classification: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class HoaReservePlanResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_id: uuid.UUID | None = None


class HoaReservePolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening_lock_mode: Literal["locked", "logged", "four_eyes"]


class HoaReserveOpeningDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


def plan_out(p: HoaReservePlan, plan_item_amount: Decimal | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": p.id,
        "reserve_id": p.reserve_id,
        "year": p.year,
        "economic_plan_id": p.economic_plan_id,
        "planned_contribution": str(p.planned_contribution),
        "resolution_id": p.resolution_id,
        "status": p.status,
        "tax_classification": p.tax_classification,
        "tax_classification_status": p.tax_classification_status,
        "tax_note": TAX_NOTE,
        "note": p.note,
        "resolved_at": p.resolved_at,
    }
    if plan_item_amount is not None:
        out["plan_item_amount"] = str(plan_item_amount)
        out["deviation"] = str(p.planned_contribution - plan_item_amount)
    return out


def change_out(c: HoaReserveOpeningChange) -> dict[str, Any]:
    return {
        "id": c.id,
        "reserve_id": c.reserve_id,
        "mode": c.mode,
        "changes": c.changes,
        "reason": c.reason,
        "status": c.status,
        "requested_by": c.created_by,
        "requested_at": c.created_at,
        "decided_by": c.decided_by,
        "decided_at": c.decided_at,
    }


async def resolved_plan(
    session: AsyncSession, reserve_id: uuid.UUID, year: int
) -> HoaReservePlan | None:
    result: HoaReservePlan | None = await session.scalar(
        select(HoaReservePlan).where(
            HoaReservePlan.reserve_id == reserve_id,
            HoaReservePlan.year == year,
            HoaReservePlan.status == "resolved",
        )
    )
    return result


async def lock_mode(session: AsyncSession) -> str:
    mode = await session.scalar(select(HoaReservePolicy.opening_lock_mode))
    return mode or "locked"


def _jsonable(changes: dict[str, Any]) -> dict[str, Any]:
    return {k: (str(v) if isinstance(v, Decimal) else v) for k, v in changes.items()}


async def handle_opening_change(
    session: AsyncSession,
    principal: TenantPrincipal,
    reserve: HoaReserve,
    changes: dict[str, Any],
    reason: str | None,
    locked_fields: list[str],
) -> dict[str, Any] | None:
    """Applies the tenant switch to locked opening fields. ``locked`` raises 409; ``logged``
    writes an applied log row; ``four_eyes`` removes the fields from ``changes`` and records a
    pending request. Returns the pending request or None."""
    if not locked_fields:
        return None
    mode = await lock_mode(session)
    if mode == "locked":
        raise ProblemError(
            ErrorCodes.HOA_RESERVE_OPENING_LOCKED,
            detail="Abrechnung des Anfangsjahres ist berechnet oder freigegeben; "
            "Korrektur nur per neuer Bewegung.",
        )
    if not reason or len(reason.strip()) < 5:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Begründung der Änderung ist erforderlich."
        )
    diff = {key: {"old": getattr(reserve, key), "new": changes[key]} for key in locked_fields}
    diff = {k: _jsonable(v) for k, v in diff.items()}
    row = HoaReserveOpeningChange(
        tenant_id=principal.tenant_id,
        reserve_id=reserve.id,
        mode=mode,
        changes=diff,
        reason=reason.strip(),
        status="applied" if mode == "logged" else "pending",
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    session.add(row)
    await session.flush()
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=f"hoa_reserve.opening_change_{row.status}",
        entity_type="hoa_reserve",
        entity_id=reserve.id,
        actor_user_id=principal.user_id,
        payload={"change_id": str(row.id), "changes": diff, "mode": mode},
    )
    if mode == "logged":
        return None
    for key in locked_fields:
        changes.pop(key, None)
    return change_out(row)


async def _check_refs(
    session: AsyncSession,
    ledger: Any,
    year: int,
    economic_plan_id: uuid.UUID | None,
    resolution_id: uuid.UUID | None,
) -> None:
    if economic_plan_id is not None:
        plan = await session.get(EconomicPlan, economic_plan_id)
        if plan is None or plan.ledger_id != ledger.id or plan.year != year:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Wirtschaftsplan gehört nicht zu Buchungskreis und Jahr der Rücklage.",
            )
    if resolution_id is not None:
        res = await session.get(Resolution, resolution_id)
        if res is None or res.legal_entity_id != ledger.legal_entity_id:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Beschluss gehört nicht zur Gemeinschaft."
            )
        if res.status in REFUSED_RESOLUTION:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Beschluss ist negativ, aufgehoben oder nichtig."
            )


async def _plan_item_amount(session: AsyncSession, p: HoaReservePlan) -> Decimal | None:
    if p.economic_plan_id is None:
        return None
    amounts = await session.scalars(
        select(PlanItem.amount).where(
            PlanItem.plan_id == p.economic_plan_id, PlanItem.reserve_id == p.reserve_id
        )
    )
    return sum(amounts.all(), ZERO)


async def _plan_with_scope(session: AsyncSession, plan_id: uuid.UUID) -> tuple[Any, Any]:
    p = await session.get(HoaReservePlan, plan_id, with_for_update=True)
    if p is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    _, ledger = await _reserve_with_ledger(session, p.reserve_id)
    return p, ledger


# Reserve plan ------------------------------------------------------------------------------


@router.get(
    "/reserves/{reserve_id}/plans",
    summary="Rücklagenplan je Jahr (Soll-Zuführung, Beschluss, Status) (AE07)",
    dependencies=[Depends(strict_query)],
)
async def list_reserve_plans(
    reserve_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        await _reserve_with_ledger(session, reserve_id)
        rows = (
            await session.scalars(
                select(HoaReservePlan)
                .where(HoaReservePlan.reserve_id == reserve_id)
                .order_by(HoaReservePlan.year.desc(), HoaReservePlan.created_at.desc())
            )
        ).all()
        return [plan_out(p, await _plan_item_amount(session, p)) for p in rows]


@router.post(
    "/reserves/{reserve_id}/plans",
    status_code=201,
    summary="Rücklagenplan als Entwurf anlegen (AE07)",
)
async def create_reserve_plan(
    reserve_id: uuid.UUID,
    body: HoaReservePlanIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        _, ledger = await _reserve_with_ledger(session, reserve_id)
        await _check_refs(session, ledger, body.year, body.economic_plan_id, body.resolution_id)
        p = HoaReservePlan(
            tenant_id=principal.tenant_id,
            reserve_id=reserve_id,
            status="draft",
            created_by=principal.user_id,
            updated_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(p)
        await session.flush()
        return plan_out(p, await _plan_item_amount(session, p))


@router.get("/reserve-plans/{plan_id}", summary="Rücklagenplan lesen (AE07)")
async def get_reserve_plan(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        p, _ = await _plan_with_scope(session, plan_id)
        return plan_out(p, await _plan_item_amount(session, p))


@router.patch("/reserve-plans/{plan_id}", summary="Rücklagenplan im Entwurf ändern (AE07)")
async def patch_reserve_plan(
    plan_id: uuid.UUID,
    body: HoaReservePlanPatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "planned_contribution" in changes and changes["planned_contribution"] is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Soll-Zuführung darf nicht leer sein.")
    async with tenant_tx(request, principal) as session:
        p, ledger = await _plan_with_scope(session, plan_id)
        if p.status != "draft":
            raise ProblemError(ErrorCodes.HOA_RESERVE_PLAN_LOCKED)
        await _check_refs(
            session,
            ledger,
            p.year,
            changes.get("economic_plan_id"),
            changes.get("resolution_id"),
        )
        for key, value in changes.items():
            setattr(p, key, value)
        p.updated_by = principal.user_id
        await session.flush()
        return plan_out(p, await _plan_item_amount(session, p))


@router.post(
    "/reserve-plans/{plan_id}/resolve",
    summary="Rücklagenplan als beschlossen kennzeichnen (Beschluss erforderlich) (AE07)",
)
async def resolve_reserve_plan(
    plan_id: uuid.UUID,
    body: HoaReservePlanResolveIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Marks the Soll as resolved; an earlier resolved row of the same year is superseded.
    No posting and no demand is created (Sollstellung stays in the economic plan flow)."""
    async with tenant_tx(request, principal) as session:
        p, ledger = await _plan_with_scope(session, plan_id)
        if p.status != "draft":
            raise ProblemError(ErrorCodes.HOA_RESERVE_PLAN_LOCKED)
        resolution_id = body.resolution_id or p.resolution_id
        if resolution_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Beschlussbezug ist für den Beschluss erforderlich."
            )
        await _check_refs(session, ledger, p.year, None, resolution_id)
        previous = await session.scalar(
            select(HoaReservePlan)
            .where(
                HoaReservePlan.reserve_id == p.reserve_id,
                HoaReservePlan.year == p.year,
                HoaReservePlan.status == "resolved",
            )
            .with_for_update()
        )
        if previous is not None:
            previous.status = "superseded"
            previous.updated_by = principal.user_id
            await session.flush()
        p.resolution_id = resolution_id
        p.status = "resolved"
        p.resolved_at = datetime.now(UTC)
        p.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_reserve_plan.resolved",
            entity_type="hoa_reserve_plan",
            entity_id=p.id,
            actor_user_id=principal.user_id,
            payload={
                "planned_contribution": str(p.planned_contribution),
                "superseded_id": str(previous.id) if previous else None,
            },
        )
        return plan_out(p, await _plan_item_amount(session, p))


@router.post(
    "/plans/{plan_id}/reserve-plans/derive",
    summary="Rücklagenpläne als Entwurf aus dem Wirtschaftsplan ableiten (AE07)",
)
async def derive_reserve_plans(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> list[dict[str, Any]]:
    """One draft per reserve with the sum of its reserve items; resolution reference from the
    plan. An existing draft for the same plan and reserve is updated, resolved rows stay."""
    from mhvp.core.auth.scope import (
        ensure_session_legal_entity_allowed,
        ensure_session_property_allowed,
    )
    from mhvp.hoa.routers import _hoa_ledger

    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        ledger = await _hoa_ledger(session, plan.ledger_id)
        ensure_session_property_allowed(session, ledger.property_id)
        ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
        items = (
            await session.scalars(
                select(PlanItem).where(
                    PlanItem.plan_id == plan.id, PlanItem.reserve_id.is_not(None)
                )
            )
        ).all()
        sums: dict[uuid.UUID, Decimal] = {}
        for item in items:
            if item.reserve_id is None:
                continue
            sums[item.reserve_id] = sums.get(item.reserve_id, ZERO) + item.amount
        out: list[dict[str, Any]] = []
        for reserve_id in sorted(sums, key=str):
            draft = await session.scalar(
                select(HoaReservePlan).where(
                    HoaReservePlan.reserve_id == reserve_id,
                    HoaReservePlan.economic_plan_id == plan.id,
                    HoaReservePlan.status == "draft",
                )
            )
            if draft is None:
                draft = HoaReservePlan(
                    tenant_id=principal.tenant_id,
                    reserve_id=reserve_id,
                    year=plan.year,
                    economic_plan_id=plan.id,
                    status="draft",
                    created_by=principal.user_id,
                )
                session.add(draft)
            draft.planned_contribution = sums[reserve_id]
            draft.resolution_id = plan.resolution_id
            draft.updated_by = principal.user_id
            await session.flush()
            out.append(plan_out(draft, sums[reserve_id]))
        return out


# Opening switch (V01-01) -------------------------------------------------------------------


@router.get("/reserve-policy", summary="Umgang mit Anfangsbeständen nach Abrechnung (Schalter)")
async def get_reserve_policy(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return {"opening_lock_mode": await lock_mode(session), "note": POLICY_NOTE}


@router.put("/reserve-policy", summary="Umgang mit Anfangsbeständen setzen (V01-01)")
async def put_reserve_policy(
    body: HoaReservePolicyIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(HoaReservePolicy).with_for_update())
        if row is None:
            row = HoaReservePolicy(tenant_id=principal.tenant_id)
            session.add(row)
        row.opening_lock_mode = body.opening_lock_mode
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_reserve_policy.updated",
            entity_type="hoa_reserve_policy",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"opening_lock_mode": body.opening_lock_mode},
        )
        return {"opening_lock_mode": body.opening_lock_mode, "note": POLICY_NOTE}


@router.get(
    "/reserves/{reserve_id}/opening-changes",
    summary="Protokoll der Änderungen des Anfangsbestands (V01-01)",
    dependencies=[Depends(strict_query)],
)
async def list_opening_changes(
    reserve_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        await _reserve_with_ledger(session, reserve_id)
        rows = await session.scalars(
            select(HoaReserveOpeningChange)
            .where(HoaReserveOpeningChange.reserve_id == reserve_id)
            .order_by(HoaReserveOpeningChange.created_at.desc())
        )
        return [change_out(c) for c in rows.all()]


async def _decide(
    change_id: uuid.UUID,
    approve: bool,
    request: Request,
    principal: TenantPrincipal,
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        c = await session.get(HoaReserveOpeningChange, change_id, with_for_update=True)
        if c is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _reserve_with_ledger(session, c.reserve_id)
        if c.status != "pending":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Änderung ist bereits entschieden.")
        if c.created_by == principal.user_id:
            raise ProblemError(ErrorCodes.HOA_RESERVE_OPENING_SELF_APPROVAL)
        reserve = await session.get(HoaReserve, c.reserve_id, with_for_update=True)
        if reserve is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if approve:
            for key, value in c.changes.items():
                old = value["old"]
                current = getattr(reserve, key)
                current_s = str(current) if isinstance(current, Decimal) else current
                if current_s != old:
                    raise ProblemError(
                        ErrorCodes.CONFLICT,
                        detail="Rücklage wurde seit dem Antrag geändert; neuer Antrag nötig.",
                    )
            for key, value in c.changes.items():
                new = value["new"]
                setattr(
                    reserve,
                    key,
                    Decimal(new) if key == "opening_balance" and new is not None else new,
                )
            reserve.updated_by = principal.user_id
        c.status = "applied" if approve else "rejected"
        c.decided_by = principal.user_id
        c.decided_at = datetime.now(UTC)
        c.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"hoa_reserve.opening_change_{c.status}",
            entity_type="hoa_reserve",
            entity_id=c.reserve_id,
            actor_user_id=principal.user_id,
            payload={"change_id": str(c.id)},
        )
        return change_out(c)


@router.post(
    "/reserve-opening-changes/{change_id}/approve",
    summary="Änderung des Anfangsbestands freigeben (zweite Person) (V01-01)",
)
async def approve_opening_change(
    change_id: uuid.UUID,
    body: HoaReserveOpeningDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    return await _decide(change_id, True, request, principal)


@router.post(
    "/reserve-opening-changes/{change_id}/reject",
    summary="Änderung des Anfangsbestands ablehnen (V01-01)",
)
async def reject_opening_change(
    change_id: uuid.UUID,
    body: HoaReserveOpeningDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    return await _decide(change_id, False, request, principal)
