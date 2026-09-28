"""Entry standards (Erfassungsstandards, rule ES-01 to ES-10, docs/rules/ES-erfassungsstandards.md).

Pure functions without database access: they check one draft or stored record and return
findings. Only ES-01 (German postcode) is a hard validation, enforced by the property endpoints
on create and on change of postcode or country; every other rule yields a non blocking warning.
The CRM mirrors these rules in ``apps/web-crm/src/lib/entry-standards.ts`` (same ids).

Contacts carry separate ``first_name`` and ``last_name`` fields; the display name
"Name, Vorname" is derived by ``mhvp.contacts.services.display_name`` and is a display and
sorting convention, never free text. The rules therefore check that the parts sit in the
right fields.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

Severity = Literal["error", "warning", "hint"]

POSTCODE_DE = re.compile(r"^[0-9]{5}$")
# "Straße Hausnummer, PLZ Ort", e.g. "Rheinpromenade 13, 40789 Monheim am Rhein" or
# "Hauptstraße 4a-6, 41812 Erkelenz".
PROPERTY_NAME = re.compile(
    r"^\S.*\s[0-9]+\s?[A-Za-z]?(\s?[-/]\s?[0-9]+\s?[A-Za-z]?)?,\s[0-9]{5}\s\S.*$"
)
_STREET_WITH_NUMBER = re.compile(r"\s[0-9]+\s?[A-Za-z]?$")
_NAME_PARTICLES = frozenset(
    {"von", "van", "de", "der", "den", "zu", "zur", "vom", "di", "da", "del", "la", "le", "ten"}
    | {"ter", "du", "dos", "af"}
)
_COMPANY_MARKERS = re.compile(
    r"(?i)(\bgmbh\b|\bmbh\b|\bag\b|\bkg\b|\bohg\b|\bgbr\b|\bug\b|\be\.\s?v\.|\bweg\b|"
    r"\bhausverwaltung\b|\bverwaltung\b|\bstadtwerke\b|\bversicherung\b|\bbank\b|"
    r"\bsparkasse\b|\bgesellschaft\b|\bstiftung\b|\bltd\b|\binc\b)"
)


@dataclass(frozen=True)
class Finding:
    rule: str
    field: str | None
    severity: Severity
    message: str


def postcode_error(country: str | None, postal_code: str | None) -> str | None:
    """ES-01: a German postcode has exactly five digits. Empty is allowed (ES-02 warns)."""
    if (country or "DE").upper() != "DE" or not postal_code or not postal_code.strip():
        return None
    if POSTCODE_DE.fullmatch(postal_code.strip()):
        return None
    return "Die Postleitzahl muss in Deutschland aus genau fünf Ziffern bestehen."


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def check_property(data: Mapping[str, Any]) -> list[Finding]:
    """ES-01 to ES-04 for one property draft or record."""
    out: list[Finding] = []
    error = postcode_error(data.get("country"), data.get("postal_code"))
    if error:
        out.append(Finding("ES-01", "postal_code", "error", error))
    for key, label in (
        ("street", "Straße"),
        ("house_number", "Hausnummer"),
        ("postal_code", "Postleitzahl"),
        ("city", "Ort"),
    ):
        if _blank(data.get(key)):
            out.append(
                Finding("ES-02", key, "warning", f"{label} fehlt; die Zuordnung braucht sie.")
            )
    street = data.get("street")
    if (
        isinstance(street, str)
        and _STREET_WITH_NUMBER.search(street.strip())
        and _blank(data.get("house_number"))
    ):
        out.append(
            Finding(
                "ES-03",
                "street",
                "warning",
                "Die Hausnummer steht im Feld Straße; bitte in das Feld Hausnummer übernehmen.",
            )
        )
    name = data.get("name")
    if isinstance(name, str) and name.strip() and not PROPERTY_NAME.fullmatch(name.strip()):
        out.append(
            Finding(
                "ES-04",
                "name",
                "hint",
                "Objektname nach Standard: Straße Hausnummer, PLZ Ort "
                f"(Vorschlag: {suggest_property_name(data) or 'Anschrift ergänzen'}).",
            )
        )
    return out


def suggest_property_name(data: Mapping[str, Any]) -> str | None:
    parts = [str(data.get(k) or "").strip() for k in ("street", "house_number", "postal_code")]
    city = str(data.get("city") or "").strip()
    street, number, postcode = parts
    if not (street and number and postcode and city):
        return None
    return f"{street} {number}, {postcode} {city}"


def check_contact(data: Mapping[str, Any]) -> list[Finding]:
    """ES-05 to ES-08 for one contact draft or record (kind, first_name, last_name, ...)."""
    out: list[Finding] = []
    kind = str(data.get("kind") or "person")
    first = str(data.get("first_name") or "").strip()
    last = str(data.get("last_name") or "").strip()
    if kind == "company":
        if _blank(data.get("company_name")):
            out.append(Finding("ES-08", "company_name", "warning", "Firmenname fehlt."))
        return out
    if "," in last or "," in first:
        out.append(
            Finding(
                "ES-05",
                "last_name",
                "warning",
                "Nachname und Vorname gehören in getrennte Felder; die Anzeige Name, Vorname "
                "entsteht automatisch.",
            )
        )
    elif not first and _looks_like_full_name(last):
        out.append(
            Finding(
                "ES-06",
                "last_name",
                "warning",
                "Im Feld Nachname steht vermutlich Vorname und Nachname; bitte den Vornamen "
                "in das Feld Vorname übernehmen.",
            )
        )
    if _COMPANY_MARKERS.search(f"{first} {last}"):
        out.append(
            Finding(
                "ES-07",
                "kind",
                "warning",
                "Der Name enthält einen Firmenbestandteil; bitte als Firma erfassen.",
            )
        )
    if not first and not out:
        out.append(Finding("ES-08", "first_name", "hint", "Vorname fehlt."))
    return out


def _looks_like_full_name(value: str) -> bool:
    words = value.split()
    if len(words) < 2:
        return False
    # "von Bülow" or "de la Cruz" are surnames with particles, not "Vorname Name".
    return words[0].lower() not in _NAME_PARTICLES


def deadline_in_past(due_on: date | None, today: date) -> bool:
    """ES-09: a deadline before today needs an explicit confirmation in the form."""
    return due_on is not None and due_on < today


def check_deadline(data: Mapping[str, Any], today: date) -> list[Finding]:
    """ES-09 and ES-10 for a deadline (ticket working due date with its assignee)."""
    out: list[Finding] = []
    due = data.get("due_on")
    due_date = date.fromisoformat(due) if isinstance(due, str) and due else due
    if isinstance(due_date, date) and deadline_in_past(due_date, today):
        out.append(
            Finding("ES-09", "due_on", "warning", "Das Fristdatum liegt in der Vergangenheit.")
        )
    if due_date and _blank(data.get("assignee_user_id")):
        out.append(
            Finding(
                "ES-10",
                "assignee_user_id",
                "warning",
                "Für die Frist ist keine verantwortliche Person eingetragen.",
            )
        )
    return out
