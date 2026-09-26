"""Daily reconciliation report of the parallel operation (13.1, M8-03, Lückenliste A68).

The staged raw rows of the Immoware24 exports (``import_staging_row`` of the report types
``journal`` and ``bank_transactions``) are aggregated per property and compared with the
platform: account balances of the property's ledgers, open receivables and payables, reserve
accounts, bank balances and incoming payments. The result is a list of figures per property
and metric with source value, platform value, difference and hint, stored as an import run
(``source = immoware24:reconciliation``) with JSON summary; the CSV is rendered from it.

The report only reads and compares. Nothing is posted, corrected or marked; a difference is a
finding for the operator, not an instruction to the platform (rule 0.1.3, 0.1.7).

Column names of the exports are not specified (13.1). The defaults below are assumptions
(docs/ASSUMPTIONS.md A-047) and every tenant can replace them via the stored column
configuration (``ImportMapping`` rows named :data:`MAPPING_NAME`).
"""

import csv
import io
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import (
    AccountCategory,
    EntryStatus,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
    OpenItem,
    OpenItemKind,
    OpenItemSettlement,
)
from mhvp.ai.models import ImportRun, ImportStatus
from mhvp.banking.models import BankStatement, BankTransaction
from mhvp.core import crypto
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.imports.fields import parse_date, parse_decimal
from mhvp.imports.models import ImportMapping, ImportSourceFile, ReportType, StagingRow
from mhvp.properties.models import Property, PropertyBankAccount

RECONCILIATION_SOURCE = "immoware24:reconciliation"
MAPPING_NAME = "Abgleichbericht (A68)"
REPORT_KIND = "reconciliation_report"
ZERO = Decimal("0.00")
CENT = Decimal("0.01")
MAX_WARNINGS = 100
CSV_HEADER = (
    "Objekt",
    "Kennzahl",
    "Schlüssel",
    "Quelle",
    "Plattform",
    "Differenz",
    "Abweichung",
    "Hinweis",
)

# Metric identifiers (stable API values; labels live in the UI catalogues).
KONTOSALDO = "kontosaldo"
DEBITOREN_OP = "debitoren_op"
KREDITOREN_OP = "kreditoren_op"
RUECKLAGE = "ruecklage"
BANKSTAND = "bankstand"
ZAHLUNGEN = "zahlungen"
METRICS = (KONTOSALDO, DEBITOREN_OP, KREDITOREN_OP, RUECKLAGE, BANKSTAND, ZAHLUNGEN)


@dataclass(frozen=True)
class ColumnField:
    name: str
    label: str
    required: bool = False


# Target fields of the column configuration per report type. ``amount`` is the signed amount
# (debit positive); when it is not mapped, ``debit`` minus ``credit`` is used.
JOURNAL_COLUMNS: tuple[ColumnField, ...] = (
    ColumnField("property_number", "Objektnummer", True),
    ColumnField("account_number", "Kontonummer", True),
    ColumnField("booking_date", "Buchungsdatum"),
    ColumnField("amount", "Betrag (Soll positiv)"),
    ColumnField("debit", "Soll"),
    ColumnField("credit", "Haben"),
)
BANK_COLUMNS: tuple[ColumnField, ...] = (
    ColumnField("property_number", "Objektnummer", True),
    ColumnField("iban", "IBAN des Objektkontos", True),
    ColumnField("booking_date", "Buchungsdatum"),
    ColumnField("amount", "Betrag (Gutschrift positiv)", True),
    ColumnField("balance", "Saldo nach Buchung"),
)
COLUMN_FIELDS: dict[str, tuple[ColumnField, ...]] = {
    ReportType.JOURNAL.value: JOURNAL_COLUMNS,
    ReportType.BANK_TRANSACTIONS.value: BANK_COLUMNS,
}
# Assumed headers of the Immoware24 exports (docs/ASSUMPTIONS.md A-047); configurable.
DEFAULT_COLUMNS: dict[str, dict[str, str]] = {
    ReportType.JOURNAL.value: {
        "property_number": "Objekt",
        "account_number": "Konto",
        "booking_date": "Datum",
        "amount": "Betrag",
        "debit": "Soll",
        "credit": "Haben",
    },
    ReportType.BANK_TRANSACTIONS.value: {
        "property_number": "Objekt",
        "iban": "IBAN",
        "booking_date": "Datum",
        "amount": "Betrag",
        "balance": "Saldo",
    },
}
RECONCILED_TYPES = (ReportType.JOURNAL, ReportType.BANK_TRANSACTIONS)


def validate_columns(columns: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Checks a column configuration: only known report types and target fields, required
    fields mapped. Returns the configuration with the defaults filled in for report types
    that are not given."""
    unknown_types = sorted(set(columns) - set(COLUMN_FIELDS))
    if unknown_types:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannte Reporttypen: {', '.join(unknown_types)}."
        )
    result: dict[str, dict[str, str]] = {}
    for report_type, fields in COLUMN_FIELDS.items():
        given = columns.get(report_type)
        if given is None:
            result[report_type] = dict(DEFAULT_COLUMNS[report_type])
            continue
        known = {f.name for f in fields}
        unknown = sorted(set(given) - known)
        if unknown:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Unbekannte Zielfelder für {report_type}: {', '.join(unknown)}.",
            )
        missing = [f.label for f in fields if f.required and not given.get(f.name)]
        if missing:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Pflichtfelder ohne Spalte für {report_type}: {', '.join(missing)}.",
            )
        result[report_type] = {k: str(v).strip() for k, v in given.items() if str(v).strip()}
    return result


async def load_columns(session: AsyncSession) -> tuple[dict[str, dict[str, str]], bool]:
    """Effective column configuration of the tenant and whether it was customised."""
    rows = (
        await session.scalars(
            select(ImportMapping).where(
                ImportMapping.name == MAPPING_NAME, ImportMapping.active.is_(True)
            )
        )
    ).all()
    columns = {rt: dict(cols) for rt, cols in DEFAULT_COLUMNS.items()}
    for row in rows:
        columns[row.report_type.value] = dict(row.columns)
    return columns, bool(rows)


async def store_columns(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    columns: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    """Stores the configuration as versioned ``ImportMapping`` rows (one per report type)."""
    checked = validate_columns(columns)
    for report_type, cols in checked.items():
        previous = (
            await session.scalars(
                select(ImportMapping)
                .where(
                    ImportMapping.name == MAPPING_NAME,
                    ImportMapping.report_type == ReportType(report_type),
                )
                .order_by(ImportMapping.version.desc())
            )
        ).all()
        for p in previous:
            p.active = False
        session.add(
            ImportMapping(
                tenant_id=tenant_id,
                created_by=user_id,
                report_type=ReportType(report_type),
                name=MAPPING_NAME,
                version=(previous[0].version + 1) if previous else 1,
                columns=cols,
                value_maps={},
                active=True,
            )
        )
    await session.flush()
    return checked


# Source aggregation (pure) ---------------------------------------------------------------


def normalise_property_number(value: Any) -> str | None:
    """Property numbers of the platform are three digits; one and two digit numbers of the
    export are zero padded (same rule as the Objektdaten import)."""
    text = str(value).strip() if value is not None else ""
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    if not text:
        return None
    if text.isdigit() and len(text) <= 3:
        return text.zfill(3)
    return text


def normalise_account_number(value: Any) -> str | None:
    """Ledger accounts of the platform carry six digits; shorter export numbers are zero
    padded on the left (assumption A-047), non digits are removed."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    digits = re.sub(r"\D", "", str(value)) if value is not None else ""
    if not digits:
        return None
    return digits.zfill(6) if len(digits) <= 6 else digits


def normalise_iban(value: Any) -> str | None:
    text = re.sub(r"\s+", "", str(value)).upper() if value is not None else ""
    return text or None


def _cell(raw: dict[str, Any], columns: dict[str, str], name: str) -> Any:
    column = columns.get(name)
    if not column:
        return None
    value = raw.get(column)
    if isinstance(value, str):
        value = value.strip() or None
    return value


def _money(value: Any) -> Decimal:
    return parse_decimal(value).quantize(CENT)


@dataclass
class SourceAggregate:
    """Aggregated figures of the staged rows, keyed by property number."""

    # (property, account) -> balance (debit minus credit)
    journal: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    # (property, iban) -> figures of the bank rows
    bank: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    max_date: date | None = None

    def warn(self, message: str) -> None:
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(message)
        self.counts["invalid"] += 1

    @property
    def properties(self) -> list[str]:
        return sorted({p for p, _ in self.journal} | {p for p, _ in self.bank})


def aggregate_rows(
    rows: Iterable[tuple[ReportType, int, dict[str, Any]]],
    columns: dict[str, dict[str, str]],
    as_of: date | None,
) -> SourceAggregate:
    """Sums the raw rows per property. Rows after ``as_of`` are ignored (counted), rows that
    cannot be read are warnings; nothing is guessed."""
    agg = SourceAggregate()
    for report_type, number, raw in rows:
        cols = columns[report_type.value]
        label = f"{report_type.value} Zeile {number}"
        prop = normalise_property_number(_cell(raw, cols, "property_number"))
        if prop is None:
            agg.warn(f"{label}: Objektnummer fehlt")
            continue
        day: date | None = None
        raw_day = _cell(raw, cols, "booking_date")
        if raw_day is not None:
            try:
                day = parse_date(raw_day)
            except ValueError as exc:
                agg.warn(f"{label}: {exc}")
                continue
            if as_of is not None and day > as_of:
                agg.counts["after_as_of"] += 1
                continue
            if agg.max_date is None or day > agg.max_date:
                agg.max_date = day
        try:
            if report_type is ReportType.JOURNAL:
                _aggregate_journal_row(agg, raw, cols, prop, label)
            else:
                _aggregate_bank_row(agg, raw, cols, prop, day, number, label)
        except ValueError as exc:
            agg.warn(f"{label}: {exc}")
            continue
        agg.counts[report_type.value] += 1
    return agg


def _aggregate_journal_row(
    agg: SourceAggregate, raw: dict[str, Any], cols: dict[str, str], prop: str, label: str
) -> None:
    account = normalise_account_number(_cell(raw, cols, "account_number"))
    if account is None:
        raise ValueError("Kontonummer fehlt")
    amount_cell = _cell(raw, cols, "amount")
    if amount_cell is not None:
        amount = _money(amount_cell)
    else:
        debit_cell, credit_cell = _cell(raw, cols, "debit"), _cell(raw, cols, "credit")
        if debit_cell is None and credit_cell is None:
            raise ValueError("Betrag fehlt (weder Betrag noch Soll/Haben)")
        amount = (_money(debit_cell) if debit_cell is not None else ZERO) - (
            _money(credit_cell) if credit_cell is not None else ZERO
        )
    key = (prop, account)
    agg.journal[key] = agg.journal.get(key, ZERO) + amount


def _aggregate_bank_row(
    agg: SourceAggregate,
    raw: dict[str, Any],
    cols: dict[str, str],
    prop: str,
    day: date | None,
    number: int,
    label: str,
) -> None:
    iban = normalise_iban(_cell(raw, cols, "iban"))
    if iban is None:
        raise ValueError("IBAN fehlt")
    amount_cell = _cell(raw, cols, "amount")
    if amount_cell is None:
        raise ValueError("Betrag fehlt")
    amount = _money(amount_cell)
    entry = agg.bank.setdefault(
        (prop, iban),
        {
            "credits": ZERO,
            "turnover": ZERO,
            "balance": None,
            "balance_at": None,
            "from_date": None,
            "to_date": None,
        },
    )
    entry["turnover"] += amount
    if amount > 0:
        entry["credits"] += amount
    balance_cell = _cell(raw, cols, "balance")
    if balance_cell is not None:
        at = (day or date.min, number)
        if entry["balance_at"] is None or at >= entry["balance_at"]:
            entry["balance"], entry["balance_at"] = _money(balance_cell), at
    if day is not None:
        if entry["from_date"] is None or day < entry["from_date"]:
            entry["from_date"] = day
        if entry["to_date"] is None or day > entry["to_date"]:
            entry["to_date"] = day


# Platform figures -----------------------------------------------------------------------


@dataclass
class PlatformFigures:
    property_id: uuid.UUID | None = None
    property_name: str | None = None
    ledgers: int = 0
    # account number -> (balance debit minus credit, category)
    accounts: dict[str, tuple[Decimal, str]] = field(default_factory=dict)
    receivables: Decimal = ZERO
    payables: Decimal = ZERO
    # iban fingerprint -> {"id", "suffix", "kind", "statement_balance", "statement_date"}
    bank_accounts: dict[str, dict[str, Any]] = field(default_factory=dict)
    suffixes: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


async def platform_figures(session: AsyncSession, number: str, as_of: date) -> PlatformFigures:
    """Reads the platform values of one property as of ``as_of`` (posted entries only)."""
    figures = PlatformFigures()
    prop = await session.scalar(select(Property).where(Property.number == number))
    if prop is None:
        return figures
    figures.property_id, figures.property_name = prop.id, prop.name
    ledger_ids = list(await session.scalars(select(Ledger.id).where(Ledger.property_id == prop.id)))
    figures.ledgers = len(ledger_ids)
    if ledger_ids:
        accounts = (
            await session.execute(
                select(LedgerAccount.number, LedgerAccount.category).where(
                    LedgerAccount.ledger_id.in_(ledger_ids)
                )
            )
        ).all()
        # Posted lines until as_of only; drafts and later entries do not count (B07).
        posted = (
            await session.execute(
                select(
                    LedgerAccount.number,
                    func.coalesce(func.sum(JournalLine.debit), 0),
                    func.coalesce(func.sum(JournalLine.credit), 0),
                )
                .select_from(JournalLine)
                .join(LedgerAccount, LedgerAccount.id == JournalLine.account_id)
                .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                .where(
                    LedgerAccount.ledger_id.in_(ledger_ids),
                    JournalEntry.status == EntryStatus.POSTED,
                    JournalEntry.booking_date <= as_of,
                )
                .group_by(LedgerAccount.number)
            )
        ).all()
        balances = {n: (Decimal(d) - Decimal(c)).quantize(CENT) for n, d, c in posted}
        for acc_number, category in accounts:
            # Several ledgers of one property (E01) may share a number: same category, summed.
            figures.accounts[acc_number] = (balances.get(acc_number, ZERO), category.value)
        figures.receivables = await _open_items(session, ledger_ids, OpenItemKind.RECEIVABLE, as_of)
        figures.payables = await _open_items(session, ledger_ids, OpenItemKind.PAYABLE, as_of)

    bank_accounts = (
        await session.scalars(
            select(PropertyBankAccount).where(PropertyBankAccount.property_id == prop.id)
        )
    ).all()
    for account in bank_accounts:
        statement = (
            await session.execute(
                select(BankStatement.closing_balance, BankStatement.closing_date)
                .where(
                    BankStatement.property_bank_account_id == account.id,
                    BankStatement.closing_balance.is_not(None),
                    func.coalesce(BankStatement.closing_date, BankStatement.to_date) <= as_of,
                )
                .order_by(
                    func.coalesce(BankStatement.closing_date, BankStatement.to_date).desc(),
                    BankStatement.created_at.desc(),
                )
                .limit(1)
            )
        ).first()
        turnover = Decimal(
            await session.scalar(
                select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
                    BankTransaction.property_bank_account_id == account.id,
                    BankTransaction.booking_date <= as_of,
                )
            )
            or 0
        ).quantize(CENT)
        figures.bank_accounts[account.iban_fingerprint] = {
            "id": account.id,
            "suffix": account.iban_suffix,
            "kind": account.kind.value,
            "statement_balance": (
                Decimal(statement[0]).quantize(CENT) if statement is not None else None
            ),
            "statement_date": statement[1] if statement is not None else None,
            "turnover": turnover,
        }
        figures.suffixes[account.iban_suffix].append(account.iban_fingerprint)
    return figures


async def _open_items(
    session: AsyncSession, ledger_ids: list[uuid.UUID], kind: OpenItemKind, as_of: date
) -> Decimal:
    """Open amount as of a date: items booked until ``as_of`` minus settlements until then
    (6.9.13, B07). Written off items count as settled."""
    total = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(OpenItem.amount), 0)).where(
                OpenItem.ledger_id.in_(ledger_ids),
                OpenItem.kind == kind,
                OpenItem.booking_date <= as_of,
                OpenItem.written_off.is_(False),
            )
        )
        or 0
    )
    settled = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(OpenItemSettlement.amount), 0))
            .join(OpenItem, OpenItem.id == OpenItemSettlement.open_item_id)
            .where(
                OpenItem.ledger_id.in_(ledger_ids),
                OpenItem.kind == kind,
                OpenItem.booking_date <= as_of,
                OpenItem.written_off.is_(False),
                OpenItemSettlement.date <= as_of,
            )
        )
        or 0
    )
    return (total - settled).quantize(CENT)


async def platform_credits(
    session: AsyncSession, bank_account_id: uuid.UUID, from_date: date, to_date: date
) -> Decimal:
    return Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
                BankTransaction.property_bank_account_id == bank_account_id,
                BankTransaction.amount > 0,
                BankTransaction.booking_date >= from_date,
                BankTransaction.booking_date <= to_date,
            )
        )
        or 0
    ).quantize(CENT)


# Comparison ----------------------------------------------------------------------------


def _money_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value.quantize(CENT))


def _line(
    prop: str,
    metric: str,
    key: str | None,
    source: Decimal | None,
    platform: Decimal | None,
    hint: str | None = None,
) -> dict[str, Any]:
    difference = (
        (platform - source).quantize(CENT) if source is not None and platform is not None else None
    )
    deviates = difference is None or difference != ZERO
    return {
        "property_number": prop,
        "metric": metric,
        "key": key,
        "source": _money_str(source),
        "platform": _money_str(platform),
        "difference": _money_str(difference),
        "deviates": deviates,
        "hint": hint,
    }


def compare_property(
    prop: str, agg: SourceAggregate, figures: PlatformFigures, credits: dict[str, Decimal]
) -> list[dict[str, Any]]:
    """Builds the comparison lines of one property. ``credits`` holds the platform credits per
    IBAN fingerprint for the source period of that account (read by the caller)."""
    lines: list[dict[str, Any]] = []
    journal = {a: b for (p, a), b in agg.journal.items() if p == prop}
    bank = {i: e for (p, i), e in agg.bank.items() if p == prop}
    if figures.property_id is None:
        missing_property = "Objekt nicht auf der Plattform"
        for account, balance in sorted(journal.items()):
            lines.append(_line(prop, KONTOSALDO, account, balance, None, missing_property))
        for iban, entry in sorted(bank.items()):
            lines.append(
                _line(prop, BANKSTAND, iban[-4:], entry["balance"], None, missing_property)
            )
        return lines

    if journal:
        lines.extend(_compare_journal(prop, journal, figures))

    for iban, entry in sorted(bank.items()):
        print_ = crypto.fingerprint(iban)
        bank_account = figures.bank_accounts.get(print_)
        if bank_account is None:
            candidates = figures.suffixes.get(iban[-4:], [])
            if len(candidates) == 1:
                bank_account = figures.bank_accounts[candidates[0]]
                print_ = candidates[0]
        suffix = iban[-4:]
        if bank_account is None:
            missing = "Bankkonto nicht am Objekt hinterlegt"
            lines.append(_line(prop, BANKSTAND, suffix, entry["balance"], None, missing))
            lines.append(_line(prop, ZAHLUNGEN, suffix, entry["credits"], None, missing))
            continue
        hint: str | None
        source_balance: Decimal
        if entry["balance"] is None:
            source_balance, hint = entry["turnover"], "Quelle ohne Saldo, Summe der Umsätze"
        else:
            source_balance, hint = entry["balance"], None
        platform_balance: Decimal
        if bank_account["statement_balance"] is None:
            platform_balance = bank_account["turnover"]
            no_statement = "Plattform ohne Kontoauszugssaldo, Summe der Umsätze"
            hint = f"{hint}; {no_statement}" if hint else no_statement
        else:
            platform_balance = bank_account["statement_balance"]
        lines.append(_line(prop, BANKSTAND, suffix, source_balance, platform_balance, hint))
        period_hint = None
        if entry["from_date"] is None:
            period_hint = "Quelle ohne Buchungsdatum, Zeitraum unbestimmt"
        lines.append(
            _line(prop, ZAHLUNGEN, suffix, entry["credits"], credits.get(print_), period_hint)
        )
    return lines


def _compare_journal(
    prop: str, journal: dict[str, Decimal], figures: PlatformFigures
) -> list[dict[str, Any]]:
    """Account balances plus the derived figures: debtor balances (debit) are receivables,
    creditor balances (credit, negative in debit minus credit terms) are payables and the
    reserve is the credit balance of the reserve accounts; both shown as positive amounts."""
    lines: list[dict[str, Any]] = []
    no_ledger = "Kein Buchungskreis zum Objekt" if figures.ledgers == 0 else None
    by_category: dict[str, Decimal] = defaultdict(lambda: ZERO)
    unknown_accounts = 0
    for account, balance in sorted(journal.items()):
        platform = figures.accounts.get(account)
        if platform is None:
            unknown_accounts += 1
            unknown = no_ledger or "Konto nicht im Buchungskreis, Kontoart unbekannt"
            lines.append(_line(prop, KONTOSALDO, account, balance, None, unknown))
            continue
        by_category[platform[1]] += balance
        lines.append(_line(prop, KONTOSALDO, account, balance, platform[0]))
    for account, (balance, _) in sorted(figures.accounts.items()):
        if account not in journal and balance != ZERO:
            lines.append(
                _line(prop, KONTOSALDO, account, None, balance, "Konto nicht in der Quelle")
            )
    unknown_hint = (
        f"{unknown_accounts} Quellkonto/-konten ohne Kontoart nicht enthalten"
        if unknown_accounts
        else None
    )
    hint = no_ledger or unknown_hint
    has_ledger = figures.ledgers > 0
    reserve_platform = sum(
        (b for b, c in figures.accounts.values() if c == AccountCategory.RESERVE.value), ZERO
    )
    lines.append(
        _line(
            prop,
            DEBITOREN_OP,
            None,
            by_category[AccountCategory.DEBTOR.value],
            figures.receivables if has_ledger else None,
            hint,
        )
    )
    lines.append(
        _line(
            prop,
            KREDITOREN_OP,
            None,
            -by_category[AccountCategory.CREDITOR.value],
            figures.payables if has_ledger else None,
            hint,
        )
    )
    lines.append(
        _line(
            prop,
            RUECKLAGE,
            None,
            -by_category[AccountCategory.RESERVE.value],
            -reserve_platform if has_ledger else None,
            hint,
        )
    )
    return lines


async def build_report(
    session: AsyncSession,
    sources: list[ImportSourceFile],
    columns: dict[str, dict[str, str]],
    as_of: date | None,
) -> dict[str, Any]:
    """Aggregates the staging rows of ``sources`` and compares them with the platform."""
    rows: list[tuple[ReportType, int, dict[str, Any]]] = []
    for source in sources:
        staged = await session.execute(
            select(StagingRow.row_number, StagingRow.raw)
            .where(StagingRow.source_file_id == source.id)
            .order_by(StagingRow.row_number)
        )
        rows.extend((source.report_type, n, raw) for n, raw in staged.all())
    agg = aggregate_rows(rows, columns, as_of)
    effective_as_of = as_of or agg.max_date or datetime.now(tz=UTC).date()
    lines: list[dict[str, Any]] = []
    properties: list[dict[str, Any]] = []
    for prop in agg.properties:
        figures = await platform_figures(session, prop, effective_as_of)
        credits: dict[str, Decimal] = {}
        for (p, iban), entry in agg.bank.items():
            if p != prop or entry["from_date"] is None:
                continue
            print_ = crypto.fingerprint(iban)
            if print_ not in figures.bank_accounts:
                candidates = figures.suffixes.get(iban[-4:], [])
                if len(candidates) != 1:
                    continue
                print_ = candidates[0]
            credits[print_] = await platform_credits(
                session, figures.bank_accounts[print_]["id"], entry["from_date"], entry["to_date"]
            )
        prop_lines = compare_property(prop, agg, figures, credits)
        lines.extend(prop_lines)
        properties.append(
            {
                "number": prop,
                "name": figures.property_name,
                "on_platform": figures.property_id is not None,
                "compared": len(prop_lines),
                "deviations": sum(1 for line in prop_lines if line["deviates"]),
            }
        )
    return {
        "kind": REPORT_KIND,
        "as_of": effective_as_of.isoformat(),
        "sources": [
            {
                "id": str(s.id),
                "report_type": s.report_type.value,
                "document_id": str(s.document_id),
                "row_count": s.row_count,
            }
            for s in sources
        ],
        "columns": columns,
        "counts": dict(agg.counts),
        "warnings": agg.warnings,
        "totals": {
            "properties": len(properties),
            "compared": len(lines),
            "deviations": sum(1 for line in lines if line["deviates"]),
            "missing_on_platform": sum(1 for p in properties if not p["on_platform"]),
        },
        "properties": properties,
        "lines": lines,
    }


async def latest_sources(session: AsyncSession) -> list[ImportSourceFile]:
    """Newest staged file per reconciled report type."""
    result = []
    for report_type in RECONCILED_TYPES:
        row = await session.scalar(
            select(ImportSourceFile)
            .where(ImportSourceFile.report_type == report_type)
            .order_by(ImportSourceFile.created_at.desc())
            .limit(1)
        )
        if row is not None:
            result.append(row)
    return result


async def create_report(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    *,
    as_of: date | None = None,
    source_file_ids: list[uuid.UUID] | None = None,
    trigger: str = "manual",
) -> ImportRun:
    """Runs the comparison and stores it as import run. Raises when no staged rows exist."""
    if source_file_ids:
        sources = list(
            (
                await session.scalars(
                    select(ImportSourceFile).where(ImportSourceFile.id.in_(source_file_ids))
                )
            ).all()
        )
        if len(sources) != len(set(source_file_ids)):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        wrong = [s for s in sources if s.report_type not in RECONCILED_TYPES]
        if wrong:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Nur Journal und Bankumsätze werden abgeglichen.",
            )
    else:
        sources = await latest_sources(session)
    if not sources:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Keine Rohzeilen (Journal oder Bankumsätze) zum Abgleich vorhanden.",
        )
    columns, _ = await load_columns(session)
    report = await build_report(session, sources, columns, as_of)
    report["trigger"] = trigger
    run = ImportRun(
        tenant_id=tenant_id,
        created_by=user_id,
        source=RECONCILIATION_SOURCE,
        status=ImportStatus.APPLIED,
        document_ids=[s.document_id for s in sources],
        summary=report,
    )
    session.add(run)
    await session.flush()
    return run


# CSV ----------------------------------------------------------------------------------


def format_eur(value: str | None) -> str:
    """``1234.5`` -> ``1.234,50`` (UI format, rule 10); empty for missing values."""
    if value is None:
        return ""
    amount = Decimal(value).quantize(CENT)
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount):.2f}".split(".")
    groups: list[str] = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{sign}{'.'.join(groups)},{cents}"


def report_csv(report: dict[str, Any]) -> str:
    """Semicolon separated, German decimals, UTF-8 with BOM (Excel)."""
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for line in report.get("lines", []):
        writer.writerow(
            [
                line["property_number"],
                line["metric"],
                line.get("key") or "",
                format_eur(line.get("source")),
                format_eur(line.get("platform")),
                format_eur(line.get("difference")),
                "ja" if line["deviates"] else "nein",
                line.get("hint") or "",
            ]
        )
    return buffer.getvalue()
