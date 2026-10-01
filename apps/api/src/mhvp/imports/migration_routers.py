"""Migration from Immoware24 without parallel operation (/api/v1/imports/migration, 6.9.10,
D11, M8-03, V9): migration journal, opening balances with four eyes release, reconciliation
report per property, switch of the leading system (G1).

Permissions: ``accounting:read`` for lists and reports, ``accounting:create`` for the journal
import, balance entry, posting and reconciliation run, ``accounting:update`` for the cut off
date and the column configuration, ``accounting:approve`` for the release of the balances and
the decision on a switch request. Ledgers of legal entities outside the session scope (A37)
answer 404 like the ledger endpoints.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import Ledger, LedgerAccount
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_session_legal_entity_allowed,
    property_allowed,
    property_column_guard,
    session_allowed_legal_entity_ids,
    session_allowed_property_ids,
    session_principal,
)
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGateResolver
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentSource, LinkRole
from mhvp.documents.services import store_document
from mhvp.imports import migration as mig
from mhvp.imports.migration_models import (
    AcceptanceStatus,
    MigratedJournalEntry,
    MigratedJournalLine,
    MigrationAcceptance,
    MigrationOpeningBalance,
    MigrationReconciliationReport,
    MigrationSwitchRequest,
    OpeningBalanceStatus,
)
from mhvp.imports.migration_year import year_expenses
from mhvp.imports.models import ImportSourceFile
from mhvp.platform.models import Tenant
from mhvp.properties.models import LegalEntity, Property

# M2-02, R08-01: target property of the import (path ids resolve to the property; ledgers
# through the ledger, opening balances and switch requests through their ledger).
MIGRATION_GUARD = property_column_guard(
    {
        "property_id": Property.id,
        "ledger_id": Ledger.property_id,
        "balance_id": MigrationOpeningBalance.ledger_id,
        "request_id": MigrationSwitchRequest.ledger_id,
        "report_id": MigrationReconciliationReport.property_id,
        "acceptance_id": MigrationAcceptance.property_id,
    }
)
router = APIRouter(
    prefix="/imports/migration",
    tags=["Migration Immoware24"],
    dependencies=[Depends(MIGRATION_GUARD)],
)
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")
MAX_UPLOAD = 20 * 1024 * 1024


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JournalColumnsIn(_In):
    columns: dict[str, str]


class JournalColumnsOut(BaseModel):
    columns: dict[str, str]
    customised: bool
    fields: list[dict[str, Any]]


class JournalImportIn(_In):
    source_file_id: uuid.UUID
    year: int = Field(ge=2000, le=2100)
    year_complete: bool = False


class JournalEntryOut(BaseModel):
    id: uuid.UUID
    source: str
    source_entry_id: str
    booking_date: date
    fiscal_year: int
    text: str
    reference: str | None
    document_ref: str | None
    year_complete: bool
    reconciled: bool
    debit_total: Decimal
    credit_total: Decimal
    lines: list[dict[str, Any]]


class JournalOut(BaseModel):
    ledger_id: uuid.UUID
    summary: dict[str, Any]
    entries: list[JournalEntryOut]


class CutoffIn(_In):
    migration_cutoff: date | None


class LedgerMigrationOut(BaseModel):
    id: uuid.UUID
    name: str
    legal_entity_id: uuid.UUID
    leading_system: str
    migration_cutoff: date | None


class BalanceLineIn(_In):
    kind: str
    account_id: uuid.UUID
    amount: Decimal
    text: str | None = Field(default=None, max_length=500)
    property_bank_account_id: uuid.UUID | None = None
    due_date: date | None = None


class OpeningBalancesIn(_In):
    cutoff_date: date
    note: str | None = None
    lines: list[BalanceLineIn]


class BalanceLineOut(BaseModel):
    id: uuid.UUID
    kind: str
    account_id: uuid.UUID
    account_number: str
    account_name: str
    amount: Decimal
    text: str | None
    property_bank_account_id: uuid.UUID | None
    due_date: date | None


class OpeningBalancesOut(BaseModel):
    id: uuid.UUID
    ledger_id: uuid.UUID
    cutoff_date: date
    status: str
    entered_via: str
    note: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    released_by: uuid.UUID | None
    released_at: datetime | None
    release_comment: str | None
    posted_at: datetime | None
    journal_entry_id: uuid.UUID | None
    total_debit: Decimal
    total_credit: Decimal
    lines: list[BalanceLineOut]


class BalanceImportOut(BaseModel):
    balances: OpeningBalancesOut | None
    errors: list[str]


class MigrationDecisionIn(_In):
    comment: str | None = None


class ReconciliationLineOut(BaseModel):
    ledger_id: uuid.UUID | None
    metric: str
    key: str
    label: str
    source: str | None
    platform: str | None
    difference: str | None
    deviates: bool
    hint: str | None


class MigrationReportListOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    created_at: datetime
    created_by: uuid.UUID | None
    as_of: date
    zero_difference: bool
    compared: int
    deviations: int
    total_difference: Decimal
    document_id: uuid.UUID | None


class MigrationReportOut(MigrationReportListOut):
    summary: dict[str, Any]
    lines: list[ReconciliationLineOut]


class ReconciliationRunIn(_In):
    as_of: date | None = None


class SwitchRequestIn(_In):
    comment: str | None = None


class SwitchRequestOut(BaseModel):
    id: uuid.UUID
    ledger_id: uuid.UUID
    report_id: uuid.UUID
    status: str
    comment: str | None
    requested_by: uuid.UUID
    created_at: datetime
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    decision_comment: str | None


# Helpers ---------------------------------------------------------------------------------


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID, *, lock: bool = False) -> Ledger:
    query = select(Ledger).where(Ledger.id == ledger_id)
    if lock:
        query = query.with_for_update()
    ledger = await session.scalar(query)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    return ledger


async def _property(session: AsyncSession, property_id: uuid.UUID) -> Property:
    prop = await session.get(Property, property_id)
    if prop is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return prop


async def _balance(
    session: AsyncSession, balance_id: uuid.UUID, *, lock: bool = False
) -> tuple[MigrationOpeningBalance, Ledger]:
    query = select(MigrationOpeningBalance).where(MigrationOpeningBalance.id == balance_id)
    if lock:
        query = query.with_for_update()
    balance = await session.scalar(query)
    if balance is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return balance, await _ledger(session, balance.ledger_id, lock=lock)


async def _balances_out(
    session: AsyncSession, balance: MigrationOpeningBalance
) -> OpeningBalancesOut:
    lines = [
        BalanceLineOut(
            id=line.id,
            kind=line.kind,
            account_id=line.account_id,
            account_number=account.number,
            account_name=account.name,
            amount=line.amount,
            text=line.text,
            property_bank_account_id=line.property_bank_account_id,
            due_date=line.due_date,
        )
        for line, account in await mig.balance_lines(session, balance.id)
    ]
    return OpeningBalancesOut(
        id=balance.id,
        ledger_id=balance.ledger_id,
        cutoff_date=balance.cutoff_date,
        status=balance.status,
        entered_via=balance.entered_via,
        note=balance.note,
        created_by=balance.created_by,
        created_at=balance.created_at,
        released_by=balance.released_by,
        released_at=balance.released_at,
        release_comment=balance.release_comment,
        posted_at=balance.posted_at,
        journal_entry_id=balance.journal_entry_id,
        total_debit=sum((line.amount for line in lines if line.amount > 0), Decimal("0.00")),
        total_credit=sum((-line.amount for line in lines if line.amount < 0), Decimal("0.00")),
        lines=lines,
    )


def _report_list_out(report: MigrationReconciliationReport) -> MigrationReportListOut:
    return MigrationReportListOut(
        id=report.id,
        property_id=report.property_id,
        created_at=report.created_at,
        created_by=report.created_by,
        as_of=report.as_of,
        zero_difference=report.zero_difference,
        compared=report.compared,
        deviations=report.deviations,
        total_difference=report.total_difference,
        document_id=report.document_id,
    )


def _report_out(report: MigrationReconciliationReport) -> MigrationReportOut:
    return MigrationReportOut(
        **_report_list_out(report).model_dump(),
        summary=report.summary,
        lines=[ReconciliationLineOut(**line) for line in report.lines],
    )


def _switch_out(item: MigrationSwitchRequest) -> SwitchRequestOut:
    return SwitchRequestOut(
        id=item.id,
        ledger_id=item.ledger_id,
        report_id=item.report_id,
        status=item.status,
        comment=item.comment,
        requested_by=item.requested_by,
        created_at=item.created_at,
        decided_by=item.decided_by,
        decided_at=item.decided_at,
        decision_comment=item.decision_comment,
    )


def _ledger_out(ledger: Ledger) -> LedgerMigrationOut:
    return LedgerMigrationOut(
        id=ledger.id,
        name=ledger.name,
        legal_entity_id=ledger.legal_entity_id,
        leading_system=ledger.leading_system.value,
        migration_cutoff=ledger.migration_cutoff,
    )


def _resolver(request: Request) -> ReleaseGateResolver:
    resolver: ReleaseGateResolver = request.app.state.release_gate_resolver
    return resolver


# Status ----------------------------------------------------------------------------------


@router.get("/status", summary="Migrationsstatus je Objekt", dependencies=[Depends(strict_query)])
async def status(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        items = await mig.migration_status(session, session_allowed_legal_entity_ids(session))
        prop_allowed = session_allowed_property_ids(session)  # M2-02, R08-01
        if prop_allowed is None:
            return items
        return [i for i in items if uuid.UUID(i["property_id"]) in prop_allowed]


# Journal ---------------------------------------------------------------------------------


@router.get("/journal-columns", summary="Spaltenzuordnung des Journal-Exports")
async def journal_columns(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> JournalColumnsOut:
    async with tenant_tx(request, principal) as session:
        columns, customised = await mig.load_journal_columns(session)
    return JournalColumnsOut(
        columns=columns,
        customised=customised,
        fields=[
            {"name": name, "label": label, "required": required}
            for name, label, required in mig.JOURNAL_FIELDS
        ],
    )


@router.put("/journal-columns", summary="Spaltenzuordnung des Journal-Exports speichern")
async def put_journal_columns(
    body: JournalColumnsIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> JournalColumnsOut:
    async with tenant_tx(request, principal) as session:
        columns = await mig.store_journal_columns(
            session, principal.tenant_id, principal.user_id, body.columns
        )
    return JournalColumnsOut(
        columns=columns,
        customised=True,
        fields=[
            {"name": name, "label": label, "required": required}
            for name, label, required in mig.JOURNAL_FIELDS
        ],
    )


@router.get("/ledgers/{ledger_id}", summary="Buchungskreis: Stichtag und führendes System")
async def get_ledger(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> LedgerMigrationOut:
    async with tenant_tx(request, principal) as session:
        return _ledger_out(await _ledger(session, ledger_id))


@router.put("/ledgers/{ledger_id}/cutoff", summary="Migrationsstichtag des Buchungskreises")
async def put_cutoff(
    ledger_id: uuid.UUID,
    body: CutoffIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> LedgerMigrationOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        posted = await session.scalar(
            select(MigrationOpeningBalance).where(
                MigrationOpeningBalance.ledger_id == ledger.id,
                MigrationOpeningBalance.status == OpeningBalanceStatus.POSTED.value,
            )
        )
        if posted is not None and posted.cutoff_date != body.migration_cutoff:
            raise ProblemError(
                ErrorCodes.MIG_STATE,
                detail=(
                    f"Zum Stichtag {posted.cutoff_date:%d.%m.%Y} sind Eröffnungssalden gebucht; "
                    "der Stichtag wird nicht mehr geändert."
                ),
            )
        old = ledger.migration_cutoff
        ledger.migration_cutoff = body.migration_cutoff
        ledger.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.migration_cutoff_changed",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            changes={
                "migration_cutoff": {
                    "old": old.isoformat() if old else None,
                    "new": body.migration_cutoff.isoformat() if body.migration_cutoff else None,
                }
            },
        )
        await session.flush()
        return _ledger_out(ledger)


@router.get("/ledgers/{ledger_id}/journal", summary="Migrationsjournal des Buchungskreises")
async def get_journal(
    ledger_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    limit: int = Query(default=200, ge=1, le=2000),
) -> JournalOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        summary = await mig.journal_summary(session, ledger.id)
        entries = (
            await session.scalars(
                select(MigratedJournalEntry)
                .where(MigratedJournalEntry.ledger_id == ledger.id)
                .order_by(MigratedJournalEntry.booking_date, MigratedJournalEntry.source_entry_id)
                .limit(limit)
            )
        ).all()
        lines: dict[uuid.UUID, list[dict[str, Any]]] = {}
        if entries:
            for line in (
                await session.scalars(
                    select(MigratedJournalLine)
                    .where(MigratedJournalLine.entry_id.in_([e.id for e in entries]))
                    .order_by(MigratedJournalLine.entry_id, MigratedJournalLine.line_no)
                )
            ).all():
                lines.setdefault(line.entry_id, []).append(
                    {
                        "line_no": line.line_no,
                        "account_number": line.account_number,
                        "account_id": str(line.account_id) if line.account_id else None,
                        "debit": str(line.debit),
                        "credit": str(line.credit),
                        "text": line.text,
                    }
                )
        return JournalOut(
            ledger_id=ledger.id,
            summary=summary,
            entries=[
                JournalEntryOut(
                    id=e.id,
                    source=e.source,
                    source_entry_id=e.source_entry_id,
                    booking_date=e.booking_date,
                    fiscal_year=e.fiscal_year,
                    text=e.text,
                    reference=e.reference,
                    document_ref=e.document_ref,
                    year_complete=e.year_complete,
                    reconciled=e.reconciled,
                    debit_total=e.debit_total,
                    credit_total=e.credit_total,
                    lines=lines.get(e.id, []),
                )
                for e in entries
            ],
        )


@router.post(
    "/ledgers/{ledger_id}/journal", summary="Journal-Export als Migrationsjournal übernehmen"
)
async def import_journal(
    ledger_id: uuid.UUID,
    body: JournalImportIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        source = await session.get(ImportSourceFile, body.source_file_id)
        if source is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Importdatei nicht gefunden.")
        columns, _ = await mig.load_journal_columns(session)
        result = await mig.import_journal(
            session,
            ledger,
            source,
            columns,
            year=body.year,
            year_complete=body.year_complete,
            user_id=principal.user_id,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="migration.journal_imported",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload={"source_file_id": str(source.id), **result.as_dict()},
        )
        return result.as_dict()


# Opening balances ------------------------------------------------------------------------


@router.get(
    "/ledgers/{ledger_id}/opening-balances",
    summary="Eröffnungssalden des Buchungskreises",
    dependencies=[Depends(strict_query)],
)
async def list_opening_balances(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[OpeningBalancesOut]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        rows = (
            await session.scalars(
                select(MigrationOpeningBalance)
                .where(MigrationOpeningBalance.ledger_id == ledger.id)
                .order_by(MigrationOpeningBalance.cutoff_date.desc())
            )
        ).all()
        return [await _balances_out(session, b) for b in rows]


@router.put("/ledgers/{ledger_id}/opening-balances", summary="Eröffnungssalden erfassen (Formular)")
async def put_opening_balances(
    ledger_id: uuid.UUID,
    body: OpeningBalancesIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> OpeningBalancesOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        balance = await mig.save_opening_balances(
            session,
            ledger,
            body.cutoff_date,
            [
                mig.BalanceIn(
                    kind=line.kind,
                    account_id=line.account_id,
                    amount=line.amount,
                    text=line.text,
                    property_bank_account_id=line.property_bank_account_id,
                    due_date=line.due_date,
                )
                for line in body.lines
            ],
            user_id=principal.user_id,
            entered_via="form",
            note=body.note,
        )
        return await _balances_out(session, balance)


@router.post(
    "/ledgers/{ledger_id}/opening-balances/import",
    summary="Eröffnungssalden aus einer Saldenliste (CSV) übernehmen",
)
async def import_opening_balances(
    ledger_id: uuid.UUID,
    request: Request,
    cutoff_date: date = Form(),
    file: UploadFile = File(),
    note: str | None = Form(default=None),
    principal: TenantPrincipal = Depends(CREATE),
) -> BalanceImportOut:
    data = await file.read()
    if not data:
        raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail="Die Datei ist leer.")
    if len(data) > MAX_UPLOAD:
        raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail="Die Datei ist zu groß.")
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        accounts = {
            a.number: a
            for a in (
                await session.scalars(
                    select(LedgerAccount).where(LedgerAccount.ledger_id == ledger.id)
                )
            ).all()
        }
        balances, errors = mig.parse_balance_list(data, accounts)
        if errors and any(not e.startswith("Datei als") for e in errors):
            return BalanceImportOut(balances=None, errors=errors)
        balance = await mig.save_opening_balances(
            session,
            ledger,
            cutoff_date,
            balances,
            user_id=principal.user_id,
            entered_via="import",
            note=note or f"Saldenliste {file.filename or ''}".strip(),
        )
        return BalanceImportOut(balances=await _balances_out(session, balance), errors=errors)


@router.get("/opening-balances/{balance_id}", summary="Eröffnungssalden")
async def get_opening_balances(
    balance_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> OpeningBalancesOut:
    async with tenant_tx(request, principal) as session:
        balance, _ = await _balance(session, balance_id)
        return await _balances_out(session, balance)


@router.post(
    "/opening-balances/{balance_id}/release", summary="Eröffnungssalden freigeben (zweite Person)"
)
async def release_opening_balances(
    balance_id: uuid.UUID,
    body: MigrationDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> OpeningBalancesOut:
    async with tenant_tx(request, principal) as session:
        balance, _ = await _balance(session, balance_id, lock=True)
        await mig.release_opening_balances(
            session,
            balance,
            user_id=principal.user_id,
            is_platform_admin=principal.is_platform_admin,
            comment=body.comment,
        )
        return await _balances_out(session, balance)


@router.post(
    "/opening-balances/{balance_id}/post",
    summary="Eröffnungssalden buchen (Quelle migration, nur nach Freigabe und mit Stichtag)",
)
async def post_opening_balances(
    balance_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> OpeningBalancesOut:
    async with tenant_tx(request, principal) as session:
        balance, ledger = await _balance(session, balance_id, lock=True)
        await mig.post_opening_balances(session, ledger, balance, user_id=principal.user_id)
        return await _balances_out(session, balance)


# Reconciliation --------------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/reconciliation",
    summary="Abgleichberichte des Objekts",
    dependencies=[Depends(strict_query)],
)
async def list_reports(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[MigrationReportListOut]:
    async with tenant_tx(request, principal) as session:
        prop = await _property(session, property_id)
        rows = (
            await session.scalars(
                select(MigrationReconciliationReport)
                .where(MigrationReconciliationReport.property_id == prop.id)
                .order_by(MigrationReconciliationReport.created_at.desc())
            )
        ).all()
        return [_report_list_out(r) for r in rows]


@router.post(
    "/properties/{property_id}/reconciliation",
    status_code=201,
    summary="Abgleich mit Nulldifferenzprüfung ausführen und als Dokument ablegen",
)
async def run_reconciliation(
    property_id: uuid.UUID,
    body: ReconciliationRunIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> MigrationReportOut:
    async with tenant_tx(request, principal) as session:
        prop = await _property(session, property_id)
        as_of = body.as_of
        if as_of is None:
            cutoffs = (
                await session.scalars(
                    select(Ledger.migration_cutoff)
                    .join(LegalEntity, LegalEntity.id == Ledger.legal_entity_id)
                    .where(
                        (Ledger.property_id == prop.id) | (LegalEntity.property_id == prop.id),
                        Ledger.migration_cutoff.is_not(None),
                    )
                )
            ).all()
            if not cutoffs:
                raise ProblemError(
                    ErrorCodes.MIG_CUTOFF_MISSING,
                    detail="Kein Buchungskreis des Objekts hat einen Migrationsstichtag; "
                    "Stichtag angeben oder setzen.",
                )
            as_of = max(c for c in cutoffs if c is not None)
        report = await mig.build_report(session, prop, as_of)
        row = await mig.store_report(session, prop, report, user_id=principal.user_id)
        tenant = await session.get(Tenant, principal.tenant_id)
        pdf = mig.report_pdf(report, tenant.name if tenant else "", row.created_at)
        document = await store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=pdf,
            title=f"Abgleichbericht Migration {prop.number} zum {as_of:%d.%m.%Y}",
            filename=f"abgleich-migration-{prop.number}-{as_of.isoformat()}.pdf",
            mime_type="application/pdf",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[("property", prop.id, LinkRole.GENERATED)],
            created_by=principal.user_id,
            settings=request.app.state.settings,
        )
        row.document_id = document.id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="migration.reconciled",
            entity_type="migration_reconciliation_report",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "property_id": str(prop.id),
                "as_of": as_of.isoformat(),
                "zero_difference": row.zero_difference,
                "deviations": row.deviations,
                "document_id": str(document.id),
            },
        )
        await session.flush()
        return _report_out(row)


@router.get("/reconciliation/{report_id}", summary="Abgleichbericht")
async def get_report(
    report_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> MigrationReportOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(MigrationReconciliationReport, report_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _report_out(row)


@router.get(
    "/reconciliation/{report_id}/pdf", summary="Abgleichbericht (PDF)", response_class=Response
)
async def get_report_pdf(
    report_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await session.get(MigrationReconciliationReport, report_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        document = await session.get(Document, row.document_id) if row.document_id else None
        if document is not None:
            data = BlobStore(request.app.state.settings).get(document.storage_ref)
            filename = document.filename
        else:
            tenant = await session.get(Tenant, principal.tenant_id)
            data = mig.report_pdf(
                {**row.summary, "lines": row.lines}, tenant.name if tenant else "", row.created_at
            )
            filename = f"abgleich-migration-{row.as_of.isoformat()}.pdf"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Switch of the leading system -----------------------------------------------------------


@router.get(
    "/switch-requests",
    summary="Anträge auf Wechsel des führenden Systems",
    dependencies=[Depends(strict_query)],
)
async def list_switch_requests(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    ledger_id: uuid.UUID | None = Query(default=None),
) -> list[SwitchRequestOut]:
    async with tenant_tx(request, principal) as session:
        allowed = session_allowed_legal_entity_ids(session)
        query = (
            select(MigrationSwitchRequest, Ledger)
            .join(Ledger, Ledger.id == MigrationSwitchRequest.ledger_id)
            .order_by(MigrationSwitchRequest.created_at.desc())
        )
        if ledger_id is not None:
            query = query.where(MigrationSwitchRequest.ledger_id == ledger_id)
        rows = (await session.execute(query)).all()
        return [
            _switch_out(item)
            for item, ledger in rows
            if (allowed is None or ledger.legal_entity_id in allowed)
            and property_allowed(session_principal(session), ledger.property_id)
        ]


@router.post(
    "/ledgers/{ledger_id}/switch-requests",
    status_code=201,
    summary="Wechsel des führenden Systems beantragen (G1, Nulldifferenz)",
)
async def request_switch(
    ledger_id: uuid.UUID,
    body: SwitchRequestIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> SwitchRequestOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        item = await mig.request_switch(
            session, ledger, _resolver(request), user_id=principal.user_id, comment=body.comment
        )
        return _switch_out(item)


async def _decide(
    request: Request,
    principal: TenantPrincipal,
    request_id: uuid.UUID,
    approve: bool,
    comment: str | None,
) -> SwitchRequestOut:
    async with tenant_tx(request, principal) as session:
        item = await session.scalar(
            select(MigrationSwitchRequest)
            .where(MigrationSwitchRequest.id == request_id)
            .with_for_update()
        )
        if item is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        ledger = await _ledger(session, item.ledger_id, lock=True)
        await mig.decide_switch(
            session,
            ledger,
            item,
            _resolver(request),
            approve=approve,
            user_id=principal.user_id,
            is_platform_admin=principal.is_platform_admin,
            comment=comment,
        )
        return _switch_out(item)


@router.post("/switch-requests/{request_id}/approve", summary="Wechsel freigeben (zweite Person)")
async def approve_switch(
    request_id: uuid.UUID,
    body: MigrationDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> SwitchRequestOut:
    return await _decide(request, principal, request_id, True, body.comment)


@router.post("/switch-requests/{request_id}/reject", summary="Wechsel ablehnen")
async def reject_switch(
    request_id: uuid.UUID,
    body: MigrationDecisionIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> SwitchRequestOut:
    return await _decide(request, principal, request_id, False, body.comment)


# Year view of the takeover year (D11, M8-08) ---------------------------------------------


class MigYearAccountOut(BaseModel):
    account_number: str
    account_name: str
    prior_period: Decimal
    later_period: Decimal
    total: Decimal


class MigYearExpensesOut(BaseModel):
    ledger_id: uuid.UUID
    year: int
    migration_cutoff: date | None
    prior_period_total: Decimal
    later_period_total: Decimal
    total: Decimal
    prior_year_complete: bool
    accounts: list[MigYearAccountOut]


@router.get(
    "/ledgers/{ledger_id}/year-expenses",
    summary="Ausgaben des Übernahmejahres (Vorperiode Migrationsjournal, Nachperiode Journal)",
)
async def get_year_expenses(
    ledger_id: uuid.UUID,
    request: Request,
    year: int = Query(ge=2000, le=2100),
    principal: TenantPrincipal = Depends(READ),
) -> MigYearExpensesOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        return MigYearExpensesOut(**await year_expenses(session, ledger, year))


# Acceptance record (13.1, M8-09) ---------------------------------------------------------


class MigAcceptancePerson(_In):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=200)


class MigAcceptanceIn(_In):
    review_scope: str = Field(default="", max_length=10000)
    responsible_persons: list[MigAcceptancePerson] = Field(default_factory=list, max_length=50)
    non_migratable_data: str = Field(default="", max_length=10000)
    fallback_plan: str = Field(default="", max_length=10000)
    archive_concept: str = Field(default="", max_length=10000)
    reconciliation_report_id: uuid.UUID | None = None


class MigAcceptanceOut(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    status: str
    review_scope: str
    responsible_persons: list[dict[str, Any]]
    non_migratable_data: str
    fallback_plan: str
    archive_concept: str
    reconciliation_report_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    signed_by: uuid.UUID | None
    signed_at: datetime | None


def _acceptance_out(item: MigrationAcceptance) -> MigAcceptanceOut:
    return MigAcceptanceOut(
        id=item.id,
        property_id=item.property_id,
        status=item.status,
        review_scope=item.review_scope,
        responsible_persons=item.responsible_persons,
        non_migratable_data=item.non_migratable_data,
        fallback_plan=item.fallback_plan,
        archive_concept=item.archive_concept,
        reconciliation_report_id=item.reconciliation_report_id,
        created_by=item.created_by,
        created_at=item.created_at,
        signed_by=item.signed_by,
        signed_at=item.signed_at,
    )


async def _acceptance(
    session: AsyncSession, acceptance_id: uuid.UUID, *, lock: bool = False
) -> MigrationAcceptance:
    query = select(MigrationAcceptance).where(MigrationAcceptance.id == acceptance_id)
    if lock:
        query = query.with_for_update()
    item = await session.scalar(query)
    if item is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return item


async def _check_report(
    session: AsyncSession, report_id: uuid.UUID | None, property_id: uuid.UUID
) -> None:
    if report_id is None:
        return
    report = await session.get(MigrationReconciliationReport, report_id)
    if report is None or report.property_id != property_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


@router.get(
    "/properties/{property_id}/acceptance",
    summary="Abnahmeprotokolle des Objekts",
    dependencies=[Depends(strict_query)],
)
async def list_acceptances(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[MigAcceptanceOut]:
    async with tenant_tx(request, principal) as session:
        prop = await _property(session, property_id)
        rows = (
            await session.scalars(
                select(MigrationAcceptance)
                .where(MigrationAcceptance.property_id == prop.id)
                .order_by(MigrationAcceptance.created_at.desc())
            )
        ).all()
        return [_acceptance_out(r) for r in rows]


@router.post(
    "/properties/{property_id}/acceptance",
    status_code=201,
    summary="Abnahmeprotokoll anlegen (Entwurf)",
)
async def create_acceptance(
    property_id: uuid.UUID,
    body: MigAcceptanceIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> MigAcceptanceOut:
    async with tenant_tx(request, principal) as session:
        prop = await _property(session, property_id)
        await _check_report(session, body.reconciliation_report_id, prop.id)
        item = MigrationAcceptance(
            tenant_id=principal.tenant_id,
            property_id=prop.id,
            review_scope=body.review_scope,
            responsible_persons=[p.model_dump() for p in body.responsible_persons],
            non_migratable_data=body.non_migratable_data,
            fallback_plan=body.fallback_plan,
            archive_concept=body.archive_concept,
            reconciliation_report_id=body.reconciliation_report_id,
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        session.add(item)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="migration.acceptance_created",
            entity_type="migration_acceptance",
            entity_id=item.id,
            actor_user_id=principal.user_id,
            changes={},
        )
        return _acceptance_out(item)


@router.put("/acceptance/{acceptance_id}", summary="Abnahmeprotokoll bearbeiten (nur Entwurf)")
async def update_acceptance(
    acceptance_id: uuid.UUID,
    body: MigAcceptanceIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> MigAcceptanceOut:
    async with tenant_tx(request, principal) as session:
        item = await _acceptance(session, acceptance_id, lock=True)
        if item.status != AcceptanceStatus.DRAFT.value:
            raise ProblemError(
                ErrorCodes.MIG_STATE, detail="Ein unterzeichnetes Protokoll wird nicht geändert."
            )
        await _check_report(session, body.reconciliation_report_id, item.property_id)
        item.review_scope = body.review_scope
        item.responsible_persons = [p.model_dump() for p in body.responsible_persons]
        item.non_migratable_data = body.non_migratable_data
        item.fallback_plan = body.fallback_plan
        item.archive_concept = body.archive_concept
        item.reconciliation_report_id = body.reconciliation_report_id
        item.updated_by = principal.user_id
        await session.flush()
        return _acceptance_out(item)


@router.post(
    "/acceptance/{acceptance_id}/sign", summary="Abnahmeprotokoll unterzeichnen (zweite Person)"
)
async def sign_acceptance(
    acceptance_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> MigAcceptanceOut:
    async with tenant_tx(request, principal) as session:
        item = await _acceptance(session, acceptance_id, lock=True)
        if item.status != AcceptanceStatus.DRAFT.value:
            raise ProblemError(ErrorCodes.MIG_STATE)
        if not (
            item.review_scope.strip()
            and item.responsible_persons
            and item.fallback_plan.strip()
            and item.archive_concept.strip()
        ):
            raise ProblemError(
                ErrorCodes.MIG_STATE,
                detail=(
                    "Prüfumfang, verantwortliche Personen, Rückfallplan und Archivkonzept "
                    "sind vor der Unterzeichnung auszufüllen."
                ),
            )
        mig._four_eyes(
            principal.user_id, item.updated_by or item.created_by, principal.is_platform_admin
        )
        item.status = AcceptanceStatus.SIGNED.value
        item.signed_by = principal.user_id
        item.signed_at = datetime.now(UTC)
        item.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="migration.acceptance_signed",
            entity_type="migration_acceptance",
            entity_id=item.id,
            actor_user_id=principal.user_id,
            changes={},
        )
        await session.flush()
        return _acceptance_out(item)
