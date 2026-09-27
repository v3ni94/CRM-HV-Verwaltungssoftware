"""DATEV batch self check endpoints (/api/v1/accounting/datev/..., M18-01, gate G1).

``POST /exports/{id}/check`` runs ``mhvp.accounting.datev_check`` on the stored file of a DATEV
export run and keeps the report on the run; ``GET .../check`` returns the stored report as JSON
or text; ``POST /check-file`` checks a pasted or uploaded file without storing anything;
``GET /sample-batch`` hands out the 20 line test batch for the import test at the tax advisor.
Reading needs ``accounting:read``, the stored check ``accounting:export`` like the export.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import datev_check
from mhvp.accounting.models import ExportRun, Ledger
from mhvp.accounting.reports import ensure_ledger_in_scope
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/accounting/datev", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
EXPORT = require_permission("accounting:export")

DATEV_FORMAT = "datev_buchungsstapel"


class ExportRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ledger_id: uuid.UUID
    period_from: Any
    period_to: Any
    rows: int
    sha256: str
    note: str | None
    created_at: datetime
    checked_at: datetime | None
    check_status: str | None = None
    has_content: bool = False


class CheckOut(BaseModel):
    export_id: uuid.UUID | None
    checked_at: datetime | None
    report: dict[str, Any]
    text: str


class FileCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=5_000_000)


def _run_out(run: ExportRun) -> ExportRunOut:
    return ExportRunOut(
        id=run.id,
        ledger_id=run.ledger_id,
        period_from=run.period_from,
        period_to=run.period_to,
        rows=run.rows,
        sha256=run.sha256,
        note=run.note,
        created_at=run.created_at,
        checked_at=run.checked_at,
        check_status=(run.check_report or {}).get("status"),
        has_content=run.content is not None,
    )


async def _run(session: AsyncSession, export_id: uuid.UUID) -> ExportRun:
    run = await session.scalar(
        select(ExportRun).where(ExportRun.id == export_id, ExportRun.format == DATEV_FORMAT)
    )
    if run is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ledger = await session.get(Ledger, run.ledger_id)
    if ledger is not None:
        ensure_ledger_in_scope(session, ledger)
    return run


@router.get("/exports", summary="DATEV-Exporte des Mandanten")
async def list_exports(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[ExportRunOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ExportRun)
            .where(ExportRun.format == DATEV_FORMAT)
            .order_by(ExportRun.created_at.desc())
            .limit(100)
        )
        return [_run_out(r) for r in rows.all()]


@router.post("/exports/{export_id}/check", summary="Buchungsstapel formal prüfen")
async def check_export(
    export_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(EXPORT)
) -> CheckOut:
    async with tenant_tx(request, principal) as session:
        run = await _run(session, export_id)
        if run.content is None:
            raise ProblemError(ErrorCodes.DATEV_EXPORT_CONTENT_MISSING)
        report = datev_check.check_batch(run.content)
        run.check_report = report.as_dict()
        run.checked_at = datetime.now(UTC)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="export_run.checked",
            entity_type="export_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"status": report.status, "errors": report.errors, "warnings": report.warnings},
        )
        await session.flush()
        return CheckOut(
            export_id=run.id,
            checked_at=run.checked_at,
            report=run.check_report,
            text=datev_check.report_text(report),
        )


@router.get("/exports/{export_id}/check", summary="Gespeicherter Prüfbericht", response_model=None)
async def get_check(
    export_id: uuid.UUID,
    request: Request,
    format: Literal["json", "text"] = Query(default="json"),
    principal: TenantPrincipal = Depends(READ),
) -> Response | CheckOut:
    async with tenant_tx(request, principal) as session:
        run = await _run(session, export_id)
        if run.check_report is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND,
                detail="Für diesen Export liegt kein Prüfbericht vor.",
            )
        text = (
            datev_check.report_text(datev_check.check_batch(run.content))
            if run.content is not None
            else ""
        )
        if format == "text":
            return Response(
                text.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={"content-disposition": f"attachment; filename=pruefbericht-{run.id}.txt"},
            )
        return CheckOut(
            export_id=run.id, checked_at=run.checked_at, report=run.check_report, text=text
        )


@router.get("/exports/{export_id}/download", summary="Exportdatei herunterladen")
async def download_export(
    export_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        run = await _run(session, export_id)
        if run.content is None:
            raise ProblemError(ErrorCodes.DATEV_EXPORT_CONTENT_MISSING)
        name = f"EXTF_Buchungsstapel_{run.period_from:%Y%m%d}_{run.period_to:%Y%m%d}.csv"
        return Response(
            run.content.encode("utf-8"),
            media_type="text/csv; charset=utf-8",
            headers={"content-disposition": f"attachment; filename={name}"},
        )


@router.post("/check-file", summary="Beliebigen Buchungsstapel formal prüfen (ohne Speicherung)")
async def check_file(
    body: FileCheckIn, request: Request, principal: TenantPrincipal = Depends(READ)
) -> CheckOut:
    report = datev_check.check_batch(body.content)
    return CheckOut(
        export_id=None,
        checked_at=None,
        report=report.as_dict(),
        text=datev_check.report_text(report),
    )


async def _sample(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    from mhvp.platform.models import ChartOfAccountsKind, TenantBillingSettings

    settings = await session.scalar(
        select(TenantBillingSettings).where(TenantBillingSettings.tenant_id == tenant_id)
    )
    today = local_today()
    chart = (
        settings.datev_chart_of_accounts.value.upper()
        if settings and settings.datev_chart_of_accounts is not ChartOfAccountsKind.UNSET
        else "SKR03"
    )
    return datev_check.sample_batch(
        consultant_number=(settings.datev_consultant_number if settings else None) or "1234567",
        client_number=(settings.datev_client_number if settings else None) or "12345",
        chart_of_accounts=chart,
        account_length=(settings.datev_account_length if settings else None) or 4,
        fiscal_year_start=today.replace(month=1, day=1),
        date_from=today.replace(month=1, day=1),
        date_to=today.replace(month=12, day=31),
        generated=f"{today:%Y%m%d}000000000",
    )


@router.get(
    "/sample-batch",
    summary="Testdatei mit 20 fiktiven Buchungen für den Importtest",
    response_model=None,
)
async def sample_batch(
    request: Request,
    format: Literal["csv", "check"] = Query(default="csv"),
    principal: TenantPrincipal = Depends(READ),
) -> Response | CheckOut:
    """Uses the tenant's consultant and client numbers when set, otherwise placeholder numbers
    that the tax advisor replaces. Every booking is fictional and marked as Testbuchung."""
    async with tenant_tx(request, principal) as session:
        content = await _sample(session, principal.tenant_id)
    if format == "check":
        report = datev_check.check_batch(content)
        return CheckOut(
            export_id=None,
            checked_at=None,
            report=report.as_dict(),
            text=datev_check.report_text(report),
        )
    return Response(
        content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": "attachment; filename=EXTF_Buchungsstapel_Importtest.csv"},
    )
