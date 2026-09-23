"""Ledger endpoints (/api/v1/accounting, M10).

Postings are allowed in ledgers that are not leading (parallel operation with Immoware24).
Declaring the platform as leading system requires release gate G1 (18.0, 6.9.10).
"""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as svc
from mhvp.accounting.models import (
    ChartTemplate,
    EntryKind,
    EntrySource,
    EntryStatus,
    JournalEntry,
    JournalLine,
    LeadingSystem,
    Ledger,
    LedgerAccount,
)
from mhvp.accounting.schemas import (
    AccountIn,
    AccountOut,
    AccountPatch,
    EntryIn,
    EntryOut,
    LeadingIn,
    LedgerIn,
    LedgerOut,
    LineOut,
    LockIn,
    ReverseIn,
    TemplateOut,
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


def _lines(body: EntryIn) -> list[svc.LineIn]:
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
) -> list[TemplateOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(ChartTemplate).order_by(ChartTemplate.code, ChartTemplate.version)
        )
        return [TemplateOut.model_validate(t) for t in rows.all()]


@router.post("/templates/default", status_code=201, summary="Entwurf nach Anhang A.1 anlegen")
async def create_default_template(
    request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> TemplateOut:
    async with tenant_tx(request, principal) as session:
        return TemplateOut.model_validate(await svc.default_template(session, principal.tenant_id))


@router.post(
    "/templates/{template_id}/release", summary="Vorlage freigeben (Betreiberentscheidung V8)"
)
async def release_template(
    template_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> TemplateOut:
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
        return TemplateOut.model_validate(template)


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
    body: EntryIn,
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
    body: EntryIn,
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
