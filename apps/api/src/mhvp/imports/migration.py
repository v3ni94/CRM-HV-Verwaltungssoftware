"""Switch from Immoware24 without parallel operation (6.9.10, annex D case D11, M8-03, V9).

Four steps per ledger (legal entity, E01) and property:

1. Migration journal: the staged rows of the Immoware24 journal export become
   ``migrated_journal_entry`` and ``migrated_journal_line`` with their original identifiers.
   They are a readable prior period for the statements of the takeover year and are never
   posted into the live journal.
2. Opening balances as of the cut off date, entered by import (balance list) or form by one
   person, released by a second person, posted as one ``EntrySource.migration`` journal
   entry of kind ``opening_balance`` only after the release and only into a ledger whose
   ``migration_cutoff`` equals the cut off date.
3. Reconciliation report per property with zero difference check: Immoware24 balance list
   (the entered balances) against the posted platform balances per account, open items per
   debtor and creditor, bank balance against the imported statement, reserve; the journal
   must be present, balanced and confirmed complete for the year. The report is stored as
   PDF document of the property.
4. Switch of the leading system: requested by one person, decided by another, refused while
   release gate G1 is closed, only with a zero difference report newer than the posting.

Nothing here guesses: an account number without platform account, a missing statement or a
missing journal is a deviation with a German hint, never a filled value (rule 0.1.3).
"""

import io
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as svc
from mhvp.accounting.models import (
    AccountCategory,
    EntryKind,
    EntrySource,
    EntryStatus,
    JournalEntry,
    JournalLine,
    LeadingSystem,
    Ledger,
    LedgerAccount,
    OpenItem,
    OpenItemKind,
    OpenItemSettlement,
)
from mhvp.banking.models import BankStatement
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import (
    ReleaseGate,
    ReleaseGateClosedError,
    ReleaseGateResolver,
    ensure_release_gate_open,
)
from mhvp.imports.fields import parse_date, parse_decimal
from mhvp.imports.migration_models import (
    SOURCE_IMMOWARE24,
    MigratedJournalEntry,
    MigratedJournalLine,
    MigrationOpeningBalance,
    MigrationOpeningBalanceLine,
    MigrationReconciliationReport,
    MigrationSwitchRequest,
    OpeningBalanceKind,
    OpeningBalanceStatus,
    SwitchRequestStatus,
)
from mhvp.imports.models import ImportMapping, ImportSourceFile, ReportType, StagingRow
from mhvp.imports.reconciliation import normalise_account_number, normalise_property_number
from mhvp.properties.models import LegalEntity, Property, PropertyBankAccount

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAPPING_NAME = "Migrationsjournal"
MAX_WARNINGS = 200

# Target fields of the journal export for the migration journal. The headers are an
# assumption (docs/ASSUMPTIONS.md A-047 family) and are saved per tenant as
# ``import_mapping`` (report type journal, name "Migrationsjournal").
JOURNAL_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("entry_id", "Buchungsnummer (Kennung des Buchungssatzes)", True),
    ("property_number", "Objektnummer", True),
    ("account_number", "Kontonummer", True),
    ("booking_date", "Buchungsdatum", True),
    ("amount", "Betrag (Soll positiv)", False),
    ("debit", "Soll", False),
    ("credit", "Haben", False),
    ("text", "Buchungstext", False),
    ("reference", "Referenz", False),
    ("document_ref", "Belegverweis", False),
)
DEFAULT_JOURNAL_COLUMNS: dict[str, str] = {
    "entry_id": "Buchungsnummer",
    "property_number": "Objekt",
    "account_number": "Konto",
    "booking_date": "Datum",
    "amount": "Betrag",
    "debit": "Soll",
    "credit": "Haben",
    "text": "Buchungstext",
    "reference": "Referenz",
    "document_ref": "Beleg",
}
# Metric identifiers of the report lines (labels live in the UI catalogues).
KONTOSALDO = "kontosaldo"
DEBITOREN_OP = "debitoren_op"
KREDITOREN_OP = "kreditoren_op"
BANKSTAND = "bankstand"
RUECKLAGE = "ruecklage"
JOURNAL = "journal"
BALANCE_SHEET = frozenset(
    {
        AccountCategory.BANK,
        AccountCategory.CASH,
        AccountCategory.RESERVE,
        AccountCategory.LOAN,
        AccountCategory.TECHNICAL,
        AccountCategory.DEBTOR,
        AccountCategory.CREDITOR,
        AccountCategory.TRANSIT,
        AccountCategory.TAX,
    }
)
KIND_CATEGORIES: dict[str, frozenset[AccountCategory]] = {
    OpeningBalanceKind.DEBTOR.value: frozenset({AccountCategory.DEBTOR}),
    OpeningBalanceKind.CREDITOR.value: frozenset({AccountCategory.CREDITOR}),
    OpeningBalanceKind.BANK.value: frozenset({AccountCategory.BANK}),
    OpeningBalanceKind.RESERVE.value: frozenset({AccountCategory.RESERVE}),
    OpeningBalanceKind.ACCOUNT.value: frozenset(
        {
            AccountCategory.CASH,
            AccountCategory.LOAN,
            AccountCategory.TECHNICAL,
            AccountCategory.TRANSIT,
            AccountCategory.TAX,
        }
    ),
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT)


def _str(value: Decimal | None) -> str | None:
    return None if value is None else str(_money(value))


# Column configuration -------------------------------------------------------------------


def validate_journal_columns(columns: dict[str, str]) -> dict[str, str]:
    known = {name for name, _, _ in JOURNAL_FIELDS}
    unknown = sorted(set(columns) - known)
    if unknown:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Unbekannte Zielfelder: {', '.join(unknown)}."
        )
    result = {k: v.strip() for k, v in columns.items() if isinstance(v, str) and v.strip()}
    missing = [label for name, label, required in JOURNAL_FIELDS if required and name not in result]
    if missing:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Pflichtfelder ohne Spalte: {', '.join(missing)}."
        )
    if "amount" not in result and ("debit" not in result or "credit" not in result):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Entweder die Spalte Betrag oder die Spalten Soll und Haben sind zuzuordnen.",
        )
    return result


async def load_journal_columns(session: AsyncSession) -> tuple[dict[str, str], bool]:
    row = await session.scalar(
        select(ImportMapping)
        .where(
            ImportMapping.name == MAPPING_NAME,
            ImportMapping.report_type == ReportType.JOURNAL,
            ImportMapping.active.is_(True),
        )
        .order_by(ImportMapping.version.desc())
        .limit(1)
    )
    if row is None:
        return dict(DEFAULT_JOURNAL_COLUMNS), False
    return dict(row.columns), True


async def store_journal_columns(
    session: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID | None, columns: dict[str, str]
) -> dict[str, str]:
    checked = validate_journal_columns(columns)
    previous = (
        await session.scalars(
            select(ImportMapping)
            .where(
                ImportMapping.name == MAPPING_NAME,
                ImportMapping.report_type == ReportType.JOURNAL,
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
            report_type=ReportType.JOURNAL,
            name=MAPPING_NAME,
            version=(previous[0].version + 1) if previous else 1,
            columns=checked,
            value_maps={},
            active=True,
        )
    )
    await session.flush()
    return checked


# Migration journal ----------------------------------------------------------------------


@dataclass
class JournalImportResult:
    ledger_id: uuid.UUID
    year: int
    year_complete: bool
    imported: int = 0
    lines: int = 0
    existing: int = 0
    other_property: int = 0
    other_year: int = 0
    invalid: int = 0
    unmatched_accounts: list[str] = field(default_factory=list)
    unbalanced: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    first_date: date | None = None
    last_date: date | None = None
    debit_total: Decimal = ZERO
    credit_total: Decimal = ZERO

    def warn(self, message: str) -> None:
        self.invalid += 1
        if len(self.warnings) < MAX_WARNINGS:
            self.warnings.append(message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ledger_id": str(self.ledger_id),
            "year": self.year,
            "year_complete": self.year_complete,
            "imported": self.imported,
            "lines": self.lines,
            "existing": self.existing,
            "other_property": self.other_property,
            "other_year": self.other_year,
            "invalid": self.invalid,
            "unmatched_accounts": self.unmatched_accounts,
            "unbalanced": self.unbalanced,
            "warnings": self.warnings,
            "first_date": self.first_date.isoformat() if self.first_date else None,
            "last_date": self.last_date.isoformat() if self.last_date else None,
            "debit_total": _str(self.debit_total),
            "credit_total": _str(self.credit_total),
        }


def _cell(raw: dict[str, Any], columns: dict[str, str], name: str) -> Any:
    column = columns.get(name)
    if not column:
        return None
    value = raw.get(column)
    if isinstance(value, str):
        value = value.strip() or None
    return value


@dataclass
class _ParsedLine:
    entry_id: str
    row_number: int
    day: date
    account: str
    debit: Decimal
    credit: Decimal
    text: str | None
    reference: str | None
    document_ref: str | None
    raw: dict[str, Any]


def parse_journal_row(raw: dict[str, Any], columns: dict[str, str], row_number: int) -> _ParsedLine:
    """One staged row of the journal export as one line; raises ``ValueError`` with a German
    reason when a required value is missing or unreadable."""
    entry_id = _cell(raw, columns, "entry_id")
    if entry_id is None:
        raise ValueError("Buchungsnummer fehlt")
    account = normalise_account_number(_cell(raw, columns, "account_number"))
    if account is None:
        raise ValueError("Kontonummer fehlt")
    raw_day = _cell(raw, columns, "booking_date")
    if raw_day is None:
        raise ValueError("Buchungsdatum fehlt")
    day = parse_date(raw_day)
    amount_cell = _cell(raw, columns, "amount")
    if amount_cell is not None:
        amount = _money(parse_decimal(amount_cell))
        debit, credit = (amount, ZERO) if amount >= 0 else (ZERO, -amount)
    else:
        debit_cell, credit_cell = _cell(raw, columns, "debit"), _cell(raw, columns, "credit")
        if debit_cell is None and credit_cell is None:
            raise ValueError("Betrag fehlt (weder Betrag noch Soll/Haben)")
        debit = _money(parse_decimal(debit_cell)) if debit_cell is not None else ZERO
        credit = _money(parse_decimal(credit_cell)) if credit_cell is not None else ZERO
        if debit < 0 or credit < 0:
            raise ValueError("Soll und Haben dürfen nicht negativ sein")
    if debit == 0 and credit == 0:
        raise ValueError("Betrag ist null")
    text_value = _cell(raw, columns, "text")
    reference = _cell(raw, columns, "reference")
    document_ref = _cell(raw, columns, "document_ref")
    return _ParsedLine(
        entry_id=str(entry_id)[:100],
        row_number=row_number,
        day=day,
        account=account,
        debit=debit,
        credit=credit,
        text=str(text_value)[:500] if text_value is not None else None,
        reference=str(reference)[:100] if reference is not None else None,
        document_ref=str(document_ref)[:200] if document_ref is not None else None,
        raw=raw,
    )


async def ledger_property(session: AsyncSession, ledger: Ledger) -> Property:
    prop = None
    if ledger.property_id is not None:
        prop = await session.get(Property, ledger.property_id)
    if prop is None:
        entity = await session.get(LegalEntity, ledger.legal_entity_id)
        if entity is not None and entity.property_id is not None:
            prop = await session.get(Property, entity.property_id)
    if prop is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Buchungskreis ist keinem Objekt zugeordnet; die Objektnummer der "
            "Exportzeilen kann nicht geprüft werden.",
        )
    return prop


async def import_journal(
    session: AsyncSession,
    ledger: Ledger,
    source_file: ImportSourceFile,
    columns: dict[str, str],
    *,
    year: int,
    year_complete: bool,
    user_id: uuid.UUID | None,
) -> JournalImportResult:
    """Imports the rows of a staged journal export for one ledger and one calendar year.
    Entries already present (same source identifier) are skipped; rows of other properties
    or years are counted, invalid rows are warnings. Nothing is posted."""
    if source_file.report_type is not ReportType.JOURNAL:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Die Datei ist kein Journal-Export (Reporttyp journal)."
        )
    prop = await ledger_property(session, ledger)
    result = JournalImportResult(ledger_id=ledger.id, year=year, year_complete=year_complete)
    accounts: dict[str, uuid.UUID] = {
        str(number): account_id
        for number, account_id in (
            await session.execute(
                select(LedgerAccount.number, LedgerAccount.id).where(
                    LedgerAccount.ledger_id == ledger.id
                )
            )
        ).all()
    }
    existing = set(
        (
            await session.scalars(
                select(MigratedJournalEntry.source_entry_id).where(
                    MigratedJournalEntry.ledger_id == ledger.id,
                    MigratedJournalEntry.source == SOURCE_IMMOWARE24,
                )
            )
        ).all()
    )
    rows = (
        await session.execute(
            select(StagingRow.row_number, StagingRow.raw)
            .where(StagingRow.source_file_id == source_file.id)
            .order_by(StagingRow.row_number)
        )
    ).all()
    grouped: dict[str, list[_ParsedLine]] = defaultdict(list)
    for row_number, raw in rows:
        label = f"Zeile {row_number}"
        number = normalise_property_number(_cell(raw, columns, "property_number"))
        if number is None:
            result.warn(f"{label}: Objektnummer fehlt")
            continue
        if number != prop.number:
            result.other_property += 1
            continue
        try:
            line = parse_journal_row(raw, columns, row_number)
        except ValueError as exc:
            result.warn(f"{label}: {exc}")
            continue
        if line.day.year != year:
            result.other_year += 1
            continue
        grouped[line.entry_id].append(line)
    unmatched: set[str] = set()
    for entry_id, lines in grouped.items():
        if entry_id in existing:
            result.existing += 1
            continue
        days = {line.day for line in lines}
        if len(days) > 1:
            result.warn(f"Buchung {entry_id}: mehrere Buchungsdaten in einem Satz")
            continue
        debit = sum((line.debit for line in lines), ZERO)
        credit = sum((line.credit for line in lines), ZERO)
        if debit != credit:
            result.unbalanced.append(entry_id)
        first = lines[0]
        entry = MigratedJournalEntry(
            tenant_id=ledger.tenant_id,
            created_by=user_id,
            ledger_id=ledger.id,
            source=SOURCE_IMMOWARE24,
            source_entry_id=entry_id,
            source_file_id=source_file.id,
            row_numbers=[line.row_number for line in lines],
            booking_date=first.day,
            fiscal_year=svc.fiscal_year(ledger, first.day),
            text=next((line.text for line in lines if line.text), "") or "",
            reference=first.reference,
            document_ref=next((line.document_ref for line in lines if line.document_ref), None),
            year_complete=year_complete,
            debit_total=debit,
            credit_total=credit,
        )
        session.add(entry)
        await session.flush()
        for no, line in enumerate(lines, start=1):
            account_id = accounts.get(line.account)
            if account_id is None:
                unmatched.add(line.account)
            session.add(
                MigratedJournalLine(
                    tenant_id=ledger.tenant_id,
                    entry_id=entry.id,
                    line_no=no,
                    account_number=line.account,
                    account_id=account_id,
                    debit=line.debit,
                    credit=line.credit,
                    text=line.text,
                    raw=line.raw,
                )
            )
        result.imported += 1
        result.lines += len(lines)
        result.debit_total += debit
        result.credit_total += credit
        result.first_date = (
            first.day if result.first_date is None else min(result.first_date, first.day)
        )
        result.last_date = (
            first.day if result.last_date is None else max(result.last_date, first.day)
        )
    result.unmatched_accounts = sorted(unmatched)
    await session.flush()
    return result


async def journal_summary(session: AsyncSession, ledger_id: uuid.UUID) -> dict[str, Any]:
    row = (
        await session.execute(
            select(
                func.count(MigratedJournalEntry.id),
                func.coalesce(func.sum(MigratedJournalEntry.debit_total), 0),
                func.coalesce(func.sum(MigratedJournalEntry.credit_total), 0),
                func.min(MigratedJournalEntry.booking_date),
                func.max(MigratedJournalEntry.booking_date),
                func.bool_and(MigratedJournalEntry.year_complete),
                func.bool_and(MigratedJournalEntry.reconciled),
            ).where(MigratedJournalEntry.ledger_id == ledger_id)
        )
    ).one()
    count = int(row[0] or 0)
    return {
        "entries": count,
        "debit_total": _str(Decimal(row[1])),
        "credit_total": _str(Decimal(row[2])),
        "first_date": row[3].isoformat() if row[3] else None,
        "last_date": row[4].isoformat() if row[4] else None,
        "year_complete": bool(row[5]) if count else False,
        "reconciled": bool(row[6]) if count else False,
    }


# Opening balances -----------------------------------------------------------------------


@dataclass(frozen=True)
class BalanceIn:
    kind: str
    account_id: uuid.UUID
    amount: Decimal
    text: str | None = None
    property_bank_account_id: uuid.UUID | None = None
    due_date: date | None = None


async def _balance_set(
    session: AsyncSession, ledger: Ledger, cutoff: date, *, lock: bool = False
) -> MigrationOpeningBalance | None:
    query = select(MigrationOpeningBalance).where(
        MigrationOpeningBalance.ledger_id == ledger.id,
        MigrationOpeningBalance.cutoff_date == cutoff,
    )
    if lock:
        query = query.with_for_update()
    result: MigrationOpeningBalance | None = await session.scalar(query)
    return result


async def save_opening_balances(
    session: AsyncSession,
    ledger: Ledger,
    cutoff: date,
    balances: list[BalanceIn],
    *,
    user_id: uuid.UUID | None,
    entered_via: str,
    note: str | None,
    source_file_id: uuid.UUID | None = None,
) -> MigrationOpeningBalance:
    """Creates or replaces the draft of a ledger and cut off date. A released or posted set is
    immutable (release again after every change would be pointless otherwise)."""
    if not balances:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Mindestens ein Saldo ist anzugeben.")
    accounts = {
        a.id: a
        for a in (
            await session.scalars(select(LedgerAccount).where(LedgerAccount.ledger_id == ledger.id))
        ).all()
    }
    seen: set[uuid.UUID] = set()
    for i, b in enumerate(balances, start=1):
        account = accounts.get(b.account_id)
        if account is None:
            raise ProblemError(
                ErrorCodes.ACC_WRONG_ENTITY,
                detail=f"Saldo {i}: Konto gehört nicht zu diesem Buchungskreis.",
            )
        if b.kind not in KIND_CATEGORIES:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Saldo {i}: Art {b.kind!r} unbekannt."
            )
        if account.category not in KIND_CATEGORIES[b.kind]:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"Saldo {i}: Konto {account.number} ({account.category.value}) passt nicht "
                    f"zur Art {b.kind}."
                ),
            )
        amount = _money(b.amount)
        if amount == 0:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Saldo {i}: Betrag ist null.")
        if abs(amount) != abs(b.amount):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Saldo {i}: Betrag hat mehr als zwei Nachkommastellen.",
            )
        if b.account_id in seen:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Saldo {i}: Konto {account.number} doppelt."
            )
        seen.add(b.account_id)
        if b.kind == OpeningBalanceKind.BANK.value and b.property_bank_account_id is not None:
            bank = await session.get(PropertyBankAccount, b.property_bank_account_id)
            if bank is None or bank.legal_entity_id != ledger.legal_entity_id:
                raise ProblemError(
                    ErrorCodes.ACC_WRONG_ENTITY,
                    detail=f"Saldo {i}: Bankkonto gehört nicht zu diesem Rechtsträger.",
                )
    current = await _balance_set(session, ledger, cutoff, lock=True)
    if current is not None and current.status != OpeningBalanceStatus.DRAFT.value:
        raise ProblemError(
            ErrorCodes.MIG_STATE,
            detail="Die Eröffnungssalden sind bereits freigegeben oder gebucht und werden nicht "
            "mehr geändert.",
        )
    if current is None:
        current = MigrationOpeningBalance(
            tenant_id=ledger.tenant_id,
            created_by=user_id,
            ledger_id=ledger.id,
            cutoff_date=cutoff,
            status=OpeningBalanceStatus.DRAFT.value,
        )
        session.add(current)
        await session.flush()
    else:
        for old in (
            await session.scalars(
                select(MigrationOpeningBalanceLine).where(
                    MigrationOpeningBalanceLine.opening_balance_id == current.id
                )
            )
        ).all():
            await session.delete(old)
        await session.flush()
        # A changed draft belongs to the person who changed it (release by someone else).
        current.created_by = user_id
    current.entered_via = entered_via
    current.note = note
    current.source_file_id = source_file_id
    current.updated_by = user_id
    for b in balances:
        session.add(
            MigrationOpeningBalanceLine(
                tenant_id=ledger.tenant_id,
                opening_balance_id=current.id,
                kind=b.kind,
                account_id=b.account_id,
                amount=_money(b.amount),
                text=b.text,
                property_bank_account_id=(
                    b.property_bank_account_id if b.kind == OpeningBalanceKind.BANK.value else None
                ),
                due_date=b.due_date,
            )
        )
    await session.flush()
    return current


async def balance_lines(
    session: AsyncSession, balance_id: uuid.UUID
) -> list[tuple[MigrationOpeningBalanceLine, LedgerAccount]]:
    rows = (
        await session.execute(
            select(MigrationOpeningBalanceLine, LedgerAccount)
            .join(LedgerAccount, LedgerAccount.id == MigrationOpeningBalanceLine.account_id)
            .where(MigrationOpeningBalanceLine.opening_balance_id == balance_id)
            .order_by(LedgerAccount.number)
        )
    ).all()
    return [(line, account) for line, account in rows]


def _four_eyes(actor: uuid.UUID | None, author: uuid.UUID | None, is_platform_admin: bool) -> None:
    if actor is None or actor == author or is_platform_admin:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person vornehmen."
        )


async def release_opening_balances(
    session: AsyncSession,
    balance: MigrationOpeningBalance,
    *,
    user_id: uuid.UUID | None,
    is_platform_admin: bool,
    comment: str | None,
) -> MigrationOpeningBalance:
    if balance.status != OpeningBalanceStatus.DRAFT.value:
        raise ProblemError(
            ErrorCodes.MIG_STATE,
            detail="Nur ein Entwurf der Eröffnungssalden kann freigegeben werden.",
        )
    _four_eyes(user_id, balance.created_by, is_platform_admin)
    balance.status = OpeningBalanceStatus.RELEASED.value
    balance.released_by, balance.released_at = user_id, datetime.now(UTC)
    balance.release_comment = comment
    balance.updated_by = user_id
    await emit(
        session,
        tenant_id=balance.tenant_id,
        type="migration.opening_balances_released",
        entity_type="migration_opening_balance",
        entity_id=balance.id,
        actor_user_id=user_id,
        payload={
            "ledger_id": str(balance.ledger_id),
            "cutoff_date": balance.cutoff_date.isoformat(),
        },
    )
    await session.flush()
    return balance


async def _opening_account(session: AsyncSession, ledger: Ledger) -> LedgerAccount:
    account = await session.scalar(
        select(LedgerAccount)
        .where(
            LedgerAccount.ledger_id == ledger.id,
            LedgerAccount.category == AccountCategory.OPENING_BALANCE,
            LedgerAccount.active.is_(True),
        )
        .order_by(LedgerAccount.number)
        .limit(1)
    )
    if account is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Buchungskreis hat kein Anfangsbestandskonto (Kontoart opening_balance).",
        )
    return account


async def _contract_for_account(
    session: AsyncSession, account: LedgerAccount, as_of: date
) -> uuid.UUID | None:
    """Contract behind a person account: the account's own contract, else the contract of
    its party and unit valid on ``as_of`` (debtor accounts of M5 carry party and unit)."""
    from mhvp.contracts.models import Contract

    if account.contract_id is not None:
        return account.contract_id
    if account.party_id is None or account.unit_id is None:
        return None
    result: uuid.UUID | None = await session.scalar(
        select(Contract.id)
        .where(
            Contract.party_id == account.party_id,
            Contract.unit_id == account.unit_id,
            Contract.start_date <= as_of,
            (Contract.end_date.is_(None)) | (Contract.end_date >= as_of),
        )
        .order_by(Contract.start_date.desc())
        .limit(1)
    )
    return result


async def post_opening_balances(
    session: AsyncSession,
    ledger: Ledger,
    balance: MigrationOpeningBalance,
    *,
    user_id: uuid.UUID | None,
) -> JournalEntry:
    """Posts the released balances as one journal entry (kind opening_balance, source
    migration) dated on the cut off date. Requires the ledger's cut off date to be set and
    equal to the balances' date; the second person's release counts as the four eyes check
    of ``svc.post``. Open items of debtors and creditors carry the contract of the account."""
    if balance.status == OpeningBalanceStatus.POSTED.value:
        raise ProblemError(
            ErrorCodes.MIG_STATE, detail="Die Eröffnungssalden sind bereits gebucht."
        )
    if balance.status != OpeningBalanceStatus.RELEASED.value:
        raise ProblemError(
            ErrorCodes.MIG_STATE,
            detail="Die Eröffnungssalden sind nicht freigegeben; die Freigabe durch eine zweite "
            "Person fehlt.",
        )
    if ledger.migration_cutoff is None:
        raise ProblemError(
            ErrorCodes.MIG_CUTOFF_MISSING,
            detail="Der Migrationsstichtag des Buchungskreises ist nicht gesetzt.",
        )
    if ledger.migration_cutoff != balance.cutoff_date:
        raise ProblemError(
            ErrorCodes.MIG_CUTOFF_MISSING,
            detail=(
                f"Der Migrationsstichtag des Buchungskreises ({ledger.migration_cutoff:%d.%m.%Y}) "
                f"weicht vom Stichtag der Eröffnungssalden ({balance.cutoff_date:%d.%m.%Y}) ab."
            ),
        )
    rows = await balance_lines(session, balance.id)
    lines: list[svc.LineIn] = []
    net = ZERO
    for line, account in rows:
        amount = _money(line.amount)
        net += amount
        lines.append(
            svc.LineIn(
                account_id=account.id,
                debit=amount if amount > 0 else ZERO,
                credit=-amount if amount < 0 else ZERO,
                text=line.text or f"Anfangsbestand {account.number} {account.name}"[:500],
            )
        )
    if net != 0:
        counter = await _opening_account(session, ledger)
        lines.append(
            svc.LineIn(
                account_id=counter.id,
                debit=-net if net < 0 else ZERO,
                credit=net if net > 0 else ZERO,
                text="Gegenbuchung Anfangsbestand",
            )
        )
    entry = JournalEntry(
        tenant_id=ledger.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        booking_date=balance.cutoff_date,
        text=f"Anfangsbestände Migration Immoware24 zum {balance.cutoff_date:%d.%m.%Y}",
        kind=EntryKind.OPENING_BALANCE,
        source=EntrySource.MIGRATION,
        reference=f"migration:{balance.id}",
        idempotency_key=f"migration-opening-{balance.id}",
        approved_by=balance.released_by,
    )
    await svc.write_draft(session, ledger, entry, lines, [])
    await svc.post(session, ledger, entry, user_id)
    # Open items per debtor and creditor: the contract of the person account (7.3).
    for line, account in rows:
        item = await session.scalar(
            select(OpenItem).where(
                OpenItem.journal_entry_id == entry.id, OpenItem.account_id == account.id
            )
        )
        if item is None:
            continue
        item.contract_id = await _contract_for_account(session, account, balance.cutoff_date)
        if line.due_date is not None:
            item.due_date = line.due_date
    balance.status = OpeningBalanceStatus.POSTED.value
    balance.posted_at, balance.posted_by = datetime.now(UTC), user_id
    balance.journal_entry_id = entry.id
    balance.updated_by = user_id
    await emit(
        session,
        tenant_id=ledger.tenant_id,
        type="migration.opening_balances_posted",
        entity_type="migration_opening_balance",
        entity_id=balance.id,
        actor_user_id=user_id,
        payload={"ledger_id": str(ledger.id), "journal_entry_id": str(entry.id)},
    )
    await session.flush()
    return entry


# Reconciliation --------------------------------------------------------------------------


def _line(
    ledger: Ledger,
    metric: str,
    key: str,
    label: str,
    source: Decimal | None,
    platform: Decimal | None,
    hint: str | None = None,
) -> dict[str, Any]:
    difference = None if source is None or platform is None else _money(platform - source)
    deviates = difference is None or difference != 0
    return {
        "ledger_id": str(ledger.id),
        "metric": metric,
        "key": key,
        "label": label,
        "source": _str(source),
        "platform": _str(platform),
        "difference": _str(difference),
        "deviates": deviates,
        "hint": hint,
    }


async def _account_balances(
    session: AsyncSession, ledger: Ledger, as_of: date
) -> dict[uuid.UUID, Decimal]:
    rows = (
        await session.execute(
            select(
                JournalLine.account_id,
                func.coalesce(func.sum(JournalLine.debit), 0),
                func.coalesce(func.sum(JournalLine.credit), 0),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date <= as_of,
            )
            .group_by(JournalLine.account_id)
        )
    ).all()
    return {account_id: _money(Decimal(d) - Decimal(c)) for account_id, d, c in rows}


async def _open_amount(
    session: AsyncSession, ledger: Ledger, account_id: uuid.UUID, kind: OpenItemKind, as_of: date
) -> Decimal:
    total = Decimal(
        await session.scalar(
            select(func.coalesce(func.sum(OpenItem.amount), 0)).where(
                OpenItem.ledger_id == ledger.id,
                OpenItem.account_id == account_id,
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
                OpenItem.ledger_id == ledger.id,
                OpenItem.account_id == account_id,
                OpenItem.kind == kind,
                OpenItem.booking_date <= as_of,
                OpenItem.written_off.is_(False),
                OpenItemSettlement.date <= as_of,
            )
        )
        or 0
    )
    return _money(total - settled)


async def _statement_balance(
    session: AsyncSession, bank_account_id: uuid.UUID, as_of: date
) -> tuple[Decimal | None, date | None]:
    row = (
        await session.execute(
            select(BankStatement.closing_balance, BankStatement.closing_date, BankStatement.to_date)
            .where(
                BankStatement.property_bank_account_id == bank_account_id,
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
    if row is None:
        return None, None
    return _money(Decimal(row[0])), row[1] or row[2]


async def _ledger_lines(session: AsyncSession, ledger: Ledger, as_of: date) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    balance = await _balance_set(session, ledger, as_of)
    if balance is None:
        lines.append(
            _line(
                ledger,
                KONTOSALDO,
                "*",
                "Eröffnungssalden",
                None,
                None,
                "Keine Eröffnungssalden zu diesem Stichtag erfasst",
            )
        )
    elif balance.status != OpeningBalanceStatus.POSTED.value:
        lines.append(
            _line(
                ledger,
                KONTOSALDO,
                "*",
                "Eröffnungssalden",
                None,
                None,
                "Eröffnungssalden nicht gebucht (Status " + balance.status + ")",
            )
        )
    else:
        balances = await _account_balances(session, ledger, as_of)
        bank_accounts = {
            b.id: b
            for b in (
                await session.scalars(
                    select(PropertyBankAccount).where(
                        PropertyBankAccount.legal_entity_id == ledger.legal_entity_id
                    )
                )
            ).all()
        }
        for line, account in await balance_lines(session, balance.id):
            source = _money(line.amount)
            label = f"{account.number} {account.name}"
            platform = balances.get(account.id, ZERO)
            if line.kind == OpeningBalanceKind.DEBTOR.value:
                open_amount = await _open_amount(
                    session, ledger, account.id, OpenItemKind.RECEIVABLE, as_of
                )
                lines.append(
                    _line(ledger, DEBITOREN_OP, account.number, label, source, open_amount)
                )
            elif line.kind == OpeningBalanceKind.CREDITOR.value:
                open_amount = await _open_amount(
                    session, ledger, account.id, OpenItemKind.PAYABLE, as_of
                )
                lines.append(
                    _line(ledger, KREDITOREN_OP, account.number, label, -source, open_amount)
                )
            elif line.kind == OpeningBalanceKind.RESERVE.value:
                lines.append(_line(ledger, RUECKLAGE, account.number, label, -source, -platform))
            elif line.kind == OpeningBalanceKind.BANK.value:
                lines.append(_line(ledger, KONTOSALDO, account.number, label, source, platform))
                bank = (
                    bank_accounts.get(line.property_bank_account_id)
                    if line.property_bank_account_id
                    else None
                )
                if bank is None and account.property_bank_account_id is not None:
                    bank = bank_accounts.get(account.property_bank_account_id)
                if bank is None:
                    lines.append(
                        _line(
                            ledger,
                            BANKSTAND,
                            account.number,
                            label,
                            source,
                            None,
                            "Kein Bankkonto des Objekts zugeordnet",
                        )
                    )
                else:
                    closing, day = await _statement_balance(session, bank.id, as_of)
                    hint = None
                    if closing is None:
                        hint = "Kein Kontoauszug mit Schlusssaldo bis zum Stichtag eingelesen"
                    elif day is not None and day != as_of:
                        hint = f"Schlusssaldo vom {day:%d.%m.%Y}"
                    lines.append(
                        _line(
                            ledger, BANKSTAND, f"…{bank.iban_suffix}", label, source, closing, hint
                        )
                    )
            else:
                lines.append(_line(ledger, KONTOSALDO, account.number, label, source, platform))
    journal = await journal_summary(session, ledger.id)
    if journal["entries"] == 0:
        lines.append(
            _line(
                ledger,
                JOURNAL,
                str(as_of.year),
                "Migrationsjournal",
                None,
                None,
                "Kein Migrationsjournal für diesen Buchungskreis eingelesen",
            )
        )
    else:
        hint = None if journal["year_complete"] else "Jahresvollständigkeit nicht bestätigt"
        source = Decimal(journal["debit_total"] or "0")
        platform = Decimal(journal["credit_total"] or "0")
        journal_line = _line(
            ledger,
            JOURNAL,
            str(as_of.year),
            "Migrationsjournal Soll gegen Haben",
            source,
            platform,
            hint,
        )
        if hint is not None:
            journal_line["deviates"] = True
        lines.append(journal_line)
    return lines


async def build_report(session: AsyncSession, prop: Property, as_of: date) -> dict[str, Any]:
    ledgers = (
        await session.scalars(
            select(Ledger)
            .join(LegalEntity, LegalEntity.id == Ledger.legal_entity_id)
            .where((Ledger.property_id == prop.id) | (LegalEntity.property_id == prop.id))
            .order_by(Ledger.name)
        )
    ).all()
    lines: list[dict[str, Any]] = []
    ledger_info = []
    for ledger in ledgers:
        ledger_lines = await _ledger_lines(session, ledger, as_of)
        lines.extend(ledger_lines)
        ledger_info.append(
            {
                "id": str(ledger.id),
                "name": ledger.name,
                "leading_system": ledger.leading_system.value,
                "migration_cutoff": (
                    ledger.migration_cutoff.isoformat() if ledger.migration_cutoff else None
                ),
                "cutoff_matches": ledger.migration_cutoff == as_of,
                "deviations": sum(1 for line in ledger_lines if line["deviates"]),
            }
        )
        if ledger.migration_cutoff != as_of:
            lines.append(
                _line(
                    ledger,
                    KONTOSALDO,
                    "stichtag",
                    "Migrationsstichtag",
                    None,
                    None,
                    "Migrationsstichtag des Buchungskreises fehlt oder weicht ab",
                )
            )
    if not ledgers:
        lines.append(
            {
                "ledger_id": None,
                "metric": KONTOSALDO,
                "key": "*",
                "label": "Buchungskreis",
                "source": None,
                "platform": None,
                "difference": None,
                "deviates": True,
                "hint": "Kein Buchungskreis für dieses Objekt",
            }
        )
    deviations = sum(1 for line in lines if line["deviates"])
    total = sum((abs(Decimal(line["difference"])) for line in lines if line["difference"]), ZERO)
    return {
        "property_id": str(prop.id),
        "property_number": prop.number,
        "property_name": prop.name,
        "as_of": as_of.isoformat(),
        "ledgers": ledger_info,
        "lines": lines,
        "compared": len(lines),
        "deviations": deviations,
        "total_difference": _str(total),
        "zero_difference": deviations == 0,
    }


def _esc(value: Any) -> str:
    return re.sub(
        r"[&<>]", lambda m: {"&": "&amp;", "<": "&lt;", ">": "&gt;"}[m.group()], str(value)
    )


def format_eur(value: str | None) -> str:
    if value is None:
        return "nicht vorhanden"
    amount = Decimal(value)
    sign = "-" if amount < 0 else ""
    whole, frac = f"{abs(amount):.2f}".split(".")
    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}{'.'.join(groups)},{frac} EUR"


METRIC_LABELS = {
    KONTOSALDO: "Kontosaldo",
    DEBITOREN_OP: "Offene Posten Debitor",
    KREDITOREN_OP: "Offene Posten Kreditor",
    BANKSTAND: "Bankstand gegen Kontoauszug",
    RUECKLAGE: "Rücklage",
    JOURNAL: "Migrationsjournal",
}


def report_pdf(report: dict[str, Any], tenant_name: str, created_at: datetime) -> bytes:
    """Reconciliation report as PDF (internal working paper without letterhead)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12)
    head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=13, leading=16)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Abgleichbericht Migration Immoware24",
    )
    as_of = date.fromisoformat(report["as_of"])
    result = (
        "Nulldifferenz" if report["zero_difference"] else f"{report['deviations']} Abweichungen"
    )
    story: list[Any] = [
        Paragraph("Abgleichbericht Migration Immoware24", head),
        Paragraph(
            _esc(
                f"Mandant {tenant_name}, Objekt {report['property_number']} "
                f"{report['property_name']}, Stichtag {as_of:%d.%m.%Y}, erstellt "
                f"{created_at:%d.%m.%Y %H:%M} UTC, Ergebnis: {result}, Summe der Differenzen "
                f"{format_eur(report['total_difference'])}"
            ),
            body,
        ),
        Spacer(1, 4 * mm),
    ]
    grid = TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, "#808080"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (3, 1), (5, -1), "RIGHT"),
        ]
    )
    rows: list[list[Any]] = [
        ["Kennzahl", "Schlüssel", "Bezeichnung", "Immoware24", "Plattform", "Differenz", "Hinweis"]
    ]
    for line in report["lines"]:
        rows.append(
            [
                METRIC_LABELS.get(line["metric"], line["metric"]),
                line["key"],
                Paragraph(_esc(line["label"]), body),
                format_eur(line["source"]),
                format_eur(line["platform"]),
                format_eur(line["difference"]) if line["difference"] is not None else "",
                Paragraph(_esc(line["hint"] or ("Abweichung" if line["deviates"] else "")), body),
            ]
        )
    table = Table(rows, colWidths=[28 * mm, 16 * mm, 40 * mm, 24 * mm, 24 * mm, 20 * mm, 22 * mm])
    table.setStyle(grid)
    story.append(table)
    doc.build(story)
    return buf.getvalue()


async def store_report(
    session: AsyncSession,
    prop: Property,
    report: dict[str, Any],
    *,
    user_id: uuid.UUID | None,
) -> MigrationReconciliationReport:
    row = MigrationReconciliationReport(
        tenant_id=prop.tenant_id,
        created_by=user_id,
        property_id=prop.id,
        as_of=date.fromisoformat(report["as_of"]),
        zero_difference=report["zero_difference"],
        compared=report["compared"],
        deviations=report["deviations"],
        total_difference=Decimal(report["total_difference"] or "0"),
        lines=report["lines"],
        summary={k: v for k, v in report.items() if k != "lines"},
    )
    session.add(row)
    await session.flush()
    if report["zero_difference"]:
        # Reconciliation marker of the migrated journal (Überleitungskennzeichen, 6.9.10).
        ledger_ids = [uuid.UUID(info["id"]) for info in report["ledgers"]]
        for entry in (
            await session.scalars(
                select(MigratedJournalEntry).where(MigratedJournalEntry.ledger_id.in_(ledger_ids))
            )
        ).all():
            entry.reconciled = True
            entry.reconciled_report_id = row.id
    await session.flush()
    return row


async def latest_report(
    session: AsyncSession, property_id: uuid.UUID
) -> MigrationReconciliationReport | None:
    result: MigrationReconciliationReport | None = await session.scalar(
        select(MigrationReconciliationReport)
        .where(MigrationReconciliationReport.property_id == property_id)
        .order_by(MigrationReconciliationReport.created_at.desc())
        .limit(1)
    )
    return result


# Switch of the leading system -----------------------------------------------------------


def g1_closed_error() -> ProblemError:
    return ProblemError(
        ErrorCodes.RELEASE_GATE_CLOSED,
        detail=(
            "Der Wechsel des führenden Systems auf die Plattform erfordert die Freigabestufe G1 "
            "(Produktive Buchführung). G1 ist für diesen Mandanten nicht freigegeben; der "
            "Buchungskreis bleibt bei Immoware24 führend."
        ),
        developer_message="Release gate G1 is closed for this tenant; leading system unchanged.",
        extensions={"gate": ReleaseGate.G1.value},
    )


async def ensure_g1(tenant_id: uuid.UUID, resolver: ReleaseGateResolver) -> None:
    try:
        await ensure_release_gate_open(ReleaseGate.G1, tenant_id, resolver)
    except ReleaseGateClosedError:
        raise g1_closed_error() from None


async def ensure_switchable(session: AsyncSession, ledger: Ledger) -> MigrationReconciliationReport:
    """The report the switch relies on: zero difference, dated on the ledger's cut off date
    and newer than the posted opening balances."""
    if ledger.leading_system is LeadingSystem.MHVP:
        raise ProblemError(ErrorCodes.MIG_STATE, detail="Die Plattform ist bereits führend.")
    if ledger.migration_cutoff is None:
        raise ProblemError(
            ErrorCodes.MIG_CUTOFF_MISSING,
            detail="Der Migrationsstichtag des Buchungskreises ist nicht gesetzt.",
        )
    balance = await _balance_set(session, ledger, ledger.migration_cutoff)
    if balance is None or balance.status != OpeningBalanceStatus.POSTED.value:
        raise ProblemError(
            ErrorCodes.MIG_NOT_RECONCILED,
            detail="Die Eröffnungssalden zum Migrationsstichtag sind nicht gebucht.",
        )
    prop = await ledger_property(session, ledger)
    report = await latest_report(session, prop.id)
    if report is None or report.as_of != ledger.migration_cutoff:
        raise ProblemError(
            ErrorCodes.MIG_NOT_RECONCILED,
            detail="Für das Objekt fehlt ein Abgleichbericht zum Migrationsstichtag.",
        )
    if balance.posted_at is not None and report.created_at < balance.posted_at:
        raise ProblemError(
            ErrorCodes.MIG_NOT_RECONCILED,
            detail="Der Abgleichbericht ist älter als die Buchung der Eröffnungssalden; "
            "Abgleich erneut ausführen.",
        )
    if not report.zero_difference:
        raise ProblemError(
            ErrorCodes.MIG_NOT_RECONCILED,
            detail=(
                f"Der letzte Abgleichbericht weist {report.deviations} Abweichungen aus "
                f"(Summe {format_eur(str(report.total_difference))}); der Wechsel ist erst bei "
                "Nulldifferenz möglich."
            ),
        )
    return report


async def request_switch(
    session: AsyncSession,
    ledger: Ledger,
    resolver: ReleaseGateResolver,
    *,
    user_id: uuid.UUID | None,
    comment: str | None,
) -> MigrationSwitchRequest:
    if user_id is None:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES,
            detail="Der Antrag muss von einer angemeldeten Person kommen.",
        )
    await ensure_g1(ledger.tenant_id, resolver)
    report = await ensure_switchable(session, ledger)
    pending = await session.scalar(
        select(MigrationSwitchRequest).where(
            MigrationSwitchRequest.ledger_id == ledger.id,
            MigrationSwitchRequest.status == SwitchRequestStatus.REQUESTED.value,
        )
    )
    if pending is not None:
        raise ProblemError(
            ErrorCodes.MIG_STATE, detail="Für diesen Buchungskreis wartet bereits ein Antrag."
        )
    item = MigrationSwitchRequest(
        tenant_id=ledger.tenant_id,
        created_by=user_id,
        ledger_id=ledger.id,
        report_id=report.id,
        comment=comment,
        requested_by=user_id,
    )
    session.add(item)
    await emit(
        session,
        tenant_id=ledger.tenant_id,
        type="migration.switch_requested",
        entity_type="migration_switch_request",
        entity_id=item.id,
        actor_user_id=user_id,
        payload={"ledger_id": str(ledger.id), "report_id": str(report.id)},
    )
    await session.flush()
    return item


async def decide_switch(
    session: AsyncSession,
    ledger: Ledger,
    item: MigrationSwitchRequest,
    resolver: ReleaseGateResolver,
    *,
    approve: bool,
    user_id: uuid.UUID | None,
    is_platform_admin: bool,
    comment: str | None,
) -> MigrationSwitchRequest:
    if item.status != SwitchRequestStatus.REQUESTED.value:
        raise ProblemError(ErrorCodes.MIG_STATE, detail="Der Antrag ist bereits entschieden.")
    _four_eyes(user_id, item.requested_by, is_platform_admin)
    if approve:
        await ensure_g1(ledger.tenant_id, resolver)
        report = await ensure_switchable(session, ledger)
        if report.id != item.report_id:
            raise ProblemError(
                ErrorCodes.MIG_NOT_RECONCILED,
                detail="Seit dem Antrag liegt ein neuerer Abgleichbericht vor; den Antrag erneut "
                "stellen.",
            )
        ledger.leading_system = LeadingSystem.MHVP
        ledger.updated_by = user_id
    item.status = (
        SwitchRequestStatus.APPROVED.value if approve else SwitchRequestStatus.REJECTED.value
    )
    item.decided_by, item.decided_at = user_id, datetime.now(UTC)
    item.decision_comment = comment
    item.updated_by = user_id
    await emit(
        session,
        tenant_id=ledger.tenant_id,
        type="migration.switch_approved" if approve else "migration.switch_rejected",
        entity_type="migration_switch_request",
        entity_id=item.id,
        actor_user_id=user_id,
        payload={"ledger_id": str(ledger.id), "leading_system": ledger.leading_system.value},
        changes={"status": {"old": "requested", "new": item.status}},
    )
    await session.flush()
    return item


# Status per property ---------------------------------------------------------------------


async def migration_status(
    session: AsyncSession, allowed: frozenset[uuid.UUID] | None
) -> list[dict[str, Any]]:
    """Per property with at least one ledger: the migration steps of every ledger."""
    rows = (
        await session.execute(
            select(Ledger, LegalEntity, Property)
            .join(LegalEntity, LegalEntity.id == Ledger.legal_entity_id)
            .join(
                Property,
                (Property.id == Ledger.property_id) | (Property.id == LegalEntity.property_id),
            )
            .order_by(Property.number, Ledger.name)
        )
    ).all()
    latest_balance = {
        b.ledger_id: b
        for b in (
            await session.scalars(
                select(MigrationOpeningBalance).order_by(MigrationOpeningBalance.cutoff_date)
            )
        ).all()
    }
    journal_counts: dict[uuid.UUID, int] = {
        ledger_id: int(count)
        for ledger_id, count in (
            await session.execute(
                select(
                    MigratedJournalEntry.ledger_id, func.count(MigratedJournalEntry.id)
                ).group_by(MigratedJournalEntry.ledger_id)
            )
        ).all()
    }
    pending = {
        r.ledger_id: r
        for r in (
            await session.scalars(
                select(MigrationSwitchRequest).where(
                    MigrationSwitchRequest.status == SwitchRequestStatus.REQUESTED.value
                )
            )
        ).all()
    }
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for ledger, entity, prop in rows:
        if allowed is not None and entity.id not in allowed:
            continue
        item = out.setdefault(
            prop.id,
            {
                "property_id": str(prop.id),
                "property_number": prop.number,
                "property_name": prop.name,
                "ledgers": [],
                "report": None,
            },
        )
        if item["report"] is None:
            report = await latest_report(session, prop.id)
            if report is not None:
                item["report"] = {
                    "id": str(report.id),
                    "created_at": report.created_at.isoformat(),
                    "as_of": report.as_of.isoformat(),
                    "zero_difference": report.zero_difference,
                    "deviations": report.deviations,
                    "document_id": str(report.document_id) if report.document_id else None,
                }
        balance = latest_balance.get(ledger.id)
        req = pending.get(ledger.id)
        item["ledgers"].append(
            {
                "id": str(ledger.id),
                "name": ledger.name,
                "legal_entity_id": str(entity.id),
                "legal_entity_kind": entity.kind.value,
                "leading_system": ledger.leading_system.value,
                "migration_cutoff": (
                    ledger.migration_cutoff.isoformat() if ledger.migration_cutoff else None
                ),
                "journal_entries": int(journal_counts.get(ledger.id, 0)),
                "journal_imported": int(journal_counts.get(ledger.id, 0)) > 0,
                "opening_balance_id": str(balance.id) if balance else None,
                "opening_balances_status": balance.status if balance else None,
                "opening_balances_entered": balance is not None,
                "released": balance is not None
                and balance.status
                in (OpeningBalanceStatus.RELEASED.value, OpeningBalanceStatus.POSTED.value),
                "posted": balance is not None
                and balance.status == OpeningBalanceStatus.POSTED.value,
                "reconciled": bool(
                    item["report"]
                    and item["report"]["zero_difference"]
                    and ledger.migration_cutoff is not None
                    and item["report"]["as_of"] == ledger.migration_cutoff.isoformat()
                ),
                "switched": ledger.leading_system is LeadingSystem.MHVP,
                "switch_request_id": str(req.id) if req else None,
            }
        )
    return list(out.values())


# Balance list import (CSV) ---------------------------------------------------------------

BALANCE_LIST_COLUMNS: dict[str, tuple[str, ...]] = {
    "Konto": ("Konto", "Kontonummer", "Konto-Nr", "Sachkonto", "Personenkonto"),
    "Saldo": ("Saldo", "Betrag", "Saldo EUR"),
}
BALANCE_TEXT_COLUMNS = ("Bezeichnung", "Text", "Name", "Kontobezeichnung")
CATEGORY_KIND: dict[AccountCategory, str] = {
    AccountCategory.DEBTOR: OpeningBalanceKind.DEBTOR.value,
    AccountCategory.CREDITOR: OpeningBalanceKind.CREDITOR.value,
    AccountCategory.BANK: OpeningBalanceKind.BANK.value,
    AccountCategory.RESERVE: OpeningBalanceKind.RESERVE.value,
    AccountCategory.CASH: OpeningBalanceKind.ACCOUNT.value,
    AccountCategory.LOAN: OpeningBalanceKind.ACCOUNT.value,
    AccountCategory.TECHNICAL: OpeningBalanceKind.ACCOUNT.value,
    AccountCategory.TRANSIT: OpeningBalanceKind.ACCOUNT.value,
    AccountCategory.TAX: OpeningBalanceKind.ACCOUNT.value,
}


def parse_balance_list(
    data: bytes, accounts: dict[str, LedgerAccount]
) -> tuple[list[BalanceIn], list[str]]:
    """Reads a balance list (columns Konto and Saldo, debit positive) into balance lines of
    the ledger's accounts. Unknown accounts, zero balances and accounts that are no balance
    sheet accounts are reported as German errors; nothing is guessed (rule 0.1.3)."""
    from mhvp.imports.csvtext import decode_csv, read_table

    text, note = decode_csv(data)
    table = read_table(text, "Saldenliste")
    try:
        table.require(BALANCE_LIST_COLUMNS, "Saldenliste")
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
    account_col = table.column(*BALANCE_LIST_COLUMNS["Konto"])
    amount_col = table.column(*BALANCE_LIST_COLUMNS["Saldo"])
    text_col = table.column(*BALANCE_TEXT_COLUMNS)
    errors: list[str] = [note] if note else []
    out: list[BalanceIn] = []
    seen: dict[str, int] = {}
    for row in table.rows:
        label = f"Zeile {row.line}"
        number = normalise_account_number(table.cell(row, account_col))
        if number is None:
            errors.append(f"{label}: Kontonummer fehlt")
            continue
        account = accounts.get(number)
        if account is None:
            errors.append(f"{label}: Konto {number} gibt es im Buchungskreis nicht")
            continue
        kind = CATEGORY_KIND.get(account.category)
        if kind is None:
            errors.append(
                f"{label}: Konto {number} ({account.category.value}) ist kein Bestandskonto"
            )
            continue
        raw_amount = table.cell(row, amount_col)
        if raw_amount is None:
            errors.append(f"{label}: Saldo fehlt")
            continue
        try:
            amount = _money(parse_decimal(raw_amount))
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
            continue
        if amount == 0:
            continue  # a zero balance is no opening balance
        if number in seen:
            errors.append(f"{label}: Konto {number} doppelt (Zeile {seen[number]})")
            continue
        seen[number] = row.line
        out.append(
            BalanceIn(
                kind=kind,
                account_id=account.id,
                amount=amount,
                text=table.cell(row, text_col),
                property_bank_account_id=account.property_bank_account_id,
            )
        )
    return out, errors
