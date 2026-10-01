"""Document endpoints (/api/v1/documents, categories, retention, DMS, templates, letters)."""

import html
import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import session_allowed_legal_entity_ids, session_allowed_property_ids
from mhvp.core.escaping import content_disposition
from mhvp.core.etag import check_if_match, etag_of
from mhvp.core.events import emit
from mhvp.core.listparams import (
    LIST_PARAMS_DOC,
    ListParams,
    apply_filters,
    apply_sort,
    check_include,
    embed,
    list_params,
    strict_query,
)
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters, mirror_deletion, retention, trash
from mhvp.documents import schemas as s
from mhvp.documents import services as svc
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    DeletionProposal,
    DeletionProposalItem,
    DeletionProposalStatus,
    DmsConnection,
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentMirror,
    DocumentMirrorDeletion,
    DocumentSource,
    DocumentTemplate,
    GeneratedDocument,
    LinkRole,
    MirrorDeletionStatus,
    MirrorStatus,
    RetentionProfile,
    StorageKind,
)
from mhvp.documents.paperless_search import (
    COMPANY_OPTIONS_KEY,
    PaperlessDocument,
    PaperlessSearch,
    PaperlessSearchError,
    format_company_options,
    parse_company_options,
    parse_field_id,
)
from mhvp.handover import images
from mhvp.tickets.models import Ticket

router = APIRouter(tags=["Dokumente"])
READ = require_permission("documents:read")
CREATE = require_permission("documents:create")
UPDATE = require_permission("documents:update")
DELETE = require_permission("documents:delete")
APPROVE = require_permission("documents:approve")
SETTINGS = require_permission("tenant_settings:update")
SETTINGS_READ = require_permission("tenant_settings:read")
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]
_LINKS = TypeAdapter(list[s.LinkIn])
_LOCAL = ZoneInfo("Europe/Berlin")  # letter date only; deadline time zone is open (M1-09)


def _today() -> date:
    return datetime.now(_LOCAL).date()


def _blobs(request: Request) -> BlobStore:
    return BlobStore(request.app.state.settings)


def _draft_marker() -> Any:
    """SQL expression of the draft flag: ``source_meta->>'is_draft'`` as boolean, missing
    key or missing metadata counts as not a draft."""
    return func.coalesce(Document.source_meta["is_draft"].as_boolean(), False)


def _scope_filter(session: Any) -> Any:
    """A37 (docs/rules/M18-05-steuerberaterzugang.md): for a scoped membership (tax advisor)
    only documents linked to one of its legal entities exist; returns the subquery of allowed
    document ids or ``None`` when the principal is not restricted."""
    allowed = session_allowed_legal_entity_ids(session)
    if allowed is None:
        return None
    return select(DocumentLink.document_id).where(
        DocumentLink.entity_type == "legal_entity", DocumentLink.entity_id.in_(list(allowed))
    )


def _property_scope_filter(session: Any) -> Any:
    """M2-02/S16-02 (docs/rules/M2-02-objektzuordnung.md): for a membership with a property
    assignment only documents linked to an assigned property, or to a unit, contract or ticket
    of one, exist; returns the subquery of allowed document ids or ``None`` when unrestricted."""
    allowed = session_allowed_property_ids(session)
    if allowed is None:
        return None
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Unit

    ids = list(allowed)
    return select(DocumentLink.document_id).where(
        or_(
            (DocumentLink.entity_type == "property") & DocumentLink.entity_id.in_(ids),
            (DocumentLink.entity_type == "unit")
            & DocumentLink.entity_id.in_(select(Unit.id).where(Unit.property_id.in_(ids))),
            (DocumentLink.entity_type == "contract")
            & DocumentLink.entity_id.in_(select(Contract.id).where(Contract.property_id.in_(ids))),
            (DocumentLink.entity_type == "ticket")
            & DocumentLink.entity_id.in_(select(Ticket.id).where(Ticket.property_id.in_(ids))),
        )
    )


async def _document_property_refs(
    session: Any, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Q12 include=properties: properties of the links (property, unit, contract, ticket),
    within the property assignment (M2-02)."""
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Unit
    from mhvp.properties.refs import property_refs

    if not document_ids:
        return {}
    links = (
        await session.execute(
            select(
                DocumentLink.document_id, DocumentLink.entity_type, DocumentLink.entity_id
            ).where(
                DocumentLink.document_id.in_(document_ids),
                DocumentLink.entity_type.in_(("property", "unit", "contract", "ticket")),
            )
        )
    ).all()
    resolve: dict[str, dict[uuid.UUID, uuid.UUID]] = {}
    for kind, model in (("unit", Unit), ("contract", Contract), ("ticket", Ticket)):
        ids = {e for _, t, e in links if t == kind}
        if ids:
            rows = await session.execute(
                select(model.id, model.property_id).where(model.id.in_(ids))
            )
            resolve[kind] = {i: p for i, p in rows.all() if p is not None}
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for doc_id, kind, entity_id in links:
        prop_id = entity_id if kind == "property" else resolve.get(kind, {}).get(entity_id)
        if prop_id is not None:
            pairs.add((doc_id, prop_id))
    refs = await property_refs(session, {p for _, p in pairs})
    out: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for doc_id, prop_id in pairs:
        if prop_id in refs:
            out.setdefault(doc_id, []).append(refs[prop_id])
    for value in out.values():
        value.sort(key=lambda r: r["number"])
    return out


async def _get(session: Any, model: Any, entity_id: uuid.UUID, *, lock: bool = False) -> Any:
    # AC01-01: lock=True loads FOR UPDATE before an If-Match comparison.
    row = await session.get(model, entity_id, with_for_update=True if lock else None)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if model is Document:
        for scoped in (_scope_filter(session), _property_scope_filter(session)):
            if scoped is None:
                continue
            visible = await session.scalar(
                select(Document.id).where(Document.id == entity_id, Document.id.in_(scoped))
            )
            if visible is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _flush(session: Any, message: str) -> None:
    try:
        await session.flush()
    except IntegrityError:
        raise ProblemError(ErrorCodes.CONFLICT, detail=message) from None


async def _event(
    session: Any, principal: TenantPrincipal, type_: str, entity_id: uuid.UUID, **payload: Any
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type=type_.split(".")[0],
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload={k: v if isinstance(v, int | bool | None) else str(v) for k, v in payload.items()},
    )


async def _out(session: Any, document: Document) -> s.DocumentOut:
    await session.flush()
    await session.refresh(document)
    out = s.DocumentOut.model_validate(document)
    out.links = [
        s.LinkOut.model_validate(x)
        for x in (
            await session.scalars(
                select(DocumentLink)
                .where(DocumentLink.document_id == document.id)
                .order_by(DocumentLink.created_at)
            )
        ).all()
    ]
    out.mirrors = [
        s.MirrorOut.model_validate(m)
        for m in (
            await session.scalars(
                select(DocumentMirror).where(DocumentMirror.document_id == document.id)
            )
        ).all()
    ]
    out.duplicate_of = list(
        (
            await session.scalars(
                select(Document.id).where(
                    Document.sha256 == document.sha256, Document.id != document.id
                )
            )
        ).all()
    )
    return out


# Documents -----------------------------------------------------------------------------


@router.post("/documents", status_code=201, summary="Dokument hochladen")
async def upload(
    request: Request,
    file: UploadFile = File(),
    title: str | None = Form(default=None, max_length=300),
    category_id: uuid.UUID | None = Form(default=None),
    links: str | None = Form(
        default=None, description="JSON-Liste aus entity_type, entity_id, role"
    ),
    principal: TenantPrincipal = Depends(CREATE),
) -> s.DocumentOut:
    limit = request.app.state.settings.document_max_bytes
    data = await file.read(limit + 1)
    mime = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    svc.check_upload(mime, data, limit)
    if images.supports(mime):
        # Photos lose metadata (EXIF, GPS, camera) and are scaled before they are stored, for
        # every module that uploads through this endpoint (M30-04, operator 27.09.2026). An
        # undecodable pseudo image carries no readable metadata and is stored as uploaded.
        try:
            data = images.sanitize_image(
                data, mime, max_edge=request.app.state.settings.handover_image_max_edge
            )
            mime = images.output_mime_type(mime)
        except images.ImageSanitizeError:
            pass
    try:
        link_items = _LINKS.validate_json(links) if links else []
    except ValidationError as exc:
        raise svc.invalid(f"links ungültig: {exc.errors()[0]['msg']}") from None
    # ``store_document`` normalises the name again (path parts, control characters, NFC,
    # length); this call keeps the naive fallback so ``title`` defaults to something readable
    # even before the full sanitisation runs.
    filename = (file.filename or "upload").replace("/", "_").replace("\\", "_")
    async with tenant_tx(request, principal) as session:
        if category_id is not None:
            await _get(session, DocumentCategory, category_id)
        document = await svc.store_document(
            session,
            _blobs(request),
            tenant_id=principal.tenant_id,
            data=data,
            title=title or filename,
            filename=filename,
            mime_type=mime,
            source=DocumentSource.UPLOAD,
            category_id=category_id,
            links=[(x.entity_type, x.entity_id, x.role) for x in link_items],
            created_by=principal.user_id,
            settings=request.app.state.settings,
        )
        await _event(session, principal, "document.created", document.id, size=document.size)
        return await _out(session, document)


_DOCUMENT_FILTERS = {
    "category_id": Document.category_id,
    "mime_type": Document.mime_type,
    "source": Document.source,
    "storage": Document.storage,
    "text_status": Document.text_status,
    "retention_profile_id": Document.retention_profile_id,
    "created_by": Document.created_by,
    "source_system": Document.source_system,
}
_DOCUMENT_SORT = {
    "created_at": Document.created_at,
    "updated_at": Document.updated_at,
    "title": Document.title,
    "filename": Document.filename,
    "size": Document.size,
    "retention_until": Document.retention_until,
}


@router.get(
    "/documents",
    summary="Dokumente suchen (Volltext)",
    response_model=s.DocumentPage,
    description=LIST_PARAMS_DOC
    + " include: properties (Objekte über Verknüpfung mit Objekt, Einheit, Vertrag, Ticket).",
    dependencies=[Depends(strict_query)],
)
async def list_documents(
    request: Request,
    q: str | None = Query(default=None, min_length=2, max_length=200),
    entity_type: str | None = Query(default=None, max_length=63),
    entity_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    is_draft: bool | None = Query(
        default=None,
        description="true: nur Entwürfe (z. B. automatisch erzeugte Briefe), false: ohne "
        "Entwürfe, leer: kein Filter",
    ),
    page: Page = 1,
    page_size: PageSize = 50,
    params: ListParams = Depends(list_params),
    principal: TenantPrincipal = Depends(READ),
) -> Any:
    includes = check_include(params, ("properties",))
    async with tenant_tx(request, principal) as session:
        query = apply_filters(select(Document), params, _DOCUMENT_FILTERS)
        if is_draft is not None:
            # A83: a draft is marked with ``source_meta["is_draft"] = true`` (automation letters).
            query = query.where(_draft_marker() == is_draft)
        snippet: Any = None
        if q:
            ts = func.websearch_to_tsquery("german", q)
            query = query.where(
                or_(Document.search_vector.op("@@")(ts), Document.title.ilike(f"%{q.strip()}%"))
            )
            snippet = func.ts_headline(
                "german",
                func.coalesce(Document.ocr_text, Document.title),
                ts,
                "MaxWords=20, MinWords=5, StartSel=<<, StopSel=>>",
            )
        if entity_type or entity_id:
            link = select(DocumentLink.document_id)
            if entity_type:
                link = link.where(DocumentLink.entity_type == entity_type)
            if entity_id:
                link = link.where(DocumentLink.entity_id == entity_id)
            query = query.where(Document.id.in_(link))
        if category_id:
            query = query.where(Document.category_id == category_id)
        scoped = _scope_filter(session)  # A37: legal entity scope of the membership
        if scoped is not None:
            query = query.where(Document.id.in_(scoped))
        property_scoped = _property_scope_filter(session)  # M2-02/S16-02
        if property_scoped is not None:
            query = query.where(Document.id.in_(property_scoped))
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        columns: list[Any] = [Document] + (
            [snippet.label("snippet")] if snippet is not None else []
        )
        rows = (
            await session.execute(
                apply_sort(
                    query.with_only_columns(*columns),
                    params,
                    _DOCUMENT_SORT,
                    (Document.created_at.desc(), Document.id),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = []
        for row in rows:
            hit = s.DocumentHit.model_validate(row[0])
            hit.is_draft = bool((row[0].source_meta or {}).get("is_draft"))
            hit.snippet = row[1] if len(row) > 1 else None
            items.append(hit)
        embedded: dict[str, Any] = {}
        if "properties" in includes:
            by_doc = await _document_property_refs(session, [row[0].id for row in rows])
            embedded["properties"] = lambda item: by_doc.get(uuid.UUID(item["id"]), [])
        return embed(
            s.DocumentPage(items=items, total=total, page=page, page_size=page_size),
            params,
            s.DocumentHit,
            embedded,
        )


def _deletions(rows: list[DocumentMirrorDeletion]) -> list[s.DocumentDeletionOut]:
    by_document: dict[uuid.UUID, list[DocumentMirrorDeletion]] = {}
    for row in rows:
        by_document.setdefault(row.document_id, []).append(row)
    out: list[s.DocumentDeletionOut] = []
    for document_id, steps in by_document.items():
        open_steps = [x for x in steps if x.status is MirrorDeletionStatus.OPEN]
        out.append(
            s.DocumentDeletionOut(
                document_id=document_id,
                status=MirrorDeletionStatus.OPEN if open_steps else MirrorDeletionStatus.DONE,
                requested_at=min(x.requested_at for x in steps),
                requested_by=steps[0].requested_by,
                steps=[s.MirrorDeletionStepOut.model_validate(x) for x in steps],
            )
        )
    return out


@router.get(
    "/documents/deletions",
    summary="Löschungen mit Spiegelschritten",
    dependencies=[Depends(strict_query)],
)
async def list_deletions(
    request: Request,
    status: MirrorDeletionStatus | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.DocumentDeletionOut]:
    """Platform deletions with their mirror steps (Drive delete, Paperless tag "gelöscht",
    M6-03). A deletion is ``open`` ("offen") until every step is done."""
    async with tenant_tx(request, principal) as session:
        rows = list(
            await session.scalars(
                select(DocumentMirrorDeletion).order_by(
                    DocumentMirrorDeletion.requested_at.desc(), DocumentMirrorDeletion.kind
                )
            )
        )
    deletions = _deletions(rows)
    if status is not None:
        deletions = [d for d in deletions if d.status is status]
    return deletions


@router.post(
    "/documents/deletions/{document_id}/retry", summary="Offene Spiegelschritte erneut anstoßen"
)
async def retry_deletion(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> s.DocumentDeletionOut:
    """Re-queues the open mirror steps of a deletion with the standard retry ladder."""
    async with tenant_tx(request, principal) as session:
        rows = list(
            await session.scalars(
                select(DocumentMirrorDeletion)
                .where(DocumentMirrorDeletion.document_id == document_id)
                .order_by(DocumentMirrorDeletion.kind)
            )
        )
        if not rows:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        jobs = [
            mirror_deletion.MirrorDeletionJob.from_step(x)
            for x in rows
            if x.status is MirrorDeletionStatus.OPEN
        ]
        for job in jobs:
            await _event(
                session,
                principal,
                "document.mirror_delete_requested",
                document_id,
                mirror=job.kind,
                external_ref=job.external_ref,
                retry=True,
            )
    mirror_deletion.enqueue(jobs)
    return _deletions(rows)[0]


def _checklist_out(item: Any, queued: int = 0) -> s.DocumentDeletionChecklistOut:
    return s.DocumentDeletionChecklistOut(
        document_id=item.document_id,
        deleted_at=item.deleted_at,
        status=item.status,
        items=[
            s.DocumentDeletionChecklistItemOut(target=i.target, status=i.status, detail=i.detail)
            for i in item.items
        ],
        mirror_jobs_queued=queued,
        purge_at=item.purge_at,
    )


@router.get(
    "/documents/deletions/{document_id}/checklist",
    summary="Löschcheckliste je Ziel (Index, Original, Spiegel, Ableitungen, AC07)",
    dependencies=[Depends(strict_query)],
)
async def deletion_checklist(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.DocumentDeletionChecklistOut:
    from mhvp.documents import deletion_checklist as checklist

    async with tenant_tx(request, principal) as session:
        item = await checklist.build(session, document_id, _blobs(request), _today())
        if item is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _checklist_out(item)


@router.post(
    "/documents/deletions/{document_id}/follow-up",
    summary="Nachlauf der Löschung: offene Ziele erneut bearbeiten (AC07)",
)
async def deletion_follow_up(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> s.DocumentDeletionChecklistOut:
    """Never deletes a document that exists again (restore): that is the replay path with its
    hold and hash checks; a retention hold always wins."""
    from mhvp.documents import deletion_checklist as checklist

    async with tenant_tx(request, principal) as session:
        item = await checklist.follow_up(
            session,
            tenant_id=principal.tenant_id,
            document_id=document_id,
            blobs=_blobs(request),
            actor_user_id=principal.user_id,
        )
        if item is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    queued = mirror_deletion.enqueue(item.jobs)
    return _checklist_out(item, queued)


# Trash (AE33, AC07-03) ------------------------------------------------------------------------


def _scope_conditions(session: Any) -> list[Any]:
    """Document scope of the membership (tax advisor, property assignment) as conditions."""
    return [
        Document.id.in_(scoped)
        for scoped in (_scope_filter(session), _property_scope_filter(session))
        if scoped is not None
    ]


async def _get_trashed(session: Any, document_id: uuid.UUID) -> Document:
    """A document in the trash, within the scope of the membership; 404 otherwise."""
    with trash.trashed_visible(session):
        document = await _get(session, Document, document_id)
    if document.deleted_at is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return document  # type: ignore[no-any-return]


def _trash_settings_out(enabled: bool, days: int) -> s.DocumentTrashSettingsOut:
    return s.DocumentTrashSettingsOut(
        enabled=enabled, retention_days=days, proposed_days=trash.PROPOSED_DAYS
    )


@router.get(
    "/documents/trash-settings",
    summary="Papierkorb: Schalter und Frist des Mandanten",
    dependencies=[Depends(strict_query)],
)
async def get_trash_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> s.DocumentTrashSettingsOut:
    async with tenant_tx(request, principal) as session:
        return _trash_settings_out(*await trash.current(session))


@router.put("/documents/trash-settings", summary="Papierkorb: Schalter und Frist setzen")
async def put_trash_settings(
    body: s.DocumentTrashSettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> s.DocumentTrashSettingsOut:
    """Off by default. The period is a proposal (30 days) and stays open for decision
    (OPEN_QUESTIONS AE33-01); changing it affects documents trashed afterwards only."""
    async with tenant_tx(request, principal) as session:
        row = await trash.setting_of(session, principal.tenant_id)
        before = {"enabled": row.enabled, "retention_days": row.retention_days}
        row.enabled, row.retention_days = body.enabled, body.retention_days
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="document_trash_setting.updated",
            entity_type="document_trash_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "before": before,
                "after": {"enabled": row.enabled, "retention_days": row.retention_days},
            },
        )
        return _trash_settings_out(row.enabled, row.retention_days)


@router.get(
    "/documents/trash",
    summary="Papierkorb: gelöschte Dokumente mit Fristende und Sperren",
    dependencies=[Depends(strict_query)],
)
async def list_trash(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    principal: TenantPrincipal = Depends(DELETE),
) -> list[s.DocumentTrashEntryOut]:
    async with tenant_tx(request, principal) as session:
        rows = await trash.entries(
            session, today=_today(), scope_filters=_scope_conditions(session), limit=limit
        )
        return [
            s.DocumentTrashEntryOut(
                document_id=r.document.id,
                title=r.document.title,
                filename=r.document.filename,
                category_id=r.document.category_id,
                deleted_at=r.document.deleted_at,
                deleted_by=r.document.deleted_by,
                purge_at=r.document.purge_at,
                days_left=r.days_left,
                status=r.status,
                blocker=r.blocker,
            )
            for r in rows
            if r.document.deleted_at is not None and r.document.purge_at is not None
        ]


@router.post(
    "/documents/trash/{document_id}/restore",
    summary="Dokument aus dem Papierkorb wiederherstellen (protokolliert)",
)
async def restore_from_trash(
    document_id: uuid.UUID,
    body: s.DocumentTrashActionIn,
    request: Request,
    principal: TenantPrincipal = Depends(DELETE),
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get_trashed(session, document_id)
        await trash.restore(
            session,
            document,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            reason=body.reason,
        )
        return await _out(session, document)


@router.post(
    "/documents/trash/{document_id}/purge",
    status_code=204,
    summary="Dokument aus dem Papierkorb endgültig löschen (vor Fristende, protokolliert)",
)
async def purge_from_trash(
    document_id: uuid.UUID,
    body: s.DocumentTrashActionIn,
    request: Request,
    principal: TenantPrincipal = Depends(DELETE),
) -> Response:
    """Every retention check runs again; a hold or a rule answers 409 and the refusal is
    logged. The mirror steps (Drive, Paperless) are journaled and queued like any deletion."""
    async with tenant_tx(request, principal) as session:
        document = await _get_trashed(session, document_id)
        result = await trash.purge(
            session,
            _blobs(request),
            document,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
            today=_today(),
            reason=body.reason,
            early=True,
        )
    if not result.deleted:
        raise ProblemError(ErrorCodes.RETENTION_LOCKED, detail=result.reason)
    mirror_deletion.enqueue(result.jobs)
    return Response(status_code=204)


@router.get("/documents/{document_id}", summary="Dokument lesen")
async def get_document(
    document_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        response.headers["ETag"] = etag_of(document.updated_at)  # S12-04
        return await _out(session, document)


@router.get(
    "/documents/{document_id}/portal-read-receipts",
    summary="Portalzugriffe (Indiz, keine Zustellung)",
)
async def read_receipts(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Portal read receipts of a document (11.3, D34, A53): who opened or downloaded it
    through the portal and when. An indication only, kept apart from dispatch evidence
    (``mhvp.communication``) and from any receipt date; it changes no delivery status."""
    from mhvp.portal import read_receipts as receipts

    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        return {
            "document_id": document.id,
            "note": receipts.LEGAL_NOTE,
            "items": await receipts.for_document(session, document.id),
        }


@router.get(
    "/documents/{document_id}/read-receipts",
    summary="Portalzugriffe (alter Pfad, gleich /portal-read-receipts)",
)
async def read_receipts_legacy(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Alias of the published path (1.21.0); same answer as ``/portal-read-receipts``. A
    formal deprecation mark follows with ADR 0009 once that is in place."""
    return await read_receipts(document_id, request, principal)


@router.get(
    "/documents/{document_id}/content",
    summary="Original herunterladen",
    response_class=Response,
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def download(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        if document.storage is StorageKind.GOOGLE_DRIVE:
            # M35 takeover documents: no local copy, `storage_ref` is the Drive file id (the
            # same convention `mhvp.documents.dms.GoogleDriveStore.put`/`resolve` use for a
            # mirrored document's `external_ref`).
            data = await svc.download_from_drive(session, request, document)
        else:
            data = _blobs(request).get(document.storage_ref)
        await _event(session, principal, "document.downloaded", document.id)
    return Response(
        content=data,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": content_disposition("attachment", document.filename),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


async def _ensure_resolution_of_document(session: Any, document: Any, resolution: Any) -> None:
    """Review W79 (U11-01): the resolution that starts the retention period belongs to the
    community of the document, i.e. to a legal entity linked to the document directly or
    through a linked property. Outside the legal entity or property scope of the membership the
    resolution does not exist (404); a resolution of another community is refused (422), it
    would move the deletion date of a record it does not concern."""
    from mhvp.core.auth.scope import (
        ensure_session_legal_entity_allowed,
        ensure_session_property_allowed,
    )
    from mhvp.properties.models import LegalEntity

    entity = await session.get(LegalEntity, resolution.legal_entity_id)
    ensure_session_legal_entity_allowed(session, resolution.legal_entity_id)
    if session_allowed_property_ids(session) is not None:
        ensure_session_property_allowed(session, entity.property_id if entity else None)
    links = (
        await session.execute(
            select(DocumentLink.entity_type, DocumentLink.entity_id).where(
                DocumentLink.document_id == document.id,
                DocumentLink.entity_type.in_(("legal_entity", "property")),
            )
        )
    ).all()
    entity_ids = {eid for kind, eid in links if kind == "legal_entity"}
    property_ids = {eid for kind, eid in links if kind == "property"}
    if resolution.legal_entity_id in entity_ids or (
        entity is not None and entity.property_id in property_ids
    ):
        return
    raise svc.invalid(
        "Der Beschluss gehört nicht zur Gemeinschaft des Dokuments "
        "(Verknüpfung mit Rechtsträger oder Objekt fehlt)."
    )


@router.patch("/documents/{document_id}", summary="Metadaten ändern")
async def patch_document(
    document_id: uuid.UUID,
    body: s.DocumentPatch,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id, lock=True)
        check_if_match(if_match, document.updated_at)
        changes = body.model_dump(exclude_unset=True)
        if "permanent_record" in changes:
            # S711-06: the permanent record flag is only ever cleared with documents:approve.
            if changes["permanent_record"] is None:
                raise svc.invalid("permanent_record ist true oder false.")
            if (
                document.permanent_record
                and not changes["permanent_record"]
                and not principal.has("documents:approve")
            ):
                raise ProblemError(
                    ErrorCodes.FORBIDDEN,
                    detail="Die Kennzeichnung als Dauerunterlage hebt nur die Freigabe auf.",
                )
        if changes.get("category_id"):
            await _get(session, DocumentCategory, changes["category_id"])
        if changes.get("retention_profile_id"):
            await _get(session, RetentionProfile, changes["retention_profile_id"])
        if changes.get("retention_resolution_id"):
            from mhvp.hoa.models import Resolution

            resolution = await _get(session, Resolution, changes["retention_resolution_id"])
            await _ensure_resolution_of_document(session, document, resolution)
        before_roles = set(document.visibility or []) - {"internal"}
        for key, value in changes.items():
            setattr(document, key, value)
        # Retention matrix (M6-04): a new category takes the mapped profile, a new profile or
        # base date recomputes the period; an explicit retention_until stays as given.
        if "retention_until" not in changes:
            profile: RetentionProfile | None = None
            if "retention_profile_id" in changes and document.retention_profile_id:
                profile = await session.get(RetentionProfile, document.retention_profile_id)
            elif "category_id" in changes:
                profile = await retention.profile_for_category(session, document.category_id)
            elif (
                "retention_base_on" in changes or "retention_resolution_id" in changes
            ) and document.retention_profile_id:
                profile = await session.get(RetentionProfile, document.retention_profile_id)
            if profile is not None:
                await retention.assign_profile(session, document, profile)
        await _event(session, principal, "document.updated", document.id, fields=sorted(changes))
        added_roles = sorted(set(document.visibility or []) - {"internal"} - before_roles)
        if "visibility" in changes and added_roles:
            # S12-01: newly released for portal roles (tenant, owner, provider, board).
            await _event(
                session, principal, "document.shared", document.id, roles=",".join(added_roles)
            )
        await svc.mark_mirrors_dirty(session, document.id)
        await session.flush()
        await session.refresh(document, ["updated_at"])
        response.headers["ETag"] = etag_of(document.updated_at)
        return await _out(session, document)


@router.post("/documents/{document_id}/links", status_code=201, summary="Verknüpfen")
async def add_link(
    document_id: uuid.UUID,
    body: s.LinkIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        await svc.check_link_target(session, body.entity_type, body.entity_id)
        session.add(
            DocumentLink(
                tenant_id=principal.tenant_id, document_id=document.id, **body.model_dump()
            )
        )
        await _flush(session, "Die Verknüpfung besteht bereits.")
        await _event(
            session,
            principal,
            "document.linked",
            document.id,
            target_type=body.entity_type,
            target_id=body.entity_id,
        )
        await svc.mark_mirrors_dirty(session, document.id)
        return await _out(session, document)


@router.delete("/documents/{document_id}/links/{link_id}", summary="Verknüpfung lösen")
async def remove_link(
    document_id: uuid.UUID,
    link_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        link = await _get(session, DocumentLink, link_id)
        if link.document_id != document.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if link.role in (LinkRole.ORIGINAL, LinkRole.EVIDENCE, LinkRole.GENERATED):
            raise svc.invalid("Original-, Nachweis- und Erzeugungsbezüge bleiben erhalten.")
        await session.delete(link)
        await _event(session, principal, "document.unlinked", document.id, link=link_id)
        return await _out(session, document)


@router.post("/documents/{document_id}/hold", summary="Löschungssperre setzen")
async def set_hold(
    document_id: uuid.UUID,
    body: s.HoldIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        if document.retention_hold_reason is not None:
            # V11-07: an active hold is never overwritten (reason, kind and the person counted
            # for the four eyes check stay); it is lifted first by a second person.
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=(
                    "Es besteht bereits eine Löschungssperre; "
                    "sie wird zuerst von einer zweiten Person aufgehoben."
                ),
            )
        document.retention_hold_reason = body.reason
        document.retention_hold_kind = body.kind or "other"
        await _event(
            session,
            principal,
            "document.hold_set",
            document.id,
            reason=body.reason,
            kind=document.retention_hold_kind,
        )
        return await _out(session, document)


@router.delete("/documents/{document_id}/hold", summary="Löschungssperre aufheben")
async def clear_hold(
    document_id: uuid.UUID,
    body: s.HoldIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        if document.retention_hold_reason is not None:
            await retention.require_second_person(
                session,
                event_type="document.hold_set",
                entity_id=document.id,
                user_id=principal.user_id,
            )
        previous = document.retention_hold_reason
        document.retention_hold_reason = None
        document.retention_hold_kind = None
        await _event(
            session,
            principal,
            "document.hold_cleared",
            document.id,
            reason=body.reason,
            previous=previous,
        )
        return await _out(session, document)


@router.get("/documents/{document_id}/retention-status", summary="Aufbewahrungs- und Sperrstatus")
async def retention_status(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.DocumentRetentionStatusOut:
    """Why the document is kept today (S711-06): manual hold, automatic procedure hold,
    WEG permanent record or period; ``deletion_blocker`` None means deletable."""
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        today = datetime.now(UTC).date()
        return s.DocumentRetentionStatusOut(
            document_id=document.id,
            retention_until=document.retention_until,
            retention_hold_reason=document.retention_hold_reason,
            retention_hold_kind=document.retention_hold_kind,
            procedure_hold=await retention.procedure_hold(session, document.id),
            ticket_hold=await retention.ticket_hold(session, document.id),
            permanent_record=document.permanent_record,
            deletion_blocker=await svc.deletion_blocker(session, document, today),
            retention_resolution_id=document.retention_resolution_id,
            hold_set_by_four_eyes_required=document.retention_hold_reason is not None,
        )


@router.delete("/documents/{document_id}", status_code=204, summary="Dokument löschen")
async def delete_document(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> Response:
    """Only after a released retention profile expired and without a hold (6.9.5, D46)."""
    # The refusal is logged in its own transaction: raising inside the transaction would roll
    # the event back with it, and D46 requires the refusal to be recorded.
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        blocker = await svc.deletion_blocker(session, document, _today())
        if blocker is not None:
            await _event(
                session, principal, "document.deletion_refused", document.id, reason=blocker
            )
    if blocker is not None:
        raise ProblemError(ErrorCodes.RETENTION_LOCKED, detail=blocker)
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        blocker = await svc.deletion_blocker(session, document, _today())
        if blocker is not None:  # changed in between
            raise ProblemError(ErrorCodes.RETENTION_LOCKED, detail=blocker)
        # A43 (6.9.5, M6-03, operator decision 26.09.2026): the Drive copy is deleted and the
        # Paperless document tagged "gelöscht" by a logged job after this deletion; the steps
        # are journaled in the same transaction, and the deletion stays "offen" until every
        # step succeeded (GET /documents/deletions). Shared with the proposal run (M6-04).
        # AE33 (AC07-03): with the tenant switch for the trash on, the document moves to the
        # trash first (restorable, final deletion after the period); without it this is final.
        deleted = await retention.dispose(
            session,
            _blobs(request),
            document,
            tenant_id=principal.tenant_id,
            actor_user_id=principal.user_id,
        )
    mirror_deletion.enqueue(deleted.jobs)
    return Response(status_code=204)


@router.post("/documents/{document_id}/mirror", summary="Spiegelung erneut anstoßen")
async def remirror(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        from mhvp.objektakte import upload as objektakte_upload  # local: avoids an import cycle

        await objektakte_upload.reset_failed(session, document.id)
        await svc.queue_mirrors(session, principal.tenant_id, document.id)
        for m in (
            await session.scalars(
                select(DocumentMirror).where(
                    DocumentMirror.document_id == document.id,
                    DocumentMirror.status == MirrorStatus.FAILED,
                )
            )
        ).all():
            m.status, m.next_attempt_at, m.last_error = (
                MirrorStatus.PENDING,
                datetime.now(UTC),
                None,
            )
        return await _out(session, document)


# Categories, retention profiles ----------------------------------------------------------


@router.get(
    "/document-categories", summary="Dokumentkategorien", dependencies=[Depends(strict_query)]
)
async def list_categories(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.CategoryOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(DocumentCategory).order_by(
                    DocumentCategory.sort_order, DocumentCategory.name
                )
            )
        ).all()
        return [s.CategoryOut.model_validate(r) for r in rows]


@router.get(
    "/document-folders",
    summary="Ordnerstruktur der Objektakte",
    dependencies=[Depends(strict_query)],
)
async def list_document_folders(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    """Package F (handbook Objektordner): the six standard folders of 11.2 with their filing
    rule, the tenant's categories per folder and, for 04 and 05, the subfolders known from the
    objektakte takeover. Read only; the CRM never invents subfolder names."""
    from mhvp.documents.folders import folder_structure

    async with tenant_tx(request, principal) as session:
        return await folder_structure(session)


@router.post(
    "/document-categories/ensure-defaults",
    summary="Fehlende Standardkategorien ergänzen",
)
async def ensure_default_categories(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> list[s.CategoryOut]:
    """Adds the standard categories a tenant does not have yet (idempotent, never changes an
    existing row); needed for tenants created before ``tenant_file`` and ``owner_file``
    (Package F). Returns the full list afterwards."""
    from mhvp.documents.defaults import ensure_document_defaults

    async with tenant_tx(request, principal) as session:
        await ensure_document_defaults(session, principal.tenant_id)
        rows = (
            await session.scalars(
                select(DocumentCategory).order_by(
                    DocumentCategory.sort_order, DocumentCategory.name
                )
            )
        ).all()
        return [s.CategoryOut.model_validate(r) for r in rows]


@router.post("/document-categories", status_code=201, summary="Kategorie anlegen")
async def create_category(
    body: s.CategoryIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.CategoryOut:
    async with tenant_tx(request, principal) as session:
        if body.parent_id is not None:
            await _get(session, DocumentCategory, body.parent_id)
        row = DocumentCategory(tenant_id=principal.tenant_id, **body.model_dump())
        session.add(row)
        await _flush(session, f"Kategorie {body.code} besteht bereits.")
        return s.CategoryOut.model_validate(row)


@router.patch("/document-categories/{category_id}", summary="Kategorie ändern (Profilzuordnung)")
async def patch_category(
    category_id: uuid.UUID,
    body: s.CategoryPatch,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> s.CategoryOut:
    """Maps a document category to a retention profile (M6-04). Documents stored or
    recategorised afterwards take the profile; ``POST /retention-profiles/apply`` assigns
    it to existing documents without a profile."""
    async with tenant_tx(request, principal) as session:
        row = await _get(session, DocumentCategory, category_id)
        changes = body.model_dump(exclude_unset=True)
        if changes.get("retention_profile_id"):
            await _get(session, RetentionProfile, changes["retention_profile_id"])
        for key, value in changes.items():
            setattr(row, key, value)
        await _event(
            session,
            principal,
            "document_category.updated",
            row.id,
            fields=sorted(changes),
            retention_profile_id=row.retention_profile_id,
        )
        return s.CategoryOut.model_validate(row)


@router.get(
    "/retention-profiles", summary="Aufbewahrungsprofile", dependencies=[Depends(strict_query)]
)
async def list_profiles(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.RetentionProfileOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(RetentionProfile).order_by(RetentionProfile.document_class)
            )
        ).all()
        return [s.RetentionProfileOut.model_validate(r) for r in rows]


@router.post("/retention-profiles", status_code=201, summary="Aufbewahrungsprofil entwerfen")
async def create_profile(
    body: s.RetentionProfileIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.RetentionProfileOut:
    async with tenant_tx(request, principal) as session:
        row = RetentionProfile(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await _flush(session, "Für diese Unterlagenklasse besteht bereits ein Profil.")
        await _event(
            session, principal, "retention_profile.created", row.id, basis=body.legal_basis
        )
        return s.RetentionProfileOut.model_validate(row)


@router.post("/retention-profiles/{profile_id}/release", summary="Aufbewahrungsprofil freigeben")
async def release_profile(
    profile_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.RetentionProfileOut:
    """Releases a draft for the calling tenant only (M6-04): needs ``tenant_settings:update``,
    four eyes (the person who drafted the profile cannot release it, Produktschutz) and is
    audited as ``retention_profile.released`` with the released values."""
    async with tenant_tx(request, principal) as session:
        row = await _get(session, RetentionProfile, profile_id)
        if row.released_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Das Profil ist bereits freigegeben.")
        if principal.user_id is None or row.created_by == principal.user_id:
            raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
        row.released_at, row.released_by = datetime.now(UTC), principal.user_id
        previous_note = row.review_note
        row.review_note = None
        await _event(
            session,
            principal,
            "retention_profile.released",
            row.id,
            document_class=row.document_class,
            legal_entity_kind=row.legal_entity_kind,
            retention_years=row.retention_years,
            retention_months=row.retention_months,
            permanent=row.permanent,
            start_rule=row.start_rule.value,
            legal_basis=row.legal_basis,
            previous_review_note=previous_note,
        )
        return s.RetentionProfileOut.model_validate(row)


@router.patch("/retention-profiles/{profile_id}", summary="Aufbewahrungsprofil bearbeiten")
async def patch_profile(
    profile_id: uuid.UUID,
    body: s.RetentionProfilePatch,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> s.RetentionProfileOut:
    """Edits a profile (M6-04). A released profile becomes a draft again with the editor as
    author, so the change needs a new release by a second person; documents keep their
    computed date until the profile is applied again."""
    async with tenant_tx(request, principal) as session:
        row = await _get(session, RetentionProfile, profile_id)
        changes = body.model_dump(exclude_unset=True)
        if not changes:
            return s.RetentionProfileOut.model_validate(row)
        for key, value in changes.items():
            setattr(row, key, value)
        if not row.permanent and row.retention_years == 0 and row.retention_months == 0:
            raise svc.invalid("Frist fehlt: Jahre oder Monate angeben oder dauerhaft wählen.")
        was_released = row.released_at is not None
        row.released_at, row.released_by = None, None
        row.created_by = principal.user_id
        if not row.review_note:
            row.review_note = "Geändert, erneute Freigabe erforderlich"
        await _flush(session, "Das Profil konnte nicht gespeichert werden.")
        await _event(
            session,
            principal,
            "retention_profile.updated",
            row.id,
            fields=sorted(changes),
            was_released=was_released,
            retention_years=row.retention_years,
            retention_months=row.retention_months,
            permanent=row.permanent,
            start_rule=row.start_rule.value,
        )
        return s.RetentionProfileOut.model_validate(row)


@router.post("/retention-profiles/apply", summary="Profile nach Kategoriezuordnung anwenden")
async def apply_profiles(
    request: Request,
    all_documents: bool = Query(
        default=False, description="auch bereits zugeordnete Dokumente neu berechnen"
    ),
    principal: TenantPrincipal = Depends(SETTINGS),
) -> s.RetentionApplyOut:
    async with tenant_tx(request, principal) as session:
        assigned = await retention.apply_category_mapping(
            session, only_unassigned=not all_documents
        )
        await _event(
            session, principal, "retention_profile.applied", principal.tenant_id, assigned=assigned
        )
        return s.RetentionApplyOut(assigned=assigned)


# Holds per ticket (Vorgang) and deletion proposals (M6-04) --------------------------------


@router.post("/tickets/{ticket_id}/retention-hold", summary="Löschungssperre am Vorgang setzen")
async def set_ticket_hold(
    ticket_id: uuid.UUID,
    body: s.HoldIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.TicketHoldOut:
    """While set, no document linked to the ticket is deleted (Rechtsstreit, Beweissicherung)."""
    async with tenant_tx(request, principal) as session:
        ticket = await _get(session, Ticket, ticket_id)
        ticket.retention_hold_reason = body.reason
        await _event(session, principal, "ticket.hold_set", ticket.id, reason=body.reason)
        return s.TicketHoldOut(
            ticket_id=ticket.id, retention_hold_reason=ticket.retention_hold_reason
        )


@router.delete("/tickets/{ticket_id}/retention-hold", summary="Löschungssperre am Vorgang aufheben")
async def clear_ticket_hold(
    ticket_id: uuid.UUID,
    body: s.HoldIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> s.TicketHoldOut:
    async with tenant_tx(request, principal) as session:
        ticket = await _get(session, Ticket, ticket_id)
        if ticket.retention_hold_reason is not None:
            await retention.require_second_person(
                session,
                event_type="ticket.hold_set",
                entity_id=ticket.id,
                user_id=principal.user_id,
            )
        previous = ticket.retention_hold_reason
        ticket.retention_hold_reason = None
        await _event(
            session,
            principal,
            "ticket.hold_cleared",
            ticket.id,
            reason=body.reason,
            previous=previous,
        )
        return s.TicketHoldOut(ticket_id=ticket.id, retention_hold_reason=None)


async def _proposal_out(session: Any, proposal: DeletionProposal) -> s.DeletionProposalOut:
    await session.flush()
    await session.refresh(proposal)
    out = s.DeletionProposalOut.model_validate(proposal)
    out.items = [
        s.DeletionProposalItemOut.model_validate(i)
        for i in (
            await session.scalars(
                select(DeletionProposalItem)
                .where(DeletionProposalItem.proposal_id == proposal.id)
                .order_by(DeletionProposalItem.retention_until, DeletionProposalItem.title)
            )
        ).all()
    ]
    return out


@router.get("/deletion-proposals", summary="Löschvorschläge", dependencies=[Depends(strict_query)])
async def list_deletion_proposals(
    request: Request,
    status: DeletionProposalStatus | None = Query(default=None),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.DeletionProposalOut]:
    async with tenant_tx(request, principal) as session:
        query = select(DeletionProposal).order_by(DeletionProposal.created_at.desc()).limit(100)
        if status is not None:
            query = query.where(DeletionProposal.status == status)
        rows = (await session.scalars(query)).all()
        return [await _proposal_out(session, r) for r in rows]


@router.post("/deletion-proposals", status_code=201, summary="Löschvorschlag jetzt erstellen")
async def create_deletion_proposal(
    request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> s.DeletionProposalOut:
    """Same run as the monthly job (``mhvp.documents.deletion_proposals``), started by hand.
    Answers 409 when no document is due; nothing is deleted here."""
    async with tenant_tx(request, principal) as session:
        proposal = await retention.propose(
            session, tenant_id=principal.tenant_id, today=_today(), created_by=principal.user_id
        )
        if proposal is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Kein Dokument ist fällig oder alle fälligen sind bereits vorgeschlagen.",
            )
        return await _proposal_out(session, proposal)


@router.get(
    "/deletion-proposals/{proposal_id}",
    summary="Löschvorschlag lesen",
    dependencies=[Depends(strict_query)],
)
async def get_deletion_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.DeletionProposalOut:
    async with tenant_tx(request, principal) as session:
        return await _proposal_out(session, await _get(session, DeletionProposal, proposal_id))


@router.post("/deletion-proposals/{proposal_id}/approve", summary="Löschvorschlag freigeben")
async def approve_deletion_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> s.DeletionProposalOut:
    """Four eyes: not by the person who started the proposal (MHVP-GATE-0002)."""
    async with tenant_tx(request, principal) as session:
        proposal = await _get(session, DeletionProposal, proposal_id)
        await retention.approve(session, proposal, user_id=principal.user_id)
        return await _proposal_out(session, proposal)


@router.post("/deletion-proposals/{proposal_id}/reject", summary="Löschvorschlag ablehnen")
async def reject_deletion_proposal(
    proposal_id: uuid.UUID,
    body: s.DeletionProposalNoteIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> s.DeletionProposalOut:
    async with tenant_tx(request, principal) as session:
        proposal = await _get(session, DeletionProposal, proposal_id)
        await retention.reject(session, proposal, user_id=principal.user_id, note=body.note)
        return await _proposal_out(session, proposal)


@router.post("/deletion-proposals/{proposal_id}/execute", summary="Löschvorschlag ausführen")
async def execute_deletion_proposal(
    proposal_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> s.DeletionProposalExecuteOut:
    """Deletes the approved documents (index, S3 original, mirror steps per M6-03). Four eyes
    again: not by the approver. Every document is re-checked on the day of execution and kept
    with a logged reason when a hold or a period blocks it."""
    async with tenant_tx(request, principal) as session:
        proposal = await _get(session, DeletionProposal, proposal_id)
        result = await retention.execute(
            session, proposal, blobs=_blobs(request), user_id=principal.user_id, today=_today()
        )
        out = await _proposal_out(session, proposal)
    mirror_deletion.enqueue(result.jobs)
    return s.DeletionProposalExecuteOut(
        proposal=out, deleted=result.deleted, skipped=result.skipped
    )


# DMS connections -------------------------------------------------------------------------


def _connection_out(row: DmsConnection) -> s.DmsConnectionOut:
    return s.DmsConnectionOut(
        kind=row.kind,
        enabled=row.enabled,
        base_url=row.base_url,
        has_secret=bool(row.secret),
        options={k: str(v) for k, v in (row.options or {}).items()},
        has_webhook_secret=bool(row.webhook_secret),
        auto_receipt_intake=bool(row.auto_receipt_intake),
    )


def _paperless_options(options: dict[str, str]) -> dict[str, str]:
    """Validates the Paperless field ids and the company option mapping (Hub 7.2) before they
    are stored; the mapping is kept in its normalised text form, an empty one is dropped."""
    try:
        for key, label in (
            ("object_field_id", "Feld-ID Objektnummer"),
            ("company_field_id", "Feld-ID Gesellschaft"),
        ):
            field_id = parse_field_id(options.get(key), label)
            if field_id is None:
                options.pop(key, None)
            else:
                options[key] = str(field_id)
        company_options = parse_company_options(options.get(COMPANY_OPTIONS_KEY))
    except ValueError as exc:
        raise svc.invalid(str(exc)) from None
    if company_options:
        options[COMPANY_OPTIONS_KEY] = format_company_options(company_options)
    else:
        options.pop(COMPANY_OPTIONS_KEY, None)
    return options


@router.get("/dms-connections", summary="DMS-Anbindungen", dependencies=[Depends(strict_query)])
async def list_connections(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> list[s.DmsConnectionOut]:
    async with tenant_tx(request, principal) as session:
        return [_connection_out(r) for r in (await session.scalars(select(DmsConnection))).all()]


@router.put("/dms-connections/{kind}", summary="DMS-Anbindung einrichten")
async def put_connection(
    kind: StorageKind,
    body: s.DmsConnectionIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> s.DmsConnectionOut:
    if kind is StorageKind.MINIO:
        raise svc.invalid("Der Objektspeicher ist fest eingerichtet.")
    insecure = bool(body.base_url) and not str(body.base_url).startswith("https://")
    if (
        kind is StorageKind.PAPERLESS
        and insecure
        and request.app.state.settings.env in ("staging", "prod")
    ):
        raise svc.invalid("Paperless muss per HTTPS angebunden werden.")
    options = dict(body.options)
    if kind is StorageKind.PAPERLESS:
        options = _paperless_options(options)
    if kind is StorageKind.GOOGLE_DRIVE and options.get("folder_scheme", "").strip():
        from mhvp.documents.folder_scheme import validate_folder_scheme

        try:
            options["folder_scheme"] = validate_folder_scheme(options["folder_scheme"])
        except ValueError as exc:
            raise svc.invalid(str(exc)) from None
    else:
        options.pop("folder_scheme", None)
    if kind is StorageKind.GOOGLE_DRIVE and body.enabled:
        missing = [k for k in ("root_folder_id", "client_id") if not body.options.get(k)]
        if missing:
            raise svc.invalid(f"Für Google Drive fehlen: {', '.join(missing)}.")
    if body.secret is not None and kind is StorageKind.GOOGLE_DRIVE:
        try:
            secret = json.loads(body.secret)
        except ValueError:
            secret = None
        if not (
            isinstance(secret, dict) and secret.get("client_secret") and secret.get("refresh_token")
        ):
            raise svc.invalid("Drive-Geheimnis: JSON mit client_secret und refresh_token.")
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(DmsConnection).where(DmsConnection.kind == kind))
        if row is None:
            row = DmsConnection(tenant_id=principal.tenant_id, kind=kind)
            session.add(row)
        row.enabled, row.base_url, row.options = body.enabled, body.base_url, options
        if body.secret is not None:
            row.secret = body.secret
        if kind is StorageKind.PAPERLESS:
            # A30: webhook secret is write only; the intake switch needs a secret to be useful
            # but is stored as given (default off, M14-05).
            if body.webhook_secret is not None:
                row.webhook_secret = body.webhook_secret
            row.auto_receipt_intake = body.auto_receipt_intake
        if row.enabled and not row.secret:
            raise svc.invalid("Ohne Zugangsdaten kann die Anbindung nicht aktiviert werden.")
        await session.flush()
        await _event(
            session,
            principal,
            "dms_connection.updated",
            row.id,
            kind=kind.value,
            enabled=row.enabled,
        )
        return _connection_out(row)


# Templates and letters -------------------------------------------------------------------


@router.get("/document-templates", summary="Vorlagen", dependencies=[Depends(strict_query)])
async def list_templates(
    request: Request,
    context_type: Annotated[
        str | None,
        Query(description="Nur Vorlagen, die für diesen Kontext erlaubt sind (leer: alle)"),
    ] = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.TemplateOut]:
    from mhvp.documents.models import TEMPLATE_CONTEXT_TYPES

    if context_type is not None and context_type not in TEMPLATE_CONTEXT_TYPES:
        raise svc.invalid("Unbekannter Kontexttyp.")
    async with tenant_tx(request, principal) as session:
        query = (
            select(DocumentTemplate)
            .where(DocumentTemplate.active.is_(True))
            .order_by(DocumentTemplate.name)
        )
        if context_type is not None:
            # A template without context types is unrestricted.
            query = query.where(
                or_(
                    func.cardinality(DocumentTemplate.context_types) == 0,
                    DocumentTemplate.context_types.contains([context_type]),
                )
            )
        rows = (await session.scalars(query)).all()
        return [s.TemplateOut.model_validate(r) for r in rows]


@router.post("/document-templates", status_code=201, summary="Vorlage anlegen oder neue Version")
async def create_template(
    body: s.TemplateIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.TemplateOut:
    """A new version keeps older ones, so generated letters stay traceable to their template."""
    try:
        placeholders = letters.placeholders_of(body.subject, body.body)
    except letters.PlaceholderError as exc:
        raise ProblemError(ErrorCodes.PLACEHOLDER, detail=str(exc)) from None
    async with tenant_tx(request, principal) as session:
        if body.master_template_id is not None:
            await _get(session, DocumentTemplate, body.master_template_id)
        previous = (
            await session.scalars(
                select(DocumentTemplate)
                .where(DocumentTemplate.code == body.code)
                .order_by(DocumentTemplate.version.desc())
            )
        ).all()
        for p in previous:
            p.active = False
        row = DocumentTemplate(
            tenant_id=principal.tenant_id,
            version=(previous[0].version + 1) if previous else 1,
            placeholders_used=placeholders,
            **body.model_dump(),
        )
        session.add(row)
        await _flush(session, "Vorlage konnte nicht gespeichert werden.")
        return s.TemplateOut.model_validate(row)


@router.patch("/document-templates/{template_id}", summary="Kontexttypen einer Vorlage pflegen")
async def update_template_context(
    template_id: uuid.UUID,
    body: s.TemplateContextIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> s.TemplateOut:
    """Context types are metadata of a version; placeholders_used is recomputed from the text."""
    async with tenant_tx(request, principal) as session:
        row = await _get(session, DocumentTemplate, template_id)
        row.context_types = body.context_types
        try:
            row.placeholders_used = letters.placeholders_of(row.subject, row.body)
        except letters.PlaceholderError as exc:
            raise ProblemError(ErrorCodes.PLACEHOLDER, detail=str(exc)) from None
        await _flush(session, "Vorlage konnte nicht gespeichert werden.")
        return s.TemplateOut.model_validate(row)


async def _letter(
    session: Any,
    request: Request,
    principal: TenantPrincipal,
    template: DocumentTemplate,
    head: letters.Letterhead,
    *,
    contact_id: uuid.UUID,
    property_id: uuid.UUID | None,
    unit_id: uuid.UUID | None,
    contract_id: uuid.UUID | None,
    letter_date: date,
    reference: str | None,
    fields: dict[str, str],
    signatory: list[str],
    store: bool,
    represents: uuid.UUID | None = None,
) -> tuple[bytes, Document | None]:
    given = {
        k: v
        for k, v in (("property", property_id), ("unit", unit_id), ("contract", contract_id))
        if v is not None
    }
    not_allowed = [k for k in given if template.context_types and k not in template.context_types]
    if not_allowed:
        raise svc.invalid(
            f"Die Vorlage ist für den Kontext {', '.join(not_allowed)} nicht vorgesehen."
        )
    contact, lines, recipient = await svc.recipient(session, contact_id)
    context, info, links = await svc.entity_context(session, property_id, unit_id, contract_id)
    if represents is not None:
        # Authorised representative (delivery rule, mhvp.contacts.recipients): the letter
        # names the represented contact under the recipient and is linked to both contacts.
        principal_contact = await svc.recipient_name(session, represents)
        lines.insert(1, f"für {principal_contact}")
        recipient["vertreten_fuer"] = principal_contact
        links.append(("contact", represents))
    else:
        recipient["vertreten_fuer"] = ""
    context.update(
        empfaenger=recipient,
        felder=fields,
        datum=letter_date.strftime("%d.%m.%Y"),
        gesellschaft={"name": head.company.get("name", "")},
    )
    try:
        subject = letters.render_text(template.subject, context)
        body = letters.render_text(template.body, context)
    except letters.PlaceholderError as exc:
        raise ProblemError(
            ErrorCodes.PLACEHOLDER, detail=f"{contact.display_name}: {exc}"
        ) from None
    if reference:
        info.insert(0, ("Unser Zeichen", reference))
    pdf = letters.render_pdf(
        head, letters.Letter(lines, subject, body, letter_date, info, signatory=signatory)
    )
    if not store:
        return pdf, None
    title = html.unescape(subject)
    document = await svc.store_document(
        session,
        _blobs(request),
        tenant_id=principal.tenant_id,
        data=pdf,
        title=title,
        filename=f"{letter_date.isoformat()}_{template.code}_{contact.display_name}.pdf"[:255],
        mime_type="application/pdf",
        source=DocumentSource.GENERATED,
        category_id=template.category_id,
        links=[("contact", contact.id, LinkRole.GENERATED)]
        + [(t, i, LinkRole.GENERATED) for t, i in links],
        created_by=principal.user_id,
    )
    # Most specific entity first (contract, unit, property), else the recipient (GA04-11).
    context_type, context_id = next(
        ((k, given[k]) for k in ("contract", "unit", "property") if k in given),
        ("contact", contact.id),
    )
    session.add(
        GeneratedDocument(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            document_id=document.id,
            template_id=template.id,
            template_code=template.code,
            template_version=template.version,
            context_type=context_type,
            context_id=context_id,
            recipient_contact_id=contact.id,
        )
    )
    await _event(
        session,
        principal,
        "document.generated",
        document.id,
        template=template.code,
        template_version=template.version,
    )
    return pdf, document


async def _template(session: Any, template_id: uuid.UUID) -> DocumentTemplate:
    template: DocumentTemplate = await _get(session, DocumentTemplate, template_id)
    if not template.active:
        raise svc.invalid("Die Vorlage ist nicht mehr aktiv.")
    return template


@router.post(
    "/letters/preview",
    summary="Brief als Vorschau (nicht abgelegt)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def preview_letter(
    body: s.LetterIn, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    from mhvp.contacts.recipients import resolve_recipients

    async with tenant_tx(request, principal) as session:
        template = await _template(session, body.template_id)
        head = await svc.letterhead(session, _blobs(request))
        first = (await resolve_recipients(session, [body.contact_id]))[0]
        pdf, _ = await _letter(
            session,
            request,
            principal,
            template,
            head,
            contact_id=first.contact_id,
            represents=first.represents,
            property_id=body.property_id,
            unit_id=body.unit_id,
            contract_id=body.contract_id,
            letter_date=body.letter_date or _today(),
            reference=body.reference,
            fields=body.fields,
            signatory=body.signatory,
            store=False,
        )
    return Response(
        content=pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"}
    )


@router.post("/letters", status_code=201, summary="Brief erzeugen und ablegen")
async def create_letter(
    body: s.LetterIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.LetterOut:
    """Generated letters are filed and linked automatically (11.3); nothing is sent. The
    recipients follow the delivery rule of authorised representatives (M23-07): the first
    document is returned, further copies (representative or represented contact) in
    ``further_documents``."""
    from mhvp.contacts.recipients import resolve_recipients

    async with tenant_tx(request, principal) as session:
        template = await _template(session, body.template_id)
        head = await svc.letterhead(session, _blobs(request))
        documents = []
        for recipient in await resolve_recipients(session, [body.contact_id]):
            _, document = await _letter(
                session,
                request,
                principal,
                template,
                head,
                contact_id=recipient.contact_id,
                represents=recipient.represents,
                property_id=body.property_id,
                unit_id=body.unit_id,
                contract_id=body.contract_id,
                letter_date=body.letter_date or _today(),
                reference=body.reference,
                fields=body.fields,
                signatory=body.signatory,
                store=True,
            )
            assert document is not None  # noqa: S101 - store=True
            documents.append(await _out(session, document))
        first, *further = documents
        return s.LetterOut(**first.model_dump(), further_documents=further)


@router.post("/letters/serial", status_code=201, summary="Serienbrief erzeugen")
async def serial_letter(
    body: s.SerialLetterIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.SerialLetterOut:
    """One document per recipient, all or none (one transaction). The recipients follow the
    delivery rule of authorised representatives (``mhvp.contacts.recipients``)."""
    from mhvp.contacts.recipients import resolve_recipients

    if len(set(body.contact_ids)) != len(body.contact_ids):
        raise svc.invalid("Empfänger sind doppelt angegeben.")
    async with tenant_tx(request, principal) as session:
        template = await _template(session, body.template_id)
        head = await svc.letterhead(session, _blobs(request))
        documents = []
        for recipient in await resolve_recipients(session, body.contact_ids):
            _, document = await _letter(
                session,
                request,
                principal,
                template,
                head,
                contact_id=recipient.contact_id,
                represents=recipient.represents,
                property_id=body.property_id,
                unit_id=None,
                contract_id=None,
                letter_date=body.letter_date or _today(),
                reference=body.reference,
                fields=body.fields,
                signatory=body.signatory,
                store=True,
            )
            assert document is not None  # noqa: S101 - store=True
            documents.append(await _out(session, document))
        return s.SerialLetterOut(documents=documents)


@router.get(
    "/generated-documents",
    summary="Erzeugte Dokumente mit Herkunft und Zustellung",
    dependencies=[Depends(strict_query)],
)
async def list_generated_documents(
    request: Request,
    document_id: uuid.UUID | None = None,
    context_type: Annotated[str | None, Query(max_length=32)] = None,
    context_id: uuid.UUID | None = None,
    recipient_contact_id: uuid.UUID | None = None,
    template_id: uuid.UUID | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.GeneratedDocumentOut]:
    """Provenance of produced letters: template and version, context entity, recipient and
    the dispatch record (channel, status, evidence). Only documents the caller may see."""
    from mhvp.communication.models import Dispatch

    async with tenant_tx(request, principal) as session:
        query = (
            select(GeneratedDocument, Dispatch)
            .join(Document, Document.id == GeneratedDocument.document_id)
            .join(Dispatch, Dispatch.id == GeneratedDocument.dispatch_id, isouter=True)
            .order_by(GeneratedDocument.created_at.desc(), GeneratedDocument.id)
            .limit(limit)
            .offset(offset)
        )
        for scope in (_scope_filter(session), _property_scope_filter(session)):
            if scope is not None:
                query = query.where(GeneratedDocument.document_id.in_(scope))
        if document_id is not None:
            query = query.where(GeneratedDocument.document_id == document_id)
        if context_type is not None:
            query = query.where(GeneratedDocument.context_type == context_type)
        if context_id is not None:
            query = query.where(GeneratedDocument.context_id == context_id)
        if recipient_contact_id is not None:
            query = query.where(GeneratedDocument.recipient_contact_id == recipient_contact_id)
        if template_id is not None:
            query = query.where(GeneratedDocument.template_id == template_id)
        if created_from is not None:
            query = query.where(
                GeneratedDocument.created_at >= datetime.combine(created_from, time.min, UTC)
            )
        if created_to is not None:
            query = query.where(
                GeneratedDocument.created_at
                < datetime.combine(created_to, time.min, UTC) + timedelta(days=1)
            )
        out: list[s.GeneratedDocumentOut] = []
        for row, dispatch in (await session.execute(query)).all():
            item = s.GeneratedDocumentOut.model_validate(row)
            if dispatch is not None:
                item.delivery_channel = dispatch.channel
                item.delivery_status = dispatch.status
                item.delivery_evidence_kind = dispatch.evidence_kind
                item.delivery_evidence_ref = dispatch.evidence_ref
                item.delivered_at = dispatch.delivered_at or dispatch.sent_at
            out.append(item)
        return out


# Paperless-Dokumente in Ticket- und Objektansicht (M31) -----------------------------------


async def _paperless_client(session: Any) -> PaperlessSearch:
    connection = await session.scalar(
        select(DmsConnection).where(
            DmsConnection.kind == StorageKind.PAPERLESS, DmsConnection.enabled.is_(True)
        )
    )
    if connection is None or not connection.base_url or not connection.secret:
        raise ProblemError(ErrorCodes.DMS_NOT_CONFIGURED)
    options = connection.options or {}
    try:
        object_field_id = parse_field_id(options.get("object_field_id"), "Feld-ID Objektnummer")
        company_field_id = parse_field_id(options.get("company_field_id"), "Feld-ID Gesellschaft")
        company_options = parse_company_options(options.get(COMPANY_OPTIONS_KEY))
    except ValueError as exc:
        # Stored before validation existed; never guess, ask for the settings to be fixed.
        raise ProblemError(ErrorCodes.DMS_NOT_CONFIGURED, detail=str(exc)) from None
    return PaperlessSearch(
        base_url=connection.base_url,
        token=connection.secret,
        object_field_id=object_field_id,
        company_field_id=company_field_id,
        company_options=company_options,
    )


def _check_company(client: PaperlessSearch, company: str | None) -> None:
    """A requested company option must be configured; otherwise 422 instead of an unfiltered
    or silently empty list."""
    if company is None:
        return
    if not client.company_filter_available or company not in client.company_options:
        raise svc.invalid("Diese Gesellschaft ist für Paperless nicht eingerichtet.")


Company = Annotated[
    str | None,
    Query(
        min_length=1,
        max_length=64,
        description="Options-ID des Paperless-Gesellschaftsfelds (siehe /dms-documents/companies)",
    ),
]
ObjectNumber = Annotated[str | None, Query(pattern=r"^[0-9]{3}$", description="Objektnummer")]
FullText = Annotated[str | None, Query(min_length=2, max_length=200, description="Volltext")]


def _document_out(request: Request, doc: PaperlessDocument) -> s.DmsDocumentOut:
    base = str(request.url_for("dms_document_file", paperless_id=doc.id))
    return s.DmsDocumentOut(
        id=doc.id,
        title=doc.title,
        created=doc.created,
        added=doc.added,
        correspondent=doc.correspondent,
        document_type=doc.document_type,
        tags=doc.tags,
        page_count=doc.page_count,
        original_file_name=doc.original_file_name,
        company=doc.company,
        preview_url=f"{base}?kind=preview",
        download_url=f"{base}?kind=download",
    )


@router.get("/properties/{property_id}/dms-documents", summary="Paperless-Dokumente eines Objekts")
async def property_dms_documents(
    property_id: uuid.UUID,
    request: Request,
    page: Page = 1,
    page_size: PageSize = 25,
    company: Company = None,
    principal: TenantPrincipal = Depends(READ),
) -> s.DmsDocumentPage:
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        client = await _paperless_client(session)
        try:
            _check_company(client, company)
            found = await client.list_by_object_number(
                prop.number, page=page, page_size=page_size, company_option_id=company
            )
        except PaperlessSearchError as exc:
            raise ProblemError(ErrorCodes.DMS_UNAVAILABLE, detail=str(exc)) from None
        finally:
            await client.aclose()
        return s.DmsDocumentPage(
            data=[_document_out(request, d) for d in found.items],
            meta=s.DmsDocumentPageMeta(page=page, per_page=page_size, total=found.total),
        )


@router.get("/tickets/{ticket_id}/dms-documents", summary="Paperless-Dokumente eines Tickets")
async def ticket_dms_documents(
    ticket_id: uuid.UUID,
    request: Request,
    page: Page = 1,
    page_size: PageSize = 25,
    company: Company = None,
    principal: TenantPrincipal = Depends(READ),
) -> s.DmsDocumentPage:
    from mhvp.properties.models import Property
    from mhvp.tickets.models import Ticket

    async with tenant_tx(request, principal) as session:
        ticket = await _get(session, Ticket, ticket_id)
        client = await _paperless_client(session)
        try:
            _check_company(client, company)
            by_number: dict[int, PaperlessDocument] = {}
            if ticket.property_id is not None:
                prop = await session.get(Property, ticket.property_id)
                if prop is not None:
                    for d in (
                        await client.list_by_object_number(
                            prop.number, page=1, page_size=page_size, company_option_id=company
                        )
                    ).items:
                        by_number[d.id] = d
            for d in (
                await client.list_by_ticket(
                    ticket.number, page=1, page_size=page_size, company_option_id=company
                )
            ).items:
                by_number.setdefault(d.id, d)
            if ticket.contact_id is not None:
                from mhvp.contacts.models import Contact

                contact = await session.get(Contact, ticket.contact_id)
                if contact is not None:
                    for d in (
                        await client.list_by_correspondent(
                            contact.display_name,
                            page=1,
                            page_size=page_size,
                            company_option_id=company,
                        )
                    ).items:
                        by_number.setdefault(d.id, d)
        except PaperlessSearchError as exc:
            raise ProblemError(ErrorCodes.DMS_UNAVAILABLE, detail=str(exc)) from None
        finally:
            await client.aclose()
        items = sorted(by_number.values(), key=lambda d: d.created or "", reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]
        return s.DmsDocumentPage(
            data=[_document_out(request, d) for d in page_items],
            meta=s.DmsDocumentPageMeta(page=page, per_page=page_size, total=total),
        )


@router.get(
    "/dms-documents/companies",
    summary="Gesellschaften des Paperless-Gesellschaftsfilters",
    dependencies=[Depends(strict_query)],
)
async def dms_document_companies(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.DmsCompanyOptionOut]:
    """Configured option id to company mapping (Hub 7.2) for the filter selection; empty when
    the company field or the mapping is not configured. Does not call Paperless."""
    async with tenant_tx(request, principal) as session:
        client = await _paperless_client(session)
        await client.aclose()
        if not client.company_filter_available:
            return []
        return [
            s.DmsCompanyOptionOut(option_id=option_id, label=label)
            for option_id, label in client.company_options.items()
        ]


@router.get("/dms-documents", summary="Paperless-Dokumente suchen (Objekt, Gesellschaft, Text)")
async def search_dms_documents(
    request: Request,
    object_number: ObjectNumber = None,
    company: Company = None,
    q: FullText = None,
    page: Page = 1,
    page_size: PageSize = 25,
    principal: TenantPrincipal = Depends(READ),
) -> s.DmsDocumentPage:
    """Read-only search in Paperless (Hub 7.2): object number with the Hub rule (exactly
    ``<Nummer>`` or ``<Nummer>, ...``), company option and full text, combined with AND. At
    least one criterion is required so the endpoint never lists the whole archive."""
    if object_number is None and company is None and q is None:
        raise svc.invalid("Mindestens Objektnummer, Gesellschaft oder Suchbegriff angeben.")
    async with tenant_tx(request, principal) as session:
        if session_allowed_legal_entity_ids(session) is not None:
            # Produktschutz: a scoped membership (tax advisor, A37) sees only documents of its
            # legal entities; the Paperless archive has no such link, so no free search.
            raise ProblemError(ErrorCodes.FORBIDDEN)
        client = await _paperless_client(session)
        try:
            _check_company(client, company)
            if object_number is not None and not client.object_field_id:
                raise svc.invalid("Die Feld-ID Objektnummer ist für Paperless nicht eingerichtet.")
            found = await client.search(
                object_number=object_number,
                company_option_id=company,
                query=q,
                page=page,
                page_size=page_size,
            )
        except PaperlessSearchError as exc:
            raise ProblemError(ErrorCodes.DMS_UNAVAILABLE, detail=str(exc)) from None
        finally:
            await client.aclose()
        return s.DmsDocumentPage(
            data=[_document_out(request, d) for d in found.items],
            meta=s.DmsDocumentPageMeta(page=page, per_page=page_size, total=found.total),
        )


@router.get(
    "/dms-documents/{paperless_id}/file",
    name="dms_document_file",
    summary="Paperless-Datei laden (Proxy, Token bleibt serverseitig)",
)
async def dms_document_file(
    paperless_id: int,
    request: Request,
    kind: str = Query("download", pattern="^(download|preview|thumb)$"),
    principal: TenantPrincipal = Depends(READ),
) -> StreamingResponse:
    async with tenant_tx(request, principal) as session:
        client = await _paperless_client(session)
        try:
            file = await client.fetch_file(paperless_id, kind)  # type: ignore[arg-type]
        except PaperlessSearchError as exc:
            raise ProblemError(ErrorCodes.DMS_UNAVAILABLE, detail=str(exc)) from None
        finally:
            await client.aclose()
        headers = {}
        if kind == "download" and file.filename:
            headers["Content-Disposition"] = content_disposition("attachment", file.filename)
        return StreamingResponse(
            iter([file.content]), media_type=file.content_type, headers=headers
        )


# Wave 3 (Q03): presigned transfer, ZIP import, redactions, intake address, Drive changes.
from mhvp.documents.transfer_routers import router as _transfer_router  # noqa: E402

router.include_router(_transfer_router)
