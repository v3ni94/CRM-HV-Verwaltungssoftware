"""Portal endpoints of the monthly consumption information (rule H03, section 14 role tenant):
``GET /portal/consumption-info`` lists the stored months of the own units, ``GET
/portal/consumption-info/{id}`` adds the frozen snapshot. Scope comes from the active unit
grants only; a month outside the own contract period is never shown. Everything is locked
(403) until the tenant switch and the operator's template verification are on; the
operator's verification list never reaches this output."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import consumption_info
from mhvp.billing.models import ConsumptionInfo
from mhvp.core.auth.principal import tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings
from mhvp.portal import access
from mhvp.portal.models import PortalAccount
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal", tags=["Portal"])
LOCKED = "Die Verbrauchsinformation ist noch nicht freigeschaltet."


async def _scope(
    session: AsyncSession, account: PortalAccount, today: date
) -> dict[uuid.UUID, list[tuple[date, date | None]]]:
    """{unit_id: [(from, to)]} of the active tenancy grants (scope ``unit``, role ``tenant``)."""
    settings_row = await session.scalar(select(TenantSettings))
    if (
        settings_row is None
        or not settings_row.consumption_info_enabled
        or not settings_row.consumption_info_template_verified
    ):
        raise ProblemError(ErrorCodes.FORBIDDEN, detail=LOCKED)
    out: dict[uuid.UUID, list[tuple[date, date | None]]] = {}
    for g in await access.grants(session, account, today):
        if g.scope_type == "unit" and g.role == "tenant":
            out.setdefault(g.scope_id, []).append((g.valid_from, g.valid_to))
    if not out:
        raise ProblemError(ErrorCodes.FORBIDDEN, detail="Nur für Mieter verfügbar.")
    return out


def _in_scope(row: ConsumptionInfo, scope: dict[uuid.UUID, list[tuple[date, date | None]]]) -> bool:
    end = consumption_info.month_end(row.month)
    return any(
        start <= end and (stop is None or stop >= row.month)
        for start, stop in scope.get(row.unit_id, [])
    )


@router.get("/consumption-info", summary="Eigene Verbrauchsinformationen (Monate)")
async def list_own(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        scope = await _scope(session, account, local_today())
        rows = (
            await session.scalars(
                select(ConsumptionInfo)
                .where(ConsumptionInfo.unit_id.in_(list(scope)))
                .order_by(ConsumptionInfo.month.desc())
            )
        ).all()
        return [
            consumption_info.tenant_view(r, with_snapshot=False)
            for r in rows
            if _in_scope(r, scope)
        ]


@router.get("/consumption-info/{info_id}", summary="Eigene Verbrauchsinformation eines Monats")
async def get_own(
    info_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        scope = await _scope(session, account, local_today())
        row = await session.get(ConsumptionInfo, info_id)
        if row is None or not _in_scope(row, scope):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return consumption_info.tenant_view(row, with_snapshot=True)
