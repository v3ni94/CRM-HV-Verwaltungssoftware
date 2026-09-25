"""Document endpoints (/api/v1/documents, categories, retention, DMS, templates, letters)."""

import html
import json
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import letters
from mhvp.documents import schemas as s
from mhvp.documents import services as svc
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import (
    DmsConnection,
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentMirror,
    DocumentSource,
    DocumentTemplate,
    LinkRole,
    MirrorStatus,
    RetentionProfile,
    StorageKind,
)
from mhvp.documents.paperless_search import (
    PaperlessDocument,
    PaperlessSearch,
    PaperlessSearchError,
)

router = APIRouter(tags=["Dokumente"])
READ = require_permission("documents:read")
CREATE = require_permission("documents:create")
UPDATE = require_permission("documents:update")
DELETE = require_permission("documents:delete")
APPROVE = require_permission("documents:approve")
SETTINGS = require_permission("tenant_settings:update")
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]
_LINKS = TypeAdapter(list[s.LinkIn])
_LOCAL = ZoneInfo("Europe/Berlin")  # letter date only; deadline time zone is open (M1-09)


def _today() -> date:
    return datetime.now(_LOCAL).date()


def _blobs(request: Request) -> BlobStore:
    return BlobStore(request.app.state.settings)


async def _get(session: Any, model: Any, entity_id: uuid.UUID) -> Any:
    row = await session.get(model, entity_id)
    if row is None:
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
    try:
        link_items = _LINKS.validate_json(links) if links else []
    except ValidationError as exc:
        raise svc.invalid(f"links ungültig: {exc.errors()[0]['msg']}") from None
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
        )
        await _event(session, principal, "document.created", document.id, size=document.size)
        return await _out(session, document)


@router.get("/documents", summary="Dokumente suchen (Volltext)")
async def list_documents(
    request: Request,
    q: str | None = Query(default=None, min_length=2, max_length=200),
    entity_type: str | None = Query(default=None, max_length=63),
    entity_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    page: Page = 1,
    page_size: PageSize = 50,
    principal: TenantPrincipal = Depends(READ),
) -> s.DocumentPage:
    async with tenant_tx(request, principal) as session:
        query = select(Document)
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
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        columns: list[Any] = [Document] + (
            [snippet.label("snippet")] if snippet is not None else []
        )
        rows = (
            await session.execute(
                query.with_only_columns(*columns)
                .order_by(Document.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = []
        for row in rows:
            hit = s.DocumentHit.model_validate(row[0])
            hit.snippet = row[1] if len(row) > 1 else None
            items.append(hit)
        return s.DocumentPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/documents/{document_id}", summary="Dokument lesen")
async def get_document(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        return await _out(session, await _get(session, Document, document_id))


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
        data = _blobs(request).get(document.storage_ref)
        await _event(session, principal, "document.downloaded", document.id)
    name = quote(document.filename)
    return Response(
        content=data,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{name}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.patch("/documents/{document_id}", summary="Metadaten ändern")
async def patch_document(
    document_id: uuid.UUID,
    body: s.DocumentPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        changes = body.model_dump(exclude_unset=True)
        if changes.get("category_id"):
            await _get(session, DocumentCategory, changes["category_id"])
        if changes.get("retention_profile_id"):
            await _get(session, RetentionProfile, changes["retention_profile_id"])
        for key, value in changes.items():
            setattr(document, key, value)
        await _event(session, principal, "document.updated", document.id, fields=sorted(changes))
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
        document.retention_hold_reason = body.reason
        await _event(session, principal, "document.hold_set", document.id, reason=body.reason)
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
        previous = document.retention_hold_reason
        document.retention_hold_reason = None
        await _event(
            session,
            principal,
            "document.hold_cleared",
            document.id,
            reason=body.reason,
            previous=previous,
        )
        return await _out(session, document)


@router.delete("/documents/{document_id}", status_code=204, summary="Dokument löschen")
async def delete_document(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(DELETE)
) -> Response:
    """Only after a released retention profile expired and without a hold (6.9.5, D46)."""
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
        blocker = await svc.deletion_blocker(session, document, _today())
        if blocker is not None:
            await _event(
                session, principal, "document.deletion_refused", document.id, reason=blocker
            )
            raise ProblemError(ErrorCodes.RETENTION_LOCKED, detail=blocker)
        mirrors = (
            await session.scalars(
                select(DocumentMirror).where(
                    DocumentMirror.document_id == document.id,
                    DocumentMirror.status != MirrorStatus.PENDING,
                )
            )
        ).all()
        if mirrors:
            # Mirror deletion is not implemented yet; deleting only here would break 6.9.5.
            raise ProblemError(
                ErrorCodes.RETENTION_LOCKED,
                detail=(
                    "Das Dokument ist in einem externen DMS gespiegelt; "
                    "die Löschung dort ist offen (M6-03)."
                ),
            )
        _blobs(request).delete(document.storage_ref)
        await _event(
            session,
            principal,
            "document.deleted",
            document.id,
            sha256=document.sha256,
            profile=document.retention_profile_id,
        )
        await session.delete(document)
    return Response(status_code=204)


@router.post("/documents/{document_id}/mirror", summary="Spiegelung erneut anstoßen")
async def remirror(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> s.DocumentOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, document_id)
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


@router.get("/document-categories", summary="Dokumentkategorien")
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


@router.get("/retention-profiles", summary="Aufbewahrungsprofile")
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
    profile_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> s.RetentionProfileOut:
    """Four eyes: the person who drafted the profile cannot release it (Produktschutz)."""
    async with tenant_tx(request, principal) as session:
        row = await _get(session, RetentionProfile, profile_id)
        if row.released_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Das Profil ist bereits freigegeben.")
        if principal.user_id is None or row.created_by == principal.user_id:
            raise ProblemError(ErrorCodes.GATE_FOUR_EYES)
        row.released_at, row.released_by = datetime.now(UTC), principal.user_id
        await _event(session, principal, "retention_profile.released", row.id)
        return s.RetentionProfileOut.model_validate(row)


# DMS connections -------------------------------------------------------------------------


def _connection_out(row: DmsConnection) -> s.DmsConnectionOut:
    return s.DmsConnectionOut(
        kind=row.kind,
        enabled=row.enabled,
        base_url=row.base_url,
        has_secret=bool(row.secret),
        options={k: str(v) for k, v in (row.options or {}).items()},
    )


@router.get("/dms-connections", summary="DMS-Anbindungen")
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
        row.enabled, row.base_url, row.options = body.enabled, body.base_url, body.options
        if body.secret is not None:
            row.secret = body.secret
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


@router.get("/document-templates", summary="Vorlagen")
async def list_templates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.TemplateOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(DocumentTemplate)
                .where(DocumentTemplate.active.is_(True))
                .order_by(DocumentTemplate.name)
            )
        ).all()
        return [s.TemplateOut.model_validate(r) for r in rows]


@router.post("/document-templates", status_code=201, summary="Vorlage anlegen oder neue Version")
async def create_template(
    body: s.TemplateIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.TemplateOut:
    """A new version keeps older ones, so generated letters stay traceable to their template."""
    for part in (body.subject, body.body):
        try:
            letters.check_template(part)
        except letters.PlaceholderError as exc:
            raise ProblemError(ErrorCodes.PLACEHOLDER, detail=str(exc)) from None
    async with tenant_tx(request, principal) as session:
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
            **body.model_dump(),
        )
        session.add(row)
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
) -> tuple[bytes, Document | None]:
    contact, lines, recipient = await svc.recipient(session, contact_id)
    context, info, links = await svc.entity_context(session, property_id, unit_id, contract_id)
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
    async with tenant_tx(request, principal) as session:
        template = await _template(session, body.template_id)
        head = await svc.letterhead(session, _blobs(request))
        pdf, _ = await _letter(
            session,
            request,
            principal,
            template,
            head,
            contact_id=body.contact_id,
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
) -> s.DocumentOut:
    """Generated letters are filed and linked automatically (11.3); nothing is sent."""
    async with tenant_tx(request, principal) as session:
        template = await _template(session, body.template_id)
        head = await svc.letterhead(session, _blobs(request))
        _, document = await _letter(
            session,
            request,
            principal,
            template,
            head,
            contact_id=body.contact_id,
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
        return await _out(session, document)


@router.post("/letters/serial", status_code=201, summary="Serienbrief erzeugen")
async def serial_letter(
    body: s.SerialLetterIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.SerialLetterOut:
    """One document per recipient, all or none (one transaction)."""
    if len(set(body.contact_ids)) != len(body.contact_ids):
        raise svc.invalid("Empfänger sind doppelt angegeben.")
    async with tenant_tx(request, principal) as session:
        template = await _template(session, body.template_id)
        head = await svc.letterhead(session, _blobs(request))
        documents = []
        for contact_id in body.contact_ids:
            _, document = await _letter(
                session,
                request,
                principal,
                template,
                head,
                contact_id=contact_id,
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
    object_field_id = options.get("object_field_id")
    company_field_id = options.get("company_field_id")
    return PaperlessSearch(
        base_url=connection.base_url,
        token=connection.secret,
        object_field_id=int(object_field_id) if object_field_id else None,
        company_field_id=int(company_field_id) if company_field_id else None,
    )


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
        preview_url=f"{base}?kind=preview",
        download_url=f"{base}?kind=download",
    )


@router.get("/properties/{property_id}/dms-documents", summary="Paperless-Dokumente eines Objekts")
async def property_dms_documents(
    property_id: uuid.UUID,
    request: Request,
    page: Page = 1,
    page_size: PageSize = 25,
    principal: TenantPrincipal = Depends(READ),
) -> s.DmsDocumentPage:
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        client = await _paperless_client(session)
        try:
            found = await client.list_by_object_number(prop.number, page=page, page_size=page_size)
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
    principal: TenantPrincipal = Depends(READ),
) -> s.DmsDocumentPage:
    from mhvp.properties.models import Property
    from mhvp.tickets.models import Ticket

    async with tenant_tx(request, principal) as session:
        ticket = await _get(session, Ticket, ticket_id)
        client = await _paperless_client(session)
        try:
            by_number: dict[int, PaperlessDocument] = {}
            if ticket.property_id is not None:
                prop = await session.get(Property, ticket.property_id)
                if prop is not None:
                    for d in (
                        await client.list_by_object_number(prop.number, page=1, page_size=page_size)
                    ).items:
                        by_number[d.id] = d
            for d in (
                await client.list_by_ticket(ticket.number, page=1, page_size=page_size)
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
            headers["Content-Disposition"] = f'attachment; filename="{quote(file.filename)}"'
        return StreamingResponse(
            iter([file.content]), media_type=file.content_type, headers=headers
        )
