"""Acceptance register endpoints (/api/v1/accounting/acceptance, V16, AE01).

Reading needs ``acceptance:read``; drafts ``acceptance:manage``; releasing an expected value
and recording an acceptance result ``acceptance:approve`` and a person (no API key). The
author of a version never releases it. Nothing here opens a gate.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response

from mhvp.accounting import acceptance as svc
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/accounting/acceptance", tags=["Buchhaltung"])
READ = require_permission("acceptance:read")
MANAGE = require_permission("acceptance:manage")
APPROVE = require_permission("acceptance:approve")


def _person(principal: TenantPrincipal) -> uuid.UUID:
    if principal.user_id is None:
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Acceptance actions need a person."
        )
    return principal.user_id


@router.get(
    "/cases",
    summary="Abnahmeregister: Fälle D01 bis D58 mit Sollwert und Ergebnis",
    dependencies=[Depends(strict_query)],
)
async def list_cases(
    request: Request,
    status: str | None = Query(
        default=None, pattern="^(draft|submitted|approved|rejected|superseded)$"
    ),
    principal: TenantPrincipal = Depends(READ),
) -> svc.AcceptanceCaseList:
    async with tenant_tx(request, principal) as session:
        return await svc.list_cases(session, status)


@router.get(
    "/export.md",
    summary="Abnahmeprotokoll als Markdown",
    dependencies=[Depends(strict_query)],
    response_class=Response,
)
async def export_markdown(request: Request, principal: TenantPrincipal = Depends(READ)) -> Response:
    async with tenant_tx(request, principal) as session:
        text = await svc.export_markdown(session)
    return Response(
        content=text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="abnahme-anhang-d.md"'},
    )


@router.get(
    "/cases/{case_id}",
    summary="Fassungen und Ergebnisse eines Falls",
    dependencies=[Depends(strict_query)],
)
async def case_detail(
    case_id: str, request: Request, principal: TenantPrincipal = Depends(READ)
) -> svc.AcceptanceCaseDetail:
    async with tenant_tx(request, principal) as session:
        return await svc.case_detail(session, case_id)


@router.post("/cases/{case_id}/expected", status_code=201, summary="Sollwert als Entwurf erfassen")
async def create_draft(
    case_id: str,
    body: svc.AcceptanceExpectedIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> svc.AcceptanceExpectedOut:
    user_id = _person(principal)
    async with tenant_tx(request, principal) as session:
        return await svc.create_draft(
            session, tenant_id=principal.tenant_id, user_id=user_id, case_id=case_id, body=body
        )


@router.put("/expected/{expected_id}", summary="Entwurf eines Sollwerts ändern")
async def update_draft(
    expected_id: uuid.UUID,
    body: svc.AcceptanceExpectedIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> svc.AcceptanceExpectedOut:
    user_id = _person(principal)
    async with tenant_tx(request, principal) as session:
        return await svc.update_draft(session, user_id=user_id, expected_id=expected_id, body=body)


@router.post("/expected/{expected_id}/submit", summary="Sollwert zur Freigabe einreichen")
async def submit(
    expected_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> svc.AcceptanceExpectedOut:
    user_id = _person(principal)
    async with tenant_tx(request, principal) as session:
        return await svc.submit(session, user_id=user_id, expected_id=expected_id)


@router.post(
    "/expected/{expected_id}/decision",
    summary="Sollwert freigeben oder ablehnen (zweite Person)",
)
async def decide(
    expected_id: uuid.UUID,
    body: svc.AcceptanceDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> svc.AcceptanceExpectedOut:
    user_id = _person(principal)
    async with tenant_tx(request, principal) as session:
        return await svc.decide(session, user_id=user_id, expected_id=expected_id, body=body)


@router.post(
    "/expected/{expected_id}/results",
    status_code=201,
    summary="Abnahmeergebnis zu einem freigegebenen Sollwert eintragen",
)
async def record_result(
    expected_id: uuid.UUID,
    body: svc.AcceptanceResultIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> svc.AcceptanceResultOut:
    user_id = _person(principal)
    async with tenant_tx(request, principal) as session:
        return await svc.record_result(
            session,
            tenant_id=principal.tenant_id,
            user_id=user_id,
            expected_id=expected_id,
            body=body,
        )
