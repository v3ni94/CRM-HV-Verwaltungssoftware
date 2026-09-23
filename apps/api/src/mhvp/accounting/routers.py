"""Ledger endpoints (/api/v1/accounting, M10).

Postings are allowed in ledgers that are not leading (parallel operation with Immoware24).
Declaring the platform as leading system requires release gate G1 (18.0, 6.9.10).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import dunning, invoices, receivables, reports
from mhvp.accounting import services as svc
from mhvp.accounting.models import (
    AdminFeeSetting,
    ChartTemplate,
    DunningCase,
    DunningRun,
    DunningSettings,
    EntryKind,
    EntrySource,
    EntryStatus,
    ExportRun,
    Invoice,
    InvoiceKind,
    InvoiceLine,
    InvoiceReview,
    JournalEntry,
    JournalLine,
    LeadingSystem,
    Ledger,
    LedgerAccount,
    PaymentTypeAccount,
    PostingStatus,
    ReceivableItem,
    ReceivableRun,
    RecurringInvoicePlan,
    ReviewStatus,
)
from mhvp.accounting.schemas import (
    AccountIn,
    AccountOut,
    AccountPatch,
    ChartTemplateOut,
    EntryOut,
    JournalEntryIn,
    LeadingIn,
    LedgerIn,
    LedgerOut,
    LineOut,
    LockIn,
    ReverseIn,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ReleaseGateResolver, ensure_release_gate_open
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/accounting", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
UPDATE = require_permission("accounting:update")
APPROVE = require_permission("accounting:approve")


async def _get(session: Any, model: Any, entity_id: uuid.UUID) -> Any:
    row = await session.get(model, entity_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _ledger(session: AsyncSession, ledger_id: uuid.UUID, *, lock: bool = False) -> Ledger:
    query = select(Ledger).where(Ledger.id == ledger_id)
    if lock:
        query = query.with_for_update()
    ledger = await session.scalar(query)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return ledger


async def _entry(
    session: AsyncSession, ledger: Ledger, entry_id: uuid.UUID, *, lock: bool = False
) -> JournalEntry:
    query = select(JournalEntry).where(
        JournalEntry.id == entry_id, JournalEntry.ledger_id == ledger.id
    )
    if lock:
        query = query.with_for_update()
    entry = await session.scalar(query)
    if entry is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return entry


async def _out(session: Any, entry: JournalEntry) -> EntryOut:
    out = EntryOut.model_validate(entry)
    out.lines = [LineOut.model_validate(line) for line in await svc.entry_lines(session, entry.id)]
    return out


def _lines(body: JournalEntryIn) -> list[svc.LineIn]:
    return [
        svc.LineIn(
            account_id=line.account_id,
            debit=line.debit,
            credit=line.credit,
            text=line.text,
            vat_percent=line.vat_percent,
            vat_amount=line.vat_amount,
            net_amount=line.net_amount,
            unit_id=line.unit_id,
            cost_center=line.cost_center,
        )
        for line in body.lines
    ]


# Templates ----------------------------------------------------------------------------


@router.get("/templates", summary="Kontenrahmen-Vorlagen")
async def templates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[ChartTemplateOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ChartTemplate).order_by(ChartTemplate.code, ChartTemplate.version)
        )
        return [ChartTemplateOut.model_validate(t) for t in rows.all()]


@router.post("/templates/default", status_code=201, summary="Entwurf nach Anhang A.1 anlegen")
async def create_default_template(
    request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> ChartTemplateOut:
    async with tenant_tx(request, principal) as session:
        return ChartTemplateOut.model_validate(
            await svc.default_template(session, principal.tenant_id)
        )


@router.post(
    "/templates/{template_id}/release", summary="Vorlage freigeben (Betreiberentscheidung V8)"
)
async def release_template(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> ChartTemplateOut:
    async with tenant_tx(request, principal) as session:
        template = await _get(session, ChartTemplate, template_id)
        if not template.released:
            template.released, template.released_by = True, principal.user_id
            template.released_at = datetime.now(UTC)
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="chart_template.released",
                entity_type="chart_of_accounts_template",
                entity_id=template.id,
                actor_user_id=principal.user_id,
                payload={"code": template.code, "version": template.version},
            )
            await session.flush()
        return ChartTemplateOut.model_validate(template)


# Ledgers ------------------------------------------------------------------------------


@router.post("/ledgers", status_code=201, summary="Buchungskreis je Rechtsträger anlegen")
async def create_ledger(
    body: LedgerIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> LedgerOut:
    async with tenant_tx(request, principal) as session:
        template = (
            await _get(session, ChartTemplate, body.template_id) if body.template_id else None
        )
        ledger = await svc.create_ledger(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            legal_entity_id=body.legal_entity_id,
            template=template,
            fiscal_year_start_month=body.fiscal_year_start_month,
            migration_cutoff=body.migration_cutoff,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.created",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload={"legal_entity_id": str(ledger.legal_entity_id)},
        )
        return LedgerOut.model_validate(ledger)


@router.get("/ledgers", summary="Buchungskreise")
async def list_ledgers(
    request: Request,
    property_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[LedgerOut]:
    async with tenant_tx(request, principal) as session:
        query = select(Ledger).order_by(Ledger.name)
        if property_id:
            query = query.where(Ledger.property_id == property_id)
        return [LedgerOut.model_validate(x) for x in (await session.scalars(query)).all()]


@router.get("/ledgers/{ledger_id}", summary="Buchungskreis")
async def get_ledger(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> LedgerOut:
    async with tenant_tx(request, principal) as session:
        return LedgerOut.model_validate(await _ledger(session, ledger_id))


@router.post(
    "/ledgers/{ledger_id}/sync-debtors", summary="Debitorenkonten aus Verträgen übernehmen"
)
async def sync_debtors(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, int]:
    async with tenant_tx(request, principal) as session:
        return {
            "created": await svc.sync_debtor_accounts(session, await _ledger(session, ledger_id))
        }


@router.post("/ledgers/{ledger_id}/lock", summary="Festschreiben bis Datum")
async def lock(
    ledger_id: uuid.UUID,
    body: LockIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        drafts = await svc.lock_period(session, ledger, body.until)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.locked",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload={"locked_until": body.until.isoformat()},
        )
        return {"locked_until": body.until, "drafts_in_locked_period": drafts}


@router.post("/ledgers/{ledger_id}/leading", summary="Führendes System festlegen (G1)")
async def set_leading(
    ledger_id: uuid.UUID,
    body: LeadingIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> LedgerOut:
    if body.leading_system is LeadingSystem.MHVP:
        resolver: ReleaseGateResolver = request.app.state.release_gate_resolver
        await ensure_release_gate_open(ReleaseGate.G1, principal.tenant_id, resolver)
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id, lock=True)
        ledger.leading_system = body.leading_system
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ledger.leading_system_changed",
            entity_type="ledger",
            entity_id=ledger.id,
            actor_user_id=principal.user_id,
            payload={"leading_system": body.leading_system.value},
        )
        await session.flush()
        return LedgerOut.model_validate(ledger)


# Accounts -----------------------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/accounts", summary="Konten")
async def accounts(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[AccountOut]:
    async with tenant_tx(request, principal) as session:
        await _ledger(session, ledger_id)
        rows = await session.scalars(
            select(LedgerAccount)
            .where(LedgerAccount.ledger_id == ledger_id)
            .order_by(LedgerAccount.number)
        )
        return [AccountOut.model_validate(a) for a in rows.all()]


@router.post("/ledgers/{ledger_id}/accounts", status_code=201, summary="Konto ergänzen")
async def create_account(
    ledger_id: uuid.UUID,
    body: AccountIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> AccountOut:
    from mhvp.properties.models import PropertyBankAccount

    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        if body.property_bank_account_id:
            bank = await _get(session, PropertyBankAccount, body.property_bank_account_id)
            if bank.legal_entity_id != ledger.legal_entity_id:
                raise ProblemError(
                    ErrorCodes.ACC_WRONG_ENTITY,
                    detail="Das Bankkonto gehört einem anderen Rechtsträger.",
                )
        account = LedgerAccount(
            tenant_id=principal.tenant_id,
            ledger_id=ledger.id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(account)
        try:
            await session.flush()
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Kontonummer bereits vergeben."
            ) from None
        return AccountOut.model_validate(account)


@router.patch(
    "/ledgers/{ledger_id}/accounts/{account_id}", summary="Konto ändern oder deaktivieren"
)
async def patch_account(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    body: AccountPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> AccountOut:
    async with tenant_tx(request, principal) as session:
        account = await _get(session, LedgerAccount, account_id)
        if account.ledger_id != ledger_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(account, key, value)
        account.updated_by = principal.user_id
        await session.flush()
        return AccountOut.model_validate(account)


@router.delete(
    "/ledgers/{ledger_id}/accounts/{account_id}",
    status_code=204,
    summary="Konto ohne Buchungen löschen",
)
async def delete_account(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    async with tenant_tx(request, principal) as session:
        account = await _get(session, LedgerAccount, account_id)
        if account.ledger_id != ledger_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        used = await session.scalar(
            select(func.count())
            .select_from(JournalLine)
            .where(JournalLine.account_id == account_id)
        )
        if used:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Konten mit Buchungen können nur deaktiviert werden."
            )
        await session.delete(account)


# Entries ------------------------------------------------------------------------------


@router.post("/ledgers/{ledger_id}/entries", status_code=201, summary="Buchungssatz als Entwurf")
async def create_entry(
    ledger_id: uuid.UUID,
    body: JournalEntryIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    if body.kind is EntryKind.REVERSAL:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Stornos entstehen nur über die Stornofunktion."
        )
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        if body.idempotency_key:
            existing = await session.scalar(
                select(JournalEntry).where(
                    JournalEntry.ledger_id == ledger.id,
                    JournalEntry.idempotency_key == body.idempotency_key,
                )
            )
            if existing is not None:
                return await _out(session, existing)  # repeated request: same draft (B08)
        entry = JournalEntry(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            source=EntrySource.MANUAL,
            **body.model_dump(exclude={"lines", "settlements"}),
        )
        await svc.write_draft(
            session, ledger, entry, _lines(body), [s.model_dump() for s in body.settlements]
        )
        return await _out(session, entry)


@router.put("/ledgers/{ledger_id}/entries/{entry_id}", summary="Entwurf ersetzen")
async def update_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: JournalEntryIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        entry = await _entry(session, ledger, entry_id, lock=True)
        if entry.status is EntryStatus.POSTED:
            raise ProblemError(ErrorCodes.ACC_POSTED_IMMUTABLE)
        if body.kind is EntryKind.REVERSAL:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Stornos entstehen nur über die Stornofunktion."
            )
        for key, value in body.model_dump(
            exclude={"lines", "settlements", "idempotency_key"}
        ).items():
            setattr(entry, key, value)
        entry.approved_by, entry.updated_by = None, principal.user_id  # a change voids the check
        await svc.write_draft(
            session, ledger, entry, _lines(body), [s.model_dump() for s in body.settlements]
        )
        return await _out(session, entry)


@router.delete(
    "/ledgers/{ledger_id}/entries/{entry_id}", status_code=204, summary="Entwurf löschen"
)
async def delete_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> None:
    async with tenant_tx(request, principal) as session:
        entry = await _entry(session, await _ledger(session, ledger_id), entry_id, lock=True)
        if entry.status is EntryStatus.POSTED:
            raise ProblemError(ErrorCodes.ACC_POSTED_IMMUTABLE)
        await session.delete(entry)


@router.get("/ledgers/{ledger_id}/entries", summary="Journal")
async def journal(
    ledger_id: uuid.UUID,
    request: Request,
    status: EntryStatus | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    principal: TenantPrincipal = Depends(READ),
) -> list[EntryOut]:
    async with tenant_tx(request, principal) as session:
        await _ledger(session, ledger_id)
        query = select(JournalEntry).where(JournalEntry.ledger_id == ledger_id)
        if status:
            query = query.where(JournalEntry.status == status)
        if start:
            query = query.where(JournalEntry.booking_date >= start)
        if end:
            query = query.where(JournalEntry.booking_date <= end)
        query = query.order_by(
            JournalEntry.fiscal_year.nulls_last(),
            JournalEntry.number.nulls_last(),
            JournalEntry.created_at,
        )
        rows = (await session.scalars(query.offset(offset).limit(limit))).all()
        return [await _out(session, e) for e in rows]


@router.get("/ledgers/{ledger_id}/entries/{entry_id}", summary="Buchungssatz")
async def get_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        return await _out(
            session, await _entry(session, await _ledger(session, ledger_id), entry_id)
        )


@router.post(
    "/ledgers/{ledger_id}/entries/{entry_id}/approve",
    summary="Anfangsbestand prüfen (zweite Person)",
)
async def approve_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        entry = await _entry(session, await _ledger(session, ledger_id), entry_id, lock=True)
        if entry.status is EntryStatus.POSTED:
            raise ProblemError(ErrorCodes.ACC_POSTED_IMMUTABLE)
        if entry.created_by == principal.user_id or principal.is_platform_admin:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES, detail="Die Prüfung muss eine andere Person vornehmen."
            )
        entry.approved_by = principal.user_id
        await session.flush()
        return await _out(session, entry)


@router.post(
    "/ledgers/{ledger_id}/entries/{entry_id}/post", summary="Buchen (festgeschriebene Nummer)"
)
async def post_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        entry = await _entry(session, ledger, entry_id, lock=True)
        already = entry.status is EntryStatus.POSTED
        await svc.post(session, ledger, entry, principal.user_id)
        if not already:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="journal_entry.posted",
                entity_type="journal_entry",
                entity_id=entry.id,
                actor_user_id=principal.user_id,
                payload={"number": f"{entry.fiscal_year}-{entry.number}", "kind": entry.kind.value},
            )
        return await _out(session, entry)


@router.post(
    "/ledgers/{ledger_id}/entries/{entry_id}/reverse", status_code=201, summary="Stornieren"
)
async def reverse_entry(
    ledger_id: uuid.UUID,
    entry_id: uuid.UUID,
    body: ReverseIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> EntryOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        entry = await _entry(session, ledger, entry_id, lock=True)
        booking_date = body.booking_date or svc.default_reversal_date(ledger, local_today())
        reversal = await svc.reverse(
            session,
            ledger,
            entry,
            user_id=principal.user_id,
            reason=body.reason,
            booking_date=booking_date,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="journal_entry.reversed",
            entity_type="journal_entry",
            entity_id=entry.id,
            actor_user_id=principal.user_id,
            payload={"reversal_id": str(reversal.id), "reason": body.reason},
        )
        return await _out(session, reversal)


# Reports ------------------------------------------------------------------------------


@router.get("/ledgers/{ledger_id}/accounts/{account_id}/sheet", summary="Kontenblatt")
async def account_sheet(
    ledger_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    start: date,
    end: date,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        account = await _get(session, LedgerAccount, account_id)
        if account.ledger_id != ledger_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await svc.account_sheet(session, account, start, end)


@router.get("/ledgers/{ledger_id}/trial-balance", summary="Saldenliste zum Stichtag")
async def trial_balance(
    ledger_id: uuid.UUID,
    request: Request,
    as_of: date,
    start: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await svc.trial_balance(session, await _ledger(session, ledger_id), as_of, start)


@router.get("/ledgers/{ledger_id}/open-items", summary="Offene Posten zum Stichtag")
async def open_items(
    ledger_id: uuid.UUID,
    request: Request,
    as_of: date,
    account_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        return await svc.open_items(session, await _ledger(session, ledger_id), as_of, account_id)


@router.get("/ledgers/{ledger_id}/checks", summary="Konsistenzprüfung B02, B07, B09")
async def checks(
    ledger_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        findings = await svc.checks(session, await _ledger(session, ledger_id))
        return {"ok": not findings, "findings": findings}


# Receivable runs and management fee (M13, 7.5) ----------------------------------------


class PaymentTypeMappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_type_code: str = Field(min_length=1, max_length=63)
    account_id: uuid.UUID


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_month: date
    scope: str = Field(default="all", pattern="^(all|property|contract)$")
    scope_id: uuid.UUID | None = None


class RunReverseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=2000)
    booking_date: date | None = None


class FeeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID
    start_date: date
    end_date: date | None = None
    vat_percent: Decimal = Decimal(0)
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    amounts_per_unit_type: dict[str, Decimal]
    invoice_debtor_party_id: uuid.UUID | None = None
    contract_document_id: uuid.UUID | None = None


def _run_out(run: ReceivableRun, items: list[ReceivableItem]) -> dict[str, Any]:
    return {
        "id": run.id,
        "period_month": run.period_month,
        "scope": run.scope,
        "status": run.status.value,
        "totals": run.totals,
        "posted_at": run.posted_at,
        "items": [
            {
                "contract_id": i.contract_id,
                "payment_type_code": i.payment_type_code,
                "amount": i.amount,
                "due_date": i.due_date,
                "status": i.status.value,
                "message": i.message,
                "journal_entry_id": i.journal_entry_id,
            }
            for i in items
        ],
    }


async def _items(session: AsyncSession, run_id: uuid.UUID) -> list[ReceivableItem]:
    return list(
        (
            await session.scalars(
                select(ReceivableItem)
                .where(ReceivableItem.run_id == run_id)
                .order_by(ReceivableItem.created_at)
            )
        ).all()
    )


@router.put("/ledgers/{ledger_id}/payment-type-accounts", summary="Erlöskonto je Zahlungsart")
async def set_mapping(
    ledger_id: uuid.UUID,
    body: PaymentTypeMappingIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        account = await _get(session, LedgerAccount, body.account_id)
        if account.ledger_id != ledger.id:
            raise ProblemError(ErrorCodes.ACC_WRONG_ENTITY)
        if account.category.value != "revenue":
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Sollstellungen werden auf Erlöskonten gebucht."
            )
        row = await session.scalar(
            select(PaymentTypeAccount).where(
                PaymentTypeAccount.ledger_id == ledger.id,
                PaymentTypeAccount.payment_type_code == body.payment_type_code,
            )
        )
        if row is None:
            row = PaymentTypeAccount(
                tenant_id=principal.tenant_id, ledger_id=ledger.id, **body.model_dump()
            )
            session.add(row)
        else:
            row.account_id = body.account_id
        await session.flush()
        return {"payment_type_code": row.payment_type_code, "account_id": row.account_id}


@router.post("/receivable-runs", status_code=201, summary="Sollstellungslauf: Vorschau")
async def preview_run(
    body: RunIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await receivables.create_preview(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            period=body.period_month,
            scope=body.scope,
            scope_id=body.scope_id,
        )
        return _run_out(run, await _items(session, run.id))


@router.get("/receivable-runs/{run_id}", summary="Sollstellungslauf")
async def get_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await _get(session, ReceivableRun, run_id)
        return _run_out(run, await _items(session, run.id))


@router.post("/receivable-runs/{run_id}/post", summary="Sollstellungslauf buchen")
async def post_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(ReceivableRun, run_id, with_for_update=True)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        try:
            await receivables.post_run(session, run, principal.user_id)
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Sollstellung für diesen Zeitraum wurde bereits gebucht.",
            ) from None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="receivable_run.posted",
            entity_type="receivable_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"period": run.period_month.isoformat(), "totals": run.totals},
        )
        return _run_out(run, await _items(session, run.id))


@router.post("/receivable-runs/{run_id}/reverse", summary="Sollstellungslauf stornieren")
async def reverse_run(
    run_id: uuid.UUID,
    body: RunReverseIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(ReceivableRun, run_id, with_for_update=True)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        count = await receivables.reverse_run(
            session, run, principal.user_id, body.reason, body.booking_date or local_today()
        )
        return {"reversed": count, "status": run.status.value}


@router.post("/admin-fees", status_code=201, summary="Verwalterhonorar einrichten")
async def create_fee(
    body: FeeIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        data = body.model_dump()
        data["amounts_per_unit_type"] = {k: str(v) for k, v in body.amounts_per_unit_type.items()}
        row = AdminFeeSetting(tenant_id=principal.tenant_id, created_by=principal.user_id, **data)
        session.add(row)
        await session.flush()
        return {"id": row.id}


@router.get("/admin-fees/{fee_id}/invoice-preview", summary="Honorarrechnung als Entwurf berechnen")
async def fee_preview(
    fee_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Draft only: issuing an invoice (XRechnung) needs the tax data of the tenant (M13-04)."""
    from mhvp.properties.models import Unit

    async with tenant_tx(request, principal) as session:
        fee = await _get(session, AdminFeeSetting, fee_id)
        rows = await session.execute(
            select(Unit.unit_type, func.count())
            .where(Unit.property_id == fee.property_id)
            .group_by(Unit.unit_type)
        )
        counts = {unit_type.value: int(n) for unit_type, n in rows.all()}
        return receivables.admin_fee(fee, counts)


# Incoming invoices (M14, 7.9.1) --------------------------------------------------------


class InvoiceLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    net: Decimal
    vat_percent: Decimal = Decimal(0)
    vat: Decimal = Decimal(0)
    accrual_date: date | None = None
    section_35a_amount: Decimal | None = None
    unit_id: uuid.UUID | None = None
    text: str | None = Field(default=None, max_length=500)


class InvoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID
    provider_contact_id: uuid.UUID
    kind: InvoiceKind = InvoiceKind.INVOICE
    number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None
    service_from: date | None = None
    service_to: date | None = None
    net: Decimal
    vat: Decimal
    gross: Decimal
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    discount_until: date | None = None
    payee_iban: str | None = Field(default=None, max_length=34)
    document_id: uuid.UUID | None = None
    e_invoice_format: str = Field(default="none", pattern="^(none|xrechnung|zugferd)$")
    order_reference: str | None = Field(default=None, max_length=100)
    deductions: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    supersedes_id: uuid.UUID | None = None
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=200)


class InvoiceReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: str = Field(pattern="^(completeness|factual|arithmetic_tax)$")
    result: str = Field(pattern="^(ok|query|objected|reservation)$")
    reason: str = Field(min_length=3, max_length=4000)
    scope: str | None = Field(default=None, max_length=2000)


def _invoice_out(
    inv: Invoice, lines: list[InvoiceLine], reviews: list[InvoiceReview]
) -> dict[str, Any]:
    return {
        "id": inv.id,
        "ledger_id": inv.ledger_id,
        "provider_contact_id": inv.provider_contact_id,
        "creditor_account_id": inv.creditor_account_id,
        "kind": inv.kind.value,
        "number": inv.number,
        "invoice_date": inv.invoice_date,
        "due_date": inv.due_date,
        "net": inv.net,
        "vat": inv.vat,
        "gross": inv.gross,
        "discount_percent": inv.discount_percent,
        "discount_until": inv.discount_until,
        "payee_iban_suffix": inv.payee_iban[-4:] if inv.payee_iban else None,
        "iban_confirmed": inv.iban_confirmed_by is not None,
        "document_id": inv.document_id,
        "deductions": inv.deductions,
        "review_status": inv.review_status.value,
        "posting_status": inv.posting_status.value,
        "released": inv.released_by is not None and inv.released_hash == invoices.payment_hash(inv),
        "duplicate_of_id": inv.duplicate_of_id,
        "supersedes_id": inv.supersedes_id,
        "journal_entry_id": inv.journal_entry_id,
        "version": inv.version,
        "findings": inv.findings,
        "lines": [
            {
                "account_id": ln.account_id,
                "net": ln.net,
                "vat_percent": ln.vat_percent,
                "vat": ln.vat,
                "text": ln.text,
            }
            for ln in lines
        ],
        "reviews": [
            {
                "step": r.step,
                "result": r.result,
                "reason": r.reason,
                "user_id": r.user_id,
                "version": r.invoice_version,
                "decided_at": r.decided_at,
            }
            for r in reviews
        ],
    }


async def _invoice_full(session: AsyncSession, inv: Invoice) -> dict[str, Any]:
    lines = list(
        (await session.scalars(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id))).all()
    )
    reviews = list(
        (
            await session.scalars(
                select(InvoiceReview)
                .where(InvoiceReview.invoice_id == inv.id)
                .order_by(InvoiceReview.decided_at)
            )
        ).all()
    )
    return _invoice_out(inv, lines, reviews)


async def _invoice(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return inv


@router.post("/invoices", status_code=201, summary="Eingangsrechnung erfassen")
async def create_invoice(
    body: InvoiceIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _ledger(session, body.ledger_id)
        inv = Invoice(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            **body.model_dump(exclude={"lines", "payee_iban"}),
        )
        await invoices.write(session, inv, [ln.model_dump() for ln in body.lines], body.payee_iban)
        return await _invoice_full(session, inv)


@router.put("/invoices/{invoice_id}", summary="Rechnung ändern (neue Version, Freigaben entfallen)")
async def update_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        if inv.posting_status is not PostingStatus.UNPOSTED:
            raise ProblemError(
                ErrorCodes.ACC_POSTED_IMMUTABLE,
                detail="Gebuchte Rechnungen werden per Storno korrigiert.",
            )
        before_iban = inv.payee_iban_fingerprint
        for key, value in body.model_dump(exclude={"lines", "payee_iban"}).items():
            setattr(inv, key, value)
        inv.version += 1
        inv.review_status = ReviewStatus.OPEN  # reviews refer to the old version (PÜ05)
        await invoices.write(session, inv, [ln.model_dump() for ln in body.lines], body.payee_iban)
        if inv.payee_iban_fingerprint != before_iban:
            inv.iban_confirmed_by = None
            await invoices.evaluate(session, inv)
        await session.flush()
        return await _invoice_full(session, inv)


@router.get("/invoices/{invoice_id}", summary="Rechnung mit Prüfschritten")
async def get_invoice(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await session.get(Invoice, invoice_id)
        if inv is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await _invoice_full(session, inv)


@router.get("/invoices", summary="Rechnungseingang")
async def list_invoices(
    request: Request,
    ledger_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        query = select(Invoice).order_by(Invoice.invoice_date.desc())
        if ledger_id:
            query = query.where(Invoice.ledger_id == ledger_id)
        if review_status:
            query = query.where(Invoice.review_status == review_status)
        return [
            await _invoice_full(session, i) for i in (await session.scalars(query.limit(500))).all()
        ]


@router.post(
    "/invoices/{invoice_id}/reviews", status_code=201, summary="Prüfschritt erfassen (PÜ05)"
)
async def review_invoice(
    invoice_id: uuid.UUID,
    body: InvoiceReviewIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        if inv.posting_status is not PostingStatus.UNPOSTED:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Rechnung ist bereits gebucht.")
        if principal.user_id is None:
            raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Reviews need a person.")
        session.add(
            InvoiceReview(
                tenant_id=principal.tenant_id,
                invoice_id=inv.id,
                invoice_version=inv.version,
                user_id=principal.user_id,
                **body.model_dump(),
            )
        )
        await session.flush()
        reviews = list(
            (
                await session.scalars(
                    select(InvoiceReview).where(InvoiceReview.invoice_id == inv.id)
                )
            ).all()
        )
        inv.review_status = invoices.aggregate(reviews, inv.version)
        await session.flush()
        return await _invoice_full(session, inv)


@router.post("/invoices/{invoice_id}/confirm-iban", summary="Abweichende IBAN gesondert bestätigen")
async def confirm_iban(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """A changed IBAN is confirmed by a person other than the one who entered the invoice (PÜ04)."""
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        if inv.payee_iban is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine IBAN auf der Rechnung.")
        if inv.created_by == principal.user_id or principal.is_platform_admin:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES,
                detail="Die Bestätigung muss eine andere Person vornehmen.",
            )
        inv.iban_confirmed_by = principal.user_id
        await invoices.evaluate(session, inv)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.iban_confirmed",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload={"iban_suffix": inv.payee_iban[-4:]},
        )
        await session.flush()
        return await _invoice_full(session, inv)


@router.post(
    "/invoices/{invoice_id}/release", summary="Rechnungsfreigabe (zweite Person, versionsgebunden)"
)
async def release_invoice(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        if inv.review_status not in (ReviewStatus.CLOSED_OK, ReviewStatus.CLOSED_WITH_RESERVATION):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Prüfung ist nicht abgeschlossen.")
        if inv.created_by == principal.user_id or principal.is_platform_admin:
            raise ProblemError(
                ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
            )
        if any("IBAN weicht" in f for f in inv.findings):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Abweichende IBAN ist nicht bestätigt.")
        inv.released_by, inv.released_hash = principal.user_id, invoices.payment_hash(inv)
        await session.flush()
        return await _invoice_full(session, inv)


@router.post("/invoices/{invoice_id}/post", summary="Rechnung buchen (Kreditor, offener Posten)")
async def post_invoice(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await _invoice(session, invoice_id)
        entry = await invoices.post(session, inv, principal.user_id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.posted",
            entity_type="invoice",
            entity_id=inv.id,
            actor_user_id=principal.user_id,
            payload={"journal_entry_id": str(entry.id)},
        )
        return await _invoice_full(session, inv)


@router.get("/invoices/{invoice_id}/discount", summary="Skonto zum Zahltag")
async def invoice_discount(
    invoice_id: uuid.UUID,
    pay_date: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        inv = await session.get(Invoice, invoice_id)
        if inv is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        value = invoices.discount(inv, pay_date)
        return {"discount": value, "payable": inv.gross - value}


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ledger_id: uuid.UUID
    provider_contact_id: uuid.UUID
    account_id: uuid.UUID
    gross: Decimal = Field(gt=0)
    interval_months: int = Field(default=1, ge=1, le=12)
    start_date: date
    end_date: date | None = None
    text: str = Field(min_length=1, max_length=300)


@router.post("/recurring-invoices", status_code=201, summary="Rechnungsplan anlegen")
async def create_plan(
    body: PlanIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, body.ledger_id)
        account = await _get(session, LedgerAccount, body.account_id)
        if account.ledger_id != ledger.id:
            raise ProblemError(ErrorCodes.ACC_WRONG_ENTITY)
        plan = RecurringInvoicePlan(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            next_due=body.start_date,
            **body.model_dump(),
        )
        session.add(plan)
        await session.flush()
        return {"id": plan.id, "next_due": plan.next_due}


@router.post(
    "/recurring-invoices/{plan_id}/generate",
    status_code=201,
    summary="Fällige Dauerrechnung als Entwurf erzeugen",
)
async def generate_plan(
    plan_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Next due recurring invoice as unreviewed draft; nothing is posted automatically."""
    async with tenant_tx(request, principal) as session:
        plan = await session.get(RecurringInvoicePlan, plan_id, with_for_update=True)
        if plan is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if plan.end_date is not None and plan.next_due > plan.end_date:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Der Rechnungsplan ist beendet.")
        inv = Invoice(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=plan.ledger_id,
            provider_contact_id=plan.provider_contact_id,
            kind=InvoiceKind.RECURRING,
            number=f"PLAN-{plan.id.hex[:8]}-{plan.next_due:%Y%m}",
            invoice_date=plan.next_due,
            due_date=plan.next_due,
            service_from=plan.next_due,
            net=plan.gross,
            vat=Decimal("0.00"),
            gross=plan.gross,
        )
        await invoices.write(
            session,
            inv,
            [{"account_id": plan.account_id, "net": plan.gross, "text": plan.text}],
            None,
        )
        month = plan.next_due.month - 1 + plan.interval_months
        plan.next_due = plan.next_due.replace(
            year=plan.next_due.year + month // 12, month=month % 12 + 1
        )
        await session.flush()
        return await _invoice_full(session, inv)


# Dunning (M16, 7.5); only the leading system may dun ------------------------------------


class DunningSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID | None = None
    levels: list[dict[str, Any]] = Field(min_length=1, max_length=5)
    threshold_amount: Decimal = Field(default=Decimal("0"), ge=0)


class DunningRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_date: date


def _dunning_out(run: DunningRun, cases: list[DunningCase]) -> dict[str, Any]:
    return {
        "id": run.id,
        "run_date": run.run_date,
        "status": run.status,
        "totals": run.totals,
        "fees_and_interest": "locked_until_v7",
        "cases": [
            {
                "contract_id": c.contract_id,
                "debtor_account_id": c.debtor_account_id,
                "level": c.level,
                "total": c.total,
                "fee_amount": c.fee_amount,
                "interest_amount": c.interest_amount,
                "status": c.status,
                "reason": c.reason,
                "open_items": c.open_items,
            }
            for c in cases
        ],
    }


@router.put("/dunning-settings", summary="Mahnstufen (ohne Gebühren und Zinsen bis V7)")
async def put_dunning_settings(
    body: DunningSettingsIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    for level in body.levels:
        if (
            set(level) - {"level", "min_days_overdue", "text"}
            or "level" not in level
            or "min_days_overdue" not in level
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Stufe: level, min_days_overdue, text; Gebühren, Zinsen bis V7 gesperrt.",
            )
    async with tenant_tx(request, principal) as session:
        row = await dunning.settings_for(session, body.property_id)
        if row is None or row.property_id != body.property_id:
            row = DunningSettings(tenant_id=principal.tenant_id, property_id=body.property_id)
            session.add(row)
        row.levels, row.threshold_amount = body.levels, body.threshold_amount
        await session.flush()
        return {"id": row.id, "levels": row.levels, "threshold_amount": row.threshold_amount}


@router.post("/dunning-runs", status_code=201, summary="Mahnlauf: Vorschau")
async def dunning_preview(
    body: DunningRunIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await dunning.preview(
            session,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
            run_date=body.run_date,
        )
        cases = list(
            (await session.scalars(select(DunningCase).where(DunningCase.run_id == run.id))).all()
        )
        return _dunning_out(run, cases)


@router.get("/dunning-runs", summary="Mahnläufe (neueste zuerst)")
async def dunning_runs(
    request: Request,
    limit: int = Query(default=20, ge=1, le=200),
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        runs = (
            await session.scalars(
                select(DunningRun)
                .order_by(DunningRun.run_date.desc(), DunningRun.created_at.desc())
                .limit(limit)
            )
        ).all()
        return [
            {"id": r.id, "run_date": r.run_date, "status": r.status, "totals": r.totals}
            for r in runs
        ]


@router.get("/dunning-runs/{run_id}", summary="Mahnlauf")
async def dunning_run(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        run = await session.get(DunningRun, run_id)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        cases = list(
            (await session.scalars(select(DunningCase).where(DunningCase.run_id == run.id))).all()
        )
        return _dunning_out(run, cases)


@router.post(
    "/dunning-runs/{run_id}/approve", summary="Mahnlauf freigeben (zweite Person, führendes System)"
)
async def dunning_approve(
    run_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Approvals need a person.")
    async with tenant_tx(request, principal) as session:
        run = await session.get(DunningRun, run_id, with_for_update=True)
        if run is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await dunning.approve(session, run, principal.user_id, principal.is_platform_admin)
        cases = list(
            (await session.scalars(select(DunningCase).where(DunningCase.run_id == run.id))).all()
        )
        return _dunning_out(run, cases)


# Evaluations and exports (M18, 7.5, 7.7) -----------------------------------------------

EXPORT = require_permission("accounting:export")


@router.get("/ledgers/{ledger_id}/liquidity", summary="Liquiditätsvorschau 90 Tage")
async def liquidity(
    ledger_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return await reports.liquidity(
            session, await _ledger(session, ledger_id), as_of or local_today()
        )


@router.get("/ledgers/{ledger_id}/payments-by-debtor", summary="Zahlungen je Debitor")
async def payments_by_debtor(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        return await reports.payments_by_debtor(
            session, await _ledger(session, ledger_id), start, end
        )


@router.get("/ledgers/{ledger_id}/revenue", summary="Erträge je Erlöskonto")
async def revenue(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        return await reports.revenue(session, await _ledger(session, ledger_id), start, end)


@router.post(
    "/ledgers/{ledger_id}/exports/journal",
    status_code=201,
    summary="Journal-Export (CSV) mit Prüfsumme",
)
async def export_journal(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(EXPORT),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        data, rows = await reports.journal_csv(session, ledger, start, end)
        run = ExportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            format="journal_csv",
            period_from=start,
            period_to=end,
            rows=rows,
            sha256=reports.checksum(data),
        )
        session.add(run)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="export_run.created",
            entity_type="export_run",
            entity_id=run.id,
            actor_user_id=principal.user_id,
            payload={"format": run.format, "rows": rows},
        )
        await session.flush()
        return {"id": run.id, "rows": rows, "sha256": run.sha256, "content": data.decode("utf-8")}


@router.post(
    "/ledgers/{ledger_id}/exports/datev", summary="DATEV-Buchungsstapel (nicht freigegeben)"
)
async def export_datev(ledger_id: uuid.UUID, principal: TenantPrincipal = Depends(EXPORT)) -> None:
    """The DATEV format version and the consultant/client numbers are not specified (M18-01)."""
    raise ProblemError(
        ErrorCodes.CONFLICT,
        detail="DATEV-Format und Berater-/Mandantennummern sind noch nicht festgelegt (M18-01).",
    )
