"""Machine readable audit export per legal entity and period (spec 7.7, case D55, A26).

One ZIP with one semicolon CSV per table (UTF-8 with BOM, ``csv_safe_cell`` on every text
cell), a table of contents (``index.csv`` and ``index.json`` with file, row count, columns and
SHA-256), the linked original receipts of the exported entries and an ``export.json`` with the
parameters. The scope follows section 7.7 literally: accounts, entries with lines, open item
settlements, opening balances, master data history of the involved property, units, contracts
and contacts (as far as the audit log holds it), approvals and events, reversal relations and
allocation key states. "GoBD" is a reference to the scope named in 7.7, not an assurance: the
data carrier format and its description standard are open (docs/OPEN_QUESTIONS.md M18-01,
P05) and are not claimed here. No DATEV chart of accounts, no tax classification is added.

Amounts use a decimal comma and ISO dates, like the journal CSV of ``mhvp.accounting.reports``.
The export is recorded as ``ExportRun`` (format ``audit_zip``) with the SHA-256 of the ZIP,
timestamp, creator and parameters, and the ZIP is stored as a document of the legal entity.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import (
    EntryKind,
    EntryStatus,
    ExportRun,
    Invoice,
    InvoiceReview,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerAccount,
    OpenItem,
    OpenItemSettlement,
)
from mhvp.core.escaping import csv_safe_cell
from mhvp.core.events import AuditLog, DomainEvent
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentLink, StorageKind

log = logging.getLogger(__name__)

FORMAT = "audit_zip"
# Receipts are packed into the ZIP as files while their total size stays below this limit;
# above it the ZIP carries only the reference list with SHA-256 (belege.csv). Configurable per
# run through the request (``receipts_max_bytes``).
DEFAULT_RECEIPTS_MAX_BYTES = 100 * 1024 * 1024
# Up to this many posted entries in the period the export is built inside the request;
# larger periods are queued to the worker (``mhvp.accounting.tasks.audit_export_run``).
SYNC_MAX_ENTRIES = 2_000
BOM = "﻿"
# Master data history is read from the audit log for these entity types (6.8).
HISTORY_ENTITY_TYPES = (
    "legal_entity",
    "property",
    "unit",
    "contract",
    "contact",
    "party",
    "ledger",
    "ledger_account",
    "journal_entry",
)


class ExportStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# CSV building ------------------------------------------------------------------------------


def format_cell(value: Any) -> Any:
    """Cell text: decimal comma for amounts, ISO dates and times, enum values, ``ja``/``nein``
    for booleans, empty string for None, formula neutralisation for every text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "ja" if value else "nein"
    if isinstance(value, Decimal):
        return str(value).replace(".", ",")
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (dict, list)):
        return csv_safe_cell(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
    if isinstance(value, str):
        return csv_safe_cell(value)
    return value


def csv_table(columns: list[str], rows: list[list[Any]]) -> bytes:
    """Semicolon separated, CRLF, UTF-8 with BOM, header first."""
    out = io.StringIO()
    out.write(BOM)
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([format_cell(cell) for cell in row])
    return out.getvalue().encode("utf-8")


@dataclass
class Table:
    name: str
    columns: list[str]
    rows: list[list[Any]] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return f"{self.name}.csv"


@dataclass
class Receipt:
    document_id: uuid.UUID
    filename: str
    mime_type: str
    size: int
    sha256: str
    storage: str
    entry_ids: list[uuid.UUID]
    included: bool = False
    path: str | None = None
    note: str | None = None
    data: bytes | None = None


@dataclass
class ExportBundle:
    meta: dict[str, Any]
    tables: list[Table]
    receipts: list[Receipt]
    receipt_files: dict[str, bytes]

    def table(self, name: str) -> Table:
        return next(t for t in self.tables if t.name == name)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_zip(bundle: ExportBundle) -> bytes:
    """Deterministic ZIP: tables, receipts, export.json, then index.csv and index.json which
    describe every other file with row count, columns and SHA-256."""
    index: list[dict[str, Any]] = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        def add(path: str, data: bytes, *, rows: int | None, columns: list[str] | None) -> None:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
            index.append(
                {
                    "file": path,
                    "rows": rows,
                    "columns": columns or [],
                    "bytes": len(data),
                    "sha256": _sha256(data),
                }
            )

        for table in bundle.tables:
            add(
                table.filename,
                csv_table(table.columns, table.rows),
                rows=len(table.rows),
                columns=table.columns,
            )
        for path in sorted(bundle.receipt_files):
            add(path, bundle.receipt_files[path], rows=None, columns=None)
        add(
            "export.json",
            json.dumps(
                bundle.meta, ensure_ascii=False, indent=2, sort_keys=True, default=str
            ).encode("utf-8"),
            rows=None,
            columns=None,
        )
        index_columns = ["Datei", "Zeilen", "Spalten", "Bytes", "SHA-256"]
        index_rows = [
            [e["file"], e["rows"], ";".join(e["columns"]), e["bytes"], e["sha256"]] for e in index
        ]
        add(
            "index.csv",
            csv_table(index_columns, index_rows),
            rows=len(index_rows),
            columns=index_columns,
        )
        info = zipfile.ZipInfo("index.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        zf.writestr(
            info,
            json.dumps(
                {"generated_at": bundle.meta["generated_at"], "files": index},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8"),
        )
    return buffer.getvalue()


# Data collection ----------------------------------------------------------------------------


async def count_entries(session: AsyncSession, ledger: Ledger, start: date, end: date) -> int:
    from sqlalchemy import func

    return int(
        await session.scalar(
            select(func.count(JournalEntry.id)).where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date.between(start, end),
            )
        )
        or 0
    )


async def collect(
    session: AsyncSession,
    blobs: BlobStore | None,
    ledger: Ledger,
    start: date,
    end: date,
    *,
    receipts_max_bytes: int,
    created_by: uuid.UUID | None,
    run_id: uuid.UUID | None = None,
) -> ExportBundle:
    """Reads every table of the 7.7 scope for the ledger (one per legal entity, 6.9.1) and the
    period. Only posted entries are exported; drafts are no bookkeeping (B03)."""
    from mhvp.contacts.models import Contact, PartyMember
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import (
        AllocationKey,
        LegalEntity,
        Property,
        Unit,
        UnitAllocationValue,
    )

    legal_entity = await session.get(LegalEntity, ledger.legal_entity_id)
    property_id = ledger.property_id or (legal_entity.property_id if legal_entity else None)
    prop = await session.get(Property, property_id) if property_id else None

    # Accounts -------------------------------------------------------------------------------
    accounts = list(
        await session.scalars(
            select(LedgerAccount)
            .where(LedgerAccount.ledger_id == ledger.id)
            .order_by(LedgerAccount.number)
        )
    )
    account_by_id = {a.id: a for a in accounts}
    konten = Table(
        "konten",
        [
            "Konto-ID",
            "Kontonummer",
            "Bezeichnung",
            "Kategorie",
            "Typ",
            "USt-Option",
            "Umlagekategorie",
            "Abrechnungsart",
            "Aktiv",
            "Systemkonto",
            "Kontakt-ID",
            "Vertrag-ID",
            "Einheit-ID",
            "Angelegt am",
        ],
        [
            [
                a.id,
                a.number,
                a.name,
                a.category,
                a.type,
                a.vat_option,
                a.allocation_category,
                a.statement_kind,
                a.active,
                a.is_system,
                a.contact_id,
                a.contract_id,
                a.unit_id,
                a.created_at,
            ]
            for a in accounts
        ],
    )

    # Entries and lines ------------------------------------------------------------------------
    entries = list(
        await session.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.booking_date.between(start, end),
            )
            .order_by(JournalEntry.fiscal_year, JournalEntry.number)
        )
    )
    entry_ids = [e.id for e in entries]
    entry_by_id = {e.id: e for e in entries}
    buchungen = Table(
        "buchungen",
        [
            "Buchung-ID",
            "Jahr",
            "Nummer",
            "Buchungstag",
            "Wertstellung",
            "Fälligkeit",
            "Leistungsdatum",
            "Art",
            "Quelle",
            "Text",
            "Belegnummer",
            "Beleg-Dokument-ID",
            "Bankumsatz-ID",
            "Rechnung-ID",
            "Vertrag-ID",
            "Storno von",
            "Storniert durch",
            "Stornogrund",
            "KI-Vorschlag-ID",
            "Gebucht am",
            "Gebucht von",
            "Freigegeben von",
        ],
        [
            [
                e.id,
                e.fiscal_year,
                e.number,
                e.booking_date,
                e.value_date,
                e.due_date,
                e.accrual_date,
                e.kind,
                e.source,
                e.text,
                e.reference,
                e.document_id,
                e.bank_transaction_id,
                e.invoice_id,
                e.contract_id,
                e.reverses_id,
                e.reversed_by_id,
                e.reversal_reason,
                e.ai_proposal_id,
                e.posted_at,
                e.posted_by,
                e.approved_by,
            ]
            for e in entries
        ],
    )
    lines: list[JournalLine] = []
    if entry_ids:
        lines = list(
            await session.scalars(
                select(JournalLine)
                .where(JournalLine.journal_entry_id.in_(entry_ids))
                .order_by(JournalLine.journal_entry_id, JournalLine.line_no)
            )
        )
    lines.sort(
        key=lambda ln: (
            entry_by_id[ln.journal_entry_id].fiscal_year or 0,
            entry_by_id[ln.journal_entry_id].number or 0,
            ln.line_no,
        )
    )
    buchungszeilen = Table(
        "buchungszeilen",
        [
            "Zeile-ID",
            "Buchung-ID",
            "Jahr",
            "Nummer",
            "Zeile",
            "Konto-ID",
            "Kontonummer",
            "Kontobezeichnung",
            "Soll",
            "Haben",
            "USt-Satz",
            "USt-Betrag",
            "Nettobetrag",
            "Kostenstelle",
            "Einheit-ID",
            "Schlüssel-Override-ID",
            "Text",
        ],
        [
            [
                ln.id,
                ln.journal_entry_id,
                entry_by_id[ln.journal_entry_id].fiscal_year,
                entry_by_id[ln.journal_entry_id].number,
                ln.line_no,
                ln.account_id,
                account_by_id[ln.account_id].number if ln.account_id in account_by_id else "",
                account_by_id[ln.account_id].name if ln.account_id in account_by_id else "",
                ln.debit,
                ln.credit,
                ln.vat_percent,
                ln.vat_amount,
                ln.net_amount,
                ln.cost_center,
                ln.unit_id,
                ln.allocation_key_override_id,
                ln.text,
            ]
            for ln in lines
        ],
    )

    # Reversal relations: every pair where one side lies in the period, the other side is
    # named even when it lies outside (a reversal in the next period still belongs here).
    storno_rows: list[list[Any]] = []
    seen_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    partner_ids = {
        i for e in entries for i in (e.reverses_id, e.reversed_by_id) if i is not None
    } - set(entry_ids)
    partners: dict[uuid.UUID, JournalEntry] = {}
    if partner_ids:
        partners = {
            p.id: p
            for p in await session.scalars(
                select(JournalEntry).where(JournalEntry.id.in_(partner_ids))
            )
        }
    lookup = {**entry_by_id, **partners}
    for e in entries:
        if e.reverses_id is not None:
            pair = (e.reverses_id, e.id)
        elif e.reversed_by_id is not None:
            pair = (e.id, e.reversed_by_id)
        else:
            continue
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        original, reversal = lookup.get(pair[0]), lookup.get(pair[1])
        storno_rows.append(
            [
                pair[0],
                original.fiscal_year if original else None,
                original.number if original else None,
                original.booking_date if original else None,
                pair[1],
                reversal.fiscal_year if reversal else None,
                reversal.number if reversal else None,
                reversal.booking_date if reversal else None,
                reversal.reversal_reason if reversal else None,
                reversal.posted_by if reversal else None,
            ]
        )
    storno = Table(
        "storno_beziehungen",
        [
            "Original-ID",
            "Original-Jahr",
            "Original-Nummer",
            "Original-Buchungstag",
            "Storno-ID",
            "Storno-Jahr",
            "Storno-Nummer",
            "Storno-Buchungstag",
            "Stornogrund",
            "Storniert von",
        ],
        storno_rows,
    )

    # Opening balances of the ledger up to the end of the period (posted, with approver).
    openings = list(
        await session.scalars(
            select(JournalEntry)
            .where(
                JournalEntry.ledger_id == ledger.id,
                JournalEntry.status == EntryStatus.POSTED,
                JournalEntry.kind == EntryKind.OPENING_BALANCE,
                JournalEntry.booking_date <= end,
            )
            .order_by(JournalEntry.fiscal_year, JournalEntry.number)
        )
    )
    opening_rows: list[list[Any]] = []
    if openings:
        opening_lines = list(
            await session.scalars(
                select(JournalLine)
                .where(JournalLine.journal_entry_id.in_([o.id for o in openings]))
                .order_by(JournalLine.journal_entry_id, JournalLine.line_no)
            )
        )
        opening_by_id = {o.id: o for o in openings}
        for ln in opening_lines:
            o = opening_by_id[ln.journal_entry_id]
            acc = account_by_id.get(ln.account_id)
            opening_rows.append(
                [
                    o.id,
                    o.fiscal_year,
                    o.number,
                    o.booking_date,
                    ln.line_no,
                    ln.account_id,
                    acc.number if acc else "",
                    acc.name if acc else "",
                    ln.debit,
                    ln.credit,
                    o.posted_by,
                    o.approved_by,
                    o.reversed_by_id,
                ]
            )
    eroeffnung = Table(
        "eroeffnungsbestaende",
        [
            "Buchung-ID",
            "Jahr",
            "Nummer",
            "Buchungstag",
            "Zeile",
            "Konto-ID",
            "Kontonummer",
            "Kontobezeichnung",
            "Soll",
            "Haben",
            "Gebucht von",
            "Freigegeben von",
            "Storniert durch",
        ],
        opening_rows,
    )

    # Open items and their settlements in the period (B07) --------------------------------------
    open_items = list(
        await session.scalars(
            select(OpenItem)
            .where(OpenItem.ledger_id == ledger.id, OpenItem.booking_date <= end)
            .order_by(OpenItem.booking_date, OpenItem.id)
        )
    )
    oi_by_id = {o.id: o for o in open_items}
    offene_posten = Table(
        "offene_posten",
        [
            "OP-ID",
            "Art",
            "Konto-ID",
            "Kontonummer",
            "Buchung-ID",
            "Buchungstag",
            "Fälligkeit",
            "Betrag",
            "Vertrag-ID",
            "Komponente",
            "Ausgebucht",
        ],
        [
            [
                o.id,
                o.kind,
                o.account_id,
                account_by_id[o.account_id].number if o.account_id in account_by_id else "",
                o.journal_entry_id,
                o.booking_date,
                o.due_date,
                o.amount,
                o.contract_id,
                o.component,
                o.written_off,
            ]
            for o in open_items
        ],
    )
    settlements: list[OpenItemSettlement] = []
    if open_items:
        settlements = list(
            await session.scalars(
                select(OpenItemSettlement)
                .where(
                    OpenItemSettlement.open_item_id.in_(list(oi_by_id)),
                    OpenItemSettlement.date.between(start, end),
                )
                .order_by(OpenItemSettlement.date, OpenItemSettlement.created_at)
            )
        )
    op_ausgleich = Table(
        "op_ausgleich",
        [
            "Ausgleich-ID",
            "OP-ID",
            "OP-Buchung-ID",
            "Ausgleichende Buchung-ID",
            "Datum",
            "Betrag",
            "Erfasst am",
        ],
        [
            [
                s.id,
                s.open_item_id,
                oi_by_id[s.open_item_id].journal_entry_id,
                s.journal_entry_id,
                s.date,
                s.amount,
                s.created_at,
            ]
            for s in settlements
        ],
    )

    # Approvals: second person on opening balances, invoice review steps of invoices posted in
    # the period (PÜ05). Dunning and payment approvals live in their own modules and are not
    # part of the ledger scope of 7.7.
    freigabe_rows: list[list[Any]] = []
    for e in entries:
        if e.approved_by is not None:
            freigabe_rows.append(
                [
                    "journal_entry",
                    e.id,
                    "opening_balance_approval",
                    "ok",
                    e.approved_by,
                    e.posted_at,
                    None,
                ]
            )
    invoice_ids = {e.invoice_id for e in entries if e.invoice_id is not None}
    invoices: dict[uuid.UUID, Invoice] = {}
    if invoice_ids:
        invoices = {
            inv.id: inv
            for inv in await session.scalars(select(Invoice).where(Invoice.id.in_(invoice_ids)))
        }
        reviews = await session.scalars(
            select(InvoiceReview)
            .where(InvoiceReview.invoice_id.in_(list(invoices)))
            .order_by(InvoiceReview.decided_at)
        )
        for r in reviews:
            freigabe_rows.append(
                ["invoice", r.invoice_id, r.step, r.result, r.user_id, r.decided_at, r.reason]
            )
    freigaben = Table(
        "freigaben",
        ["Objektart", "Objekt-ID", "Schritt", "Ergebnis", "Person", "Zeitpunkt", "Begründung"],
        freigabe_rows,
    )

    # Events of the exported entries and the ledger (append-only outbox, 6.8) -------------------
    event_entity_ids = set(entry_ids) | {ledger.id}
    events = list(
        await session.scalars(
            select(DomainEvent)
            .where(DomainEvent.entity_id.in_(list(event_entity_ids)))
            .order_by(DomainEvent.occurred_at, DomainEvent.id)
        )
    )
    ereignisse = Table(
        "ereignisse",
        [
            "Ereignis-ID",
            "Typ",
            "Objektart",
            "Objekt-ID",
            "Zeitpunkt",
            "Person",
            "Korrelation",
            "Nutzdaten",
        ],
        [
            [
                ev.id,
                ev.type,
                ev.entity_type,
                ev.entity_id,
                ev.occurred_at,
                ev.actor_user_id,
                ev.correlation_id,
                ev.payload,
            ]
            for ev in events
        ],
    )

    # Involved master data: property, units, contracts of the legal entity or of the entries,
    # parties and contacts of those contracts. History comes from the audit log (6.8) as far
    # as the writing modules recorded field changes.
    units: list[Any] = []
    if prop is not None:
        units = list(
            await session.scalars(
                select(Unit).where(Unit.property_id == prop.id).order_by(Unit.number)
            )
        )
    contract_ids = {e.contract_id for e in entries if e.contract_id is not None}
    contracts = list(
        await session.scalars(
            select(Contract)
            .where(
                or_(
                    Contract.legal_entity_id == ledger.legal_entity_id,
                    Contract.id.in_(list(contract_ids)) if contract_ids else Contract.id.is_(None),
                )
            )
            .order_by(Contract.number)
        )
    )
    party_ids = {c.party_id for c in contracts}
    contact_ids: set[uuid.UUID] = set()
    if party_ids:
        members = await session.scalars(
            select(PartyMember).where(PartyMember.party_id.in_(list(party_ids)))
        )
        contact_ids = {m.contact_id for m in members}
    contact_ids |= {a.contact_id for a in accounts if a.contact_id is not None}
    contacts: list[Any] = []
    if contact_ids:
        contacts = list(
            await session.scalars(select(Contact).where(Contact.id.in_(list(contact_ids))))
        )
    stammdaten = Table(
        "stammdaten",
        [
            "Objektart",
            "Objekt-ID",
            "Nummer",
            "Bezeichnung",
            "Übergeordnet-ID",
            "Angelegt am",
            "Geändert am",
        ],
        [],
    )
    if legal_entity is not None:
        stammdaten.rows.append(
            [
                "legal_entity",
                legal_entity.id,
                legal_entity.kind,
                legal_entity.name,
                legal_entity.property_id,
                legal_entity.created_at,
                legal_entity.updated_at,
            ]
        )
    if prop is not None:
        stammdaten.rows.append(
            ["property", prop.id, prop.number, prop.name, None, prop.created_at, prop.updated_at]
        )
    for u in units:
        stammdaten.rows.append(
            ["unit", u.id, u.number, u.internal_name, u.property_id, u.created_at, u.updated_at]
        )
    for c in contracts:
        stammdaten.rows.append(
            ["contract", c.id, c.number, c.kind, c.unit_id, c.created_at, c.updated_at]
        )
    for ct in sorted(contacts, key=lambda c: str(c.id)):
        stammdaten.rows.append(
            ["contact", ct.id, None, _contact_name(ct), None, ct.created_at, ct.updated_at]
        )
    history_ids: set[uuid.UUID] = (
        {ledger.id}
        | ({legal_entity.id} if legal_entity else set())
        | ({prop.id} if prop else set())
        | {u.id for u in units}
        | {c.id for c in contracts}
        | party_ids
        | contact_ids
        | set(account_by_id)
        | set(entry_ids)
    )
    history = list(
        await session.scalars(
            select(AuditLog)
            .where(
                AuditLog.entity_type.in_(HISTORY_ENTITY_TYPES),
                AuditLog.entity_id.in_(list(history_ids)),
            )
            .order_by(AuditLog.occurred_at, AuditLog.id)
        )
    )
    historie = Table(
        "stammdatenhistorie",
        [
            "Änderung-ID",
            "Ereignis-ID",
            "Objektart",
            "Objekt-ID",
            "Zeitpunkt",
            "Person",
            "Änderungen",
        ],
        [
            [
                h.id,
                h.event_id,
                h.entity_type,
                h.entity_id,
                h.occurred_at,
                h.actor_user_id,
                h.changes,
            ]
            for h in history
        ],
    )

    # Allocation keys of the property and their unit values overlapping the period -------------
    key_rows: list[list[Any]] = []
    value_rows: list[list[Any]] = []
    if prop is not None:
        keys = list(
            await session.scalars(
                select(AllocationKey)
                .where(AllocationKey.property_id == prop.id)
                .order_by(AllocationKey.sort_order, AllocationKey.code)
            )
        )
        key_by_id = {k.id: k for k in keys}
        for k in keys:
            key_rows.append(
                [
                    k.id,
                    k.code,
                    k.name,
                    k.kind,
                    k.unit_of_measure,
                    k.default_value,
                    k.meter_type_code,
                    k.is_template_derived,
                    k.created_at,
                    k.updated_at,
                ]
            )
        if keys:
            values = list(
                await session.scalars(
                    select(UnitAllocationValue)
                    .where(
                        UnitAllocationValue.allocation_key_id.in_(list(key_by_id)),
                        UnitAllocationValue.valid_from <= end,
                        or_(
                            UnitAllocationValue.valid_to.is_(None),
                            UnitAllocationValue.valid_to >= start,
                        ),
                    )
                    .order_by(
                        UnitAllocationValue.allocation_key_id,
                        UnitAllocationValue.unit_id,
                        UnitAllocationValue.valid_from,
                    )
                )
            )
            unit_by_id = {u.id: u for u in units}
            for v in values:
                value_rows.append(
                    [
                        v.id,
                        v.allocation_key_id,
                        key_by_id[v.allocation_key_id].code,
                        v.unit_id,
                        unit_by_id[v.unit_id].number if v.unit_id in unit_by_id else "",
                        v.value,
                        v.valid_from,
                        v.valid_to,
                        v.source,
                        v.created_at,
                        v.updated_at,
                    ]
                )
    schluessel = Table(
        "verteilungsschluessel",
        [
            "Schlüssel-ID",
            "Code",
            "Bezeichnung",
            "Art",
            "Einheit",
            "Standardwert",
            "Zählerart",
            "Aus Muster",
            "Angelegt am",
            "Geändert am",
        ],
        key_rows,
    )
    schluesselwerte = Table(
        "verteilungsschluessel_werte",
        [
            "Wert-ID",
            "Schlüssel-ID",
            "Schlüssel-Code",
            "Einheit-ID",
            "Einheit-Nummer",
            "Wert",
            "Gültig von",
            "Gültig bis",
            "Quelle",
            "Angelegt am",
            "Geändert am",
        ],
        value_rows,
    )

    # Receipts: documents named by the entries, linked to them, or named by their invoices --------
    receipts = await _receipts(session, blobs, entries, invoices, receipts_max_bytes)
    receipt_files: dict[str, bytes] = {}
    for receipt in receipts:
        if receipt.included and receipt.path is not None and receipt.data is not None:
            receipt_files[receipt.path] = receipt.data
    belege = Table(
        "belege",
        [
            "Dokument-ID",
            "Dateiname",
            "MIME-Typ",
            "Bytes",
            "SHA-256",
            "Ablage",
            "Buchung-IDs",
            "Im ZIP enthalten",
            "Pfad im ZIP",
            "Hinweis",
        ],
        [
            [
                r.document_id,
                r.filename,
                r.mime_type,
                r.size,
                r.sha256,
                r.storage,
                ",".join(str(i) for i in r.entry_ids),
                r.included,
                r.path,
                r.note,
            ]
            for r in receipts
        ],
    )

    generated_at = datetime.now(UTC)
    meta: dict[str, Any] = {
        "format": FORMAT,
        "scope": "Prüfexport im Umfang von MASTER-PROMPT 7.7 (Konten, Buchungen, OP-Ausgleich, "
        "Eröffnungsbestände, Stammdatenhistorie, Freigaben, Ereignisse, Stornobeziehungen, "
        "Verteilungsschlüssel, Belege). Kein DATEV-Kontenrahmen, keine steuerliche Einordnung, "
        "kein Datenträgerüberlassungsformat (M18-01).",
        "export_run_id": str(run_id) if run_id else None,
        "tenant_id": str(ledger.tenant_id),
        "legal_entity": {
            "id": str(ledger.legal_entity_id),
            "name": legal_entity.name if legal_entity else None,
            "kind": legal_entity.kind.value if legal_entity else None,
        },
        "ledger": {"id": str(ledger.id), "name": ledger.name, "locked_until": ledger.locked_until},
        "property": {"id": str(prop.id), "number": prop.number, "name": prop.name}
        if prop
        else None,
        "period_from": start.isoformat(),
        "period_to": end.isoformat(),
        "generated_at": generated_at.isoformat(),
        "data_as_of": generated_at.isoformat(),
        "created_by": str(created_by) if created_by else None,
        "entry_status": "posted only; drafts are not exported",
        "csv": {
            "delimiter": ";",
            "encoding": "UTF-8 with BOM",
            "line_terminator": "CRLF",
            "decimal_separator": ",",
            "date_format": "ISO 8601",
            "boolean": "ja/nein",
            "formula_neutralisation": "leading apostrophe on cells starting with = + - @ tab or CR",
        },
        "receipts": {
            "max_bytes": receipts_max_bytes,
            "total_bytes": sum(r.size for r in receipts),
            "included": sum(1 for r in receipts if r.included),
            "listed_only": sum(1 for r in receipts if not r.included),
        },
        "counts": {
            "accounts": len(accounts),
            "entries": len(entries),
            "lines": len(lines),
            "settlements": len(settlements),
        },
    }
    return ExportBundle(
        meta=meta,
        tables=[
            konten,
            buchungen,
            buchungszeilen,
            storno,
            eroeffnung,
            offene_posten,
            op_ausgleich,
            freigaben,
            ereignisse,
            stammdaten,
            historie,
            schluessel,
            schluesselwerte,
            belege,
        ],
        receipts=receipts,
        receipt_files=receipt_files,
    )


def _contact_name(contact: Any) -> str:
    return str(getattr(contact, "display_name", "") or "")


async def _receipts(
    session: AsyncSession,
    blobs: BlobStore | None,
    entries: list[JournalEntry],
    invoices: dict[uuid.UUID, Invoice],
    max_bytes: int,
) -> list[Receipt]:
    doc_entries: dict[uuid.UUID, list[uuid.UUID]] = {}

    def link(doc_id: uuid.UUID | None, entry_id: uuid.UUID) -> None:
        if doc_id is not None:
            doc_entries.setdefault(doc_id, [])
            if entry_id not in doc_entries[doc_id]:
                doc_entries[doc_id].append(entry_id)

    for e in entries:
        link(e.document_id, e.id)
        if e.invoice_id is not None and e.invoice_id in invoices:
            link(invoices[e.invoice_id].document_id, e.id)
    if entries:
        links = await session.scalars(
            select(DocumentLink).where(
                DocumentLink.entity_type == "journal_entry",
                DocumentLink.entity_id.in_([e.id for e in entries]),
            )
        )
        for dl in links:
            if dl.entity_id is not None:
                link(dl.document_id, dl.entity_id)
    if not doc_entries:
        return []
    documents = list(
        await session.scalars(select(Document).where(Document.id.in_(list(doc_entries))))
    )
    documents.sort(key=lambda d: str(d.id))
    total = sum(d.size for d in documents)
    pack = total <= max_bytes and blobs is not None
    receipts: list[Receipt] = []
    for d in documents:
        r = Receipt(
            document_id=d.id,
            filename=d.filename,
            mime_type=d.mime_type,
            size=d.size,
            sha256=d.sha256,
            storage=d.storage.value,
            entry_ids=doc_entries[d.id],
        )
        if not pack:
            r.note = (
                "Nur Verweis: Gesamtgröße der Belege überschreitet die Grenze."
                if blobs is not None
                else "Nur Verweis: kein Objektspeicher verfügbar."
            )
        elif d.storage is not StorageKind.MINIO or blobs is None:
            r.note = "Nur Verweis: Ablage außerhalb des Objektspeichers."
        else:
            try:
                data = blobs.get(d.storage_ref)
            except Exception as exc:  # listed with hash instead of failing the export
                log.warning("audit_export_receipt_unreadable", extra={"error": type(exc).__name__})
                r.note = "Nur Verweis: Original nicht lesbar."
            else:
                if _sha256(data) != d.sha256:
                    r.note = "Nur Verweis: Prüfsumme des Originals weicht vom Index ab."
                else:
                    r.included = True
                    r.path = f"belege/{d.id}_{_safe_name(d.filename)}"
                    r.data = data
        receipts.append(r)
    return receipts


def _safe_name(filename: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in filename)
    return keep[:120] or "beleg"


# Persistence ---------------------------------------------------------------------------------


async def store_result(
    session: AsyncSession,
    blobs: BlobStore,
    run: ExportRun,
    ledger: Ledger,
    data: bytes,
    bundle: ExportBundle,
) -> None:
    """Stores the ZIP as generated document of the legal entity and completes the run."""
    from mhvp.documents import services as docs
    from mhvp.documents.models import DocumentSource, LinkRole

    document = await docs.store_document(
        session,
        blobs,
        tenant_id=run.tenant_id,
        data=data,
        title=f"Prüfexport {ledger.name} {run.period_from:%Y-%m-%d} bis {run.period_to:%Y-%m-%d}",
        filename=f"pruefexport_{run.period_from:%Y-%m-%d}_{run.period_to:%Y-%m-%d}_{run.id}.zip",
        mime_type="application/zip",
        source=DocumentSource.GENERATED,
        category_id=None,
        links=[("legal_entity", ledger.legal_entity_id, LinkRole.GENERATED)],
        created_by=run.created_by,
    )
    run.document_id = document.id
    run.sha256 = _sha256(data)
    run.rows = bundle.meta["counts"]["lines"]
    run.status = ExportStatus.DONE.value
    run.error = None
    run.finished_at = datetime.now(UTC)
    run.params = {
        **run.params,
        "receipts": bundle.meta["receipts"],
        "counts": bundle.meta["counts"],
    }
    await session.flush()


async def execute(
    session: AsyncSession, blobs: BlobStore, run: ExportRun, ledger: Ledger
) -> ExportBundle:
    """Builds and stores the export for an existing run (used inline and by the worker)."""
    run.status = ExportStatus.RUNNING.value
    await session.flush()
    bundle = await collect(
        session,
        blobs,
        ledger,
        run.period_from,
        run.period_to,
        receipts_max_bytes=int(run.params.get("receipts_max_bytes", DEFAULT_RECEIPTS_MAX_BYTES)),
        created_by=run.created_by,
        run_id=run.id,
    )
    data = build_zip(bundle)
    await store_result(session, blobs, run, ledger, data, bundle)
    return bundle


def run_out(run: ExportRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "ledger_id": run.ledger_id,
        "format": run.format,
        "status": run.status,
        "period_from": run.period_from,
        "period_to": run.period_to,
        "rows": run.rows,
        "sha256": run.sha256 or None,
        "document_id": run.document_id,
        "params": run.params,
        "note": run.note,
        "error": run.error,
        "created_at": run.created_at,
        "created_by": run.created_by,
        "finished_at": run.finished_at,
    }
