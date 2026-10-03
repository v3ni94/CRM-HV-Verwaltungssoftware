"""Allocation basis report of a statement and the tenant switch (M17-01, AE17)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from mhvp.billing import allocation_basis
from mhvp.billing.models import Statement
from mhvp.billing.write_responses import BillingAllocationBasisSettingOut
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings

READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")
GUARD = property_column_guard({"statement_id": Statement.property_id})
statement_router = APIRouter(
    prefix="/statements", tags=["Abrechnung"], dependencies=[Depends(GUARD)]
)
router = APIRouter(prefix="/billing/allocation-basis-setting", tags=["Abrechnung"])


class AllocationBasisSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_output: bool


@statement_router.get(
    "/{statement_id}/allocation-basis-report",
    summary="Prüfbericht fehlender Umlagegrundlagen vor der Abrechnung (M17-01)",
)
async def basis_report(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        statement = await session.get(Statement, statement_id)
        if statement is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await allocation_basis.report(session, statement)


@router.get("", summary="Schalter: Prüfbericht blockiert die Ausgabe (Standard an)")
async def get_setting(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, bool]:
    async with tenant_tx(request, principal) as session:
        return {"block_output": await allocation_basis.blocking_enabled(session)}


@router.put(
    "",
    response_model=BillingAllocationBasisSettingOut,
    summary="Schalter: Prüfbericht blockiert die Ausgabe setzen",
)
async def put_setting(
    body: AllocationBasisSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, bool]:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.allocation_basis_block = body.block_output
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="allocation_basis_setting.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"block_output": body.block_output},
        )
        await session.flush()
        return {"block_output": body.block_output}
