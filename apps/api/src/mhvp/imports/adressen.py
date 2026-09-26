"""Addresses of properties after the Immoware24 object import.

The Immoware24 object list has no address columns, so imported properties lack street, house
number, postal code and city. Two ways to fill them, both only ever fill empty fields and never
overwrite (idempotent):

* ``derive_from_names``: street and house number from the property name ("Shalomweg 3",
  "WEG Am Panke Park 67-85"); state prefixes ("Z ABGEGEBEN", "Y ABRECHNUNG") are removed first.
* ``apply_address_list``: rows of an address list (CSV or XLSX) with the object number and
  columns for street, house number, postal code and city. Differences to already filled fields
  are reported as conflicts.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from mhvp.imports import objektdaten
from mhvp.properties.models import Property

FIELDS = ("street", "house_number", "postal_code", "city")
FIELD_LABELS = {
    "street": "Straße",
    "house_number": "Hausnummer",
    "postal_code": "PLZ",
    "city": "Ort",
}
_LIMITS = {"street": 200, "house_number": 20, "postal_code": 20, "city": 100}
# Further operator markers in front of the name ("X ", "Z-", "ALT:"), after the known ones.
_OTHER_PREFIX = re.compile(r"^\s*(?:[XYZ]\s*[-.:]\s*|[XYZ]\s+(?=[A-ZÄÖÜ]{3,}\b)[A-ZÄÖÜ]+\s+)")
_WEG_PREFIX = re.compile(r"^\s*(?:WEG|GbR|ETG)\b[\s:.-]*", re.IGNORECASE)
_NUMBER_SHAPE = re.compile(
    r"\d+\s?[a-zA-Z]?(?:\s*[-/+,]\s*\d+\s?[a-zA-Z]?)*(?:\s+[A-Za-z]{0,3}\d*)?"
)


def clean_name(name: str) -> str:
    """Name without state prefixes (Z ABGEGEBEN, Y ABRECHNUNG, ...) and without "WEG "."""
    text, _, _ = objektdaten.classify_name(name)
    text = _OTHER_PREFIX.sub("", text).strip()
    return _WEG_PREFIX.sub("", text).strip()


# Wie kontakte._HOUSE_NUMBER, zusaetzlich mit Hausnummernbereich und Gebaeudekennung
# ("1-21 H1", "67-85") wie in den Objektnamen aus Immoware24.
_HOUSE_NUMBER = re.compile(
    r"^(?P<street>.+?)\s+(?P<number>\d+(?:\s?[a-zA-Z]{1,2})?(?:\s?[-/]\s?\d+(?:\s?[a-zA-Z]{1,2})?)?"
    r"(?:\s+H\d+)?)\s*$"
)


def split_address(text: str | None) -> tuple[str | None, str | None]:
    """``(street, house_number)``; ``(None, None)`` if no house number is recognisable."""
    if not text:
        return None, None
    value = re.sub(r"\s+", " ", text).strip()
    match = _HOUSE_NUMBER.match(value)
    if not match or re.match(r"\d", value):
        return None, None
    street = match.group("street").strip(" ,")
    number = match.group("number").strip(" ,")
    if not re.search(r"[A-Za-zÄÖÜäöüß]{2}", street) or len(number) > 20:
        return None, None
    if not _NUMBER_SHAPE.fullmatch(number):
        return None, None
    return street[:200], number


def derive_address(name: str) -> tuple[str | None, str | None]:
    return split_address(clean_name(name))


def _same(a: str | None, b: str | None) -> bool:
    def norm(v: str | None) -> str:
        return re.sub(r"\s+", " ", (v or "").strip().lower()).replace("str.", "straße")

    return norm(a) == norm(b)


@dataclass
class AddressReport:
    apply: bool
    filled: list[dict[str, Any]] = field(default_factory=list)
    skipped: int = 0
    unrecognised: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    unknown: list[dict[str, Any]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": {
                "filled": len(self.filled),
                "skipped": self.skipped,
                "unrecognised": len(self.unrecognised),
                "conflicts": len(self.conflicts),
                "unknown": len(self.unknown),
            },
            "filled": self.filled,
            "unrecognised": self.unrecognised,
            "conflicts": self.conflicts,
            "unknown": self.unknown,
            "problems": self.problems,
        }


def _fill(prop: Property, values: dict[str, str | None], apply: bool) -> dict[str, str]:
    """Set the empty fields of ``prop`` from ``values``; returns what was (or would be) set."""
    changed: dict[str, str] = {}
    for key in FIELDS:
        value = (values.get(key) or "").strip()
        if value and not (getattr(prop, key) or "").strip():
            changed[key] = value[: _LIMITS[key]]
            if apply:
                setattr(prop, key, changed[key])
    return changed


async def derive_from_names(session: Any, tenant_id: uuid.UUID, apply: bool) -> dict[str, Any]:
    """Street and house number from the name of every property with an empty street."""
    report = AddressReport(apply=apply)
    stmt = (
        select(Property)
        .where(Property.tenant_id == tenant_id)
        .where((Property.street.is_(None)) | (Property.street == ""))
        .order_by(Property.number)
    )
    for prop in (await session.execute(stmt)).scalars():
        street, number = derive_address(prop.name)
        if street is None:
            report.unrecognised.append({"number": prop.number, "name": prop.name})
            continue
        changed = _fill(prop, {"street": street, "house_number": number}, apply)
        if changed:
            report.filled.append({"number": prop.number, "name": prop.name, **changed})
        else:
            report.skipped += 1
    if apply:
        await session.flush()
    return report.as_dict()


def _header_key(header: str) -> str | None:
    h = re.sub(r"[\s._\-]+", "", header.strip().lower())
    if h.startswith("objekt") and ("nummer" in h or h.endswith("nr") or h == "objekt"):
        return "object"
    if h in ("objektnr", "objektnummer", "objnr", "objektid"):
        return "object"
    if h in (
        "strasse",
        "straße",
        "str",
        "strassehausnummer",
        "straßehausnummer",
        "straßeundhausnummer",
        "strasseundhausnummer",
        "anschrift",
        "adresse",
    ):
        return "street"
    if h in ("hausnummer", "hausnr", "nr", "hnr"):
        return "house_number"
    if h in ("plz", "postleitzahl"):
        return "postal_code"
    if h in ("ort", "stadt", "wohnort"):
        return "city"
    return None


def map_headers(headers: list[str]) -> dict[str, int]:
    index: dict[str, int] = {}
    for i, header in enumerate(headers):
        key = _header_key(header)
        if key and key not in index:
            index[key] = i
    if "object" not in index:
        raise ValueError("Spalte Objektnummer fehlt")
    if not any(k in index for k in FIELDS):
        raise ValueError("Keine Adressspalte gefunden (Straße, Hausnummer, PLZ, Ort)")
    return index


def _object_number(raw: str) -> tuple[str | None, str | None]:
    src = raw.strip()
    src = re.sub(r"\.0+$", "", src)  # Excel numbers "82.0"
    match = re.match(r"^0*(\d+)\b", src)  # Immoware24 form "082", "82 Shalomweg 3"
    if match and not re.fullmatch(r"\d+", src):
        src = match.group(1)
    if re.fullmatch(r"0+\d{3,}", src):
        src = src.lstrip("0").zfill(3)
    return objektdaten.normalise_number(src, {})


async def apply_address_list(
    session: Any, tenant_id: uuid.UUID, rows: list[list[str]], apply: bool
) -> dict[str, Any]:
    """``rows`` including the header row. Fills only empty fields; differences are conflicts."""
    report = AddressReport(apply=apply)
    if not rows:
        raise ValueError("Die Datei enthält keine Zeilen")
    index = map_headers(rows[0])
    props = {
        p.number: p
        for p in (
            await session.execute(select(Property).where(Property.tenant_id == tenant_id))
        ).scalars()
    }

    def cell(row: list[str], key: str) -> str | None:
        i = index.get(key)
        if i is None or i >= len(row):
            return None
        return str(row[i] or "").strip() or None

    for line, row in enumerate(rows[1:], start=2):
        raw = cell(row, "object")
        if not raw:
            if any(str(c or "").strip() for c in row):
                report.problems.append(f"Zeile {line}: Objektnummer fehlt")
            continue
        number, reason = _object_number(raw)
        if number is None:
            report.problems.append(f"Zeile {line}: {reason}")
            continue
        prop = props.get(number)
        if prop is None:
            report.unknown.append({"line": line, "number": number})
            continue
        values = {k: cell(row, k) for k in FIELDS}
        if values["street"] and not values["house_number"]:
            street, house = split_address(values["street"])
            if street:
                values["street"], values["house_number"] = street, house
        if values["postal_code"] and not values["city"]:
            m = re.fullmatch(r"(\d{5})\s+(.+)", values["postal_code"])
            if m:
                values["postal_code"], values["city"] = m.group(1), m.group(2)
        for key in FIELDS:
            current = (getattr(prop, key) or "").strip()
            if values[key] and current and not _same(current, values[key]):
                report.conflicts.append(
                    {
                        "line": line,
                        "number": prop.number,
                        "field": FIELD_LABELS[key],
                        "current": current,
                        "list": values[key],
                    }
                )
        changed = _fill(prop, values, apply)
        if changed:
            report.filled.append({"number": prop.number, "name": prop.name, **changed})
        else:
            report.skipped += 1
    if apply:
        await session.flush()
    return report.as_dict()
