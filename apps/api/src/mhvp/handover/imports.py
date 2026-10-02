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
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents import services as documents
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentLink, DocumentSource, LinkRole
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
READ = require_permission("contracts:read")
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
        assigned: list[dict[str, Any]] = []
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
            assigned.append(
                {
                    "document_id": str(document.id),
                    "filename": info.filename,
                    "source_id": staged_row.get("source_id"),
                    "file_category": staged_row.get("file_category"),
                    "protocol_id": str(protocol.id),
                    "linked": [[t, str(i)] for t, i, _ in links],
                }
            )
        for s in staged:
            if s["sha256"] not in by_sha and s["storage_path"] not in by_path:
                remaining.append(s.get("storage_path") or s.get("original_filename"))
        previous = [
            a
            for a in run.summary.get("assigned_files", [])
            if a["document_id"] not in {x["document_id"] for x in assigned}
        ]
        run.summary = {
            **run.summary,
            "files_matched": len(matched),
            "files_unmatched": unmatched,
            "assigned_files": [*previous, *assigned],
        }
        await session.flush()
        return {
            "matched": matched,
            "unmatched_in_zip": unmatched,
            "staged_without_file": remaining,
        }


async def _uprotokoll_run(
    session: AsyncSession,
    principal: TenantPrincipal,
    run_id: uuid.UUID,
) -> ImportRun:
    run = await session.get(ImportRun, run_id)
    if run is None or run.tenant_id != principal.tenant_id or run.source != "uprotokoll":
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return run


@router.get("/files")
async def list_file_assignments(
    request: Request,
    import_run_id: uuid.UUID = Query(),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Lists the files that `/files` assigned for one import run (GAG-13): document, protocol
    and the handover records each is linked to. Entries whose document link was released show
    `linked` as an empty list; the staged files without an assignment are listed as pending."""
    async with tenant_tx(request, principal) as session:
        run = await _uprotokoll_run(session, principal, import_run_id)
        assigned: list[dict[str, Any]] = list(run.summary.get("assigned_files", []))
        ids = [uuid.UUID(a["document_id"]) for a in assigned]
        live: dict[uuid.UUID, list[list[str]]] = {i: [] for i in ids}
        if ids:
            rows = await session.execute(
                select(DocumentLink.document_id, DocumentLink.entity_type, DocumentLink.entity_id)
                .where(
                    DocumentLink.tenant_id == principal.tenant_id,
                    DocumentLink.document_id.in_(ids),
                    DocumentLink.entity_type.like("handover\\_%"),
                )
                .order_by(DocumentLink.entity_type, DocumentLink.entity_id)
            )
            for doc_id, entity_type, entity_id in rows.all():
                live[doc_id].append([entity_type, str(entity_id)])
        items = [
            {
                "document_id": a["document_id"],
                "filename": a["filename"],
                "file_category": a.get("file_category"),
                "protocol_id": a["protocol_id"],
                "linked": live[uuid.UUID(a["document_id"])],
            }
            for a in assigned
        ]
        done = {a.get("source_id") for a in assigned}
        pending = [
            s.get("original_filename") or s.get("storage_path")
            for s in run.summary.get("staged_files", [])
            if s.get("source_id") not in done
        ]
        return {"items": items, "total": len(items), "pending_files": pending}


@router.delete("/files/{document_id}", status_code=204)
async def release_file_assignment(
    request: Request,
    document_id: uuid.UUID,
    import_run_id: uuid.UUID = Query(),
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    """Releases one assignment: the links of the document to the handover records are removed,
    the document itself stays in the document store (retention, no deletion). A signature file
    that already created a `handover_signature` is evidence and cannot be released (409). The
    file can be assigned again by repeating `/files` with the ZIP."""
    async with tenant_tx(request, principal) as session:
        run = await _uprotokoll_run(session, principal, import_run_id)
        assigned: list[dict[str, Any]] = list(run.summary.get("assigned_files", []))
        entry = next((a for a in assigned if a["document_id"] == str(document_id)), None)
        if entry is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        document = await session.get(Document, document_id)
        if document is None or document.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        signature = await session.scalar(
            select(HandoverSignature.id).where(
                HandoverSignature.tenant_id == principal.tenant_id,
                HandoverSignature.document_id == document_id,
            )
        )
        if signature is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Die Datei ist eine Unterschrift und gehört zum Nachweis des Protokolls.",
            )
        await session.execute(
            delete(DocumentLink).where(
                DocumentLink.tenant_id == principal.tenant_id,
                DocumentLink.document_id == document_id,
                DocumentLink.entity_type.like("handover\\_%"),
            )
        )
        remaining = [a for a in assigned if a["document_id"] != str(document_id)]
        run.summary = {
            **run.summary,
            "assigned_files": remaining,
            "files_matched": len(remaining),
        }
        await session.flush()


def tables_signatures(run: ImportRun) -> list[dict[str, Any]]:
    """`protocol_signatures` rows are not staged in the summary (no binary, but their metadata is
    small); they are kept alongside the file staging under the same key for the signer name,
    role and the signing time, read back from `run.summary` set by `/apply`."""
    return list(run.summary.get("signatures", []))
