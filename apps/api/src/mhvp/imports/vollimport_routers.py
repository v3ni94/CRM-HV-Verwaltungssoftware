"""Full import of the Immoware24 exports with cut-off date (/api/v1/imports/immoware24/vollimport,
13.1, M8-01, M8-02, V9). Pre-check and dry run write nothing; apply records an ``ImportRun``
(source ``immoware24:vollimport``, undo of created objects, units and contacts as usual) and
stores the reconciliation as ``ImportFullRun``; the report is served as JSON and PDF draft.
"""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from mhvp.ai.imports import Recorder
from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.auth.scope import property_unrestricted_guard
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.uploads import read_limited
from mhvp.imports import objektdaten, vollimport
from mhvp.imports.models import FullRunStatus, ImportFullRun
from mhvp.imports.routers import READ, WRITE, _need_domain
from mhvp.platform.models import Tenant

router = APIRouter(
    prefix="/imports/immoware24/vollimport",
    tags=["Import Immoware24"],
    dependencies=[Depends(property_unrestricted_guard)],  # Y01, M2-02
)
MODE = Query(default="preview", pattern="^(preview|apply|abgleich)$")


class ExportKindOut(BaseModel):
    kind: str
    label: str
    columns: list[str]
    required: list[str]
    reconciled: bool


class FullRunListOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    status: str
    cutoff_date: date
    files: list[dict[str, Any]]
    differences: int
    duration_ms: int
    import_run_id: uuid.UUID | None


class FullRunOut(FullRunListOut):
    counts: dict[str, Any]
    report: dict[str, Any]
    opening_balances: dict[str, Any]


def _list_out(run: ImportFullRun) -> FullRunListOut:
    return FullRunListOut(
        id=run.id,
        created_at=run.created_at,
        status=run.status.value,
        cutoff_date=run.cutoff_date,
        files=run.files,
        differences=run.differences,
        duration_ms=run.duration_ms,
        import_run_id=run.import_run_id,
    )


def _out(run: ImportFullRun) -> FullRunOut:
    return FullRunOut(
        **_list_out(run).model_dump(),
        counts=run.counts,
        report=run.report,
        opening_balances=run.opening_balances,
    )


async def _uploads(files: list[UploadFile], kinds: list[str]) -> list[vollimport.Upload]:
    if len(files) != len(kinds):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Je Datei ist genau ein Exporttyp anzugeben."
        )
    out: list[vollimport.Upload] = []
    for upload, kind in zip(files, kinds, strict=True):
        kind = kind.strip().lower()
        if kind not in vollimport.EXPORT_KINDS:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Exporttyp {kind!r} unbekannt ({', '.join(vollimport.EXPORT_KINDS)}).",
            )
        data = await read_limited(
            upload,
            vollimport.MAX_BYTES,
            detail=f"{upload.filename or 'Die Datei'} ist zu groß.",
        )
        out.append(vollimport.Upload(upload.filename or kind, kind, data))
    return out


def _number_map(text: str) -> dict[str, str]:
    try:
        return objektdaten._parse_number_map(text.replace("\n", ",").split(","))
    except Exception as exc:  # argparse.ArgumentTypeError or ValueError
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=str(exc) or "Nummernzuordnung unlesbar."
        ) from exc


@router.get(
    "/exporttypen",
    summary="Bekannte Immoware24-Exporttypen mit erwarteten Spalten",
    dependencies=[Depends(strict_query)],
)
async def export_kinds(principal: TenantPrincipal = Depends(READ)) -> list[ExportKindOut]:
    return [
        ExportKindOut(
            kind=k.kind,
            label=k.label,
            columns=list(k.columns),
            required=list(k.required),
            reconciled=k.reconciled,
        )
        for k in vollimport.EXPORT_KINDS.values()
    ]


@router.post("/vorpruefung", summary="Vorprüfung der Exportdateien ohne Datenbankzugriff")
async def precheck_files(
    files: list[UploadFile] = File(),
    kinds: list[str] = Form(),
    principal: TenantPrincipal = Depends(WRITE),
) -> dict[str, Any]:
    """Encoding, delimiter, header comparison, row count, duplicate keys, missing required
    fields and SHA-256 per file. Nothing is written."""
    _need_domain(principal)
    uploads = await _uploads(files, kinds)
    checks = [vollimport.precheck(u).as_dict() for u in uploads]
    return {"ok": all(c["ok"] for c in checks), "vorpruefung": checks}


@router.post("", summary="Vollimport mit Stichtag: Trockenlauf, Übernahme oder Abgleich")
async def run_full_import(
    request: Request,
    mode: str = MODE,
    cutoff_date: date = Form(),
    files: list[UploadFile] = File(),
    kinds: list[str] = Form(),
    number_map: str = Form(default=""),
    skip_handed_over: bool = Form(default=False),
    update_existing: bool = Form(default=False),
    principal: TenantPrincipal = Depends(WRITE),
) -> dict[str, Any]:
    """``mode=preview`` runs everything in a rolled back savepoint (nothing is stored),
    ``mode=apply`` imports, reconciles and stores the run, ``mode=abgleich`` only reconciles
    and stores the run. ``update_existing`` lets a repeated import update object names, unit
    labels and locations instead of reporting them as conflict (management type never)."""
    _need_domain(principal)
    uploads = await _uploads(files, kinds)
    mapping = _number_map(number_map)
    async with tenant_tx(request, principal) as session:
        if mode == "preview":
            nested = await session.begin_nested()
            try:
                result = await vollimport.run_full(
                    session,
                    principal.tenant_id,
                    principal.user_id,
                    uploads,
                    cutoff=cutoff_date,
                    mode=mode,
                    number_map=mapping,
                    skip_handed_over=skip_handed_over,
                    update_existing=update_existing,
                )
            finally:
                await nested.rollback()
            return {"apply": False, "id": None, **result.as_dict()}
        recorder: Recorder | None = None
        run_row: ImportRun | None = None
        if mode == "apply":
            run_row = ImportRun(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                source=vollimport.SOURCE,
                status=ImportStatus.APPLIED,
                document_ids=[],
            )
            session.add(run_row)
            await session.flush()
            recorder = Recorder(session, run_row)
        result = await vollimport.run_full(
            session,
            principal.tenant_id,
            principal.user_id,
            uploads,
            cutoff=cutoff_date,
            mode=mode,
            number_map=mapping,
            skip_handed_over=skip_handed_over,
            update_existing=update_existing,
            recorder=recorder,
        )
        if result.aborted:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Vorprüfung fehlgeschlagen, es wurde nichts übernommen.",
                extensions={"vorpruefung": [p.as_dict() for p in result.prechecks]},
            )
        report = result.as_dict()
        if run_row is not None:
            run_row.summary = {"counts": result.counts, "stichtag": cutoff_date.isoformat()}
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="import_run.applied",
                entity_type="import_run",
                entity_id=run_row.id,
                actor_user_id=principal.user_id,
                payload={"source": vollimport.SOURCE, "counts": result.counts},
            )
        full = ImportFullRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            status=FullRunStatus.APPLIED if mode == "apply" else FullRunStatus.RECONCILED,
            cutoff_date=cutoff_date,
            files=result.files(),
            counts=result.counts,
            report={k: v for k, v in report.items() if k not in ("eroeffnungssalden", "importe")},
            opening_balances=result.opening_balances,
            differences=result.differences,
            duration_ms=result.duration_ms,
            import_run_id=run_row.id if run_row is not None else None,
        )
        session.add(full)
        await session.flush()
        return {
            "apply": mode == "apply",
            "id": str(full.id),
            "import_run_id": str(run_row.id) if run_row is not None else None,
            **report,
        }


@router.get(
    "", summary="Gespeicherte Vollimport-Läufe und Abgleiche", dependencies=[Depends(strict_query)]
)
async def list_runs(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[FullRunListOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ImportFullRun).order_by(ImportFullRun.created_at.desc()).limit(100)
        )
        return [_list_out(r) for r in rows]


async def _get(session: Any, run_id: uuid.UUID) -> ImportFullRun:
    run = await session.get(ImportFullRun, run_id)
    if run is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return run  # type: ignore[no-any-return]


@router.get("/{run_id}", summary="Abgleichbericht eines Laufs (JSON)")
async def get_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> FullRunOut:
    async with tenant_tx(request, principal) as session:
        return _out(await _get(session, run_id))


@router.get("/{run_id}/pdf", summary="Abgleichbericht eines Laufs als PDF-Entwurf")
async def get_run_pdf(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        run = await _get(session, run_id)
        tenant = await session.get(Tenant, principal.tenant_id)
        name = tenant.name if tenant is not None else ""
        payload = {**run.report, "eroeffnungssalden": run.opening_balances}
        pdf = vollimport.report_pdf(payload, name)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "content-disposition": (
                f'attachment; filename="abgleichbericht-{run.cutoff_date.isoformat()}-entwurf.pdf"'
            )
        },
    )
