"""Data takeover from U-Protokoll (M30 stage 4): /api/v1/handover/imports/uprotokoll.

Two steps, like every other import in the platform (13.1, `mhvp.imports`, `mhvp.ai.imports`):
preview (parses the dump, reports counts, unmatched objects and duplicates, changes nothing) and
apply (creates the rows, idempotent by source id). A third endpoint takes a ZIP of the U-Protokoll
storage directory and matches its files to the metadata staged during apply, for the photos,
signatures and the previously generated PDF that a SQL dump never carries. The import run is a
plain `mhvp.ai.models.ImportRun` with `source="uprotokoll"`, the same record every other confirmed
import of the platform uses (rule 0.1.12); nothing here books money or changes a legal deadline."""

import hashlib
import io
import uuid
import zipfile
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import select

from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import services as documents
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import DocumentSource, LinkRole
from mhvp.handover import uprotokoll_import as importer
from mhvp.handover.models import (
    HandoverDefect,
    HandoverItem,
    HandoverMeter,
    HandoverProtocol,
    HandoverRoom,
    HandoverSignature,
)

router = APIRouter(prefix="/handover/imports/uprotokoll", tags=["handover"])
UPDATE = require_permission("contracts:update")
MAX_DUMP_BYTES = 200 * 1024 * 1024
MAX_ZIP_BYTES = 500 * 1024 * 1024
# protocol_files.file_category linked to which handover_* table (database/migrations/
# 001_create_schema.sql of v3ni94/UProtkoll); anything else links only to the protocol.
_ENTITY_BY_FIELD: tuple[tuple[str, str, Any], ...] = (
    ("room_source_id", "handover_room", HandoverRoom),
    ("defect_source_id", "handover_defect", HandoverDefect),
    ("meter_source_id", "handover_meter", HandoverMeter),
    ("item_source_id", "handover_item", HandoverItem),
)


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


@router.post(
    "",
    summary="U-Protokoll-Export prüfen oder übernehmen",
)
async def preview_or_apply(
    request: Request,
    mode: str = Query(default="preview", pattern="^(preview|apply)$"),
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """`mode=preview` (default) only parses and reports, changes nothing. `mode=apply` creates
    the rows; call it only after reviewing the preview, since the operator (not this endpoint)
    decides whether the unmatched objects and duplicates it reports are acceptable."""
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
            source="uprotokoll",
            status=ImportStatus.APPLIED,
            document_ids=[],
            summary=result.as_dict(),
        )
        session.add(run)
        await session.flush()
        return {"mode": "apply", "import_run_id": run.id, **result.as_dict()}


@router.post(
    "/files",
    summary="Dateien aus dem Speicherordner von U-Protokoll zuordnen (ZIP)",
)
async def match_files(
    request: Request,
    import_run_id: uuid.UUID = Query(),
    file: UploadFile = File(),
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    """Matches each entry of the ZIP to a `protocol_files` row staged by `/apply` (by SHA-256
    first, else by the exact stored path) and stores it as a document of the protocol, room,
    defect, meter or item it belonged to in U-Protokoll; a `file_category=signature` file also
    creates the `handover_signature` row (needs the image, so it could not be created by
    `/apply`). Files with no match are reported, not silently dropped."""
    data = await file.read()
    if len(data) > MAX_ZIP_BYTES:
        raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail="Das Archiv ist zu groß.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Keine gültige ZIP-Datei.") from exc

    async with tenant_tx(request, principal) as session:
        run = await session.get(ImportRun, import_run_id)
        if run is None or run.tenant_id != principal.tenant_id or run.source != "uprotokoll":
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        staged: list[dict[str, Any]] = list(run.summary.get("staged_files", []))
        by_sha = {s["sha256"]: s for s in staged if s.get("sha256")}
        by_path = {s["storage_path"]: s for s in staged if s.get("storage_path")}
        matched, unmatched, remaining = [], [], []
        blobs = BlobStore(request.app.state.settings)
        for info in archive.infolist():
            if info.is_dir():
                continue
            content = archive.read(info)
            sha256 = hashlib.sha256(content).hexdigest()
            staged_row = by_sha.get(sha256) or by_path.get(info.filename)
            if staged_row is None:
                unmatched.append(info.filename)
                continue
            protocol = await session.scalar(
                select(HandoverProtocol).where(
                    HandoverProtocol.tenant_id == principal.tenant_id,
                    HandoverProtocol.import_source
                    == f"uprotokoll:{staged_row['protocol_source_id']}",
                )
            )
            if protocol is None:
                unmatched.append(info.filename)
                continue
            links: list[tuple[str, uuid.UUID, LinkRole]] = [
                ("handover_protocol", protocol.id, LinkRole.ATTACHMENT)
            ]
            for field_name, entity_type, model in _ENTITY_BY_FIELD:
                source_id = staged_row.get(field_name)
                if source_id is None:
                    continue
                entity = await session.scalar(
                    select(model).where(
                        model.tenant_id == principal.tenant_id,
                        model.import_source == f"uprotokoll:{source_id}",
                    )
                )
                if entity is not None:
                    links.append((entity_type, entity.id, LinkRole.EVIDENCE))
            mime_type = staged_row.get("mime_type") or "application/octet-stream"
            document = await documents.store_document(
                session,
                blobs,
                tenant_id=principal.tenant_id,
                data=content,
                title=staged_row.get("original_filename") or info.filename,
                filename=staged_row.get("original_filename") or info.filename,
                mime_type=mime_type,
                source=DocumentSource.IMPORT,
                category_id=None,
                links=links,
                created_by=principal.user_id,
            )
            if staged_row.get("file_category") == "signature":
                sig_row = next(
                    (
                        r
                        for r in tables_signatures(run)
                        if r.get("signature_file_id") == staged_row["source_id"]
                    ),
                    None,
                )
                session.add(
                    HandoverSignature(
                        tenant_id=principal.tenant_id,
                        created_by=principal.user_id,
                        import_source=f"uprotokoll:{staged_row['source_id']}",
                        protocol_id=protocol.id,
                        signer_name=(sig_row or {}).get("signer_name"),
                        signer_role=(sig_row or {}).get("signer_role"),
                        document_id=document.id,
                        sha256=sha256,
                        signed_at=importer.to_datetime((sig_row or {}).get("signed_at"))
                        or document.created_at,
                        signed_location=(sig_row or {}).get("signed_location"),
                        comment=(sig_row or {}).get("comment"),
                    )
                )
            matched.append({"filename": info.filename, "document_id": document.id})
        for s in staged:
            if s["sha256"] not in by_sha and s["storage_path"] not in by_path:
                remaining.append(s.get("storage_path") or s.get("original_filename"))
        run.summary = {**run.summary, "files_matched": len(matched), "files_unmatched": unmatched}
        await session.flush()
        return {
            "matched": matched,
            "unmatched_in_zip": unmatched,
            "staged_without_file": remaining,
        }


def tables_signatures(run: ImportRun) -> list[dict[str, Any]]:
    """`protocol_signatures` rows are not staged in the summary (no binary, but their metadata is
    small); they are kept alongside the file staging under the same key for the signer name,
    role and the signing time, read back from `run.summary` set by `/apply`."""
    return list(run.summary.get("signatures", []))
