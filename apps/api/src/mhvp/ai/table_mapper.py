"""Deterministic fast path for CSV/XLSX contact imports (M7-06, operator 25.09.2026,
docs/rules/M7-06.md, Produktschutz "Tabellenimport deterministisch, KI nur für
Spaltenzuordnung und Restzeilen").

Instead of sending every row to the LLM, one small ``map_columns`` call returns which source
column holds which target field (see ``mhvp.ai.tasks.ColumnMappingResult``); this module then
splits names, addresses, phones, e-mails and IBAN in Python, reusing the platform validators via
``mhvp.ai.imports`` / ``mhvp.contacts.services`` further down the pipeline. Rows that cannot be
mapped with confidence (multiple persons in one cell, no name at all, ambiguous company/person
split) are collected as ``residual`` rows and still go through the LLM, just far fewer of them.

Nothing here talks to a provider; ``gateway.py`` calls ``build_column_samples`` for the
``map_columns`` prompt and ``apply_mapping`` for the deterministic pass.
"""

import io
import re
from dataclasses import dataclass, field
from typing import Any

from openpyxl import load_workbook

from mhvp.ai.tasks import TargetField

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _decode_text(data: bytes) -> str:
    """Same encoding chain as ``gateway.decode_text`` (kept local to avoid a circular import:
    ``gateway`` calls into this module for the fast path)."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


MIN_CONFIDENCE = 0.6  # below this, or without a header, the whole run falls back (rule 2)
SAMPLE_ROWS = 5

COMPANY_MARKERS = (
    "gmbh",
    "mbh",
    "ug (haftungsbeschränkt)",
    "ug haftungsbeschränkt",
    " ug",
    "ohg",
    "kg",
    "gbr",
    "e.k.",
    "ek",
    "ag",
    "e.v.",
    "ev",
    "stiftung",
    "genossenschaft",
    "gesellschaft",
    "verwaltung",
    "hausverwaltung",
    "wohnungsbau",
)
# Whole-word markers only (avoids false positives like "Krug" containing "ug"); checked against
# a normalised token list, not a raw substring search.
SALUTATIONS = {"herr": "Herr", "frau": "Frau"}
TITLES = {"dr", "dr.", "prof", "prof.", "prof.dr", "dipl.-ing", "dipl.-ing.", "dipl-ing"}
AMBIGUOUS_JOINERS = (" und ", " & ", "/", " sowie ")


class NoHeaderError(Exception):
    """The table has no usable header row (map_columns said ``has_header: false``)."""


@dataclass
class TableData:
    filename: str
    header: list[str]
    rows: list[list[str]]  # data rows only, aligned to header length
    raw_chars: int


def _clean_row(row: list[Any]) -> list[str]:
    cells = ["" if c is None else str(c).strip() for c in row]
    while cells and not cells[-1]:
        cells.pop()
    return cells


def _pad(row: list[str], width: int) -> list[str]:
    return (row + [""] * width)[:width]


def load_csv(data: bytes) -> tuple[list[str], list[list[str]], int]:
    import csv

    text = _decode_text(data)

    class _Semicolon(csv.excel):
        delimiter = ";"

    try:
        dialect: Any = csv.Sniffer().sniff(text[:4096], delimiters=";,\t") if text else csv.excel
    except csv.Error:
        # Irregular rows in the sniffed sample (e.g. a short one): ";" is the common German
        # export delimiter and a safer default than guessing further.
        dialect = _Semicolon
    all_rows = [_clean_row(r) for r in csv.reader(io.StringIO(text), dialect)]
    all_rows = [r for r in all_rows if any(r)]
    if not all_rows:
        return [], [], len(text)
    header, body = all_rows[0], all_rows[1:]
    width = len(header)
    return header, [_pad(r, width) for r in body], len(text)


def load_xlsx(data: bytes) -> tuple[list[str], list[list[str]], int]:
    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = book.worksheets[0]
    all_rows = [_clean_row(list(r)) for r in sheet.iter_rows(values_only=True)]
    all_rows = [r for r in all_rows if any(r)]
    raw_chars = sum(len(" | ".join(r)) for r in all_rows)
    if not all_rows:
        return [], [], raw_chars
    header, body = all_rows[0], all_rows[1:]
    width = len(header)
    return header, [_pad(r, width) for r in body], raw_chars


def load_table(mime_type: str, data: bytes, filename: str) -> TableData:
    header, rows, raw_chars = load_xlsx(data) if mime_type == XLSX else load_csv(data)
    return TableData(filename=filename, header=header, rows=rows, raw_chars=raw_chars)


def column_samples(table: TableData, *, sample_rows: int = SAMPLE_ROWS) -> str:
    """Header plus at most ``sample_rows`` sample rows, for the ``map_columns`` prompt."""
    lines = ["Kopfzeile: " + " | ".join(table.header)]
    for i, row in enumerate(table.rows[:sample_rows], start=1):
        lines.append(f"Beispielzeile {i}: " + " | ".join(row))
    return "\n".join(lines)


# Deterministic row processing --------------------------------------------------------------


def _looks_like_company(raw: str) -> bool:
    tokens = re.findall(r"[\wÄÖÜäöüß.\-]+", raw.lower())
    return any(t.strip(".") in {m.strip(" .") for m in COMPANY_MARKERS} for t in tokens) or any(
        marker in raw.lower() for marker in ("gmbh", "hausverwaltung")
    )


def _is_ambiguous_persons(raw: str) -> bool:
    lowered = f" {raw.lower()} "
    return any(joiner in lowered for joiner in AMBIGUOUS_JOINERS)


@dataclass
class ParsedName:
    kind: str  # "person" | "company"
    salutation: str | None = None
    title: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    ambiguous: bool = False


def parse_name(raw: str) -> ParsedName | None:
    """Splits a single "full name" cell. Returns ``None`` (residual) when the cell names more
    than one person, is empty, or cannot be read as a name at all."""
    raw = raw.strip()
    if not raw:
        return None
    if _looks_like_company(raw):
        return ParsedName(kind="company", company_name=raw)
    if _is_ambiguous_persons(raw):
        return None  # e.g. "Hans und Erika Müller": a human decides who is the main contact
    tokens = raw.split()
    idx = 0
    salutation: str | None = None
    if tokens and tokens[0].strip(".").lower() in SALUTATIONS:
        salutation = SALUTATIONS[tokens[0].strip(".").lower()]
        idx = 1
    title_tokens: list[str] = []
    while idx < len(tokens) and tokens[idx].strip(".").lower().replace("-", "") in {
        t.strip(".").replace("-", "") for t in TITLES
    }:
        title_tokens.append(tokens[idx])
        idx += 1
    title = " ".join(title_tokens) or None
    remaining = tokens[idx:]
    if not remaining:
        return None  # salutation/title only, no actual name
    if len(remaining) == 1:
        return ParsedName(kind="person", salutation=salutation, title=title, last_name=remaining[0])
    return ParsedName(
        kind="person",
        salutation=salutation,
        title=title,
        first_name=remaining[0],
        last_name=" ".join(remaining[1:]),
    )


_STREET_RE = re.compile(r"^(?P<street>.*\D)\s*(?P<number>\d+\s*[a-zA-Z]?(?:[-/]\d+[a-zA-Z]?)?)$")


def split_street(raw: str) -> tuple[str | None, str | None]:
    raw = raw.strip()
    if not raw:
        return None, None
    match = _STREET_RE.match(raw)
    if not match:
        return raw, None
    return match.group("street").strip(" ,"), match.group("number").replace(" ", "")


_POSTAL_CITY_RE = re.compile(r"^(?P<plz>\d{4,5})\s+(?P<city>.+)$")


def split_postal_city(raw: str) -> tuple[str | None, str | None]:
    raw = raw.strip()
    if not raw:
        return None, None
    match = _POSTAL_CITY_RE.match(raw)
    if not match:
        return None, raw
    return match.group("plz"), match.group("city").strip()


def split_list(raw: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;,/]| und ", raw) if p.strip()]


ROLE_MAP = {
    "eigentümer": "owner",
    "eigentuemer": "owner",
    "owner": "owner",
    "vermieter": "owner",
    "mieter": "tenant",
    "tenant": "tenant",
    "dienstleister": "provider",
    "provider": "provider",
}


def _role_from_text(raw: str) -> str | None:
    return ROLE_MAP.get(raw.strip().lower())


@dataclass
class MappedRows:
    contacts: list[dict[str, Any]]
    residual: list[dict[str, Any]] = field(default_factory=list)  # {"row": int, "cells": {...}}
    processed_rows: int = 0


def apply_mapping(
    table: TableData,
    mappings: dict[str, TargetField],
    *,
    default_role: str | None,
) -> MappedRows:
    """Deterministic pass (Python only, no AI): builds ``ExtractedContact``-shaped dicts for
    every row it can read with confidence; everything else goes to ``residual`` for the LLM."""
    by_field: dict[str, list[str]] = {}
    for column, target in mappings.items():
        if target == "ignore" or column not in table.header:
            continue
        by_field.setdefault(target, []).append(column)
    col_index = {name: i for i, name in enumerate(table.header)}

    def cell(row: list[str], field_name: str) -> str:
        columns = by_field.get(field_name, [])
        for name in columns:
            i = col_index.get(name)
            if i is not None and i < len(row) and row[i]:
                return row[i]
        return ""

    contacts: list[dict[str, Any]] = []
    residual: list[dict[str, Any]] = []
    for row_number, row in enumerate(table.rows, start=2):  # header is row 1
        parsed: ParsedName | None
        if by_field.get("name_full"):
            parsed = parse_name(cell(row, "name_full"))
        else:
            company = cell(row, "company_name")
            if company:
                parsed = ParsedName(kind="company", company_name=company)
            else:
                last = cell(row, "last_name")
                first = cell(row, "first_name")
                salutation_raw = cell(row, "salutation")
                if not last:
                    parsed = None
                else:
                    parsed = ParsedName(
                        kind="person",
                        salutation=SALUTATIONS.get(salutation_raw.strip(".").lower())
                        if salutation_raw
                        else None,
                        title=cell(row, "title") or None,
                        first_name=first or None,
                        last_name=last,
                    )
        if parsed is None:
            residual.append(
                {"row": row_number, "cells": dict(zip(table.header, row, strict=False))}
            )
            continue

        street, house_number = (
            split_street(cell(row, "address_full"))
            if by_field.get("address_full")
            else (cell(row, "street") or None, cell(row, "house_number") or None)
        )
        postal_code, city = (
            split_postal_city(cell(row, "postal_city"))
            if by_field.get("postal_city")
            else (cell(row, "postal_code") or None, cell(row, "city") or None)
        )
        phones = split_list(cell(row, "phone")) if cell(row, "phone") else []
        emails = split_list(cell(row, "email")) if cell(row, "email") else []
        iban = cell(row, "iban") or None
        role = _role_from_text(cell(row, "role")) if cell(row, "role") else default_role
        contacts.append(
            {
                "source_row": row_number,
                "kind": parsed.kind,
                "salutation": parsed.salutation,
                "title": parsed.title,
                "first_name": parsed.first_name,
                "last_name": parsed.last_name,
                "company_name": parsed.company_name,
                "street": street,
                "house_number": house_number,
                "postal_code": postal_code,
                "city": city,
                "phones": phones,
                "emails": emails,
                "iban": iban,
                "role": role,
                "unit_number": cell(row, "unit_number") or None,
                "co_members": [],
                "confidence": 1.0,
            }
        )
    return MappedRows(contacts=contacts, residual=residual, processed_rows=len(table.rows))


def residual_table_text(table: TableData, residual: list[dict[str, Any]]) -> str:
    """Renders the residual rows the same way ``gateway._table_text`` would, so the existing
    row-chunked extraction prompt and row numbering (``source_row``) keep working unchanged."""
    lines = [f"Zeile 1: {' | '.join(table.header)}"]
    for item in residual:
        row_number, cells = item["row"], item["cells"]
        values = [cells.get(name, "") for name in table.header]
        lines.append(f"Zeile {row_number}: " + " | ".join(values))
    return "\n".join(lines)
