"""Wave 3 document endpoints (Q03): presigned transfer (S12-06), ZIP bulk upload as
``import_run`` (M6-03), redacted copies with protocol (M25-01), tenant intake address (M6-04)
and the Drive Changes sync (M6-05). Included into ``mhvp.documents.routers.router``."""

from __future__ import annotations

import hashlib
import io
import mimetypes
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.storage import presigned_download_url, presigned_upload_url
from mhvp.documents import intake_address
from mhvp.documents import schemas as s
from mhvp.documents import services as svc
from mhvp.documents.models import (
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentRedaction,
    DocumentSource,
    LinkRole,
    StorageKind,
)
from mhvp.documents.text import ALLOWED_MIME_TYPES
from mhvp.handover import images

router = APIRouter(tags=["Dokumente"])
READ = require_permission("documents:read")
CREATE = require_permission("documents:create")
UPDATE = require_permission("documents:update")
APPROVE = require_permission("documents:approve")
SETTINGS = require_permission("tenant_settings:update")
URL_SECONDS = 300
ZIP_MAX_ENTRIES = 200
# Total of all unpacked entries as a multiple of the single file limit (SECURITY-2026-10-01,
# Befund 1): 200 entries of the single limit each would otherwise be held in memory at once.
ZIP_MAX_TOTAL_FACTOR = 8
_LINKS = TypeAdapter(list[s.LinkIn])
_STEPS = TypeAdapter(list[str])


def _r() -> Any:
    from mhvp.documents import routers  # local: routers includes this module

    return routers


def _sanitize(data: bytes, mime: str, request: Request) -> tuple[bytes, str]:
    if images.supports(mime):
        try:
            data = images.sanitize_image(
                data, mime, max_edge=request.app.state.settings.handover_image_max_edge
            )
            mime = images.output_mime_type(mime)
        except images.ImageSanitizeError:
            pass
    return data, mime


# Presigned transfer (S12-06) --------------------------------------------------------------


@router.post(
    "/documents/uploads", status_code=201, summary="Direkten Upload vorbereiten (signierte URL)"
)
async def create_upload_intent(
    body: s.DocumentUploadIntentIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.DocumentUploadIntentOut:
    """Signed PUT URL into the temporary area (``tmp/``, lifecycle rule M6-08). Nothing is
    registered yet: ``/documents/uploads/{id}/complete`` runs the same checks as the multipart
    upload (type, content, size, malware scan) and files the document."""
    limit = request.app.state.settings.document_max_bytes
    mime = body.mime_type.split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME_TYPES:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED, detail=f"Dateityp {mime} ist nicht zulässig."
        )
    if body.size > limit:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED,
            detail=f"Die Datei ist größer als {limit // (1024 * 1024)} MB.",
        )
    blobs = _r()._blobs(request)
    upload_id = uuid.uuid4()
    key = blobs.tmp_key(principal.tenant_id, upload_id)
    try:
        url = presigned_upload_url(
            blobs.client, blobs.bucket, key, content_type=mime, expires=URL_SECONDS
        )
    except (BotoCoreError, ClientError) as exc:
        raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE) from exc
    return s.DocumentUploadIntentOut(
        upload_id=upload_id, url=url, headers={"Content-Type": mime}, expires_in=URL_SECONDS
    )


@router.post(
    "/documents/uploads/{upload_id}/complete",
    status_code=201,
    summary="Direkten Upload abschließen und ablegen",
)
async def complete_upload(
    upload_id: uuid.UUID,
    body: s.DocumentUploadCompleteIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.DocumentOut:
    routers = _r()
    blobs = routers._blobs(request)
    key = blobs.tmp_key(principal.tenant_id, upload_id)
    limit = request.app.state.settings.document_max_bytes
    data = blobs.get_tmp(key, limit)
    if data is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Der Upload wurde nicht gefunden.")
    mime = body.mime_type.split(";")[0].strip().lower()
    svc.check_upload(mime, data, limit)
    data, mime = _sanitize(data, mime, request)
    filename = body.filename.replace("/", "_").replace("\\", "_")
    async with tenant_tx(request, principal) as session:
        if body.category_id is not None:
            await routers._get(session, DocumentCategory, body.category_id)
        document = await svc.store_document(
            session,
            blobs,
            tenant_id=principal.tenant_id,
            data=data,
            title=body.title or filename,
            filename=filename,
            mime_type=mime,
            source=DocumentSource.UPLOAD,
            category_id=body.category_id,
            links=[(x.entity_type, x.entity_id, x.role) for x in body.links],
            created_by=principal.user_id,
            settings=request.app.state.settings,
        )
        await routers._event(
            session, principal, "document.created", document.id, size=document.size, direct=True
        )
        out = await routers._out(session, document)
    blobs.delete(key)
    return out  # type: ignore[no-any-return]


@router.get("/documents/{document_id}/download-url", summary="Signierte Download-URL")
async def download_url(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.DocumentDownloadUrlOut:
    """Short lived signed GET URL of the original (S12-06); permission, tenant and scope are
    checked here, the download itself is journaled like ``/content``."""
    routers = _r()
    blobs = routers._blobs(request)
    async with tenant_tx(request, principal) as session:
        document = await routers._get(session, Document, document_id)
        if document.storage is not StorageKind.MINIO:
            raise svc.invalid("Nur Originale im Dokumentenspeicher haben eine Download-URL.")
        try:
            url = presigned_download_url(
                blobs.client,
                blobs.bucket,
                document.storage_ref,
                filename=document.filename,
                expires=URL_SECONDS,
            )
        except (BotoCoreError, ClientError) as exc:
            raise ProblemError(ErrorCodes.STORAGE_UNAVAILABLE) from exc
        await routers._event(session, principal, "document.downloaded", document.id, signed=True)
    return s.DocumentDownloadUrlOut(url=url, expires_in=URL_SECONDS)


# ZIP bulk upload (M6-03) -------------------------------------------------------------------


def _zip_entries(
    data: bytes, limit: int
) -> tuple[list[tuple[str, bytes]], list[s.DocumentZipSkippedOut]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED, detail="Die ZIP-Datei ist beschädigt."
        ) from None
    files = [i for i in archive.infolist() if not i.is_dir()]
    if len(files) > ZIP_MAX_ENTRIES:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED,
            detail=f"Die ZIP-Datei enthält mehr als {ZIP_MAX_ENTRIES} Dateien.",
        )
    entries: list[tuple[str, bytes]] = []
    skipped: list[s.DocumentZipSkippedOut] = []
    total_limit = limit * ZIP_MAX_TOTAL_FACTOR
    total = 0
    for info in files:
        name = info.filename.replace("\\", "/")
        base = name.rsplit("/", 1)[-1]
        if not base or base.startswith(".") or name.startswith("__MACOSX/"):
            continue
        if info.flag_bits & 0x1:
            skipped.append(s.DocumentZipSkippedOut(name=name, reason="verschlüsselt"))
            continue
        if info.file_size > limit:
            skipped.append(s.DocumentZipSkippedOut(name=name, reason="zu groß"))
            continue
        with archive.open(info) as handle:
            content = handle.read(limit + 1)  # the declared size is not trusted (zip bomb)
        if len(content) > limit:
            skipped.append(s.DocumentZipSkippedOut(name=name, reason="zu groß"))
            continue
        total += len(content)
        if total > total_limit:
            raise ProblemError(
                ErrorCodes.UPLOAD_REJECTED,
                detail=(
                    "Der entpackte Inhalt der ZIP-Datei ist größer als "
                    f"{total_limit // (1024 * 1024)} MB."
                ),
            )
        entries.append((name, content))
    return entries, skipped


@router.post("/documents/zip-import", status_code=201, summary="Massenupload aus ZIP (import_run)")
async def zip_import(
    request: Request,
    file: UploadFile = File(),
    category_id: uuid.UUID | None = Form(default=None),
    links: str | None = Form(default=None, description="JSON-Liste aus entity_type, entity_id"),
    principal: TenantPrincipal = Depends(CREATE),
) -> s.DocumentZipImportOut:
    """Every file of the archive runs through the normal pipeline (type and content check,
    malware scan, text extraction, retention, mirrors); a refused file is listed with its
    reason and does not stop the others. The run is recorded as ``import_run`` (source
    ``document_zip``) with one item per document; undoing it never deletes documents (0.1.7)."""
    from mhvp.ai.models import ImportRun, ImportRunItem, ImportStatus

    routers = _r()
    settings = request.app.state.settings
    limit = settings.document_max_bytes
    archive_limit = limit * 4
    data = await file.read(archive_limit + 1)
    if len(data) > archive_limit:
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED,
            detail=f"Die ZIP-Datei ist größer als {archive_limit // (1024 * 1024)} MB.",
        )
    try:
        link_items = _LINKS.validate_json(links) if links else []
    except ValidationError as exc:
        raise svc.invalid(f"links ungültig: {exc.errors()[0]['msg']}") from None
    entries, skipped = _zip_entries(data, limit)
    blobs = routers._blobs(request)
    created: list[uuid.UUID] = []
    async with tenant_tx(request, principal) as session:
        if category_id is not None:
            await routers._get(session, DocumentCategory, category_id)
        for name, content in entries:
            base = name.rsplit("/", 1)[-1]
            mime = (mimetypes.guess_type(base)[0] or "application/octet-stream").lower()
            try:
                svc.check_upload(mime, content, limit)
                payload, mime = _sanitize(content, mime, request)
                async with session.begin_nested():
                    document = await svc.store_document(
                        session,
                        blobs,
                        tenant_id=principal.tenant_id,
                        data=payload,
                        title=base,
                        filename=base,
                        mime_type=mime,
                        source=DocumentSource.IMPORT,
                        category_id=category_id,
                        links=[(x.entity_type, x.entity_id, x.role) for x in link_items],
                        created_by=principal.user_id,
                        settings=settings,
                    )
            except ProblemError as exc:
                if exc.status != 422:  # storage or scanner down: stop, nothing half done
                    raise
                reason = str(exc.detail or exc.error.title)
                skipped.append(s.DocumentZipSkippedOut(name=name, reason=reason))
                continue
            created.append(document.id)
        run_id: uuid.UUID | None = None
        if created:
            run = ImportRun(
                tenant_id=principal.tenant_id,
                source="document_zip",
                status=ImportStatus.APPLIED,
                document_ids=created,
                summary={
                    "filename": (file.filename or "upload.zip")[:255],
                    "created": len(created),
                    "skipped": len(skipped),
                },
                created_by=principal.user_id,
            )
            session.add(run)
            await session.flush()
            for sequence, document_id in enumerate(created):
                session.add(
                    ImportRunItem(
                        tenant_id=principal.tenant_id,
                        import_run_id=run.id,
                        sequence=sequence,
                        entity_type="document",
                        entity_id=document_id,
                    )
                )
            run_id = run.id
            await routers._event(
                session,
                principal,
                "document.zip_imported",
                run.id,
                created=len(created),
                skipped=len(skipped),
            )
    return s.DocumentZipImportOut(import_run_id=run_id, created=created, skipped=skipped)


# Redacted copies (M25-01) ------------------------------------------------------------------


@router.get("/documents/{document_id}/redactions", summary="Geschwärzte Kopien eines Originals")
async def list_redactions(
    document_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.DocumentRedactionOut]:
    routers = _r()
    async with tenant_tx(request, principal) as session:
        await routers._get(session, Document, document_id)
        rows = (
            await session.scalars(
                select(DocumentRedaction)
                .where(DocumentRedaction.original_document_id == document_id)
                .order_by(DocumentRedaction.created_at)
            )
        ).all()
        return [s.DocumentRedactionOut.model_validate(r) for r in rows]


@router.post(
    "/documents/{document_id}/redactions",
    status_code=201,
    summary="Geschwärzte Kopie mit Protokoll anlegen",
)
async def create_redaction(
    document_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(),
    reason: str = Form(min_length=5, max_length=1000),
    scope: str = Form(min_length=3, max_length=2000, description="Umfang der Schwärzung"),
    steps: str = Form(description="JSON-Liste der Bearbeitungsschritte"),
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.DocumentRedactionOut:
    """The redacted file is a new document (internal until released), linked to the original
    with role ``generated`` and to the original's entities; the original is not changed."""
    routers = _r()
    try:
        step_list = _STEPS.validate_json(steps)
    except ValidationError:
        raise svc.invalid("steps ist eine JSON-Liste von Texten.") from None
    step_list = [x.strip()[:500] for x in step_list if x.strip()]
    if not step_list or len(step_list) > 50:
        raise svc.invalid("Mindestens ein Bearbeitungsschritt (höchstens 50) ist anzugeben.")
    settings = request.app.state.settings
    limit = settings.document_max_bytes
    data = await file.read(limit + 1)
    mime = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    svc.check_upload(mime, data, limit)
    blobs = routers._blobs(request)
    async with tenant_tx(request, principal) as session:
        original = await routers._get(session, Document, document_id)
        if await session.scalar(
            select(DocumentRedaction.id).where(DocumentRedaction.copy_document_id == document_id)
        ):
            raise svc.invalid("Eine geschwärzte Kopie ist selbst kein Original.")
        if hashlib.sha256(data).hexdigest() == original.sha256:
            raise svc.invalid(
                "Die Datei ist identisch mit dem Original, es wurde nichts geschwärzt."
            )
        original_links = (
            await session.scalars(
                select(DocumentLink).where(
                    DocumentLink.document_id == original.id, DocumentLink.entity_type != "document"
                )
            )
        ).all()
        links = [(x.entity_type, x.entity_id, LinkRole.ATTACHMENT) for x in original_links]
        links.append(("document", original.id, LinkRole.GENERATED))
        filename = (file.filename or original.filename).replace("/", "_").replace("\\", "_")
        copy = await svc.store_document(
            session,
            blobs,
            tenant_id=principal.tenant_id,
            data=data,
            title=f"{original.title} (geschwärzt)"[:300],
            filename=filename,
            mime_type=mime,
            source=DocumentSource.GENERATED,
            category_id=original.category_id,
            links=links,
            created_by=principal.user_id,
            visibility=["internal"],
            scan_for_malware=True,
            settings=settings,
        )
        redaction = DocumentRedaction(
            tenant_id=principal.tenant_id,
            original_document_id=original.id,
            copy_document_id=copy.id,
            reason=reason.strip(),
            scope=scope.strip(),
            steps=step_list,
            created_by=principal.user_id,
        )
        session.add(redaction)
        await session.flush()
        await routers._event(
            session,
            principal,
            "document.redaction_created",
            original.id,
            copy=copy.id,
            steps=len(step_list),
        )
        await session.refresh(redaction)
        return s.DocumentRedactionOut.model_validate(redaction)


@router.post(
    "/documents/{document_id}/redactions/{redaction_id}/release",
    summary="Geschwärzte Kopie freigeben (Vier Augen)",
)
async def release_redaction(
    document_id: uuid.UUID,
    redaction_id: uuid.UUID,
    body: s.DocumentRedactionReleaseIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> s.DocumentRedactionOut:
    routers = _r()
    async with tenant_tx(request, principal) as session:
        await routers._get(session, Document, document_id)
        redaction = await session.get(DocumentRedaction, redaction_id)
        if redaction is None or redaction.original_document_id != document_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if redaction.released_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Kopie ist bereits freigegeben.")
        if redaction.created_by is not None and redaction.created_by == principal.user_id:
            raise ProblemError(
                ErrorCodes.FORBIDDEN, detail="Die Freigabe erteilt eine zweite Person (Vier Augen)."
            )
        copy = await session.get(Document, redaction.copy_document_id)
        if copy is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        copy.visibility = list(body.visibility)
        redaction.released_at = datetime.now(UTC)
        redaction.released_by = principal.user_id
        redaction.released_visibility = list(body.visibility)
        await svc.mark_mirrors_dirty(session, copy.id)
        await routers._event(
            session,
            principal,
            "document.redaction_released",
            document_id,
            copy=copy.id,
            visibility=",".join(body.visibility),
        )
        await session.flush()
        await session.refresh(redaction)
        return s.DocumentRedactionOut.model_validate(redaction)


# Tenant intake address (M6-04) -------------------------------------------------------------


def _intake_out(config: intake_address.IntakeAddress | None) -> s.DocumentIntakeAddressOut:
    if config is None:
        return s.DocumentIntakeAddressOut(configured=False)
    return s.DocumentIntakeAddressOut(
        configured=True,
        enabled=config.enabled,
        address=config.address,
        mailbox_address=config.mailbox_address,
        allowed_senders=config.allowed_senders,
        distribute=config.distribute,
    )


async def _tenant_settings(session: Any) -> Any:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings))
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Mandanteneinstellungen fehlen.")
    return row


@router.get("/document-intake-address", summary="Eingangsadresse für Weiterleitungen")
async def get_intake_address(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.DocumentIntakeAddressOut:
    async with tenant_tx(request, principal) as session:
        row = await _tenant_settings(session)
        return _intake_out(intake_address.load(row.sources))


@router.put("/document-intake-address", summary="Eingangsadresse einrichten")
async def put_intake_address(
    body: s.DocumentIntakeAddressIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
    rotate: bool = False,
) -> s.DocumentIntakeAddressOut:
    """Keeps the token unless ``rotate`` is set or the mailbox changes (a new address is then
    handed out; forwards to the old one are no longer recognised)."""
    async with tenant_tx(request, principal) as session:
        row = await _tenant_settings(session)
        current = intake_address.load(row.sources)
        mailbox = body.mailbox_address.lower()
        token = (
            current.token
            if current is not None and not rotate and current.mailbox_address == mailbox
            else intake_address.new_token()
        )
        config = intake_address.IntakeAddress(
            mailbox_address=mailbox,
            token=token,
            allowed_senders=body.allowed_senders,
            enabled=body.enabled,
            distribute=body.distribute,
        )
        row.sources = {**(row.sources or {}), intake_address.CONFIG_KEY: config.as_dict()}
        await _r()._event(
            session,
            principal,
            "document.intake_address_set",
            principal.tenant_id,
            enabled=config.enabled,
            distribute=config.distribute,
            rotated=current is None or token != current.token,
        )
        return _intake_out(config)


# Direct browser upload switch (S12-06, Q03-01) --------------------------------------------

DIRECT_UPLOAD_KEY = "document_direct_upload"


@router.get("/document-direct-upload", summary="Direkter Browser-Upload (Mandantenschalter)")
async def get_direct_upload(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> s.DocumentDirectUploadOut:
    async with tenant_tx(request, principal) as session:
        row = await _tenant_settings(session)
        return s.DocumentDirectUploadOut(enabled=bool((row.sources or {}).get(DIRECT_UPLOAD_KEY)))


@router.put("/document-direct-upload", summary="Direkten Browser-Upload ein- oder ausschalten")
async def put_direct_upload(
    body: s.DocumentDirectUploadIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS),
) -> s.DocumentDirectUploadOut:
    """Default off. The CRM uploads through the API unless this switch is on; the object
    storage endpoint must then be reachable from the browser and allow CORS for PUT
    (runbook object storage). The API endpoints stay available either way."""
    async with tenant_tx(request, principal) as session:
        row = await _tenant_settings(session)
        row.sources = {**(row.sources or {}), DIRECT_UPLOAD_KEY: body.enabled}
        await _r()._event(
            session,
            principal,
            "document.direct_upload_set",
            principal.tenant_id,
            enabled=body.enabled,
        )
        return s.DocumentDirectUploadOut(enabled=body.enabled)


# Drive Changes API (M6-05) -----------------------------------------------------------------


@router.post("/dms-changes/google-drive/sync", summary="Drive-Änderungen jetzt abholen")
async def sync_drive_changes(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS)
) -> s.DocumentDriveChangesOut:
    import httpx

    from mhvp.documents import drive_changes
    from mhvp.documents.dms import DmsError
    from mhvp.objektakte.drive_quota import drive_http_client

    async with drive_http_client(timeout=30.0) as client:
        try:
            async with tenant_tx(request, principal) as session:
                result = await drive_changes.sync_session(
                    session, principal.tenant_id, client, principal.user_id
                )
        except (DmsError, httpx.HTTPError) as exc:
            raise ProblemError(
                ErrorCodes.DMS_UNAVAILABLE, detail="Google Drive ist nicht erreichbar."
            ) from exc
    if result is None:
        raise svc.invalid("Keine aktive Google-Drive-Anbindung eingerichtet.")
    return s.DocumentDriveChangesOut(
        started=result.started,
        changes=result.changes,
        matched=result.matched,
        removed=result.removed,
    )
