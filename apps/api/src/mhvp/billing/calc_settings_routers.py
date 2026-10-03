"""Tenant switches of the calculation rules (AK01, GAI-202, GAI-214, GAI-204).

GET needs ``accounting:read``; PUT needs ``accounting:approve`` because the switches change
calculation results (decision AJ01-01, AJ01-02, AJ02-01 stays with the operator). Partial
update: omitted fields keep their value. Nothing is booked, sent or released.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from mhvp.billing import calc_settings
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings

READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")
router = APIRouter(prefix="/billing/calculation-settings", tags=["Abrechnung"])


class BillingCalcSettingsOut(BaseModel):
    heating_negative_costs_mode: Literal["legacy_warn", "distribute"]
    hoa_remainder_mode: Literal["report_only", "first_month", "last_month"]
    check_amounts_tolerance_cents: Literal[0, 1]


class BillingCalcSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heating_negative_costs_mode: Literal["legacy_warn", "distribute"] | None = None
    hoa_remainder_mode: Literal["report_only", "first_month", "last_month"] | None = None
    check_amounts_tolerance_cents: Literal[0, 1] | None = None


def _out(s: calc_settings.CalcSettings) -> BillingCalcSettingsOut:
    return BillingCalcSettingsOut.model_validate(s.__dict__)


@router.get("", summary="Rechenschalter: negative Heizkosten, Restcent Hausgeld, Bruttotoleranz")
async def get_calc_settings(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> BillingCalcSettingsOut:
    async with tenant_tx(request, principal) as session:
        return _out(await calc_settings.load(session))


@router.put("", summary="Rechenschalter setzen (Freigaberecht, nur Rechenentwurf)")
async def put_calc_settings(
    body: BillingCalcSettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> BillingCalcSettingsOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        changes = body.model_dump(exclude_none=True)
        before = {k: getattr(row, k) for k in changes}
        for key, value in changes.items():
            setattr(row, key, value)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="billing_calc_settings.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"before": before, "after": changes},
        )
        await session.flush()
        return _out(await calc_settings.load(session))
