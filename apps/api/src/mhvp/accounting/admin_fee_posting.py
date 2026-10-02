"""Revenue posting drafts of the Verwalterhonorar (18 M13, M13-07, rule M13-07).

An issued and released fee invoice (or credit note) produces two journal drafts, one per
ledger (6.9.1, E01):

* payer side, in the ledger of ``debtor_legal_entity_id``: expense Verwaltervergütung to the
  liability towards the manager;
* manager side, in the ledger of a legal entity of kind ``manager``: receivable to revenue.

The accounts come only from :class:`AdminFeePostingConfig` of the tenant; there is no default
chart assignment, so without a configuration no draft is created (MHVP-ACC-0007). A credit
note mirrors the sides. Only drafts are written, behind release gate G1; the drafts are posted
through the regular posting path (B03 to B09), which also checks G1. A posted draft is never
changed here; a correction is the credit note with its own drafts (rule 0.1.7).
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as svc
from mhvp.accounting.models import (
    AccountType,
    AdminFeeInvoice,
    AdminFeePostingConfig,
    EntryKind,
    EntrySource,
    JournalEntry,
    Ledger,
    LedgerAccount,
)
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_session_legal_entity_allowed,
    ensure_session_property_allowed,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import (
    ClosedReleaseGateResolver,
    ReleaseGate,
    ensure_release_gate_open,
)

router = APIRouter(prefix="/accounting", tags=["Buchhaltung"])
READ = require_permission("accounting:read")
APPROVE = require_permission("accounting:approve")
ZERO = Decimal("0")
ACCOUNT_NUMBER = r"^[0-9]{6}$"


class AdminFeePostingConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manager_ledger_id: uuid.UUID
    manager_receivable_account_id: uuid.UUID
    manager_revenue_account_id: uuid.UUID
    manager_vat_account_id: uuid.UUID | None = None
    payer_expense_account_number: str = Field(pattern=ACCOUNT_NUMBER)
    payer_payable_account_number: str = Field(pattern=ACCOUNT_NUMBER)
    payer_vat_account_number: str | None = Field(default=None, pattern=ACCOUNT_NUMBER)


class AdminFeePostingConfigOut(AdminFeePostingConfigIn):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: uuid.UUID


class AdminFeePostingDraftsOut(BaseModel):
    invoice_id: uuid.UUID
    payer_entry_id: uuid.UUID
    manager_entry_id: uuid.UUID
    created: bool


def _not_configured(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.ACC_ADMIN_FEE_POSTING_NOT_CONFIGURED, detail=detail)


async def _manager_ledger(session: AsyncSession, ledger_id: uuid.UUID) -> Ledger:
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    ledger = await session.get(Ledger, ledger_id)
    if ledger is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Unbekannter Buchungskreis.")
    entity = await session.get(LegalEntity, ledger.legal_entity_id)
    if entity is None or entity.kind is not LegalEntityKind.MANAGER:
        raise ProblemError(
            ErrorCodes.ACC_WRONG_ENTITY,
            detail="Der Erlös wird nur im Buchungskreis eines Verwalter-Rechtsträgers gebucht.",
        )
    return ledger


@router.get("/admin-fee-posting-config", summary="Honorarbuchung: Kontenzuordnung")
async def get_posting_config(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> AdminFeePostingConfigOut | None:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(AdminFeePostingConfig))
        return AdminFeePostingConfigOut.model_validate(row) if row else None


@router.put("/admin-fee-posting-config", summary="Honorarbuchung: Kontenzuordnung festlegen")
async def put_posting_config(
    body: AdminFeePostingConfigIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> AdminFeePostingConfigOut:
    async with tenant_tx(request, principal) as session:
        ledger = await _manager_ledger(session, body.manager_ledger_id)
        ids = {body.manager_receivable_account_id, body.manager_revenue_account_id}
        if body.manager_vat_account_id is not None:
            ids.add(body.manager_vat_account_id)
        if len(ids) != (3 if body.manager_vat_account_id else 2):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Die Konten müssen verschieden sein.")
        accounts = await svc._accounts(session, ledger, ids)
        # U01: account kind against the chart (receivable asset, revenue income, VAT liability).
        expected = [
            (body.manager_receivable_account_id, AccountType.ASSET, "Forderungskonto"),
            (body.manager_revenue_account_id, AccountType.INCOME, "Erlöskonto"),
            (body.manager_vat_account_id, AccountType.LIABILITY, "Umsatzsteuerkonto"),
        ]
        for account_id, kind, label in expected:
            if account_id is not None and accounts[account_id].type is not kind:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail=(
                        f"{label} {accounts[account_id].number} hat die Kontoart "
                        f"{accounts[account_id].type.value}, erwartet {kind.value}."
                    ),
                )
        payer = {body.payer_expense_account_number, body.payer_payable_account_number}
        if body.payer_vat_account_number is not None:
            payer.add(body.payer_vat_account_number)
        if len(payer) != (3 if body.payer_vat_account_number else 2):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Die Kontonummern des Zahlers müssen verschieden sein.",
            )
        row = await session.scalar(select(AdminFeePostingConfig).with_for_update())
        if row is None:
            row = AdminFeePostingConfig(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="admin_fee_posting_config.saved",
            entity_type="admin_fee_posting_config",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"manager_ledger_id": str(body.manager_ledger_id)},
        )
        return AdminFeePostingConfigOut.model_validate(row)


async def _payer_account(
    session: AsyncSession, ledger: Ledger, number: str, kind: AccountType | None = None
) -> LedgerAccount:
    account = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == ledger.id, LedgerAccount.number == number
        )
    )
    if account is None:
        raise _not_configured(f"Konto {number} fehlt im Buchungskreis {ledger.name} des Zahlers.")
    # Review W79 (U01): the payer accounts are named by number and resolved per payer ledger,
    # the PUT therefore cannot check them; the kind is checked here (expense, liability).
    if kind is not None and account.type is not kind:
        raise _not_configured(
            f"Konto {number} im Buchungskreis {ledger.name} hat die Kontoart "
            f"{account.type.value}, erwartet {kind.value}."
        )
    return account


def _sides(
    debit: list[tuple[uuid.UUID, Decimal]], credit: list[tuple[uuid.UUID, Decimal]], text: str
) -> list[svc.LineIn]:
    """Lines for a positive amount; a negative amount (credit note) swaps the sides."""
    lines: list[svc.LineIn] = []
    for account_id, amount in debit:
        if amount > 0:
            lines.append(svc.LineIn(account_id, amount, ZERO, text=text))
        elif amount < 0:
            lines.append(svc.LineIn(account_id, ZERO, -amount, text=text))
    for account_id, amount in credit:
        if amount > 0:
            lines.append(svc.LineIn(account_id, ZERO, amount, text=text))
        elif amount < 0:
            lines.append(svc.LineIn(account_id, -amount, ZERO, text=text))
    return lines


def build_lines(
    invoice: AdminFeeInvoice,
    *,
    payer_expense: uuid.UUID,
    payer_payable: uuid.UUID,
    payer_vat: uuid.UUID | None,
    manager_receivable: uuid.UUID,
    manager_revenue: uuid.UUID,
    manager_vat: uuid.UUID | None,
    text: str,
) -> tuple[list[svc.LineIn], list[svc.LineIn]]:
    """Payer and manager lines; amounts are taken from the frozen invoice (B06)."""
    gross, net, vat = invoice.gross, invoice.net, invoice.vat
    if net + vat != gross:
        raise ProblemError(
            ErrorCodes.ACC_UNBALANCED,
            detail="Netto und Umsatzsteuer ergeben nicht den Bruttobetrag.",
        )
    split_payer = payer_vat is not None and vat != 0
    split_manager = manager_vat is not None and vat != 0
    payer_debit = [(payer_expense, net if split_payer else gross)]
    if split_payer and payer_vat is not None:
        payer_debit.append((payer_vat, vat))
    manager_credit = [(manager_revenue, net if split_manager else gross)]
    if split_manager and manager_vat is not None:
        manager_credit.append((manager_vat, vat))
    payer = _sides(payer_debit, [(payer_payable, gross)], text)
    manager = _sides([(manager_receivable, gross)], manager_credit, text)
    return payer, manager


@router.post(
    "/admin-fee-invoices/{invoice_id}/posting-drafts",
    status_code=201,
    summary="Honorarrechnung: Buchungsentwürfe beim Zahler und beim Verwalter anlegen",
)
async def create_posting_drafts(
    invoice_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> AdminFeePostingDraftsOut:
    resolver = getattr(request.app.state, "release_gate_resolver", ClosedReleaseGateResolver())
    await ensure_release_gate_open(ReleaseGate.G1, principal.tenant_id, resolver)
    async with tenant_tx(request, principal) as session:
        invoice = await session.get(AdminFeeInvoice, invoice_id, with_for_update=True)
        if invoice is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if invoice.payer_entry_id is not None and invoice.manager_entry_id is not None:
            return AdminFeePostingDraftsOut(
                invoice_id=invoice.id,
                payer_entry_id=invoice.payer_entry_id,
                manager_entry_id=invoice.manager_entry_id,
                created=False,
            )
        if invoice.released_at is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Die Honorarrechnung ist nicht freigegeben, daher kein Buchungsentwurf.",
            )
        config = await session.scalar(select(AdminFeePostingConfig))
        if config is None:
            raise _not_configured("Für die Honorarbuchung ist keine Kontenzuordnung hinterlegt.")
        if invoice.debtor_legal_entity_id is None:
            raise _not_configured("Die Rechnung hat keinen Rechtsträger des Zahlers.")
        payer_ledger = await session.scalar(
            select(Ledger).where(Ledger.legal_entity_id == invoice.debtor_legal_entity_id)
        )
        if payer_ledger is None:
            raise _not_configured("Für den Rechtsträger des Zahlers besteht kein Buchungskreis.")
        # U15: property and legal entity scope of the member on both ledgers (M2-02, A37).
        ensure_session_property_allowed(session, payer_ledger.property_id)
        ensure_session_legal_entity_allowed(session, payer_ledger.legal_entity_id)
        manager_ledger = await _manager_ledger(session, config.manager_ledger_id)
        ensure_session_legal_entity_allowed(session, manager_ledger.legal_entity_id)
        if manager_ledger.id == payer_ledger.id:
            raise ProblemError(
                ErrorCodes.ACC_WRONG_ENTITY,
                detail="Zahler und Verwalter müssen verschiedene Buchungskreise haben.",
            )
        from mhvp.accounting import period_lock

        for ledger in (payer_ledger, manager_ledger):
            svc.ensure_open_period(ledger, invoice.invoice_date)
            # GAE-02 (AE20): object period lock checked up front, not only at post().
            if ledger.property_id is not None:
                await period_lock.ensure_open_for_properties(
                    session, ledger, {ledger.property_id}, invoice.invoice_date
                )
        expense = await _payer_account(
            session, payer_ledger, config.payer_expense_account_number, AccountType.EXPENSE
        )
        payable = await _payer_account(
            session, payer_ledger, config.payer_payable_account_number, AccountType.LIABILITY
        )
        payer_vat = (
            await _payer_account(session, payer_ledger, config.payer_vat_account_number)
            if config.payer_vat_account_number
            else None
        )
        label = "Gutschrift" if invoice.kind == "credit_note" else "Rechnung"
        text = f"Verwaltervergütung {label} {invoice.number}"
        payer_lines, manager_lines = build_lines(
            invoice,
            payer_expense=expense.id,
            payer_payable=payable.id,
            payer_vat=payer_vat.id if payer_vat else None,
            manager_receivable=config.manager_receivable_account_id,
            manager_revenue=config.manager_revenue_account_id,
            manager_vat=config.manager_vat_account_id,
            text=text,
        )
        entries: dict[str, JournalEntry] = {}
        for side, ledger, lines in (
            ("payer", payer_ledger, payer_lines),
            ("manager", manager_ledger, manager_lines),
        ):
            entry = JournalEntry(
                tenant_id=principal.tenant_id,
                created_by=principal.user_id,
                ledger_id=ledger.id,
                source=EntrySource.MANUAL,
                kind=EntryKind.CUSTOM,
                booking_date=invoice.invoice_date,
                text=text,
                reference=invoice.number,
                document_id=invoice.pdf_document_id or invoice.xml_document_id,
                idempotency_key=f"admin_fee_invoice:{invoice.id}:{side}",
            )
            entries[side] = await svc.write_draft(session, ledger, entry, lines, [])
        invoice.payer_entry_id = entries["payer"].id
        invoice.manager_entry_id = entries["manager"].id
        invoice.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="admin_fee_invoice.posting_drafts_created",
            entity_type="admin_fee_invoice",
            entity_id=invoice.id,
            actor_user_id=principal.user_id,
            payload={
                "number": invoice.number,
                "payer_entry_id": str(invoice.payer_entry_id),
                "manager_entry_id": str(invoice.manager_entry_id),
            },
        )
        return AdminFeePostingDraftsOut(
            invoice_id=invoice.id,
            payer_entry_id=invoice.payer_entry_id,
            manager_entry_id=invoice.manager_entry_id,
            created=True,
        )
