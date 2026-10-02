"""AG20 / GAE-12 (W07, P01, AA07-01): allocation proposal of ``calc.allocation_owner``.

The hook ``calc.allocation_owner`` (tenant rule per acquisition kind) is shown as a proposal next
to the owner the software actually uses: in the plan takeover preview (owner at ``valid_from``,
rule W02) and per statement (owner at the resolution date, assumption M24-01). Behind a tenant
switch, default off. Nothing changes the takeover, the result posting or any receivable: which
owner owes the statement result per acquisition kind stays open (W07, P01, gate G4).
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa import calc
from mhvp.hoa.models import HoaAllocationProposalSetting, HoaStatement, Resolution
from mhvp.hoa.property_scope import HOA_GUARD

router = APIRouter(prefix="/hoa", tags=["WEG"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")

NOTE = (
    "Zuordnungsvorschlag nach der Mandantenregel je Erwerbsart, keine Buchung, keine "
    "Forderung. Maßgeblich bleibt der verwendete Eigentümer; die Rechtsfrage ist offen "
    "(W07, P01, AA07-01, Gate G4)."
)


class HoaAllocationProposalSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


async def allocation_proposal_enabled(session: AsyncSession) -> bool:
    """Tenant switch, default off (no row means off)."""
    return bool(await session.scalar(select(HoaAllocationProposalSetting.enabled)))


def _contract_ref(contract: Any) -> dict[str, Any] | None:
    if contract is None:
        return None
    return {"contract_id": str(contract.id), "contract_number": contract.number}


async def proposal_for(
    session: AsyncSession,
    unit_id: uuid.UUID,
    used: Any,
    *,
    default_day: date,
    due_day: date | None,
    resolution_day: date | None,
) -> dict[str, Any]:
    """Proposed owner of the hook next to the used one; ``differs`` flags a deviation."""
    proposed = await calc.allocation_owner(
        session, unit_id, default_day=default_day, due_day=due_day, resolution_day=resolution_day
    )
    used_id = used.id if used is not None else None
    proposed_id = proposed.id if proposed is not None else None
    return {
        "proposed": _contract_ref(proposed),
        "differs": proposed_id != used_id,
    }


async def plan_resolution_day(
    session: AsyncSession, resolution_id: uuid.UUID | None
) -> date | None:
    if resolution_id is None:
        return None
    res = await session.get(Resolution, resolution_id)
    return res.decided_on if res is not None else None


@router.get(
    "/allocation-proposal-settings",
    summary="Zuordnungsvorschlag Eigentümerwechsel (Schalter)",
    dependencies=[Depends(strict_query)],
)
async def get_allocation_proposal_setting(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return {"enabled": await allocation_proposal_enabled(session), "note": NOTE}


class HoaAllocationProposalSettingOut(BaseModel):
    """Response of the switch (GAI-304)."""

    model_config = ConfigDict(extra="allow")
    enabled: bool
    note: str


@router.put(
    "/allocation-proposal-settings",
    summary="Zuordnungsvorschlag Eigentümerwechsel (setzen)",
    response_model=HoaAllocationProposalSettingOut,
)
async def put_allocation_proposal_setting(
    body: HoaAllocationProposalSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(HoaAllocationProposalSetting).with_for_update())
        if row is None:
            row = HoaAllocationProposalSetting(tenant_id=principal.tenant_id, enabled=body.enabled)
            session.add(row)
        row.enabled = body.enabled
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_allocation_proposal_setting.updated",
            entity_type="hoa_allocation_proposal_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled},
        )
        return {"enabled": body.enabled, "note": NOTE}


@router.get(
    "/statements/{statement_id}/allocation-proposal",
    summary="Zuordnungsvorschlag des Abrechnungsergebnisses (W07, P01)",
    dependencies=[Depends(strict_query)],
)
async def statement_allocation_proposal(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Per unit with a result: owner used by the result posting (owner at the resolution date,
    M24-01) and the proposal of the tenant rule. 409 while the switch is off or the statement
    has no snapshot or no resolution."""
    async with tenant_tx(request, principal) as session:
        st = await session.get(HoaStatement, statement_id)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if not await allocation_proposal_enabled(session):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Zuordnungsvorschlag ist ausgeschaltet.")
        day = await plan_resolution_day(session, st.resolution_id)
        if st.snapshot is None or day is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Abrechnung ohne Berechnung oder ohne Beschluss.",
            )
        items = []
        for unit in st.snapshot.get("units", []):
            result = Decimal(unit["result"])
            if result == 0:
                continue
            unit_id = uuid.UUID(unit["unit_id"])
            used = await calc.owner_at(session, unit_id, day)
            items.append(
                {
                    "unit_id": str(unit_id),
                    "unit_number": unit.get("unit_number"),
                    "result": str(result),
                    "used": _contract_ref(used),
                    **await proposal_for(
                        session, unit_id, used, default_day=day, due_day=None, resolution_day=day
                    ),
                }
            )
        return {
            "statement_id": str(st.id),
            "resolution_day": day,
            "items": items,
            "note": NOTE,
        }
