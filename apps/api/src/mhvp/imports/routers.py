"""Import assistant endpoints (/api/v1/imports/immoware24, 13.1)."""

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import property_unrestricted_guard
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document
from mhvp.imports import column_detection as detection
from mhvp.imports import services as svc
from mhvp.imports.fields import FIELDS
from mhvp.imports.models import (
    FileStatus,
    ImportColumnAssignment,
    ImportMapping,
    ImportSourceFile,
    ReportType,
    RowStatus,
    StagingRow,
)

router = APIRouter(
    prefix="/imports/immoware24",
    tags=["Import Immoware24"],
    dependencies=[Depends(property_unrestricted_guard)],  # Y01, M2-02
)
READ = require_permission("ai:read")
WRITE = require_permission("ai:create")
# Creating master data needs the domain permissions too.
DOMAIN = {"properties:create", "contacts:create", "contracts:create"}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldOut(BaseModel):
    name: str
    kind: str
    required: bool
    choices: list[str]
    label: str


class SourceIn(_In):
    document_id: uuid.UUID
    report_type: ReportType
    sheet: str | None = Field(default=None, max_length=100)
    header_row: int = Field(default=1, ge=1, le=50)


class MappingIn(_In):
    report_type: ReportType
    name: str = Field(min_length=1, max_length=200)
    columns: dict[str, str]
    value_maps: dict[str, dict[str, str]] = Field(default_factory=dict)


class MappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    report_type: ReportType
    name: str
    version: int
    columns: dict[str, str]
    value_maps: dict[str, dict[str, str]]
    active: bool


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    document_id: uuid.UUID
    report_type: ReportType
    sheet: str | None
    header_row: int
    headers: list[str]
    row_count: int
    mapping_id: uuid.UUID | None
    status: FileStatus
    import_run_id: uuid.UUID | None
    report: dict[str, Any]


class RowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    row_number: int
    raw: dict[str, Any]
    values: dict[str, Any] | None
    status: RowStatus
    errors: list[str]
    entity_type: str | None
    entity_id: uuid.UUID | None


class ValidateIn(_In):
    mapping_id: uuid.UUID


async def _get(session: Any, model: Any, entity_id: uuid.UUID) -> Any:
    row = await session.get(model, entity_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


def _need_domain(principal: TenantPrincipal) -> None:
    missing = DOMAIN - set(principal.permissions)
    if missing:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message=f"missing {sorted(missing)}")


@router.get("/fields", summary="Zielfelder je Report")
async def fields(principal: TenantPrincipal = Depends(READ)) -> dict[str, list[FieldOut]]:
    return {
        rt.value: [
            FieldOut(
                name=f.name,
                kind=f.kind,
                required=f.required,
                choices=list(f.choices),
                label=f.label,
            )
            for f in items
        ]
        for rt, items in FIELDS.items()
    }


@router.post("/mappings", status_code=201, summary="Mapping-Vorlage speichern (neue Version)")
async def create_mapping(
    body: MappingIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> MappingOut:
    known = {f.name for f in FIELDS[body.report_type]}
    unknown = sorted(set(body.columns) - known)
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannte Zielfelder: {', '.join(unknown)}."
        )
    async with tenant_tx(request, principal) as session:
        previous = (
            await session.scalars(
                select(ImportMapping)
                .where(
                    ImportMapping.report_type == body.report_type, ImportMapping.name == body.name
                )
                .order_by(ImportMapping.version.desc())
            )
        ).all()
        for p in previous:
            p.active = False
        row = ImportMapping(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            version=(previous[0].version + 1) if previous else 1,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        return MappingOut.model_validate(row)


@router.get("/mappings", summary="Mapping-Vorlagen", dependencies=[Depends(strict_query)])
async def list_mappings(
    request: Request,
    report_type: ReportType | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[MappingOut]:
    async with tenant_tx(request, principal) as session:
        query = select(ImportMapping).where(ImportMapping.active.is_(True))
        if report_type:
            query = query.where(ImportMapping.report_type == report_type)
        return [
            MappingOut.model_validate(m)
            for m in (await session.scalars(query.order_by(ImportMapping.name))).all()
        ]


@router.post("/files", status_code=201, summary="Exportdatei einlesen (Staging)")
async def create_source(
    body: SourceIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> SourceOut:
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, body.document_id)
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        headers, rows = svc.read_table(data, document.mime_type, body.sheet, body.header_row)
        source = ImportSourceFile(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            document_id=document.id,
            report_type=body.report_type,
            sheet=body.sheet,
            header_row=body.header_row,
            headers=headers,
            row_count=len(rows),
        )
        session.add(source)
        await session.flush()
        for number, raw in enumerate(rows, start=body.header_row + 1):
            session.add(
                StagingRow(
                    tenant_id=principal.tenant_id,
                    source_file_id=source.id,
                    row_number=number,
                    raw=raw,
                )
            )
        await session.flush()
        return SourceOut.model_validate(source)


@router.get("/files/{source_id}", summary="Stand der Datei")
async def get_source(
    source_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> SourceOut:
    async with tenant_tx(request, principal) as session:
        return SourceOut.model_validate(await _get(session, ImportSourceFile, source_id))


@router.get(
    "/files/{source_id}/rows",
    summary="Zeilen mit Status (Validierungsbericht)",
    dependencies=[Depends(strict_query)],
)
async def rows(
    source_id: uuid.UUID,
    request: Request,
    status: RowStatus | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ),
) -> list[RowOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, ImportSourceFile, source_id)
        query = select(StagingRow).where(StagingRow.source_file_id == source_id)
        if status:
            query = query.where(StagingRow.status == status)
        items = (
            await session.scalars(query.order_by(StagingRow.row_number).offset(offset).limit(limit))
        ).all()
        return [RowOut.model_validate(r) for r in items]


@router.post("/files/{source_id}/validate", summary="Zuordnen und prüfen")
async def validate(
    source_id: uuid.UUID,
    body: ValidateIn,
    request: Request,
    principal: TenantPrincipal = Depends(WRITE),
) -> SourceOut:
    async with tenant_tx(request, principal) as session:
        source = await _get(session, ImportSourceFile, source_id)
        if source.status is FileStatus.APPLIED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Datei wurde bereits übernommen.")
        mapping = await _get(session, ImportMapping, body.mapping_id)
        if mapping.report_type is not source.report_type:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Die Vorlage passt nicht zum Report.")
        counts = await svc.validate(session, source, mapping.columns, mapping.value_maps)
        source.mapping_id, source.status = mapping.id, FileStatus.VALIDATED
        source.report = {"validation": counts, "mapping_version": mapping.version}
        await session.flush()
        await session.refresh(source)
        return SourceOut.model_validate(source)


def _require_validated(source: ImportSourceFile) -> None:
    if source.status is not FileStatus.VALIDATED:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Die Datei ist nicht geprüft oder bereits übernommen."
        )


@router.post("/files/{source_id}/test-run", summary="Testlauf (nichts wird gespeichert)")
async def dry_run(
    source_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> dict[str, Any]:
    _need_domain(principal)
    async with tenant_tx(request, principal) as session:
        source = await _get(session, ImportSourceFile, source_id)
        _require_validated(source)
        nested = await session.begin_nested()
        try:
            report = await svc.run(session, principal, source, None)
        finally:
            await nested.rollback()
        return {"test_run": True, **report}


@router.post("/files/{source_id}/apply", status_code=201, summary="Übernehmen")
async def apply(
    source_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> SourceOut:
    """All valid rows in one transaction, recorded as import run (undo: /imports/{id}/undo)."""
    _need_domain(principal)
    async with tenant_tx(request, principal) as session:
        source = await _get(session, ImportSourceFile, source_id)
        _require_validated(source)
        run_row = ImportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            source=f"immoware24:{source.report_type.value}",
            status=ImportStatus.APPLIED,
            document_ids=[source.document_id],
        )
        session.add(run_row)
        await session.flush()
        report = await svc.run(session, principal, source, run_row)
        run_row.summary = report["counts"]
        source.status, source.import_run_id = FileStatus.APPLIED, run_row.id
        source.report = {
            **source.report,
            "apply": report,
            "reconciliation": await svc.reconcile(session, source),
        }
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="import_run.applied",
            entity_type="import_run",
            entity_id=run_row.id,
            actor_user_id=principal.user_id,
            payload={"source": run_row.source, "rows": source.row_count},
        )
        await session.flush()
        await session.refresh(source)
        return SourceOut.model_validate(source)


@router.get("/files/{source_id}/reconciliation", summary="Abgleichbericht")
async def reconciliation(
    source_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        source = await _get(session, ImportSourceFile, source_id)
        return await svc.reconcile(session, source)


@router.get("/overview", summary="Übersicht Bestand")
async def overview(request: Request, principal: TenantPrincipal = Depends(READ)) -> dict[str, int]:
    """Platform totals to compare with the Immoware24 figures (acceptance M8)."""
    from mhvp.contacts.models import Contact
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import Property, Unit

    async with tenant_tx(request, principal) as session:

        async def count(model: Any, *where: Any) -> int:
            return int(
                await session.scalar(select(func.count()).select_from(model).where(*where)) or 0
            )

        return {
            "properties": await count(Property),
            "units": await count(Unit),
            "contacts": await count(Contact, Contact.deleted_at.is_(None)),
            "contracts": await count(Contract),
        }


# AE37 (Q08-01, M8): header heuristic, stored assignments per tenant and report type,
# validation report before saving a mapping, status of the required exports. Nothing here
# imports, posts or changes master data; a proposal only fills the mapping form.


class ImportHeaderDetectIn(_In):
    document_id: uuid.UUID
    report_type: ReportType
    sheet: str | None = Field(default=None, max_length=100)


class ImportHeaderCandidateOut(BaseModel):
    row: int
    score: int
    filled: int
    text_cells: int
    matched_terms: list[str]
    duplicates: list[str]
    reason: str


class ImportHeaderDetectionOut(BaseModel):
    header_row: int | None
    headers: list[str]
    sheet: str | None
    sheets: list[str]
    rows_scanned: int
    candidates: list[ImportHeaderCandidateOut]


class ImportColAlternativeOut(BaseModel):
    header: str
    score: int
    basis: str


class ImportColFieldProposalOut(BaseModel):
    name: str
    label: str
    required: bool
    header: str | None
    score: int
    basis: str | None
    basis_label: str | None
    status: str
    note: str | None
    alternatives: list[ImportColAlternativeOut]


class ImportColProposalOut(BaseModel):
    report_type: ReportType
    headers: list[str]
    columns: dict[str, str]
    fields: list[ImportColFieldProposalOut]
    unassigned_headers: list[str]
    ignored_headers: list[str]
    missing_required: list[str]
    stored_used: int


class ImportColCheckIn(_In):
    mapping_id: uuid.UUID | None = None
    columns: dict[str, str] | None = None
    value_maps: dict[str, dict[str, str]] | None = None
    sample_size: int | None = Field(default=None, ge=1, le=20)


class ImportColRequiredOut(BaseModel):
    name: str
    label: str
    header: str | None
    status: str
    empty: int


class ImportColFieldStatsOut(BaseModel):
    name: str
    label: str
    header: str | None
    filled: int
    empty: int
    errors: int
    examples: list[str]


class ImportColSampleRowOut(BaseModel):
    row_number: int
    raw: dict[str, Any]
    values: dict[str, Any]
    errors: list[str]


class ImportColCheckOut(BaseModel):
    report_type: ReportType
    rows: int
    valid: int
    invalid: int
    staged_only: bool
    required: list[ImportColRequiredOut]
    fields: list[ImportColFieldStatsOut]
    not_in_file: list[str]
    assigned_twice: list[str]
    unassigned_headers: list[str]
    sample_rows: list[ImportColSampleRowOut]
    error_rows: list[ImportColSampleRowOut]
    ready: bool


class ImportColAssignmentItemIn(_In):
    header: str = Field(min_length=1, max_length=200)
    target_field: str | None = Field(default=None, max_length=63)


class ImportColAssignmentsIn(_In):
    report_type: ReportType
    assignments: list[ImportColAssignmentItemIn] = Field(min_length=1, max_length=200)


class ImportColAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    report_type: ReportType
    header: str
    header_key: str
    target_field: str | None
    use_count: int
    last_used_at: datetime | None
    updated_at: datetime


class ImportExportRequirementOut(BaseModel):
    report_type: ReportType
    source: str
    required_fields: list[str]
    optional_fields: list[str]
    stored_assignments: int
    required_covered: list[str]
    files: int
    last_file_at: datetime | None
    last_headers: int | None
    applied: bool
    status: str


async def _stored(session: Any, report_type: ReportType) -> dict[str, str | None]:
    rows = (
        await session.scalars(
            select(ImportColumnAssignment).where(ImportColumnAssignment.report_type == report_type)
        )
    ).all()
    return {r.header_key: r.target_field for r in rows}


@router.post(
    "/header-detection",
    summary="Kopfzeile einer Exportdatei erkennen (Vorschlag, AE37)",
)
async def header_detection(
    body: ImportHeaderDetectIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> ImportHeaderDetectionOut:
    """Scores the first 30 rows of any CSV or XLSX file; nothing is staged or stored."""
    async with tenant_tx(request, principal) as session:
        document = await _get(session, Document, body.document_id)
        data = BlobStore(request.app.state.settings).get(document.storage_ref)
        head, sheets, sheet = detection.read_head(data, document.mime_type, body.sheet)
        candidates = detection.detect_header_row(
            head, body.report_type, await _stored(session, body.report_type)
        )
    best = candidates[0] if candidates else None
    headers = (
        [str(c).strip() for c in head[best.row - 1] if c is not None and str(c).strip()]
        if best
        else []
    )
    return ImportHeaderDetectionOut(
        header_row=best.row if best else None,
        headers=headers,
        sheet=sheet,
        sheets=sheets,
        rows_scanned=len(head),
        candidates=[ImportHeaderCandidateOut(**asdict(c)) for c in candidates[:5]],
    )


@router.get(
    "/files/{source_id}/column-proposal",
    summary="Spaltenvorschlag je Zielfeld (Kopfzeilenheuristik, AE37)",
)
async def column_proposal(
    source_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> ImportColProposalOut:
    async with tenant_tx(request, principal) as session:
        source = await _get(session, ImportSourceFile, source_id)
        samples = (
            await session.scalars(
                select(StagingRow.raw)
                .where(StagingRow.source_file_id == source.id)
                .order_by(StagingRow.row_number)
                .limit(50)
            )
        ).all()
        stored = await _stored(session, source.report_type)
    return ImportColProposalOut.model_validate(
        detection.propose_columns(source.report_type, list(source.headers), list(samples), stored)
    )


@router.post(
    "/files/{source_id}/check",
    summary="Prüfbericht einer Zuordnung ohne Speichern (Pflichtspalten, Beispielzeilen)",
)
async def check_mapping(
    source_id: uuid.UUID,
    body: ImportColCheckIn,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> ImportColCheckOut:
    if (body.mapping_id is None) == (body.columns is None):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Bitte entweder eine Vorlage oder eine Zuordnung angeben."
        )
    async with tenant_tx(request, principal) as session:
        source = await _get(session, ImportSourceFile, source_id)
        if body.mapping_id is not None:
            mapping = await _get(session, ImportMapping, body.mapping_id)
            if mapping.report_type is not source.report_type:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Die Vorlage passt nicht zum Report."
                )
            columns, value_maps = dict(mapping.columns), dict(mapping.value_maps)
        else:
            columns, value_maps = dict(body.columns or {}), dict(body.value_maps or {})
        known = {f.name for f in FIELDS[source.report_type]}
        unknown = sorted(set(columns) - known)
        if unknown:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Unbekannte Zielfelder: {', '.join(unknown)}."
            )
        rows = (
            await session.execute(
                select(StagingRow.row_number, StagingRow.raw)
                .where(StagingRow.source_file_id == source.id)
                .order_by(StagingRow.row_number)
            )
        ).all()
    report = detection.check_report(
        source.report_type,
        list(source.headers),
        [(r.row_number, r.raw) for r in rows],
        {k: v for k, v in columns.items() if v},
        value_maps,
        body.sample_size or 5,
    )
    return ImportColCheckOut.model_validate(report)


@router.get(
    "/column-assignments",
    summary="Gespeicherte Spaltenzuordnungen je Berichtstyp (AE37)",
    dependencies=[Depends(strict_query)],
)
async def list_column_assignments(
    request: Request,
    report_type: ReportType | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[ImportColAssignmentOut]:
    async with tenant_tx(request, principal) as session:
        query = select(ImportColumnAssignment)
        if report_type:
            query = query.where(ImportColumnAssignment.report_type == report_type)
        rows = (
            await session.scalars(
                query.order_by(ImportColumnAssignment.report_type, ImportColumnAssignment.header)
            )
        ).all()
        return [ImportColAssignmentOut.model_validate(r) for r in rows]


@router.put(
    "/column-assignments",
    summary="Spaltenzuordnungen merken (je Mandant und Berichtstyp, AE37)",
)
async def save_column_assignments(
    body: ImportColAssignmentsIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> list[ImportColAssignmentOut]:
    """Upsert per normalised header; ``target_field`` null: header is deliberately ignored."""
    known = {f.name for f in FIELDS[body.report_type]}
    if not known:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Für diesen Bericht gibt es keine Zielfelder."
        )
    keys: dict[str, ImportColAssignmentItemIn] = {}
    for item in body.assignments:
        key = detection.header_key(item.header)
        if not key:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Spaltenüberschrift {item.header!r} ist leer."
            )
        if key in keys:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Spaltenüberschrift {item.header!r} ist mehrfach angegeben.",
            )
        if item.target_field is not None and item.target_field not in known:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Unbekanntes Zielfeld: {item.target_field}."
            )
        keys[key] = item
    now = datetime.now(UTC)
    async with tenant_tx(request, principal) as session:
        model = ImportColumnAssignment
        for key, item in keys.items():
            statement = pg_insert(model).values(
                tenant_id=principal.tenant_id,
                report_type=body.report_type,
                header_key=key,
                header=item.header.strip(),
                target_field=item.target_field,
                use_count=1,
                last_used_at=now,
                created_by=principal.user_id,
                updated_by=principal.user_id,
            )
            await session.execute(
                statement.on_conflict_do_update(
                    constraint="uq_import_column_assignment_header",
                    set_={
                        "header": statement.excluded.header,
                        "target_field": statement.excluded.target_field,
                        "use_count": model.use_count + 1,
                        "last_used_at": now,
                        "updated_by": principal.user_id,
                        "updated_at": func.now(),
                    },
                )
            )
        rows = (
            await session.scalars(
                select(ImportColumnAssignment)
                .where(ImportColumnAssignment.report_type == body.report_type)
                .order_by(ImportColumnAssignment.header)
                .execution_options(populate_existing=True)
            )
        ).all()
        return [ImportColAssignmentOut.model_validate(r) for r in rows]


@router.delete(
    "/column-assignments/{assignment_id}",
    status_code=204,
    summary="Gespeicherte Spaltenzuordnung entfernen (AE37)",
)
async def delete_column_assignment(
    assignment_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, ImportColumnAssignment, assignment_id)
        await session.delete(row)
        await session.flush()
    return Response(status_code=204)


@router.get(
    "/export-requirements",
    summary="Stand der benötigten Exporte je Berichtstyp (Anforderungsliste, AE37)",
    dependencies=[Depends(strict_query)],
)
async def export_requirements(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[ImportExportRequirementOut]:
    """Per report type: required and optional target fields, stored assignments, staged and
    applied files. The export itself (menu path, format, header) stays to be confirmed by the
    operator in ``docs/integrations/immoware24-exporte.md``."""
    async with tenant_tx(request, principal) as session:
        assignments = (await session.scalars(select(ImportColumnAssignment))).all()
        files = (
            await session.execute(
                select(
                    ImportSourceFile.report_type,
                    ImportSourceFile.status,
                    ImportSourceFile.created_at,
                    func.cardinality(ImportSourceFile.headers),
                ).order_by(ImportSourceFile.created_at)
            )
        ).all()
    result = []
    for report_type in ReportType:
        fields = FIELDS.get(report_type, ())
        required = [f.name for f in fields if f.required]
        own = [a for a in assignments if a.report_type is report_type]
        covered = sorted({a.target_field for a in own if a.target_field in required})
        own_files = [f for f in files if f[0] is report_type]
        applied = any(f[1] is FileStatus.APPLIED for f in own_files)
        if applied:
            status = "applied"
        elif not own_files:
            status = "file_missing"
        elif len(covered) < len(required):
            status = "mapping_open"
        else:
            status = "mapping_stored"
        result.append(
            ImportExportRequirementOut(
                report_type=report_type,
                source=detection.SPEC_SOURCES.get(report_type, ""),
                required_fields=required,
                optional_fields=[f.name for f in fields if not f.required],
                stored_assignments=len(own),
                required_covered=covered,
                files=len(own_files),
                last_file_at=own_files[-1][2] if own_files else None,
                last_headers=own_files[-1][3] if own_files else None,
                applied=applied,
                status=status,
            )
        )
    return result
