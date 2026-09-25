"""M35 Stufe 3 part 4 (docs/plans/M35-objektakte-uebernahme.md section 4): completeness check
and its settings. `/api/v1/objektakte/required-documents` (settings, list/create/delete) and
`/api/v1/objektakte/properties/{id}/completeness` (+ a "Nachforderungsschreiben" draft text).

Permissions: `documents:read` for the checks and listing required documents, `documents:update`
for changing the required-document settings (same pair as the review center).
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import DocumentCategory
from mhvp.objektakte.completeness import check_completeness, nachforderungsschreiben_text
from mhvp.objektakte.models import ObjektakteRequiredDocument
from mhvp.properties.models import ManagementType, Property

router = APIRouter(prefix="/objektakte", tags=["objektakte-completeness"])
READ = require_permission("documents:read")
UPDATE = require_permission("documents:update")


def _row_out(row: ObjektakteRequiredDocument) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "management_type": row.management_type.value,
        "document_category_id": str(row.document_category_id),
        "mandatory": row.mandatory,
    }


@router.get("/required-documents", summary="Pflichtunterlagen je Verwaltungsart auflisten")
async def list_required_documents(
    request: Request,
    management_type: ManagementType | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        stmt = select(ObjektakteRequiredDocument)
        if management_type is not None:
            stmt = stmt.where(ObjektakteRequiredDocument.management_type == management_type)
        rows = (await session.execute(stmt)).scalars().all()
        return [_row_out(r) for r in rows]


class RequiredDocumentIn(BaseModel):
    management_type: ManagementType
    document_category_id: uuid.UUID
    mandatory: bool = True


@router.post("/required-documents", status_code=201, summary="Pflichtunterlage anlegen oder ändern")
async def upsert_required_document(
    body: RequiredDocumentIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        category = await session.get(DocumentCategory, body.document_category_id)
        if category is None:
            raise ProblemError(ErrorCodes.NOT_FOUND, detail="Dokumentkategorie nicht gefunden.")
        row = await session.scalar(
            select(ObjektakteRequiredDocument).where(
                ObjektakteRequiredDocument.management_type == body.management_type,
                ObjektakteRequiredDocument.document_category_id == body.document_category_id,
            )
        )
        if row is None:
            row = ObjektakteRequiredDocument(
                tenant_id=principal.tenant_id,
                management_type=body.management_type,
                document_category_id=body.document_category_id,
            )
            session.add(row)
        row.mandatory = body.mandatory
        await session.flush()
        await session.refresh(row)
        return _row_out(row)


@router.delete(
    "/required-documents/{required_id}",
    status_code=204,
    summary="Pflichtunterlage entfernen",
)
async def delete_required_document(
    required_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> None:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ObjektakteRequiredDocument, required_id)
        if row is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        await session.delete(row)


async def _property(session: AsyncSession, property_id: uuid.UUID) -> Property:
    row = await session.get(Property, property_id)
    if row is None:
        raise ProblemError(ErrorCodes.NOT_FOUND)
    return row


@router.get(
    "/properties/{property_id}/completeness", summary="Vollständigkeit der Objektakte prüfen"
)
async def get_completeness(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        result = await check_completeness(session, principal.tenant_id, property_row)
        return result.as_dict()


@router.post(
    "/properties/{property_id}/completeness/nachforderungsschreiben",
    summary="Nachforderungsschreiben als Entwurf erzeugen",
)
async def draft_nachforderungsschreiben(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        result = await check_completeness(session, principal.tenant_id, property_row)
        if not result.missing:
            return {"draft": False, "text": None, "missing": []}
        text = nachforderungsschreiben_text(property_row, result.missing)
        return {"draft": True, "text": text, "missing": [vars(m) for m in result.missing]}
