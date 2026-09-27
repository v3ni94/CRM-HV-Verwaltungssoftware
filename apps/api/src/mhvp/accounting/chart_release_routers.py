"""Chart of accounts release endpoints (/api/v1/accounting/templates/{id}/..., M10-01/M10-02).

Submit for review and new version need ``accounting:update``, the release itself
``accounting:approve`` (existing route in ``mhvp.accounting.routers``), history and exports
``accounting:read`` so that the tax advisor role can read the chart it is asked to release.
"""

import uuid
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import chart_release as svc
from mhvp.accounting.models import ChartTemplate
from mhvp.accounting.schemas import ChartTemplateOut
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/accounting/templates", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
UPDATE = require_permission("accounting:update")


async def _template(session: AsyncSession, template_id: uuid.UUID) -> ChartTemplate:
    template = await session.get(ChartTemplate, template_id)
    if template is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return template


@router.post("/{template_id}/submit-review", summary="Kontenrahmen zur Prüfung geben")
async def submit_review(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> ChartTemplateOut:
    async with tenant_tx(request, principal) as session:
        template = await _template(session, template_id)
        template = await svc.submit_review(
            session, template, tenant_id=principal.tenant_id, user_id=principal.user_id
        )
        return ChartTemplateOut.model_validate(template)


@router.post("/{template_id}/back-to-draft", summary="Kontenrahmen zurück in den Entwurf")
async def back_to_draft(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> ChartTemplateOut:
    async with tenant_tx(request, principal) as session:
        template = await _template(session, template_id)
        template = await svc.back_to_draft(
            session, template, tenant_id=principal.tenant_id, user_id=principal.user_id
        )
        return ChartTemplateOut.model_validate(template)


@router.post(
    "/{template_id}/versions",
    status_code=201,
    summary="Neue Version des Kontenrahmens anlegen (Entwurf)",
)
async def new_version(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> ChartTemplateOut:
    async with tenant_tx(request, principal) as session:
        template = await _template(session, template_id)
        created = await svc.new_version(
            session, template, tenant_id=principal.tenant_id, user_id=principal.user_id
        )
        return ChartTemplateOut.model_validate(created)


@router.put("/{template_id}/accounts", summary="Konten eines Entwurfs ersetzen")
async def update_accounts(
    template_id: uuid.UUID,
    body: svc.AccountsIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> ChartTemplateOut:
    async with tenant_tx(request, principal) as session:
        template = await _template(session, template_id)
        template = await svc.update_accounts(
            session, template, body, tenant_id=principal.tenant_id, user_id=principal.user_id
        )
        return ChartTemplateOut.model_validate(template)


@router.get("/{template_id}/history", summary="Versionsverlauf des Kontenrahmens")
async def history(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[ChartTemplateOut]:
    async with tenant_tx(request, principal) as session:
        template = await _template(session, template_id)
        return [
            ChartTemplateOut.model_validate(t) for t in await svc.history(session, template.code)
        ]


@router.get("/{template_id}/export", summary="Kontenrahmen als CSV oder PDF für den Steuerberater")
async def export(
    template_id: uuid.UUID,
    request: Request,
    format: Literal["csv", "pdf"] = Query(default="csv"),
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        template = await _template(session, template_id)
        from mhvp.platform.models import Tenant

        tenant = await session.get(Tenant, principal.tenant_id)
        tenant_name = tenant.name if tenant else ""
        filename = f"kontenrahmen-{template.code}-v{template.version}.{format}"
        headers = {"content-disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}
        if format == "pdf":
            return Response(
                svc.export_pdf(template, tenant_name=tenant_name),
                media_type="application/pdf",
                headers=headers,
            )
        return Response(
            svc.export_csv(template).encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers=headers,
        )
