"""Ledger endpoints (/api/v1/accounting, M10).

Postings are allowed in ledgers that are not leading (parallel operation with Immoware24).
Declaring the platform as leading system requires release gate G1 (18.0, 6.9.10).
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import (
    dunning,
    dunning_letters,
    invoices,
    numbering,
    receivables,
    reports,
    xrechnung,
)
from mhvp.accounting import services as svc
from mhvp.accounting.models import (
    AdminFeeSetting,
    ChartTemplate,
    DunningCase,
    DunningMahnbescheidPrep,
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
from mhvp.core.auth.scope import (
    ensure_session_legal_entity_allowed,
    session_allowed_legal_entity_ids,
)
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
    # A37: legal entity scope of the membership (tax advisor); foreign ledgers answer 404.
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
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
        # A37: a scoped membership (tax advisor) only lists its assigned legal entities.
        allowed = session_allowed_legal_entity_ids(session)
        if allowed is not None:
            query = query.where(Ledger.legal_entity_id.in_(list(allowed)))
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
            # D48: two concurrent calls with the same key are serialised so that the second
            # one finds the first draft instead of failing on the unique index (B08).
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"entry_idempotency:{ledger.id}:{body.idempotency_key}"},
            )
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
    from mhvp.contacts.models import Party

    async with tenant_tx(request, principal) as session:
        if body.invoice_debtor_party_id is not None:
            await _get(session, Party, body.invoice_debtor_party_id)  # D58: debtor must exist
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
    async with tenant_tx(request, principal) as session:
        fee = await _get(session, AdminFeeSetting, fee_id)
        counts = await receivables.fee_unit_counts(session, fee, local_today())
        return await receivables.admin_fee_draft(session, fee, counts)


@router.post(
    "/admin-fees/{fee_id}/invoice-issue",
    summary="Honorarrechnung als XRechnung ausstellen (Rechnungsnummer, USt-Prüfung)",
)
async def fee_issue(
    fee_id: uuid.UUID,
    request: Request,
    invoice_date: date | None = None,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Allocates the gapless PREFIX-JJJJ-000001 invoice number (M13-04) and blocks when the
    tenant's VAT status or tax data required for XRechnung is missing."""
    from mhvp.platform.models import TenantBillingSettings

    async with tenant_tx(request, principal) as session:
        fee = await _get(session, AdminFeeSetting, fee_id)
        issue_date = invoice_date or local_today()
        counts = await receivables.fee_unit_counts(session, fee, issue_date)
        draft = await receivables.admin_fee_draft(session, fee, counts)
        billing_settings = await session.scalar(
            select(TenantBillingSettings).where(
                TenantBillingSettings.tenant_id == principal.tenant_id
            )
        )
        numbering.assert_xrechnung_allowed(billing_settings)
        number = await numbering.allocate_invoice_number(
            session, principal.tenant_id, issue_date.year
        )
        # A12: the issued invoice is frozen for the XRechnung XML
        # (GET /accounting/invoices/{id}/xrechnung.xml, mhvp.accounting.xrechnung).
        issued = await xrechnung.issue(
            session,
            fee=fee,
            draft=draft,
            number=number,
            issue_date=issue_date,
            billing=billing_settings,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        draft["id"] = str(issued.id)
        draft["number"] = number
        draft["invoice_date"] = issue_date
        draft["status"] = issued.status.value
        draft["xrechnung_url"] = f"/api/v1/accounting/invoices/{issued.id}/xrechnung.xml"
        # A69: outgoing event for subscribers (section 12, docs/integrations/webhooks.md).
        # Identifiers and amounts only; the debtor's name, address and IBAN stay out.
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="invoice.issued",
            entity_type="admin_fee_invoice",
            entity_id=issued.id,
            actor_user_id=principal.user_id,
            payload={
                "invoice_id": str(issued.id),
                "number": number,
                "invoice_date": issue_date.isoformat(),
                "kind": "admin_fee",
                "fee_setting_id": str(fee.id),
                "property_id": str(fee.property_id),
                "debtor_legal_entity_id": (
                    str(issued.debtor_legal_entity_id) if issued.debtor_legal_entity_id else None
                ),
                "net": str(issued.net),
                "vat": str(issued.vat),
                "gross": str(issued.gross),
                "currency": "EUR",
                "xrechnung_url": draft["xrechnung_url"],
            },
        )
        return draft


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
    recipient_name: str | None = Field(default=None, max_length=400)
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
    """Tenant default (``property_id`` None): ``levels`` required, an omitted
    ``threshold_amount`` means 0 and an omitted ``interest_enabled`` means off. Object
    override: every field may be ``null`` and then inherits the tenant default (M16-11); a
    level entry may leave out ``text``, ``fee_amount``, ``payment_days`` and ``letter_text``
    to inherit them from the tenant level of the same number."""

    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID | None = None
    levels: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=5)
    threshold_amount: Decimal | None = Field(default=None, ge=0)
    fee_from_level: int | None = Field(default=None, ge=1)
    interest_enabled: bool | None = None
    interest_base_rate: Decimal | None = Field(default=None, ge=0)
    interest_spread: Decimal | None = Field(default=None, ge=0)


class DunningSettingsPresetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    property_id: uuid.UUID | None = None
    interest_profile: str | None = Field(default=None, pattern="^(verbraucher|unternehmer)$")


class DunningRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_date: date


class DunningLetterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    letter_date: date | None = None


class DunningLetterTextPreviewIn(BaseModel):
    """Text of one level with sample items for the settings form (A33). Only values given
    here are used: no fee without ``fee_amount``, no deadline without ``payment_days``."""

    model_config = ConfigDict(extra="forbid")
    level: int = Field(ge=1, le=9)
    text: str | None = Field(default=None, max_length=200)
    letter_text: str | None = Field(default=None, max_length=4000)
    fee_amount: Decimal | None = Field(default=None, ge=0)
    payment_days: int | None = Field(default=None, ge=0)
    letter_date: date | None = None


def _settings_status(eff: dunning.EffectiveSettings | None) -> str:
    if eff is None or not eff.levels:
        return "nicht eingerichtet"
    fees_configured = eff.fee_from_level is not None and any(
        lv.get("fee_amount") is not None for lv in eff.levels
    )
    interest_configured = eff.interest_enabled and eff.interest_base_rate is not None
    if fees_configured and interest_configured:
        return "gebuehr_und_zins_hinterlegt"
    if fees_configured:
        return "nur_gebuehr_hinterlegt"
    if interest_configured:
        return "nur_zins_hinterlegt"
    return "kein_betrag_hinterlegt"


async def _dunning_out(
    session: AsyncSession, run: DunningRun, cases: list[DunningCase]
) -> dict[str, Any]:
    """Each case carries ``highest_level`` of the ladder that applies to its ledger's property
    (object override or tenant default, M16-10), so clients never compare against the wrong
    ceiling."""
    ceiling: dict[uuid.UUID, int | None] = {}
    out = []
    for case in cases:
        if case.ledger_id not in ceiling:
            ledger = await session.get(Ledger, case.ledger_id)
            eff = await dunning.settings_for(session, ledger.property_id if ledger else None)
            ceiling[case.ledger_id] = (
                max((int(lv["level"]) for lv in eff.levels), default=None) if eff else None
            )
        out.append({**_case_out(case), "highest_level": ceiling[case.ledger_id]})
    return {
        "id": run.id,
        "run_date": run.run_date,
        "status": run.status,
        "totals": run.totals,
        "cases": out,
    }


def _own_out(row: DunningSettings | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "levels": row.levels,
        "threshold_amount": row.threshold_amount,
        "fee_from_level": row.fee_from_level,
        "interest_enabled": row.interest_enabled,
        "interest_base_rate": row.interest_base_rate,
        "interest_spread": row.interest_spread,
    }


def _dunning_settings_out(
    eff: dunning.EffectiveSettings | None, property_id: uuid.UUID | None
) -> dict[str, Any]:
    """Effective values (after inheritance) plus ``own`` (the stored row of this scope, or
    ``null``) and ``sources`` per field (``objekt`` or ``mandant``)."""
    if eff is None:
        return {
            "id": None,
            "property_id": property_id,
            "levels": [],
            "threshold_amount": Decimal("0.00"),
            "fee_from_level": None,
            "interest_enabled": False,
            "interest_base_rate": None,
            "interest_spread": None,
            "status": "nicht eingerichtet",
            "sources": {},
            "own": None,
            "tenant_default_exists": False,
        }
    own = eff.property_row if property_id is not None else eff.tenant_row
    return {
        "id": own.id if own is not None else None,
        "property_id": property_id,
        "levels": eff.levels,
        "threshold_amount": eff.threshold_amount,
        "fee_from_level": eff.fee_from_level,
        "interest_enabled": eff.interest_enabled,
        "interest_base_rate": eff.interest_base_rate,
        "interest_spread": eff.interest_spread,
        "status": _settings_status(eff),
        "sources": eff.sources,
        "own": _own_out(own),
        "tenant_default_exists": eff.tenant_row is not None,
    }


def _check_levels(levels: list[dict[str, Any]], *, override: bool) -> None:
    for level in levels:
        if (
            set(level) - dunning.LEVEL_KEYS
            or "level" not in level
            or "min_days_overdue" not in level
            or (not override and "text" not in level)
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Stufe: level, min_days_overdue, text, optional fee_amount, payment_days, "
                    "letter_text."
                ),
            )
        fee = level.get("fee_amount")
        if fee is not None and Decimal(str(fee)) < 0:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Mahngebühr darf nicht negativ sein.")
        days = level.get("payment_days")
        if days is not None and int(days) < 0:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Zahlungsfrist darf nicht negativ sein."
            )
        if level.get("letter_text"):
            dunning_letters.check_letter_text(str(level["letter_text"]))
    numbers = [int(lv["level"]) for lv in levels]
    if len(numbers) != len(set(numbers)):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Jede Mahnstufe nur einmal.")


@router.get(
    "/dunning-settings", summary="Mahnstufen, Gebühren und Zins lesen (Mandant oder Objekt)"
)
async def get_dunning_settings(
    request: Request,
    property_id: uuid.UUID | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        eff = await dunning.settings_for(session, property_id)
        return _dunning_settings_out(eff, property_id)


@router.get(
    "/dunning-settings/overrides",
    summary="Objekte mit eigener Mahnstufen-Überschreibung",
)
async def list_dunning_overrides(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(DunningSettings)
                .where(DunningSettings.property_id.is_not(None))
                .order_by(DunningSettings.created_at)
            )
        ).all()
        return [
            {
                "id": r.id,
                "property_id": r.property_id,
                "overridden_fields": [
                    name for name in dunning.INHERITABLE_FIELDS if getattr(r, name) is not None
                ],
            }
            for r in rows
        ]


@router.put("/dunning-settings", summary="Mahnstufen, Gebühren (je Stufe, nur mit Betrag) und Zins")
async def put_dunning_settings(
    body: DunningSettingsIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    override = body.property_id is not None
    if not override and body.levels is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Mandantenvorgabe: Mahnstufen (levels) sind Pflicht."
        )
    if body.levels is not None:
        _check_levels(body.levels, override=override)
    async with tenant_tx(request, principal) as session:
        tenant_row = await dunning.settings_row(session, None)
        if override and tenant_row is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Zuerst die Mandantenvorgabe anlegen, dann Objekte überschreiben.",
            )
        if override and all(getattr(body, name) is None for name in dunning.INHERITABLE_FIELDS):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Eine Objektüberschreibung braucht mindestens einen eigenen Wert.",
            )
        row = await dunning.settings_row(session, body.property_id)
        if row is None:
            row = DunningSettings(tenant_id=principal.tenant_id, property_id=body.property_id)
            session.add(row)
        row.levels = body.levels
        row.fee_from_level = body.fee_from_level
        row.interest_base_rate = body.interest_base_rate
        row.interest_spread = body.interest_spread
        if override:
            row.threshold_amount = body.threshold_amount
            row.interest_enabled = body.interest_enabled
        else:  # the tenant default is always complete; omitted means 0 / off, never inherit
            row.threshold_amount = body.threshold_amount or Decimal("0")
            row.interest_enabled = bool(body.interest_enabled)
        await session.flush()
        eff = dunning.resolve(
            row if not override else tenant_row, row if override else None, body.property_id
        )
        if eff is not None and eff.interest_enabled and eff.interest_base_rate is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Verzugszins kann erst mit hinterlegtem Basiszinssatz aktiviert werden "
                    "(halbjährlich zu pflegen, kein Wert hinterlegt bis Eingabe)."
                ),
            )
        return _dunning_settings_out(eff, body.property_id)


@router.delete(
    "/dunning-settings",
    status_code=204,
    summary="Objektüberschreibung entfernen (Objekt erbt wieder die Mandantenvorgabe)",
)
async def delete_dunning_override(
    request: Request, property_id: uuid.UUID, principal: TenantPrincipal = Depends(APPROVE)
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await dunning.settings_row(session, property_id)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await session.delete(row)
        await session.flush()
    return Response(status_code=204)


@router.post(
    "/dunning-settings/presets",
    status_code=201,
    summary="Vorschlagswerte laden (Betreiberentscheidung 25.09.2026, V7)",
)
async def post_dunning_settings_presets(
    body: DunningSettingsPresetIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        tenant_row = await dunning.settings_row(session, None)
        if body.property_id is not None and tenant_row is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Zuerst die Mandantenvorgabe anlegen, dann Objekte überschreiben.",
            )
        row = await dunning.settings_row(session, body.property_id)
        if row is None:
            row = DunningSettings(tenant_id=principal.tenant_id, property_id=body.property_id)
            session.add(row)
        row.levels = dunning.preset_levels()
        row.fee_from_level = 2  # ab der 1. Mahnung (V7)
        row.interest_enabled = False if body.property_id is None else None
        row.interest_base_rate = None
        if body.property_id is None and row.threshold_amount is None:
            row.threshold_amount = Decimal("0")
        if body.interest_profile:
            row.interest_spread = Decimal(dunning.interest_spread_presets()[body.interest_profile])
        await session.flush()
        eff = dunning.resolve(
            tenant_row if body.property_id is not None else row,
            row if body.property_id is not None else None,
            body.property_id,
        )
        return {
            **_dunning_settings_out(eff, body.property_id),
            "note": (
                "Vorschlagswerte laut Betreiberentscheidung 25.09.2026 (V7, teilweise "
                "entschieden). Gebührenbeträge und Basiszinssatz bleiben leer, bis der "
                "Betreiber sie einträgt; rechtliche Prüfung der Gebührenhöhe und Grundlage "
                "steht aus."
            ),
        }


@router.post(
    "/dunning-settings/letter-preview",
    summary="Textbaustein einer Mahnstufe mit Beispielposten (A33, nur Text, kein Versand)",
)
async def dunning_letter_text_preview(
    body: DunningLetterTextPreviewIn,
    principal: TenantPrincipal = Depends(READ),
) -> dict[str, Any]:
    """Standard text or the given ``letter_text`` of a level, rendered with sample items;
    placeholders are checked (422 on unknown ones). No bank account is passed: which account
    may appear in a letter is an open operator decision (M16-13)."""
    if body.letter_text:
        dunning_letters.check_letter_text(body.letter_text)
    return dunning_letters.sample_preview(
        level=body.level,
        level_text=body.text,
        letter_text=body.letter_text,
        fee_amount=body.fee_amount,
        payment_days=body.payment_days,
        letter_date=body.letter_date or local_today(),
    )


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
        return await _dunning_out(session, run, cases)


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
        return await _dunning_out(session, run, cases)


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
        return await _dunning_out(session, run, cases)


class DunningMarkSentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: str = Field(pattern="^(post|email|portal)$")


def _case_out(case: DunningCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "contract_id": case.contract_id,
        "debtor_account_id": case.debtor_account_id,
        "level": case.level,
        "total": case.total,
        "fee_amount": case.fee_amount,
        "interest_amount": case.interest_amount,
        "status": case.status,
        "reason": case.reason,
        "open_items": case.open_items,
        "fee_entry_id": case.fee_entry_id,
        "fee_invoice_draft_id": case.fee_invoice_draft_id,
        "delivery_channel": case.delivery_channel,
        "delivered_at": case.delivered_at,
        "letter_document_id": case.letter_document_id,
    }


@router.post(
    "/dunning-cases/{case_id}/mark-sent",
    summary="Mahnung als versendet markieren (M16-09: nur so kann die Stufe steigen)",
)
async def dunning_mark_sent(
    case_id: uuid.UUID,
    body: DunningMarkSentIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    if principal.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Needs a person.")
    async with tenant_tx(request, principal) as session:
        case = await session.get(DunningCase, case_id, with_for_update=True)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await dunning.mark_sent(session, case, body.channel, principal.user_id)
        return _case_out(case)


async def _letter_pdf(
    session: AsyncSession, request: Request, case_id: uuid.UUID, letter_date: date | None
) -> tuple[DunningCase, dunning_letters.LetterDraft, bytes]:
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore

    case = await session.get(DunningCase, case_id)
    if case is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
    draft = await dunning_letters.build(session, case, head, letter_date or local_today())
    return case, draft, dunning_letters.render(head, draft)


@router.post(
    "/dunning-cases/{case_id}/letter-preview",
    summary="Mahnschreiben als PDF-Entwurf (Vorschau, nicht abgelegt, kein Versand)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def dunning_letter_preview(
    case_id: uuid.UUID,
    request: Request,
    body: DunningLetterIn | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        _, draft, pdf = await _letter_pdf(
            session, request, case_id, body.letter_date if body else None
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{quote(draft.filename)}"',
        },
    )


@router.post(
    "/dunning-cases/{case_id}/letter",
    status_code=201,
    summary="Mahnschreiben als PDF-Entwurf erzeugen und ablegen (kein Versand)",
)
async def dunning_letter_create(
    case_id: uuid.UUID,
    request: Request,
    body: DunningLetterIn | None = None,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        case, draft, pdf = await _letter_pdf(
            session, request, case_id, body.letter_date if body else None
        )
        from mhvp.documents.blobs import BlobStore

        document_id = await dunning_letters.store(
            session,
            BlobStore(request.app.state.settings),
            case=case,
            draft=draft,
            pdf=pdf,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        return {
            **_case_out(case),
            "letter_document_id": document_id,
            "hinweis": dunning_letters.DRAFT_LABEL,
        }


@router.post(
    "/dunning-cases/{case_id}/letter/send",
    summary="Mahnschreiben versenden (gesperrt: G1 geschlossen, Versand nicht umgesetzt, M16-02)",
)
async def dunning_letter_send(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Locked on purpose (0.1.1, API first 0.1.4): the endpoint exists so that clients and
    jobs hit the same lock. G1 must be open for the tenant, and even then the dispatch path
    (postal or e-mail evidence, M16-02) is not released, so the request is always refused."""
    resolver: ReleaseGateResolver = request.app.state.release_gate_resolver
    await ensure_release_gate_open(ReleaseGate.G1, principal.tenant_id, resolver)
    raise ProblemError(
        ErrorCodes.CONFLICT,
        detail=(
            "Der Versand von Mahnschreiben ist nicht freigegeben (M16-02). Das Schreiben "
            "bleibt Entwurf; der Versand erfolgt außerhalb der Plattform und wird mit "
            '"Als versendet markieren" dokumentiert.'
        ),
        extensions={"locked": "dunning_letter_send", "case_id": str(case_id)},
    )


def _mahnbescheid_out(prep: Any) -> dict[str, Any]:
    return {
        "id": prep.id,
        "case_id": prep.case_id,
        "antragsteller_legal_entity_id": prep.antragsteller_legal_entity_id,
        "antragsgegner": prep.antragsgegner_snapshot,
        "hauptforderung": prep.hauptforderung,
        "nebenforderungen": prep.nebenforderungen,
        "zustelladresse": prep.zustelladresse,
        "aktenzeichen_intern": prep.aktenzeichen_intern,
        "status": prep.status,
        "hinweis": (
            "Vorbereitung, Prüfung durch Rechtsanwalt. Fristen sind nur Hinweise und zu prüfen; "
            "keine rechtliche Vollständigkeitsprüfung, keine Antragstellung durch die Plattform."
        ),
    }


@router.post(
    "/dunning-cases/{case_id}/mahnbescheid-vorbereitung",
    status_code=201,
    summary="Mahnbescheid vorbereiten (nach letzter Stufe)",
)
async def dunning_prepare_mahnbescheid(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        case = await session.get(DunningCase, case_id)
        if case is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        case_ledger = await session.get(Ledger, case.ledger_id)
        if case_ledger is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        settings = await dunning.settings_for(session, case_ledger.property_id)
        highest = max((int(lv["level"]) for lv in settings.levels), default=0) if settings else 0
        if case.level < highest:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Mahnbescheid nur nach der letzten Mahnstufe vorzubereiten.",
            )
        prep = await dunning.prepare_mahnbescheid(session, case, principal.user_id)
        return _mahnbescheid_out(prep)


@router.get(
    "/dunning-cases/{case_id}/mahnbescheid-vorbereitung",
    summary="Mahnbescheid-Vorbereitung (Export für Anwalt oder Online-Mahnantrag)",
)
async def dunning_get_mahnbescheid(
    case_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        prep = await session.scalar(
            select(DunningMahnbescheidPrep).where(DunningMahnbescheidPrep.case_id == case_id)
        )
        if prep is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return _mahnbescheid_out(prep)


async def _mahnbescheid_pdf(
    session: AsyncSession, request: Request, case_id: uuid.UUID, letter_date: date | None
) -> tuple[DunningCase, DunningMahnbescheidPrep, dunning_letters.LetterDraft, bytes]:
    """PDF of the stored preparation record (A31): it must exist first (POST
    ``mahnbescheid-vorbereitung``), so the export never precedes the data set."""
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore

    case = await session.get(DunningCase, case_id)
    if case is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    prep = await session.scalar(
        select(DunningMahnbescheidPrep).where(DunningMahnbescheidPrep.case_id == case.id)
    )
    if prep is None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Zuerst die Mahnbescheid-Vorbereitung anlegen, dann den PDF-Export erzeugen.",
        )
    head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
    draft = await dunning_letters.build_mahnbescheid(
        session, case, prep, head, letter_date or local_today()
    )
    return case, prep, draft, dunning_letters.render(head, draft)


@router.post(
    "/dunning-cases/{case_id}/mahnbescheid-preview",
    summary="Mahnbescheid-Vorbereitung als PDF (Vorschau, nicht abgelegt, kein Antrag)",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def dunning_mahnbescheid_preview(
    case_id: uuid.UUID,
    request: Request,
    body: DunningLetterIn | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> Response:
    async with tenant_tx(request, principal) as session:
        _, _, draft, pdf = await _mahnbescheid_pdf(
            session, request, case_id, body.letter_date if body else None
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{quote(draft.filename)}"',
        },
    )


@router.post(
    "/dunning-cases/{case_id}/mahnbescheid",
    status_code=201,
    summary="Mahnbescheid-Vorbereitung als PDF erzeugen und ablegen (kein Antrag)",
)
async def dunning_mahnbescheid_create(
    case_id: uuid.UUID,
    request: Request,
    body: DunningLetterIn | None = None,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from mhvp.documents.blobs import BlobStore

    async with tenant_tx(request, principal) as session:
        _, prep, draft, pdf = await _mahnbescheid_pdf(
            session, request, case_id, body.letter_date if body else None
        )
        document_id = await dunning_letters.store_mahnbescheid(
            session,
            BlobStore(request.app.state.settings),
            draft=draft,
            pdf=pdf,
            tenant_id=principal.tenant_id,
            user_id=principal.user_id,
        )
        return {
            **_mahnbescheid_out(prep),
            "document_id": document_id,
            "hinweis": dunning_letters.MAHNBESCHEID_NOTICE,
        }


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
    "/ledgers/{ledger_id}/exports/datev",
    status_code=201,
    summary="DATEV-Buchungsstapel (nur mit hinterlegten Beraterdaten)",
)
async def export_datev(
    ledger_id: uuid.UUID,
    start: date,
    end: date,
    request: Request,
    principal: TenantPrincipal = Depends(EXPORT),
) -> dict[str, Any]:
    """Emits the DATEV EXTF Buchungsstapel header only once consultant_number, client_number
    and chart_of_accounts are set (operator decision 25.09.2026, M18-01). Otherwise rejects with
    the existing message. Account numbers come from the operator's DATEV mapping (A36);
    missing mappings answer 409 MHVP-BILL-0008 with the list of accounts."""
    from mhvp.platform.models import ChartOfAccountsKind, TenantBillingSettings

    async with tenant_tx(request, principal) as session:
        ledger = await _ledger(session, ledger_id)
        settings = await session.scalar(
            select(TenantBillingSettings).where(
                TenantBillingSettings.tenant_id == principal.tenant_id
            )
        )
        if (
            settings is None
            or not settings.datev_consultant_number
            or not settings.datev_client_number
            or settings.datev_chart_of_accounts is ChartOfAccountsKind.UNSET
        ):
            raise ProblemError(
                ErrorCodes.DATEV_NOT_CONFIGURED,
                detail=(
                    "DATEV-Format und Berater-/Mandantennummern sind noch nicht "
                    "festgelegt (M18-01)."
                ),
            )
        data, rows = await reports.datev_csv(
            session,
            ledger,
            start,
            end,
            consultant_number=settings.datev_consultant_number,
            client_number=settings.datev_client_number,
            chart_of_accounts=settings.datev_chart_of_accounts.value,
            account_length=settings.datev_account_length,
            fiscal_year_start_month=settings.datev_fiscal_year_start_month,
        )
        run = ExportRun(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ledger_id=ledger.id,
            format="datev_buchungsstapel",
            period_from=start,
            period_to=end,
            rows=rows,
            sha256=reports.checksum(data),
            # A36: the Konto field carries the operator's mapping (datev_account_mapping);
            # unmapped accounts stopped the export before this point (MHVP-BILL-0008).
            note="Kontenzuordnung angewendet",
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


# Invoice intake (M14, manual actions only; no automatic polling, see docs/OPEN_QUESTIONS.md
# M14-05) -------------------------------------------------------------------------------------

intake_router = APIRouter(prefix="/invoices/intake", tags=["Buchhaltung"])


class PaperlessIntakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    paperless_document_id: int


@intake_router.post(
    "/paperless", status_code=202, summary="Beleg aus Paperless holen und Rechnung erfassen"
)
async def paperless_intake(
    body: PaperlessIntakeIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Pulls one document by id from Paperless-ngx into the document store (read only client
    already used for the ticket/property DMS panels, M31) and starts extract_invoice on it. No
    automatic polling: this is a manual action per document (M14-05)."""
    from mhvp.ai.models import AiTask
    from mhvp.ai.routers import start_extraction_run
    from mhvp.documents import services as doc_services
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource
    from mhvp.documents.paperless_search import PaperlessSearchError

    async with tenant_tx(request, principal) as session:
        from mhvp.documents.routers import _paperless_client

        client = await _paperless_client(session)
        try:
            file = await client.fetch_file(body.paperless_document_id, "download")
        except PaperlessSearchError as exc:
            raise ProblemError(ErrorCodes.DMS_UNAVAILABLE, detail=str(exc)) from None
        finally:
            await client.aclose()
        filename = file.filename or f"paperless-{body.paperless_document_id}.pdf"
        document = await doc_services.store_document(
            session,
            BlobStore(request.app.state.settings),
            tenant_id=principal.tenant_id,
            data=file.content,
            title=filename,
            filename=filename,
            mime_type=file.content_type,
            source=DocumentSource.IMPORT,
            category_id=None,
            links=[],
            created_by=principal.user_id,
        )
        document_id = document.id
    run = await start_extraction_run(
        request,
        principal,
        AiTask.EXTRACT_INVOICE,
        [document_id],
        "Rechnung aus Paperless erfassen",
        "invoice",
        None,
    )
    return {"document_id": str(document_id), "run_id": str(run.id), "proposal_id": run.proposal_id}
