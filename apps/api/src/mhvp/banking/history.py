"""Memory of the learning bookkeeper (ADR 0014, rule M12-04, plan M12 S3 and S7).

Two read only views over the decision log and the posted invoices, both behind the tenant
switch ``learning_bookkeeper_enabled`` (default off) and both bound to one legal entity (B01,
E01):

* ``counterparty_history``: the confirmed decisions of persons for the same counterparty
  (IBAN fingerprint, or SEPA creditor id as the stable key when the creditor changed its
  IBAN) in the same legal entity and direction, as plain dicts for
  ``posting_proposal._history_proposal`` (stage 1d). Only ``accepted_unchanged`` and
  ``modified`` decisions with a person as author on postings that were not reversed count as
  evidence; a reversed posting is returned with ``reversed=True`` as a counter example.
  Automatic postings (``auto_posted``), Immoware24 journal, imports, drafts and model answers
  are never read here (7.4 no. 6).
* ``creditor_account_history``: cost account proposals per invoice line for the receipt
  intake (9.2, plan S7) from the confirmed invoices of the same provider in the same ledger
  and from the counter accounts persons chose for the provider's outgoing bank transactions.
  The proposal carries only the account identity and counts; allocation category, operating
  cost type, § 35a and VAT are never derived from it (0.1.3, M17-01, M14-02).

Nothing here writes, posts or leaves the platform.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import (
    AccountCategory,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    OpenItem,
    PostingStatus,
)
from mhvp.banking.models import BankTransaction, PostingDecision, PostingDecisionStatus

# Most recent decisions per counterparty read for one proposal (assumption A-077).
HISTORY_LIMIT = 20
# Accounts proposed per invoice line in the receipt intake (assumption A-077).
ACCOUNT_PROPOSALS_PER_LINE = 3
# Invoices of the provider read for the account history (newest first).
INVOICE_HISTORY_LIMIT = 50

CONFIRMED = (
    PostingDecisionStatus.ACCEPTED_UNCHANGED.value,
    PostingDecisionStatus.MODIFIED.value,
)
SOURCE_HISTORY = "history"  # ``source`` of an account proposal ("Verlauf" in the CRM)


def _entry_label(entry: JournalEntry) -> str | None:
    if entry.fiscal_year is None or entry.number is None:
        return None
    return f"{entry.fiscal_year}-{entry.number}"


async def _entry_accounts(
    session: AsyncSession, entry_id: uuid.UUID, bank_account_id: uuid.UUID
) -> list[str]:
    """Account numbers of a posting other than the bank account, sorted (the pattern)."""
    rows = await session.scalars(
        select(LedgerAccount.number)
        .join(JournalLine, JournalLine.account_id == LedgerAccount.id)
        .where(JournalLine.journal_entry_id == entry_id, LedgerAccount.id != bank_account_id)
        .distinct()
    )
    return sorted(set(rows.all()))


async def _contract_end(session: AsyncSession, final: dict[str, Any] | None) -> date | None:
    """End date of the contract behind the first settled open item of a decision (W07, D15)."""
    from mhvp.contracts.models import Contract

    for row in (final or {}).get("settlements") or []:
        try:
            item_id = uuid.UUID(str(row.get("open_item_id")))
        except ValueError:
            continue
        item = await session.get(OpenItem, item_id)
        if item is None or item.contract_id is None:
            continue
        contract = await session.get(Contract, item.contract_id)
        return contract.end_date if contract is not None else None
    return None


async def counterparty_history(
    session: AsyncSession, tx: BankTransaction, *, bank_account_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Confirmed decisions of persons for the same counterparty, legal entity and direction,
    newest first, at most ``HISTORY_LIMIT`` (see module docstring). ``bank_account_id`` is
    the ledger account of the transaction's bank account (excluded from the pattern)."""
    keys = []
    if tx.counterpart_iban_fingerprint:
        keys.append(BankTransaction.counterpart_iban_fingerprint == tx.counterpart_iban_fingerprint)
    if tx.creditor_id:
        keys.append(BankTransaction.creditor_id == tx.creditor_id)
    if not keys:
        return []
    direction = BankTransaction.amount > 0 if tx.amount > 0 else BankTransaction.amount < 0
    rows = (
        await session.execute(
            select(PostingDecision, BankTransaction)
            .join(BankTransaction, BankTransaction.id == PostingDecision.bank_transaction_id)
            .where(
                PostingDecision.legal_entity_id == tx.legal_entity_id,
                PostingDecision.status.in_(CONFIRMED),
                PostingDecision.decided_by.is_not(None),
                PostingDecision.journal_entry_id.is_not(None),
                PostingDecision.bank_transaction_id != tx.id,
                or_(*keys),
                direction,
            )
            .order_by(PostingDecision.decided_at.desc(), PostingDecision.id.desc())
            .limit(HISTORY_LIMIT)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for decision, other in rows:
        entry = await session.get(JournalEntry, decision.journal_entry_id)
        if entry is None:
            continue
        accounts = await _entry_accounts(session, entry.id, bank_account_id)
        if not accounts:
            continue
        matched_by = (
            "iban"
            if tx.counterpart_iban_fingerprint
            and other.counterpart_iban_fingerprint == tx.counterpart_iban_fingerprint
            else "creditor_id"
        )
        contract_end = await _contract_end(session, decision.final)
        out.append(
            {
                "decision_id": str(decision.id),
                "journal_entry_id": str(entry.id),
                "label": _entry_label(entry),
                "booking_date": entry.booking_date.isoformat(),
                "decided_at": decision.decided_at.isoformat() if decision.decided_at else None,
                "amount": str(other.amount),
                "accounts": accounts,
                "text": (decision.final or {}).get("text") or entry.text,
                "reversed": entry.reversed_by_id is not None,
                "bulk": bool(decision.bulk),
                "key": matched_by,
                "contract_end": contract_end.isoformat() if contract_end else None,
            }
        )
    return out


# Receipt intake (S7) ----------------------------------------------------------------------


@dataclass
class _AccountStat:
    account: LedgerAccount
    count_invoices: int = 0
    count_posted: int = 0
    count_bank: int = 0
    last_used_on: date | None = None
    texts: set[str] = field(default_factory=set)

    @property
    def total(self) -> int:
        return self.count_invoices + self.count_bank

    def touch(self, day: date | None) -> None:
        if day is not None and (self.last_used_on is None or day > self.last_used_on):
            self.last_used_on = day

    def out(self, *, index: int | None, reason: str) -> dict[str, Any]:
        return {
            "account_id": str(self.account.id),
            "account_number": self.account.number,
            "name": self.account.name,
            "count": self.total,
            "count_invoices": self.count_invoices,
            "count_posted": self.count_posted,
            "count_bank": self.count_bank,
            "last_used_on": self.last_used_on.isoformat() if self.last_used_on else None,
            "source": SOURCE_HISTORY,
            "line_index": index,
            "reason": reason,
        }


def _norm(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


async def _provider_fingerprints(session: AsyncSession, contact_id: uuid.UUID) -> list[str]:
    from mhvp.contacts.models import ContactBankAccount

    rows = await session.scalars(
        select(ContactBankAccount.iban_fingerprint).where(
            ContactBankAccount.contact_id == contact_id,
            ContactBankAccount.iban_fingerprint.is_not(None),
        )
    )
    return sorted({fp for fp in rows.all() if fp})


async def creditor_account_history(
    session: AsyncSession,
    *,
    ledger_id: uuid.UUID,
    provider_contact_id: uuid.UUID,
    line_texts: list[str | None] | None = None,
) -> dict[str, Any]:
    """Cost account proposals for the lines of a new invoice of ``provider_contact_id`` in
    ``ledger_id`` (one legal entity). Sources, both decisions of persons: the lines of the
    provider's confirmed invoices in the ledger (posted ones counted separately; duplicates and
    superseded versions skipped) and the counter accounts chosen for the provider's outgoing
    bank transactions in the decision log. ``line_texts`` (one per new line, may be ``None``)
    let a line with the same wording as an earlier line rank its account first; otherwise the
    line position, then the overall frequency decides. Returns ``{"lines": [{"index",
    "proposals": [...]}], "creditor_account": {...} | None, "sources": {...}}``."""
    from mhvp.accounting.models import Ledger

    ledger = await session.get(Ledger, ledger_id)
    if ledger is None:
        return {"lines": [], "creditor_account": None, "sources": {}}
    stats: dict[uuid.UUID, _AccountStat] = {}
    by_position: dict[int, dict[uuid.UUID, int]] = defaultdict(lambda: defaultdict(int))
    by_text: dict[str, dict[uuid.UUID, int]] = defaultdict(lambda: defaultdict(int))
    accounts: dict[uuid.UUID, LedgerAccount] = {}

    async def stat(account_id: uuid.UUID) -> _AccountStat | None:
        if account_id not in accounts:
            account = await session.get(LedgerAccount, account_id)
            if (
                account is None
                or account.ledger_id != ledger.id
                or account.category
                in (AccountCategory.BANK, AccountCategory.DEBTOR, AccountCategory.CREDITOR)
            ):
                return None
            accounts[account_id] = account
        return stats.setdefault(account_id, _AccountStat(accounts[account_id]))

    invoices = (
        await session.scalars(
            select(Invoice)
            .where(
                Invoice.ledger_id == ledger.id,
                Invoice.provider_contact_id == provider_contact_id,
                Invoice.duplicate_of_id.is_(None),
            )
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc())
            .limit(INVOICE_HISTORY_LIMIT)
        )
    ).all()
    superseded = {inv.supersedes_id for inv in invoices if inv.supersedes_id}
    creditor_account: LedgerAccount | None = None
    counted_invoices = 0
    for inv in invoices:
        if inv.id in superseded:
            continue
        counted_invoices += 1
        if creditor_account is None and inv.creditor_account_id is not None:
            creditor_account = await session.get(LedgerAccount, inv.creditor_account_id)
        lines = (
            await session.scalars(
                select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id).order_by(InvoiceLine.id)
            )
        ).all()
        for index, line in enumerate(lines):
            entry = await stat(line.account_id)
            if entry is None:
                continue
            entry.count_invoices += 1
            if inv.posting_status is PostingStatus.POSTED:
                entry.count_posted += 1
            entry.touch(inv.invoice_date)
            by_position[index][line.account_id] += 1
            if line.text:
                entry.texts.add(_norm(line.text))
                by_text[_norm(line.text)][line.account_id] += 1

    fingerprints = await _provider_fingerprints(session, provider_contact_id)
    counted_bank = 0
    if fingerprints:
        bank_accounts = set(
            (
                await session.scalars(
                    select(LedgerAccount.id).where(
                        LedgerAccount.ledger_id == ledger.id,
                        LedgerAccount.category == AccountCategory.BANK,
                    )
                )
            ).all()
        )
        rows = (
            await session.execute(
                select(PostingDecision, BankTransaction)
                .join(BankTransaction, BankTransaction.id == PostingDecision.bank_transaction_id)
                .where(
                    PostingDecision.legal_entity_id == ledger.legal_entity_id,
                    PostingDecision.status.in_(CONFIRMED),
                    PostingDecision.decided_by.is_not(None),
                    PostingDecision.journal_entry_id.is_not(None),
                    BankTransaction.counterpart_iban_fingerprint.in_(fingerprints),
                    BankTransaction.amount < 0,
                )
                .order_by(PostingDecision.decided_at.desc())
                .limit(HISTORY_LIMIT)
            )
        ).all()
        for decision, tx in rows:
            posting = await session.get(JournalEntry, decision.journal_entry_id)
            if posting is None or posting.reversed_by_id is not None:
                continue
            line_ids = await session.scalars(
                select(JournalLine.account_id)
                .where(JournalLine.journal_entry_id == posting.id)
                .distinct()
            )
            counted_bank += 1
            for account_id in line_ids.all():
                if account_id in bank_accounts:
                    continue
                item = await stat(account_id)
                if item is None:
                    continue
                item.count_bank += 1
                item.touch(tx.booking_date)

    ranked = sorted(
        stats.values(),
        key=lambda s: (-s.total, -s.count_posted, s.last_used_on or date.min, s.account.number),
    )

    def _reason(entry: _AccountStat, *, text_hit: bool, position_hit: bool) -> str:
        parts = []
        if entry.count_invoices:
            parts.append(
                f"{entry.count_invoices} mal auf Rechnungen des Ausstellers erfasst"
                + (f" ({entry.count_posted} gebucht)" if entry.count_posted else "")
            )
        if entry.count_bank:
            parts.append(f"{entry.count_bank} mal bei Bankumsätzen des Ausstellers gewählt")
        if text_hit:
            parts.append("gleicher Positionstext")
        elif position_hit:
            parts.append("gleiche Position")
        return ", ".join(parts)

    texts = list(line_texts or [None])
    lines_out: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        key = _norm(text)
        preferred = by_text.get(key, {}) if key else {}
        positional = by_position.get(index, {})
        ordered = sorted(
            ranked,
            key=lambda s: (
                -preferred.get(s.account.id, 0),
                -positional.get(s.account.id, 0),
                -s.total,
                s.account.number,
            ),
        )
        lines_out.append(
            {
                "index": index,
                "proposals": [
                    s.out(
                        index=index,
                        reason=_reason(
                            s,
                            text_hit=preferred.get(s.account.id, 0) > 0,
                            position_hit=positional.get(s.account.id, 0) > 0,
                        ),
                    )
                    for s in ordered[:ACCOUNT_PROPOSALS_PER_LINE]
                ],
            }
        )
    return {
        "lines": lines_out,
        "creditor_account": (
            {
                "account_id": str(creditor_account.id),
                "account_number": creditor_account.number,
                "name": creditor_account.name,
            }
            if creditor_account is not None
            else None
        ),
        "sources": {"invoices": counted_invoices, "bank_decisions": counted_bank},
    }


def account_decision(
    proposals: dict[str, Any], final_account_ids: list[uuid.UUID | str]
) -> dict[str, Any]:
    """Diff between the first proposal per line and the account the reviewer confirmed
    (plan S7: Entscheidungs-Diff erfasst). Pure; ``outcome`` is ``no_proposal`` when no line
    had a proposal, ``accepted_unchanged`` when every proposed line was kept, ``modified``
    otherwise. Lines beyond the proposals count as modifications only when a proposal existed
    for the overall history (the first line's proposals serve as fallback)."""
    lines = proposals.get("lines") or []
    fallback = (lines[0].get("proposals") or []) if lines else []
    proposed: list[dict[str, Any]] = []
    diff: list[dict[str, Any]] = []
    for index, final_id in enumerate(final_account_ids):
        candidates = lines[index].get("proposals") if index < len(lines) else fallback
        first = (candidates or [None])[0]
        proposed_id = first.get("account_id") if first else None
        proposed.append(
            {
                "index": index,
                "account_id": proposed_id,
                "account_number": first.get("account_number") if first else None,
            }
        )
        if proposed_id is not None and str(final_id) != str(proposed_id):
            diff.append(
                {
                    "index": index,
                    "proposed_account_id": proposed_id,
                    "final_account_id": str(final_id),
                }
            )
    if not any(p["account_id"] for p in proposed):
        outcome = "no_proposal"
    else:
        outcome = "modified" if diff else "accepted_unchanged"
    return {
        "proposed": proposed,
        "final": [{"index": i, "account_id": str(a)} for i, a in enumerate(final_account_ids)],
        "diff": diff,
        "outcome": outcome,
        "sources": proposals.get("sources") or {},
    }


__all__ = [
    "ACCOUNT_PROPOSALS_PER_LINE",
    "HISTORY_LIMIT",
    "account_decision",
    "counterparty_history",
    "creditor_account_history",
]
