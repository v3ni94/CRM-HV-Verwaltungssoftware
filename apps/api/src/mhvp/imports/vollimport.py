"""Full import of the Immoware24 exports with pre-check, dry run, reconciliation and cut-off
date (13.1, M8-01, M8-02, V9, annex D cases D01 and D02).

The operator uploads the export files of one cut-off date (Objektdaten, Kontaktlisten,
Adressliste, optionally Bankumsätze and a Saldenliste). Every file passes a pre-check
(encoding, delimiter, header comparison against the expected columns, row count, duplicate
keys, missing required fields, SHA-256). A dry run (``mode=preview``) runs the same importers
inside a rolled back savepoint and previews per entity what would be created, left unchanged
or reported as conflict. ``mode=apply`` writes and then reconciles target (rows in the file)
against actual (records in the platform) per entity with a difference list: missing,
duplicate, deviating fields. ``mode=abgleich`` only reconciles.

Contract lists (Mietverträge, Eigentümerverträge) are imported after objects and contacts
(``mhvp.imports.vollimport_vertraege``): party via contact id, unit via object and unit
number, rent and Hausgeld as contract payments, key Immoware24 contract number or
object/unit/start; the reconciliation adds counts and target sums per object.

Keys are the Immoware24 object number, unit number (``<object>/<unit>``) and contact id, so a
repeated import of the same files creates nothing twice; with ``update_existing`` deviating
master data fields (object name, unit label and location) are updated instead of reported as
conflict. The management type of an existing object is never changed by an import.

Balances from a Saldenliste become opening balance proposals per contract as a draft only:
gate G1 (productive bookkeeping) stays closed, nothing is posted (rule 0.1.1, B01).
"""

from __future__ import annotations

import hashlib
import io
import re
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from mhvp.contacts.models import Contact, ContactRoleCode, Party
from mhvp.contracts.models import Contract, ContractKind
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.imports import adressen, kontakte, objektdaten
from mhvp.imports import reconciliation as rec
from mhvp.imports import vollimport_vertraege as vertraege
from mhvp.imports.csvtext import Table, column_key, decode_csv, detect_delimiter, read_table
from mhvp.imports.fields import parse_decimal
from mhvp.imports.models import ReportType
from mhvp.properties.models import Property, Unit

SOURCE = "immoware24:vollimport"
MAX_BYTES = 20 * 1024 * 1024
CONTACT_KINDS: dict[str, ContactRoleCode] = {
    "eigentuemer": ContactRoleCode.EIGENTUEMER,
    "mieter": ContactRoleCode.MIETER,
    "sonstige": ContactRoleCode.SONSTIGES,
    "bank": ContactRoleCode.BANK,
    "dienstleister": ContactRoleCode.DIENSTLEISTER,
}
# Assumed columns of a balance list (docs/OPEN_QUESTIONS.md V9 addendum): the real export
# header is not specified and must be confirmed by the operator before productive use.
SALDEN_COLUMNS: dict[str, tuple[str, ...]] = {
    "Objekt-Nummer": objektdaten.COLUMNS["Objekt-Nummer"],
    "VE-Nummer": objektdaten.COLUMNS["VE-Nummer"],
    "Vertragsart": ("Vertragsart", "Art", "Rolle"),
    "Name": ("Name", "Vertragspartner", "Kontakt", "Debitor"),
    "Saldo": ("Saldo", "Kontostand", "Offener Betrag", "Betrag"),
}
CONTRACT_KINDS: dict[str, ContractKind] = {
    "mietvertraege": ContractKind.TENANCY,
    "eigentuemervertraege": ContractKind.OWNERSHIP,
}
_BANK_DEFAULTS = rec.DEFAULT_COLUMNS[ReportType.BANK_TRANSACTIONS.value]
BANK_COLUMNS: dict[str, tuple[str, ...]] = {
    "Objekt": (_BANK_DEFAULTS["property_number"], "Objekt-Nummer", "Objektnummer"),
    "IBAN": (_BANK_DEFAULTS["iban"], "Konto"),
    "Datum": (_BANK_DEFAULTS["booking_date"], "Buchungstag", "Buchungsdatum", "Valuta"),
    "Betrag": (_BANK_DEFAULTS["amount"], "Umsatz"),
    "Saldo": (_BANK_DEFAULTS["balance"], "Kontostand"),
}
ADRESSEN_COLUMNS: dict[str, tuple[str, ...]] = {
    "Objektnummer": ("Objektnummer", "Objekt-Nummer", "Objekt Nr", "Objekt"),
    "Straße": ("Straße", "Strasse", "Anschrift", "Adresse"),
    "Hausnummer": ("Hausnummer", "Haus-Nr.", "Nr"),
    "PLZ": ("PLZ", "Postleitzahl"),
    "Ort": ("Ort", "Stadt"),
}


@dataclass(frozen=True)
class ExportKind:
    """One Immoware24 export type the assistant knows: expected columns and row key."""

    kind: str
    label: str
    columns: dict[str, tuple[str, ...]]
    required: tuple[str, ...]
    key_columns: tuple[str, ...]
    reconciled: bool


def _contact_kind(kind: str, label: str) -> ExportKind:
    return ExportKind(kind, label, kontakte.COLUMNS, kontakte.REQUIRED, ("id",), True)


EXPORT_KINDS: dict[str, ExportKind] = {
    "objektdaten": ExportKind(
        "objektdaten",
        "Objektdaten (Objekte und Einheiten)",
        objektdaten.COLUMNS,
        objektdaten.REQUIRED,
        ("Objekt-Nummer", "VE-Nummer"),
        True,
    ),
    "eigentuemer": _contact_kind("eigentuemer", "Kontaktliste Eigentümer"),
    "mieter": _contact_kind("mieter", "Kontaktliste Mieter"),
    "sonstige": _contact_kind("sonstige", "Kontaktliste Sonstige"),
    "bank": _contact_kind("bank", "Kontaktliste Banken"),
    "dienstleister": _contact_kind("dienstleister", "Kontaktliste Dienstleister"),
    "adressen": ExportKind(
        "adressen",
        "Adressliste der Objekte",
        ADRESSEN_COLUMNS,
        ("Objektnummer",),
        ("Objektnummer",),
        True,
    ),
    "mietvertraege": ExportKind(
        "mietvertraege",
        "Mietverträge (Mieter je Einheit, Laufzeit, Miete)",
        vertraege.MIET_COLUMNS,
        vertraege.MIET_REQUIRED,
        (*vertraege.KEY_COLUMNS, "Mietbeginn"),
        True,
    ),
    "eigentuemervertraege": ExportKind(
        "eigentuemervertraege",
        "Eigentümerverträge (Eigentümer je Einheit, Laufzeit, Hausgeld)",
        vertraege.EIG_COLUMNS,
        vertraege.EIG_REQUIRED,
        (*vertraege.KEY_COLUMNS, "Beginn"),
        True,
    ),
    "bankumsaetze": ExportKind(
        "bankumsaetze",
        "Bankumsätze (nur Vorprüfung, Einlesen über den Importassistenten)",
        BANK_COLUMNS,
        ("Objekt", "IBAN", "Betrag"),
        (),
        False,
    ),
    "salden": ExportKind(
        "salden",
        "Saldenliste zum Stichtag (Eröffnungssalden-Vorschlag, Entwurf)",
        SALDEN_COLUMNS,
        ("Objekt-Nummer", "VE-Nummer", "Saldo"),
        ("Objekt-Nummer", "VE-Nummer", "Vertragsart", "Name"),
        False,
    ),
}


# Pre-check ------------------------------------------------------------------------------


@dataclass
class Upload:
    name: str
    kind: str
    data: bytes


@dataclass
class Precheck:
    name: str
    kind: str
    ok: bool
    sha256: str
    bytes: int
    encoding: str
    delimiter: str
    headers: list[str]
    missing_required: list[str]
    missing_optional: list[str]
    unknown_headers: list[str]
    row_count: int
    duplicate_keys: list[dict[str, Any]]
    missing_fields: list[dict[str, Any]]
    notes: list[str]
    text: str = field(default="", repr=False)
    table: Table | None = field(default=None, repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "datei": self.name,
            "art": self.kind,
            "ok": self.ok,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "zeichensatz": self.encoding,
            "trennzeichen": self.delimiter,
            "kopfzeile": self.headers,
            "pflichtspalten_fehlend": self.missing_required,
            "optionale_spalten_fehlend": self.missing_optional,
            "unbekannte_spalten": self.unknown_headers,
            "zeilen": self.row_count,
            "dubletten": self.duplicate_keys,
            "pflichtfelder_fehlend": self.missing_fields,
            "hinweise": self.notes,
        }


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def precheck(upload: Upload) -> Precheck:
    """Reads the file without touching the database and reports what an import would face."""
    spec = EXPORT_KINDS.get(upload.kind)
    if spec is None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=f"Exporttyp {upload.kind!r} unbekannt ({', '.join(EXPORT_KINDS)}).",
        )
    digest = sha256_hex(upload.data)
    size = len(upload.data)
    if size == 0:
        return Precheck(
            upload.name,
            upload.kind,
            False,
            digest,
            0,
            "leer",
            "",
            [],
            list(spec.required),
            [],
            [],
            0,
            [],
            [],
            ["Die Datei ist leer."],
        )
    if size > MAX_BYTES:
        return Precheck(
            upload.name,
            upload.kind,
            False,
            digest,
            size,
            "",
            "",
            [],
            [],
            [],
            [],
            0,
            [],
            [],
            ["Die Datei ist größer als 20 MB."],
        )
    text, encoding_note = decode_csv(upload.data)
    encoding = "UTF-8"
    if encoding_note:
        encoding = (
            "UTF-16"
            if "UTF-16" in encoding_note
            else ("Windows-1252" if "1252" in encoding_note else "Latin-1")
        )
    elif upload.data.startswith(b"\xef\xbb\xbf"):
        encoding = "UTF-8 (BOM)"
    notes: list[str] = [encoding_note] if encoding_note else []
    if "\x00" in text:
        notes.append("Datei enthält NUL-Zeichen und wird nicht gelesen.")
        return Precheck(
            upload.name,
            upload.kind,
            False,
            digest,
            size,
            encoding,
            "",
            [],
            list(spec.required),
            [],
            [],
            0,
            [],
            [],
            notes,
        )
    try:
        table = read_table(text, upload.name)
    except ValueError as exc:
        notes.append(str(exc))
        return Precheck(
            upload.name,
            upload.kind,
            False,
            digest,
            size,
            encoding,
            detect_delimiter(text),
            [],
            list(spec.required),
            [],
            [],
            0,
            [],
            [],
            notes,
        )
    notes.extend(table.notes)
    known_keys = {column_key(s) for names in spec.columns.values() for s in names}
    unknown = sorted({h for h in table.headers if h and column_key(h) not in known_keys})
    missing_required = [c for c in spec.required if table.column(*spec.columns[c]) is None]
    missing_optional = [
        c for c in spec.columns if c not in spec.required and table.column(*spec.columns[c]) is None
    ]
    col = {label: table.column(*names) for label, names in spec.columns.items()}
    missing_fields: list[dict[str, Any]] = []
    seen: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for row in table.rows:
        for label in spec.required:
            if col[label] is not None and table.cell(row, col[label]) is None:
                missing_fields.append({"zeile": row.line, "feld": label})
        if spec.key_columns:
            key = tuple(table.cell(row, col[c]) or "" for c in spec.key_columns)
            if any(key):
                seen[key].append(row.line)
    duplicates = [
        {"schluessel": " / ".join(k), "zeilen": lines}
        for k, lines in seen.items()
        if len(lines) > 1 and upload.kind != "objektdaten"
    ]
    if upload.kind == "objektdaten":
        # A unit may repeat only with identical content (the parser keeps one copy); rows
        # with the same object and unit number but different content are duplicates.
        duplicates = _objektdaten_duplicates(table, col)
    if upload.kind == "adressen" and not missing_required:
        try:
            adressen.map_headers(list(table.headers))
        except ValueError as exc:
            notes.append(str(exc))
            missing_required.append("Straße, Hausnummer, PLZ oder Ort")
    ok = not missing_required and not missing_fields and not duplicates
    if not table.rows:
        notes.append("Die Datei enthält keine Datenzeilen.")
        ok = False
    return Precheck(
        upload.name,
        upload.kind,
        ok,
        digest,
        size,
        encoding,
        {";": "Semikolon", ",": "Komma", "\t": "Tabulator"}[table.delimiter],
        list(table.headers),
        missing_required,
        missing_optional,
        unknown,
        len(table.rows),
        duplicates,
        missing_fields[:200],
        notes,
        text,
        table,
    )


def _objektdaten_duplicates(table: Table, col: dict[str, int | None]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[tuple[str, ...], list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in table.rows:
        obj = table.cell(row, col["Objekt-Nummer"])
        unit = table.cell(row, col["VE-Nummer"])
        if obj is None or unit is None:
            continue
        by_key[(obj, unit)][tuple(row.cells)].append(row.line)
    out: list[dict[str, Any]] = []
    for (obj, unit), variants in by_key.items():
        if len(variants) > 1:
            lines = sorted(line for ls in variants.values() for line in ls)
            out.append({"schluessel": f"{obj} / {unit}", "zeilen": lines})
    return out


# Reconciliation -------------------------------------------------------------------------


@dataclass
class EntityReport:
    entity: str
    target: int = 0
    actual: int = 0
    matched: int = 0
    missing: list[dict[str, Any]] = field(default_factory=list)
    duplicate: list[dict[str, Any]] = field(default_factory=list)
    deviating: list[dict[str, Any]] = field(default_factory=list)
    extra: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Contract lists: count and target sum per object (file) against the platform.
    per_object: list[dict[str, Any]] = field(default_factory=list)

    @property
    def differences(self) -> int:
        return len(self.missing) + len(self.duplicate) + len(self.deviating)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entitaet": self.entity,
            "soll": self.target,
            "ist": self.actual,
            "uebereinstimmend": self.matched,
            "differenzen": self.differences,
            "fehlend": self.missing[:500],
            "doppelt": self.duplicate[:500],
            "abweichend": self.deviating[:500],
            "zusaetzlich": self.extra[:500],
            "hinweise": self.notes,
            "je_objekt": self.per_object[:500],
        }


def _same_text(a: str | None, b: str | None) -> bool:
    return (a or "").strip().casefold() == (b or "").strip().casefold()


async def reconcile_objektdaten(
    session: Any,
    tenant_id: uuid.UUID,
    parsed: objektdaten.ParsedObjektdaten,
    number_map: dict[str, str],
) -> tuple[EntityReport, EntityReport]:
    """Objects and units of the file against the platform (keys: object number, unit source id)."""
    props = EntityReport("objekte")
    units = EntityReport("einheiten")
    prepared = objektdaten.prepare(parsed, number_map)
    props.target = len(prepared)
    units.target = sum(len(p.row.units) for p in prepared)
    db_props = list(
        (await session.execute(select(Property).where(Property.tenant_id == tenant_id))).scalars()
    )
    by_number: dict[str, list[Property]] = defaultdict(list)
    by_source: dict[str, list[Property]] = defaultdict(list)
    for p in db_props:
        by_number[p.number].append(p)
        if p.source_system == objektdaten.SOURCE_SYSTEM and p.source_id:
            by_source[p.source_id].append(p)
    db_units = list(
        (await session.execute(select(Unit).where(Unit.tenant_id == tenant_id))).scalars()
    )
    prop_id_to_number = {p.id: p.number for p in db_props}
    units_by_key: dict[tuple[str, str], list[Unit]] = defaultdict(list)
    units_by_source: dict[str, list[Unit]] = defaultdict(list)
    for u in db_units:
        units_by_key[(prop_id_to_number.get(u.property_id, ""), u.number)].append(u)
        if u.source_system == objektdaten.SOURCE_SYSTEM and u.source_id:
            units_by_source[u.source_id].append(u)
    props.actual = len(by_source) or len(by_number)
    units.actual = len(units_by_source) or len(db_units)
    matched_prop_ids: set[uuid.UUID] = set()
    matched_unit_ids: set[uuid.UUID] = set()
    for item in prepared:
        src = item.row.source_number
        if item.number is None:
            props.missing.append({"schluessel": src, "grund": "; ".join(item.problems)})
            for u in item.row.units:
                units.missing.append(
                    {"schluessel": f"{src}/{u.number}", "grund": "Objekt nicht importierbar"}
                )
            continue
        candidates = by_source.get(src) or by_number.get(item.number) or []
        if not candidates:
            props.missing.append(
                {"schluessel": src, "nummer": item.number, "grund": "nicht angelegt"}
            )
            for u in item.row.units:
                units.missing.append({"schluessel": f"{src}/{u.number}", "grund": "Objekt fehlt"})
            continue
        if len(candidates) > 1:
            props.duplicate.append(
                {
                    "schluessel": src,
                    "anzahl": len(candidates),
                    "ids": [str(c.id) for c in candidates],
                }
            )
        prop = candidates[0]
        matched_prop_ids.add(prop.id)
        fields: list[dict[str, Any]] = []
        if not _same_text(prop.name, item.name):
            fields.append({"feld": "name", "soll": item.name, "ist": prop.name})
        if item.management_type and prop.management_type.value != item.management_type:
            fields.append(
                {
                    "feld": "management_type",
                    "soll": item.management_type,
                    "ist": prop.management_type.value,
                }
            )
        if fields:
            props.deviating.append({"schluessel": src, "nummer": item.number, "felder": fields})
        else:
            props.matched += 1
        for u in item.row.units:
            key = f"{src}/{u.number}"
            found = units_by_source.get(key) or units_by_key.get((item.number, u.number[:20])) or []
            if not found:
                units.missing.append({"schluessel": key, "grund": "nicht angelegt"})
                continue
            if len(found) > 1:
                units.duplicate.append(
                    {"schluessel": key, "anzahl": len(found), "ids": [str(x.id) for x in found]}
                )
            unit = found[0]
            matched_unit_ids.add(unit.id)
            ufields: list[dict[str, Any]] = []
            label = (u.label or None) and u.label[:50]
            location = (u.location or None) and u.location[:100]
            if label is not None and not _same_text(unit.label, label):
                ufields.append({"feld": "label", "soll": label, "ist": unit.label})
            if location is not None and not _same_text(unit.location, location):
                ufields.append({"feld": "location", "soll": location, "ist": unit.location})
            if ufields:
                units.deviating.append({"schluessel": key, "felder": ufields})
            else:
                units.matched += 1
    for p in db_props:
        if p.id not in matched_prop_ids and p.source_system == objektdaten.SOURCE_SYSTEM:
            props.extra.append({"schluessel": p.source_id or p.number, "nummer": p.number})
    for u in db_units:
        if u.id not in matched_unit_ids and u.source_system == objektdaten.SOURCE_SYSTEM:
            units.extra.append({"schluessel": u.source_id or u.number})
    if props.extra or units.extra:
        props.notes.append(
            "Zusätzliche Datensätze stammen aus früheren Importen und sind keine Differenz "
            "der Datei."
        )
    return props, units


async def reconcile_kontakte(
    session: Any, tenant_id: uuid.UUID, parsed: kontakte.ParsedKontakte, kind: str
) -> EntityReport:
    """Contacts of one list against the platform (key: ``external_ids["immoware24"]``)."""
    report = EntityReport(f"kontakte_{kind}")
    rows = parsed.rows
    report.target = len({r.external_id for r in rows})
    ids = sorted({r.external_id for r in rows})
    db_contacts: list[Contact] = []
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        db_contacts.extend(
            (
                await session.execute(
                    select(Contact).where(
                        Contact.tenant_id == tenant_id,
                        Contact.external_ids["immoware24"].astext.in_(chunk),
                        Contact.deleted_at.is_(None),
                    )
                )
            ).scalars()
        )
    by_id: dict[str, list[Contact]] = defaultdict(list)
    for c in db_contacts:
        by_id[str(c.external_ids.get("immoware24"))].append(c)
    report.actual = len(by_id)
    role = CONTACT_KINDS[kind].value
    seen: set[str] = set()
    for row in rows:
        if row.external_id in seen:
            continue
        seen.add(row.external_id)
        found = by_id.get(row.external_id) or []
        if not found:
            report.missing.append(
                {"schluessel": row.external_id, "name": row.name, "zeile": row.line}
            )
            continue
        # Multi person names create one contact per member with the same external id (M8-04).
        members = [c for c in found if c.external_ids.get("immoware24_member")]
        singles = [c for c in found if not c.external_ids.get("immoware24_member")]
        if len(singles) > 1:
            report.duplicate.append(
                {
                    "schluessel": row.external_id,
                    "anzahl": len(singles),
                    "ids": [str(c.id) for c in singles],
                }
            )
        contact = singles[0] if singles else (members[0] if members else found[0])
        fields: list[dict[str, Any]] = []
        if role not in (contact.roles or []):
            fields.append({"feld": "roles", "soll": role, "ist": ", ".join(contact.roles or [])})
        exported = contact.external_ids.get("immoware24_name")
        if exported and not members and not _same_text(str(exported), row.name):
            fields.append({"feld": "name", "soll": row.name, "ist": str(exported)})
        if fields:
            report.deviating.append({"schluessel": row.external_id, "felder": fields})
        else:
            report.matched += 1
    return report


async def reconcile_adressen(session: Any, tenant_id: uuid.UUID, table: Table) -> EntityReport:
    """Address list against the properties: missing object, deviating filled fields."""
    report = EntityReport("adressen")
    rows = [list(table.headers)] + [list(r.cells) for r in table.rows]
    index = adressen.map_headers(rows[0])
    props = {
        p.number: p
        for p in (
            await session.execute(select(Property).where(Property.tenant_id == tenant_id))
        ).scalars()
    }
    report.actual = len(props)
    for line, row in zip((r.line for r in table.rows), rows[1:], strict=True):
        raw = row[index["object"]] if index["object"] < len(row) else ""
        if not raw.strip():
            continue
        report.target += 1
        number, reason = adressen._object_number(raw)
        if number is None:
            report.missing.append({"schluessel": raw, "zeile": line, "grund": reason})
            continue
        prop = props.get(number)
        if prop is None:
            report.missing.append({"schluessel": number, "zeile": line, "grund": "Objekt fehlt"})
            continue
        fields: list[dict[str, Any]] = []
        for key in adressen.FIELDS:
            i = index.get(key)
            value = (row[i].strip() if i is not None and i < len(row) else "") or None
            current = (getattr(prop, key) or "").strip() or None
            if value and current and not adressen._same(current, value):
                fields.append({"feld": key, "soll": value, "ist": current})
        if fields:
            report.deviating.append({"schluessel": number, "felder": fields})
        else:
            report.matched += 1
    return report


# Opening balances (draft, G1 closed) ------------------------------------------------------


_KIND_WORDS = {
    "eigentuemer": ContractKind.OWNERSHIP,
    "eigentümer": ContractKind.OWNERSHIP,
    "ownership": ContractKind.OWNERSHIP,
    "mieter": ContractKind.TENANCY,
    "tenancy": ContractKind.TENANCY,
    "miete": ContractKind.TENANCY,
}


async def opening_balance_proposals(
    session: Any, tenant_id: uuid.UUID, table: Table, cutoff: date, number_map: dict[str, str]
) -> dict[str, Any]:
    """Balances per unit and contract at the cut-off date as a draft list, never posted.
    An entry is ``zugeordnet`` when exactly one contract of the unit (and kind, and name if
    needed) exists at the cut-off date, otherwise ``offen`` with the reason."""
    col = {label: table.column(*names) for label, names in SALDEN_COLUMNS.items()}
    props = {
        p.number: p
        for p in (
            await session.execute(select(Property).where(Property.tenant_id == tenant_id))
        ).scalars()
    }
    entries: list[dict[str, Any]] = []
    total = Decimal(0)
    counts: Counter[str] = Counter()
    for row in table.rows:
        obj = table.cell(row, col["Objekt-Nummer"])
        ve = table.cell(row, col["VE-Nummer"])
        raw_amount = table.cell(row, col["Saldo"])
        entry: dict[str, Any] = {
            "zeile": row.line,
            "objekt": obj,
            "ve": ve,
            "name": table.cell(row, col["Name"]),
            "vertragsart": table.cell(row, col["Vertragsart"]),
            "saldo": None,
            "contract_id": None,
            "status": "offen",
            "grund": None,
        }
        entries.append(entry)
        if obj is None or ve is None or raw_amount is None:
            entry["grund"] = "Objekt-Nummer, VE-Nummer oder Saldo fehlt"
            counts["offen"] += 1
            continue
        try:
            amount = parse_decimal(raw_amount).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            entry["grund"] = f"Saldo {raw_amount!r} nicht lesbar"
            counts["offen"] += 1
            continue
        entry["saldo"] = str(amount)
        total += amount
        number, note = objektdaten.normalise_number(obj, number_map)
        prop = props.get(number or "")
        if prop is None:
            entry["grund"] = note or "Objekt fehlt"
            counts["offen"] += 1
            continue
        unit = await session.scalar(
            select(Unit).where(Unit.property_id == prop.id, Unit.number == ve[:20])
        )
        if unit is None:
            entry["grund"] = "Einheit fehlt"
            counts["offen"] += 1
            continue
        wanted = _KIND_WORDS.get((entry["vertragsart"] or "").strip().casefold())
        query = select(Contract).where(
            Contract.unit_id == unit.id,
            Contract.start_date <= cutoff,
            (Contract.end_date.is_(None)) | (Contract.end_date >= cutoff),
        )
        if wanted is not None:
            query = query.where(Contract.kind == wanted)
        contracts = list((await session.execute(query)).scalars())
        if len(contracts) > 1 and entry["name"]:
            # Several contracts at the cut-off date (for example ownership and tenancy of a
            # SEV unit without Vertragsart): the exported name decides, never a guess.
            named = [
                c
                for c in contracts
                if _same_text((await session.get(Party, c.party_id)).name, entry["name"])
            ]
            if len(named) == 1:
                contracts = named
        if len(contracts) != 1:
            entry["grund"] = (
                "kein Vertrag zum Stichtag" if not contracts else "mehrere Verträge zum Stichtag"
            )
            counts["offen"] += 1
            continue
        entry["contract_id"] = str(contracts[0].id)
        entry["vertrag"] = contracts[0].number
        entry["vertragsart"] = contracts[0].kind.value
        entry["status"] = "zugeordnet"
        counts["zugeordnet"] += 1
    return {
        "stichtag": cutoff.isoformat(),
        "status": "entwurf",
        "hinweis": (
            "Eröffnungssalden sind ein Entwurf hinter Gate G1. Es wird nichts gebucht; die "
            "Übernahme als Eröffnungsbuchung setzt die Freigabe von G1 und eine Prüfung je "
            "Vertrag voraus."
        ),
        "summe": str(total.quantize(Decimal("0.01"))),
        "anzahl": dict(counts),
        "eintraege": entries[:2000],
    }


# Full run ----------------------------------------------------------------------------------


@dataclass
class FullRunResult:
    mode: str
    cutoff: date
    prechecks: list[Precheck]
    aborted: bool
    counts: dict[str, Any] = field(default_factory=dict)
    preview: dict[str, dict[str, int]] = field(default_factory=dict)
    import_reports: dict[str, Any] = field(default_factory=dict)
    entities: list[EntityReport] = field(default_factory=list)
    opening_balances: dict[str, Any] = field(default_factory=dict)
    updated: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def differences(self) -> int:
        return sum(e.differences for e in self.entities)

    def files(self) -> list[dict[str, Any]]:
        return [
            {
                "datei": p.name,
                "art": p.kind,
                "sha256": p.sha256,
                "bytes": p.bytes,
                "zeilen": p.row_count,
            }
            for p in self.prechecks
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "stichtag": self.cutoff.isoformat(),
            "abgebrochen": self.aborted,
            "dateien": self.files(),
            "vorpruefung": [p.as_dict() for p in self.prechecks],
            "counts": self.counts,
            "vorschau": self.preview,
            "importe": self.import_reports,
            "abgleich": [e.as_dict() for e in self.entities],
            "differenzen": self.differences,
            "aktualisiert": self.updated,
            "eroeffnungssalden": self.opening_balances,
            "dauer_ms": self.duration_ms,
        }


def _preview_counts(report: dict[str, Any], entity_prefix: str) -> dict[str, int]:
    out: Counter[str] = Counter()
    for key, value in report.get("counts", {}).items():
        if key.startswith(entity_prefix + "_"):
            out[key[len(entity_prefix) + 1 :]] += int(value)
    return dict(out)


async def _update_existing(
    session: Any, tenant_id: uuid.UUID, prepared: list[objektdaten.Prepared]
) -> list[dict[str, Any]]:
    """Idempotent re-import: name, label and location of existing records follow the file.
    The management type is never changed here (a change touches ledgers and allocations)."""
    updated: list[dict[str, Any]] = []
    for item in prepared:
        if item.number is None or item.problems:
            continue
        prop = await session.scalar(
            select(Property).where(Property.tenant_id == tenant_id, Property.number == item.number)
        )
        if prop is None:
            continue
        if not _same_text(prop.name, item.name):
            updated.append(
                {
                    "entitaet": "objekt",
                    "schluessel": item.row.source_number,
                    "feld": "name",
                    "alt": prop.name,
                    "neu": item.name,
                }
            )
            prop.name = item.name
        for u in item.row.units:
            unit = await session.scalar(
                select(Unit).where(Unit.property_id == prop.id, Unit.number == u.number[:20])
            )
            if unit is None:
                continue
            key = f"{item.row.source_number}/{u.number}"
            for attr, value in (
                ("label", (u.label or None) and u.label[:50]),
                ("location", (u.location or None) and u.location[:100]),
            ):
                if value is not None and not _same_text(getattr(unit, attr), value):
                    updated.append(
                        {
                            "entitaet": "einheit",
                            "schluessel": key,
                            "feld": attr,
                            "alt": getattr(unit, attr),
                            "neu": value,
                        }
                    )
                    setattr(unit, attr, value)
    if updated:
        await session.flush()
    return updated


async def run_full(
    session: Any,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    uploads: list[Upload],
    *,
    cutoff: date,
    mode: str,
    number_map: dict[str, str] | None = None,
    skip_handed_over: bool = False,
    update_existing: bool = False,
    recorder: Any | None = None,
) -> FullRunResult:
    """Pre-check, import (preview or apply) and reconciliation in the caller's session.

    ``mode``: ``preview`` (the caller rolls back), ``apply`` (writes) or ``abgleich`` (no
    import, comparison only). A failed pre-check aborts before anything is imported."""
    started = time.perf_counter()
    number_map = number_map or {}
    result = FullRunResult(mode, cutoff, [precheck(u) for u in uploads], aborted=False)
    kinds = Counter(u.kind for u in uploads)
    for kind, n in kinds.items():
        if n > 1 and kind not in CONTACT_KINDS:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Exporttyp {kind} darf nur einmal hochgeladen werden.",
            )
    if not any(
        p.kind in ("objektdaten", *CONTACT_KINDS, "adressen", *CONTRACT_KINDS)
        for p in result.prechecks
    ):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=(
                "Mindestens eine Objektdaten-, Kontakt-, Adress- oder Vertragsliste ist "
                "erforderlich."
            ),
        )
    if any(not p.ok for p in result.prechecks):
        result.aborted = True
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        return result
    write = mode in ("preview", "apply")
    counts: dict[str, Any] = {}
    obj = next((p for p in result.prechecks if p.kind == "objektdaten"), None)
    parsed_obj: objektdaten.ParsedObjektdaten | None = None
    if obj is not None:
        parsed_obj = objektdaten.parse_objektdaten(obj.text, obj.name)
        if write:
            prepared = objektdaten.prepare(parsed_obj, number_map)
            report = await objektdaten.apply_prepared(
                session,
                tenant_id,
                user_id,
                prepared,
                skip_handed_over=skip_handed_over,
                recorder=recorder,
                file_notes=obj.notes,
            )
            result.import_reports["objektdaten"] = report
            counts["objektdaten"] = report["counts"]
            result.preview["objekte"] = _preview_counts(report, "property")
            result.preview["einheiten"] = _preview_counts(report, "unit")
            if update_existing:
                result.updated.extend(await _update_existing(session, tenant_id, prepared))
    contact_lists: list[tuple[Precheck, kontakte.ParsedKontakte]] = []
    for p in result.prechecks:
        if p.kind in CONTACT_KINDS:
            parsed_k = kontakte.parse_kontakte(p.text, CONTACT_KINDS[p.kind], p.name)
            parsed_k.notes = [*p.notes, *parsed_k.notes]
            contact_lists.append((p, parsed_k))
    if contact_lists and write:
        merged = kontakte.ParsedKontakte()
        for _, parsed_k in contact_lists:
            merged.extend(parsed_k)
        report = await kontakte.apply_prepared(
            session,
            tenant_id,
            user_id,
            kontakte.prepare(merged),
            recorder=recorder,
            file_notes=merged.notes,
        )
        result.import_reports["kontakte"] = report
        counts["kontakte"] = report["counts"]
        result.preview["kontakte"] = dict(report["counts"])
    adr = next((p for p in result.prechecks if p.kind == "adressen"), None)
    if adr is not None and adr.table is not None and write:
        rows = [list(adr.table.headers)] + [list(r.cells) for r in adr.table.rows]
        report = await adressen.apply_address_list(session, tenant_id, rows, apply=True)
        result.import_reports["adressen"] = report
        counts["adressen"] = report["counts"]
        result.preview["adressen"] = dict(report["counts"])
    # Contract lists after objects and contacts (ownerships before tenancies inside).
    parsed_contracts: dict[ContractKind, vertraege.ParsedContracts] = {}
    for p in result.prechecks:
        if p.kind in CONTRACT_KINDS and p.table is not None:
            parsed_contracts[CONTRACT_KINDS[p.kind]] = vertraege.parse_contracts(
                p.table, CONTRACT_KINDS[p.kind]
            )
    if parsed_contracts and write:
        report = await vertraege.apply_contracts(
            session,
            tenant_id,
            user_id,
            parsed_contracts,
            number_map=number_map,
            recorder=recorder,
        )
        result.import_reports["vertraege"] = report
        counts["vertraege"] = report["counts"]
        for entity, entity_counts in report["counts"].items():
            result.preview[entity] = dict(entity_counts)
    # Reconciliation: target from the files, actual from the platform (after the import).
    if parsed_obj is not None:
        props, units = await reconcile_objektdaten(session, tenant_id, parsed_obj, number_map)
        result.entities.extend([props, units])
    for p, parsed_k in contact_lists:
        result.entities.append(await reconcile_kontakte(session, tenant_id, parsed_k, p.kind))
    if adr is not None and adr.table is not None:
        result.entities.append(await reconcile_adressen(session, tenant_id, adr.table))
    for kind in (ContractKind.OWNERSHIP, ContractKind.TENANCY):
        if kind in parsed_contracts:
            result.entities.append(
                await vertraege.reconcile_contracts(
                    session, tenant_id, parsed_contracts[kind], number_map, cutoff
                )
            )
    for p in result.prechecks:
        if p.kind == "bankumsaetze":
            e = EntityReport("bankumsaetze")
            e.target = p.row_count
            e.notes.append(
                "Nur Vorprüfung: Bankumsätze werden über den Importassistenten als Rohzeilen "
                "eingelesen und im täglichen Abgleichbericht verglichen; hier wird nichts gebucht."
            )
            result.entities.append(e)
    salden = next((p for p in result.prechecks if p.kind == "salden"), None)
    if salden is not None and salden.table is not None:
        result.opening_balances = await opening_balance_proposals(
            session, tenant_id, salden.table, cutoff, number_map
        )
    result.counts = counts
    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


# PDF draft -----------------------------------------------------------------------------------


def _pdf_escape(value: Any) -> str:
    return re.sub(
        r"[&<>]", lambda m: {"&": "&amp;", "<": "&lt;", ">": "&gt;"}[m.group()], str(value)
    )


def report_pdf(run: dict[str, Any], tenant_name: str) -> bytes:
    """Draft PDF of a stored run: files with checksums, per entity target/actual and the first
    differences. Marked as draft; no letterhead of a legal entity (internal working paper)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    body = ParagraphStyle("body", fontName="Helvetica", fontSize=9, leading=12)
    head = ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=13, leading=16)
    sub = ParagraphStyle("sub", fontName="Helvetica-Bold", fontSize=10, leading=13)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Abgleichbericht Vollimport (Entwurf)",
    )
    cutoff = run.get("stichtag") or ""
    if len(cutoff) == 10:
        cutoff = f"{cutoff[8:10]}.{cutoff[5:7]}.{cutoff[0:4]}"
    story: list[Any] = [
        Paragraph("ENTWURF: Abgleichbericht Vollimport Immoware24", head),
        Paragraph(
            _pdf_escape(
                f"Mandant {tenant_name}, Stichtag {cutoff}, Modus {run.get('mode', '')}, "
                f"Differenzen gesamt {run.get('differenzen', 0)}"
            ),
            body,
        ),
        Spacer(1, 4 * mm),
        Paragraph("Dateien und Prüfsummen (SHA-256)", sub),
    ]
    grid = TableStyle(
        [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, "#808080"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
    )
    rows = [["Datei", "Art", "Zeilen", "SHA-256"]] + [
        [
            Paragraph(_pdf_escape(f["datei"]), body),
            f["art"],
            str(f["zeilen"]),
            Paragraph(
                _pdf_escape(f["sha256"]),
                ParagraphStyle("m", fontName="Courier", fontSize=6.5, leading=8),
            ),
        ]
        for f in run.get("dateien", [])
    ]
    story.append(Table(rows, colWidths=[45 * mm, 28 * mm, 16 * mm, 85 * mm], style=grid))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Soll (Datei) gegen Ist (Plattform) je Entität", sub))
    rows = [["Entität", "Soll", "Ist", "Übereinstimmend", "Fehlend", "Doppelt", "Abweichend"]] + [
        [
            e["entitaet"],
            str(e["soll"]),
            str(e["ist"]),
            str(e["uebereinstimmend"]),
            str(len(e["fehlend"])),
            str(len(e["doppelt"])),
            str(len(e["abweichend"])),
        ]
        for e in run.get("abgleich", [])
    ]
    story.append(
        Table(
            rows,
            colWidths=[40 * mm, 18 * mm, 18 * mm, 30 * mm, 20 * mm, 20 * mm, 24 * mm],
            style=grid,
        )
    )
    for e in run.get("abgleich", []):
        diffs = (
            [("fehlend", d) for d in e["fehlend"]]
            + [("doppelt", d) for d in e["doppelt"]]
            + [("abweichend", d) for d in e["abweichend"]]
        )
        if not diffs:
            continue
        story.append(Spacer(1, 3 * mm))
        story.append(
            Paragraph(
                _pdf_escape(
                    f"Differenzen {e['entitaet']} (erste {min(len(diffs), 60)} von {len(diffs)})"
                ),
                sub,
            )
        )
        rows = [["Art", "Schlüssel", "Details"]]
        for kind, d in diffs[:60]:
            details = (
                d.get("grund")
                or "; ".join(
                    f"{f['feld']}: Soll {f.get('soll')!r}, Ist {f.get('ist')!r}"
                    for f in d.get("felder", [])
                )
                or (f"{d.get('anzahl')} Datensätze" if d.get("anzahl") else "")
            )
            rows.append(
                [
                    kind,
                    Paragraph(_pdf_escape(d.get("schluessel", "")), body),
                    Paragraph(_pdf_escape(details), body),
                ]
            )
        story.append(Table(rows, colWidths=[20 * mm, 40 * mm, 114 * mm], style=grid))
    ob = run.get("eroeffnungssalden") or {}
    if ob:
        story.append(Spacer(1, 4 * mm))
        story.append(
            Paragraph("Eröffnungssalden-Vorschlag (Entwurf, G1 geschlossen, keine Buchung)", sub)
        )
        story.append(
            Paragraph(
                _pdf_escape(
                    f"Summe {rec.format_eur(ob.get('summe'))} EUR, Einträge {ob.get('anzahl')}"
                ),
                body,
            )
        )
    doc.build(story)
    return buf.getvalue()
