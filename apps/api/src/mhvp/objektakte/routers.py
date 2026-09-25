"""M35 objektakte takeover endpoints: `/api/v1/objektakte/imports` (docs/plans/
M35-objektakte-uebernahme.md section 4). Preview first (counts, matched/new properties,
duplicates), then an explicit apply; apply is idempotent by source id (rule 0.1.12)."""

import uuid
import zipfile
from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import select

from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, TextStatus
from mhvp.objektakte import objektakte_import as importer

router = APIRouter(prefix="/objektakte/imports", tags=["objektakte"])
READ = require_permission("documents:read")
WRITE = require_permission("documents:create")
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
