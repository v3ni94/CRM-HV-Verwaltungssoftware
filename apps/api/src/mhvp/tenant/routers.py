"""Tenant setup steps (/api/v1/tenant): own legal entity of the managing company (A32)."""

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.tenant import manager_entity

router = APIRouter(prefix="/tenant", tags=["Mandant"])


class ManagerEntityOut(BaseModel):
    """``eingerichtet`` once legal entity and ledger exist, else ``nicht_eingerichtet``."""

    status: str
    name: str | None
    legal_entity_id: uuid.UUID | None
    ledger_id: uuid.UUID | None
    accounts_count: int
    created: bool


def _out(result: manager_entity.ManagerEntityStatus) -> ManagerEntityOut:
    return ManagerEntityOut(
        status=result.status,
        name=result.name,
        legal_entity_id=result.legal_entity_id,
        ledger_id=result.ledger_id,
        accounts_count=result.accounts_count,
        created=result.created,
    )


@router.get("/manager-entity", summary="Rechtsträger der verwaltenden Gesellschaft (Status)")
async def get_manager_entity(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> ManagerEntityOut:
    async with tenant_tx(request, principal) as session:
        return _out(await manager_entity.status(session))


@router.post(
    "/manager-entity",
    summary="Rechtsträger und Buchungskreis der verwaltenden Gesellschaft einrichten",
)
async def create_manager_entity(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> ManagerEntityOut:
    """Idempotent one-off setup step (Einstellungen, Mandant): creates the ``manager`` legal
    entity named after the tenant's company master data and its ledger with the default
    chart of accounts; a second call returns the existing state unchanged."""
    async with tenant_tx(request, principal) as session:
        return _out(
            await manager_entity.ensure(
                session, tenant_id=principal.tenant_id, user_id=principal.user_id
            )
        )
