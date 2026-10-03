"""Anhänge am Antwortentwurf (operator 27.09.2026, Betreiberwunsch "Antworten"): Liste,
Verknüpfen eines vorhandenen DMS-Dokuments (Verweis, keine Kopie), Upload vom lokalen Rechner
(Multipart, Größen-, Typ- und Inhaltsprüfung sowie Virenscan wie jeder andere Upload, Ablage
als Dokument des Mandanten) und Entfernen. Änderungen sind nur am Entwurf erlaubt
(``direction = out``, ``status = draft``); die Dokumente selbst bleiben unberührt. Beim
Versand fügt ``mhvp.communication.attachments.attach_documents`` alle Verweise bei."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.escaping import LIKE_ESCAPE, escape_like
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError

router = APIRouter(prefix="/mail", tags=["Postfach"])
READ = require_permission("communication:read")
UPDATE = require_permission("communication:update")

MAX_ATTACHMENTS = 20


class DraftAttachmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID


def _attachment_out(document: Any) -> dict[str, Any]:
    return {
        "document_id": document.id,
        "title": document.title,
        "filename": document.filename,
        "mime_type": document.mime_type,
        "size": document.size,
    }


async def _draft(session: AsyncSession, message_id: uuid.UUID, principal: TenantPrincipal) -> Any:
    from mhvp.communication.routers import _message

    row = await _message(session, message_id, principal)
    if row.direction != "out" or row.status != "draft":
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Anhänge können nur an einem Entwurf geändert werden.",
        )
    return row


async def _listing(session: AsyncSession, document_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    from mhvp.documents.models import Document

    if not document_ids:
        return []
    rows = (await session.scalars(select(Document).where(Document.id.in_(document_ids)))).all()
    by_id = {d.id: d for d in rows}
    # Reihenfolge des Entwurfs; Dokumente, die der Mandantenfilter (RLS) nicht liefert,
    # werden nicht angezeigt.
    return [_attachment_out(by_id[i]) for i in document_ids if i in by_id]


@router.get(
    "/messages/{message_id}/attachments",
    summary="Anhänge einer Nachricht",
    dependencies=[Depends(strict_query)],
)
async def list_attachments(
    message_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    from mhvp.communication.routers import _message

    async with tenant_tx(request, principal) as session:
        row = await _message(session, message_id, principal)
        return await _listing(session, list(row.attachment_document_ids))


@router.get(
    "/messages/{message_id}/attachment-candidates",
    summary="Dokumente des Mandanten als Anhang suchen (DMS)",
    dependencies=[Depends(strict_query)],
)
async def attachment_candidates(
    message_id: uuid.UUID,
    request: Request,
    q: str = Query(min_length=2, max_length=200),
    principal: TenantPrincipal = Depends(UPDATE),
) -> list[dict[str, Any]]:
    """Suche nach Titel oder Dateiname, höchstens 20 Treffer, nur Metadaten; der
    Rechtsträgerbereich der Mitgliedschaft (A37) gilt unverändert."""
    from mhvp.communication.routers import _message
    from mhvp.documents.models import Document
    from mhvp.documents.routers import _scope_filter

    async with tenant_tx(request, principal) as session:
        await _message(session, message_id, principal)
        like = f"%{escape_like(q.strip())}%"
        query = select(Document).where(
            or_(
                Document.title.ilike(like, escape=LIKE_ESCAPE),
                Document.filename.ilike(like, escape=LIKE_ESCAPE),
            )
        )
        scoped = _scope_filter(session)
        if scoped is not None:
            query = query.where(Document.id.in_(scoped))
        docs = (await session.scalars(query.order_by(Document.created_at.desc()).limit(20))).all()
        return [_attachment_out(d) for d in docs]


def _append(row: Any, document_id: uuid.UUID) -> None:
    ids = list(row.attachment_document_ids)
    if document_id in ids:
        return
    if len(ids) >= MAX_ATTACHMENTS:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=f"Höchstens {MAX_ATTACHMENTS} Anhänge je Entwurf.",
        )
    ids.append(document_id)
    row.attachment_document_ids = ids  # neue Liste, damit SQLAlchemy die Änderung erkennt


@router.post(
    "/messages/{message_id}/attachments",
    status_code=201,
    summary="DMS-Dokument als Anhang des Entwurfs verknüpfen",
)
async def add_attachment(
    message_id: uuid.UUID,
    body: DraftAttachmentIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> list[dict[str, Any]]:
    from mhvp.documents.models import Document
    from mhvp.documents.routers import _scope_filter

    async with tenant_tx(request, principal) as session:
        row = await _draft(session, message_id, principal)
        query = select(Document).where(Document.id == body.document_id)
        scoped = _scope_filter(session)
        if scoped is not None:
            query = query.where(Document.id.in_(scoped))
        document = await session.scalar(query)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Dokument nicht gefunden.")
        from mhvp.documents import payment_files  # local: import cycle

        await payment_files.ensure_no_payment_attachment(session, [document.id])
        _append(row, document.id)
        row.updated_by = principal.user_id
        await session.flush()
        return await _listing(session, list(row.attachment_document_ids))


@router.post(
    "/messages/{message_id}/attachments/upload",
    status_code=201,
    summary="Datei vom lokalen Rechner als Anhang hochladen",
)
async def upload_attachment(
    message_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(),
    title: str | None = Form(default=None, max_length=300),
    principal: TenantPrincipal = Depends(UPDATE),
) -> list[dict[str, Any]]:
    """Gleiche Prüfungen wie ``POST /documents`` (Größe, zulässiger Typ, Inhalt passt zum
    Typ, Virenscan in ``store_document``); die Datei wird als Dokument des Mandanten abgelegt
    und mit dem Vorgang des Entwurfs verknüpft, falls vorhanden."""
    from mhvp.documents import services as document_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.handover import images

    settings = request.app.state.settings
    limit = settings.document_max_bytes
    data = await file.read(limit + 1)
    mime = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    document_services.check_upload(mime, data, limit)
    if images.supports(mime):
        try:
            data = images.sanitize_image(data, mime, max_edge=settings.handover_image_max_edge)
            mime = images.output_mime_type(mime)
        except images.ImageSanitizeError:
            pass
    filename = (file.filename or "anhang").replace("/", "_").replace("\\", "_")
    async with tenant_tx(request, principal) as session:
        row = await _draft(session, message_id, principal)
        if len(row.attachment_document_ids) >= MAX_ATTACHMENTS:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Höchstens {MAX_ATTACHMENTS} Anhänge je Entwurf."
            )
        links: list[tuple[str, uuid.UUID, LinkRole]] = []
        if row.ticket_id:
            links.append(("ticket", row.ticket_id, LinkRole.ATTACHMENT))
        document = await document_services.store_document(
            session,
            BlobStore(settings),
            tenant_id=principal.tenant_id,
            data=data,
            title=title or filename,
            filename=filename,
            mime_type=mime,
            source=DocumentSource.UPLOAD,
            category_id=None,
            links=links,
            created_by=principal.user_id,
            settings=settings,
        )
        _append(row, document.id)
        row.updated_by = principal.user_id
        await session.flush()
        return await _listing(session, list(row.attachment_document_ids))


@router.delete(
    "/messages/{message_id}/attachments/{document_id}",
    summary="Anhang vom Entwurf entfernen (Dokument bleibt erhalten)",
)
async def remove_attachment(
    message_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        row = await _draft(session, message_id, principal)
        if document_id not in row.attachment_document_ids:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Anhang nicht gefunden.")
        row.attachment_document_ids = [i for i in row.attachment_document_ids if i != document_id]
        row.updated_by = principal.user_id
        await session.flush()
        return await _listing(session, list(row.attachment_document_ids))
