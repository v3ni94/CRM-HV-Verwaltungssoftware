"""Anhänge ausgehender Mails aus dem Dokumentenmodul (operator 26.09.2026, Antwortvorlagen mit
Standardanhängen): jedes ``attachment_document_ids``-Dokument der ausgehenden Nachricht wird
beim Versand als MIME-Anhang beigefügt. Fehlende Dokumente brechen den Versand ab, damit nie
eine unvollständige Antwort hinausgeht."""

from __future__ import annotations

import uuid
from email.message import EmailMessage

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError


async def attach_documents(
    session: AsyncSession, request: Request, msg: EmailMessage, document_ids: list[uuid.UUID]
) -> int:
    """Fügt die Dokumente als Anhänge an ``msg`` an; gibt die Anzahl zurück."""
    if not document_ids:
        return 0
    from mhvp.documents import services as document_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import Document, StorageKind

    count = 0
    for document_id in document_ids:
        document = await session.get(Document, document_id)
        if document is None:
            raise ProblemError(ErrorCodes.CONFLICT, detail=f"Anhang nicht gefunden: {document_id}")
        if document.storage is StorageKind.GOOGLE_DRIVE:
            data = await document_services.download_from_drive(session, request, document)
        else:
            data = BlobStore(request.app.state.settings).get(document.storage_ref)
        maintype, _, subtype = (document.mime_type or "application/octet-stream").partition("/")
        msg.add_attachment(
            data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=document.filename,
        )
        count += 1
    return count
