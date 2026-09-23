"""Evaluations and exports (7.5 Liquidität, 7.7, M18). Views are per legal entity; tenant wide
lists only show, never offset (B01)."""

import csv
import hashlib
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    AccountCategory,
    EntryStatus,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
    OpenItemSettlement,
)

HORIZON_DAYS = 90


async def _balance(session: AsyncSession, account_id: Any, as_of: date) -> Decimal:
    d, c = (
        await session.execute(
            select(
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalLine.account_id == account_id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date <= as_of,
            )
        )
    ).one()
    return Decimal(d) - Decimal(c)


async def liquidity(session: AsyncSession, ledger: Ledger, as_of: date) -> dict[str, Any]:
    """Actual funds, expected in- and outflows within 90 days, reserves and deposits apart.
    An open receivable or planned debit is not available liquidity (7.5)."""
    from mhvp.properties.models import BankAccountKind, PropertyBankAccount

    free = reserve = deposit = Decimal("0.00")
    accounts = (
        await session.scalars(
            select(LedgerAccount).where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.category.in_((AccountCategory.BANK, AccountCategory.CASH)),
            )
        )
    ).all()
    lines = []
    for account in accounts:
        value = await _balance(session, account.id, as_of)
        kind = "free"
        if account.property_bank_account_id:
            bank = await session.get(PropertyBankAccount, account.property_bank_account_id)
            if bank is not None and bank.segregated:
                kind = "deposit"
            elif bank is not None and bank.kind is BankAccountKind.RESERVE:
                kind = "reserve"
        elif account.number == "001201":
            kind = "reserve"
        if kind == "deposit":
            deposit += value
        elif kind == "reserve":
            reserve += value
        else:
            free += value
        lines.append(
            {"number": account.number, "name": account.name, "balance": value, "kind": kind}
        )
    horizon = as_of + timedelta(days=HORIZON_DAYS)
    items = await acc.open_items(session, ledger, as_of)
    inflow = sum(
        (
            i["remaining"]
            for i in items
            if i["kind"] == "receivable"
            and i["remaining"] > 0
            and (i["due_date"] or as_of) <= horizon
        ),
        Decimal("0.00"),
    )
    outflow = sum(
        (
            i["remaining"]
            for i in items
            if i["kind"] == "payable" and (i["due_date"] or as_of) <= horizon
        ),
        Decimal("0.00"),
    )
    return {
        "ledger_id": ledger.id,
        "as_of": as_of,
        "horizon": horizon,
        "accounts": lines,
        "free_funds": free,
        "reserve_funds": reserve,
        "segregated_deposits": deposit,
        "expected_inflows": inflow,
        "expected_outflows": outflow,
        "projected_free_funds": free - outflow,
        "note": "Erwartete Einzahlungen sind keine vorhandene Liquidität (nicht projiziert).",
    }


async def payments_by_debtor(
    session: AsyncSession, ledger: Ledger, start: date, end: date
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(LedgerAccount.number, LedgerAccount.name, func.sum(OpenItemSettlement.amount))
            .join(JournalEntry, JournalEntry.id == OpenItemSettlement.journal_entry_id)
            .join(
                JournalLine,
                (JournalLine.journal_entry_id == JournalEntry.id) & (JournalLine.credit > 0),
            )
            .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
            .where(
                JournalEntry.ledger_id == ledger.id,
                LedgerAccount.category == AccountCategory.DEBTOR,
                OpenItemSettlement.date.between(start, end),
            )
            .group_by(LedgerAccount.number, LedgerAccount.name)
            .order_by(LedgerAccount.number)
        )
    ).all()
    return [{"number": n, "name": name, "settled": Decimal(total)} for n, name, total in rows]


async def revenue(
    session: AsyncSession, ledger: Ledger, start: date, end: date
) -> list[dict[str, Any]]:
    tb = await acc.trial_balance(session, ledger, end, start)
    return [
        {"number": a["number"], "name": a["name"], "amount": -a["balance"]}
        for a in tb["accounts"]
        if a["category"] == AccountCategory.REVENUE.value
    ]


async def journal_csv(
    session: AsyncSession, ledger: Ledger, start: date, end: date
) -> tuple[bytes, int]:
    """Neutral journal export (semicolon CSV, German decimal comma, ISO dates). Not a DATEV or
    GoBD data carrier format (M18-01)."""
    rows = (
        await session.execute(
            select(JournalEntry, JournalLine, LedgerAccount)
            .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
            .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
            .where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date.between(start, end),
            )
            .order_by(JournalEntry.fiscal_year, JournalEntry.number, JournalLine.line_no)
        )
    ).all()
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Jahr",
            "Nummer",
            "Buchungstag",
            "Belegnummer",
            "Art",
            "Text",
            "Konto",
            "Kontobezeichnung",
            "Soll",
            "Haben",
            "Storno von",
            "Beleg-ID",
        ]
    )
    for entry, line, account in rows:
        writer.writerow(
            [
                entry.fiscal_year,
                entry.number,
                entry.booking_date.isoformat(),
                entry.reference or "",
                entry.kind.value,
                line.text or entry.text,
                account.number,
                account.name,
                str(line.debit).replace(".", ","),
                str(line.credit).replace(".", ","),
                str(entry.reverses_id or ""),
                str(entry.document_id or ""),
            ]
        )
    return out.getvalue().encode("utf-8"), len(rows)


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
