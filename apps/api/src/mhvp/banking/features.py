"""Feature extraction for the stage 1 posting proposal (ADR 0014, plan M12 3.1 no. 3).

``collect`` assembles, read only, everything ``posting_proposal.propose`` needs for one bank
transaction from the ledger of the transaction's legal entity (B01): the transaction dict,
the approved and active bank rules, the open receivables with their evidence and the open
payables. ``Features.hash`` is a canonical SHA-256 over that input, so a stored proposal
snapshot (``posting_decision``) can be recognised as stale when the facts changed (a new open
item, a rule approved, a payer IBAN released). ``RULE_VERSION`` is part of the hash: a change
of the extraction invalidates every pending snapshot.

Stage 1d (plan M12 S3) adds, inside the transaction dict: the confirmed decisions of persons
for the same counterparty (``history``, only with ``learning_bookkeeper_enabled``), the posted
invoices linked to the transaction (``linked_invoices``), an own payment order found by the
end-to-end id (``payment_order``), the partner bank account of a recognised transfer pair
(``transfer_pair``) and the booking texts of the ledger's accounts (``account_texts``); rules
carry the end date of their contract and payables their invoice id. All of it is part of the
hash, so a new confirmed decision of the same counterparty refreshes the pending snapshot
("Historie wirkt sofort", plan 3.3).

Nothing here reads across legal entities or tenants, and nothing leaves the platform. The
stored summary (``Features.summary``) is minimised: no counterpart name, no full purpose, no
plain IBAN, only the pseudonymous fingerprint, identifiers and counts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Version of the feature extraction. Bump on every change of ``collect`` or ``summary`` that
# alters what a proposal is computed from; documented in docs/rules/M12-04.
RULE_VERSION = "2026.09.28-2"

# End-to-end ids that banks deliver when the originator gave none (ISO 20022).
_NO_END_TO_END = {"", "NOTPROVIDED", "NOTPROVIDED.", "N/A"}


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, set | frozenset):
        return sorted(str(v) for v in value)
    raise TypeError(f"not serialisable: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Deterministic JSON (sorted keys, no whitespace, stable scalar encoding)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


@dataclass
class Features:
    """Input of ``posting_proposal.propose`` for one transaction plus its identity."""

    tx: dict[str, Any]
    rules: list[dict[str, Any]] = field(default_factory=list)
    open_items: list[dict[str, Any]] = field(default_factory=list)
    payables: list[dict[str, Any]] = field(default_factory=list)
    rule_version: str = RULE_VERSION

    def hash(self) -> str:
        payload = {
            "rule_version": self.rule_version,
            "tx": self.tx,
            "rules": sorted(self.rules, key=lambda r: str(r.get("id"))),
            "open_items": sorted(self.open_items, key=lambda i: str(i.get("id"))),
            "payables": sorted(self.payables, key=lambda p: str(p.get("id"))),
        }
        return hashlib.sha256(canonical_json(payload).encode()).hexdigest()

    def summary(self) -> dict[str, Any]:
        """Minimised summary stored with a decision (no names, no purpose text, no IBAN)."""
        amount = Decimal(str(self.tx["amount"]))
        summary = {
            "rule_version": self.rule_version,
            "amount": str(amount),
            "direction": "credit" if amount > 0 else "debit",
            "booking_date": self.tx.get("booking_date"),
            "counterpart_iban_fingerprint": self.tx.get("counterpart_iban_fingerprint"),
            "has_mandate_reference": bool(self.tx.get("mandate_reference")),
            "has_end_to_end_id": bool(self.tx.get("end_to_end_id")),
            "transaction_code": self.tx.get("transaction_code"),
            "rule_ids": sorted(str(r["id"]) for r in self.rules),
            "open_item_ids": sorted(str(i["id"]) for i in self.open_items),
            "payable_ids": sorted(str(p["id"]) for p in self.payables),
            # Stage 1d (S3): counts and identifiers only.
            "history_count": len(self.tx.get("history") or []),
            "history_reversed": sum(1 for e in self.tx.get("history") or [] if e.get("reversed")),
            "linked_invoice_ids": sorted(
                str(i.get("invoice_id")) for i in self.tx.get("linked_invoices") or []
            ),
            "payment_order_id": (self.tx.get("payment_order") or {}).get("id"),
            "transfer_pair": bool(self.tx.get("transfer_pair")),
        }
        # JSON scalars only (dates as ISO strings): the summary is stored in JSONB.
        loaded: dict[str, Any] = json.loads(canonical_json(summary))
        return loaded


async def _is_deposit_item(session: AsyncSession, item: dict[str, Any], contract: Any) -> bool:
    """Best effort ``is_deposit`` for a receivable open item (M12-01 remainder, operator
    22.09.2026 Kontierungsagent finding): ``OpenItem`` has no Forderungsart distinguishing a
    deposit demand from rent or Hausgeld (``OpenItemKind`` is only receivable/payable, and the
    ``component`` column is never populated by ``_apply_open_items``). Derived instead over the
    contract's own deposit demand: an open (not yet fully settled) ``Deposit`` of the same
    contract whose ``amount_due`` matches the item exactly. Documented as an assumption, not a
    stored Merkmal; see docs/ASSUMPTIONS.md."""
    if item["kind"] != "receivable" or contract is None:
        return False
    from mhvp.contracts.models import Deposit

    rows = await session.scalars(
        select(Deposit).where(
            Deposit.contract_id == contract.id,
            Deposit.status == "open",
            Deposit.amount_due == item["amount"],
        )
    )
    return rows.first() is not None


async def _transfer_pair(session: AsyncSession, tx: Any, ledger: Any) -> dict[str, Any] | None:
    """Partner bank account (ledger account number) of a recognised transfer pair (D04)."""
    from mhvp.accounting.models import LedgerAccount
    from mhvp.banking.models import BankTransaction

    if tx.transfer_pair_id is None:
        return None
    partner = await session.get(BankTransaction, tx.transfer_pair_id)
    if partner is None or partner.legal_entity_id != tx.legal_entity_id:
        return None
    account = await session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.ledger_id == ledger.id,
            LedgerAccount.property_bank_account_id == partner.property_bank_account_id,
        )
    )
    if account is None:
        return None
    return {
        "partner_transaction_id": str(partner.id),
        "partner_account_number": account.number,
    }


async def _payment_order(session: AsyncSession, tx: Any, ledger: Any) -> dict[str, Any] | None:
    """Own payment order of the ledger carrying the transaction's end-to-end id (plan 3.2:
    End-to-End-Referenz gegen PaymentOrder.end_to_end_id). Outgoing only; the bank echoes the
    id of an executed own transfer, so this is evidence for the invoice or open item the
    order was made for."""
    from mhvp.banking.models import PaymentOrder

    e2e = (tx.end_to_end_id or "").strip()
    if tx.amount >= 0 or e2e.upper() in _NO_END_TO_END:
        return None
    order = await session.scalar(
        select(PaymentOrder)
        .where(PaymentOrder.ledger_id == ledger.id, PaymentOrder.end_to_end_id == e2e)
        .order_by(PaymentOrder.created_at.desc())
    )
    if order is None:
        return None
    return {
        "id": str(order.id),
        "end_to_end_id": order.end_to_end_id,
        "invoice_id": str(order.invoice_id) if order.invoice_id else None,
        "open_item_id": str(order.open_item_id) if order.open_item_id else None,
        "amount": order.amount,
        "status": order.status.value,
    }


async def _linked_invoices(session: AsyncSession, tx: Any, ledger: Any) -> list[dict[str, Any]]:
    """Posted invoices of the ledger linked to the transaction (``InvoiceBankTransactionLink``,
    ``mhvp.banking.invoice_matching``) with creditor account, open payable and line accounts."""
    from mhvp.accounting.models import (
        Invoice,
        InvoiceLine,
        LedgerAccount,
        OpenItem,
        OpenItemSettlement,
        PostingStatus,
    )
    from mhvp.banking.models import InvoiceBankTransactionLink

    links = (
        await session.scalars(
            select(InvoiceBankTransactionLink)
            .where(InvoiceBankTransactionLink.bank_transaction_id == tx.id)
            .order_by(InvoiceBankTransactionLink.created_at)
        )
    ).all()
    out: list[dict[str, Any]] = []
    for link in links:
        invoice = await session.get(Invoice, link.invoice_id)
        if (
            invoice is None
            or invoice.ledger_id != ledger.id
            or invoice.posting_status is not PostingStatus.POSTED
        ):
            continue
        creditor = (
            await session.get(LedgerAccount, invoice.creditor_account_id)
            if invoice.creditor_account_id
            else None
        )
        open_item = None
        remaining = None
        if invoice.journal_entry_id is not None and creditor is not None:
            open_item = await session.scalar(
                select(OpenItem).where(
                    OpenItem.journal_entry_id == invoice.journal_entry_id,
                    OpenItem.account_id == creditor.id,
                )
            )
        if open_item is not None:
            settled = await session.scalar(
                select(func.coalesce(func.sum(OpenItemSettlement.amount), 0)).where(
                    OpenItemSettlement.open_item_id == open_item.id,
                    OpenItemSettlement.date <= tx.booking_date,
                )
            )
            remaining = open_item.amount - Decimal(str(settled or 0))
        lines = []
        for line in (
            await session.scalars(
                select(InvoiceLine)
                .where(InvoiceLine.invoice_id == invoice.id)
                .order_by(InvoiceLine.id)
            )
        ).all():
            account = await session.get(LedgerAccount, line.account_id)
            lines.append(
                {
                    "account_number": account.number if account else None,
                    "name": account.name if account else None,
                    "net": line.net,
                    "text": line.text,
                }
            )
        out.append(
            {
                "invoice_id": str(invoice.id),
                "number": invoice.number,
                "gross": invoice.gross,
                "posted": True,
                "match_basis": link.match_basis.value,
                "creditor_account_number": creditor.number if creditor else None,
                "open_item_id": str(open_item.id) if open_item else None,
                "remaining": remaining,
                "lines": lines,
            }
        )
    return out


async def _account_texts(session: AsyncSession, ledger: Any) -> list[dict[str, Any]]:
    """Active accounts of the ledger with booking texts (personal and bank accounts excluded)."""
    from mhvp.accounting.models import AccountCategory, LedgerAccount

    rows = (
        await session.scalars(
            select(LedgerAccount)
            .where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.active.is_(True),
                LedgerAccount.category.not_in(
                    [AccountCategory.BANK, AccountCategory.DEBTOR, AccountCategory.CREDITOR]
                ),
            )
            .order_by(LedgerAccount.number)
        )
    ).all()
    return [
        {"account_number": a.number, "name": a.name, "booking_texts": list(a.booking_texts)}
        for a in rows
        if a.booking_texts
    ]


async def _history(session: AsyncSession, tx: Any, bank: Any) -> list[dict[str, Any]]:
    """Counterparty history (``mhvp.banking.history``), only with the tenant switch on."""
    from mhvp.banking import history
    from mhvp.banking.proposals import learning_enabled

    if not await learning_enabled(session):
        return []
    return await history.counterparty_history(session, tx, bank_account_id=bank.id)


async def collect(session: AsyncSession, tx: Any) -> Features:
    """Rules, open items and payables of the ledger of the transaction's legal entity as plain
    dicts (read only). Raises the ledger problems of ``matching.ledger_for``."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import Invoice, JournalEntry, LedgerAccount
    from mhvp.banking.matching import ledger_for
    from mhvp.banking.models import BankRule, RuleState
    from mhvp.contacts.models import ContactBankAccount, PartyMember
    from mhvp.contracts.models import Contract, SepaMandate

    ledger, bank = await ledger_for(session, tx)
    rule_rows = (
        await session.scalars(
            select(BankRule).where(
                BankRule.legal_entity_id == tx.legal_entity_id,
                BankRule.approval_state.in_([RuleState.APPROVED, RuleState.ACTIVE]),
            )
        )
    ).all()
    accounts_by_id: dict[uuid.UUID, LedgerAccount] = {}
    rules: list[dict[str, Any]] = []
    for r in rule_rows:
        number = None
        if r.action.get("account_id"):
            acct = await session.get(LedgerAccount, uuid.UUID(str(r.action["account_id"])))
            number = acct.number if acct else None
        contract_end = None
        if r.contract_id is not None:
            bound = await session.get(Contract, r.contract_id)
            contract_end = bound.end_date if bound is not None else None
        rules.append(
            {
                "id": str(r.id),
                "name": r.name,
                "match": r.match,
                "action": {"kind": r.action.get("kind"), "account_number": number},
                "priority": r.priority,
                "approval_state": r.approval_state.value,
                "max_amount": r.max_amount,
                "contract_end": contract_end,
            }
        )
    tx_dict: dict[str, Any] = {
        "amount": tx.amount,
        "booking_date": tx.booking_date,
        "purpose": tx.purpose,
        "counterpart_name": tx.counterpart_name,
        "counterpart_iban_fingerprint": tx.counterpart_iban_fingerprint,
        "mandate_reference": tx.mandate_reference,
        "end_to_end_id": tx.end_to_end_id,
        "creditor_id": tx.creditor_id,
        "transaction_code": tx.transaction_code,
        # Stage 1d (S3); every key optional for ``posting_proposal.propose``.
        "transfer_pair": await _transfer_pair(session, tx, ledger),
        "payment_order": await _payment_order(session, tx, ledger),
        "linked_invoices": await _linked_invoices(session, tx, ledger),
        "account_texts": await _account_texts(session, ledger),
        "history": await _history(session, tx, bank),
    }
    items: list[dict[str, Any]] = []
    payables: list[dict[str, Any]] = []
    for item in await acc.open_items(session, ledger, tx.booking_date):
        if item["kind"] == "payable":
            invoice = await session.scalar(
                select(Invoice).where(Invoice.journal_entry_id == item["journal_entry_id"])
            )
            payables.append(
                {
                    "id": item["id"],
                    "invoice_id": str(invoice.id) if invoice else None,
                    "remaining": abs(item["remaining"]),
                    "number": invoice.number if invoice else None,
                    "payee_iban_fingerprint": invoice.payee_iban_fingerprint if invoice else None,
                    "account_number": item["account_number"],
                }
            )
            continue
        account = accounts_by_id.get(item["account_id"])
        if account is None:
            account = await session.get(LedgerAccount, item["account_id"])
            if account is not None:
                accounts_by_id[item["account_id"]] = account
        contract = await session.get(Contract, item["contract_id"]) if item["contract_id"] else None
        mandate_ref = None
        if contract is not None and contract.sepa_mandate_id:
            mandate = await session.get(SepaMandate, contract.sepa_mandate_id)
            mandate_ref = mandate.reference if mandate else None
        fingerprints: list[str] = []
        if account is not None and account.party_id is not None:
            fingerprints = sorted(
                fp
                for fp in await session.scalars(
                    select(ContactBankAccount.iban_fingerprint)
                    .join(PartyMember, PartyMember.contact_id == ContactBankAccount.contact_id)
                    .where(PartyMember.party_id == account.party_id)
                )
                if fp
            )
        entry = await session.get(JournalEntry, item["journal_entry_id"])
        items.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "remaining": item["remaining"],
                "due_date": item["due_date"] or item["booking_date"],
                "reference": entry.reference if entry is not None else None,
                "contract_number": contract.number if contract else None,
                "contract_id": str(contract.id) if contract else None,
                "mandate_reference": mandate_ref,
                "party_iban_fingerprints": fingerprints,
                "account_number": item["account_number"],
                "debtor_key": str(account.party_id) if account and account.party_id else None,
                "is_deposit": await _is_deposit_item(session, item, contract),
            }
        )
    return Features(tx=tx_dict, rules=rules, open_items=items, payables=payables)
