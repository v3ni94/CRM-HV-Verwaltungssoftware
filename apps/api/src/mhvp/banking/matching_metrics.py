"""Matching key figures per tenant and period (M12 acceptance: coverage and error rate apart).

Both figures come from existing data only (bank transaction status, rule hits, journal entries
and their reversals); nothing is estimated.

* Coverage (Abdeckungsgrad): share of transactions in the period that the automation assigned
  unambiguously and posted (``matched_rule_id`` set) among all transactions of the period.
* Error rate (Fehlerquote): share of those automatic assignments whose posting was later
  reversed by a reviewer, split into corrected (a person posted the transaction again) and
  cancelled (reversal only).

Operational figures, no proof of safety (7.4): a low error rate never releases automation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import EntryKind, JournalEntry
from mhvp.banking.models import BankTransaction, TransactionStatus

OPEN_STATES = (TransactionStatus.NEW, TransactionStatus.NEEDS_REVIEW, TransactionStatus.PROPOSED)


@dataclass(frozen=True)
class MatchingMetrics:
    period_from: date | None
    period_to: date | None
    transactions: int
    incoming: int
    auto_matched: int
    manual_booked: int
    open: int
    ignored: int
    auto_reversed: int
    auto_corrected: int
    auto_cancelled: int

    @property
    def coverage(self) -> Decimal | None:
        return _ratio(self.auto_matched, self.transactions)

    @property
    def error_rate(self) -> Decimal | None:
        return _ratio(self.auto_reversed, self.auto_matched)

    def as_dict(self) -> dict[str, Any]:
        return {
            "period_from": self.period_from,
            "period_to": self.period_to,
            "transactions": self.transactions,
            "incoming": self.incoming,
            "auto_matched": self.auto_matched,
            "manual_booked": self.manual_booked,
            "open": self.open,
            "ignored": self.ignored,
            "coverage": self.coverage,
            "auto_reversed": self.auto_reversed,
            "auto_corrected": self.auto_corrected,
            "auto_cancelled": self.auto_cancelled,
            "error_rate": self.error_rate,
            "note": (
                "Betriebskennzahlen aus vorhandenen Daten; eine niedrige Fehlerquote ist kein "
                "Nachweis und keine Freigabe der Automatik (7.4)."
            ),
        }


def _ratio(part: int, whole: int) -> Decimal | None:
    if whole == 0:
        return None
    return (Decimal(part) / Decimal(whole)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


async def compute(
    session: AsyncSession, *, period_from: date | None = None, period_to: date | None = None
) -> MatchingMetrics:
    query = select(BankTransaction)
    if period_from is not None:
        query = query.where(BankTransaction.booking_date >= period_from)
    if period_to is not None:
        query = query.where(BankTransaction.booking_date <= period_to)
    rows = (await session.scalars(query)).all()
    auto = [t for t in rows if t.matched_rule_id is not None and t.journal_entry_id is not None]
    reversed_count = corrected = cancelled = 0
    if auto:
        entries = (
            await session.scalars(
                select(JournalEntry).where(
                    JournalEntry.bank_transaction_id.in_([t.id for t in auto])
                )
            )
        ).all()
        by_tx: dict[uuid.UUID, list[JournalEntry]] = {}
        for e in entries:
            if e.bank_transaction_id is not None:
                by_tx.setdefault(e.bank_transaction_id, []).append(e)
        for t in auto:
            own = by_tx.get(t.id, [])
            original = next((e for e in own if e.id == t.journal_entry_id), None)
            if original is None or original.reversed_by_id is None:
                continue
            reversed_count += 1
            # A person posted the transaction again after the reversal: corrected, else cancelled.
            later = [
                e
                for e in own
                if e.id != original.id
                and e.kind is not EntryKind.REVERSAL
                and e.reversed_by_id is None
                and e.created_by is not None
            ]
            if later:
                corrected += 1
            else:
                cancelled += 1
    return MatchingMetrics(
        period_from=period_from,
        period_to=period_to,
        transactions=len(rows),
        incoming=sum(1 for t in rows if t.amount > 0),
        auto_matched=len(auto),
        manual_booked=sum(
            1 for t in rows if t.status is TransactionStatus.BOOKED and t.matched_rule_id is None
        ),
        open=sum(1 for t in rows if t.status in OPEN_STATES),
        ignored=sum(1 for t in rows if t.status is TransactionStatus.IGNORED),
        auto_reversed=reversed_count,
        auto_corrected=corrected,
        auto_cancelled=cancelled,
    )
