"""Handover protocol API (M30): /api/v1/handover.

Rights follow the broker area (M28): read with contracts:read, write with contracts:create
and contracts:update, delete with contracts:delete. Every write checks the lock: a completed,
sent, archived or cancelled protocol is immutable; changes go into a new version.
"""

import base64
import hashlib
import re
import secrets
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, or_, select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, FieldError, ProblemError
from mhvp.documents import services as documents
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentLink, DocumentSource, LinkRole
from mhvp.handover import pdf as pdf_renderer
from mhvp.handover import services as svc
from mhvp.handover.models import STATUSES, STEPS, HandoverProtocol, HandoverSignature
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/handover", tags=["handover"])
READ = require_permission("contracts:read")
CREATE = require_permission("contracts:create")
UPDATE = require_permission("contracts:update")
DELETE = require_permission("contracts:delete")
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]
_PNG = re.compile(r"^data:image/png;base64,([A-Za-z0-9+/=]+)$")
ROLES = (
    "moving_out",
    "moving_in",
    "seller",
    "buyer",
    "handing_over",
    "taking_over",
    "management",
    "broker",
    "caretaker",
    "proxy",
    "witness",
    "relative",
    "expert",
    "craftsman",
    "other",
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProtocolCreateIn(_In):
    kind: str = Field(default="rental", pattern="^(rental|sale|general)$")
    unit_id: uuid.UUID | None = None
    listing_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None


class ProtocolPatch(_In):
    kind: str | None = Field(default=None, pattern="^(rental|sale|general)$")
    current_step: str | None = Field(default=None, pattern="^(" + "|".join(STEPS) + ")$")
    property_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    contract_id: uuid.UUID | None = None
    listing_id: uuid.UUID | None = None
    street: str | None = Field(default=None, max_length=200)
    house_number: str | None = Field(default=None, max_length=20)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    object_label: str | None = Field(default=None, max_length=200)
    building: str | None = Field(default=None, max_length=100)
    floor: str | None = Field(default=None, max_length=20)
    unit_number: str | None = Field(default=None, max_length=50)
    unit_label: str | None = Field(default=None, max_length=100)
    unit_position: str | None = Field(default=None, max_length=100)
    external_object_number: str | None = Field(default=None, max_length=100)
    owner_name: str | None = Field(default=None, max_length=200)
    handover_date: date | None = None
    handover_start: time | None = None
    handover_end: time | None = None
    hide_time_information: bool | None = None
    handover_location: str | None = Field(default=None, max_length=200)
    ticket_number: str | None = Field(default=None, max_length=50)
    reference_number: str | None = Field(default=None, max_length=100)
    management_number: str | None = Field(default=None, max_length=100)
    rental_contract_number: str | None = Field(default=None, max_length=100)
    internal_contact: str | None = Field(default=None, max_length=200)
    internal_note: str | None = Field(default=None, max_length=20000)
    general_note: str | None = Field(default=None, max_length=20000)
    deposit_amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    deposit_account_holder: str | None = Field(default=None, max_length=200)
    deposit_iban: str | None = Field(default=None, max_length=34)
    deposit_bic: str | None = Field(default=None, max_length=11)
    deposit_bank_name: str | None = Field(default=None, max_length=200)
    deposit_note: str | None = Field(default=None, max_length=4000)
    deposit_iban_verified: bool | None = None
    deposit_separate_statement: bool | None = None


class ParticipantIn(_In):
    contact_id: uuid.UUID | None = None
    role: str = Field(default="other", pattern="^(" + "|".join(ROLES) + ")$")
    salutation: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    company: str | None = Field(default=None, max_length=200)
    street: str | None = Field(default=None, max_length=200)
    house_number: str | None = Field(default=None, max_length=20)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    comment: str | None = Field(default=None, max_length=4000)
    sort_order: int = 0


class MeterIn(_In):
    meter_id: uuid.UUID | None = None
    meter_type: str | None = Field(default=None, max_length=63)
    custom_type: str | None = Field(default=None, max_length=100)
    number: str | None = Field(default=None, max_length=100)
    value: Decimal | None = Field(default=None, ge=0, decimal_places=3)
    unit: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=200)
    read_on: date | None = None
    read_at: time | None = None
    comment: str | None = Field(default=None, max_length=4000)
    sort_order: int = 0


class RoomIn(_In):
    room_type: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    condition: str | None = Field(
        default=None, pattern="^(ok|defective|not_checked|not_accessible|not_included)$"
    )
    comment: str | None = Field(default=None, max_length=4000)
    sort_order: int = 0


class DefectIn(_In):
    room_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    location: str | None = Field(default=None, max_length=200)
    priority: str | None = Field(default=None, pattern="^(info|low|medium|high|urgent)$")
    responsibility: str | None = Field(default=None, max_length=100)
    defect_status: str | None = Field(
        default=None, pattern="^(pre_existing|new|acknowledged|rejected|unclear)$"
    )
    comment: str | None = Field(default=None, max_length=4000)
    sort_order: int = 0


class KeyIn(_In):
    key_type: str | None = Field(default=None, max_length=100)
    custom_name: str | None = Field(default=None, max_length=200)
    quantity: int | None = Field(default=None, ge=0, le=9999)
    key_number: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern="^(handed_over|not_handed_over|to_follow)$")
    comment: str | None = Field(default=None, max_length=4000)
    sort_order: int = 0


class ItemIn(_In):
    item_type: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=200)
    quantity: int | None = Field(default=None, ge=0, le=9999)
    condition: str | None = Field(default=None, max_length=100)
    comment: str | None = Field(default=None, max_length=4000)
    sort_order: int = 0


class NoteIn(_In):
    category: str | None = Field(
        default=None, pattern="^(agreement|hint|defect|open_task|follow_up|payment|other)$"
    )
    text: str | None = Field(default=None, max_length=8000)
    responsible_party: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    status: str | None = Field(default=None, max_length=50)
    is_internal: bool = False
    sort_order: int = 0


SECTION_SCHEMAS: dict[str, type[_In]] = {
    "participants": ParticipantIn,
    "meters": MeterIn,
    "rooms": RoomIn,
    "defects": DefectIn,
    "keys": KeyIn,
    "items": ItemIn,
    "notes": NoteIn,
}


class OrderIn(_In):
    ids: list[uuid.UUID] = Field(max_length=500)


class SignatureIn(_In):
    image: str = Field(min_length=100, max_length=3_000_000, description="PNG als Data-URI")
    signer_name: str | None = Field(default=None, max_length=200)
    signer_role: str | None = Field(default=None, pattern="^(" + "|".join(ROLES) + ")$")
    participant_id: uuid.UUID | None = None
    signed_location: str | None = Field(default=None, max_length=200)
    comment: str | None = Field(default=None, max_length=255)


class CompleteIn(_In):
    force: bool = False


class VersionIn(_In):
    reason: str = Field(min_length=3, max_length=2000)


class StatusIn(_In):
    action: str = Field(pattern="^(cancel|archive|unarchive)$")


class HandoverDispatchIn(_In):
    participant_ids: list[uuid.UUID] | None = None
    channel: str = Field(default="email", pattern="^(email|portal|post)$")


def _blobs(request: Request) -> BlobStore:
    return BlobStore(request.app.state.settings)


def _row(obj: Any) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


async def _fresh(session: Any, obj: Any) -> Any:
    """Flush and reload: server side timestamps are expired after a flush (async session)."""
    await session.flush()
    await session.refresh(obj)
    return obj


def _protocol_out(p: HandoverProtocol) -> dict[str, Any]:
    out = _row(p)
    out["locked"] = svc.is_locked(p)
    out["finalized"] = svc.is_finalized(p)
    out["address"] = svc.address_line(p)
    return out


async def _get(session: Any, protocol_id: uuid.UUID) -> HandoverProtocol:
    row: HandoverProtocol | None = await session.get(HandoverProtocol, protocol_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _full_out(session: Any, p: HandoverProtocol) -> dict[str, Any]:
    await _fresh(session, p)
    full = await svc.load_full(session, p)
    out = _protocol_out(p)
    for name in svc.SECTIONS:
        out[name] = [_row(x) for x in full[name]]
    for item in out["participants"]:
        item["role_label"] = svc.role_label(item["role"], p.kind)
        item["portal_access"] = await portal_access_of(session, p, item["contact_id"])
    out["signatures"] = [_row(x) for x in full["signatures"]]
    out["documents"] = full["documents"]
    out["hints"] = svc.completion_hints(full)
    out["versions"] = [
        {
            "id": v.id,
            "version": v.version,
            "status": v.status,
            "completed_at": v.completed_at,
            "change_reason": v.change_reason,
            "pdf_document_id": v.pdf_document_id,
        }
        for v in (
            await session.scalars(
                select(HandoverProtocol)
                .where(HandoverProtocol.number == p.number)
                .order_by(HandoverProtocol.version)
            )
        ).all()
    ]
    return out


async def _event(
    session: Any, principal: TenantPrincipal, type_: str, p: HandoverProtocol, **payload: Any
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type="handover_protocol",
        entity_id=p.id,
        actor_user_id=principal.user_id,
        payload={"number": p.number, "version": p.version, **payload},
    )


# Protocols -------------------------------------------------------------------------------


@router.get("/protocols", summary="Übergabeprotokolle")
async def list_protocols(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, pattern="^(" + "|".join(STATUSES) + ")$"),
    kind: str | None = Query(default=None, pattern="^(rental|sale|general)$"),
    property_id: uuid.UUID | None = None,
    unit_id: uuid.UUID | None = None,
    include_archived: bool = False,
    page: Page = 1,
    page_size: PageSize = 50,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        query = select(HandoverProtocol)
        if q:
            like = f"%{q.strip()}%"
            query = query.where(
                or_(
                    HandoverProtocol.number.ilike(like),
                    HandoverProtocol.ticket_number.ilike(like),
                    HandoverProtocol.reference_number.ilike(like),
                    HandoverProtocol.street.ilike(like),
                    HandoverProtocol.postal_code.ilike(like),
                    HandoverProtocol.city.ilike(like),
                    HandoverProtocol.object_label.ilike(like),
                    HandoverProtocol.unit_number.ilike(like),
                )
            )
        if status:
            query = query.where(HandoverProtocol.status == status)
        elif not include_archived:
            query = query.where(HandoverProtocol.status != "archived")
        if kind:
            query = query.where(HandoverProtocol.kind == kind)
        if property_id:
            query = query.where(HandoverProtocol.property_id == property_id)
        if unit_id:
            query = query.where(HandoverProtocol.unit_id == unit_id)
        total = await session.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await session.scalars(
                query.order_by(HandoverProtocol.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = []
        for p in rows:
            out = _protocol_out(p)
            out["participants_summary"] = await _participants_summary(session, p)
            items.append(out)
        return {"items": items, "total": int(total or 0), "page": page, "page_size": page_size}


async def _participants_summary(session: Any, p: HandoverProtocol) -> str:
    from mhvp.handover.models import HandoverParticipant

    rows = (
        await session.scalars(
            select(HandoverParticipant)
            .where(HandoverParticipant.protocol_id == p.id)
            .order_by(HandoverParticipant.sort_order)
        )
    ).all()
    names = [
        x.last_name or x.company or x.first_name
        for x in rows
        if (x.last_name or x.company or x.first_name)
    ]
    return ", ".join(names[:4]) + (" u. a." if len(names) > 4 else "")


@router.get("/protocols/prefill", summary="Vorbelegung aus Einheit und Objekt")
async def prefill(
    unit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await svc.prefill(session, unit_id)


@router.post("/protocols", status_code=201, summary="Übergabeprotokoll anlegen")
async def create_protocol(
    body: ProtocolCreateIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        values: dict[str, Any] = {}
        if body.unit_id:
            values = await svc.prefill(session, body.unit_id)
        if body.listing_id:
            from mhvp.letting.models import Listing

            listing = await session.get(Listing, body.listing_id)
            if listing is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Anzeige nicht gefunden.")
            if not values:
                values = await svc.prefill(session, listing.unit_id)
            values["listing_id"] = listing.id
        if body.contract_id:
            from mhvp.contracts.models import Contract

            if await session.get(Contract, body.contract_id) is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vertrag nicht gefunden.")
            values["contract_id"] = body.contract_id
        p = HandoverProtocol(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
            number=await svc.protocol_number(session, principal.tenant_id, local_today()),
            kind=body.kind,
            handover_date=local_today(),
            **values,
        )
        session.add(p)
        await session.flush()
        await _event(session, principal, "handover.created", p, kind=body.kind)
        return await _full_out(session, p)


@router.get("/protocols/{protocol_id}", summary="Übergabeprotokoll lesen")
async def get_protocol(
    protocol_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await _full_out(session, await _get(session, protocol_id))


@router.patch("/protocols/{protocol_id}", summary="Protokollfelder ändern (Autosave)")
async def patch_protocol(
    protocol_id: uuid.UUID,
    body: ProtocolPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        changes = body.model_dump(exclude_unset=True)
        if "unit_id" in changes and changes["unit_id"] and changes["unit_id"] != p.unit_id:
            changes = {**(await svc.prefill(session, changes["unit_id"])), **changes}
        for key, value in changes.items():
            if isinstance(value, str):
                value = value.strip() or None
            setattr(p, key, value)
        p.updated_by = principal.user_id
        if p.status == "draft" and any(k not in ("current_step",) for k in changes):
            p.status = "in_progress"
        await _fresh(session, p)
        await _event(session, principal, "handover.updated", p, fields=sorted(changes))
        return _protocol_out(p)


# Documents (photos, attachments) -----------------------------------------------------------


@router.post(
    "/protocols/{protocol_id}/documents", status_code=201, summary="Foto oder Anhang hochladen"
)
async def upload_document(
    protocol_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(),
    section: str | None = Form(default=None, pattern="^(meters|rooms|defects|items)$"),
    item_id: uuid.UUID | None = Form(default=None),
    title: str | None = Form(default=None, max_length=300),
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    limit = request.app.state.settings.document_max_bytes
    data = await file.read(limit + 1)
    mime = (file.content_type or "application/octet-stream").split(";")[0].strip()
    documents.check_upload(mime, data, limit)
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        links: list[tuple[str, uuid.UUID, LinkRole]] = [
            ("handover_protocol", p.id, LinkRole.ATTACHMENT)
        ]
        if section and item_id:
            model = svc.SECTIONS[section][0]
            row = await session.get(model, item_id)
            if row is None or row.protocol_id != p.id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Teildatensatz gehört nicht zum Protokoll."
                )
            links.append((f"handover_{section[:-1]}", item_id, LinkRole.EVIDENCE))
        if p.unit_id:
            links.append(("unit", p.unit_id, LinkRole.ATTACHMENT))
        document = await documents.store_document(
            session,
            _blobs(request),
            tenant_id=principal.tenant_id,
            data=data,
            title=title or file.filename or "Datei",
            filename=file.filename or "datei",
            mime_type=mime,
            source=DocumentSource.UPLOAD,
            category_id=None,
            links=links,
            created_by=principal.user_id,
        )
        await _event(session, principal, "handover.document.added", p, document_id=str(document.id))
        docs = await svc.documents_of(session, p.id)
        return next(d for d in docs if d["id"] == document.id)


@router.delete(
    "/protocols/{protocol_id}/documents/{document_id}",
    status_code=204,
    summary="Foto oder Anhang entfernen",
)
async def delete_document(
    protocol_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        document = await session.get(Document, document_id)
        link = await session.scalar(
            select(DocumentLink).where(
                DocumentLink.document_id == document_id,
                DocumentLink.entity_type == "handover_protocol",
                DocumentLink.entity_id == p.id,
            )
        )
        if document is None or link is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if link.role is LinkRole.GENERATED or await session.scalar(
            select(HandoverSignature.id).where(HandoverSignature.document_id == document_id)
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Unterschriften und PDF-Versionen werden nicht gelöscht.",
            )
        # Remove the links of this protocol version; the file stays while another version uses it.
        for row in (
            await session.scalars(
                select(DocumentLink).where(DocumentLink.document_id == document_id)
            )
        ).all():
            if row.entity_type == "handover_protocol" and row.entity_id == p.id:
                await session.delete(row)
            elif row.entity_type.startswith("handover_") and row.entity_type != "handover_protocol":
                model = svc.SECTIONS[row.entity_type.removeprefix("handover_") + "s"][0]
                sub = await session.get(model, row.entity_id)
                if sub is not None and sub.protocol_id == p.id:
                    await session.delete(row)
        await session.flush()
        remaining = await session.scalar(
            select(func.count())
            .select_from(DocumentLink)
            .where(
                DocumentLink.document_id == document_id,
                DocumentLink.entity_type == "handover_protocol",
            )
        )
        if not remaining:
            for row in (
                await session.scalars(
                    select(DocumentLink).where(DocumentLink.document_id == document_id)
                )
            ).all():
                await session.delete(row)
            await session.flush()
            _blobs(request).delete(document.storage_ref)
            await session.delete(document)
        await _event(
            session, principal, "handover.document.removed", p, document_id=str(document_id)
        )
    return Response(status_code=204)


# Signatures --------------------------------------------------------------------------------


@router.post(
    "/protocols/{protocol_id}/signatures", status_code=201, summary="Unterschrift speichern"
)
async def add_signature(
    protocol_id: uuid.UUID,
    body: SignatureIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    match = _PNG.match(body.image)
    if not match:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine gültige Unterschrift übermittelt.")
    try:
        png = base64.b64decode(match.group(1), validate=True)
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unterschriftsdaten ungültig.") from exc
    if not png.startswith(b"\x89PNG") or len(png) < 100 or len(png) > 2 * 1024 * 1024:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unterschriftsdaten ungültig.")
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        if body.participant_id:
            existing = await session.scalar(
                select(HandoverSignature.id).where(
                    HandoverSignature.protocol_id == p.id,
                    HandoverSignature.participant_id == body.participant_id,
                )
            )
            if existing:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Für diese Person liegt bereits eine Unterschrift vor. "
                    "Bitte zuerst die vorhandene löschen.",
                )
        signed_at = datetime.now(UTC)
        document = await documents.store_document(
            session,
            _blobs(request),
            tenant_id=principal.tenant_id,
            data=png,
            title=f"Unterschrift {body.signer_name or ''} {p.number}".strip(),
            filename=f"unterschrift_{signed_at:%Y%m%d%H%M%S}.png",
            mime_type="image/png",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[("handover_protocol", p.id, LinkRole.EVIDENCE)],
            created_by=principal.user_id,
        )
        sig = HandoverSignature(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            protocol_id=p.id,
            participant_id=body.participant_id,
            signer_name=body.signer_name,
            signer_role=body.signer_role,
            document_id=document.id,
            sha256=hashlib.sha256(png).hexdigest(),
            signed_at=signed_at,
            signed_location=body.signed_location,
            comment=body.comment,
        )
        session.add(sig)
        if p.status in ("draft", "in_progress"):
            p.status = "signature_pending"
        await _fresh(session, sig)
        await _event(session, principal, "handover.signed", p, signature_id=str(sig.id))
        return _row(sig)


@router.delete(
    "/protocols/{protocol_id}/signatures/{signature_id}",
    status_code=204,
    summary="Unterschrift löschen",
)
async def delete_signature(
    protocol_id: uuid.UUID,
    signature_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        sig = await session.get(HandoverSignature, signature_id)
        if sig is None or sig.protocol_id != p.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        document_id = sig.document_id
        await session.delete(sig)
        await session.flush()
        # The signature file is evidence only for this protocol version; other versions keep it
        # through their own signature rows.
        if not await session.scalar(
            select(HandoverSignature.id).where(HandoverSignature.document_id == document_id)
        ):
            for row in (
                await session.scalars(
                    select(DocumentLink).where(DocumentLink.document_id == document_id)
                )
            ).all():
                await session.delete(row)
            document = await session.get(Document, document_id)
            if document is not None:
                await session.flush()
                _blobs(request).delete(document.storage_ref)
                await session.delete(document)
        await _event(
            session, principal, "handover.signature.deleted", p, signature_id=str(signature_id)
        )
    return Response(status_code=204)


# Completion, versions, status --------------------------------------------------------------


@router.get("/protocols/{protocol_id}/hints", summary="Hinweise vor dem Abschluss")
async def hints(
    protocol_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        return {"hints": svc.completion_hints(await svc.load_full(session, p))}


async def _render(session: Any, request: Request, p: HandoverProtocol, *, draft: bool) -> bytes:
    full = await svc.load_full(session, p)
    head = await documents.letterhead(session, _blobs(request))
    blobs = _blobs(request)
    photos: dict[str, list[bytes]] = {}
    for d in full["documents"]:
        if d["kind"] == "photo" and d["item_id"] and d["mime_type"] in ("image/jpeg", "image/png"):
            document = await session.get(Document, d["id"])
            if document is not None:
                photos.setdefault(str(d["item_id"]), []).append(blobs.get(document.storage_ref))
    signatures: dict[str, bytes] = {}
    for sig in full["signatures"]:
        document = await session.get(Document, sig.document_id)
        if document is not None:
            signatures[str(sig.id)] = blobs.get(document.storage_ref)
    return pdf_renderer.render(
        full,
        head,
        photos=photos,
        signatures=signatures,
        draft=draft,
        change_reason=p.change_reason if p.version > 1 else None,
    )


@router.post("/protocols/{protocol_id}/complete", summary="Verbindlich abschließen")
async def complete(
    protocol_id: uuid.UUID,
    body: CompleteIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        full = await svc.load_full(session, p)
        hints_ = svc.completion_hints(full)
        if hints_ and not body.force:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Es liegen Hinweise vor. Zum Abschluss trotz Hinweisen force=true senden: "
                + " ".join(hints_),
            )
        p.status = "completed"
        p.completed_at = datetime.now(UTC)
        p.completed_by = principal.user_id
        p.updated_by = principal.user_id
        await session.flush()
        pdf = await _render(session, request, p, draft=False)
        document = await svc.store_pdf(session, _blobs(request), p, pdf, user_id=principal.user_id)
        await _event(
            session, principal, "handover.completed", p, document_id=str(document.id), hints=hints_
        )
        return await _full_out(session, p)


@router.get(
    "/protocols/{protocol_id}/pdf",
    summary="PDF (gespeicherte Version oder Vorschau als Entwurf)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def get_pdf(
    protocol_id: uuid.UUID,
    request: Request,
    download: bool = False,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        stored = await session.get(Document, p.pdf_document_id) if p.pdf_document_id else None
        if stored is not None and svc.is_finalized(p):
            content, filename = _blobs(request).get(stored.storage_ref), stored.filename
        else:
            content, filename = (
                await _render(session, request, p, draft=not svc.is_finalized(p)),
                svc.pdf_filename(p),
            )
        disposition = "attachment" if download else "inline"
        return Response(
            content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
        )


@router.post("/protocols/{protocol_id}/versions", status_code=201, summary="Neue Version anlegen")
async def new_version(
    protocol_id: uuid.UUID,
    body: VersionIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        source = await _get(session, protocol_id)
        new = await svc.create_version(
            session, source, reason=body.reason, user_id=principal.user_id
        )
        await _event(
            session,
            principal,
            "handover.version_created",
            new,
            source_id=str(source.id),
            reason=body.reason,
        )
        return await _full_out(session, new)


@router.post("/protocols/{protocol_id}/status", summary="Stornieren, archivieren, zurückholen")
async def change_status(
    protocol_id: uuid.UUID,
    body: StatusIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        before = p.status
        if body.action == "cancel":
            if p.status == "cancelled":
                raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits storniert.")
            if svc.is_finalized(p) and not principal.has("contracts:delete"):
                raise ProblemError(
                    ErrorCodes.FORBIDDEN,
                    detail="Abgeschlossene Protokolle storniert nur, wer Verträge löschen darf.",
                )
            p.status = "cancelled"
        elif body.action == "archive":
            if p.status == "archived":
                raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits archiviert.")
            p.status, p.archived_at = "archived", datetime.now(UTC)
        else:
            if p.status != "archived":
                raise ProblemError(ErrorCodes.CONFLICT, detail="Nicht archiviert.")
            p.status = (
                "sent"
                if (p.completed_at and await _was_sent(session, p))
                else ("completed" if p.completed_at else "in_progress")
            )
            p.archived_at = None
        p.updated_by = principal.user_id
        await _fresh(session, p)
        await _event(
            session, principal, f"handover.{body.action}", p, before=before, after=p.status
        )
        return _protocol_out(p)


async def _was_sent(session: Any, p: HandoverProtocol) -> bool:
    from mhvp.communication.models import Dispatch

    if not p.pdf_document_id:
        return False
    return (
        await session.scalar(select(Dispatch.id).where(Dispatch.document_id == p.pdf_document_id))
    ) is not None


@router.post(
    "/protocols/{protocol_id}/dispatches",
    status_code=201,
    summary="Zustellung an Beteiligte vorbereiten",
)
async def prepare_dispatches(
    protocol_id: uuid.UUID,
    body: HandoverDispatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """One dispatch (M23) per participant with a CRM contact. E-mail creates a draft in the
    outbox that needs the four-eyes approval (M20-01); nothing leaves the system here."""
    from mhvp.communication import dispatch as dispatch_module
    from mhvp.handover.models import HandoverParticipant

    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        if not svc.is_finalized(p) or not p.pdf_document_id:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Zustellung erst nach dem Abschluss möglich."
            )
        rows = (
            await session.scalars(
                select(HandoverParticipant).where(HandoverParticipant.protocol_id == p.id)
            )
        ).all()
        wanted = set(body.participant_ids or [])
        created, skipped = [], []
        for x in rows:
            if wanted and x.id not in wanted:
                continue
            if not x.contact_id:
                skipped.append({"participant_id": x.id, "reason": "kein Kontakt im CRM"})
                continue
            try:
                row = await dispatch_module._create(
                    session,
                    principal,
                    dispatch_module.DispatchIn(
                        document_id=p.pdf_document_id, contact_id=x.contact_id, channel=body.channel
                    ),
                    batch=f"handover:{p.id}",
                )
                created.append(dispatch_module._out(row))
            except ProblemError as exc:
                skipped.append({"participant_id": x.id, "reason": exc.detail or exc.error.title})
        if created and p.status == "completed":
            p.status = "sent"
        await session.flush()
        await _event(session, principal, "handover.dispatched", p, count=len(created))
        return {"created": created, "skipped": skipped}


async def prepare_helper_completion_dispatch(
    session: Any, principal: TenantPrincipal, p: HandoverProtocol, helper_contact_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Helper finish flow (M30, ported from U-Protokoll): one dispatch draft (M23) per
    participant with an e-mail address plus the helper, prepared right after the completion
    triggered from the portal. Still only a draft in the outbox with the four-eyes approval
    (M20-01); nothing is sent from here."""
    from mhvp.communication import dispatch as dispatch_module
    from mhvp.handover.models import HandoverParticipant

    if not p.pdf_document_id:
        return []
    rows = (
        await session.scalars(
            select(HandoverParticipant).where(HandoverParticipant.protocol_id == p.id)
        )
    ).all()
    contact_ids = {x.contact_id for x in rows if x.contact_id}
    contact_ids.add(helper_contact_id)
    created: list[dict[str, Any]] = []
    for contact_id in contact_ids:
        try:
            row = await dispatch_module._create(
                session,
                principal,
                dispatch_module.DispatchIn(
                    document_id=p.pdf_document_id, contact_id=contact_id, channel="email"
                ),
                batch=f"handover:{p.id}",
            )
            created.append(dispatch_module._out(row))
        except ProblemError:
            continue
    if created and p.status == "completed":
        p.status = "sent"
        await session.flush()
    return created


async def notify_creator_of_completion(
    session: Any, principal: TenantPrincipal, p: HandoverProtocol
) -> None:
    """Internal notification to the staff user who created the protocol; there is no separate
    push/mail notification channel in the platform yet, so this uses the same event feed as
    every other internal notice (docs/plans/M30-uebergabeprotokoll.md)."""
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="handover.portal.helper_finished",
        entity_type="handover_protocol",
        entity_id=p.id,
        actor_user_id=principal.user_id,
        payload={"number": p.number, "notify_user_id": str(p.created_by) if p.created_by else None},
    )


# Portal access of a participant (M30 stage 3) ------------------------------------------------


class PortalAccessIn(_In):
    email: str | None = Field(default=None, min_length=3, max_length=320)


# Gehilfenzugang (M30, ported from U-Protokoll "Gehilfenzugänge"): the participant, tenant or
# owner fills in and signs the protocol themselves. This reuses the existing portal account and
# access grant (M21) with a scope on exactly this protocol; there is no second, password based
# authentication next to the portal session (decision of the integrator 25.09.2026). The default
# expiry mirrors U-Protokoll migration 006 (setting ``helper.access_days = 30``); unrelated to
# the 14 day read only period after completion (``READ_DAYS`` in mhvp.handover.portal).
HELPER_KINDS = ("helper", "tenant", "owner")
DEFAULT_HELPER_EXPIRY_DAYS = 30


class HelperAccessIn(_In):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    kind: str = Field(default="helper", pattern="^(" + "|".join(HELPER_KINDS) + ")$")
    register_as_participant: bool = False
    participant_role: str | None = Field(default=None, pattern="^(moving_in|moving_out)$")
    expires_days: int | None = Field(default=None, ge=1, le=365)
    # M30-01: the invitation code is stored only as a hash, so the mail draft must be prepared
    # while the code exists in clear text. False shows the code once in the response instead.
    invitation_as_mail_draft: bool = True


async def _find_or_create_contact(
    session: Any, principal: TenantPrincipal, name: str, email: str
) -> uuid.UUID:
    """Match an existing contact by e-mail, else create a minimal person contact for the
    Gehilfenzugang (no CRM contact required to invite a helper)."""
    from mhvp.contacts.models import Contact, ContactEmail, ContactKind

    existing = await session.scalar(
        select(ContactEmail.contact_id).where(
            ContactEmail.tenant_id == principal.tenant_id, ContactEmail.email == email
        )
    )
    if existing is not None:
        return uuid.UUID(str(existing))
    parts = name.strip().split(" ", 1)
    contact = Contact(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        kind=ContactKind.PERSON,
        first_name=parts[0] or None,
        last_name=parts[1] if len(parts) > 1 else None,
        display_name=name.strip() or email,
    )
    session.add(contact)
    await session.flush()
    session.add(
        ContactEmail(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            contact_id=contact.id,
            email=email,
            is_primary=True,
        )
    )
    await session.flush()
    return contact.id


def _portal_url(request: Request) -> str | None:
    url = getattr(request.app.state.settings, "web_portal_url", None)
    return str(url).rstrip("/") if url else None


def invitation_text(
    *,
    number: str,
    name: str | None,
    token: str,
    expires_at: datetime | None,
    portal_url: str | None,
) -> tuple[str, str]:
    """Subject and body of the invitation (M30-01), shared by the mail draft and the letter.

    The code exists in clear text only while this text is built; it is stored as a hash."""
    greeting = f"Guten Tag {name}," if name else "Guten Tag,"
    where = (
        f"Bitte rufen Sie das Portal unter {portal_url} auf"
        if portal_url
        else "Bitte rufen Sie das Kundenportal der Verwaltung auf"
    )
    valid = (
        f"Der Einladungscode ist bis zum {expires_at.astimezone(UTC):%d.%m.%Y} gültig und kann "
        "nur einmal verwendet werden."
        if expires_at is not None
        else "Der Einladungscode kann nur einmal verwendet werden."
    )
    body = (
        f"{greeting}\n\n"
        f"für das Übergabeprotokoll {number} wurde für Sie ein Zugang im Portal eingerichtet. "
        "Dort können Sie das Protokoll ausfüllen und abschließen.\n\n"
        f"{where} und geben Sie bei der Aktivierung den folgenden Einladungscode ein:\n"
        f"{token}\n\n"
        f"{valid}\n\n"
        "Bei der Aktivierung vergeben Sie ein Passwort. Anschließend richten Sie einen zweiten "
        "Faktor ein (Einmalcode aus einer Authenticator-App auf Ihrem Smartphone), der bei "
        "jeder Anmeldung abgefragt wird.\n\n"
        "Bitte geben Sie den Einladungscode nicht an Dritte weiter."
    )
    return f"Zugang zum Übergabeprotokoll {number}", body


async def _draft_invitation_mail(
    session: Any,
    principal: TenantPrincipal,
    *,
    to_email: str,
    subject: str,
    body_text: str,
    contact_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Mail draft in the existing outbox (M20), needs the four-eyes approval before it is sent;
    None if the tenant has no enabled mailbox, so the caller shows the code once instead."""
    from mhvp.communication.models import Mailbox, Message

    mailbox_id = await session.scalar(
        select(Mailbox.id)
        .where(Mailbox.tenant_id == principal.tenant_id, Mailbox.enabled.is_(True))
        .limit(1)
    )
    if mailbox_id is None:
        return None
    draft = Message(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        direction="out",
        status="draft",
        mailbox_id=mailbox_id,
        to_addresses=[to_email],
        subject=subject[:998],
        body=body_text,
        contact_id=contact_id,
    )
    session.add(draft)
    await session.flush()
    return draft.id


@router.get("/protocols/{protocol_id}/helper-access", summary="Gehilfenzugänge auflisten")
async def list_helper_access(
    protocol_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    from mhvp.contacts.models import Contact, ContactEmail
    from mhvp.portal.models import AccessGrant, PortalAccount

    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        rows = (
            await session.execute(
                select(AccessGrant, PortalAccount)
                .join(PortalAccount, PortalAccount.id == AccessGrant.account_id)
                .where(AccessGrant.scope_type == "handover", AccessGrant.scope_id == p.id)
                .order_by(AccessGrant.created_at)
            )
        ).all()
        out = []
        for grant, account in rows:
            contact = await session.get(Contact, account.contact_id)
            out.append(
                {
                    "grant_id": grant.id,
                    "account_id": account.id,
                    "contact_id": account.contact_id,
                    "name": (
                        " ".join(x for x in (contact.first_name, contact.last_name) if x)
                        if contact is not None
                        else None
                    ),
                    "kind": grant.role,
                    "right": grant.right,
                    "valid_from": grant.valid_from,
                    "valid_to": grant.valid_to,
                    "account_status": account.status,
                    "activated": account.activated_at is not None,
                    "has_email": bool(
                        await session.scalar(
                            select(ContactEmail.id)
                            .where(ContactEmail.contact_id == account.contact_id)
                            .limit(1)
                        )
                    ),
                }
            )
        return out


@router.post(
    "/protocols/{protocol_id}/helper-access",
    status_code=201,
    summary="Gehilfenzugang anlegen (Portalzugang mit eingeschränkter Sicht auf ein Protokoll)",
)
async def create_helper_access(
    protocol_id: uuid.UUID,
    body: HelperAccessIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.handover.models import HandoverParticipant
    from mhvp.portal.models import AccessGrant, PortalAccount
    from mhvp.portal.routers import provision_account

    email = body.email.strip().lower()
    display_name = body.name.strip()
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        contact_id = await _find_or_create_contact(session, principal, display_name, email)
        if body.register_as_participant:
            parts = display_name.split(" ", 1)
            session.add(
                HandoverParticipant(
                    tenant_id=principal.tenant_id,
                    created_by=principal.user_id,
                    protocol_id=p.id,
                    contact_id=contact_id,
                    role=body.participant_role or "other",
                    first_name=parts[0] or None,
                    last_name=parts[1] if len(parts) > 1 else None,
                    email=email,
                )
            )
        account = await session.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == contact_id)
        )
    token: str | None = None
    if account is None:
        created = await provision_account(
            request, principal, contact_id=contact_id, email=email, display_name=display_name
        )
        token = created["invitation_token"]
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        account = await session.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == contact_id)
        )
        if account is None:  # pragma: no cover - created above or found before
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        grant = await session.scalar(
            select(AccessGrant).where(
                AccessGrant.account_id == account.id,
                AccessGrant.scope_type == "handover",
                AccessGrant.scope_id == p.id,
            )
        )
        valid_to = local_today() + timedelta(days=body.expires_days or DEFAULT_HELPER_EXPIRY_DAYS)
        if grant is None:
            grant = AccessGrant(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                account_id=account.id,
                scope_type="handover",
                scope_id=p.id,
                right="edit",
                legal_basis="handover_helper",
                role=body.kind,
                valid_from=local_today(),
            )
            session.add(grant)
        grant.right = "edit"
        grant.role = body.kind
        grant.valid_from = local_today()
        grant.valid_to = valid_to
        await session.flush()
        mail_id = None
        if token is not None and body.invitation_as_mail_draft:
            subject, text = invitation_text(
                number=p.number,
                name=display_name,
                token=token,
                expires_at=account.invitation_expires_at,
                portal_url=_portal_url(request),
            )
            mail_id = await _draft_invitation_mail(
                session,
                principal,
                to_email=email,
                subject=subject,
                body_text=text,
                contact_id=contact_id,
            )
        await _event(
            session,
            principal,
            "handover.helper_access.granted",
            p,
            grant_id=str(grant.id),
            kind=body.kind,
            invited=token is not None,
            mail_draft_id=str(mail_id) if mail_id else None,
        )
        return {
            "grant_id": grant.id,
            "account_id": account.id,
            "contact_id": contact_id,
            "kind": grant.role,
            "valid_to": grant.valid_to,
            # Shown once, only when no mail draft could be prepared (no mailbox configured).
            "invitation_token": token if mail_id is None else None,
            "mail_draft_id": mail_id,
        }


@router.delete(
    "/protocols/{protocol_id}/helper-access/{grant_id}",
    status_code=204,
    summary="Gehilfenzugang beenden",
)
async def revoke_helper_access(
    protocol_id: uuid.UUID,
    grant_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    from mhvp.portal.models import AccessGrant

    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        grant = await session.get(AccessGrant, grant_id)
        if grant is None or grant.scope_type != "handover" or grant.scope_id != p.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(grant)
        await session.flush()
        await _event(
            session, principal, "handover.helper_access.revoked", p, grant_id=str(grant_id)
        )
    return Response(status_code=204)


@router.post(
    "/protocols/{protocol_id}/helper-access/{grant_id}/resend",
    summary="Zugangsdaten erneut zustellen",
)
async def resend_helper_access(
    protocol_id: uuid.UUID,
    grant_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    from mhvp.contacts.models import ContactEmail
    from mhvp.portal.models import AccessGrant, PortalAccount
    from mhvp.portal.routers import INVITE_DAYS, _hash

    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        grant = await session.get(AccessGrant, grant_id)
        if grant is None or grant.scope_type != "handover" or grant.scope_id != p.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        account = await session.get(PortalAccount, grant.account_id)
        if account is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if account.activated_at is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Der Zugang wurde bereits aktiviert, ein neuer Einladungscode ist nicht "
                "nötig.",
            )
        secret = secrets.token_urlsafe(32)
        account.invitation_hash = _hash(secret)
        account.invitation_expires_at = datetime.now(UTC) + timedelta(days=INVITE_DAYS)
        token = f"{principal.tenant_id.hex}.{secret}"
        email = await session.scalar(
            select(ContactEmail.email).where(
                ContactEmail.contact_id == account.contact_id, ContactEmail.is_primary.is_(True)
            )
        )
        await session.flush()
        mail_id = None
        if email:
            mail_id = await _draft_invitation_mail(
                session,
                principal,
                to_email=email,
                subject=f"Zugang zum Übergabeprotokoll {p.number} (erneut)",
                body_text=invitation_text(
                    number=p.number,
                    name=None,
                    token=token,
                    expires_at=account.invitation_expires_at,
                    portal_url=_portal_url(request),
                )[1],
                contact_id=account.contact_id,
            )
        await _event(session, principal, "handover.helper_access.resent", p, grant_id=str(grant_id))
        return {"invitation_token": token if mail_id is None else None, "mail_draft_id": mail_id}


async def _rotate_invitation(
    session: Any, principal: TenantPrincipal, p: HandoverProtocol, grant_id: uuid.UUID
) -> tuple[Any, str, str | None, str | None]:
    """New one time invitation code for a not yet activated helper access (M30-01).

    Only the hash is stored, so a code shown earlier cannot be recovered; every delivery path
    issues a fresh code and thereby invalidates the previous one. Returns the account, the
    clear text token, the primary e-mail and the display name of the contact."""
    from mhvp.contacts.models import Contact, ContactEmail
    from mhvp.portal.models import AccessGrant, PortalAccount
    from mhvp.portal.routers import INVITE_DAYS, _hash

    grant = await session.get(AccessGrant, grant_id)
    if grant is None or grant.scope_type != "handover" or grant.scope_id != p.id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    account = await session.get(PortalAccount, grant.account_id)
    if account is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if account.activated_at is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Der Zugang wurde bereits aktiviert, ein Einladungscode ist nicht nötig.",
        )
    secret = secrets.token_urlsafe(32)
    account.invitation_hash = _hash(secret)
    account.invitation_expires_at = datetime.now(UTC) + timedelta(days=INVITE_DAYS)
    email = await session.scalar(
        select(ContactEmail.email).where(
            ContactEmail.contact_id == account.contact_id, ContactEmail.is_primary.is_(True)
        )
    )
    contact = await session.get(Contact, account.contact_id)
    name = contact.display_name if contact is not None else None
    return account, f"{principal.tenant_id.hex}.{secret}", email, name


@router.post(
    "/protocols/{protocol_id}/helper-access/{grant_id}/invitation-draft",
    summary="Einladung als E-Mail-Entwurf anlegen (neuer Einladungscode, Vier-Augen-Freigabe)",
)
async def helper_invitation_draft(
    protocol_id: uuid.UUID,
    grant_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Mail draft in the outbox, nothing is sent. The code is never part of the response."""
    from mhvp.communication.models import Mailbox

    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        if not await session.scalar(select(Mailbox.id).where(Mailbox.enabled.is_(True)).limit(1)):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Kein aktiviertes Postfach hinterlegt. Bitte das Anschreiben verwenden.",
            )
        account, token, email, name = await _rotate_invitation(session, principal, p, grant_id)
        if not email:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Für den Beteiligten ist keine E-Mail-Adresse erfasst. Bitte das "
                "Anschreiben verwenden.",
            )
        subject, text = invitation_text(
            number=p.number,
            name=name,
            token=token,
            expires_at=account.invitation_expires_at,
            portal_url=_portal_url(request),
        )
        mail_id = await _draft_invitation_mail(
            session,
            principal,
            to_email=email,
            subject=subject,
            body_text=text,
            contact_id=account.contact_id,
        )
        await session.flush()
        await _event(
            session,
            principal,
            "handover.helper_access.invitation_drafted",
            p,
            grant_id=str(grant_id),
            mail_draft_id=str(mail_id),
        )
        return {"mail_draft_id": mail_id, "invitation_expires_at": account.invitation_expires_at}


@router.post(
    "/protocols/{protocol_id}/helper-access/{grant_id}/invitation-letter",
    summary="Einladung als Anschreiben (PDF, neuer Einladungscode)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def helper_invitation_letter(
    protocol_id: uuid.UUID,
    grant_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    """Letter on the tenant letterhead (M6 renderer). POST, not GET: issuing the letter
    rotates the invitation code, a prefetch must not invalidate a code already handed out."""
    from mhvp.documents import letters

    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        head = await documents.letterhead(session, _blobs(request))
        account, token, _email, name = await _rotate_invitation(session, principal, p, grant_id)
        try:
            _contact, lines, _data = await documents.recipient(session, account.contact_id)
        except ProblemError:
            lines = [name or ""]  # no postal address recorded: name only, address by hand
        subject, text = invitation_text(
            number=p.number,
            name=name,
            token=token,
            expires_at=account.invitation_expires_at,
            portal_url=_portal_url(request),
        )
        content = letters.render_pdf(
            head,
            letters.Letter(
                recipient_lines=lines,
                subject=letters.render_text("{{ s }}", {"s": subject}),
                body=letters.render_text("{{ b }}", {"b": text}),
                letter_date=local_today(),
                info=[("Protokoll", p.number)],
            ),
        )
        await session.flush()
        await _event(
            session,
            principal,
            "handover.helper_access.invitation_letter",
            p,
            grant_id=str(grant_id),
        )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "content-disposition": f'attachment; filename="einladung-{p.number}.pdf"',
            "cache-control": "no-store",
        },
    )


async def portal_access_of(
    session: Any, p: HandoverProtocol, contact_id: uuid.UUID | None
) -> dict[str, Any] | None:
    """Portal account and handover grant of a participant, None without account or grant."""
    from mhvp.portal.models import AccessGrant, PortalAccount

    if contact_id is None:
        return None
    account = await session.scalar(
        select(PortalAccount).where(PortalAccount.contact_id == contact_id)
    )
    if account is None:
        return None
    grant = await session.scalar(
        select(AccessGrant).where(
            AccessGrant.account_id == account.id,
            AccessGrant.scope_type == "handover",
            AccessGrant.scope_id == p.id,
        )
    )
    if grant is None:
        return None
    today = local_today()
    return {
        "account_status": account.status,
        "right": grant.right,
        "valid_to": grant.valid_to,
        "active": grant.valid_from <= today and (grant.valid_to is None or grant.valid_to >= today),
    }


@router.post(
    "/protocols/{protocol_id}/participants/{participant_id}/portal-access",
    status_code=201,
    summary="Portalzugang für einen Beteiligten (Gehilfe) einrichten",
)
async def grant_portal_access(
    protocol_id: uuid.UUID,
    participant_id: uuid.UUID,
    body: PortalAccessIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """The participant fills in and signs the protocol in the portal (docs/rules/M30-01.md).

    Needs a CRM contact on the participant. Without a portal account one is created (role
    portal_user, invitation token shown once); the grant is ``handover`` / ``edit`` until the
    completion. Repeated calls renew the grant."""
    from mhvp.handover.models import HandoverParticipant
    from mhvp.portal.models import AccessGrant, PortalAccount
    from mhvp.portal.routers import provision_account

    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        participant = await session.get(HandoverParticipant, participant_id)
        if participant is None or participant.protocol_id != p.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if participant.contact_id is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Der Beteiligte muss mit einem Kontakt des CRM verknüpft sein.",
            )
        contact_id = participant.contact_id
        email = (body.email or participant.email or "").strip()
        display_name = (
            " ".join(x for x in (participant.first_name, participant.last_name) if x)
            or participant.company
            or "Beteiligter"
        )
        account = await session.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == contact_id)
        )
    token: str | None = None
    if account is None:
        if not email:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Für die Einladung wird eine E-Mail-Adresse benötigt.",
            )
        created = await provision_account(
            request, principal, contact_id=contact_id, email=email, display_name=display_name
        )
        token = created["invitation_token"]
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        account = await session.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == contact_id)
        )
        if account is None:  # pragma: no cover - created above or found before
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        grant = await session.scalar(
            select(AccessGrant).where(
                AccessGrant.account_id == account.id,
                AccessGrant.scope_type == "handover",
                AccessGrant.scope_id == p.id,
            )
        )
        if grant is None:
            grant = AccessGrant(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                account_id=account.id,
                scope_type="handover",
                scope_id=p.id,
                right="edit",
                legal_basis="handover_participant",
                role="participant",
                valid_from=local_today(),
            )
            session.add(grant)
        grant.right, grant.valid_to, grant.valid_from = "edit", None, local_today()
        await session.flush()
        await _event(
            session,
            principal,
            "handover.portal_access.granted",
            p,
            participant_id=str(participant_id),
            account_id=str(account.id),
            invited=token is not None,
        )
        out = await portal_access_of(session, p, contact_id) or {}
        out["account_id"] = account.id
        out["invitation_token"] = token
        out["email"] = email or None
        return out


@router.delete(
    "/protocols/{protocol_id}/participants/{participant_id}/portal-access",
    status_code=204,
    summary="Portalzugang eines Beteiligten beenden",
)
async def revoke_portal_access(
    protocol_id: uuid.UUID,
    participant_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    from mhvp.handover.models import HandoverParticipant
    from mhvp.portal.models import AccessGrant, PortalAccount

    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        participant = await session.get(HandoverParticipant, participant_id)
        if participant is None or participant.protocol_id != p.id or not participant.contact_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        account = await session.scalar(
            select(PortalAccount).where(PortalAccount.contact_id == participant.contact_id)
        )
        grant = (
            await session.scalar(
                select(AccessGrant).where(
                    AccessGrant.account_id == account.id,
                    AccessGrant.scope_type == "handover",
                    AccessGrant.scope_id == p.id,
                )
            )
            if account is not None
            else None
        )
        if grant is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(grant)
        await session.flush()
        await _event(
            session,
            principal,
            "handover.portal_access.revoked",
            p,
            participant_id=str(participant_id),
        )
    return Response(status_code=204)


# Sections (generic, placed last so that the specific routes above win) ------------------------


def _section(name: str) -> tuple[type[Any], type[_In]]:
    if name not in svc.SECTIONS:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"Unbekannter Abschnitt {name!r}.")
    return svc.SECTIONS[name][0], SECTION_SCHEMAS[name]


async def _body(request: Request, schema: type[_In]) -> _In:
    """Validate the JSON body against the section schema (same problem format as FastAPI).

    A delegating router (portal, M30 stage 3) may put a pre-filtered payload into
    ``request.state.handover_payload``; it then replaces the raw body."""
    payload = getattr(request.state, "handover_payload", None)
    try:
        return schema.model_validate(payload if payload is not None else await request.json())
    except ValidationError as exc:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            errors=[
                FieldError(
                    location=["body", *e["loc"]],
                    field=".".join(str(x) for x in e["loc"]),
                    code=str(e["type"]),
                    message=e["msg"],
                )
                for e in exc.errors()
            ],
        ) from exc


async def _validate_refs(
    session: Any, name: str, p: HandoverProtocol, data: dict[str, Any]
) -> None:
    for column, target in svc.SECTIONS[name][1].items():
        ref = data.get(column)
        if ref is None:
            continue
        model = svc.SECTIONS[target][0]
        row = await session.get(model, ref)
        if row is None or row.protocol_id != p.id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Verweis gehört nicht zum Protokoll.")
    if name == "participants" and data.get("contact_id"):
        from mhvp.contacts.models import Contact

        if await session.get(Contact, data["contact_id"]) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kontakt nicht gefunden.")
    if name == "meters" and data.get("meter_id"):
        from mhvp.properties.models import Meter

        if await session.get(Meter, data["meter_id"]) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Zähler nicht gefunden.")


@router.post("/protocols/{protocol_id}/{section}", status_code=201, summary="Teildatensatz anlegen")
async def create_item(
    protocol_id: uuid.UUID,
    section: str,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    model, schema = _section(section)
    body = await _body(request, schema)
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        data = body.model_dump()
        await _validate_refs(session, section, p, data)
        if section == "participants" and data.get("contact_id"):
            data = {
                **(await _contact_snapshot(session, data["contact_id"])),
                **{k: v for k, v in data.items() if v not in (None, "")},
            }
        row = model(
            tenant_id=principal.tenant_id, protocol_id=p.id, created_by=principal.user_id, **data
        )
        session.add(row)
        if p.status == "draft":
            p.status = "in_progress"
        await _fresh(session, row)
        await _event(session, principal, f"handover.{section}.added", p, item_id=str(row.id))
        out = _row(row)
        if section == "participants":
            out["role_label"] = svc.role_label(out["role"], p.kind)
            out["portal_access"] = await portal_access_of(session, p, row.contact_id)
        return out


async def _contact_snapshot(session: Any, contact_id: uuid.UUID) -> dict[str, Any]:
    from mhvp.contacts.models import Contact, ContactAddress, ContactEmail, ContactPhone

    contact = await session.get(Contact, contact_id)
    if contact is None:
        return {}
    address = await session.scalar(
        select(ContactAddress).where(ContactAddress.contact_id == contact_id).limit(1)
    )
    email = await session.scalar(
        select(ContactEmail.email)
        .where(ContactEmail.contact_id == contact_id)
        .order_by(ContactEmail.is_primary.desc())
        .limit(1)
    )
    phone = await session.scalar(
        select(ContactPhone.number).where(ContactPhone.contact_id == contact_id).limit(1)
    )
    return {
        "salutation": contact.salutation,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "company": contact.company_name,
        "street": address.street if address else None,
        "house_number": address.house_number if address else None,
        "postal_code": address.postal_code if address else None,
        "city": address.city if address else None,
        "email": email,
        "phone": phone,
    }


@router.post("/protocols/{protocol_id}/{section}/order", summary="Reihenfolge speichern")
async def order_items(
    protocol_id: uuid.UUID,
    section: str,
    body: OrderIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    model, _ = _section(section)
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        for index, item_id in enumerate(body.ids):
            row = await session.get(model, item_id)
            if row is not None and row.protocol_id == p.id:
                row.sort_order = index
        await session.flush()
        return {"ok": True}


@router.patch("/protocols/{protocol_id}/{section}/{item_id}", summary="Teildatensatz ändern")
async def patch_item(
    protocol_id: uuid.UUID,
    section: str,
    item_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    model, schema = _section(section)
    body = await _body(request, schema)
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        row = await session.get(model, item_id)
        if row is None or row.protocol_id != p.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = body.model_dump(exclude_unset=True)
        await _validate_refs(session, section, p, data)
        for key, value in data.items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await _fresh(session, row)
        await _event(session, principal, f"handover.{section}.updated", p, item_id=str(row.id))
        out = _row(row)
        if section == "participants":
            out["role_label"] = svc.role_label(out["role"], p.kind)
            out["portal_access"] = await portal_access_of(session, p, row.contact_id)
        return out


@router.delete(
    "/protocols/{protocol_id}/{section}/{item_id}", status_code=204, summary="Teildatensatz löschen"
)
async def delete_item(
    protocol_id: uuid.UUID,
    section: str,
    item_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    model, _ = _section(section)
    async with tenant_tx(request, principal) as session:
        p = await _get(session, protocol_id)
        svc.require_unlocked(p)
        row = await session.get(model, item_id)
        if row is None or row.protocol_id != p.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(row)
        await session.flush()
        await _event(session, principal, f"handover.{section}.deleted", p, item_id=str(item_id))
    return Response(status_code=204)
