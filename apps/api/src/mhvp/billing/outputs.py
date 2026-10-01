"""Filed outputs of a statement run (GA06-02, GA06-03): generated PDF documents linked to the
run through ``generated_document`` (context type and id), listed for the CRM preview.

Filing is an output of the statement and therefore needs gate G3 of the tenant; the documents
stay internal (no portal visibility) and carry the draft marking. Nothing is sent.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal
from mhvp.documents import services as docs
from mhvp.documents.models import Document, DocumentSource, GeneratedDocument, LinkRole


async def file_output(
    session: AsyncSession,
    blobs: Any,
    principal: TenantPrincipal,
    *,
    pdf: bytes,
    title: str,
    filename: str,
    links: list[tuple[str, uuid.UUID]],
    context_type: str,
    context_id: uuid.UUID,
    origin: str,
) -> Document:
    document = await docs.store_document(
        session,
        blobs,
        tenant_id=principal.tenant_id,
        data=pdf,
        title=title,
        filename=filename,
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=[(t, i, LinkRole.GENERATED) for t, i in links],
        created_by=principal.user_id,
    )
    session.add(
        GeneratedDocument(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            document_id=document.id,
            template_code=origin,
            context_type=context_type,
            context_id=context_id,
        )
    )
    await session.flush()
    return document


async def list_outputs(
    session: AsyncSession, context_type: str, context_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(GeneratedDocument, Document)
        .join(Document, Document.id == GeneratedDocument.document_id)
        .where(
            GeneratedDocument.context_type == context_type,
            GeneratedDocument.context_id == context_id,
        )
        .order_by(GeneratedDocument.created_at)
    )
    return [
        {
            "document_id": d.id,
            "origin": g.template_code,
            "title": d.title,
            "filename": d.filename,
            "created_at": g.created_at,
            "created_by": g.created_by,
        }
        for g, d in rows.all()
    ]
