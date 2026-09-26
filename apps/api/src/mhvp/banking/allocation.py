"""Payer's determination (Tilgungsbestimmung) from the payment purpose (M12-03, D39, 7.4 Nr. 5).

Deterministic parsing without AI: invoice numbers, charge numbers (Sollstellung), month or
quarter periods and property or unit identifiers. IBANs, BICs, SEPA references and calendar
dates are removed first so their digits are never read as a number or a period. The hints only
change the order and the reason of suggestions; they never book anything by themselves.
"""

import re
from dataclasses import dataclass
from datetime import date

REASON_DETERMINED = "Bestimmung aus Verwendungszweck"
REASON_RULE = "Regel ohne Bestimmung"

MONTHS = {
    "januar": 1, "jan": 1, "jänner": 1,
    "februar": 2, "feb": 2,
    "märz": 3, "maerz": 3, "marz": 3, "mär": 3, "mrz": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}  # fmt: skip

_IDENT = r"([a-z0-9][a-z0-9\-/]*\d[a-z0-9\-/]*|\d[a-z0-9\-/]*)"
_SEP = r"\s*(?:[:#]|nr\.?|nummer)?\s*[:#.]?\s*"
_NOISE = [
    # IBAN, grouped or not
    re.compile(r"\b[a-z]{2}\d{2}(?:\s?[a-z0-9]{4}){2,7}(?:\s?[a-z0-9]{1,4})?\b"),
    # SEPA structured fields with their value
    re.compile(r"\b(?:eref|mref|kref|cred|iban|bic|abwa|abwe)\s*[+:]\s*\S+"),
    # BIC after the keyword is covered above; calendar dates 05.02.2026 or 2026-02-05
    re.compile(r"\b\d{1,2}\.\d{1,2}\.(?:\d{4}|\d{2})\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
]
_INVOICE = re.compile(
    r"\b(?:rechnungsnummer|rechnung|rechn\.?|re\.?-?nr\.?|rg\.?-?nr\.?|rnr\.?|rg\.?|re\.?|invoice)"
    + _SEP
    + _IDENT
)
_CHARGE = re.compile(
    r"\b(?:sollstellungsnummer|sollstellung|soll-?nr\.?|sst\.?-?nr\.?)" + _SEP + _IDENT
)
_UNIT = re.compile(r"\b(?:wohnungsnummer|wohnung|whg\.?|einheit|we|ve)" + _SEP + _IDENT)
_PROPERTY = re.compile(r"\b(?:objektnummer|objekt|obj\.?|liegenschaft)" + _SEP + _IDENT)
_NUMERIC_MONTH = re.compile(r"(?<![\d.])(0?[1-9]|1[0-2])\s*[/.\-]\s*(20\d{2})(?!\d)")
_NAMED_MONTH = re.compile(
    r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b\.?\s*(20\d{2})?(?!\d)"
)
_QUARTER = re.compile(r"\b([1-4])\.\s*quartal\s*(20\d{2})?|\bq([1-4])\s*[/\-]?\s*(20\d{2})?\b")


@dataclass(frozen=True)
class AllocationHints:
    """Structured determination hints; periods are (year or None, month)."""

    invoice_numbers: tuple[str, ...] = ()
    charge_numbers: tuple[str, ...] = ()
    periods: tuple[tuple[int | None, int], ...] = ()
    units: tuple[str, ...] = ()
    properties: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.invoice_numbers or self.charge_numbers or self.periods)


def _clean(purpose: str) -> str:
    text = " ".join(purpose.lower().split())
    for pattern in _NOISE:
        text = pattern.sub(" ", text)
    return text


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(v.strip("-/") for v in values if v.strip("-/")))


def parse_allocation_hint(purpose: str) -> AllocationHints:
    """Extract determination hints from a payment purpose, deterministic and without AI."""
    text = _clean(purpose or "")
    invoices = _unique([m.group(1) for m in _INVOICE.finditer(text)])
    charges = _unique([m.group(1) for m in _CHARGE.finditer(text)])
    units = _unique([m.group(1) for m in _UNIT.finditer(text)])
    properties = _unique([m.group(1) for m in _PROPERTY.finditer(text)])
    periods: list[tuple[int | None, int]] = []
    rest = text
    for m in _QUARTER.finditer(text):
        quarter = int(m.group(1) or m.group(3))
        year_text = m.group(2) or m.group(4)
        year = int(year_text) if year_text else None
        periods.extend((year, month) for month in range(quarter * 3 - 2, quarter * 3 + 1))
        rest = rest.replace(m.group(0), " ")
    for m in _NUMERIC_MONTH.finditer(rest):
        periods.append((int(m.group(2)), int(m.group(1))))
    for m in _NAMED_MONTH.finditer(rest):
        periods.append((int(m.group(2)) if m.group(2) else None, MONTHS[m.group(1)]))
    return AllocationHints(
        invoice_numbers=invoices,
        charge_numbers=charges,
        periods=tuple(dict.fromkeys(periods)),
        units=units,
        properties=properties,
    )


def _norm(value: str) -> str:
    return re.sub(r"[\s\-/]", "", value.lower())


def matches_item(hints: AllocationHints, *, reference: str | None, period: date | None) -> bool:
    """True if a number hint equals the item reference or a period hint covers its month."""
    if reference:
        ref = _norm(reference)
        if any(_norm(n) == ref for n in (*hints.invoice_numbers, *hints.charge_numbers)):
            return True
    if period is not None:
        for year, month in hints.periods:
            if month == period.month and (year is None or year == period.year):
                return True
    return False
