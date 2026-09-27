"""`GET /api/v1/objektakte/reconciliation` (M35 Stufe 5, parallel operation): the document
reconciliation report objektakte vs. CRM per object. Reads objektakte through the same client
and connection checks as the DMS page (`mhvp.objektakte.dms_routers._client`), needs
`objektakte:read`. `?number=` limits the report to one object (cheaper during the day; the
full run walks every object of objektakte, one paged request each)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.objektakte import dms_service as svc
from mhvp.objektakte import reconciliation
from mhvp.objektakte.dms_routers import _client, _upstream
from mhvp.objektakte.remote import ObjektakteError

router = APIRouter(prefix="/objektakte/reconciliation", tags=["objektakte"])
READ = require_permission("objektakte:read")


@router.get("", summary="Abgleichbericht objektakte gegen CRM (Dokumente je Objekt)")
async def get_reconciliation(
    request: Request,
    number: str | None = Query(default=None, max_length=16, pattern=r"^[0-9A-Za-z]{1,16}$"),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    client = await _client(request, principal)
    remote: list[reconciliation.RemoteDoc] = []
    try:
        async with client:
            raw_numbers = (
                [number]
                if number
                else [
                    str(obj.get("number"))
                    for obj in await client.objects()
                    if obj.get("number") is not None
                ]
            )
            for raw in raw_numbers:
                key = svc.normalize_number(raw) or raw
                rows = await client.all_documents(raw)
                remote.extend(reconciliation.remote_documents(key, rows))
    except ObjektakteError as exc:
        raise _upstream(exc) from None
    async with tenant_tx(request, principal) as session:
        crm = await reconciliation.crm_documents(session, principal.tenant_id)
    wanted = (svc.normalize_number(number) or number) if number else None
    if wanted:
        crm = [doc for doc in crm if doc.object_number == wanted]
    report = reconciliation.reconcile(crm, remote)
    report["scope"] = {"number": wanted}
    return report
