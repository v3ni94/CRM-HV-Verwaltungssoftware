"""Service provider portal: upload an e-invoice as XML and read it (M22-01, 14 Dienstleister).

``POST /portal/work-orders/{order_id}/einvoice`` takes a plain XRechnung file (UBL or CII, no
PDF) for an own order that is documented as done. The structured part is read deterministically
with ``mhvp.receipts.einvoice`` (no provider call, values as in the XML, IBAN only masked). The
response is a proposal for ``POST /portal/work-orders/{id}/invoice`` (number, date, gross) plus
the file as a document of the provider; nothing is submitted and nothing is posted here. A file
that cannot be read is refused with 422 and stored nowhere. Formal readability is no statement
on the substance of the invoice (D41); the management reviews it as any other submission.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.escaping import sanitize_filename
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal.routers import Portal, _own_order, portal_user
from mhvp.receipts import einvoice

router = APIRouter(prefix="/portal", tags=["Portal"])
NOTE = (
    "Die Werte stammen aus dem strukturierten Teil der Datei und sind ein Vorschlag. "
    "Bitte prüfen und mit Rechnung einreichen bestätigen; die Verwaltung prüft die Rechnung."
)


@router.post(
    "/work-orders/{order_id}/einvoice",
    status_code=201,
    summary="E-Rechnung (XML) hochladen und auswerten (Vorschlag)",
)
async def upload_einvoice(
    order_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(),
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.documents.services import check_upload, store_document

    principal, account = ctx
    limit = request.app.state.settings.document_max_bytes
    data = await file.read(limit + 1)  # bounded read (SECURITY-2026-10-01, Befund 2)
    mime = (file.content_type or "application/xml").split(";")[0].strip()
    if mime not in einvoice.XML_MIME_TYPES:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED, detail="Erwartet wird eine XML-Datei (XRechnung)."
        )
    check_upload(mime, data, limit)
    result = einvoice.read(mime, data)
    if result.einvoice is None:
        detail = "; ".join(result.findings) or "Die Datei enthält keine lesbare E-Rechnung."
        raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail=detail)
    inv = result.einvoice
    async with tenant_tx(request, principal) as session:
        order = await _own_order(session, account, order_id)
        if order.status.value != "done":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Rechnung erst nach dokumentierter Ausführung."
            )
        name, _ = sanitize_filename(file.filename or "e-rechnung.xml")
        doc = await store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=data,
            title=name[:300],
            filename=name,
            mime_type=mime,
            source=DocumentSource.PORTAL,
            category_id=None,
            links=[("contact", account.contact_id, LinkRole.ORIGINAL)],
            created_by=principal.user_id,
            visibility=["provider"],
        )
        fields = einvoice.draft_fields(inv)
        return {
            "document_id": doc.id,
            "number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "gross": str(inv.gross) if inv.gross is not None else None,
            "currency": inv.currency,
            "fields": {
                key: fields[key]["value"]
                for key in ("supplier_name", "recipient_name", "net", "vat", "due_date")
            },
            "findings": [*result.findings, *einvoice.formal_findings(inv)],
            "note": NOTE,
        }
