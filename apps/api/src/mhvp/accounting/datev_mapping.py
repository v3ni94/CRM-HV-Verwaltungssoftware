"""CRM account to DATEV Sachkonto mapping per tenant (A36, M18-01, rule M18-04).

The mapping is operator master data: nothing is preloaded, no SKR03/SKR04 chart is shipped.
Resolution order for a CRM account number on a booking date:

1. active rows of the ledger before tenant wide rows (``ledger_id`` empty);
2. within that, the latest ``valid_from`` that is not after the booking date; a row without
   ``valid_from`` applies since ever.

The DATEV batch export (``mhvp.accounting.reports.datev_csv``) refuses with
``MHVP-BILL-0008`` when any posted line has no resolvable mapping; raw CRM numbers are never
written silently.
"""

import csv
import io
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import (
    DatevAccountMapping,
    EntryStatus,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
)

# Accepted CSV column names (case insensitive); the first name of each tuple is the export
# name. German headings of a spreadsheet export are accepted as aliases.
COLUMNS: dict[str, tuple[str, ...]] = {
    "account_code": ("account_code", "konto", "crm-konto", "crm_konto", "kontonummer"),
    "datev_account": ("datev_account", "datev-konto", "datev_konto", "sachkonto", "datev"),
    "label": ("label", "bezeichnung", "name"),
    "valid_from": ("valid_from", "gültig ab", "gueltig_ab", "gültig_ab", "ab"),
}
MAX_IMPORT_ROWS = 5000


@dataclass(frozen=True)
class MappingRow:
    account_code: str
    datev_account: str
    label: str | None
    valid_from: date | None


class Resolver:
    """In memory resolution of one ledger's mappings (tenant wide rows included)."""

    def __init__(self, rows: Iterable[DatevAccountMapping], ledger_id: uuid.UUID) -> None:
        self._by_code: dict[str, list[DatevAccountMapping]] = {}
        self._ledger_id = ledger_id
        for row in rows:
            if not row.active:
                continue
            if row.ledger_id is not None and row.ledger_id != ledger_id:
                continue
            self._by_code.setdefault(row.account_code, []).append(row)

    def resolve(self, account_code: str, on: date) -> str | None:
        candidates = [
            r
            for r in self._by_code.get(account_code, ())
            if r.valid_from is None or r.valid_from <= on
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda r: (
                r.ledger_id is not None,  # ledger specific wins
                r.valid_from or date.min,  # latest validity wins
            ),
            reverse=True,
        )
        return candidates[0].datev_account


async def load_resolver(session: AsyncSession, ledger: Ledger) -> Resolver:
    rows = (
        await session.scalars(
            select(DatevAccountMapping).where(
                DatevAccountMapping.tenant_id == ledger.tenant_id,
                DatevAccountMapping.active.is_(True),
                (DatevAccountMapping.ledger_id == ledger.id)
                | (DatevAccountMapping.ledger_id.is_(None)),
            )
        )
    ).all()
    return Resolver(rows, ledger.id)


@dataclass
class ReportLine:
    account_id: uuid.UUID
    account_code: str
    account_name: str
    datev_account: str | None
    lines_in_period: int
    first_booking_date: date | None
    last_booking_date: date | None
    unmapped: bool
    unmapped_lines: int
    reason: str | None


@dataclass
class Report:
    ledger_id: uuid.UUID
    period_from: date
    period_to: date
    accounts: list[ReportLine] = field(default_factory=list)

    @property
    def unmapped_count(self) -> int:
        return sum(1 for a in self.accounts if a.unmapped)

    @property
    def used_unmapped_count(self) -> int:
        return sum(1 for a in self.accounts if a.unmapped and a.lines_in_period)


async def report(session: AsyncSession, ledger: Ledger, start: date, end: date) -> Report:
    """Which accounts of the ledger lack a DATEV mapping. Accounts with posted lines in the
    period are checked per booking date (a mapping valid only from a later date leaves the
    earlier lines unmapped); accounts without lines are checked as of the period end."""
    resolver = await load_resolver(session, ledger)
    accounts = (
        await session.scalars(
            select(LedgerAccount)
            .where(LedgerAccount.ledger_id == ledger.id)
            .order_by(LedgerAccount.number)
        )
    ).all()
    usage = (
        await session.execute(
            select(
                JournalLine.account_id,
                JournalEntry.booking_date,
                func.count(JournalLine.id),
            )
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date.between(start, end),
            )
            .group_by(JournalLine.account_id, JournalEntry.booking_date)
        )
    ).all()
    per_account: dict[uuid.UUID, list[tuple[date, int]]] = {}
    for account_id, booking_date, count in usage:
        per_account.setdefault(account_id, []).append((booking_date, int(count)))
    out = Report(ledger_id=ledger.id, period_from=start, period_to=end)
    for account in accounts:
        dates = sorted(per_account.get(account.id, []))
        total = sum(c for _, c in dates)
        unmapped_lines = sum(c for d, c in dates if resolver.resolve(account.number, d) is None)
        as_of_end = resolver.resolve(account.number, end)
        unmapped = unmapped_lines > 0 or as_of_end is None
        reason: str | None = None
        if as_of_end is None:
            reason = "keine Zuordnung"
        elif unmapped_lines:
            reason = "Zuordnung gilt erst nach einzelnen Buchungstagen"
        out.accounts.append(
            ReportLine(
                account_id=account.id,
                account_code=account.number,
                account_name=account.name,
                datev_account=as_of_end,
                lines_in_period=total,
                first_booking_date=dates[0][0] if dates else None,
                last_booking_date=dates[-1][0] if dates else None,
                unmapped=unmapped,
                unmapped_lines=unmapped_lines,
                reason=reason,
            )
        )
    return out


# CSV import -----------------------------------------------------------------------------


@dataclass
class ImportRow:
    line_no: int
    account_code: str | None
    datev_account: str | None
    label: str | None
    valid_from: date | None
    action: str  # create | update | unchanged | error
    error: str | None = None
    existing_id: uuid.UUID | None = None
    existing_datev_account: str | None = None


def _normalise_header(cells: list[str]) -> dict[str, int]:
    index: dict[str, int] = {}
    for position, raw in enumerate(cells):
        cell = raw.strip().lstrip("﻿").lower()
        for column, aliases in COLUMNS.items():
            if cell in aliases and column not in index:
                index[column] = position
    return index


def _parse_date(value: str) -> date:
    value = value.strip()
    if len(value) == 10 and value[2] == "." and value[5] == ".":
        d, m, y = value.split(".")
        return date(int(y), int(m), int(d))
    return date.fromisoformat(value)


def _cell(header: dict[str, int], cells: list[str], column: str) -> str | None:
    position = header.get(column)
    if position is None or position >= len(cells):
        return None
    value = cells[position].strip()
    return value or None


def parse_csv(content: str) -> tuple[list[ImportRow], list[str]]:
    """Parses the operator's CSV (semicolon or comma, header row required). Returns the rows
    with their parse state and a list of file level errors (empty when the header is usable)."""
    text = content.lstrip("﻿")
    sample = text[:2048]
    delimiter = ";"
    if sample and sample.count(",") > sample.count(";"):
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[ImportRow] = []
    header: dict[str, int] | None = None
    errors: list[str] = []
    for line_no, cells in enumerate(reader, start=1):
        if not any(c.strip() for c in cells):
            continue
        if header is None:
            header = _normalise_header(cells)
            if "account_code" not in header or "datev_account" not in header:
                errors.append(
                    "Kopfzeile ohne die Spalten account_code (Konto) und datev_account "
                    "(DATEV-Konto)."
                )
                return [], errors
            continue
        if len(rows) >= MAX_IMPORT_ROWS:
            errors.append(f"Mehr als {MAX_IMPORT_ROWS} Zeilen; Datei teilen.")
            break

        account_code = _cell(header, cells, "account_code")
        datev_account = _cell(header, cells, "datev_account")
        label = _cell(header, cells, "label")
        raw_valid = _cell(header, cells, "valid_from")
        valid_from: date | None = None
        error: str | None = None
        if not account_code or not datev_account:
            error = "Konto oder DATEV-Konto fehlt."
        elif len(account_code) > 32 or len(datev_account) > 16:
            error = "Konto oder DATEV-Konto zu lang."
        elif not datev_account.isdigit():
            error = "DATEV-Konto muss numerisch sein."
        if raw_valid and error is None:
            try:
                valid_from = _parse_date(raw_valid)
            except ValueError:
                error = "Gültig ab ist kein Datum (TT.MM.JJJJ oder JJJJ-MM-TT)."
        if label and len(label) > 200:
            label = label[:200]
        rows.append(
            ImportRow(
                line_no=line_no,
                account_code=account_code,
                datev_account=datev_account,
                label=label,
                valid_from=valid_from,
                action="error" if error else "create",
                error=error,
            )
        )
    if header is None:
        errors.append("Die Datei ist leer.")
    return rows, errors


async def plan_import(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    ledger_id: uuid.UUID | None,
    content: str,
) -> tuple[list[ImportRow], list[str]]:
    """Preview: compares the parsed rows with the stored mappings of the same scope (tenant,
    ledger or tenant wide, account_code, valid_from) and marks create, update, unchanged."""
    rows, errors = parse_csv(content)
    if errors:
        return rows, errors
    existing = (
        await session.scalars(
            select(DatevAccountMapping).where(
                DatevAccountMapping.tenant_id == tenant_id,
                DatevAccountMapping.ledger_id == ledger_id
                if ledger_id is not None
                else DatevAccountMapping.ledger_id.is_(None),
            )
        )
    ).all()
    by_key = {(m.account_code, m.valid_from): m for m in existing}
    seen: set[tuple[str, date | None]] = set()
    for row in rows:
        if row.action == "error" or row.account_code is None:
            continue
        key = (row.account_code, row.valid_from)
        if key in seen:
            row.action = "error"
            row.error = "Doppelte Zeile für dasselbe Konto und Gültig ab."
            continue
        seen.add(key)
        match = by_key.get(key)
        if match is None:
            continue
        row.existing_id = match.id
        row.existing_datev_account = match.datev_account
        same = (
            match.datev_account == row.datev_account
            and (match.label or None) == (row.label or None)
            and match.active
        )
        row.action = "unchanged" if same else "update"
    return rows, errors


async def apply_import(
    session: AsyncSession,
    rows: list[ImportRow],
    *,
    tenant_id: uuid.UUID,
    ledger_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> dict[str, int]:
    """Writes the planned rows. Rows with errors are skipped and counted; the caller decides
    whether an import with errors is allowed at all (the endpoint refuses)."""
    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    existing_ids = [r.existing_id for r in rows if r.existing_id is not None]
    by_id: dict[uuid.UUID, DatevAccountMapping] = {}
    if existing_ids:
        found = (
            await session.scalars(
                select(DatevAccountMapping).where(DatevAccountMapping.id.in_(existing_ids))
            )
        ).all()
        by_id = {m.id: m for m in found}
    for row in rows:
        if row.action == "error" or row.account_code is None or row.datev_account is None:
            counts["skipped"] += 1
            continue
        if row.action == "unchanged":
            counts["unchanged"] += 1
            continue
        if row.action == "update" and row.existing_id in by_id:
            mapping = by_id[row.existing_id]
            mapping.datev_account = row.datev_account
            mapping.label = row.label
            mapping.active = True
            mapping.updated_by = actor_user_id
            counts["updated"] += 1
            continue
        session.add(
            DatevAccountMapping(
                tenant_id=tenant_id,
                ledger_id=ledger_id,
                account_code=row.account_code,
                datev_account=row.datev_account,
                label=row.label,
                active=True,
                valid_from=row.valid_from,
                created_by=actor_user_id,
                updated_by=actor_user_id,
            )
        )
        counts["created"] += 1
    await session.flush()
    return counts


def row_to_dict(row: ImportRow) -> dict[str, Any]:
    return {
        "line_no": row.line_no,
        "account_code": row.account_code,
        "datev_account": row.datev_account,
        "label": row.label,
        "valid_from": row.valid_from,
        "action": row.action,
        "error": row.error,
        "existing_id": row.existing_id,
        "existing_datev_account": row.existing_datev_account,
    }
