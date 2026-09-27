"""M35-01 technical preparation: `/api/v1/objektakte/local-model`. Status of the objektakte
model artifact and the per tenant flag (`objektakte:read`), and `POST
/objektakte/review/{case_id}/ask-local-model` style proposal for one review case
(`objektakte:update`), behind the flag `TenantSettings.objektakte_classification
["local_model"]["enabled"]` (default off). Always a proposal, never an applied category
(rule 0.1.6); the flag is set through the tenant settings endpoint, not here."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, DocumentLink
from mhvp.objektakte import local_model
from mhvp.objektakte.models import DocumentReviewCase
from mhvp.platform.models import TenantSettings
from mhvp.properties.models import Property

router = APIRouter(prefix="/objektakte/local-model", tags=["objektakte"])
READ = require_permission("objektakte:read")
UPDATE = require_permission("objektakte:update")


async def _flag(session: Any, tenant_id: uuid.UUID) -> local_model.LocalModelFlag:
    settings = await session.scalar(
        select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
    )
    return local_model.read_flag(settings)


@router.get("", summary="Stand des lokalen objektakte-Klassifikationsmodells")
async def get_status(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    models_dir = request.app.state.settings.objektakte_models_dir
    async with tenant_tx(request, principal) as session:
        flag = await _flag(session, principal.tenant_id)
    return {
        "enabled": flag.enabled,
        "version": flag.version,
        "artifact": local_model.artifact_status(models_dir, flag.version),
    }


@router.post("/cases/{case_id}/propose", summary="Vorschlag des lokalen Modells für einen Prüffall")
async def propose(
    request: Request, case_id: uuid.UUID, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    models_dir = request.app.state.settings.objektakte_models_dir
    predictor_override = getattr(request.app.state, "objektakte_local_predictor", None)  # tests
    async with tenant_tx(request, principal) as session:
        flag = await _flag(session, principal.tenant_id)
        if not flag.enabled:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Das lokale Klassifikationsmodell ist für diesen Mandanten ausgeschaltet.",
            )
        case = await session.get(DocumentReviewCase, case_id)
        if case is None or case.document_id is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        document = await session.get(Document, case.document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        management_type: str | None = None
        link = await session.scalar(
            select(DocumentLink).where(
                DocumentLink.document_id == document.id, DocumentLink.entity_type == "property"
            )
        )
        if link is not None:
            prop = await session.get(Property, link.entity_id)
            if prop is not None and getattr(prop, "management_type", None) is not None:
                management_type = str(prop.management_type.value)
        try:
            predictor = predictor_override or local_model.load_predictor(models_dir, flag)
            proposal = await local_model.propose_with_local_model(
                session, principal.tenant_id, document, predictor, management_type=management_type
            )
        except local_model.LocalModelUnavailableError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail=str(exc)) from None
        return {"case_id": str(case.id), "proposal": proposal}
