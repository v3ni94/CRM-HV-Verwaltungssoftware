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
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from openpyxl import load_workbook
from pydantic import BaseModel, ConfigDict, Field

from mhvp.ai.tasks import TargetField
from mhvp.imports.fields import parse_date, parse_decimal

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


def mapping_usable(output: dict[str, Any] | None) -> bool:
    """Rule 2 of the M7-06 plan: the deterministic pass runs only with a header row and an
    overall confidence of at least ``MIN_CONFIDENCE``; otherwise every row goes through the
    LLM (same condition as ``gateway._run_fast_contacts``)."""
    return (
        output is not None
        and bool(output.get("has_header", True))
        and float(output.get("confidence") or 0) >= MIN_CONFIDENCE
    )


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


# Property lists (A47, extract_property fast path) ------------------------------------------
#
# Owner/tenant lists of one property ("Objektnummer | Einheit | Lage | Eigentümer | Mieter |
# Hausgeld | Miete | Vorauszahlungen | Beginn | IBAN") map onto the ``PropertyResult`` shape of
# ``extract_property`` (units, parties with payments). The column model lives here, not in
# ``mhvp.ai.tasks``, because the mapping call is an internal helper of the fast path and shares
# the ``map_columns`` task (tier, cost, logging) with the contact variant. Rule 0.1.6: the
# result stays a proposal; an IBAN is shown masked only and never copied into the proposal.

PropertyTargetField = Literal[
    "property_number",
    "property_name",
    "unit_number",
    "unit_label",
    "building",
    "location",
    "unit_type",
    "living_area_sqm",
    "mea",
    "owner_name",
    "tenant_name",
    "party_name",
    "role",
    "owner_start",
    "tenant_start",
    "start_date",
    "hoa_fee",
    "reserve",
    "rent",
    "operating_cost_advance",
    "heating_cost_advance",
    "garage",
    "parking",
    "other_payment",
    "payment_valid_from",
    "iban",
    "ignore",
]

PAYMENT_FIELDS: tuple[str, ...] = (
    "hoa_fee",
    "reserve",
    "rent",
    "operating_cost_advance",
    "heating_cost_advance",
    "garage",
    "parking",
    "other_payment",
)
OWNER_PAYMENTS = frozenset({"hoa_fee", "reserve"})
TENANT_PAYMENTS = frozenset({"rent", "operating_cost_advance", "heating_cost_advance"})


class PropertyColumnMapping(BaseModel):
    """One source column of an owner/tenant list mapped to a target field of the property
    fast path (``PropertyTargetField``)."""

    model_config = ConfigDict(extra="forbid")

    source_column: str
    target_field: PropertyTargetField
    confidence: float = Field(description="0 bis 1, wie sicher die Zuordnung ist")


class PropertyColumnMappingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[PropertyColumnMapping]
    has_header: bool = Field(description="false, wenn die erste Zeile bereits Daten enthält")
    default_role: Literal["owner", "tenant"] | None = Field(
        description="Rolle aller Parteien einer party_name-Spalte, falls keine Spalte role nennt"
    )
    confidence: float = Field(description="0 bis 1, wie sicher die Zuordnung insgesamt ist")


PROPERTY_MAP_PROMPT = Path(__file__).parent / "prompts" / "map_columns" / "property_v1.md"


def property_map_system_prompt() -> str:
    return PROPERTY_MAP_PROMPT.read_text(encoding="utf-8")


def property_map_schema() -> dict[str, Any]:
    return PropertyColumnMappingResult.model_json_schema()


UNIT_TYPE_MAP = {
    "wohnung": "apartment",
    "we": "apartment",
    "wohneinheit": "apartment",
    "apartment": "apartment",
    "gewerbe": "commercial",
    "gewerbeeinheit": "commercial",
    "laden": "commercial",
    "commercial": "commercial",
    "büro": "office",
    "buero": "office",
    "office": "office",
    "stellplatz": "parking",
    "tg-stellplatz": "parking",
    "tiefgarage": "parking",
    "parking": "parking",
    "garage": "garage",
    "keller": "storage",
    "lager": "storage",
    "abstellraum": "storage",
    "storage": "storage",
    "garten": "garden",
    "garden": "garden",
    "sonstiges": "other",
    "other": "other",
}


def unit_type_from_text(raw: str) -> str | None:
    """German unit type text to the platform code; ``None`` when the text is unknown (the row
    then stays residual instead of guessing a type)."""
    return UNIT_TYPE_MAP.get(raw.strip().lower())


def mask_iban(raw: str) -> str:
    """Country code plus check digits and the last four characters stay readable, the rest is
    masked; a too short value is masked completely."""
    compact = raw.replace(" ", "").upper()
    if len(compact) < 10:
        return "*" * len(compact)
    return f"{compact[:4]} **** {compact[-4:]}"


def _decimal_text(raw: str) -> str | None:
    """German or dotted number as text with a point (``ExtractedUnit`` shape); ``None`` for an
    empty cell. Raises ``ValueError`` for unreadable text (``mhvp.imports.fields``)."""
    if not raw.strip():
        return None
    return str(parse_decimal(raw))


def _date_text(raw: str) -> str | None:
    if not raw.strip():
        return None
    return parse_date(raw).isoformat()


@dataclass
class MappedProperty:
    property: dict[str, Any]
    buildings: list[str]
    units: list[dict[str, Any]]
    parties: list[dict[str, Any]]
    questions: list[str]
    residual: list[dict[str, Any]] = field(default_factory=list)  # {"row": int, "cells": {...}}
    processed_rows: int = 0


class _ResidualRowError(Exception):
    """The row cannot be converted deterministically; it goes to the LLM path."""


def _party_dict(
    parsed: ParsedName, role: str, unit_number: str, start: str | None, source: str
) -> dict[str, Any]:
    return {
        "role": role,
        "unit_number": unit_number,
        "kind": parsed.kind,
        "salutation": parsed.salutation,
        "first_name": parsed.first_name,
        "last_name": parsed.last_name,
        "company_name": parsed.company_name,
        "start_date": start,
        "payments": [],
        "source": source,
        "confidence": 1.0,
    }


def apply_property_mapping(
    table: TableData,
    mappings: dict[str, str],
    *,
    default_role: str | None,
) -> MappedProperty:
    """Deterministic pass for an owner/tenant list (Python only, no AI): one unit per distinct
    unit number, one party per named owner/tenant cell with its payments; rows without a unit
    number, with an ambiguous name cell, an unknown unit type, an unreadable number or date, or
    an amount without a party to carry it go to ``residual`` for the LLM."""
    by_field: dict[str, list[str]] = {}
    for column, target in mappings.items():
        if target == "ignore" or column not in table.header:
            continue
        by_field.setdefault(target, []).append(column)
    col_index = {name: i for i, name in enumerate(table.header)}

    def cell(row: list[str], field_name: str) -> str:
        for name in by_field.get(field_name, []):
            i = col_index.get(name)
            if i is not None and i < len(row) and row[i]:
                return row[i]
        return ""

    property_data: dict[str, Any] = {
        "number": None,
        "name": None,
        "management_type": None,
        "street": None,
        "house_number": None,
        "postal_code": None,
        "city": None,
    }
    buildings: list[str] = []
    units: dict[str, dict[str, Any]] = {}
    parties: list[dict[str, Any]] = []
    questions: list[str] = []
    residual: list[dict[str, Any]] = []

    for row_number, row in enumerate(table.rows, start=2):  # header is row 1
        source = f"{table.filename}, Zeile {row_number}"
        try:
            unit_number = cell(row, "unit_number").strip()
            if not unit_number:
                raise _ResidualRowError
            unit_type_raw = cell(row, "unit_type")
            unit_type = unit_type_from_text(unit_type_raw) if unit_type_raw else "apartment"
            if unit_type is None:
                raise _ResidualRowError
            try:
                area = _decimal_text(cell(row, "living_area_sqm"))
                mea = _decimal_text(cell(row, "mea"))
                owner_start = _date_text(cell(row, "owner_start") or cell(row, "start_date"))
                tenant_start = _date_text(cell(row, "tenant_start") or cell(row, "start_date"))
                valid_from = _date_text(cell(row, "payment_valid_from"))
                amounts = {
                    name: _decimal_text(cell(row, name))
                    for name in PAYMENT_FIELDS
                    if by_field.get(name)
                }
            except ValueError:
                raise _ResidualRowError from None

            row_parties: dict[str, dict[str, Any]] = {}
            for name_field, role, start in (
                ("owner_name", "owner", owner_start),
                ("tenant_name", "tenant", tenant_start),
            ):
                raw_name = cell(row, name_field)
                if not raw_name:
                    continue
                parsed = parse_name(raw_name)
                if parsed is None:
                    raise _ResidualRowError
                row_parties[role] = _party_dict(parsed, role, unit_number, start, source)
            party_raw = cell(row, "party_name")
            if party_raw:
                role_text = cell(row, "role")
                party_role = _role_from_text(role_text) if role_text else default_role
                if party_role not in ("owner", "tenant"):
                    raise _ResidualRowError
                parsed = parse_name(party_raw)
                if parsed is None:
                    raise _ResidualRowError
                start = owner_start if party_role == "owner" else tenant_start
                row_parties[party_role] = _party_dict(
                    parsed, party_role, unit_number, start, source
                )

            for name, gross in amounts.items():
                if gross is None or Decimal(gross) == 0:
                    continue
                if name in OWNER_PAYMENTS:
                    carrier = row_parties.get("owner")
                elif name in TENANT_PAYMENTS:
                    carrier = row_parties.get("tenant")
                elif len(row_parties) == 1:
                    carrier = next(iter(row_parties.values()))
                else:
                    carrier = row_parties.get("tenant")  # garage/parking/other: tenant first
                if carrier is None:
                    raise _ResidualRowError  # an amount without a party to carry it
                code = "other" if name == "other_payment" else name
                carrier["payments"].append(
                    {
                        "payment_type_code": code,
                        "gross": gross,
                        "valid_from": valid_from or carrier["start_date"],
                    }
                )
        except _ResidualRowError:
            residual.append(
                {"row": row_number, "cells": dict(zip(table.header, row, strict=False))}
            )
            continue

        if property_data["number"] is None and cell(row, "property_number"):
            property_data["number"] = cell(row, "property_number")
        if property_data["name"] is None and cell(row, "property_name"):
            property_data["name"] = cell(row, "property_name")
        building = cell(row, "building") or None
        if building and building not in buildings:
            buildings.append(building)
        unit = units.get(unit_number)
        if unit is None:
            units[unit_number] = {
                "number": unit_number,
                "label": cell(row, "unit_label") or None,
                "building": building,
                "location": cell(row, "location") or None,
                "unit_type": unit_type,
                "living_area_sqm": area,
                "mea": mea,
                "source": source,
                "confidence": 1.0,
            }
        else:  # same unit on a second row (e.g. owner row plus tenant row): fill gaps only
            for key, value in (
                ("label", cell(row, "unit_label") or None),
                ("building", building),
                ("location", cell(row, "location") or None),
                ("living_area_sqm", area),
                ("mea", mea),
            ):
                if unit.get(key) is None and value is not None:
                    unit[key] = value
        parties.extend(row_parties.values())
        iban_raw = cell(row, "iban")
        if iban_raw:
            holders = (
                " und ".join({"owner": "Eigentümer", "tenant": "Mieter"}[r] for r in row_parties)
                or "Partei"
            )
            questions.append(
                f"Einheit {unit_number} ({holders}): IBAN {mask_iban(iban_raw)} nicht "
                "übernommen; Bankverbindung nur nach Bestätigung im Kontakt erfassen."
            )
    return MappedProperty(
        property=property_data,
        buildings=buildings,
        units=list(units.values()),
        parties=parties,
        questions=questions,
        residual=residual,
        processed_rows=len(table.rows),
    )
