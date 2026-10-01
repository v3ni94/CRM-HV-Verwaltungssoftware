"""M35 Stufe 3 part 4 (docs/plans/M35-objektakte-uebernahme.md section 4): completeness check
and its settings. `/api/v1/objektakte/required-documents` (settings, list/create/delete) and
`/api/v1/objektakte/properties/{id}/completeness` (+ a "Nachforderungsschreiben" draft text).

Permissions (M35 Stufe 4, docs/rules/M35-03.md): `objektakte:read` for the checks and listing
required documents, `objektakte:approve` for changing the required-document settings
(configuration, same level as the classification rules), `objektakte:delete` for removing one.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_path_guard
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letter_records
from mhvp.documents import services as doc_services
from mhvp.documents.letter_records import LetterRecordIn
from mhvp.documents.models import DocumentCategory
from mhvp.objektakte.completeness import (
    check_completeness,
    nachforderungsschreiben_letter,
    nachforderungsschreiben_text,
)
from mhvp.objektakte.models import ObjektakteRequiredDocument
from mhvp.properties.models import ManagementType, Property
from mhvp.workspace.services import local_today

router = APIRouter(
    prefix="/objektakte",
    tags=["objektakte-completeness"],
    dependencies=[Depends(property_path_guard)],
)  # M2-02, R08-01
READ = require_permission("objektakte:read")
MANAGE = require_permission("objektakte:approve")
DELETE = require_permission("objektakte:delete")


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
    body: RequiredDocumentIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
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
    required_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
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


class NachforderungPdfIn(LetterRecordIn):
    """Recipient (the previous manager or whoever holds the documents) and the record."""

    contact_id: uuid.UUID


@router.post(
    "/properties/{property_id}/completeness/nachforderungsschreiben/pdf",
    status_code=201,
    summary="Nachforderungsschreiben auf dem Briefbogen ablegen (PDF, Versandnachweis, Ticket)",
)
async def nachforderungsschreiben_pdf(
    property_id: uuid.UUID,
    body: NachforderungPdfIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("documents:create")),
) -> dict[str, Any]:
    """Letter on the tenant letterhead (``mhvp.documents.letters``) with the missing
    document classes, filed as a generated document of the property, the recipient and the
    optional ticket; with a dispatch record (channel, date, user, reference). Nothing is sent
    by the platform: a mail draft leaves only through the mail approval, a posting is
    recorded as done outside. Needs ``objektakte:read`` as well (the check itself)."""
    from mhvp.documents.blobs import BlobStore

    if not principal.has("objektakte:read"):
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Missing objektakte:read.")
    blobs = BlobStore(request.app.state.settings)
    async with tenant_tx(request, principal) as session:
        property_row = await _property(session, property_id)
        result = await check_completeness(session, principal.tenant_id, property_row)
        if not result.missing:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Alle Pflichtunterlagen sind vorhanden.")
        head = await doc_services.letterhead(session, blobs)
        contact, recipient_lines, data = await doc_services.recipient(session, body.contact_id)
        letter_date = body.letter_date or local_today()
        letter = nachforderungsschreiben_letter(
            property_row,
            result.missing,
            recipient_lines=recipient_lines,
            greeting=str(data["anrede"]),
            letter_date=letter_date,
            company_name=str(head.company.get("name", "")),
        )
        document = await letter_records.store_letter(
            session,
            blobs,
            principal=principal,
            head=head,
            letter=letter,
            title=(
                f"Nachforderungsschreiben Objektakte {property_row.number}, {contact.display_name}"
            ),
            filename=f"{letter_date.isoformat()}_nachforderung_{property_row.number}.pdf",
            links=[("property", property_row.id), ("contact", contact.id)],
        )
        if body.ticket_id is not None:
            await letter_records.link_ticket(
                session,
                principal=principal,
                document=document,
                ticket_id=body.ticket_id,
                note=f"Nachforderungsschreiben auf Briefbogen abgelegt: {document.title}",
            )
        dispatch = None
        if body.dispatch is not None:
            dispatch = await letter_records.record_dispatch(
                session,
                principal=principal,
                document=document,
                contact_id=contact.id,
                record=body.dispatch,
                entity_type="property",
                entity_id=property_row.id,
            )
        return {
            "document_id": document.id,
            "title": document.title,
            "filename": document.filename,
            "contact_id": contact.id,
            "ticket_id": body.ticket_id,
            "missing": [vars(m) for m in result.missing],
            "dispatch": letter_records.dispatch_out(dispatch),
            "hinweis": (
                "Das Schreiben ist abgelegt; der Versand erfolgt nicht durch die Plattform "
                "(Post außerhalb, E-Mail nur über die Mailfreigabe)."
            ),
        }
