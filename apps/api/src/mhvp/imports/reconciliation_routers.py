"""Reconciliation reports of the parallel operation (/api/v1/imports/reconciliation-reports,
13.1, A68). Read and compare only; nothing is posted or corrected."""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from mhvp.ai.models import ImportRun
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.imports import reconciliation as rec

router = APIRouter(prefix="/imports/reconciliation-reports", tags=["Import Immoware24"])
# The report shows bank balances, account balances and open items per property: accounting
# data, so the accounting permissions apply (Sicherheitsreview 1.22, Befund 3).
READ = require_permission("accounting:read")
WRITE = require_permission("accounting:create")


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportIn(_In):
    as_of: date | None = None
    source_file_ids: list[uuid.UUID] | None = Field(default=None, max_length=10)


class ColumnsIn(_In):
    columns: dict[str, dict[str, str]]


class ColumnFieldOut(BaseModel):
    name: str
    label: str
    required: bool


class ColumnsOut(BaseModel):
    columns: dict[str, dict[str, str]]
    defaults: dict[str, dict[str, str]]
    customised: bool
    fields: dict[str, list[ColumnFieldOut]]


class ReportListOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    as_of: str | None
    trigger: str | None
    totals: dict[str, int]
    sources: list[dict[str, Any]]


class ReconciliationReportOut(ReportListOut):
    counts: dict[str, int]
    warnings: list[str]
    columns: dict[str, dict[str, str]]
    properties: list[dict[str, Any]]
    lines: list[dict[str, Any]]


def _list_out(run: ImportRun) -> ReportListOut:
    s = run.summary
    return ReportListOut(
        id=run.id,
        created_at=run.created_at,
        as_of=s.get("as_of"),
        trigger=s.get("trigger"),
        totals=s.get("totals", {}),
        sources=s.get("sources", []),
    )


def _out(run: ImportRun) -> ReconciliationReportOut:
    s = run.summary
    return ReconciliationReportOut(
        **_list_out(run).model_dump(),
        counts=s.get("counts", {}),
        warnings=s.get("warnings", []),
        columns=s.get("columns", {}),
        properties=s.get("properties", []),
        lines=s.get("lines", []),
    )


async def _get_report(session: Any, report_id: uuid.UUID) -> ImportRun:
    run: ImportRun | None = await session.get(ImportRun, report_id)
    if run is None or run.source != rec.RECONCILIATION_SOURCE:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return run


@router.get("", summary="Abgleichberichte")
async def list_reports(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    principal: TenantPrincipal = Depends(READ),
) -> list[ReportListOut]:
    async with tenant_tx(request, principal) as session:
        runs = (
            await session.scalars(
                select(ImportRun)
                .where(ImportRun.source == rec.RECONCILIATION_SOURCE)
                .order_by(ImportRun.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [_list_out(r) for r in runs]


@router.post("", status_code=201, summary="Abgleichbericht jetzt erstellen")
async def create_report(
    body: ReportIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> ReconciliationReportOut:
    """Compares the newest staged journal and bank rows (or the given files) with the
    platform as of ``as_of`` (default: newest booking date of the rows). Read only."""
    async with tenant_tx(request, principal) as session:
        run = await rec.create_report(
            session,
            principal.tenant_id,
            principal.user_id,
            as_of=body.as_of,
            source_file_ids=body.source_file_ids,
            trigger="manual",
        )
        await session.refresh(run)
        return _out(run)


@router.get("/columns", summary="Spaltenzuordnung des Abgleichs")
async def get_columns(request: Request, principal: TenantPrincipal = Depends(READ)) -> ColumnsOut:
    async with tenant_tx(request, principal) as session:
        columns, customised = await rec.load_columns(session)
    return ColumnsOut(
        columns=columns,
        defaults=rec.DEFAULT_COLUMNS,
        customised=customised,
        fields={
            rt: [ColumnFieldOut(name=f.name, label=f.label, required=f.required) for f in fields]
            for rt, fields in rec.COLUMN_FIELDS.items()
        },
    )


@router.put("/columns", summary="Spaltenzuordnung des Abgleichs speichern")
async def put_columns(
    body: ColumnsIn, request: Request, principal: TenantPrincipal = Depends(WRITE)
) -> ColumnsOut:
    async with tenant_tx(request, principal) as session:
        await rec.store_columns(session, principal.tenant_id, principal.user_id, body.columns)
        columns, customised = await rec.load_columns(session)
    return ColumnsOut(
        columns=columns,
        defaults=rec.DEFAULT_COLUMNS,
        customised=customised,
        fields={
            rt: [ColumnFieldOut(name=f.name, label=f.label, required=f.required) for f in fields]
            for rt, fields in rec.COLUMN_FIELDS.items()
        },
    )


@router.get("/{report_id}", summary="Abgleichbericht (JSON)")
async def get_report(
    report_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> ReconciliationReportOut:
    async with tenant_tx(request, principal) as session:
        return _out(await _get_report(session, report_id))


@router.get("/{report_id}/csv", summary="Abgleichbericht (CSV)", response_class=Response)
async def get_report_csv(
    report_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        run = await _get_report(session, report_id)
        text = rec.report_csv(run.summary)
        as_of = run.summary.get("as_of") or run.created_at.date().isoformat()
    return Response(
        content=text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="abgleich-{as_of}.csv"'},
    )
