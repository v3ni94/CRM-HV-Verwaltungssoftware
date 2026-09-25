"""Portal side of the handover protocols (M30 stage 3): /api/v1/portal/handover.

A participant with a portal account (M21) and an active grant ``handover`` on exactly one
protocol fills it in, adds photos, signs and completes it. Every write is delegated to the CRM
handlers in :mod:`mhvp.handover.routers` so that locking, validation, numbering and events stay
in one place; the portal only narrows what can be read and written: internal fields, internal
remarks, CRM references (contacts, meters, units) and other versions never leave the CRM. After
the completion the grant turns read only and expires (``READ_DAYS``), rule docs/rules/M30-01.md.
"""

import uuid
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select

from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentLink
from mhvp.handover import routers as crm
from mhvp.handover import services as svc
from mhvp.handover.models import HandoverNote, HandoverProtocol
from mhvp.portal.models import AccessGrant, PortalAccount
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/handover", tags=["Portal"])

# Days after the completion during which the participant may still open the finished PDF.
READ_DAYS = 14
# Protocol fields the participant may change; internal fields and CRM references are excluded.
PATCH_FIELDS = frozenset(crm.ProtocolPatch.model_fields) - {
    "kind",
    "property_id",
    "unit_id",
    "contract_id",
    "listing_id",
    "management_number",
    "internal_contact",
    "internal_note",
    "deposit_iban_verified",
}
# Protocol fields that are never shown in the portal.
HIDDEN_FIELDS = frozenset({"internal_note", "internal_contact", "management_number"})
# Sub record fields the participant may not set (CRM references, internal flag).
DROPPED_ITEM_FIELDS: dict[str, frozenset[str]] = {
    "participants": frozenset({"contact_id"}),
    "meters": frozenset({"meter_id"}),
    "notes": frozenset({"is_internal"}),
}
Ctx = Annotated[Portal, Depends(portal_user)]


def _grant_query(account: PortalAccount, protocol_id: uuid.UUID | None = None) -> Any:
    today = local_today()
    query = select(AccessGrant).where(
        AccessGrant.account_id == account.id,
        AccessGrant.scope_type == "handover",
        AccessGrant.valid_from <= today,
        or_(AccessGrant.valid_to.is_(None), AccessGrant.valid_to >= today),
    )
    return query.where(AccessGrant.scope_id == protocol_id) if protocol_id else query


async def _granted(
    session: Any, account: PortalAccount, protocol_id: uuid.UUID, *, write: bool = False
) -> tuple[HandoverProtocol, AccessGrant]:
    grant = await session.scalar(_grant_query(account, protocol_id))
    p = await session.get(HandoverProtocol, protocol_id) if grant is not None else None
    if grant is None or p is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if write and grant.right != "edit":
        raise ProblemError(
            ErrorCodes.FORBIDDEN,
            detail="Das Protokoll ist abgeschlossen, Änderungen sind nicht mehr möglich.",
        )
    return p, grant


def _public(full: dict[str, Any], grant: AccessGrant) -> dict[str, Any]:
    out = {k: v for k, v in full.items() if k not in HIDDEN_FIELDS and k != "versions"}
    out["notes"] = [n for n in full.get("notes", []) if not n.get("is_internal")]
    out["access"] = {"right": grant.right, "valid_to": grant.valid_to}
    return out


async def _writable(request: Request, ctx: Portal, protocol_id: uuid.UUID) -> TenantPrincipal:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _granted(session, account, protocol_id, write=True)
    return principal


def _payload(request: Request, section: str, data: Any) -> None:
    if section not in svc.SECTIONS:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannter Abschnitt {section!r}.")
    if not isinstance(data, dict):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Inhalt der Anfrage ist ungültig.")
    dropped = DROPPED_ITEM_FIELDS.get(section, frozenset())
    request.state.handover_payload = {k: v for k, v in data.items() if k not in dropped}


async def _visible_note(session: Any, section: str, item_id: uuid.UUID) -> None:
    """Internal remarks are invisible in the portal, so they cannot be changed either."""
    if section != "notes":
        return
    note = await session.get(HandoverNote, item_id)
    if note is None or note.is_internal:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


@router.get("", summary="Eigene Übergabeprotokolle")
async def list_protocols(request: Request, ctx: Ctx) -> list[dict[str, Any]]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        grants = (await session.scalars(_grant_query(account))).all()
        out = []
        for grant in grants:
            p = await session.get(HandoverProtocol, grant.scope_id)
            if p is None:
                continue
            out.append(
                {
                    "id": p.id,
                    "number": p.number,
                    "version": p.version,
                    "kind": p.kind,
                    "status": p.status,
                    "address": svc.address_line(p),
                    "handover_date": p.handover_date,
                    "locked": svc.is_locked(p),
                    "right": grant.right,
                    "valid_to": grant.valid_to,
                }
            )
        out.sort(key=lambda x: (x["locked"], x["number"]))
        return out


@router.get("/{protocol_id}", summary="Übergabeprotokoll lesen")
async def get_protocol(protocol_id: uuid.UUID, request: Request, ctx: Ctx) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        p, grant = await _granted(session, account, protocol_id)
        return _public(await crm._full_out(session, p), grant)


@router.patch("/{protocol_id}", summary="Protokollfelder ändern")
async def patch_protocol(protocol_id: uuid.UUID, request: Request, ctx: Ctx) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, grant = await _granted(session, account, protocol_id, write=True)
    data = await request.json()
    if not isinstance(data, dict):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Inhalt der Anfrage ist ungültig.")
    rejected = sorted(set(data) - PATCH_FIELDS)
    if rejected:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Diese Felder können im Portal nicht geändert werden: " + ", ".join(rejected),
        )
    request.state.handover_payload = data
    body = await crm._body(request, crm.ProtocolPatch)
    out = await crm.patch_protocol(protocol_id, body, request, principal)  # type: ignore[arg-type]
    return _public(out, grant)


@router.get("/{protocol_id}/hints", summary="Hinweise vor dem Abschluss")
async def hints(protocol_id: uuid.UUID, request: Request, ctx: Ctx) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _granted(session, account, protocol_id)
    return await crm.hints(protocol_id, request, principal)


@router.post("/{protocol_id}/complete", summary="Protokoll verbindlich abschließen")
async def complete(
    protocol_id: uuid.UUID, body: crm.CompleteIn, request: Request, ctx: Ctx
) -> dict[str, Any]:
    """Completion by the participant: PDF on the letterhead, lock, then the grant becomes read
    only for READ_DAYS so the finished PDF can still be opened; the management prepares the
    dispatch in the CRM (no automatic mail, M20-01)."""
    principal, account = ctx
    await _writable(request, ctx, protocol_id)
    await crm.complete(protocol_id, body, request, principal)
    async with tenant_tx(request, principal) as session:
        p, grant = await _granted(session, account, protocol_id)
        grant.right = "read"
        grant.valid_to = local_today() + timedelta(days=READ_DAYS)
        await session.flush()
        # Helper finish flow (ported from U-Protokoll): one delivery draft per participant with
        # an e-mail address plus the helper, and an internal notice to the creating staff user.
        # Both still need staff action (four-eyes approval, reading the event feed); nothing is
        # sent automatically (M20-01).
        await crm.prepare_helper_completion_dispatch(session, principal, p, account.contact_id)
        await crm.notify_creator_of_completion(session, principal, p)
        await crm._event(
            session, principal, "handover.portal.completed", p, valid_to=str(grant.valid_to)
        )
        return _public(await crm._full_out(session, p), grant)


@router.get(
    "/{protocol_id}/pdf",
    summary="PDF (Entwurf oder abgeschlossene Fassung)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_pdf(
    protocol_id: uuid.UUID, request: Request, ctx: Ctx, download: bool = False
) -> Response:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _granted(session, account, protocol_id)
    return await crm.get_pdf(protocol_id, request, download, principal)


# Documents (photos of sub records, attachments) ------------------------------------------------


@router.post("/{protocol_id}/documents", status_code=201, summary="Foto oder Anhang hochladen")
async def upload_document(
    protocol_id: uuid.UUID,
    request: Request,
    ctx: Ctx,
    file: UploadFile = File(),
    section: str | None = Form(default=None, pattern="^(meters|rooms|defects|items)$"),
    item_id: uuid.UUID | None = Form(default=None),
    title: str | None = Form(default=None, max_length=300),
) -> dict[str, Any]:
    principal = await _writable(request, ctx, protocol_id)
    return await crm.upload_document(protocol_id, request, file, section, item_id, title, principal)


@router.delete(
    "/{protocol_id}/documents/{document_id}", status_code=204, summary="Foto oder Anhang entfernen"
)
async def delete_document(
    protocol_id: uuid.UUID, document_id: uuid.UUID, request: Request, ctx: Ctx
) -> Response:
    principal = await _writable(request, ctx, protocol_id)
    return await crm.delete_document(protocol_id, document_id, request, principal)


@router.get(
    "/{protocol_id}/documents/{document_id}/content",
    summary="Foto, Anhang oder Unterschrift anzeigen",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def document_content(
    protocol_id: uuid.UUID, document_id: uuid.UUID, request: Request, ctx: Ctx
) -> Response:
    """Only files linked to the granted protocol; the generic document download of the portal
    (access matrix) does not cover handover files."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        p, _ = await _granted(session, account, protocol_id)
        linked = await session.scalar(
            select(DocumentLink.id).where(
                DocumentLink.document_id == document_id,
                DocumentLink.entity_type == "handover_protocol",
                DocumentLink.entity_id == p.id,
            )
        )
        document = await session.get(Document, document_id) if linked else None
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        mime, filename = document.mime_type, document.filename
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


# Signatures ------------------------------------------------------------------------------------


@router.post("/{protocol_id}/signatures", status_code=201, summary="Unterschrift speichern")
async def add_signature(
    protocol_id: uuid.UUID, body: crm.SignatureIn, request: Request, ctx: Ctx
) -> dict[str, Any]:
    principal = await _writable(request, ctx, protocol_id)
    return await crm.add_signature(protocol_id, body, request, principal)


@router.delete(
    "/{protocol_id}/signatures/{signature_id}", status_code=204, summary="Unterschrift löschen"
)
async def delete_signature(
    protocol_id: uuid.UUID, signature_id: uuid.UUID, request: Request, ctx: Ctx
) -> Response:
    principal = await _writable(request, ctx, protocol_id)
    return await crm.delete_signature(protocol_id, signature_id, request, principal)


# Sub records (generic, placed last) -----------------------------------------------------------


@router.post("/{protocol_id}/{section}/order", summary="Reihenfolge speichern")
async def order_items(
    protocol_id: uuid.UUID, section: str, body: crm.OrderIn, request: Request, ctx: Ctx
) -> dict[str, Any]:
    principal = await _writable(request, ctx, protocol_id)
    return await crm.order_items(protocol_id, section, body, request, principal)


@router.post("/{protocol_id}/{section}", status_code=201, summary="Teildatensatz anlegen")
async def create_item(
    protocol_id: uuid.UUID, section: str, request: Request, ctx: Ctx
) -> dict[str, Any]:
    principal = await _writable(request, ctx, protocol_id)
    _payload(request, section, await request.json())
    return await crm.create_item(protocol_id, section, request, principal)


@router.patch("/{protocol_id}/{section}/{item_id}", summary="Teildatensatz ändern")
async def patch_item(
    protocol_id: uuid.UUID, section: str, item_id: uuid.UUID, request: Request, ctx: Ctx
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _granted(session, account, protocol_id, write=True)
        await _visible_note(session, section, item_id)
    _payload(request, section, await request.json())
    return await crm.patch_item(protocol_id, section, item_id, request, principal)


@router.delete(
    "/{protocol_id}/{section}/{item_id}", status_code=204, summary="Teildatensatz löschen"
)
async def delete_item(
    protocol_id: uuid.UUID, section: str, item_id: uuid.UUID, request: Request, ctx: Ctx
) -> Response:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await _granted(session, account, protocol_id, write=True)
        await _visible_note(session, section, item_id)
    return await crm.delete_item(protocol_id, section, item_id, request, principal)
