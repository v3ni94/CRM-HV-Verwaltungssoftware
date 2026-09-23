"""Import assistant endpoints (/api/v1/imports/immoware24, 13.1)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document
from mhvp.imports import services as svc
from mhvp.imports.fields import FIELDS
from mhvp.imports.models import (
    FileStatus,
    ImportMapping,
    ImportSourceFile,
    ReportType,
    RowStatus,
    StagingRow,
)

router = APIRouter(prefix="/imports/immoware24", tags=["Import Immoware24"])
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


@router.get("/mappings", summary="Mapping-Vorlagen")
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


@router.get("/files/{source_id}/rows", summary="Zeilen mit Status (Validierungsbericht)")
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
