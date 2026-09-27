"""Open item settlement proposal in the statutory order (M10-03, 7.4 Nr. 5, D39).

Operator decision 26.09.2026: when the payer gives no Tilgungsbestimmung the platform
*proposes* an allocation in the statutory order and never applies it by itself. A staff member
confirms the proposal (same permission as the existing explicit open item settlement), the
confirmation is audited with the rule version, and an explicit determination of the payer
always wins (D39). Every posting stays behind release gate G1.

The order implemented here (``RULE_VERSION``) is deterministic and recomputable by hand:

1. due items before items not yet due;
2. among due items: the one with less security first (no security data exists on open items
   yet, so all items rank equal here), then the more burdensome one (an item in a sent dunning
   case), then the older one (due date, then booking date);
3. within the same rank: costs (dunning fee) before interest before principal;
4. ties are broken by the open item id so two runs always give the same result.

The legal review of this order is open until G1 (Rechtsberatung); the proposal carries the
note ``PROPOSAL_NOTE`` for that reason. Nothing in this module writes to the database.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    AccountCategory,
    DunningCase,
    EntryKind,
    JournalEntry,
    Ledger,
    LedgerAccount,
    OpenItemKind,
)
from mhvp.core.problems import ErrorCodes, ProblemError

RULE_ID = "M10-03"
RULE_VERSION = "1"
PROPOSAL_NOTE = "Vorschlag nach gesetzlicher Reihenfolge, Rechtsprüfung vor G1 offen"

REASON_DETERMINED = "Bestimmung des Zahlers"
REASON_STATUTORY = "gesetzliche Reihenfolge"

CLASS_COSTS = "costs"
CLASS_INTEREST = "interest"
CLASS_PRINCIPAL = "principal"
_CLASS_RANK = {CLASS_COSTS: 0, CLASS_INTEREST: 1, CLASS_PRINCIPAL: 2}
_CLASS_BY_KIND = {EntryKind.DUNNING_FEE: CLASS_COSTS, EntryKind.INTEREST: CLASS_INTEREST}

ZERO = Decimal("0.00")
_FAR = date.max


@dataclass(frozen=True)
class ProposalItem:
    """One open receivable as the proposal sees it (all facts as of the cut-off date)."""

    open_item_id: uuid.UUID
    remaining: Decimal
    booking_date: date
    due_date: date | None
    claim_class: str = CLASS_PRINCIPAL
    burdensome: bool = False  # in a sent dunning case
    security: int = 0  # 0 = no security data; lower ranks first
    reference: str | None = None


@dataclass(frozen=True)
class Determination:
    """Explicit Tilgungsbestimmung of the payer: item and optional amount (None = remaining)."""

    open_item_id: uuid.UUID
    amount: Decimal | None = None


@dataclass
class Allocation:
    open_item_id: uuid.UUID
    amount: Decimal
    remaining_before: Decimal
    reason: str
    rank: int
    due_date: date | None
    claim_class: str


@dataclass
class Proposal:
    amount: Decimal
    as_of: date
    allocations: list[Allocation] = field(default_factory=list)
    unallocated: Decimal = ZERO
    basis: str = "statutory_order"  # statutory_order, determination, mixed, none

    @property
    def fingerprint(self) -> str:
        parts = [f"{RULE_ID}:{RULE_VERSION}", str(self.amount), self.as_of.isoformat()]
        parts += [f"{a.open_item_id}:{a.amount}:{a.reason}" for a in self.allocations]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": RULE_ID,
            "rule_version": RULE_VERSION,
            "note": PROPOSAL_NOTE,
            "requires_confirmation": True,
            "basis": self.basis,
            "amount": self.amount,
            "as_of": self.as_of,
            "allocations": [
                {
                    "open_item_id": a.open_item_id,
                    "amount": a.amount,
                    "remaining_before": a.remaining_before,
                    "reason": a.reason,
                    "rank": a.rank,
                    "due_date": a.due_date,
                    "claim_class": a.claim_class,
                }
                for a in self.allocations
            ],
            "unallocated": self.unallocated,
            "fingerprint": self.fingerprint,
        }


def statutory_key(item: ProposalItem, as_of: date) -> tuple[Any, ...]:
    """Sort key of the statutory order; smaller sorts first."""
    due = item.due_date or item.booking_date
    return (
        due > as_of,  # due before not yet due
        item.security,  # less security first
        not item.burdensome,  # more burdensome first
        due,  # older first (by due date)
        _CLASS_RANK.get(item.claim_class, 2),  # costs, interest, principal
        item.booking_date,
        str(item.open_item_id),
    )


def propose(
    items: list[ProposalItem],
    amount: Decimal,
    as_of: date,
    determination: list[Determination] | None = None,
) -> Proposal:
    """Pure function: allocate ``amount`` over ``items``. Determined items first, in the order
    the payer gave them (D39); the rest in the statutory order; what is left stays unallocated
    (credit, never income, D07)."""
    if amount <= 0:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Zahlbetrag muss größer 0 sein.")
    by_id = {i.open_item_id: i for i in items}
    proposal = Proposal(amount=amount, as_of=as_of)
    rest = amount
    left = {i.open_item_id: i.remaining for i in items if i.remaining > 0}
    rank = 0

    def take(item: ProposalItem, wanted: Decimal | None, reason: str) -> None:
        nonlocal rest, rank
        open_amount = left.get(item.open_item_id, ZERO)
        value = min(rest, open_amount if wanted is None else min(wanted, open_amount))
        if value <= 0:
            return
        rank += 1
        proposal.allocations.append(
            Allocation(
                open_item_id=item.open_item_id,
                amount=value,
                remaining_before=open_amount,
                reason=reason,
                rank=rank,
                due_date=item.due_date,
                claim_class=item.claim_class,
            )
        )
        left[item.open_item_id] = open_amount - value
        rest -= value

    determined = 0
    for d in determination or []:
        item = by_id.get(d.open_item_id)
        if item is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Die Tilgungsbestimmung nennt einen unbekannten offenen Posten.",
            )
        if d.amount is not None and d.amount <= 0:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Der bestimmte Betrag muss größer 0 sein."
            )
        before = len(proposal.allocations)
        take(item, d.amount, REASON_DETERMINED)
        determined += len(proposal.allocations) - before
    for item in sorted(items, key=lambda i: statutory_key(i, as_of)):
        if rest <= 0:
            break
        take(item, None, REASON_STATUTORY)
    proposal.unallocated = rest
    statutory = len(proposal.allocations) - determined
    if determined and statutory:
        proposal.basis = "mixed"
    elif determined:
        proposal.basis = "determination"
    elif statutory:
        proposal.basis = "statutory_order"
    else:
        proposal.basis = "none"
    return proposal


async def items_for(
    session: AsyncSession, ledger: Ledger, account_id: uuid.UUID, as_of: date
) -> list[ProposalItem]:
    """Open receivables of one debtor account as of a date, with the facts the order needs."""
    account = await session.get(LedgerAccount, account_id)
    if account is None or account.ledger_id != ledger.id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Personenkonto nicht gefunden.")
    if account.category is not AccountCategory.DEBTOR:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Der Ausgleich nach Reihenfolge gilt für Debitoren."
        )
    rows = [
        r
        for r in await acc.open_items(session, ledger, as_of, account_id)
        if r["kind"] == OpenItemKind.RECEIVABLE.value and r["remaining"] > 0
    ]
    if not rows:
        return []
    entries = {
        e.id: e
        for e in await session.scalars(
            select(JournalEntry).where(JournalEntry.id.in_([r["journal_entry_id"] for r in rows]))
        )
    }
    dunned: set[str] = set()
    for case in await session.scalars(
        select(DunningCase).where(
            DunningCase.debtor_account_id == account_id, DunningCase.status == "sent"
        )
    ):
        dunned.update(str(i.get("open_item_id")) for i in case.open_items)
    out = []
    for r in rows:
        entry = entries.get(r["journal_entry_id"])
        out.append(
            ProposalItem(
                open_item_id=r["id"],
                remaining=Decimal(r["remaining"]),
                booking_date=r["booking_date"],
                due_date=r["due_date"],
                claim_class=_CLASS_BY_KIND.get(entry.kind, CLASS_PRINCIPAL)
                if entry
                else CLASS_PRINCIPAL,
                burdensome=str(r["id"]) in dunned,
                reference=entry.reference if entry else None,
            )
        )
    return out


def determination_from_purpose(
    items: list[ProposalItem], purpose: str | None
) -> list[Determination]:
    """Determination from the payment purpose (invoice or charge number, period), reusing the
    deterministic parser of the bank matching (M12-03). Only unambiguous hits count; an item
    is named when its reference or its due month is in the purpose."""
    if not purpose:
        return []
    from mhvp.banking import allocation

    hints = allocation.parse_allocation_hint(purpose)
    if hints.empty:
        return []
    named = [
        i
        for i in sorted(items, key=lambda i: (i.due_date or i.booking_date, str(i.open_item_id)))
        if allocation.matches_item(
            hints, reference=i.reference, period=i.due_date or i.booking_date
        )
    ]
    return [Determination(i.open_item_id) for i in named]


def verify_fingerprint(proposal: Proposal, fingerprint: str) -> None:
    if proposal.fingerprint != fingerprint:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail=(
                "Der Vorschlag ist nicht mehr aktuell (offene Posten oder Regelversion haben "
                "sich geändert). Bitte neu berechnen und erneut bestätigen."
            ),
            extensions={"rule": RULE_ID, "rule_version": RULE_VERSION},
        )
