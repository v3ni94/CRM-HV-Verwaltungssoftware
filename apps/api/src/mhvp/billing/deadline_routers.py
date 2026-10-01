"""Statement deadline overview and tenant switches (M17-04, orientation only)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from mhvp.billing import deadline
from mhvp.billing.models import Statement, StatementSnapshot
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_column_guard
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

STATEMENT_GUARD = property_column_guard({"statement_id": Statement.property_id})
router = APIRouter(prefix="/billing/deadline-settings", tags=["Abrechnung"])
statement_router = APIRouter(
    prefix="/statements", tags=["Abrechnung"], dependencies=[Depends(STATEMENT_GUARD)]
)
READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")


class BillingDeadlineSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: str | None = Field(default=None, pattern="^(block_claims|notice)$")
    watch_enabled: bool | None = None
    warn_days_first: int | None = Field(default=None, ge=1, le=365)
    warn_days_second: int | None = Field(default=None, ge=1, le=365)


def _out(row: Any) -> dict[str, Any]:
    return {
        "policy": row.policy,
        "watch_enabled": row.watch_enabled,
        "warn_days_first": row.warn_days_first,
        "warn_days_second": row.warn_days_second,
        "notice": deadline.NOTICE_TEXT,
    }


@router.get(
    "", summary="Schalter der Abrechnungsfrist (Orientierung)", dependencies=[Depends(strict_query)]
)
async def get_settings(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _out(await deadline.setting(session, principal.tenant_id))


@router.put("", summary="Schalter der Abrechnungsfrist setzen")
async def put_settings(
    body: BillingDeadlineSettingIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await deadline.setting(session, principal.tenant_id)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="statement.deadline_settings_changed",
            entity_type="tenant",
            entity_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            payload=body.model_dump(exclude_none=True),
        )
        return _out(row)


@statement_router.get(
    "/{statement_id}/deadlines",
    summary="Fristende und Zugang je Vertrag (Orientierung)",
    dependencies=[Depends(strict_query)],
)
async def get_deadlines(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await session.get(Statement, statement_id)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        snap = await session.get(StatementSnapshot, st.snapshot_id) if st.snapshot_id else None
        return await deadline.overview(session, st, snap, local_today())
