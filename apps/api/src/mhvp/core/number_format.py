"""Per tenant number formats (GA01-07, section 5.2 tenant_settings), technical preparation.

The configuration lives in the JSON document ``tenant_settings.sources["number_formats"]`` (no
schema change). Without an entry the formats stay exactly as they are hard coded today
(``DEFAULT_FORMATS``). The invoice scope carries VAT mandatory details, so its format can only be
changed after release by the tax adviser (OPEN_QUESTIONS AA17-01, gate G1); the API rejects it
until ``INVOICE_FORMAT_RELEASED`` is switched on by that decision.
"""

import re
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCOPES = ("property", "contract", "document", "ticket", "invoice")
LOCKED_SCOPES = frozenset({"invoice"})
INVOICE_FORMAT_RELEASED = False
SOURCES_KEY = "number_formats"
PREFIX_PATTERN = re.compile(r"^[A-Z0-9]{0,10}$")


class NumberFormat(BaseModel):
    """Prefix, digits, start value and year reference of one number circle."""

    model_config = ConfigDict(extra="forbid")

    prefix: str = Field(default="", max_length=10, pattern=r"^[A-Z0-9]*$")
    digits: int = Field(default=6, ge=1, le=12)
    start: int = Field(default=1, ge=1, le=999_999_999)
    year_based: bool = False


# Formats as hard coded before GA01-07: contract 000123, property 3 digits, ticket plain number,
# rent invoice MR-JJJJ-NNNNNN (accounting/rent_invoice.py).
DEFAULT_FORMATS: dict[str, NumberFormat] = {
    "property": NumberFormat(digits=3),
    "contract": NumberFormat(digits=6),
    "document": NumberFormat(digits=1),
    "ticket": NumberFormat(digits=1),
    "invoice": NumberFormat(prefix="MR", digits=6, year_based=True),
}


def effective_formats(sources: dict[str, Any] | None) -> dict[str, NumberFormat]:
    configured = (sources or {}).get(SOURCES_KEY) or {}
    result = dict(DEFAULT_FORMATS)
    if isinstance(configured, dict):
        for scope in SCOPES:
            if isinstance(configured.get(scope), dict):
                result[scope] = NumberFormat.model_validate(configured[scope])
    return result


def format_number(fmt: NumberFormat, value: int, on: date | None = None) -> str:
    """``[PREFIX-][JJJJ-]NNNN`` with zero padded digits; empty parts are left out."""
    parts = [fmt.prefix] if fmt.prefix else []
    if fmt.year_based:
        parts.append(str((on or datetime.now(UTC).date()).year))
    parts.append(f"{value:0{fmt.digits}d}")
    return "-".join(parts)


def preview(fmt: NumberFormat, on: date | None = None, count: int = 3) -> list[str]:
    return [format_number(fmt, fmt.start + i, on) for i in range(count)]
