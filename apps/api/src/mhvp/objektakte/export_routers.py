"""Objektakte export for the successor manager (M12 gaps, 29.09.2026):
``/api/v1/properties/{id}/objektakte-export``. Starting needs ``properties:update`` and
``documents:read`` plus the operator's confirmation of the personal data note; the ZIP is
built by the Celery job ``mhvp.objektakte.export_property`` (see ``mhvp.objektakte.export``)
and filed as a document of the property. Every download is the domain event
``objektakte_export.downloaded`` with the user."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.escaping import content_disposition
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.objektakte.export import PERSONAL_DATA_NOTE
from mhvp.objektakte.models import ObjektakteExport, ObjektakteExportStatus
from mhvp.properties.models import Property, PropertyStatus, PropertyTermination

router = APIRouter(prefix="/properties", tags=["Objekte"])
UPDATE = require_permission("properties:update")
READ = require_permission("properties:read")


class ObjektakteExportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool = False
    personal_data_acknowledged: bool = False
    note: str | None = Field(default=None, max_length=1000)


def _out(row: ObjektakteExport) -> dict[str, Any]:
    return {
        "id": row.id,
        "property_id": row.property_id,
        "status": row.status.value,
        "requested_by": row.requested_by,
        "note": row.note,
        "document_id": row.document_id,
        "counts": row.counts,
        "error": row.error,
        "created_at": row.created_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "download_count": row.download_count,
        "last_downloaded_at": row.last_downloaded_at,
    }


def _require_documents_read(principal: TenantPrincipal) -> None:
    if not principal.has("documents:read"):
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Missing documents:read.")


async def _property(session: Any, property_id: uuid.UUID) -> Property:
    row: Property | None = await session.get(Property, property_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.get("/{property_id}/objektakte-export", summary="Exporte der Objektakte (Abgabe)")
async def list_exports(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _property(session, property_id)
        rows = list(
            await session.scalars(
                select(ObjektakteExport)
                .where(ObjektakteExport.property_id == property_id)
                .order_by(ObjektakteExport.created_at.desc())
            )
        )
        return {
            "items": [_out(r) for r in rows],
            "personal_data_note": PERSONAL_DATA_NOTE,
            "can_start": principal.has("properties:update") and principal.has("documents:read"),
        }


@router.post(
    "/{property_id}/objektakte-export",
    status_code=202,
    summary="Objektakte für den Nachfolger exportieren (Hintergrundjob, ZIP als Dokument)",
)
async def start_export(
    property_id: uuid.UUID,
    body: ObjektakteExportIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Needs a recorded termination (Verwaltung beenden) or the status ``terminated``, the
    confirmation and the acknowledged personal data note. One export at a time per property."""
    from mhvp.objektakte.tasks import export_property

    _require_documents_read(principal)
    if not body.confirm or not body.personal_data_acknowledged:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Export und Datenschutzhinweis sind zu bestätigen.",
        )
    async with tenant_tx(request, principal) as session:
        prop = await _property(session, property_id)
        termination = await session.scalar(
            select(PropertyTermination.id).where(PropertyTermination.property_id == prop.id)
        )
        if termination is None and prop.status is not PropertyStatus.TERMINATED:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Zuerst die Beendigung der Verwaltung erfassen (Verwaltung beenden).",
            )
        running = await session.scalar(
            select(ObjektakteExport.id).where(
                ObjektakteExport.property_id == prop.id,
                ObjektakteExport.status.in_(
                    [ObjektakteExportStatus.QUEUED, ObjektakteExportStatus.RUNNING]
                ),
            )
        )
        if running is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ein Export läuft bereits.")
        row = ObjektakteExport(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_id=prop.id,
            requested_by=principal.user_id,
            personal_data_acknowledged=True,
            note=body.note,
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="objektakte_export.requested",
            entity_type="objektakte_export",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"property_id": str(prop.id), "note": body.note},
        )
        await session.refresh(row)
        out = _out(row)
    export_property.delay(str(principal.tenant_id), str(row.id))
    return out


@router.get(
    "/{property_id}/objektakte-export/{export_id}",
    summary="Stand eines Objektakte-Exports",
)
async def get_export(
    property_id: uuid.UUID,
    export_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ObjektakteExport, export_id)
        if row is None or row.property_id != property_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _out(row)


@router.get(
    "/{property_id}/objektakte-export/{export_id}/download",
    summary="ZIP des Objektakte-Exports herunterladen (Ereignis je Abruf)",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
)
async def download_export(
    property_id: uuid.UUID,
    export_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    from mhvp.documents.blobs import BlobStore

    _require_documents_read(principal)
    async with tenant_tx(request, principal) as session:
        row = await session.get(ObjektakteExport, export_id, with_for_update=True)
        if row is None or row.property_id != property_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status is not ObjektakteExportStatus.DONE or row.document_id is None:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail=f"Der Export ist nicht fertig ({row.status.value})."
            )
        document = await session.get(Document, row.document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument fehlt.")
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        row.download_count += 1
        row.last_downloaded_at = datetime.now(UTC)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="objektakte_export.downloaded",
            entity_type="objektakte_export",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"property_id": str(property_id), "document_id": str(document.id)},
        )
        filename = document.filename
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition("attachment", filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
