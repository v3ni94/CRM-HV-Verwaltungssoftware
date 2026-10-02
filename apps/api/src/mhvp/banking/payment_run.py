"""Payment run preview, bulk orders, payouts without invoice and bank limits (7.5 Zahllauf,
M15-03, M15-04, M15-07, S15-02).

The preview lists released and posted invoices with an open payable and no active order,
grouped by legal entity with the ordering accounts of that entity, plus due direct debit
runs. It creates nothing. Bulk creation calls ``payments.order_from_invoice`` per invoice
in a savepoint, so one failing invoice never blocks the others. A payout without invoice
(owner payout, statement credit, deposit refund) is an order on a payable open item to a
released bank account of the payee. Every order still needs two approvals and the file needs
release gate G2; limits agreed with the bank are checked before a file is generated.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.banking import payments
from mhvp.banking.models import OrderStatus, PaymentBankConfig, PaymentOrder
from mhvp.core import crypto
from mhvp.core.problems import ErrorCodes, ProblemError

# Order states that still block a new order on the same open item.
ACTIVE_ORDER_STATUSES = (
    OrderStatus.DRAFT,
    OrderStatus.APPROVED,
    OrderStatus.EXPORTED,
    OrderStatus.SUBMITTED,
    OrderStatus.ACCEPTED_BY_BANK,
)
# Order states that count against the daily limit of the ordering account.
LIMIT_STATUSES = (
    OrderStatus.EXPORTED,
    OrderStatus.SUBMITTED,
    OrderStatus.ACCEPTED_BY_BANK,
    OrderStatus.EXECUTED,
    OrderStatus.PARTIALLY_EXECUTED,
)
PAYOUT_REASONS = ("owner_payout", "statement_credit", "deposit_refund", "other_refund")
PAYOUT_LABELS = {
    "owner_payout": "Auszahlung an Eigentümer",
    "statement_credit": "Guthaben aus Abrechnung",
    "deposit_refund": "Kautionsrückzahlung",
    "other_refund": "Erstattung",
}
VOP_NOTE = (
    "Je nach Bank prüft diese vor der Ausführung Empfängername und IBAN "
    "(Empfängerüberprüfung, Verification of Payee). Eine Abweichungsmeldung der Bank wird vor "
    "der Einreichung mit dem Empfänger geklärt; das Verfahren der Bank ist zu verifizieren."
)


async def bank_config(session: AsyncSession, account_id: uuid.UUID) -> PaymentBankConfig | None:
    return await session.scalar(  # type: ignore[no-any-return]
        select(PaymentBankConfig).where(PaymentBankConfig.property_bank_account_id == account_id)
    )


def limits_out(config: PaymentBankConfig | None) -> dict[str, Any]:
    return {
        "single_order_limit": (
            str(config.single_order_limit) if config and config.single_order_limit else None
        ),
        "daily_limit": str(config.daily_limit) if config and config.daily_limit else None,
        "source_status": "zu verifizieren",
        "verification_of_payee": VOP_NOTE,
    }


def limit_findings(
    orders: list[PaymentOrder],
    config: PaymentBankConfig | None,
    already: dict[date, Decimal] | None = None,
) -> list[str]:
    """Findings of orders of one ordering account against the agreed limits (M15-04): an
    order above the single order limit, and the sum per execution date (including orders
    already handed out, ``already``) above the daily limit."""
    if config is None:
        return []
    findings = []
    if config.single_order_limit is not None:
        for o in orders:
            if o.amount > config.single_order_limit:
                findings.append(
                    f"{o.counterpart_name}: {o.amount} EUR über dem Einzelauftragslimit "
                    f"{config.single_order_limit} EUR"
                )
    if config.daily_limit is not None:
        per_day: dict[date, Decimal] = dict(already or {})
        for o in orders:
            per_day[o.execution_date] = per_day.get(o.execution_date, Decimal("0.00")) + o.amount
        for day, total in sorted(per_day.items()):
            if total > config.daily_limit:
                findings.append(
                    f"Ausführung {day:%d.%m.%Y}: Summe {total} EUR über dem Tageslimit "
                    f"{config.daily_limit} EUR"
                )
    return findings


async def _already_out(
    session: AsyncSession, account_id: uuid.UUID, days: set[date], exclude: set[uuid.UUID]
) -> dict[date, Decimal]:
    query = (
        select(PaymentOrder.execution_date, func.coalesce(func.sum(PaymentOrder.amount), 0))
        .where(
            PaymentOrder.property_bank_account_id == account_id,
            PaymentOrder.execution_date.in_(days),
            PaymentOrder.status.in_(LIMIT_STATUSES),
        )
        .group_by(PaymentOrder.execution_date)
    )
    if exclude:
        query = query.where(PaymentOrder.id.not_in(exclude))
    return {day: Decimal(total) for day, total in (await session.execute(query)).all()}


async def ensure_within_limits(session: AsyncSession, orders: list[PaymentOrder]) -> None:
    """Refuse a payment file that exceeds a limit agreed with the bank (M15-04)."""
    by_account: dict[uuid.UUID, list[PaymentOrder]] = {}
    for o in orders:
        by_account.setdefault(o.property_bank_account_id, []).append(o)
    for account_id, group in by_account.items():
        config = await bank_config(session, account_id)
        if config is None or (config.single_order_limit is None and config.daily_limit is None):
            continue
        already = await _already_out(
            session, account_id, {o.execution_date for o in group}, {o.id for o in group}
        )
        if findings := limit_findings(group, config, already):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Banklimit überschritten: " + "; ".join(findings),
            )


async def _busy_items(session: AsyncSession) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(PaymentOrder.open_item_id).where(
            PaymentOrder.open_item_id.is_not(None), PaymentOrder.status.in_(ACTIVE_ORDER_STATUSES)
        )
    )
    return {r for r in rows.all() if r is not None}


async def preview(
    session: AsyncSession, *, as_of: date, horizon_days: int = 7, ledger_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Payable invoices due until ``as_of + horizon_days`` grouped by legal entity with the
    usable ordering accounts, and direct debit runs due in the same window (M15-03)."""
    from mhvp.accounting import leading
    from mhvp.accounting.direct_debit import ACTIVE_RUN_STATUSES
    from mhvp.accounting.direct_debit_models import DirectDebitOrder, DirectDebitRun
    from mhvp.accounting.models import Invoice, Ledger, OpenItem, PostingStatus
    from mhvp.contacts.models import Contact
    from mhvp.properties.models import LegalEntity, PropertyBankAccount

    until = as_of + timedelta(days=horizon_days)
    query = (
        select(Invoice, OpenItem, Ledger)
        .join(OpenItem, OpenItem.journal_entry_id == Invoice.journal_entry_id)
        .join(Ledger, Ledger.id == Invoice.ledger_id)
        .where(
            Invoice.posting_status == PostingStatus.POSTED,
            OpenItem.kind == "payable",
            OpenItem.written_off.is_(False),
        )
        .order_by(Invoice.due_date.nulls_last(), Invoice.number)
    )
    if ledger_id is not None:
        query = query.where(Invoice.ledger_id == ledger_id)
    busy = await _busy_items(session)
    groups: dict[uuid.UUID, dict[str, Any]] = {}
    for invoice, item, ledger in (await session.execute(query)).all():
        due = invoice.due_date or item.due_date or item.booking_date
        if due > until or item.id in busy:
            continue
        rest = await acc.remaining(session, item.id)
        if rest <= 0:
            continue
        block = None
        if not invoice.payee_iban:
            block = "Rechnung ohne Empfänger-IBAN"
        elif any("IBAN weicht" in f for f in invoice.findings):
            block = "Abweichende IBAN ist nicht bestätigt (PÜ04)"
        elif not await leading.is_leading(
            session, ledger, leading.LeadingKind.PAYMENT_ORDER, as_of
        ):
            block = "Buchungskreis ist nicht im führenden System (13.1)"
        group = groups.get(ledger.legal_entity_id)
        if group is None:
            entity = await session.get(LegalEntity, ledger.legal_entity_id)
            accounts = (
                await session.scalars(
                    select(PropertyBankAccount).where(
                        PropertyBankAccount.legal_entity_id == ledger.legal_entity_id,
                        PropertyBankAccount.segregated.is_(False),
                        PropertyBankAccount.valid_from <= as_of,
                        (PropertyBankAccount.valid_to.is_(None))
                        | (PropertyBankAccount.valid_to >= as_of),
                    )
                )
            ).all()
            group = groups[ledger.legal_entity_id] = {
                "legal_entity_id": str(ledger.legal_entity_id),
                "legal_entity_name": entity.name if entity else "",
                "bank_accounts": [
                    {
                        "id": str(a.id),
                        "iban_suffix": a.iban_suffix,
                        "holder": a.holder,
                        "limits": limits_out(await bank_config(session, a.id)),
                    }
                    for a in accounts
                ],
                "invoices": [],
                "total": Decimal("0.00"),
            }
        contact = await session.get(Contact, invoice.provider_contact_id)
        group["invoices"].append(
            {
                "invoice_id": str(invoice.id),
                "ledger_id": str(ledger.id),
                "number": invoice.number,
                "payee": contact.display_name if contact else "",
                "iban_suffix": invoice.payee_iban[-4:] if invoice.payee_iban else None,
                "due_date": due.isoformat(),
                "overdue": due < as_of,
                "gross": str(invoice.gross),
                "remaining": str(rest),
                "eligible": block is None,
                "block_reason": block,
            }
        )
        if block is None:
            group["total"] += rest
    runs = (
        await session.scalars(
            select(DirectDebitRun)
            .where(
                DirectDebitRun.status.in_(ACTIVE_RUN_STATUSES[:3]),
                DirectDebitRun.collection_date <= until,
            )
            .order_by(DirectDebitRun.collection_date)
        )
    ).all()
    debits = []
    for run in runs:
        missing = await session.scalar(
            select(func.count(DirectDebitOrder.id)).where(
                DirectDebitOrder.run_id == run.id,
                DirectDebitOrder.pre_notification_document_id.is_(None),
            )
        )
        debits.append(
            {
                "run_id": str(run.id),
                "status": run.status.value,
                "collection_date": run.collection_date.isoformat(),
                "control_sum": str(run.control_sum),
                "transaction_count": run.transaction_count,
                "pre_notifications_missing": int(missing or 0),
            }
        )
    entities = list(groups.values())
    for g in entities:
        g["total"] = str(g["total"])
    return {
        "as_of": as_of.isoformat(),
        "until": until.isoformat(),
        "legal_entities": entities,
        "invoice_count": sum(len(g["invoices"]) for g in entities),
        "direct_debit_runs": debits,
        "verification_of_payee": VOP_NOTE,
        "note": "Vorschau: es werden keine Aufträge und keine Dateien erzeugt.",
    }


async def create_orders(
    session: AsyncSession,
    *,
    items: list[tuple[uuid.UUID, uuid.UUID]],
    execution_date: date,
    user_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Draft orders for many invoices (M15-03); each in a savepoint, failures are reported
    per invoice. Limits are reported as warnings here and enforced on the payment file."""
    from mhvp.accounting.models import Invoice

    created: list[PaymentOrder] = []
    failed: list[dict[str, Any]] = []
    for invoice_id, account_id in items:
        invoice = await session.get(Invoice, invoice_id)
        if invoice is None:
            failed.append({"invoice_id": str(invoice_id), "detail": "Rechnung nicht gefunden."})
            continue
        try:
            async with session.begin_nested():
                order = await payments.order_from_invoice(
                    session,
                    invoice=invoice,
                    bank_account_id=account_id,
                    execution_date=execution_date,
                    user_id=user_id,
                )
        except ProblemError as exc:
            failed.append(
                {"invoice_id": str(invoice_id), "detail": exc.detail or exc.developer_message}
            )
            continue
        created.append(order)
    warnings: list[str] = []
    by_account: dict[uuid.UUID, list[PaymentOrder]] = {}
    for o in created:
        by_account.setdefault(o.property_bank_account_id, []).append(o)
    for account_id, group in by_account.items():
        already = await _already_out(session, account_id, {o.execution_date for o in group}, set())
        warnings += limit_findings(group, await bank_config(session, account_id), already)
    return {"created": created, "failed": failed, "limit_warnings": warnings}


async def order_for_payout(
    session: AsyncSession,
    *,
    open_item_id: uuid.UUID,
    contact_bank_account_id: uuid.UUID,
    bank_account_id: uuid.UUID,
    execution_date: date,
    reason: str,
    purpose: str | None,
    user_id: uuid.UUID | None,
) -> PaymentOrder:
    """Payout without invoice (M15-07) on a payable open item of the ledger: owner payout,
    credit from a statement, deposit refund. The payee account must be released (M5-01) and,
    when the item belongs to a contract, belong to a member of the contract party. A deposit
    refund is paid only from the segregated deposit account, everything else never from it."""
    from mhvp.accounting.models import Invoice, Ledger, OpenItem, OpenItemKind
    from mhvp.contacts.models import Contact, ContactBankAccount, PartyMember
    from mhvp.contacts.services import approval_block_reason
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import PropertyBankAccount

    if reason not in PAYOUT_REASONS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannter Auszahlungsgrund.")
    item = await session.get(OpenItem, open_item_id, with_for_update=True)
    if item is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Offener Posten nicht gefunden.")
    if item.kind is not OpenItemKind.PAYABLE or item.written_off:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Auszahlungen nur auf offene Verbindlichkeiten."
        )
    if await session.scalar(
        select(Invoice.id).where(Invoice.journal_entry_id == item.journal_entry_id)
    ):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Rechnungen werden über den Rechnungszahllauf bezahlt."
        )
    if item.id in await _busy_items(session):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für den Posten besteht bereits ein Zahlungsauftrag."
        )
    rest = await acc.remaining(session, item.id)
    if rest <= 0:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Posten ist ausgeglichen.")
    ledger = await session.get(Ledger, item.ledger_id)
    bank = await session.get(PropertyBankAccount, bank_account_id)
    if bank is None or ledger is None or bank.legal_entity_id != ledger.legal_entity_id:
        raise ProblemError(
            ErrorCodes.ACC_WRONG_ENTITY,
            detail="Auszahlung nur vom Konto des Rechtsträgers des Postens.",
        )
    if bank.segregated != (reason == "deposit_refund"):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Kautionsrückzahlungen nur vom getrennten Kautionskonto, andere Auszahlungen "
                "nie vom Kautionskonto."
            ),
        )
    payee = await session.get(ContactBankAccount, contact_bank_account_id)
    if payee is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Bankverbindung nicht gefunden.")
    if (blocked := approval_block_reason(payee)) is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail=blocked)
    if payee.valid_to is not None and payee.valid_to < execution_date:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Bankverbindung nicht mehr gültig.")
    if item.contract_id is not None:
        contract = await session.get(Contract, item.contract_id)
        if contract is None:  # pragma: no cover
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Vertrag nicht gefunden.")
        member = await session.scalar(
            select(PartyMember.id).where(
                PartyMember.party_id == contract.party_id,
                PartyMember.contact_id == payee.contact_id,
            )
        )
        if member is None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Der Empfänger ist nicht Vertragspartei des Postens.",
            )
    contact = await session.get(Contact, payee.contact_id)
    name = payee.holder or (contact.display_name if contact else "Empfänger")
    order = PaymentOrder(
        tenant_id=item.tenant_id,
        created_by=user_id,
        ledger_id=item.ledger_id,
        property_bank_account_id=bank.id,
        kind="payout",
        invoice_id=None,
        open_item_id=item.id,
        amount=rest,
        discount=Decimal("0.00"),
        counterpart_name=name[:140],
        counterpart_iban=payee.iban,
        counterpart_iban_fingerprint=crypto.fingerprint(payee.iban),
        purpose=(purpose or PAYOUT_LABELS[reason])[:140],
        end_to_end_id=f"E2E{uuid.uuid4().hex[:28]}".upper(),
        execution_date=execution_date,
        contact_bank_account_id=payee.id,
        payout_reason=reason,
    )
    session.add(order)
    await session.flush()
    return order
