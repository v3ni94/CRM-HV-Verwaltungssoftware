"""G1 opening checklist endpoints (/api/v1/accounting/g1-opening, M12-09).

Reading needs ``accounting:read``; recording an acceptance result ``accounting:approve``;
filing the G1 request the same right as the platform flow, ``release_gates:create``, and a
person (no API key). The decision stays with a second person on the platform page.
"""

import uuid

from fastapi import APIRouter, Depends, Request

from mhvp.accounting import g1_opening as svc
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/accounting/g1-opening", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")
REQUEST = require_permission("release_gates:create")


@router.get("", summary="Checkliste zur Öffnung der Freigabestufe G1")
async def overview(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> svc.G1OpeningOut:
    async with tenant_tx(request, principal) as session:
        return await svc.overview(session)


@router.put("/items/{item_key}", summary="Ergebnis eines Prüfpunkts eintragen")
async def set_item(
    item_key: str,
    body: svc.ItemIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> svc.ItemOut:
    async with tenant_tx(request, principal) as session:
        return await svc.set_item(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            item_key=item_key,
            body=body,
        )


@router.post("/request", status_code=201, summary="Freigabe G1 beantragen (Vier Augen)")
async def file_request(
    body: svc.RequestIn, request: Request, principal: TenantPrincipal = Depends(REQUEST)
) -> svc.GateRequestSummary:
    if principal.user_id is None:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Gate requests need a person, not an API key."
        )
    user_id: uuid.UUID = principal.user_id
    async with tenant_tx(request, principal) as session:
        return await svc.file_request(
            session, tenant_id=principal.tenant_id, user_id=user_id, body=body
        )
