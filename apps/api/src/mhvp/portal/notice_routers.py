"""Schwarzes Brett je Objekt (14, M21-01, A54, 6.2): CRM maintenance and portal view.

CRM (permission ``properties:update`` for writes, ``properties:read`` for the list): notices
are created at a property with title, text, validity from/to, category, type (neutral, info,
warning, danger), audiences (tenant, owner, provider) and several documents. "Beenden" removes
a notice from the portal at once and keeps the record. Portal: only notices of properties the
account holds an active grant (or a work order, for providers) for, only for the matching
audience and only within the validity period on the current day (access matrix 6.9.6). The read
confirmation per notice (notice_board_read) is an indication only. A notice is information of
the management; it is no delivery of a document and starts no deadline."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_path_guard
from mhvp.core.escaping import content_disposition
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.portal import access
from mhvp.portal.models import PortalAccount
from mhvp.portal.notices import (
    AUDIENCES,
    LEGACY_ALL,
    NoticeBoardRead,
    PropertyNotice,
    audience_matches,
    is_current,
    legacy_audience,
)
from mhvp.portal.routers import Portal, portal_user
from mhvp.properties.models import LegalEntity, Property, Unit
from mhvp.properties.services import check_catalog
from mhvp.workspace.services import local_today

# M2-02/S16-02: path ids outside the property assignment answer 404.
crm_router = APIRouter(tags=["Objekte"], dependencies=[Depends(property_path_guard)])
portal_router = APIRouter(prefix="/portal", tags=["Portal"])
READ = require_permission("properties:read")
UPDATE = require_permission("properties:update")
# A notice counts as "new" in the portal for this many days after its creation.
NEW_DAYS = 14


AudienceList = list[Literal["tenant", "owner", "provider"]]


class NoticeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20000)
    valid_from: date
    valid_to: date | None = None
    category: str | None = Field(default=None, max_length=64)
    type: Literal["neutral", "info", "warning", "danger"] = "neutral"
    # New: list of audiences. Legacy single value ``audience`` (tenant, owner, all) still works.
    audiences: AudienceList | None = Field(default=None, min_length=1, max_length=3)
    audience: Literal["tenant", "owner", "all"] | None = None
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    document_id: uuid.UUID | None = None


class NoticePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    valid_from: date | None = None
    valid_to: date | None = None
    clear_valid_to: bool = False
    category: str | None = Field(default=None, max_length=64)
    clear_category: bool = False
    type: Literal["neutral", "info", "warning", "danger"] | None = None
    audiences: AudienceList | None = Field(default=None, min_length=1, max_length=3)
    audience: Literal["tenant", "owner", "all"] | None = None
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    document_id: uuid.UUID | None = None
    clear_document: bool = False


def _audiences(
    audiences: Sequence[str] | None, legacy: str | None, default: list[str]
) -> list[str]:
    """Resolves the audience input to a sorted, duplicate free list."""
    if audiences is not None:
        chosen = list(audiences)
    elif legacy is not None:
        chosen = list(LEGACY_ALL) if legacy == "all" else [legacy]
    else:
        chosen = list(default)
    if not chosen or any(a not in AUDIENCES for a in chosen):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zielgruppe ungültig.")
    return [a for a in AUDIENCES if a in set(chosen)]


def _validate(valid_from: date, valid_to: date | None) -> None:
    if valid_to is not None and valid_to < valid_from:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Gültig bis darf nicht vor Gültig von liegen."
        )


def _ids(ids: list[uuid.UUID] | None, legacy: uuid.UUID | None) -> list[uuid.UUID] | None:
    if ids is None and legacy is None:
        return None
    out: list[uuid.UUID] = []
    for d in [*(ids or []), *([legacy] if legacy else [])]:
        if d not in out:
            out.append(d)
    return out


# Document visibility (6.9.6) a notice audience needs: the attachment is served through the
# notice, so the document must already be released for every group the notice addresses.
AUDIENCE_LABELS = {"tenant": "Mieter", "owner": "Eigentümer", "provider": "Dienstleister"}


async def _documents(session: Any, document_ids: list[uuid.UUID], audiences: list[str]) -> None:
    for document_id in document_ids:
        document = await session.get(Document, document_id)
        if document is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Dokument nicht gefunden.")
        visibility = set(document.visibility or [])
        missing = [g for g in audiences if g not in visibility]
        if missing:
            groups = ", ".join(AUDIENCE_LABELS[g] for g in missing)
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Das Dokument ist nicht für die Zielgruppe freigegeben (fehlt: {groups}).",
            )


def _out(n: PropertyNotice, today: date, stats: dict[str, int] | None = None) -> dict[str, Any]:
    out = {
        "id": n.id,
        "property_id": n.property_id,
        "title": n.title,
        "body": n.body,
        "valid_from": n.valid_from,
        "valid_to": n.valid_to,
        "category": n.category,
        "type": n.type,
        "audiences": list(n.audiences),
        "audience": legacy_audience(list(n.audiences)),
        "document_ids": list(n.document_ids),
        "document_id": n.document_ids[0] if n.document_ids else None,
        "ended_at": n.ended_at,
        "is_current": is_current(n, today),
        "created_at": n.created_at,
        "updated_at": n.updated_at,
    }
    if stats is not None:
        out["read_count"] = stats.get("read", 0)
        out["recipient_count"] = stats.get("recipients", 0)
    return out


async def _notice(session: Any, notice_id: uuid.UUID) -> PropertyNotice:
    row: PropertyNotice | None = await session.get(PropertyNotice, notice_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


# CRM --------------------------------------------------------------------------------------


async def _recipient_accounts(
    session: Any, property_id: uuid.UUID, audiences: list[str], today: date
) -> set[uuid.UUID]:
    """Portal accounts the notice addresses today: active unit or community grants at the
    property with a matching role, and providers with a work order at the property."""
    from mhvp.portal.models import AccessGrant
    from mhvp.tickets.models import WorkOrder

    out: set[uuid.UUID] = set()
    units = select(Unit.id).where(Unit.property_id == property_id)
    entities = select(LegalEntity.id).where(LegalEntity.property_id == property_id)
    held = [a for a in audiences if a in ("tenant", "owner")]
    if held:
        rows = await session.scalars(
            select(AccessGrant.account_id).where(
                AccessGrant.role.in_(held),
                AccessGrant.valid_from <= today,
                (AccessGrant.valid_to.is_(None)) | (AccessGrant.valid_to >= today),
                ((AccessGrant.scope_type == "unit") & AccessGrant.scope_id.in_(units))
                | ((AccessGrant.scope_type == "legal_entity") & AccessGrant.scope_id.in_(entities)),
            )
        )
        out.update(rows)
    if "provider" in audiences:
        rows = await session.scalars(
            select(PortalAccount.id).where(
                PortalAccount.contact_id.in_(
                    select(WorkOrder.provider_contact_id).where(
                        WorkOrder.property_id == property_id
                    )
                )
            )
        )
        out.update(rows)
    return out


async def _stats(session: Any, n: PropertyNotice, today: date) -> dict[str, int]:
    """Read quota: confirmations of addressed accounts against the addressed accounts."""
    recipients = await _recipient_accounts(session, n.property_id, list(n.audiences), today)
    readers = set(
        await session.scalars(
            select(NoticeBoardRead.account_id).where(NoticeBoardRead.notice_id == n.id)
        )
    )
    return {"recipients": len(recipients), "read": len(readers & recipients) if recipients else 0}


@crm_router.get(
    "/properties/{property_id}/notices",
    summary="Aushänge des Objekts",
    dependencies=[Depends(strict_query)],
)
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
        return [_out(n, today, await _stats(session, n, today)) for n in rows]


@crm_router.post("/properties/{property_id}/notices", status_code=201, summary="Aushang anlegen")
async def create_notice(
    property_id: uuid.UUID,
    body: NoticeIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    _validate(body.valid_from, body.valid_to)
    audiences = _audiences(body.audiences, body.audience, list(LEGACY_ALL))
    document_ids = _ids(body.document_ids, body.document_id) or []
    async with tenant_tx(request, principal) as session:
        if await session.get(Property, property_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await check_catalog(session, "notice_category", body.category)
        await _documents(session, document_ids, audiences)
        row = PropertyNotice(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            property_id=property_id,
            title=body.title,
            body=body.body,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            category=body.category,
            type=body.type,
            audiences=audiences,
            document_ids=document_ids,
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
            payload={"property_id": str(property_id), "audiences": audiences, "type": body.type},
        )
        today = local_today()
        return _out(row, today, await _stats(session, row, today))


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
        _validate(valid_from, valid_to)
        audiences = _audiences(body.audiences, body.audience, list(row.audiences))
        new_ids = _ids(body.document_ids, body.document_id)
        if body.clear_document:
            document_ids: list[uuid.UUID] = []
        elif new_ids is not None:
            document_ids = new_ids
        else:
            document_ids = list(row.document_ids)
        if new_ids is not None or audiences != list(row.audiences):
            await _documents(session, document_ids, audiences)
        if body.clear_category:
            row.category = None
        elif "category" in changes:
            await check_catalog(session, "notice_category", body.category)
            row.category = body.category
        if body.type is not None:
            row.type = body.type
        for field in ("title", "body"):
            if field in changes:
                setattr(row, field, changes[field])
        row.valid_from, row.valid_to = valid_from, valid_to
        row.audiences, row.document_ids = audiences, document_ids
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
        today = local_today()
        return _out(row, today, await _stats(session, row, today))


@crm_router.get("/notices/{notice_id}/reads", summary="Lesebestätigungen eines Aushangs")
async def notice_reads(
    notice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Read quota and confirmations (6.2 notice_board_read). An indication only: no delivery,
    no legally assessed receipt, no deadline."""
    async with tenant_tx(request, principal) as session:
        row = await _notice(session, notice_id)
        reads = (
            await session.execute(
                select(NoticeBoardRead, PortalAccount.contact_id)
                .join(PortalAccount, PortalAccount.id == NoticeBoardRead.account_id)
                .where(NoticeBoardRead.notice_id == notice_id)
                .order_by(NoticeBoardRead.read_at.desc())
            )
        ).all()
        stats = await _stats(session, row, local_today())
        return {
            "notice_id": notice_id,
            "recipient_count": stats["recipients"],
            "read_count": stats["read"],
            "reads": [
                {"account_id": r.account_id, "contact_id": cid, "read_at": r.read_at}
                for r, cid in reads
            ],
            "note": "Indiz für die Kenntnisnahme im Portal. Keine Zustellung und kein rechtlich "
            "bewerteter Zugang.",
        }


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
    # Providers: properties of their work orders (6.2 audience provider).
    from mhvp.tickets.models import WorkOrder

    if account.contact_id is not None:
        for prop in await session.scalars(
            select(WorkOrder.property_id)
            .where(WorkOrder.provider_contact_id == account.contact_id)
            .distinct()
        ):
            out.setdefault(prop, set()).add("provider")
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


@portal_router.get(
    "/notices",
    summary="Aushänge der eigenen Objekte (Schwarzes Brett)",
    dependencies=[Depends(strict_query)],
)
async def portal_notices(
    request: Request, ctx: Portal = Depends(portal_user)
) -> list[dict[str, Any]]:
    """Current notices of the account's properties for its roles. Reading writes nothing."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        today = local_today()
        new_since = datetime.now(tz=UTC) - timedelta(days=NEW_DAYS)
        visible = await _visible_notices(session, account, today)
        reads = {
            r.notice_id: r.read_at
            for r in await session.scalars(
                select(NoticeBoardRead).where(NoticeBoardRead.account_id == account.id)
            )
        }
        doc_ids = {d for n, _, _ in visible for d in n.document_ids}
        files = (
            {
                d.id: d.filename
                for d in await session.scalars(select(Document).where(Document.id.in_(doc_ids)))
            }
            if doc_ids
            else {}
        )
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
                "category": n.category,
                "type": n.type,
                "has_document": any(d in files for d in n.document_ids),
                "documents": [
                    {"id": d, "filename": files[d]} for d in n.document_ids if d in files
                ],
                "is_new": n.created_at >= new_since,
                "read": n.id in reads,
                "read_at": reads.get(n.id),
                "created_at": n.created_at,
            }
            for n, p, _ in visible
        ]


class PortalNoticeReadOut(BaseModel):
    """AK11 (GAI-304): typed response, ``extra="allow"`` keeps later fields."""

    model_config = ConfigDict(extra="allow")
    notice_id: uuid.UUID
    read: bool
    read_at: datetime


@portal_router.post(
    "/notices/{notice_id}/read",
    summary="Aushang als gelesen bestätigen (Lesebestätigung)",
    response_model=PortalNoticeReadOut,
)
async def portal_notice_read(
    notice_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """Idempotent read confirmation of a visible notice (6.2 notice_board_read). An indication
    only, no delivery and no legally assessed receipt."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        visible = {n.id for n, _, _ in await _visible_notices(session, account, local_today())}
        if notice_id not in visible:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
        existing = await session.scalar(
            select(NoticeBoardRead).where(
                NoticeBoardRead.notice_id == notice_id, NoticeBoardRead.account_id == account.id
            )
        )
        if existing is None:
            existing = NoticeBoardRead(
                tenant_id=account.tenant_id,
                created_by=account.user_id,
                notice_id=notice_id,
                account_id=account.id,
                read_at=datetime.now(tz=UTC),
            )
            session.add(existing)
            await session.flush()
        return {"notice_id": notice_id, "read": True, "read_at": existing.read_at}


async def _serve(
    request: Request, ctx: Portal, notice_id: uuid.UUID, document_id: uuid.UUID | None
) -> Response:
    from mhvp.documents.blobs import BlobStore

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        visible = {n.id: n for n, _, _ in await _visible_notices(session, account, local_today())}
        notice = visible.get(notice_id)
        if notice is None or not notice.document_ids:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
        target = document_id or notice.document_ids[0]
        if target not in notice.document_ids:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        document = await session.get(Document, target)
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


@portal_router.get(
    "/notices/{notice_id}/document",
    summary="Erste Anlage eines Aushangs herunterladen",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def portal_notice_document(
    notice_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> Response:
    """The attachment is visible exactly like the notice (same property, audience and day).
    No document read receipt is written: a notice is information of the management."""
    return await _serve(request, ctx, notice_id, None)


@portal_router.get(
    "/notices/{notice_id}/documents/{document_id}",
    summary="Anlage eines Aushangs herunterladen",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def portal_notice_attachment(
    notice_id: uuid.UUID,
    document_id: uuid.UUID,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> Response:
    return await _serve(request, ctx, notice_id, document_id)
