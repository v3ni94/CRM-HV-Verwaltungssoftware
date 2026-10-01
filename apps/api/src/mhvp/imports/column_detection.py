"""Header heuristics for exports of unknown layout (13.1, M8, Q08-01, AE37).

The column names of the Immoware24 exports are not specified (13.1: "Unbekannte Spalten anhand
echter Exportdateien prüfen, manuell zuordnen und das Mapping versionieren"). This module does
not know any Immoware24 format. It works on the header row of any CSV or XLSX file and on the
platform target fields of a report type (``mhvp.imports.fields.FIELDS``):

* ``detect_header_row``: which of the first rows of a sheet is the header (title lines above
  the header are common in spreadsheet exports). Scored by filled text cells, distinct names,
  terms of the target fields and data rows below; every candidate carries a German reason.
* ``propose_columns``: one proposal per target field. A stored assignment of the tenant for the
  report type wins (``import_column_assignment``, confirmed by a user on a real file); then the
  field label and name, a small list of general German business terms (no Immoware24 column
  names), part words and string similarity. Number and date fields check the sample values.
  Every header is used once; the result is a proposal the user confirms, never an import.
* ``check_report``: validation report without saving anything: required columns (assigned,
  missing, not in the file, empty), per field filled, empty, errors and example values, sample
  rows with converted values and errors, rows valid and invalid.

The heuristic is deterministic (no AI, no network) and decides nothing: a proposal only fills
the mapping form (rule 0.1.3, 0.1.6).
"""

from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from openpyxl import load_workbook

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.imports import services as _services  # registers the W3 and W5 target fields
from mhvp.imports.csvtext import column_key
from mhvp.imports.fields import FIELDS, Field, convert, parse_date, parse_decimal
from mhvp.imports.models import ReportType

SCAN_ROWS = 30
SAMPLE_VALUES = 20
MIN_SCORE = 60  # percent; below this no proposal is made
SURE_SCORE = 90

# Scores in percent per basis of a proposal.
SCORE_STORED = 100
SCORE_LABEL = 95
SCORE_NAME = 90
SCORE_TERM = 85
SCORE_PART = 70
SIMILARITY_MIN = 0.75

# Abbreviations of general German spelling, expanded per word before comparing.
_ABBREVIATIONS = {
    "nr": "nummer",
    "str": "strasse",
    "tel": "telefon",
    "qm": "m2",
}
# General German business terms per platform field name (not Immoware24 column names, rule
# 0.1.3): they only produce a proposal with basis "Fachbegriff" that the user confirms.
TERMS: dict[str, tuple[str, ...]] = {
    "property_number": ("Objekt", "Objektnummer", "Objekt Nummer"),
    "unit_number": ("Einheit", "Einheitennummer", "Einheit Nummer"),
    "number": ("Nummer",),
    "postal_code": ("Postleitzahl",),
    "street": ("Strasse",),
    "house_number": ("Hausnr", "Haus Nummer"),
    "city": ("Stadt", "Wohnort"),
    "phone": ("Telefonnummer", "Rufnummer"),
    "email": ("Mail", "E-Mail-Adresse", "Mailadresse"),
    "last_name": ("Familienname",),
    "company_name": ("Firmenname", "Unternehmen"),
    "living_area_sqm": ("Wohnfläche", "Fläche"),
    "mea": ("MEA", "Miteigentumsanteile"),
    "start_date": ("Beginn", "Vertragsbeginn"),
    "end_date": ("Ende", "Vertragsende"),
    "valid_from": ("gültig von", "ab"),
    "gross": ("Betrag", "Bruttobetrag"),
    "vat_percent": ("Steuersatz", "MwSt", "USt"),
}

# Source of a report type in the table of section 13.1 (spec terms, not export names).
SPEC_SOURCES: dict[ReportType, str] = {
    ReportType.PROPERTIES: "Reports: Objektliste",
    ReportType.UNITS: "Reports: Belegungsliste",
    ReportType.CONTACTS: "Reports: Adressbuch, Eigentümer, Mieter",
    ReportType.TENANCIES: "Reports: Mietverträge",
    ReportType.OWNERSHIPS: "Reports: Eigentümerverträge",
    ReportType.PAYMENTS: "Verträge: Liste vereinbarter Zahlungen",
    ReportType.JOURNAL: "Buchungen: Journal",
    ReportType.BANK_TRANSACTIONS: "Bankumsätze",
    ReportType.SEPA_OVERVIEW: "Verträge: SEPA-Übersicht je Objekt",
    ReportType.CHART_OF_ACCOUNTS: "Buchungen: Konten",
    ReportType.BANK_HISTORY: "Bankumsätze mit Zuordnung aus Journal",
    ReportType.DOCUMENT_INDEX: "DMS",
    ReportType.TICKET_HISTORY: "Tickets",
    ReportType.OPEN_ITEMS: "Buchungen: offene Posten",
    ReportType.DEPOSIT: "Reports: Kautionen",
    ReportType.ALLOCATION_KEY: "Reports: Umlageschlüssel",
    ReportType.METER: "Reports: Zähler",
    ReportType.ENERGY_CERTIFICATE: "Reports: Energieausweise",
    ReportType.SERVICE_PROVIDER: "Reports: Dienstleister",
    ReportType.PORTAL_USER: "Reports: Portalnutzer",
}

BASIS_LABELS = {
    "stored": "gespeicherte Zuordnung",
    "label": "Feldbezeichnung",
    "name": "Feldname",
    "term": "Fachbegriff",
    "part": "Teilwort",
    "similar": "ähnliche Schreibweise",
}


def header_key(name: str) -> str:
    """Key of a stored assignment: ``column_key`` (case, spacing, umlauts do not matter)."""
    return column_key(name)[:200]


_SPELLING: dict[str, str | int | None] = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "²": "2"}
_SPELLING_TABLE = str.maketrans(_SPELLING)


def _words(name: str) -> list[str]:
    text = name.strip().casefold().translate(_SPELLING_TABLE)
    return [w for w in re.split(r"[^a-z0-9]+", text) if w]


def compare_key(name: str) -> str:
    """Key for the heuristic: words joined, general abbreviations expanded."""
    return "".join(_ABBREVIATIONS.get(w, w) for w in _words(name))


def _base_label(field: Field) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", field.label or field.name).strip()


def field_terms(field: Field) -> list[tuple[str, str]]:
    """Comparison keys of a target field with their basis, strongest first, no duplicates."""
    terms: list[tuple[str, str]] = [
        (compare_key(field.label or field.name), "label"),
        (compare_key(_base_label(field)), "label"),
        (compare_key(field.name), "name"),
    ]
    terms += [(compare_key(t), "term") for t in TERMS.get(field.name, ())]
    seen: set[str] = set()
    result = []
    for key, basis in terms:
        if key and key not in seen:
            seen.add(key)
            result.append((key, basis))
    return result


# Reading the first rows ------------------------------------------------------------------


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def read_head(
    data: bytes, mime_type: str, sheet: str | None, limit: int = SCAN_ROWS
) -> tuple[list[list[Any]], list[str], str | None]:
    """First ``limit`` rows of a sheet or CSV file, the sheet names and the sheet read.

    Same reader rules as ``services.read_table`` (first sheet by default, CSV dialect sniffed
    from the first 4 KiB), so the detected row number fits the later staging call."""
    if mime_type == _services.XLSX:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        if sheet is not None and sheet not in book.sheetnames:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Tabellenblatt {sheet!r} fehlt.")
        name = sheet or book.sheetnames[0]
        rows = [
            [_plain(c) for c in r] for r in book[name].iter_rows(values_only=True, max_row=limit)
        ]
        return rows, list(book.sheetnames), name
    if mime_type in ("text/csv", "text/plain"):
        text = data.decode("utf-8-sig", errors="replace")
        try:
            dialect: Any = csv.Sniffer().sniff(text[:4096], delimiters=";,\t")
        except csv.Error:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Trennzeichen der CSV-Datei nicht erkannt."
            ) from None
        rows = []
        for row in csv.reader(io.StringIO(text), dialect):
            rows.append(list(row))
            if len(rows) >= limit:
                break
        return rows, [], None
    raise ProblemError(ErrorCodes.VALIDATION, detail="Nur Excel (xlsx) oder CSV.")


# Header row ------------------------------------------------------------------------------


def _is_value(cell: Any) -> bool:
    """True for numbers and dates (data, not a header)."""
    if isinstance(cell, int | float | Decimal | date) and not isinstance(cell, bool):
        return True
    text = str(cell).strip()
    for parse in (parse_decimal, parse_date):
        try:
            parse(text)
            return True
        except ValueError:
            continue
    return False


def _filled(row: list[Any]) -> list[Any]:
    return [c for c in row if c is not None and str(c).strip() != ""]


@dataclass(frozen=True)
class HeaderCandidate:
    row: int  # 1 based
    score: int  # percent
    filled: int
    text_cells: int
    matched_terms: list[str]
    duplicates: list[str]
    reason: str


def _vocabulary(report_type: ReportType, stored: dict[str, str | None]) -> set[str]:
    vocab = {key for f in FIELDS[report_type] for key, _ in field_terms(f)}
    vocab |= {compare_key(h) for h in stored}
    return vocab


def detect_header_row(
    rows: list[list[Any]],
    report_type: ReportType,
    stored: dict[str, str | None] | None = None,
) -> list[HeaderCandidate]:
    """Header row candidates, best first (ties: the upper row). Empty list without text rows.

    ``stored`` maps stored header keys to target fields; their headers count as known terms."""
    stored = stored or {}
    vocab = _vocabulary(report_type, stored)
    stored_keys = set(stored)
    width = max((len(_filled(r)) for r in rows), default=0)
    candidates: list[HeaderCandidate] = []
    for index, row in enumerate(rows):
        cells = _filled(row)
        if len(cells) < 2:
            continue
        texts = [str(c).strip() for c in cells if not _is_value(c)]
        names = Counter(texts)
        duplicates = sorted(n for n, count in names.items() if count > 1)
        matched = [
            t
            for t in dict.fromkeys(texts)
            if compare_key(t) in vocab or header_key(t) in stored_keys
        ]
        below = rows[index + 1] if index + 1 < len(rows) else []
        data_below = len(_filled(below)) >= max(1, len(cells) // 2)
        text_ratio = len(texts) / len(cells)
        distinct = len(names) / len(texts) if texts else 0.0
        known = min(len(matched) / max(1, min(3, len(FIELDS[report_type]) or 3)), 1.0)
        score = (
            0.35 * text_ratio
            + 0.25 * (len(cells) / width if width else 0)
            + 0.10 * distinct
            + 0.20 * known
            + 0.10 * (1.0 if data_below else 0.0)
        )
        reason = (
            f"{len(texts)} von {len(cells)} Zellen Text, {len(matched)} Begriff(e) erkannt"
            + (", Datenzeile darunter" if data_below else ", keine Datenzeile darunter")
            + (f", doppelte Überschriften: {', '.join(duplicates)}" if duplicates else "")
        )
        candidates.append(
            HeaderCandidate(
                row=index + 1,
                score=round(score * 100),
                filled=len(cells),
                text_cells=len(texts),
                matched_terms=matched,
                duplicates=duplicates,
                reason=reason,
            )
        )
    return sorted(candidates, key=lambda c: (-c.score, c.row))


# Column proposal -------------------------------------------------------------------------


@dataclass
class _Candidate:
    field: str
    header: str
    score: int
    basis: str
    note: str | None = None


def _type_share(field: Field, values: list[Any]) -> float | None:
    """Share of sample values readable as the field type (number, date); None if untyped."""
    if field.kind not in ("decimal", "date") or not values:
        return None
    parse = parse_decimal if field.kind == "decimal" else parse_date
    ok = 0
    for value in values:
        try:
            parse(value)
            ok += 1
        except ValueError:
            continue
    return ok / len(values)


def _match(field: Field, header: str) -> tuple[int, str] | None:
    key = compare_key(header)
    if not key:
        return None
    best: tuple[int, str] | None = None
    for term, basis in field_terms(field):
        if key == term:
            score = {"label": SCORE_LABEL, "name": SCORE_NAME, "term": SCORE_TERM}[basis]
            found = (score, basis)
        elif min(len(key), len(term)) >= 4 and (term in key or key in term):
            found = (SCORE_PART, "part")
        else:
            ratio = SequenceMatcher(None, key, term).ratio()
            if ratio < SIMILARITY_MIN:
                continue
            found = (round(ratio * 80), "similar")
        if best is None or found[0] > best[0]:
            best = found
    return best


def sample_values(rows: list[dict[str, Any]], header: str, limit: int = SAMPLE_VALUES) -> list[Any]:
    values = []
    for raw in rows:
        cell = raw.get(header)
        if cell is None or str(cell).strip() == "":
            continue
        values.append(cell)
        if len(values) >= limit:
            break
    return values


def propose_columns(
    report_type: ReportType,
    headers: list[str],
    rows: list[dict[str, Any]],
    stored: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Proposal per target field: header, score (percent), basis, status and alternatives.

    ``rows`` are raw staged rows (samples), ``stored`` maps stored header keys to the target
    field (``None``: the header is deliberately not imported)."""
    stored = stored or {}
    fields = FIELDS[report_type]
    by_name = {f.name: f for f in fields}
    ignored = [h for h in headers if header_key(h) in stored and stored[header_key(h)] is None]
    candidates: list[_Candidate] = []
    for header in headers:
        target = stored.get(header_key(header))
        if header in ignored:
            continue
        if target in by_name:
            candidates.append(_Candidate(target, header, SCORE_STORED, "stored"))
        samples = sample_values(rows, header)
        for f in fields:
            if f.name == target:
                continue
            found = _match(f, header)
            if found is None:
                continue
            score, basis = found
            note = None
            share = _type_share(f, samples)
            if share is not None and share < 0.5:
                score, note = score // 2, "Beispielwerte passen nicht zum Feldtyp"
            candidates.append(_Candidate(f.name, header, score, basis, note))
    order = {f.name: i for i, f in enumerate(fields)}
    position = {h: i for i, h in enumerate(headers)}
    candidates.sort(key=lambda c: (-c.score, order[c.field], position[c.header]))
    chosen: dict[str, _Candidate] = {}
    used: set[str] = set()
    for c in candidates:
        if c.score < MIN_SCORE or c.field in chosen or c.header in used:
            continue
        chosen[c.field] = c
        used.add(c.header)
    result_fields = []
    for f in fields:
        pick = chosen.get(f.name)
        alternatives = [
            {"header": c.header, "score": c.score, "basis": c.basis}
            for c in candidates
            if c.field == f.name and (pick is None or c.header != pick.header)
        ][:3]
        if pick is None:
            status = "none"
        elif pick.basis == "stored":
            status = "stored"
        elif pick.score >= SURE_SCORE:
            status = "sure"
        else:
            status = "check"
        result_fields.append(
            {
                "name": f.name,
                "label": f.label or f.name,
                "required": f.required,
                "header": pick.header if pick else None,
                "score": pick.score if pick else 0,
                "basis": pick.basis if pick else None,
                "basis_label": BASIS_LABELS[pick.basis] if pick else None,
                "status": status,
                "note": pick.note if pick else None,
                "alternatives": alternatives,
            }
        )
    columns = {f["name"]: f["header"] for f in result_fields if f["header"]}
    return {
        "report_type": report_type.value,
        "headers": headers,
        "columns": columns,
        "fields": result_fields,
        "unassigned_headers": [h for h in headers if h not in used and h not in ignored],
        "ignored_headers": ignored,
        "missing_required": [f.name for f in fields if f.required and f.name not in columns],
        "stored_used": sum(1 for f in result_fields if f["status"] == "stored"),
    }


# Validation report -----------------------------------------------------------------------


def _empty(cell: Any) -> bool:
    return cell is None or (isinstance(cell, str) and cell.strip() == "")


def check_report(
    report_type: ReportType,
    headers: list[str],
    rows: list[tuple[int, dict[str, Any]]],
    columns: dict[str, str],
    value_maps: dict[str, dict[str, str]],
    sample_size: int = 5,
) -> dict[str, Any]:
    """Validation report of a mapping on staged rows; changes nothing.

    ``rows`` are (row number, raw row). Required columns get a status ``ok``, ``partly_empty``
    (some rows empty: these rows fail), ``empty`` (column assigned but no value), ``missing``
    (no column assigned) or ``not_in_file`` (assigned header is not in this file)."""
    fields = FIELDS[report_type]
    header_set = set(headers)
    not_in_file = sorted({h for h in columns.values() if h not in header_set})
    usage = Counter(columns.values())
    assigned_twice = sorted(h for h, n in usage.items() if n > 1)
    labels = {f.name: f"{f.label or f.name}: " for f in fields}
    per_field: dict[str, dict[str, Any]] = {
        f.name: {"filled": 0, "empty": 0, "errors": 0, "examples": []} for f in fields
    }
    valid = invalid = 0
    samples: list[dict[str, Any]] = []
    error_rows: list[dict[str, Any]] = []
    mapped = [h for h in columns.values() if h in header_set]
    for number, raw in rows:
        for f in fields:
            header = columns.get(f.name)
            if not header or header not in header_set:
                continue
            stats = per_field[f.name]
            cell = raw.get(header)
            if _empty(cell):
                stats["empty"] += 1
            else:
                stats["filled"] += 1
                if len(stats["examples"]) < 3 and str(cell) not in stats["examples"]:
                    stats["examples"].append(str(cell))
        if not fields:
            continue
        values, errors = convert(report_type, raw, columns, value_maps)
        for message in errors:
            for name, prefix in labels.items():
                if message.startswith(prefix):
                    per_field[name]["errors"] += 1
                    break
        entry = {
            "row_number": number,
            "raw": {h: raw.get(h) for h in mapped},
            "values": values,
            "errors": errors,
        }
        if errors:
            invalid += 1
            if len(error_rows) < sample_size:
                error_rows.append(entry)
        else:
            valid += 1
        if len(samples) < sample_size:
            samples.append(entry)
    required = []
    for f in fields:
        if not f.required:
            continue
        header = columns.get(f.name)
        stats = per_field[f.name]
        if not header:
            status = "missing"
        elif header not in header_set:
            status = "not_in_file"
        elif rows and stats["filled"] == 0:
            status = "empty"
        elif stats["empty"]:
            status = "partly_empty"
        else:
            status = "ok"
        required.append(
            {
                "name": f.name,
                "label": f.label or f.name,
                "header": header,
                "status": status,
                "empty": stats["empty"],
            }
        )
    blocking = {"missing", "not_in_file", "empty"}
    return {
        "report_type": report_type.value,
        "rows": len(rows),
        "valid": valid,
        "invalid": invalid,
        "staged_only": not fields,
        "required": required,
        "fields": [
            {
                "name": f.name,
                "label": f.label or f.name,
                "header": columns.get(f.name),
                **per_field[f.name],
            }
            for f in fields
            if columns.get(f.name)
        ],
        "not_in_file": not_in_file,
        "assigned_twice": assigned_twice,
        "unassigned_headers": [h for h in headers if h not in usage],
        "sample_rows": samples,
        "error_rows": error_rows,
        "ready": not not_in_file and not any(r["status"] in blocking for r in required),
    }
