"""Evaluations with common header, XLSX output, draft VAT overview, procedure documentation,
tax flags per account and the rule version register (7.7, 7.12, M18-01 to M18-09, SA-07,
S711-11). Reading needs ``accounting:read``, files need ``accounting:export`` and changes of
tax flags or the register need ``accounting:approve`` (a person decides, never a job)."""

import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import procedure_doc, report_views, report_xlsx, reports
from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    AccountCategory,
    ExportRun,
    Ledger,
    LedgerAccount,
    RuleVersion,
)
from mhvp.accounting.schemas import AccountOut
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed, property_column_guard
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

# M2-02/S16-02: reports of a ledger outside the property assignment answer 404.
router = APIRouter(
    prefix="/accounting",
    tags=["Buchhaltung"],
    dependencies=[Depends(property_column_guard({"ledger_id": Ledger.property_id}))],
)
READ = require_permission("accounting:read")
EXPORT = require_permission("accounting:export")
APPROVE = require_permission("accounting:approve")

ReportName = Literal[
    "journal",
    "monthly_matrix",
    "target_actual",
    "trial_balance",
    "open_items",
    "revenue",
    "vat_overview",
    "income_expense",
]


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID) -> Ledger:
    ledger = await session.scalar(select(Ledger).where(Ledger.id == ledger_id))
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return ledger


def _period(start: date, end: date) -> None:
    if end < start:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Zeitraumende liegt vor dem Beginn.")


# Evaluations with header ---------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/reports/monthly-matrix", summary="Monatsmatrix (M18-01)")
async def report_monthly_matrix(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    categories: list[AccountCategory] | None = Query(default=None),
    eur_only: bool = False,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return await report_views.monthly_matrix(session, ledger, start, end, categories, eur_only)


@router.get("/ledgers/{ledger_id}/reports/target-actual", summary="Soll/Ist der Forderungen")
async def report_target_actual(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    unit_id: uuid.UUID | None = None,
    component: str | None = Query(default=None, max_length=63),
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _period(start, end)
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return await report_views.target_actual(session, ledger, start, end, unit_id, component)


@router.get("/ledgers/{ledger_id}/reports/bank-statement", summary="Bankkontoabrechnung")
async def report_bank_statement(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _period(start, end)
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return await report_views.bank_statement(session, ledger, account_id, start, end)


@router.get("/ledgers/{ledger_id}/reports/vat-overview", summary="USt-Übersicht (Entwurf)")
async def report_vat_overview(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return await report_views.vat_overview(session, ledger, start, end)


@router.get(
    "/ledgers/{ledger_id}/reports/vat-overview-by-property",
    summary="USt-Übersicht je Objekt und Kostenstelle (Entwurf)",
)
async def report_vat_overview_by_property(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _period(start, end)
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return await report_views.vat_overview_by_property(session, ledger, start, end)


@router.get(
    "/ledgers/{ledger_id}/reports/income-expense",
    summary="Einnahmen und Ausgaben (keine EÜR)",
)
async def report_income_expense(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    eur_only: bool = False,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return await report_views.income_expense(session, ledger, start, end, eur_only)


@router.get("/ledgers/{ledger_id}/reports/revenue", summary="Erträge mit Kopfangaben")
async def report_revenue(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _period(start, end)
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return {
            "header": await report_views.report_header(
                session, ledger, report="revenue", start=start, end=end
            ),
            "rows": await reports.revenue(session, ledger, start, end),
        }


@router.get(
    "/ledgers/{ledger_id}/reports/payments-by-debtor", summary="Zahlungen je Debitor mit Kopf"
)
async def report_payments_by_debtor(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _period(start, end)
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return {
            "header": await report_views.report_header(
                session, ledger, report="payments_by_debtor", start=start, end=end
            ),
            "rows": await reports.payments_by_debtor(session, ledger, start, end),
        }


@router.get("/ledgers/{ledger_id}/reports/trial-balance", summary="Saldenliste mit Kopfangaben")
async def report_trial_balance(
    ledger_id: uuid.UUID,
    as_of: date,
    request: Request,
    start: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        data = await acc.trial_balance(session, ledger, as_of, start)
        return {
            "header": await report_views.report_header(
                session, ledger, report="trial_balance", start=start, end=as_of, as_of=as_of
            ),
            **data,
        }


@router.get("/ledgers/{ledger_id}/reports/open-items", summary="OP-Liste mit Kopfangaben")
async def report_open_items(
    ledger_id: uuid.UUID,
    as_of: date,
    request: Request,
    account_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return {
            "header": await report_views.report_header(
                session,
                ledger,
                report="open_items",
                as_of=as_of,
                filters={"account_id": str(account_id) if account_id else None},
            ),
            "rows": await acc.open_items(session, ledger, as_of, account_id),
        }


@router.get("/ledgers/{ledger_id}/reports/account-sheet", summary="Kontenblatt mit Kopfangaben")
async def report_account_sheet(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    _period(start, end)
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        account = await session.get(LedgerAccount, account_id)
        if account is None or account.ledger_id != ledger.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return {
            "header": await report_views.report_header(
                session,
                ledger,
                report="account_sheet",
                start=start,
                end=end,
                filters={"account": f"{account.number} {account.name}"},
            ),
            **await acc.account_sheet(session, account, start, end),
        }


@router.get("/ledgers/{ledger_id}/reports/xlsx", summary="Auswertung oder Journal als Excel")
async def report_xlsx_download(
    ledger_id: uuid.UUID,
    report: ReportName,
    request: Request,
    start: date | None = None,
    end: date | None = None,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(EXPORT),
) -> Response:
    today = local_today()
    period_start = start or date(today.year, 1, 1)
    period_end = end or today
    _period(period_start, period_end)
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        reports.ensure_ledger_in_scope(session, ledger)
        data, rows = await report_xlsx.build_report_xlsx(
            session,
            ledger,
            report,
            start=period_start,
            end=period_end,
            as_of=as_of or period_end,
        )
        run = ExportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            format=f"xlsx_{report}"[:32],
            period_from=period_start,
            period_to=period_end,
            rows=rows,
            sha256=reports.checksum(data),
        )
        session.add(run)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="export_run.created",
            entity_type="export_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"format": run.format, "rows": rows},
        )
    filename = f"{report}-{period_start:%Y%m%d}-{period_end:%Y%m%d}.xlsx"
    return Response(
        content=data,
        media_type=report_xlsx.XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Content-SHA256": run.sha256,
        },
    )


@router.get(
    "/ledgers/{ledger_id}/procedure-documentation",
    summary="Verfahrensdokumentation als Entwurf aus dem Betrieb (M18-07)",
)
async def procedure_documentation(
    ledger_id: uuid.UUID,
    request: Request,
    download: bool = False,
    principal: TenantPrincipal = Depends(EXPORT),
) -> Response:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        resolver = request.app.state.release_gate_resolver
        facts = await procedure_doc.collect_facts(session, ledger, resolver)
        text = procedure_doc.render(ledger, facts, datetime.now(UTC))
        data = text.encode("utf-8")
        if download:
            run = ExportRun(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                ledger_id=ledger.id,
                format="procedure_doc",
                period_from=local_today(),
                period_to=local_today(),
                rows=text.count("\n"),
                sha256=reports.checksum(data),
                note="Entwurf, nicht freigegeben",
            )
            session.add(run)
            await session.flush()
    headers = {"X-Draft": "true"}
    if download:
        headers["Content-Disposition"] = (
            f"attachment; filename*=UTF-8''{quote('verfahrensdokumentation-entwurf.md')}"
        )
    return Response(content=data, media_type="text/markdown; charset=utf-8", headers=headers)


# Tax flags per account (SA-07) -----------------------------------------------------------


class AccountTaxFlagsIn(BaseModel):
    """Plain flags entered by a person. No tax treatment follows from them (V8, P03 open)."""

    model_config = ConfigDict(extra="forbid")
    eur_relevant: bool
    ust_relevant: bool
    mixed_use_review: bool = False


@router.put(
    "/ledgers/{ledger_id}/accounts/{account_id}/tax-flags",
    summary="EÜR- und USt-Kennzeichen je Konto setzen",
)
async def set_account_tax_flags(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    body: AccountTaxFlagsIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> AccountOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        account = await session.get(LedgerAccount, account_id)
        if account is None or account.ledger_id != ledger.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        before = {
            "eur_relevant": account.eur_relevant,
            "ust_relevant": account.ust_relevant,
            "mixed_use_review": account.mixed_use_review,
        }
        after = body.model_dump()
        if before != after:
            account.eur_relevant = body.eur_relevant
            account.ust_relevant = body.ust_relevant
            account.mixed_use_review = body.mixed_use_review
            account.updated_by = principal.user_id
            await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="ledger_account.tax_flags_changed",
                entity_type="ledger_account",
                entity_id=account.id,
                actor_user_id=principal.user_id,
                payload={"number": account.number},
                changes={
                    k: {"from": before[k], "to": after[k]} for k in after if before[k] != after[k]
                },
            )
        return AccountOut.model_validate(account)


# Rule version register (S711-11, 7.12) -----------------------------------------------------


class RuleVersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_id: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=200)
    effective_from: date
    effective_to: date | None = None
    case_groups: list[str] = Field(default_factory=list, max_length=30)
    source_status: str = Field(default="", max_length=200)
    change_reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _period(self) -> "RuleVersionIn":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not lie before effective_from")
        return self


class RuleVersionConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed_by: str = Field(min_length=3, max_length=200)
    confirmed_on: date


class RuleVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rule_id: str
    version: int
    title: str
    effective_from: date
    effective_to: date | None
    case_groups: list[str]
    source_status: str
    change_reason: str
    status: str
    expert_confirmed_by: str | None
    expert_confirmed_on: date | None
    created_at: datetime


async def _rule_version(session: AsyncSession, version_id: uuid.UUID) -> RuleVersion:
    row = await session.get(RuleVersion, version_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.get(
    "/rule-versions",
    summary="Regelversionen mit Wirksamkeitsdatum",
    dependencies=[Depends(strict_query)],
)
async def list_rule_versions(
    request: Request,
    rule_id: str | None = Query(default=None, max_length=60),
    principal: TenantPrincipal = Depends(READ),
) -> list[RuleVersionOut]:
    async with tenant_tx(request, principal) as session:
        query = select(RuleVersion).order_by(
            RuleVersion.rule_id, RuleVersion.effective_from, RuleVersion.version
        )
        if rule_id:
            query = query.where(RuleVersion.rule_id == rule_id)
        return [RuleVersionOut.model_validate(r) for r in await session.scalars(query)]


@router.get(
    "/rule-versions/due-checkpoints",
    summary="Fällige Prüfpunkte als Hinweis",
    dependencies=[Depends(strict_query)],
)
async def due_rule_checkpoints(
    request: Request,
    on: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[RuleVersionOut]:
    """GA08-02: dated check points (group Prüfpunkt) that are due; hint only, no lock."""
    from mhvp.accounting import rule_register

    async with tenant_tx(request, principal) as session:
        rows = (await session.scalars(select(RuleVersion))).all()
        due = rule_register.due_checkpoints(rows, on or local_today())
        return [RuleVersionOut.model_validate(r) for r in due]


@router.get("/rule-versions/effective", summary="Wirksame Regelversion zu einem Datum")
async def effective_rule_version(
    request: Request,
    rule_id: str = Query(max_length=60),
    on: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> RuleVersionOut:
    day = on or local_today()
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(
            select(RuleVersion)
            .where(
                RuleVersion.rule_id == rule_id,
                RuleVersion.status != "withdrawn",
                RuleVersion.effective_from <= day,
                (RuleVersion.effective_to.is_(None)) | (RuleVersion.effective_to >= day),
            )
            .order_by(RuleVersion.effective_from.desc(), RuleVersion.version.desc())
            .limit(1)
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return RuleVersionOut.model_validate(row)


@router.post("/rule-versions/seed-checkpoints", summary="Datierte Prüfpunkte als Entwurf anlegen")
async def seed_rule_checkpoints(
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> list[RuleVersionOut]:
    """GA08-02/03: HeizkostenV §§ 5 und 12 and CO2KostAufG §§ 5a to 5d as draft entries with a
    note and no legal consequence (7.10 H03, H05). Existing entries are kept."""
    from mhvp.accounting import rule_register

    async with tenant_tx(request, principal) as session:
        rows = await rule_register.seed_checkpoints(
            session, tenant_id=principal.tenant_id, user_id=principal.user_id, today=local_today()
        )
        return [RuleVersionOut.model_validate(r) for r in rows]


@router.post("/rule-versions", status_code=201, summary="Regelversion als Entwurf erfassen")
async def create_rule_version(
    body: RuleVersionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> RuleVersionOut:
    async with tenant_tx(request, principal) as session:
        latest = await session.execute(
            select(func.max(RuleVersion.version), func.max(RuleVersion.effective_from)).where(
                RuleVersion.rule_id == body.rule_id
            )
        )
        version, latest_from = latest.one()
        if latest_from is not None and body.effective_from <= latest_from:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Das Wirksamkeitsdatum muss nach dem der letzten Version liegen "
                    f"({latest_from:%d.%m.%Y})."
                ),
            )
        row = RuleVersion(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            version=int(version or 0) + 1,
            status="draft",
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="rule_version.created",
            entity_type="rule_version",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"rule_id": row.rule_id, "version": row.version},
        )
        return RuleVersionOut.model_validate(row)


@router.post("/rule-versions/{version_id}/confirm", summary="Fachkundige Bestätigung erfassen")
async def confirm_rule_version(
    version_id: uuid.UUID,
    body: RuleVersionConfirmIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> RuleVersionOut:
    async with tenant_tx(request, principal) as session:
        row = await _rule_version(session, version_id)
        if row.status != "draft":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur ein Entwurf kann bestätigt werden.")
        row.status = "confirmed"
        row.expert_confirmed_by = body.confirmed_by
        row.expert_confirmed_on = body.confirmed_on
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="rule_version.confirmed",
            entity_type="rule_version",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"rule_id": row.rule_id, "version": row.version},
        )
        return RuleVersionOut.model_validate(row)


@router.post("/rule-versions/{version_id}/withdraw", summary="Regelversion zurückziehen")
async def withdraw_rule_version(
    version_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> RuleVersionOut:
    async with tenant_tx(request, principal) as session:
        row = await _rule_version(session, version_id)
        if row.status == "withdrawn":
            return RuleVersionOut.model_validate(row)
        row.status = "withdrawn"
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="rule_version.withdrawn",
            entity_type="rule_version",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"rule_id": row.rule_id, "version": row.version},
        )
        return RuleVersionOut.model_validate(row)
