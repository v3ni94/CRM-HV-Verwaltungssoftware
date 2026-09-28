"""Feature extraction for the stage 1 posting proposal (ADR 0013, plan M12 3.1 no. 3).

``collect`` assembles, read only, everything ``posting_proposal.propose`` needs for one bank
transaction from the ledger of the transaction's legal entity (B01): the transaction dict,
the approved and active bank rules, the open receivables with their evidence and the open
payables. ``Features.hash`` is a canonical SHA-256 over that input, so a stored proposal
snapshot (``posting_decision``) can be recognised as stale when the facts changed (a new open
item, a rule approved, a payer IBAN released). ``RULE_VERSION`` is part of the hash: a change
of the extraction invalidates every pending snapshot.

Nothing here reads across legal entities or tenants, and nothing leaves the platform. The
stored summary (``Features.summary``) is minimised: no counterpart name, no full purpose, no
plain IBAN, only the pseudonymous fingerprint and identifiers.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Version of the feature extraction. Bump on every change of ``collect`` or ``summary`` that
# alters what a proposal is computed from; documented in docs/rules/M12-04.
RULE_VERSION = "2026.09.28-1"


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


async def collect(session: AsyncSession, tx: Any) -> Features:
    """Rules, open items and payables of the ledger of the transaction's legal entity as plain
    dicts (read only). Raises the ledger problems of ``matching.ledger_for``."""
    from mhvp.accounting import services as acc
    from mhvp.accounting.models import Invoice, JournalEntry, LedgerAccount
    from mhvp.banking.matching import ledger_for
    from mhvp.banking.models import BankRule, RuleState
    from mhvp.contacts.models import ContactBankAccount, PartyMember
    from mhvp.contracts.models import Contract, SepaMandate

    ledger, _bank = await ledger_for(session, tx)
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
        rules.append(
            {
                "id": str(r.id),
                "name": r.name,
                "match": r.match,
                "action": {"kind": r.action.get("kind"), "account_number": number},
                "priority": r.priority,
                "approval_state": r.approval_state.value,
                "max_amount": r.max_amount,
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
