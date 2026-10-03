"""Allocation basis report of a statement and the tenant switch (M17-01, AE17)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from mhvp.billing import allocation_basis
from mhvp.billing.models import Statement
from mhvp.billing.raw_responses import (
    BillingAllocationBasisGetSettingOut,
)
from mhvp.billing.write_responses import BillingAllocationBasisSettingOut
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
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


@router.get(
    "",
    summary="Schalter: Prüfbericht blockiert die Ausgabe (Standard an)",
    response_model=BillingAllocationBasisGetSettingOut,
)
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


# AP17 / GAM-108: switch "every key of a rented condominium unit needs a confirmed source".
key_confirmation_router = APIRouter(
    prefix="/billing/allocation-key-confirmation-setting", tags=["Abrechnung"]
)


class BillingKeyConfirmationSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required: bool


class BillingKeyConfirmationSettingOut(BaseModel):
    required: bool


@key_confirmation_router.get(
    "",
    summary="Schalter: jeder Schlüssel bei vermietetem Wohnungseigentum braucht Bestätigung",
    dependencies=[Depends(strict_query)],
)
async def get_key_confirmation_setting(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> BillingKeyConfirmationSettingOut:
    async with tenant_tx(request, principal) as session:
        value = await session.scalar(select(TenantSettings.allocation_key_confirmation_required))
        return BillingKeyConfirmationSettingOut(required=bool(value))


@key_confirmation_router.put(
    "", summary="Schalter: Bestätigung jedes Schlüssels bei vermietetem Wohnungseigentum setzen"
)
async def put_key_confirmation_setting(
    body: BillingKeyConfirmationSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> BillingKeyConfirmationSettingOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.allocation_key_confirmation_required = body.required
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="allocation_key_confirmation_setting.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"required": body.required},
        )
        await session.flush()
        return BillingKeyConfirmationSettingOut(required=body.required)
