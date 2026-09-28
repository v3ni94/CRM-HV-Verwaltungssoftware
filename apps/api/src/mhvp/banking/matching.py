"""Deterministic payment matching and controlled posting (7.4, 6.9.4).

Candidates combine mandate reference, end-to-end id, contract number in the purpose, payer IBAN
and amount; the IBAN alone never proves the debtor (7.4.2). Automatic posting requires an
active rule, tenant opt-in and exactly one unambiguous candidate that settles one open item in
full (partial, collective and overpayments stay manual, 7.4.4).
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    AccountCategory,
    EntryKind,
    EntrySource,
    EntryStatus,
    JournalEntry,
    Ledger,
    LedgerAccount,
    OpenItem,
    OpenItemKind,
)
from mhvp.banking import allocation
from mhvp.banking.models import BankRule, BankTransaction, RuleState, TransactionStatus
from mhvp.core.problems import ErrorCodes, ProblemError

SCORES = {"mandate": 40, "end_to_end": 40, "contract_number": 30, "iban": 15, "amount": 15}


@dataclass
class Candidate:
    open_item_id: uuid.UUID
    account_id: uuid.UUID
    contract_id: uuid.UUID | None
    remaining: Decimal
    score: int
    reasons: list[str] = field(default_factory=list)
    allocation_reason: str = allocation.REASON_RULE


async def ledger_for(session: AsyncSession, tx: BankTransaction) -> tuple[Ledger, LedgerAccount]:
    ledger = await session.scalar(
        select(Ledger).where(Ledger.legal_entity_id == tx.legal_entity_id)
    )
    if ledger is None:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Für den Rechtsträger des Kontos gibt es keinen Buchungskreis.",
        )
    bank = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == ledger.id,
            LedgerAccount.property_bank_account_id == tx.property_bank_account_id,
        )
    )
    if bank is None:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Das Bankkonto ist keinem Sachkonto zugeordnet."
        )
    return ledger, bank


async def _payer_accounts(session: AsyncSession, tx: BankTransaction) -> set[uuid.UUID]:
    """Party ids whose members have the payer IBAN on file (evidence, not proof)."""
    from mhvp.contacts.models import ContactBankAccount, PartyMember

    if tx.counterpart_iban_fingerprint is None:
        return set()
    return set(
        await session.scalars(
            select(PartyMember.party_id)
            .join(ContactBankAccount, ContactBankAccount.contact_id == PartyMember.contact_id)
            .where(ContactBankAccount.iban_fingerprint == tx.counterpart_iban_fingerprint)
        )
    )


async def candidates(session: AsyncSession, tx: BankTransaction) -> list[Candidate]:
    from mhvp.contracts.models import Contract, SepaMandate

    if tx.amount <= 0:
        return []  # outgoing payments are matched against payables in M14/M15
    ledger, _ = await ledger_for(session, tx)
    items = await acc.open_items(session, ledger, tx.booking_date)
    receivables = [
        i for i in items if i["kind"] == OpenItemKind.RECEIVABLE.value and i["remaining"] > 0
    ]
    payer_parties = await _payer_accounts(session, tx)
    purpose = (tx.purpose or "").lower()
    hints = allocation.parse_allocation_hint(tx.purpose or "")
    hit_items: dict[uuid.UUID, set[uuid.UUID]] = {}  # debtor account -> items named by the payer
    out: list[Candidate] = []
    for item in receivables:
        account = await session.get(LedgerAccount, item["account_id"])
        contract = await session.get(Contract, item["contract_id"]) if item["contract_id"] else None
        reasons: list[str] = []
        score = 0
        if contract is not None:
            if contract.number and re.search(rf"\b{re.escape(contract.number.lower())}\b", purpose):
                score += SCORES["contract_number"]
                reasons.append("Vertragsnummer im Verwendungszweck")
            if tx.mandate_reference and contract.sepa_mandate_id:
                mandate = await session.get(SepaMandate, contract.sepa_mandate_id)
                if mandate is not None and mandate.reference == tx.mandate_reference:
                    score += SCORES["mandate"]
                    reasons.append("Mandatsreferenz")
        if account is not None and account.party_id in payer_parties:
            score += SCORES["iban"]
            reasons.append("IBAN des Zahlers beim Vertragspartner hinterlegt")
        if item["remaining"] == tx.amount:
            score += SCORES["amount"]
            reasons.append("Betrag entspricht dem offenen Betrag")
        if not hints.empty:
            entry = await session.get(JournalEntry, item["journal_entry_id"])
            if allocation.matches_item(
                hints,
                reference=entry.reference if entry is not None else None,
                period=item["due_date"] or item["booking_date"],
            ):
                hit_items.setdefault(item["account_id"], set()).add(item["id"])
        if score > 0:
            out.append(
                Candidate(
                    item["id"],
                    item["account_id"],
                    item["contract_id"],
                    item["remaining"],
                    score,
                    reasons,
                )
            )
    # A hint naming exactly one open item of the debtor is settled first (D39); the rest keeps
    # the existing order. Scores and the automatic posting criteria stay unchanged.
    determined = {next(iter(ids)) for ids in hit_items.values() if len(ids) == 1}
    for c in out:
        if c.open_item_id in determined:
            c.allocation_reason = allocation.REASON_DETERMINED
            c.reasons.append(allocation.REASON_DETERMINED)
    out.sort(key=lambda c: (c.open_item_id not in determined, -c.score, str(c.open_item_id)))
    return out


async def allocation_reasons(
    session: AsyncSession, tx: BankTransaction, item_ids: list[uuid.UUID]
) -> dict[str, str]:
    """Reason per settled open item for preview and audit log (M12-03)."""
    if tx.amount <= 0 or not item_ids:
        return {str(i): allocation.REASON_RULE for i in item_ids}
    found = {c.open_item_id: c.allocation_reason for c in await candidates(session, tx)}
    return {str(i): found.get(i, allocation.REASON_RULE) for i in item_ids}


def unambiguous(found: list[Candidate], amount: Decimal) -> Candidate | None:
    """Exactly one candidate with more than IBAN and amount evidence that settles in full."""
    strong = [c for c in found if c.score > SCORES["iban"] + SCORES["amount"]]
    if len(strong) != 1:
        return None
    best = strong[0]
    return best if best.remaining == amount else None


def rule_matches(rule: BankRule, tx: BankTransaction) -> bool:
    m = rule.match
    if rule.legal_entity_id != tx.legal_entity_id:
        return False
    if (
        m.get("counterpart_iban_fingerprint")
        and m["counterpart_iban_fingerprint"] != tx.counterpart_iban_fingerprint
    ):
        return False
    if (
        m.get("name_contains")
        and m["name_contains"].lower() not in (tx.counterpart_name or "").lower()
    ):
        return False
    if m.get("purpose_regex"):
        try:
            if not re.search(m["purpose_regex"], tx.purpose or "", re.IGNORECASE):
                return False
        except re.error:
            return False
    if m.get("amount_min") is not None and tx.amount < Decimal(str(m["amount_min"])):
        return False
    return not (m.get("amount_max") is not None and tx.amount > Decimal(str(m["amount_max"])))


async def lock_for_booking(session: AsyncSession, tx_id: uuid.UUID) -> BankTransaction:
    """Row lock for a booking. A recognised transfer pair is locked as a whole in a stable
    order (by id), so parallel requests for the two halves serialise instead of both posting
    or deadlocking (D04, B08). Unpaired transactions: one ``SELECT ... FOR UPDATE`` as before."""
    pair_id = await session.scalar(
        select(BankTransaction.transfer_pair_id).where(BankTransaction.id == tx_id)
    )
    ids = [tx_id] if pair_id is None else [tx_id, pair_id]
    rows = (
        await session.scalars(
            select(BankTransaction)
            .where(BankTransaction.id.in_(ids))
            .order_by(BankTransaction.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    tx = next((r for r in rows if r.id == tx_id), None)
    if tx is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if tx.transfer_pair_id is not None and tx.transfer_pair_id not in ids:  # paired meanwhile
        await session.get(BankTransaction, tx.transfer_pair_id, with_for_update=True)
    return tx


async def _effective_entry(
    session: AsyncSession, entry_id: uuid.UUID | None
) -> JournalEntry | None:
    """The posting still in force: posted and not reversed (B03)."""
    if entry_id is None:
        return None
    entry = await session.get(JournalEntry, entry_id)
    if entry is None or entry.status is not EntryStatus.POSTED or entry.reversed_by_id:
        return None
    return entry


async def _transfer_partner(session: AsyncSession, tx: BankTransaction) -> BankTransaction:
    """The other half of a recognised transfer pair, locked; refuses a second effect (D04).

    One posting of either half moves both bank accounts, so the pair is settled as soon as one
    half carries a posting in force. After that posting is reversed, the pair is bookable
    again, once, from either half."""
    assert tx.transfer_pair_id is not None  # noqa: S101 - caller checks
    partner = await session.get(BankTransaction, tx.transfer_pair_id, with_for_update=True)
    if (
        partner is None
        or partner.transfer_pair_id != tx.id
        or partner.tenant_id != tx.tenant_id
        or partner.legal_entity_id != tx.legal_entity_id
    ):
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Das Transferpaar ist unvollständig oder betrifft einen anderen Rechtsträger.",
        )
    own = await _effective_entry(session, tx.journal_entry_id)
    if own is not None and own.bank_transaction_id == tx.id:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Umsatz ist bereits gebucht oder ignoriert."
        )
    if own is not None or await _effective_entry(session, partner.journal_entry_id) is not None:
        raise ProblemError(
            ErrorCodes.BANK_TRANSFER_PAIR_SETTLED,
            detail=(
                "Die Umbuchung ist über die Partnerseite bereits gebucht; der Transfer hat "
                "keine zweite Wirkung. Zum erneuten Buchen zuerst diese Buchung stornieren."
            ),
        )
    if partner.status is TransactionStatus.NEEDS_REVIEW:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Die Partnerseite muss zuerst als möglicher Doppelumsatz geklärt werden.",
        )
    return partner


async def book_payment(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    settlements: list[tuple[uuid.UUID, Decimal]],
    counter_account_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    source: EntrySource,
    text: str | None = None,
    discount: Decimal = Decimal("0.00"),
) -> JournalEntry:
    """Post a bank transaction: bank against debtor(s) with explicit settlement, or against one
    counter account. Complete or not at all (B02); a booked transaction cannot be booked twice.

    A recognised transfer pair (``transfer_pair_id``) is posted once, bank against the partner
    bank account, and that posting settles both halves (D04, B08). Callers lock with
    :func:`lock_for_booking`."""
    partner = await _transfer_partner(session, tx) if tx.transfer_pair_id is not None else None
    # A pair half whose posting was reversed is bookable again; everything else unchanged.
    reopened = partner is not None and tx.journal_entry_id is not None
    if not reopened and (
        tx.status in (TransactionStatus.BOOKED, TransactionStatus.IGNORED) or tx.journal_entry_id
    ):
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Umsatz ist bereits gebucht oder ignoriert."
        )
    if tx.status is TransactionStatus.NEEDS_REVIEW:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Der Umsatz muss zuerst als möglicher Doppelumsatz geklärt werden.",
        )
    if tx.transfer_pair_id is not None and counter_account_id is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Umbuchungen werden gegen das Bankkonto des Partners gebucht.",
        )
    if partner is not None:
        _, partner_bank = await ledger_for(session, partner)
        if settlements or discount or counter_account_id != partner_bank.id:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    "Umbuchungen werden ohne Postenausgleich und ohne Skonto gegen das "
                    "Bankkonto des Partners gebucht."
                ),
            )
    ledger, bank = await ledger_for(session, tx)
    amount = abs(tx.amount)
    lines: list[acc.LineIn] = []
    plan: list[dict[str, Any]] = []
    total = Decimal("0.00")
    per_account: dict[uuid.UUID, Decimal] = {}
    for item_id, value in settlements:
        item = await session.get(OpenItem, item_id)
        if item is None:
            raise ProblemError(
                ErrorCodes.RESOURCE_NOT_FOUND, detail="Offener Posten nicht gefunden."
            )
        if item.ledger_id != ledger.id:
            raise ProblemError(
                ErrorCodes.ACC_WRONG_ENTITY, detail="Offener Posten eines anderen Rechtsträgers."
            )
        per_account[item.account_id] = per_account.get(item.account_id, Decimal("0.00")) + value
        plan.append({"open_item_id": item_id, "amount": value})
        total += value
    if total > amount + discount:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Zuordnung höher als der Zahlbetrag.")
    if discount > 0 and counter_account_id is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Skonto braucht ein Gegenkonto.")
    rest = amount + discount - total
    if rest > 0 and counter_account_id is None:
        if len(per_account) != 1:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Restbetrag braucht ein Gegenkonto.")
        # Overpayment stays as credit on the same debtor account, never income (D07).
        only = next(iter(per_account))
        per_account[only] += rest
        rest = Decimal("0.00")
    incoming = tx.amount > 0
    for account_id, value in per_account.items():
        lines.append(
            acc.LineIn(
                account_id, Decimal("0") if incoming else value, value if incoming else Decimal("0")
            )
        )
    if discount > 0 and counter_account_id is not None:
        # Discount: personal account moved by more than the bank amount (7.3 Skonto).
        lines.append(
            acc.LineIn(
                counter_account_id,
                discount if incoming else Decimal("0"),
                Decimal("0") if incoming else discount,
            )
        )
    if rest > 0:
        assert counter_account_id is not None  # noqa: S101 - checked above
        lines.append(
            acc.LineIn(
                counter_account_id,
                Decimal("0") if incoming else rest,
                rest if incoming else Decimal("0"),
            )
        )
    lines.insert(
        0,
        acc.LineIn(
            bank.id, amount if incoming else Decimal("0"), Decimal("0") if incoming else amount
        ),
    )
    if per_account:
        accounts = (
            await session.scalars(select(LedgerAccount).where(LedgerAccount.id.in_(per_account)))
        ).all()
        if any(
            a.category is not AccountCategory.DEBTOR and a.category is not AccountCategory.CREDITOR
            for a in accounts
        ):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ausgleich nur auf Personenkonten.")
    kind = (
        EntryKind.BANK_TRANSFER
        if tx.transfer_pair_id
        else (EntryKind.DEBTOR_PAYMENT if incoming else EntryKind.CREDITOR_PAYMENT)
    )
    entry = JournalEntry(
        tenant_id=tx.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        booking_date=tx.booking_date,
        value_date=tx.value_date,
        text=(text or tx.purpose or tx.counterpart_name or "Bankumsatz")[:500],
        kind=kind,
        reference=tx.bank_reference,
        bank_transaction_id=tx.id,
        source=source,
    )
    await acc.write_draft(session, ledger, entry, lines, plan)
    await acc.post(session, ledger, entry, user_id)
    tx.status, tx.journal_entry_id = TransactionStatus.BOOKED, entry.id
    if partner is not None and partner.status is not TransactionStatus.IGNORED:
        # The same posting moved the partner bank account: the other half is settled by the
        # pair and carries this entry; the entry keeps ``bank_transaction_id`` of this half.
        partner.status, partner.journal_entry_id = TransactionStatus.BOOKED, entry.id
    await session.flush()
    return entry


async def auto_post(
    session: AsyncSession, tx: BankTransaction, enabled: bool
) -> JournalEntry | None:
    """Automatic posting only by an active rule within its limit (6.9.4); otherwise None."""
    if (
        not enabled
        or tx.status is not TransactionStatus.NEW
        or tx.transfer_pair_id
        or tx.amount <= 0
    ):
        return None
    rules = (
        await session.scalars(
            select(BankRule)
            .where(
                BankRule.approval_state == RuleState.ACTIVE,
                BankRule.legal_entity_id == tx.legal_entity_id,
            )
            .order_by(BankRule.priority, BankRule.created_at)
        )
    ).all()
    rule = next((r for r in rules if rule_matches(r, tx)), None)
    if rule is None or (rule.max_amount is not None and tx.amount > rule.max_amount):
        return None
    best = unambiguous(await candidates(session, tx), tx.amount)
    if best is None or (
        rule.action.get("account_id") and str(best.account_id) != rule.action["account_id"]
    ):
        return None
    entry = await book_payment(
        session,
        tx,
        settlements=[(best.open_item_id, best.remaining)],
        counter_account_id=None,
        user_id=None,
        source=EntrySource.BANK_IMPORT,
    )
    tx.matched_rule_id = rule.id
    rule.hit_count += 1
    rule.last_hit_at = datetime.now(UTC)
    await session.flush()
    return entry
