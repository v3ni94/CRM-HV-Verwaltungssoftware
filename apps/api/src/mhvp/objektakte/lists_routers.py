"""M35 Stufe 4, part "Listengenerierung" (docs/plans/M35-objektakte-uebernahme.md section 4):
read only list endpoints under `/api/v1/objektakte`, each as JSON and as CSV export.

* `GET /objektakte/lists/missing-documents` (+ `/export`): Anforderungsliste over all
  properties of the tenant.
* `GET /objektakte/properties/{id}/lists/missing-documents` (+ `/export`): Anforderungsliste
  of one property.
* `GET /objektakte/properties/{id}/lists/documents` (+ `/export`): Dokumentenübersicht je
  Kategorie of one property.
* `GET /objektakte/properties/{id}/lists/owners` and `.../tenants` (+ `/export`):
  Eigentümerliste and Mieterliste of one property (persons from current contracts, contact
  fields as shown in the CRM, no bank data).
* `POST /objektakte/properties/{id}/lists/{kind}/store`: generate the CSV of one list kind and
  file it as a document of the property (category "Liste").

Permission `objektakte:read` for reading (docs/rules/M35-03.md, same as the completeness check
the lists build on); storing a list creates a document and therefore needs `documents:create`
in addition.
Tenant separation comes from RLS inside `tenant_tx`; a property of another tenant is simply
not found (404), never revealed.
"""

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import schemas as document_schemas
from mhvp.documents.blobs import BlobStore
from mhvp.documents.routers import _out as document_out
from mhvp.objektakte import lists
from mhvp.properties.models import ManagementType, Property

router = APIRouter(prefix="/objektakte", tags=["objektakte-lists"])
READ = require_permission("objektakte:read")
DOCUMENTS_CREATE = require_permission("documents:create")
CSV_MEDIA_TYPE = "text/csv; charset=utf-8"


async def _property(session: AsyncSession, property_id: uuid.UUID) -> Property:
    row = await session.get(Property, property_id)
    if row is None:
        raise ProblemError(ErrorCodes.NOT_FOUND)
    return row


def _csv_response(content: str, filename: str) -> Response:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    return Response(
        content,
        media_type=CSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


@router.get("/lists/missing-documents", summary="Anforderungsliste über alle Objekte")
async def overview_missing_documents(
    request: Request,
    management_type: ManagementType | None = Query(default=None),
    only_incomplete: bool = Query(default=False),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        items = await lists.missing_documents_overview(
            session,
            principal.tenant_id,
            management_type=management_type,
            only_incomplete=only_incomplete,
        )
        return {"items": items, "total": len(items)}


@router.get(
    "/lists/missing-documents/export",
    summary="Anforderungsliste über alle Objekte als CSV",
    response_class=Response,
)
async def export_overview_missing_documents(
    request: Request,
    management_type: ManagementType | None = Query(default=None),
    only_incomplete: bool = Query(default=False),
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        items = await lists.missing_documents_overview(
            session,
            principal.tenant_id,
            management_type=management_type,
            only_incomplete=only_incomplete,
        )
        return _csv_response(lists.missing_documents_csv(items), "anforderungsliste.csv")


@router.get(
    "/properties/{property_id}/lists/missing-documents",
    summary="Anforderungsliste fehlender Unterlagen eines Objekts",
)
async def property_missing_documents(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        return await lists.missing_documents_list(session, principal.tenant_id, property_row)


@router.get(
    "/properties/{property_id}/lists/missing-documents/export",
    summary="Anforderungsliste eines Objekts als CSV",
    response_class=Response,
)
async def export_property_missing_documents(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        entry = await lists.missing_documents_list(session, principal.tenant_id, property_row)
        return _csv_response(
            lists.missing_documents_csv([entry]),
            f"anforderungsliste-{property_row.number}.csv",
        )


@router.get(
    "/properties/{property_id}/lists/documents",
    summary="Dokumentenübersicht je Kategorie eines Objekts",
)
async def property_documents(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        return await lists.documents_by_category(session, principal.tenant_id, property_row)


@router.get(
    "/properties/{property_id}/lists/documents/export",
    summary="Dokumentenübersicht eines Objekts als CSV",
    response_class=Response,
)
async def export_property_documents(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        overview = await lists.documents_by_category(session, principal.tenant_id, property_row)
        return _csv_response(
            lists.documents_csv(overview), f"dokumentenuebersicht-{property_row.number}.csv"
        )


@router.get(
    "/properties/{property_id}/lists/{kind}",
    summary="Eigentümerliste oder Mieterliste eines Objekts",
)
async def property_persons(
    property_id: uuid.UUID,
    kind: lists.PersonListKind,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        return await lists.persons_list(session, principal.tenant_id, property_row, kind)


@router.get(
    "/properties/{property_id}/lists/{kind}/export",
    summary="Eigentümerliste oder Mieterliste eines Objekts als CSV",
    response_class=Response,
)
async def export_property_persons(
    property_id: uuid.UUID,
    kind: lists.PersonListKind,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        listing = await lists.persons_list(session, principal.tenant_id, property_row, kind)
        return _csv_response(
            lists.persons_csv(listing),
            f"{lists.LIST_FILE_STEMS[kind]}-{property_row.number}.csv",
        )


@router.post(
    "/properties/{property_id}/lists/{kind}/store",
    status_code=201,
    summary="Liste eines Objekts als Dokument ablegen",
)
async def store_property_list(
    property_id: uuid.UUID,
    kind: lists.ListKind,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    _creator: TenantPrincipal = Depends(DOCUMENTS_CREATE),
) -> document_schemas.DocumentOut:
    """Generates the CSV of `kind` and files it as a new document (category "Liste", source
    generated, linked to the property). Every call stores a new snapshot."""
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        document = await lists.store_list(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            property_row=property_row,
            kind=kind,
            created_by=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document.created",
            entity_type="document",
            entity_id=document.id,
            actor_user_id=principal.user_id,
            payload={"size": document.size, "list_kind": kind, "property_id": str(property_id)},
        )
        return await document_out(session, document)
