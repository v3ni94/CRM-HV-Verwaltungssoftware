"""Schwarzes Brett je Objekt (14, M21-01, A54): CRM maintenance and portal view.

CRM (permission ``properties:update`` for writes, ``properties:read`` for the list): notices
are created at a property with title, text, validity from/to, audience (tenant, owner, all)
and an optional document. "Beenden" removes a notice from the portal at once and keeps the
record. Portal: only notices of properties the account holds an active grant for, only for
the matching audience and only within the validity period on the current day (access matrix
6.9.6). A notice is information of the management; it is no delivery of a document and starts
no deadline."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.escaping import content_disposition
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.portal import access
from mhvp.portal.models import PortalAccount
from mhvp.portal.notices import AUDIENCES, PropertyNotice, audience_matches, is_current
from mhvp.portal.routers import Portal, portal_user
from mhvp.properties.models import LegalEntity, Property, Unit
from mhvp.workspace.services import local_today

crm_router = APIRouter(tags=["Objekte"])
portal_router = APIRouter(prefix="/portal", tags=["Portal"])
READ = require_permission("properties:read")
UPDATE = require_permission("properties:update")
# A notice counts as "new" in the portal for this many days after its creation.
NEW_DAYS = 14


class NoticeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    valid_from: date
    valid_to: date | None = None
    audience: str = Field(default="all", pattern="^(tenant|owner|all)$")
    document_id: uuid.UUID | None = None


class NoticePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    valid_from: date | None = None
    valid_to: date | None = None
    clear_valid_to: bool = False
    audience: str | None = Field(default=None, pattern="^(tenant|owner|all)$")
    document_id: uuid.UUID | None = None
    clear_document: bool = False


def _validate(valid_from: date, valid_to: date | None, audience: str) -> None:
    if audience not in AUDIENCES:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zielgruppe ungültig.")
    if valid_to is not None and valid_to < valid_from:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Gültig bis darf nicht vor Gültig von liegen."
        )


# Document visibility (6.9.6) a notice audience needs: the attachment is served through the
# notice, so the document must already be released for every group the notice addresses.
AUDIENCE_VISIBILITY = {"tenant": ("tenant",), "owner": ("owner",), "all": ("tenant", "owner")}
AUDIENCE_LABELS = {"tenant": "Mieter", "owner": "Eigentümer"}


async def _document(session: Any, document_id: uuid.UUID | None, audience: str) -> None:
    if document_id is None:
        return
    document = await session.get(Document, document_id)
    if document is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Dokument nicht gefunden.")
    visibility = set(document.visibility or [])
    missing = [g for g in AUDIENCE_VISIBILITY[audience] if g not in visibility]
    if missing:
        groups = ", ".join(AUDIENCE_LABELS[g] for g in missing)
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=f"Das Dokument ist nicht für die Zielgruppe freigegeben (fehlt: {groups}).",
        )


def _out(n: PropertyNotice, today: date) -> dict[str, Any]:
    return {
        "id": n.id,
        "property_id": n.property_id,
        "title": n.title,
        "body": n.body,
        "valid_from": n.valid_from,
        "valid_to": n.valid_to,
        "audience": n.audience,
        "document_id": n.document_id,
        "ended_at": n.ended_at,
        "is_current": is_current(n, today),
        "created_at": n.created_at,
        "updated_at": n.updated_at,
    }


async def _notice(session: Any, notice_id: uuid.UUID) -> PropertyNotice:
    row: PropertyNotice | None = await session.get(PropertyNotice, notice_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


# CRM --------------------------------------------------------------------------------------


@crm_router.get("/properties/{property_id}/notices", summary="Aushänge des Objekts")
async def list_notices(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        if await session.get(Property, property_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await session.scalars(
            select(PropertyNotice)
            .where(PropertyNotice.property_id == property_id)
            .order_by(PropertyNotice.valid_from.desc(), PropertyNotice.created_at.desc())
        )
        today = local_today()
        return [_out(n, today) for n in rows]


@crm_router.post("/properties/{property_id}/notices", status_code=201, summary="Aushang anlegen")
async def create_notice(
    property_id: uuid.UUID,
    body: NoticeIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    _validate(body.valid_from, body.valid_to, body.audience)
    async with tenant_tx(request, principal) as session:
        if await session.get(Property, property_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _document(session, body.document_id, body.audience)
        row = PropertyNotice(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_id=property_id,
            title=body.title,
            body=body.body,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            audience=body.audience,
            document_id=body.document_id,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property_notice.created",
            entity_type="property_notice",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"property_id": str(property_id), "audience": body.audience},
        )
        return _out(row, local_today())


@crm_router.patch("/notices/{notice_id}", summary="Aushang ändern")
async def patch_notice(
    notice_id: uuid.UUID,
    body: NoticePatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _notice(session, notice_id)
        if row.ended_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Beendeter Aushang ist nicht änderbar.")
        changes = body.model_dump(exclude_unset=True)
        valid_from = changes.get("valid_from", row.valid_from)
        valid_to = None if body.clear_valid_to else changes.get("valid_to", row.valid_to)
        audience = changes.get("audience", row.audience)
        _validate(valid_from, valid_to, audience)
        if body.clear_document:
            row.document_id = None
        elif "document_id" in changes:
            await _document(session, body.document_id, audience)
            row.document_id = body.document_id
        elif row.document_id is not None and audience != row.audience:
            await _document(session, row.document_id, audience)
        for field in ("title", "body"):
            if field in changes:
                setattr(row, field, changes[field])
        row.valid_from, row.valid_to, row.audience = valid_from, valid_to, audience
        await session.flush()
        await session.refresh(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property_notice.updated",
            entity_type="property_notice",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(changes)},
        )
        return _out(row, local_today())


@crm_router.post("/notices/{notice_id}/end", summary="Aushang beenden (sofort aus dem Portal)")
async def end_notice(
    notice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _notice(session, notice_id)
        if row.ended_at is None:
            row.ended_at = datetime.now(tz=UTC)
            row.ended_by = principal.user_id
            await session.flush()
            await session.refresh(row)
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="property_notice.ended",
                entity_type="property_notice",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={},
            )
        return _out(row, local_today())


# Portal -----------------------------------------------------------------------------------


async def _property_roles(
    session: Any, account: PortalAccount, today: date
) -> dict[uuid.UUID, set[str]]:
    """Properties of the account's active grants with the roles held there (6.9.6):
    unit grants carry the contract role, GdWE grants mark the owner."""
    out: dict[uuid.UUID, set[str]] = {}
    grants = await access.grants(session, account, today)
    unit_ids = {g.scope_id for g in grants if g.scope_type == "unit"}
    entity_ids = {g.scope_id for g in grants if g.scope_type == "legal_entity"}
    unit_property = (
        dict(
            (await session.execute(select(Unit.id, Unit.property_id).where(Unit.id.in_(unit_ids))))
            .tuples()
            .all()
        )
        if unit_ids
        else {}
    )
    entity_property = (
        dict(
            (
                await session.execute(
                    select(LegalEntity.id, LegalEntity.property_id).where(
                        LegalEntity.id.in_(entity_ids)
                    )
                )
            )
            .tuples()
            .all()
        )
        if entity_ids
        else {}
    )
    for g in grants:
        prop = None
        if g.scope_type == "unit":
            prop = unit_property.get(g.scope_id)
        elif g.scope_type == "legal_entity":
            prop = entity_property.get(g.scope_id)
        if prop is not None:
            out.setdefault(prop, set()).add(g.role)
    return out


async def _visible_notices(
    session: Any, account: PortalAccount, today: date
) -> list[tuple[PropertyNotice, Property, set[str]]]:
    roles = await _property_roles(session, account, today)
    if not roles:
        return []
    rows = (
        await session.execute(
            select(PropertyNotice, Property)
            .join(Property, Property.id == PropertyNotice.property_id)
            .where(PropertyNotice.property_id.in_(roles), PropertyNotice.ended_at.is_(None))
            .order_by(PropertyNotice.valid_from.desc(), PropertyNotice.created_at.desc())
        )
    ).all()
    return [
        (n, p, roles[n.property_id])
        for n, p in rows
        if is_current(n, today) and audience_matches(n, roles[n.property_id])
    ]


@portal_router.get("/notices", summary="Aushänge der eigenen Objekte (Schwarzes Brett)")
async def portal_notices(
    request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    """Current notices of the account's properties for its roles. Reading writes nothing."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        today = local_today()
        new_since = datetime.now(tz=UTC) - timedelta(days=NEW_DAYS)
        return [
            {
                "id": n.id,
                "property_id": p.id,
                "property_number": p.number,
                "property_name": p.name,
                "title": n.title,
                "body": n.body,
                "valid_from": n.valid_from,
                "valid_to": n.valid_to,
                "has_document": n.document_id is not None,
                "is_new": n.created_at >= new_since,
                "created_at": n.created_at,
            }
            for n, p, _ in await _visible_notices(session, account, today)
        ]


@portal_router.get(
    "/notices/{notice_id}/document",
    summary="Anlage eines Aushangs herunterladen",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def portal_notice_document(
    notice_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> Response:
    """The attachment is visible exactly like the notice (same property, audience and day).
    No read receipt is written: a notice is information of the management, not a delivery."""
    from mhvp.documents.blobs import BlobStore

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        visible = {n.id: n for n, _, _ in await _visible_notices(session, account, local_today())}
        notice = visible.get(notice_id)
        if notice is None or notice.document_id is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
        document = await session.get(Document, notice.document_id)
        if document is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        return Response(
            content=data,
            media_type=document.mime_type,
            headers={
                "Content-Disposition": content_disposition("attachment", document.filename),
                "X-Content-Type-Options": "nosniff",
            },
        )
