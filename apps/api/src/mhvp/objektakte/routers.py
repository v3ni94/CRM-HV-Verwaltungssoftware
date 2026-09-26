"""M35 objektakte takeover endpoints: `/api/v1/objektakte/imports` (docs/plans/
M35-objektakte-uebernahme.md section 4). Preview first (counts, matched/new properties,
duplicates), then an explicit apply; apply is idempotent by source id (rule 0.1.12)."""

import uuid
import zipfile
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, TextStatus
from mhvp.objektakte import objektakte_import as importer
from mhvp.objektakte.models import ObjektakteSourceDeletion

router = APIRouter(prefix="/objektakte/imports", tags=["objektakte"])
READ = require_permission("documents:read")
WRITE = require_permission("documents:create")
SETTINGS_WRITE = require_permission("tenant_settings:update")
MAX_DUMP_BYTES = 200 * 1024 * 1024
MAX_OCR_ZIP_BYTES = 500 * 1024 * 1024
MAX_OCR_TEXT_CHARS = 1_000_000
# Sicherheitsreview 2026-09-25, Befund 3: limits against a zip bomb in the OCR cache upload,
# checked against ZipInfo.file_size (the uncompressed size) before archive.read().
MAX_OCR_ENTRY_BYTES = 20 * 1024 * 1024
MAX_OCR_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_OCR_ENTRIES = 50_000


async def _read_dump(file: UploadFile) -> str:
    data = await file.read()
    if len(data) > MAX_DUMP_BYTES:
        raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail="Der Export ist zu groß.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Der Export ist nicht als UTF-8 (utf8mb4) lesbar."
        ) from exc


@router.post("", summary="objektakte-Export prüfen oder übernehmen")
async def preview_or_apply(
    request: Request,
    mode: str = Query(default="preview", pattern="^(preview|apply)$"),
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(WRITE),
) -> dict[str, Any]:
    """`mode=preview` (default) only parses and reports, changes nothing. `mode=apply` creates
    the rows; call it only after reviewing the preview, since the operator (not this endpoint)
    decides whether the unmatched properties and duplicates it reports are acceptable."""
    text = await _read_dump(file)
    tables = importer.parse_dump(text)
    async with tenant_tx(request, principal) as session:
        if mode == "preview":
            plan = await importer.build_plan(session, principal.tenant_id, tables)
            return {"mode": "preview", **plan.as_dict()}
        result = await importer.apply_import(session, principal, tables)
        run = ImportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            source="objektakte",
            status=ImportStatus.APPLIED,
            document_ids=[],
            summary=result.as_dict(),
        )
        session.add(run)
        await session.flush()
        return {"mode": "apply", "import_run_id": run.id, **result.as_dict()}


@router.post(
    "/{import_run_id}/ocr-cache", summary="OCR-Textcache (objektakte /data/ocr-cache) übernehmen"
)
async def apply_ocr_cache(
    request: Request,
    import_run_id: uuid.UUID,
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(WRITE),
) -> dict[str, Any]:
    """Accepts a ZIP of the objektakte `/data/ocr-cache` directory (plan section 4 item 2):
    exactly one text file per cache entry, matched to a migrated `Document` by
    `source_meta["ocr_cache_key"]` (set by the document importer from
    `documents_document.ocr_cache_key`). A match sets `ocr_text` and marks the document
    `extracted`, so full text search works without a re-OCR of the ~26,000 existing documents
    (plan section 5). Preview thumbnails are out of scope for this stage (M35-02, plan section 4
    Stufe 2 acceptance note); the CRM renders no document preview at all yet, so nothing is lost
    by not copying `/data/previews` here either.

    The key is the cache file's name without extension (objektakte writes the key verbatim as
    the file name, `ocr_cache_key.txt` or similar); an unmatched key is reported, never silently
    dropped, since it may point at a document not yet imported.
    """
    async with tenant_tx(request, principal) as session:
        run = await session.get(ImportRun, import_run_id)
        if run is None or run.tenant_id != principal.tenant_id or run.source != "objektakte":
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)

        data = await file.read()
        if len(data) > MAX_OCR_ZIP_BYTES:
            raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail="Der OCR-Cache ist zu groß.")
        try:
            archive = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Die Datei ist kein gültiges ZIP-Archiv."
            ) from exc

        matched = 0
        unmatched: list[str] = []
        skipped_too_large = 0
        total_uncompressed = 0
        entries = archive.infolist()
        if len(entries) > MAX_OCR_ENTRIES:
            raise ProblemError(
                ErrorCodes.UPLOAD_REJECTED,
                detail="Der OCR-Cache enthält zu viele Einträge.",
            )
        for info in entries:
            if info.is_dir():
                continue
            key = info.filename.rsplit("/", 1)[-1]
            if "." in key:
                key = key.rsplit(".", 1)[0]
            if not key:
                continue
            total_uncompressed += info.file_size
            if info.file_size > MAX_OCR_ENTRY_BYTES or total_uncompressed > (
                MAX_OCR_TOTAL_UNCOMPRESSED_BYTES
            ):
                skipped_too_large += 1
                continue
            try:
                raw = archive.read(info)
            except (zipfile.BadZipFile, RuntimeError):
                unmatched.append(key)
                continue
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            document = await session.scalar(
                select(Document).where(
                    Document.tenant_id == principal.tenant_id,
                    Document.source_system == "objektakte",
                    Document.source_meta["ocr_cache_key"].as_string() == key,
                )
            )
            if document is None:
                unmatched.append(key)
                continue
            document.ocr_text = text[:MAX_OCR_TEXT_CHARS]
            document.text_status = TextStatus.EXTRACTED
            matched += 1

        return {
            "import_run_id": run.id,
            "matched": matched,
            "unmatched_keys": unmatched[:200],
            "unmatched_count": len(unmatched),
            "skipped_too_large": skipped_too_large,
        }


@router.get("/{import_run_id}", summary="Ergebnis eines objektakte-Imports abrufen")
async def get_import(
    request: Request,
    import_run_id: uuid.UUID,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(ImportRun, import_run_id)
        if run is None or run.tenant_id != principal.tenant_id or run.source != "objektakte":
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return {
            "import_run_id": run.id,
            "status": run.status,
            "created_at": run.created_at,
            **run.summary,
        }


# --- Stufe 5: paralleler Betrieb, täglicher Differenzimport --------------------------------
# `/api/v1/objektakte/sync`: per tenant switch and export path for the daily Celery job
# (`mhvp.objektakte.tasks`, default off), manual trigger, last report and deletion markers.

sync_router = APIRouter(prefix="/objektakte/sync", tags=["objektakte"])


class SyncSettingsIn(BaseModel):
    enabled: bool | None = None
    dump_path: str | None = Field(default=None, max_length=500)


@sync_router.get("", summary="Stand des objektakte-Differenzimports (Wasserstand, letzter Lauf)")
async def get_sync_state(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        state = await importer.get_or_create_sync_state(session, principal.tenant_id)
        return importer.sync_state_as_dict(state)


@sync_router.put("", summary="Täglichen objektakte-Differenzimport je Mandant einstellen")
async def update_sync_settings(
    request: Request, body: SyncSettingsIn, principal: TenantPrincipal = Depends(SETTINGS_WRITE)
) -> dict[str, Any]:
    """`enabled` switches the daily job on for this tenant only (default off, ADR 0003);
    `dump_path` is the absolute `.sql` export path on the worker (validated again at run time
    by `mhvp.objektakte.tasks.read_dump_file`)."""
    async with tenant_tx(request, principal) as session:
        state = await importer.get_or_create_sync_state(session, principal.tenant_id)
        if body.dump_path is not None:
            path = body.dump_path.strip()
            if path and (not path.startswith("/") or not path.lower().endswith(".sql")):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Der Exportpfad muss absolut sein und auf .sql enden.",
                )
            state.dump_path = path or None
        if body.enabled is not None:
            if body.enabled and not state.dump_path:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Ohne Exportpfad kann der tägliche Import nicht aktiviert werden.",
                )
            state.enabled = body.enabled
        state.updated_by = principal.user_id
        await session.flush()
        return importer.sync_state_as_dict(state)


@sync_router.post("/runs", summary="objektakte-Differenzimport manuell auslösen")
async def trigger_sync_run(
    request: Request,
    file: UploadFile | None = File(default=None),
    principal: TenantPrincipal = Depends(WRITE),
) -> dict[str, Any]:
    """With an uploaded complete export the run happens right now in this request and returns
    its report. Without a file the configured `dump_path` is read by the worker
    (`mhvp.objektakte.sync_tenant`), and the report appears on `GET /objektakte/sync` once the
    task has finished. Both paths use the same water mark and the same idempotent apply."""
    if file is not None:
        text = await _read_dump(file)
        async with tenant_tx(request, principal) as session:
            report = await importer.run_differential_import(
                session,
                principal.tenant_id,
                text,
                trigger="manual_upload",
                actor_user_id=principal.user_id,
            )
            return {"mode": "inline", **report}
    async with tenant_tx(request, principal) as session:
        state = await importer.get_or_create_sync_state(session, principal.tenant_id)
        if not state.dump_path:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Kein Exportpfad hinterlegt; Export hochladen oder Pfad einstellen.",
            )
        tenant_id = principal.tenant_id
    from mhvp.objektakte.tasks import sync_tenant

    sync_tenant.delay(str(tenant_id))
    return {"mode": "queued", "tenant_id": tenant_id}


@sync_router.get("/deletions", summary="In objektakte gelöschte, im CRM markierte Datensätze")
async def list_source_deletions(
    request: Request,
    include_resolved: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        stmt = select(ObjektakteSourceDeletion).where(
            ObjektakteSourceDeletion.tenant_id == principal.tenant_id
        )
        if not include_resolved:
            stmt = stmt.where(ObjektakteSourceDeletion.resolved_at.is_(None))
        rows = (
            await session.scalars(
                stmt.order_by(ObjektakteSourceDeletion.detected_at.desc()).limit(limit)
            )
        ).all()
        return {
            "items": [
                {
                    "id": r.id,
                    "source_table": r.source_table,
                    "source_id": r.source_id,
                    "target_table": r.target_table,
                    "target_id": r.target_id,
                    "detected_at": r.detected_at,
                    "resolved_at": r.resolved_at,
                }
                for r in rows
            ]
        }
