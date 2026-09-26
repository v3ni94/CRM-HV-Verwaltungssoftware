"""M29 Stufe 4 (docs/plans/M29-dms.md): CRM endpoints of the DMS page under
``/api/v1/integrations/objektakte``. The browser never talks to objektakte; these endpoints call
the objektakte read API server side (``mhvp.objektakte.remote``) with the token from the
environment.

* ``GET /status``: whether the connection is configured for the signed in tenant.
* ``GET /objects``, ``GET /objects/{number}``: tiles and detail (status, open review cases,
  completeness, missing documents), each with the CRM property of the same number.
* ``GET /objects/{number}/documents``: one page of the document list, each row with the CRM
  document it is linked to (M6), if any. ``POST .../documents/link``: backfill, links every
  document of the object as a CRM document (same function as the webhook).
* ``GET /objects/{number}/owners``, ``.../tenants``: the lists as objektakte shows them (without
  e-mail and IBAN).
* ``/person-proposals``: owner or tenant list as import proposal (M8 pattern): create = fetch and
  test run, ``test-run`` repeats the reconciliation, ``approve`` or ``reject`` decides. Nothing is
  written into contacts, contracts or units.

Permissions: ``objektakte:read`` for reading; person data needs ``contacts:read`` in addition;
linking documents needs ``documents:create``; a proposal needs ``objektakte:update`` and its
release ``objektakte:approve``. The connection is used only for the tenant named in
``OBJEKTAKTE_TENANT`` (tenant separation: objektakte holds the data of one tenant); for every
other tenant it counts as not configured.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.config import Settings
from mhvp.core.db.tenancy import platform_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import DocumentLink
from mhvp.objektakte import dms_service as svc
from mhvp.objektakte.dms_models import ObjektaktePersonProposal, ObjektakteUpload
from mhvp.objektakte.remote import (
    ObjektakteClient,
    ObjektakteError,
    ObjektakteNotFoundError,
)
from mhvp.platform.models import Tenant, TenantStatus

router = APIRouter(prefix="/integrations/objektakte", tags=["objektakte-dms"])
READ = require_permission("objektakte:read")
UPDATE = require_permission("objektakte:update")
APPROVE = require_permission("objektakte:approve")
DOCUMENTS_CREATE = require_permission("documents:create")

PersonKind = Literal["owners", "tenants"]


def _need(principal: TenantPrincipal, *permissions: str) -> None:
    missing = [p for p in permissions if not principal.has(p)]
    if missing:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message=f"Missing permission {missing}.")


async def configured_tenant_id(request: Request) -> uuid.UUID | None:
    """The active tenant named in ``OBJEKTAKTE_TENANT`` (slug or id), or None."""
    settings: Settings = request.app.state.settings
    key = (settings.objektakte_tenant or "").strip()
    if not key:
        return None
    try:
        tenant_uuid: uuid.UUID | None = uuid.UUID(key)
    except ValueError:
        tenant_uuid = None
    query = select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
    query = (
        query.where(Tenant.id == tenant_uuid) if tenant_uuid else query.where(Tenant.slug == key)
    )
    async with platform_transaction(sessions(request)) as session:
        found: uuid.UUID | None = await session.scalar(query)
    return found


async def _connection_state(request: Request, principal: TenantPrincipal) -> str | None:
    """None when usable, otherwise the reason (``not_configured`` or ``other_tenant``)."""
    settings: Settings = request.app.state.settings
    if not settings.objektakte_api_configured:
        return "not_configured"
    tenant_id = await configured_tenant_id(request)
    if tenant_id is None:
        return "not_configured"
    if tenant_id != principal.tenant_id:
        return "other_tenant"
    return None


async def _client(request: Request, principal: TenantPrincipal) -> ObjektakteClient:
    if await _connection_state(request, principal) is not None:
        raise ProblemError(ErrorCodes.OBJEKTAKTE_NOT_CONFIGURED)
    transport = getattr(request.app.state, "objektakte_transport", None)  # tests: MockTransport
    try:
        return ObjektakteClient.from_settings(request.app.state.settings, transport=transport)
    except ObjektakteError:
        raise ProblemError(ErrorCodes.OBJEKTAKTE_NOT_CONFIGURED) from None


def _upstream(exc: ObjektakteError) -> ProblemError:
    if isinstance(exc, ObjektakteNotFoundError):
        return ProblemError(ErrorCodes.OBJEKTAKTE_OBJECT_NOT_FOUND, detail=str(exc))
    return ProblemError(ErrorCodes.OBJEKTAKTE_UNAVAILABLE, detail=str(exc))


def _object_out(raw: dict[str, Any], properties: dict[str, str]) -> dict[str, Any]:
    number = svc.normalize_number(raw.get("number"))
    return {**raw, "property_id": properties.get(number) if number else None}


@router.get("/status", summary="Anbindung objektakte: eingerichtet für diesen Mandanten?")
async def status(request: Request, principal: TenantPrincipal = Depends(READ)) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    reason = await _connection_state(request, principal)
    secret = settings.objektakte_webhook_secret
    return {
        "configured": reason is None,
        "reason": reason,
        "webhook_configured": bool(reason is None and secret and secret.get_secret_value()),
        "upload_enabled": bool(reason is None and settings.objektakte_upload_active),
    }


@router.get(
    "/documents/{document_id}/filing",
    summary="Ablage eines CRM-Dokuments über objektakte (Drive und Paperless)",
)
async def document_filing(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """State of the upload to objektakte; ``routed`` is false when the document goes the CRM's
    own mirror way (no single property, upload off, other tenant)."""
    async with tenant_tx(request, principal) as session:
        upload = await session.scalar(
            select(ObjektakteUpload).where(ObjektakteUpload.document_id == document_id)
        )
        if upload is None:
            return {"routed": False, "document_id": str(document_id)}
        remote = upload.remote or {}
        return {
            "routed": True,
            "document_id": str(document_id),
            "status": upload.status,
            "object_number": upload.object_number,
            "objektakte_document_id": upload.objektakte_document_id,
            "objektakte_status": remote.get("status"),
            "category": remote.get("category"),
            "subfolder": remote.get("subfolder"),
            "drive_url": remote.get("drive_url"),
            "paperless_id": remote.get("paperless_id"),
            "attempts": upload.attempts,
            "last_error": upload.last_error,
            "done_at": upload.done_at.isoformat() if upload.done_at else None,
        }


@router.get("/objects", summary="Objekte aus objektakte (Kacheln der DMS-Seite)")
async def objects(request: Request, principal: TenantPrincipal = Depends(READ)) -> dict[str, Any]:
    client = await _client(request, principal)
    try:
        async with client:
            rows = await client.objects()
    except ObjektakteError as exc:
        raise _upstream(exc) from None
    async with tenant_tx(request, principal) as session:
        properties = await svc.property_ids_by_number(session, principal.tenant_id)
    items = [_object_out(r, properties) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/objects/{number}", summary="Objekt aus objektakte mit fehlenden Unterlagen")
async def object_detail(
    number: str, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    client = await _client(request, principal)
    try:
        async with client:
            raw = await client.object(number)
    except ObjektakteError as exc:
        raise _upstream(exc) from None
    async with tenant_tx(request, principal) as session:
        properties = await svc.property_ids_by_number(session, principal.tenant_id)
        out = _object_out(raw, properties)
        linked = 0
        if out["property_id"]:
            linked = int(
                await session.scalar(
                    select(func.count(DocumentLink.id)).where(
                        DocumentLink.entity_type == "property",
                        DocumentLink.entity_id == uuid.UUID(out["property_id"]),
                    )
                )
                or 0
            )
    return {**out, "crm_document_count": linked}


@router.get("/objects/{number}/documents", summary="Dokumentliste eines Objekts aus objektakte")
async def object_documents(
    number: str,
    request: Request,
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=100, ge=1, le=500),
    folder: str | None = Query(default=None, max_length=100),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    client = await _client(request, principal)
    try:
        async with client:
            data = await client.documents(number, page=page, page_size=page_size, folder=folder)
    except ObjektakteError as exc:
        raise _upstream(exc) from None
    parsed: list[svc.FiledDocument] = []
    for raw in data["results"]:
        try:
            parsed.append(svc.parse_document(raw))
        except ValueError:
            continue
    async with tenant_tx(request, principal) as session:
        matches = await svc.matching_documents(session, principal.tenant_id, parsed)
    results = []
    for raw in data["results"]:
        ref = raw.get("id") if isinstance(raw, dict) else None
        match = matches.get(ref) if isinstance(ref, int) else None
        results.append({**raw, "crm_document_id": str(match.id) if match else None})
    return {
        "count": data.get("count", len(results)),
        "page": data.get("page", page),
        "page_size": data.get("page_size", page_size),
        "results": results,
    }


@router.post(
    "/objects/{number}/documents/link",
    summary="Alle Dokumente eines Objekts als CRM-Dokumente verknüpfen (Nachholen)",
)
async def link_object_documents(
    number: str, request: Request, principal: TenantPrincipal = Depends(DOCUMENTS_CREATE)
) -> dict[str, Any]:
    _need(principal, "objektakte:read")
    client = await _client(request, principal)
    try:
        async with client:
            rows = await client.all_documents(number)
    except ObjektakteError as exc:
        raise _upstream(exc) from None
    counts = {"created": 0, "linked": 0, "updated": 0, "unchanged": 0, "invalid": 0}
    docs: list[svc.FiledDocument] = []
    for raw in rows:
        try:
            docs.append(svc.parse_document(raw))
        except ValueError:
            counts["invalid"] += 1
    async with tenant_tx(request, principal) as session:
        prop = await svc.property_by_number(session, principal.tenant_id, number)
        matches = await svc.matching_documents(session, principal.tenant_id, docs)
        for doc in docs:
            result = await svc.link_filed_document(
                session,
                principal.tenant_id,
                object_number=number,
                doc=doc,
                actor_user_id=principal.user_id,
                existing=matches.get(doc.id),
            )
            counts[result.outcome] += 1
    return {
        "object_number": number,
        "property_id": str(prop.id) if prop else None,
        "total": len(rows),
        **counts,
    }


def _person_out(kind: str, raw: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "display_name", "unit_labels")
    extra = ("share",) if kind == "owners" else ("lease_start", "lease_end")
    return {k: raw.get(k) for k in keep + extra}


@router.get("/objects/{number}/{kind}", summary="Eigentümer- oder Mieterliste aus objektakte")
async def object_persons(
    number: str, kind: PersonKind, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    _need(principal, "contacts:read")
    client = await _client(request, principal)
    try:
        async with client:
            rows = await (client.owners(number) if kind == "owners" else client.tenants(number))
    except ObjektakteError as exc:
        raise _upstream(exc) from None
    items = [_person_out(kind, r) for r in rows]
    return {"object_number": number, "kind": kind, "items": items, "total": len(items)}


# --- import proposals of the owner and tenant lists (M8 pattern) --------------------------


class PersonProposalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: PersonKind


class PersonProposalDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=2000)


def _proposal_out(row: ObjektaktePersonProposal) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "property_id": str(row.property_id),
        "object_number": row.object_number,
        "kind": row.kind,
        "status": row.status,
        "fetched_at": row.fetched_at.isoformat(),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "created_by": str(row.created_by) if row.created_by else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decided_by": str(row.decided_by) if row.decided_by else None,
        "decision_note": row.decision_note,
        "summary": row.summary,
        "rows": row.rows,
        "writes_master_data": False,
    }


async def _fetch_persons(
    request: Request, principal: TenantPrincipal, number: str, kind: str
) -> list[dict[str, Any]]:
    client = await _client(request, principal)
    try:
        async with client:
            return await (client.owners(number) if kind == "owners" else client.tenants(number))
    except ObjektakteError as exc:
        raise _upstream(exc) from None


async def _proposal(session: AsyncSession, proposal_id: uuid.UUID) -> ObjektaktePersonProposal:
    row = await session.get(ObjektaktePersonProposal, proposal_id)
    if row is None:
        raise ProblemError(ErrorCodes.NOT_FOUND)
    return row


@router.post(
    "/objects/{number}/person-proposals",
    status_code=201,
    summary="Eigentümer- oder Mieterliste als Importvorschlag abrufen (Testlauf mit Abgleich)",
)
async def create_proposal(
    number: str,
    body: PersonProposalIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    _need(principal, "contacts:read")
    async with tenant_tx(request, principal) as session:
        prop = await svc.property_by_number(session, principal.tenant_id, number)
        if prop is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"Objekt {number} ist im CRM nicht angelegt; ein Abgleich ist nicht möglich."
                ),
            )
    remote = await _fetch_persons(request, principal, number, body.kind)
    async with tenant_tx(request, principal) as session:
        prop = await svc.property_by_number(session, principal.tenant_id, number)
        assert prop is not None  # noqa: S101 - checked above within the same tenant
        rows, summary = await svc.reconcile_persons(
            session, principal.tenant_id, prop, body.kind, remote
        )
        proposal = ObjektaktePersonProposal(
            tenant_id=principal.tenant_id,
            property_id=prop.id,
            object_number=prop.number,
            kind=body.kind,
            status="tested",
            fetched_at=svc.now_utc(),
            rows=rows,
            summary=summary,
            created_by=principal.user_id,
        )
        session.add(proposal)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="objektakte.person_proposal_tested",
            entity_type="objektakte_person_proposal",
            entity_id=proposal.id,
            actor_user_id=principal.user_id,
            payload={"kind": body.kind, "object_number": prop.number, "counts": summary["counts"]},
        )
        await session.refresh(proposal)
        return _proposal_out(proposal)


@router.get("/person-proposals", summary="Importvorschläge der Eigentümer- und Mieterlisten")
async def list_proposals(
    request: Request,
    object_number: str | None = Query(default=None, max_length=16),
    status_filter: Literal["tested", "approved", "rejected"] | None = Query(
        default=None, alias="status"
    ),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _need(principal, "contacts:read")
    query = select(ObjektaktePersonProposal).order_by(
        ObjektaktePersonProposal.created_at.desc(), ObjektaktePersonProposal.id.desc()
    )
    if object_number:
        number = svc.normalize_number(object_number) or object_number
        query = query.where(ObjektaktePersonProposal.object_number == number)
    if status_filter:
        query = query.where(ObjektaktePersonProposal.status == status_filter)
    async with tenant_tx(request, principal) as session:
        rows = (await session.scalars(query.limit(200))).all()
        items = [{k: v for k, v in _proposal_out(r).items() if k != "rows"} for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/person-proposals/{proposal_id}", summary="Importvorschlag mit Abgleich")
async def get_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    _need(principal, "contacts:read")
    async with tenant_tx(request, principal) as session:
        return _proposal_out(await _proposal(session, proposal_id))


@router.post(
    "/person-proposals/{proposal_id}/test-run",
    summary="Testlauf wiederholen (neu abrufen und abgleichen)",
)
async def rerun_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> dict[str, Any]:
    _need(principal, "contacts:read")
    async with tenant_tx(request, principal) as session:
        row = await _proposal(session, proposal_id)
        if row.status != "tested":
            raise ProblemError(ErrorCodes.OBJEKTAKTE_PROPOSAL_STATE)
        number, kind = row.object_number, row.kind
    remote = await _fetch_persons(request, principal, number, kind)
    async with tenant_tx(request, principal) as session:
        row = await _proposal(session, proposal_id)
        if row.status != "tested":
            raise ProblemError(ErrorCodes.OBJEKTAKTE_PROPOSAL_STATE)
        prop = await svc.property_by_number(session, principal.tenant_id, number)
        if prop is None:
            raise ProblemError(ErrorCodes.NOT_FOUND)
        rows, summary = await svc.reconcile_persons(
            session, principal.tenant_id, prop, kind, remote
        )
        row.rows, row.summary, row.fetched_at = rows, summary, svc.now_utc()
        row.updated_by = principal.user_id
        await session.flush()
        await session.refresh(row)
        return _proposal_out(row)


async def _decide(
    request: Request,
    principal: TenantPrincipal,
    proposal_id: uuid.UUID,
    status_value: str,
    note: str | None,
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _proposal(session, proposal_id)
        if row.status != "tested":
            raise ProblemError(ErrorCodes.OBJEKTAKTE_PROPOSAL_STATE)
        row.status = status_value
        row.decided_at = svc.now_utc()
        row.decided_by = principal.user_id
        row.decision_note = note
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"objektakte.person_proposal_{status_value}",
            entity_type="objektakte_person_proposal",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"kind": row.kind, "object_number": row.object_number},
        )
        await session.refresh(row)
        return _proposal_out(row)


@router.post(
    "/person-proposals/{proposal_id}/approve",
    summary="Importvorschlag freigeben (Abgleich als Arbeitsgrundlage, schreibt keine Stammdaten)",
)
async def approve_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    body: PersonProposalDecisionIn | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    _need(principal, "contacts:read")
    return await _decide(request, principal, proposal_id, "approved", body.note if body else None)


@router.post("/person-proposals/{proposal_id}/reject", summary="Importvorschlag verwerfen")
async def reject_proposal(
    proposal_id: uuid.UUID,
    request: Request,
    body: PersonProposalDecisionIn | None = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    _need(principal, "contacts:read")
    return await _decide(request, principal, proposal_id, "rejected", body.note if body else None)
