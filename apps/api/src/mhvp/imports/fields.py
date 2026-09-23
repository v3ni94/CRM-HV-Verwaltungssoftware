"""Platform target fields per report type and value parsing (German formats, 13.1).

Target fields are platform fields, not Immoware24 column names; the mapping connects both.
Values are parsed strictly: an unreadable number or date is an error, never a guess.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from mhvp.imports.models import ReportType


@dataclass(frozen=True)
class Field:
    name: str
    kind: str  # text, decimal, date, choice
    required: bool = False
    choices: tuple[str, ...] = ()
    label: str = ""


UNIT_TYPES = (
    "apartment",
    "commercial",
    "office",
    "parking",
    "garage",
    "storage",
    "garden",
    "other",
)
MANAGEMENT = ("rental", "hoa", "hoa_with_sev")
PAYMENT_TYPES = (
    "rent",
    "operating_cost_advance",
    "heating_cost_advance",
    "garage",
    "parking",
    "rent_reduction",
    "hoa_fee",
    "reserve",
    "special_levy",
    "other",
)

FIELDS: dict[ReportType, tuple[Field, ...]] = {
    ReportType.PROPERTIES: (
        Field("number", "text", True, label="Objektnummer (dreistellig)"),
        Field("name", "text", True, label="Bezeichnung"),
        Field("management_type", "choice", True, MANAGEMENT, "Verwaltungsart"),
        Field("street", "text", label="Straße"),
        Field("house_number", "text", label="Hausnummer"),
        Field("postal_code", "text", label="PLZ"),
        Field("city", "text", label="Ort"),
    ),
    ReportType.UNITS: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("number", "text", True, label="Einheitennummer"),
        Field("label", "text", label="Bezeichnung"),
        Field("building", "text", label="Gebäude"),
        Field("location", "text", label="Lage"),
        Field("unit_type", "choice", True, UNIT_TYPES, "Art"),
        Field("living_area_sqm", "decimal", label="Wohnfläche m²"),
        Field("mea", "decimal", label="Miteigentumsanteil"),
        Field("mea_valid_from", "date", label="MEA gültig ab"),
    ),
    ReportType.CONTACTS: (
        Field("external_id", "text", True, label="Kontakt-ID im Altsystem"),
        Field("kind", "choice", True, ("person", "company"), "Art"),
        Field("salutation", "choice", False, ("Herr", "Frau"), "Anrede"),
        Field("title", "text", label="Titel"),
        Field("first_name", "text", label="Vorname"),
        Field("last_name", "text", label="Nachname"),
        Field("company_name", "text", label="Firma"),
        Field("street", "text", label="Straße"),
        Field("house_number", "text", label="Hausnummer"),
        Field("postal_code", "text", label="PLZ"),
        Field("city", "text", label="Ort"),
        Field("phone", "text", label="Telefon"),
        Field("email", "text", label="E-Mail"),
        Field("iban", "text", label="IBAN"),
    ),
    ReportType.TENANCIES: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("unit_number", "text", True, label="Einheitennummer"),
        Field("contact_external_id", "text", True, label="Kontakt-ID Mieter"),
        Field("start_date", "date", True, label="Mietbeginn"),
        Field("end_date", "date", label="Mietende"),
    ),
    ReportType.OWNERSHIPS: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("unit_number", "text", True, label="Einheitennummer"),
        Field("contact_external_id", "text", True, label="Kontakt-ID Eigentümer"),
        Field("start_date", "date", True, label="Beginn"),
        Field("title_transfer_date", "date", True, label="Eigentumsübergang (Grundbuch)"),
        Field("benefit_burden_date", "date", label="Nutzen-/Lastenwechsel"),
        Field("end_date", "date", label="Ende"),
    ),
    ReportType.PAYMENTS: (
        Field("property_number", "text", True, label="Objektnummer"),
        Field("unit_number", "text", True, label="Einheitennummer"),
        Field("contact_external_id", "text", True, label="Kontakt-ID Vertragspartei"),
        Field("kind", "choice", True, ("tenancy", "ownership"), "Vertragsart"),
        Field("payment_type_code", "choice", True, PAYMENT_TYPES, "Zahlungsart"),
        Field("gross", "decimal", True, label="Betrag brutto"),
        Field("vat_percent", "decimal", True, label="Steuersatz in Prozent"),
        Field("valid_from", "date", True, label="Gültig ab"),
    ),
    # Staged only until ledger (M10) and bank adapter (M11) exist; no field mapping required.
    ReportType.JOURNAL: (),
    ReportType.BANK_TRANSACTIONS: (),
}

_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")
_GERMAN_NUMBER = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")


def parse_decimal(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Zahl nicht lesbar (Wahrheitswert)")
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    text = text.removesuffix("EUR").removesuffix("€").removesuffix("%")
    if _GERMAN_NUMBER.match(text):
        return Decimal(text.replace(".", "").replace(",", "."))
    try:
        return Decimal(text)  # already with a decimal point (e.g. 71.35)
    except InvalidOperation:
        raise ValueError(f"Zahl {value!r} nicht lesbar") from None


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    match = _DATE.match(text)
    if match:
        day, month, year = (int(g) for g in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            raise ValueError(f"Datum {value!r} gibt es nicht") from None
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"Datum {value!r} nicht lesbar (TT.MM.JJJJ)") from None


def convert(
    report_type: ReportType,
    raw: dict[str, Any],
    columns: dict[str, str],
    value_maps: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], list[str]]:
    """Map a raw row to typed target values; returns values and errors (German)."""
    values: dict[str, Any] = {}
    errors: list[str] = []
    for field in FIELDS[report_type]:
        column = columns.get(field.name)
        cell = raw.get(column) if column else None
        if isinstance(cell, str):
            cell = cell.strip() or None
        if cell is None:
            if field.required:
                errors.append(f"{field.label or field.name}: fehlt")
            continue
        mapped = value_maps.get(field.name, {}).get(str(cell), cell)
        try:
            if field.kind == "decimal":
                values[field.name] = str(parse_decimal(mapped))
            elif field.kind == "date":
                values[field.name] = parse_date(mapped).isoformat()
            elif field.kind == "choice":
                if str(mapped) not in field.choices:
                    raise ValueError(f"Wert {cell!r} ist nicht zugeordnet")
                values[field.name] = str(mapped)
            else:
                values[field.name] = str(mapped) if not isinstance(mapped, float) else f"{mapped:g}"
        except ValueError as exc:
            errors.append(f"{field.label or field.name}: {exc}")
    if report_type is ReportType.PROPERTIES and "number" in values:
        number = values["number"]
        if number.isdigit() and len(number) < 3:
            errors.append(
                f"Objektnummer {number!r} ist nicht dreistellig; bitte im Altsystem prüfen"
            )
        elif not re.fullmatch(r"[0-9]{3}", number):
            errors.append(f"Objektnummer {number!r} ist nicht dreistellig")
    return values, errors
