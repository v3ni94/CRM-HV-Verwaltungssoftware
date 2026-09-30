"""Year view of the takeover year (6.9.10, D11, M8-08, M10-07): the prior period is read from
the migration journal, the later period from the active journal, without double counting.

Rules: only expense accounts count as expense; the opening balance entry (source
``migration``) is a balance sheet movement and never an expense; migrated entries dated on or
after the cut off date are ignored (the active journal is leading from the cut off date on).
"""

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import (
    AccountType,
    EntrySource,
    EntryStatus,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
)
from mhvp.imports.migration_models import MigratedJournalEntry, MigratedJournalLine

ZERO = Decimal("0.00")


def _q(value: Decimal | None) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))


async def year_expenses(session: AsyncSession, ledger: Ledger, year: int) -> dict[str, Any]:
    """Expenses of calendar ``year`` split into prior period (migration journal, before the
    cut off date) and later period (active journal, from the cut off date)."""
    cutoff = ledger.migration_cutoff
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    prior_query = (
        select(
            LedgerAccount.number,
            LedgerAccount.name,
            func.sum(MigratedJournalLine.debit - MigratedJournalLine.credit),
        )
        .select_from(MigratedJournalLine)
        .join(MigratedJournalEntry, MigratedJournalEntry.id == MigratedJournalLine.entry_id)
        .join(LedgerAccount, LedgerAccount.id == MigratedJournalLine.account_id)
        .where(
            MigratedJournalEntry.ledger_id == ledger.id,
            LedgerAccount.type == AccountType.EXPENSE,
            MigratedJournalEntry.booking_date >= start,
            MigratedJournalEntry.booking_date <= end,
        )
        .group_by(LedgerAccount.number, LedgerAccount.name)
    )
    post_query = (
        select(
            LedgerAccount.number,
            LedgerAccount.name,
            func.sum(JournalLine.debit - JournalLine.credit),
        )
        .select_from(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
        .where(
            JournalEntry.ledger_id == ledger.id,
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.source != EntrySource.MIGRATION,
            LedgerAccount.type == AccountType.EXPENSE,
            JournalEntry.booking_date >= start,
            JournalEntry.booking_date <= end,
        )
        .group_by(LedgerAccount.number, LedgerAccount.name)
    )
    if cutoff is not None:
        prior_query = prior_query.where(MigratedJournalEntry.booking_date < cutoff)
        post_query = post_query.where(JournalEntry.booking_date >= cutoff)
    prior = {(n, name): _q(v) for n, name, v in (await session.execute(prior_query)).all()}
    later = {(n, name): _q(v) for n, name, v in (await session.execute(post_query)).all()}
    accounts = []
    for key in sorted(set(prior) | set(later)):
        p, n = prior.get(key, ZERO), later.get(key, ZERO)
        accounts.append(
            {
                "account_number": key[0],
                "account_name": key[1],
                "prior_period": p,
                "later_period": n,
                "total": p + n,
            }
        )
    prior_total = sum((a["prior_period"] for a in accounts), ZERO)
    later_total = sum((a["later_period"] for a in accounts), ZERO)
    complete = await session.scalar(
        select(func.bool_and(MigratedJournalEntry.year_complete)).where(
            MigratedJournalEntry.ledger_id == ledger.id,
            MigratedJournalEntry.fiscal_year == year,
        )
    )
    return {
        "ledger_id": ledger.id,
        "year": year,
        "migration_cutoff": cutoff,
        "prior_period_total": prior_total,
        "later_period_total": later_total,
        "total": prior_total + later_total,
        "prior_year_complete": bool(complete) if complete is not None else False,
        "accounts": accounts,
    }
