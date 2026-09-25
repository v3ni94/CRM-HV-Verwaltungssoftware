"""/api/v1/immoware: Lesezugriff auf Immoware24 per DAV, als Spiegel ohne Schreibzugriff (M32)."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from mhvp.contacts.models import Contact, ContactEmail, ContactKind, ContactPhone
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.immoware import schemas as s
from mhvp.immoware import service as svc
from mhvp.immoware.client import sanitize_error
from mhvp.immoware.models import (
    ImmowareConnection,
    ImmowareDavContact,
    ImmowareDavDocument,
    ImmowareDavEvent,
    ImmowareSyncRun,
    SyncKind,
)
from mhvp.immoware.webdav import download

router = APIRouter(prefix="/immoware", tags=["Immoware24"])
READ = require_permission("immoware:read")
MANAGE = require_permission("immoware:update")


async def _event(
    session: Any, principal: TenantPrincipal, type_: str, entity_id: uuid.UUID, **payload: Any
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type="immoware",
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload={k: v if isinstance(v, int | bool | None) else str(v) for k, v in payload.items()},
    )


def _connection_out(row: ImmowareConnection | None) -> s.ImmowareConnectionOut:
    if row is None:
        return s.ImmowareConnectionOut(
            base_url=None,
            carddav_url=None,
            caldav_url=None,
            username=None,
            has_password=False,
            enabled=False,
            verify_tls=True,
            poll_minutes=30,
            last_check_at=None,
            last_check_ok=None,
            last_error=None,
        )
    return s.ImmowareConnectionOut(
        base_url=row.base_url,
        carddav_url=row.carddav_url,
        caldav_url=row.caldav_url,
        username=row.username,
        has_password=bool(row.password),
        enabled=row.enabled,
        verify_tls=row.verify_tls,
        poll_minutes=row.poll_minutes,
        last_check_at=row.last_check_at,
        last_check_ok=row.last_check_ok,
        last_error=row.last_error,
    )


@router.get("/connection", summary="Immoware24-Anbindung lesen")
async def get_connection(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.ImmowareConnectionOut:
    async with tenant_tx(request, principal) as session:
        return _connection_out(await svc.get_connection(session))


@router.put("/connection", summary="Immoware24-Anbindung einrichten")
async def put_connection(
    body: s.ImmowareConnectionIn, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> s.ImmowareConnectionOut:
    async with tenant_tx(request, principal) as session:
        row = await svc.get_connection(session)
        if row is None:
            row = ImmowareConnection(tenant_id=principal.tenant_id)
            session.add(row)
        row.base_url = body.base_url
        row.carddav_url = body.carddav_url
        row.caldav_url = body.caldav_url
        row.username = body.username
        if body.password is not None:
            row.password = body.password
        row.enabled = body.enabled
        row.verify_tls = body.verify_tls
        row.poll_minutes = body.poll_minutes
        await session.flush()
        await _event(session, principal, "immoware.connection_updated", row.id, enabled=row.enabled)
        return _connection_out(row)


@router.post("/connection/check", summary="Verbindung pruefen (PROPFIND Depth 0)")
async def check_connection(
    request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> s.ImmowareConnectionOut:
    async with tenant_tx(request, principal) as session:
        row = await svc.get_connection(session)
        if row is None or not row.base_url or not row.username:
            raise ProblemError(ErrorCodes.IMW_NOT_CONFIGURED)
        row = await svc.check_connection(session, row)
        await _event(
            session, principal, "immoware.connection_checked", row.id, ok=bool(row.last_check_ok)
        )
        return _connection_out(row)


@router.post("/sync/{kind}", summary="Abholung manuell anstossen")
async def trigger_sync(
    kind: SyncKind, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> dict[str, str]:
    async with tenant_tx(request, principal) as session:
        connection = await svc.require_connection(session)
        run = await svc.run_sync(session, connection, kind)
        await _event(
            session, principal, f"immoware.sync_{kind.value}", run.id, status=run.status.value
        )
        return {"run_id": str(run.id)}


@router.get("/sync/runs", summary="Letzte Synchronisationslaeufe")
async def sync_runs(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.ImmowareSyncRunOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ImmowareSyncRun).order_by(ImmowareSyncRun.started_at.desc()).limit(50)
        )
        return [s.ImmowareSyncRunOut.model_validate(r) for r in rows]


def _paginate(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    return (page - 1) * page_size, page_size


@router.get("/documents", summary="Dokumentbaum durchsuchen")
async def list_documents(
    request: Request,
    path: str = Query(default=""),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        stmt = select(ImmowareDavDocument).where(ImmowareDavDocument.deleted_at.is_(None))
        if path:
            stmt = stmt.where(ImmowareDavDocument.href.like(f"{path}%"))
        if q:
            stmt = stmt.where(ImmowareDavDocument.display_name.ilike(f"%{q}%"))
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        offset, limit = _paginate(page, page_size)
        rows = await session.scalars(
            stmt.order_by(ImmowareDavDocument.href).offset(offset).limit(limit)
        )
        return {
            "data": [s.ImmowareDocumentOut.model_validate(r) for r in rows],
            "meta": s.Meta(page=page, per_page=page_size, total=total),
        }


@router.get("/documents/{document_id}/file", summary="Datei herunterladen (Proxy)")
async def download_document(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> StreamingResponse:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ImmowareDavDocument, document_id)
        if row is None or row.tenant_id != principal.tenant_id or row.deleted_at is not None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        connection = await svc.require_connection(session)
        href = row.href
        base = (connection.base_url or "").rstrip("/")
        url = href if href.startswith("http") else base + "/" + href.lstrip("/")
        client = svc.dav_client(connection)
        content_type = row.content_type or "application/octet-stream"
        await _event(session, principal, "immoware.document_downloaded", row.id)

    async def _stream() -> Any:
        try:
            async for chunk in download(client, url):
                yield chunk
        except Exception as exc:
            raise ProblemError(ErrorCodes.IMW_UNAVAILABLE, detail=sanitize_error(str(exc))) from exc
        finally:
            await client.aclose()

    return StreamingResponse(_stream(), media_type=content_type)


@router.get("/contacts", summary="Immoware24-Kontakte")
async def list_contacts(
    request: Request,
    q: str | None = Query(default=None),
    unmatched: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        stmt = select(ImmowareDavContact).where(ImmowareDavContact.deleted_at.is_(None))
        if q:
            stmt = stmt.where(ImmowareDavContact.fn.ilike(f"%{q}%"))
        if unmatched:
            stmt = stmt.where(ImmowareDavContact.matched_contact_id.is_(None))
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        offset, limit = _paginate(page, page_size)
        rows = await session.scalars(
            stmt.order_by(ImmowareDavContact.fn).offset(offset).limit(limit)
        )
        return {
            "data": [s.ImmowareContactOut.model_validate(r) for r in rows],
            "meta": s.Meta(page=page, per_page=page_size, total=total),
        }


@router.post("/contacts/{dav_contact_id}/match", summary="Mit CRM-Kontakt verknuepfen")
async def match_contact(
    dav_contact_id: uuid.UUID,
    body: s.MatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(MANAGE),
) -> s.ImmowareContactOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ImmowareDavContact, dav_contact_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        target = await session.get(Contact, body.contact_id)
        if target is None or target.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kontakt nicht gefunden.")
        row.matched_contact_id = body.contact_id
        await session.flush()
        await _event(
            session, principal, "immoware.contact_matched", row.id, contact_id=str(body.contact_id)
        )
        return s.ImmowareContactOut.model_validate(row)


@router.post(
    "/contacts/{dav_contact_id}/create-contact", status_code=201, summary="Als CRM-Kontakt anlegen"
)
async def create_contact_from_dav(
    dav_contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(MANAGE)
) -> s.ImmowareContactOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(ImmowareDavContact, dav_contact_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.matched_contact_id is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits verknuepft.")
        kind = ContactKind.COMPANY if row.org and not row.fn else ContactKind.PERSON
        display_name = row.fn or row.org or row.href
        contact = Contact(
            tenant_id=principal.tenant_id,
            kind=kind,
            company_name=row.org if kind is ContactKind.COMPANY else None,
            first_name=(
                None if kind is ContactKind.COMPANY else (row.fn or "").split(" ")[0] or None
            ),
            last_name=None
            if kind is ContactKind.COMPANY
            else " ".join((row.fn or "").split(" ")[1:]) or row.fn,
            display_name=display_name,
            external_ids={"immoware24_carddav_href": row.href},
        )
        session.add(contact)
        await session.flush()
        for email in row.emails:
            session.add(
                ContactEmail(tenant_id=principal.tenant_id, contact_id=contact.id, email=email)
            )
        for phone in row.phones:
            session.add(
                ContactPhone(tenant_id=principal.tenant_id, contact_id=contact.id, number=phone)
            )
        row.matched_contact_id = contact.id
        await session.flush()
        await _event(
            session, principal, "immoware.contact_created", row.id, contact_id=str(contact.id)
        )
        return s.ImmowareContactOut.model_validate(row)


@router.get("/events", summary="Immoware24-Termine")
async def list_events(
    request: Request,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        stmt = select(ImmowareDavEvent).where(ImmowareDavEvent.deleted_at.is_(None))
        if from_:
            stmt = stmt.where(ImmowareDavEvent.dtstart >= from_)
        if to:
            stmt = stmt.where(ImmowareDavEvent.dtstart <= to)
        total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        offset, limit = _paginate(page, page_size)
        rows = await session.scalars(
            stmt.order_by(ImmowareDavEvent.dtstart).offset(offset).limit(limit)
        )
        return {
            "data": [s.ImmowareEventOut.model_validate(r) for r in rows],
            "meta": s.Meta(page=page, per_page=page_size, total=total),
        }
