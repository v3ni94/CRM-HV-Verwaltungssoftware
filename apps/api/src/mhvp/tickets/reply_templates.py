"""Placeholders of ticket reply templates (operator 26.09.2026).

Deterministic text substitution only: ``{anrede}``, ``{name}``, ``{objekt}``,
``{ticketnummer}`` and a few companions are filled from the ticket, its contact, property and
unit. Unknown placeholders are rejected when a template is saved so that no unfilled marker
ever reaches a recipient. No AI is involved."""

from __future__ import annotations

import re
from typing import Any

PLACEHOLDERS: tuple[str, ...] = (
    "anrede",
    "name",
    "vorname",
    "nachname",
    "objekt",
    "einheit",
    "ticketnummer",
    "tickettitel",
    "datum",
)
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_]+)\}")


def unknown_placeholders(text: str | None) -> list[str]:
    """Placeholders in ``text`` that are not in ``PLACEHOLDERS`` (order of appearance)."""
    seen: list[str] = []
    for match in _PLACEHOLDER_RE.finditer(text or ""):
        key = match.group(1)
        if key not in PLACEHOLDERS and key not in seen:
            seen.append(key)
    return seen


def render(text: str | None, values: dict[str, str]) -> str:
    """Replaces every known placeholder; unknown ones stay as written."""

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return _PLACEHOLDER_RE.sub(_sub, text or "")


def salutation(contact: Any | None) -> str:
    """ "Sehr geehrte Frau X" / "Sehr geehrter Herr X", otherwise the neutral form."""
    if contact is None or not getattr(contact, "last_name", None):
        return "Sehr geehrte Damen und Herren"
    form = getattr(contact, "salutation", None)
    if form == "Herr":
        return f"Sehr geehrter Herr {contact.last_name}"
    if form == "Frau":
        return f"Sehr geehrte Frau {contact.last_name}"
    return "Sehr geehrte Damen und Herren"


def property_label(prop: Any | None) -> str:
    if prop is None:
        return ""
    parts = [getattr(prop, "name", "") or ""]
    street = getattr(prop, "street", None)
    if street:
        number = getattr(prop, "house_number", None)
        parts.append(f"{street} {number}".strip() if number else street)
    return ", ".join(p for p in parts if p)


def unit_label(unit: Any | None) -> str:
    if unit is None:
        return ""
    label = getattr(unit, "label", None)
    number = getattr(unit, "number", "") or ""
    return f"{number} ({label})" if label else number


def full_name(contact: Any | None) -> str:
    """Letter form "Vorname Nachname" for persons, the display name otherwise."""
    if contact is None:
        return ""
    first = (getattr(contact, "first_name", None) or "").strip()
    last = (getattr(contact, "last_name", None) or "").strip()
    if first or last:
        return " ".join(p for p in (first, last) if p)
    return getattr(contact, "display_name", None) or ""


def values_for(
    *,
    ticket: Any,
    contact: Any | None,
    prop: Any | None,
    unit: Any | None,
    today: str,
) -> dict[str, str]:
    return {
        "anrede": salutation(contact),
        "name": full_name(contact),
        "vorname": (getattr(contact, "first_name", None) or "") if contact else "",
        "nachname": (getattr(contact, "last_name", None) or "") if contact else "",
        "objekt": property_label(prop),
        "einheit": unit_label(unit),
        "ticketnummer": str(ticket.number),
        "tickettitel": ticket.title or "",
        "datum": today,
    }
