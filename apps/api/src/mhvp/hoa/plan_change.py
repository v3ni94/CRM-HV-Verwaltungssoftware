"""AE09 (M24-08, P07-01, M12-L2; 7.8 W02): plan change within the year.

When a resolved plan takes effect on ``valid_from`` and receivables of later months are
already posted with the old amounts, the module computes the difference per unit, contract,
component and posted month: new monthly amount of the plan minus the posted amount
(positive: claim, negative: credit). The tenant chooses the variant
(``hoa_plan_change_setting.mode``):

* ``notice`` (default): the difference is shown only; no draft is created.
* ``due_now``: draft claim or credit due on the first of the month after the resolution.
* ``next_instalment``: draft settled with the next instalment not yet posted.

Which variant applies is an open decision (docs/OPEN_QUESTIONS.md M12-L2, P07-01); the
module decides nothing. Drafts are approved by a second person and only with gate G4; the
approval posts nothing, the posting stays a later bookkeeping step behind G1. A month that
begins before ``valid_from`` (plan starting mid month) is not split here (no proration rule
released) and is listed as ``manual``."""

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.status import StatementStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.hoa import calc
from mhvp.hoa.models import EconomicPlan, HoaPlanChangeSetting, HoaPlanDifference
from mhvp.hoa.property_scope import HOA_GUARD

router = APIRouter(prefix="/hoa", tags=["WEG"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")

CENT = Decimal("0.01")
MODES = ("notice", "due_now", "next_instalment")
RESOLVED = (StatementStatus.RESOLVED, StatementStatus.ISSUED, StatementStatus.DUE)
PLAN_CHANGE_NOTE = (
    "Differenz bereits gebuchter Monate nach unterjähriger Planänderung (W02). Welche "
    "Variante gilt, ist offen (M12-L2, P07-01); Standard ist nur Hinweis. Entwürfe buchen "
    "nichts; Freigabe durch eine zweite Person mit Freigabestufe G4, die Buchung folgt erst "
    "mit G1."
)


class HoaPlanChangeSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["notice", "due_now", "next_instalment"]


async def plan_change_mode(session: AsyncSession) -> str:
    row = await session.scalar(select(HoaPlanChangeSetting))
    return row.mode if row is not None else "notice"


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _months_of(item: Any) -> int:
    """Months covered by a posted item (instalments of quarterly or yearly plans)."""
    if item.period_start and item.period_end:
        return int(
            (item.period_end.year - item.period_start.year) * 12
            + item.period_end.month
            - item.period_start.month
            + 1
        )
    return 1


async def compute_differences(session: AsyncSession, plan: EconomicPlan) -> dict[str, Any]:
    """Rows per unit, component and posted month of the plan year from ``valid_from`` on."""
    from mhvp.accounting.models import ItemStatus, ReceivableItem

    first = plan.valid_from.replace(day=1)
    year_end = date(plan.year, 12, 1)
    rows: list[dict[str, Any]] = []
    total = Decimal(0)
    for unit in (plan.snapshot or {}).get("units", []):
        unit_id = uuid.UUID(unit["unit_id"])
        for component, amount in unit["monthly"].items():
            monthly = Decimal(amount)
            month = first
            while month <= year_end:
                contract = await calc.owner_at(session, unit_id, max(month, plan.valid_from))
                if contract is not None:
                    items = (
                        await session.scalars(
                            select(ReceivableItem).where(
                                ReceivableItem.contract_id == contract.id,
                                ReceivableItem.payment_type_code == component,
                                ReceivableItem.status == ItemStatus.POSTED,
                                ReceivableItem.period_month == month,
                            )
                        )
                    ).all()
                    if items:
                        posted = sum((i.amount for i in items), Decimal(0))
                        new = (monthly * max(_months_of(i) for i in items)).quantize(
                            CENT, rounding=ROUND_HALF_UP
                        )
                        manual = month < plan.valid_from
                        diff = (new - posted).quantize(CENT, rounding=ROUND_HALF_UP)
                        rows.append(
                            {
                                "unit_id": str(unit_id),
                                "unit_number": unit["unit_number"],
                                "contract_id": str(contract.id),
                                "contract_number": contract.number,
                                "component": component,
                                "period_month": month,
                                "posted_amount": str(posted.quantize(CENT, rounding=ROUND_HALF_UP)),
                                "new_amount": str(new),
                                "difference": str(diff),
                                "kind": "manual"
                                if manual
                                else ("claim" if diff > 0 else "credit" if diff < 0 else "none"),
                            }
                        )
                        if not manual:
                            total += diff
                month = _add_months(month, 1)
    return {"rows": rows, "total": str(total.quantize(CENT, rounding=ROUND_HALF_UP))}


async def _proposed_due(session: AsyncSession, plan: EconomicPlan, mode: str) -> date:
    """``due_now``: first of the month after the resolution (else after today);
    ``next_instalment``: first month after the last posted month of the plan year."""
    from mhvp.accounting.models import ItemStatus, ReceivableItem
    from mhvp.hoa.models import Resolution

    if mode == "due_now":
        decided = None
        if plan.resolution_id is not None:
            decided = await session.scalar(
                select(Resolution.decided_on).where(Resolution.id == plan.resolution_id)
            )
        return _add_months(decided or local_today(), 1)
    last = await session.scalar(
        select(func.max(ReceivableItem.period_month)).where(
            ReceivableItem.ledger_id == plan.ledger_id,
            ReceivableItem.status == ItemStatus.POSTED,
        )
    )
    return _add_months(last or plan.valid_from, 1)


def _diff_out(row: HoaPlanDifference) -> dict[str, Any]:
    return {
        "id": row.id,
        "plan_id": row.plan_id,
        "unit_id": row.unit_id,
        "contract_id": row.contract_id,
        "component": row.payment_type_code,
        "period_month": row.period_month,
        "posted_amount": str(row.posted_amount),
        "new_amount": str(row.new_amount),
        "difference": str(row.difference),
        "mode": row.mode,
        "proposed_due": row.proposed_due,
        "status": row.status,
        "created_by": row.created_by,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
    }


async def _plan(session: AsyncSession, plan_id: uuid.UUID) -> EconomicPlan:
    plan = await session.get(EconomicPlan, plan_id)
    if plan is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return plan


@router.get("/plan-change-settings", summary="Variante der unterjährigen Planänderung")
async def get_plan_change_setting(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return {"mode": await plan_change_mode(session), "modes": MODES, "note": PLAN_CHANGE_NOTE}


@router.put("/plan-change-settings", summary="Variante der unterjährigen Planänderung setzen")
async def put_plan_change_setting(
    body: HoaPlanChangeSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> dict[str, Any]:
    """Operator decision (M12-L2, P07-01); the system asserts no legal rule."""
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(HoaPlanChangeSetting).with_for_update())
        if row is None:
            row = HoaPlanChangeSetting(tenant_id=principal.tenant_id, mode=body.mode)
            session.add(row)
        row.mode = body.mode
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_plan_change_setting.updated",
            entity_type="hoa_plan_change_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"mode": body.mode},
        )
        return {"mode": body.mode, "modes": MODES, "note": PLAN_CHANGE_NOTE}


@router.get(
    "/plans/{plan_id}/differences",
    summary="Differenz bereits gebuchter Monate (W02)",
    dependencies=[Depends(strict_query)],
)
async def plan_differences(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        plan = await _plan(session, plan_id)
        result = await compute_differences(session, plan)
        drafts = (
            await session.scalars(
                select(HoaPlanDifference)
                .where(HoaPlanDifference.plan_id == plan.id)
                .order_by(HoaPlanDifference.period_month, HoaPlanDifference.payment_type_code)
            )
        ).all()
        return result | {
            "plan_id": plan.id,
            "valid_from": plan.valid_from,
            "mode": await plan_change_mode(session),
            "drafts": [_diff_out(d) for d in drafts],
            "note": PLAN_CHANGE_NOTE,
        }


@router.post(
    "/plans/{plan_id}/differences/draft",
    summary="Differenzen als Entwurf je Einheit anlegen",
    status_code=201,
)
async def draft_plan_differences(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Only for a resolved plan and a variant other than ``notice``. Idempotent per contract,
    component and month; nothing is posted."""
    async with tenant_tx(request, principal) as session:
        plan = await session.get(EconomicPlan, plan_id, with_for_update=True)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if plan.status not in RESOLVED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Differenzen erst nach Beschluss (W02).")
        mode = await plan_change_mode(session)
        if mode == "notice":
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Variante nur Hinweis: es werden keine Entwürfe angelegt (M12-L2).",
            )
        due = await _proposed_due(session, plan, mode)
        existing = {
            (d.contract_id, d.payment_type_code, d.period_month)
            for d in (
                await session.scalars(
                    select(HoaPlanDifference).where(HoaPlanDifference.plan_id == plan.id)
                )
            ).all()
        }
        created = 0
        for row in (await compute_differences(session, plan))["rows"]:
            if row["kind"] not in ("claim", "credit"):
                continue
            key = (uuid.UUID(row["contract_id"]), row["component"], row["period_month"])
            if key in existing:
                continue
            session.add(
                HoaPlanDifference(
                    tenant_id=principal.tenant_id,
                    created_by=principal.user_id,
                    plan_id=plan.id,
                    unit_id=uuid.UUID(row["unit_id"]),
                    contract_id=key[0],
                    payment_type_code=row["component"],
                    period_month=row["period_month"],
                    posted_amount=Decimal(row["posted_amount"]),
                    new_amount=Decimal(row["new_amount"]),
                    difference=Decimal(row["difference"]),
                    mode=mode,
                    proposed_due=due,
                )
            )
            created += 1
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="economic_plan.differences_drafted",
            entity_type="economic_plan",
            entity_id=plan.id,
            actor_user_id=principal.user_id,
            payload={"created": created, "mode": mode},
        )
        return {"created": created, "mode": mode, "proposed_due": due}


async def _decide(
    request: Request, principal: TenantPrincipal, diff_id: uuid.UUID, target: str
) -> dict[str, Any]:
    await ensure_release_gate_open(
        ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
    )
    async with tenant_tx(request, principal) as session:
        row = await session.get(HoaPlanDifference, diff_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != "draft":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Entwurf ist bereits entschieden.")
        if row.created_by == principal.user_id:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES,
                detail="Die Freigabe muss eine andere Person als der Ersteller erteilen.",
            )
        row.status = target
        row.decided_by = principal.user_id
        row.decided_at = datetime.now(UTC)
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"hoa_plan_difference.{target}",
            entity_type="hoa_plan_difference",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"difference": str(row.difference), "mode": row.mode},
        )
        return _diff_out(row)


@router.post(
    "/plan-differences/{diff_id}/approve", summary="Differenzentwurf freigeben (G4, Vier Augen)"
)
async def approve_plan_difference(
    diff_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Approval only; nothing is posted (posting behind G1)."""
    return await _decide(request, principal, diff_id, "approved")


@router.post("/plan-differences/{diff_id}/reject", summary="Differenzentwurf verwerfen")
async def reject_plan_difference(
    diff_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    return await _decide(request, principal, diff_id, "rejected")
