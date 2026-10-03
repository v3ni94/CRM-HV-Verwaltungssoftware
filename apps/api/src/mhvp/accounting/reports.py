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

from mhvp.accounting import datev_mapping
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
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed
from mhvp.core.escaping import csv_safe_cell
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today

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
        # GAH-104: how the kind was derived, so the number convention fallback is visible.
        basis = "default"
        if account.property_bank_account_id:
            basis = "bank_account"
            bank = await session.get(PropertyBankAccount, account.property_bank_account_id)
            if bank is not None and bank.segregated:
                kind = "deposit"
            elif bank is not None and bank.kind is BankAccountKind.RESERVE:
                kind = "reserve"
        elif account.number == "001201":
            kind = "reserve"
            basis = "number_convention"
        if kind == "deposit":
            deposit += value
        elif kind == "reserve":
            reserve += value
        else:
            free += value
        lines.append(
            {
                "number": account.number,
                "name": account.name,
                "balance": value,
                "kind": kind,
                "kind_basis": basis,
            }
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
    debtor_credits = await debtor_credit_balances(session, ledger, as_of)
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
        # GAK-102 (7.4 Nr. 5, 7.5): credit balances of debtors (overpayments) are bound funds,
        # owed back or to be offset, never free liquidity.
        "debtor_credits": debtor_credits,
        "projected_free_funds": free - outflow - debtor_credits,
        "note": (
            "Erwartete Einzahlungen sind keine vorhandene Liquidität (nicht projiziert). "
            "Guthaben von Debitoren aus Überzahlungen sind gebundene Mittel."
        ),
    }


async def debtor_credit_balances(session: AsyncSession, ledger: Ledger, as_of: date) -> Decimal:
    """GAK-102: sum of credit balances (credit above debit) on debtor accounts at the key date."""
    balance = func.sum(JournalLine.debit) - func.sum(JournalLine.credit)
    rows = (
        await session.execute(
            select(balance)
            .select_from(JournalLine)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
            .where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.category == AccountCategory.DEBTOR,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date <= as_of,
            )
            .group_by(JournalLine.account_id)
        )
    ).scalars()
    return sum((-Decimal(b) for b in rows if b is not None and b < 0), Decimal("0.00"))


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


def ensure_ledger_in_scope(session: AsyncSession, ledger: Ledger) -> None:
    """Central filter hook (A37, docs/rules/M18-05-steuerberaterzugang.md): exports and
    evaluations of a ledger outside the membership's legal entity scope answer 404. Sessions
    without a request principal (worker, seed) are not limited."""
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)


async def journal_csv(
    session: AsyncSession, ledger: Ledger, start: date, end: date
) -> tuple[bytes, int]:
    """Neutral journal export (semicolon CSV, German decimal comma, ISO dates). Not a DATEV or
    GoBD data carrier format (M18-01)."""
    ensure_ledger_in_scope(session, ledger)
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
                csv_safe_cell(entry.reference or ""),
                entry.kind.value,
                csv_safe_cell(line.text or entry.text),
                account.number,
                csv_safe_cell(account.name),
                str(line.debit).replace(".", ","),
                str(line.credit).replace(".", ","),
                str(entry.reverses_id or ""),
                str(entry.document_id or ""),
            ]
        )
    return out.getvalue().encode("utf-8"), len(rows)


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# DATEV Buchungsstapel (M18-01) ----------------------------------------------------------
#
# Only emitted once consultant_number, client_number and chart_of_accounts are set on the
# tenant's TenantBillingSettings (operator decision 25.09.2026). The "Konto" field carries the
# operator's DATEV Sachkonto from datev_account_mapping (A36, docs/rules/M18-04); no chart of
# accounts is preloaded and unmapped accounts stop the export (MHVP-BILL-0008).
# Fields implemented in the EXTF header follow the parts of the DATEV
# "Buchungsstapel" format description that are unambiguous from the repository's integration
# notes; every other header field is left empty and documented there rather than guessed.

DATEV_FORMAT_NAME = "Buchungsstapel"
# Header field 2 (Versionsnummer des Formats) and field 5 (Formatversion) as documented in the
# public DATEV examples ("EXTF";700;21;"Buchungsstapel";7); the self check in
# ``mhvp.accounting.datev_check`` (rules DC-02, DC-04) verifies exactly these values.
DATEV_VERSION_NUMBER = 700
DATEV_FORMAT_VERSION = 7
DATEV_CATEGORY = 21


def _split_group_target(
    lines: list[tuple[JournalLine, LedgerAccount]],
) -> tuple[tuple[JournalLine, LedgerAccount], list[tuple[JournalLine, LedgerAccount]]] | None:
    """Docs/rules/M18-06 (Entwurf, zu prüfen durch Steuerberater): the summing side of a split
    booking is the side with exactly one line; every line of the other side gets that line's
    account as Gegenkonto. Returns ``None`` when neither side has exactly one line (booking not
    representable this way)."""
    debit = [(line, account) for line, account in lines if line.debit]
    credit = [(line, account) for line, account in lines if line.credit]
    if len(debit) == 1 and len(credit) != 1:
        return debit[0], credit
    if len(credit) == 1 and len(debit) != 1:
        return credit[0], debit
    return None


def _stapel_row(
    entry: JournalEntry,
    line: JournalLine,
    konto: str,
    gegenkonto: str,
) -> list[str]:
    amount = line.debit if line.debit else line.credit
    soll_haben = "S" if line.debit else "H"
    return [
        str(amount).replace(".", ","),
        soll_haben,
        konto,
        gegenkonto,
        f"{entry.booking_date:%d%m}",
        (line.text or entry.text or "")[:60],
        entry.reference or "",
    ]


async def datev_csv(
    session: AsyncSession,
    ledger: Ledger,
    start: date,
    end: date,
    *,
    consultant_number: str,
    client_number: str,
    chart_of_accounts: str,
    account_length: int | None,
    fiscal_year_start_month: int,
) -> tuple[bytes, int, list[dict[str, Any]]]:
    """DATEV EXTF Buchungsstapel CSV. Requires the three operator-entered parameters; the caller
    checks their presence (MHVP-BILL-0004) before calling this. The "Konto" field carries the
    DATEV Sachkonto from the operator's mapping (``mhvp.accounting.datev_mapping``, A36,
    M18-04) resolved per ledger and booking date. When any posted line has no mapping the
    export stops with MHVP-BILL-0008 and the list of missing accounts; raw CRM numbers are
    never written silently.

    Konto/Gegenkonto pairing (M18-01 Folgepunkt, docs/rules/M18-06, Entwurf, Quellenstatus
    "zu prüfen durch Steuerberater"): a booking with exactly two lines (one Soll, one Haben)
    becomes one Stapelzeile, Konto the Soll line, Gegenkonto the Haben line. A split booking
    (more than two lines) is written one Stapelzeile per line of the non summing side, each
    against the summing side's account as Gegenkonto (``_split_group_target``); a split
    booking with no single summing side cannot be represented this way and is left out of
    the file (never silently), reported in the returned ``skipped`` list with the Beleg-ID so
    the caller can show a "Splitbuchung nicht abbildbar" notice."""
    ensure_ledger_in_scope(session, ledger)
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
    resolver = await datev_mapping.load_resolver(session, ledger)
    missing: dict[str, dict[str, Any]] = {}
    account_target: dict[Any, str] = {}
    for entry, line, account in rows:
        target = resolver.resolve(account.number, entry.booking_date)
        if target is None:
            item = missing.setdefault(
                account.number,
                {
                    "account_code": account.number,
                    "account_name": account.name,
                    "lines": 0,
                    "first_booking_date": entry.booking_date,
                    "last_booking_date": entry.booking_date,
                },
            )
            item["lines"] += 1
            item["first_booking_date"] = min(item["first_booking_date"], entry.booking_date)
            item["last_booking_date"] = max(item["last_booking_date"], entry.booking_date)
            continue
        account_target[line.id] = target
    if missing:
        codes = ", ".join(sorted(missing))
        raise ProblemError(
            ErrorCodes.DATEV_MAPPING_MISSING,
            detail=(
                f"Für {len(missing)} Konten fehlt die DATEV-Kontenzuordnung im Zeitraum "
                f"{start:%d.%m.%Y} bis {end:%d.%m.%Y}: {codes}. Zuordnung unter Einstellungen, "
                "Buchhaltung, DATEV pflegen."
            ),
            extensions={
                "missing": [
                    {
                        **item,
                        "first_booking_date": item["first_booking_date"].isoformat(),
                        "last_booking_date": item["last_booking_date"].isoformat(),
                    }
                    for item in sorted(missing.values(), key=lambda i: str(i["account_code"]))
                ]
            },
        )
    fiscal_year_start = date(start.year, fiscal_year_start_month, 1)
    if fiscal_year_start > start:
        fiscal_year_start = date(start.year - 1, fiscal_year_start_month, 1)
    generated = f"{local_today():%Y%m%d}000000000"
    header = [
        "EXTF",
        str(DATEV_VERSION_NUMBER),
        str(DATEV_CATEGORY),
        DATEV_FORMAT_NAME,
        str(DATEV_FORMAT_VERSION),
        generated,
        "",
        "RE",
        "",
        "",
        consultant_number,
        client_number,
        f"{fiscal_year_start:%Y%m%d}",
        str(account_length or ""),
        f"{start:%Y%m%d}",
        f"{end:%Y%m%d}",
        "",
        "",
        "1",
        chart_of_accounts.upper(),
        "0",
    ]
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    writer.writerow(header)
    writer.writerow(
        [
            "Umsatz (ohne Soll/Haben-Kz)",
            "Soll/Haben-Kennzeichen",
            "Konto",
            "Gegenkonto (ohne BU-Schlüssel)",
            "Belegdatum",
            "Buchungstext",
            "Belegfeld 1",
        ]
    )
    groups: list[tuple[JournalEntry, list[tuple[JournalLine, LedgerAccount]]]] = []
    for entry, line, account in rows:
        if not groups or groups[-1][0].id != entry.id:
            groups.append((entry, []))
        groups[-1][1].append((line, account))

    skipped: list[dict[str, Any]] = []
    stapel_rows = 0
    for entry, lines in groups:
        debit_lines = [(line, account) for line, account in lines if line.debit]
        credit_lines = [(line, account) for line, account in lines if line.credit]
        if len(lines) == 2 and len(debit_lines) == 1 and len(credit_lines) == 1:
            (d_line, _d_account) = debit_lines[0]
            (c_line, _c_account) = credit_lines[0]
            writer.writerow(
                _stapel_row(entry, d_line, account_target[d_line.id], account_target[c_line.id])
            )
            stapel_rows += 1
            continue
        split = _split_group_target(lines)
        if split is None:
            skipped.append(
                {
                    "journal_entry_id": str(entry.id),
                    "document_id": str(entry.document_id) if entry.document_id else None,
                    "reference": entry.reference,
                    "message": (
                        "Splitbuchung nicht abbildbar: weder die Soll- noch die Habenseite "
                        "hat genau eine Zeile (docs/rules/M18-06, zu prüfen durch "
                        "Steuerberater). Buchung wurde ausgelassen."
                    ),
                }
            )
            continue
        (summen_line, _summen_account), split_lines = split
        summen_target = account_target[summen_line.id]
        for split_line, _split_account in split_lines:
            writer.writerow(
                _stapel_row(entry, split_line, account_target[split_line.id], summen_target)
            )
            stapel_rows += 1
    return out.getvalue().encode("utf-8"), stapel_rows, skipped
