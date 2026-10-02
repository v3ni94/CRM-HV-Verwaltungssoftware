"""AE08 / P07-02: payments per earmarked reserve (Soll and Ist), rule AE08-01.

Two variants as tenant switch (``hoa_reserve_payment_setting.mode``):

* ``bound_only`` (default): Ist per reserve only from receivable items bound to the reserve
  (``contract_payment.reserve_id`` carried to ``receivable_item.reserve_id``, M24-01).
* ``plan_ratio_proposal``: the unbound reserve payments are split in the ratio of the planned
  contributions per reserve. This is a proposal only: nothing is posted, no item is changed,
  ``contributions_paid`` and the statement basis stay as they are (G4 stays closed). Whether
  a split by plan ratio is admissible is open (P07-02, P07-04).
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import (
    EconomicPlan,
    HoaReserve,
    HoaReservePaymentSetting,
    HoaStatement,
    PlanItem,
)
from mhvp.hoa.property_scope import HOA_GUARD

router = APIRouter(prefix="/hoa", tags=["WEG"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MODES = ("bound_only", "plan_ratio_proposal")
NOTE = (
    "Vorschlag zur Information, keine Buchung und keine Änderung der Posten. Ob eine "
    "Aufteilung nach Planverhältnis zulässig ist, ist offen (P07-02, Gate G4)."
)


def split_by_plan_ratio(unassigned: Decimal, planned: dict[str, Decimal]) -> dict[str, Decimal]:
    """Split ``unassigned`` in the ratio of ``planned`` (rule AE08-01). Cent rounding half
    up (GAI-614); the rounding rest goes to the reserve with the largest plan amount
    (ties: smallest id), so the parts always add up to ``unassigned``. Without a positive
    plan: empty."""
    positive = {k: v for k, v in planned.items() if v > 0}
    total = sum(positive.values(), ZERO)
    if total <= 0 or unassigned == 0:
        return {}
    parts = {
        k: (unassigned * v / total).quantize(CENT, rounding=ROUND_HALF_UP)
        for k, v in positive.items()
    }
    rest = unassigned - sum(parts.values(), ZERO)
    if rest:
        target = sorted(positive, key=lambda k: (-positive[k], k))[0]
        parts[target] += rest
    return parts


async def split_mode(session: AsyncSession) -> str:
    mode = await session.scalar(select(HoaReservePaymentSetting.mode))
    return mode if mode in MODES else "bound_only"


def add_proposal(positions: list[dict[str, Any]], unassigned: Decimal) -> None:
    """Additive fields per statement position (only with ``plan_ratio_proposal``)."""
    parts = split_by_plan_ratio(
        unassigned, {p["reserve_id"]: Decimal(p["contributions_planned"]) for p in positions}
    )
    for p in positions:
        part = parts.get(p["reserve_id"], ZERO)
        p["contributions_paid_proposal"] = str(part)
        p["contributions_paid_with_proposal"] = str(Decimal(p["contributions_paid"]) + part)
        p["proposal_basis"] = "plan_ratio"


class HoaReservePaymentSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str


@router.get("/reserve-payment-settings", summary="Zahlungen je Zweckrücklage (Variante)")
async def get_split_setting(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return {"mode": await split_mode(session), "modes": list(MODES), "note": NOTE}


@router.put("/reserve-payment-settings", summary="Zahlungen je Zweckrücklage (Variante setzen)")
async def put_split_setting(
    body: HoaReservePaymentSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> dict[str, Any]:
    if body.mode not in MODES:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Variante.")
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(HoaReservePaymentSetting).with_for_update())
        if row is None:
            row = HoaReservePaymentSetting(tenant_id=principal.tenant_id, mode=body.mode)
            session.add(row)
        row.mode = body.mode
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_reserve_payment_setting.updated",
            entity_type="hoa_reserve_payment_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"mode": body.mode},
        )
        return {"mode": body.mode, "modes": list(MODES), "note": NOTE}


@router.get(
    "/ledgers/{ledger_id}/reserve-payments",
    summary="Soll und Ist je Zweckrücklage eines Jahres (P07-02)",
    dependencies=[Depends(strict_query)],
)
async def reserve_payments(
    ledger_id: uuid.UUID,
    year: int,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    if not 1990 <= year <= 2100:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Jahr außerhalb des Bereichs.")
    from mhvp.hoa.routers import _hoa_ledger

    async with tenant_tx(request, principal) as session:
        ledger = await _hoa_ledger(session, ledger_id)
        mode = await split_mode(session)
        reserves = (
            await session.scalars(
                select(HoaReserve)
                .where(HoaReserve.ledger_id == ledger.id)
                .order_by(HoaReserve.name)
            )
        ).all()
        plan = await session.scalar(
            select(EconomicPlan)
            .where(
                EconomicPlan.ledger_id == ledger.id,
                EconomicPlan.year == year,
                EconomicPlan.resolution_id.is_not(None),
            )
            .order_by(EconomicPlan.version.desc())
            .limit(1)
        )
        planned: dict[str, Decimal] = {str(r.id): ZERO for r in reserves}
        if plan is not None:
            for item in (
                await session.scalars(select(PlanItem).where(PlanItem.plan_id == plan.id))
            ).all():
                key = str(item.reserve_id) if item.reserve_id else None
                if key in planned:
                    planned[key] += item.amount
        statement = await session.scalar(
            select(HoaStatement)
            .where(HoaStatement.ledger_id == ledger.id, HoaStatement.year == year)
            .order_by(HoaStatement.version.desc())
            .limit(1)
        )
        block = ((statement.snapshot or {}).get("reserve") or {}) if statement else {}
        paid_by = {
            k: Decimal(v) for k, v in (block.get("contributions_paid_by_reserve") or {}).items()
        }
        unassigned = Decimal(block.get("contributions_paid_unassigned") or "0.00")
        parts = split_by_plan_ratio(unassigned, planned) if mode == "plan_ratio_proposal" else {}
        rows = []
        for r in reserves:
            key = str(r.id)
            paid = paid_by.get(key, ZERO)
            row: dict[str, Any] = {
                "reserve_id": key,
                "name": r.name,
                "planned": str(planned[key]),
                "paid_bound": str(paid),
                "open_bound": str(planned[key] - paid),
            }
            if mode == "plan_ratio_proposal":
                row["paid_proposal"] = str(parts.get(key, ZERO))
                row["paid_with_proposal"] = str(paid + parts.get(key, ZERO))
            rows.append(row)
        return {
            "ledger_id": str(ledger.id),
            "year": year,
            "mode": mode,
            "source": "statement" if block else ("plan" if plan else "none"),
            "statement_id": str(statement.id) if statement else None,
            "paid_unassigned": str(unassigned),
            "reserves": rows,
            "note": NOTE,
        }
