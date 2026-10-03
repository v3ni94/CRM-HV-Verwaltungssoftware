"""Tenant switch for direct debit approval (AO07, GAK-106).

``direct_debit_creator_may_not_approve`` (default off): the creator of a run may not approve it.
GET needs ``tenant_settings:read``, PUT ``tenant_settings:update``. Business question AN17-01
stays open; nothing is booked, sent or released here.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from mhvp.accounting.audit_events import record_change
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import TenantSettings

router = APIRouter(prefix="/accounting/direct-debit-settings", tags=["Buchhaltung"])


class DirectDebitSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direct_debit_creator_may_not_approve: bool


class DirectDebitSettingsOut(BaseModel):
    direct_debit_creator_may_not_approve: bool


@router.get(
    "",
    summary="Lastschrift: Ersteller darf nicht freigeben (Schalter)",
    dependencies=[Depends(strict_query)],
)
async def get_direct_debit_settings(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> DirectDebitSettingsOut:
    async with tenant_tx(request, principal) as session:
        value = await session.scalar(select(TenantSettings.direct_debit_creator_may_not_approve))
        return DirectDebitSettingsOut(direct_debit_creator_may_not_approve=bool(value))


@router.put("", summary="Lastschrift: Ersteller darf nicht freigeben setzen")
async def put_direct_debit_settings(
    body: DirectDebitSettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> DirectDebitSettingsOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        old = row.direct_debit_creator_may_not_approve
        row.direct_debit_creator_may_not_approve = body.direct_debit_creator_may_not_approve
        await record_change(
            session,
            tenant_id=principal.tenant_id,
            type="direct_debit_settings.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            before={"direct_debit_creator_may_not_approve": old},
            after={
                "direct_debit_creator_may_not_approve": body.direct_debit_creator_may_not_approve
            },
        )
        return DirectDebitSettingsOut(
            direct_debit_creator_may_not_approve=body.direct_debit_creator_may_not_approve
        )
