"""Central money helpers (B06, 6.9.8, RUNDUNG.md).

Cent rounding is always commercial rounding (ROUND_HALF_UP), never banker's rounding.
Distributions add up exactly to the total. Parsing of user or file input is strict: a value
that could be read in two ways is rejected instead of guessed (GAI-205).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")
#: Scale of intermediate values and ratios, NUMERIC(20,8) (6.9.8).
INTERMEDIATE = Decimal("0.00000001")


def round_cents(value: Decimal | int | str) -> Decimal:
    """Round to whole cents, half up (13.225 -> 13.23, -13.225 -> -13.23)."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def round_to(value: Decimal | int | str, exponent: Decimal) -> Decimal:
    """Round half up to the given exponent (e.g. ``Decimal("0.0001")``)."""
    return Decimal(str(value)).quantize(exponent, rounding=ROUND_HALF_UP)


def distribute_cents(total: Decimal, weights: Sequence[Decimal | int]) -> list[Decimal]:
    """Split ``total`` (whole cents) by ``weights`` so that the parts add up exactly.

    Largest remainder method on cent units: every share is first truncated toward zero,
    the remaining cents go one by one to the largest remainders (ties: earlier position).
    Negative totals are split mirror symmetric. All weights zero is an error.
    """
    total = Decimal(total)
    if total != total.quantize(CENT):
        raise ValueError("total must be a whole cent amount")
    ws = [Decimal(w) for w in weights]
    if not ws:
        raise ValueError("weights must not be empty")
    if any(w < 0 for w in ws):
        raise ValueError("weights must not be negative")
    weight_sum = sum(ws, Decimal(0))
    if weight_sum == 0:
        raise ValueError("weights must not all be zero")
    sign = -1 if total < 0 else 1
    cents = int(abs(total) / CENT)
    exact = [Decimal(cents) * w / weight_sum for w in ws]
    base = [int(e) for e in exact]  # truncation toward zero, e >= 0
    rest = cents - sum(base)
    order = sorted(range(len(ws)), key=lambda i: (-(exact[i] - base[i]), i))
    for i in order[:rest]:
        base[i] += 1
    return [sign * Decimal(b) * CENT for b in base]


_GROUPED = re.compile(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$")
_COMMA = re.compile(r"^-?\d+(,\d+)?$")
_POINT = re.compile(r"^-?\d*\.\d+$|^-?\d+$")
_AMBIGUOUS = re.compile(r"^-?\d{1,3}\.\d{3}$")


def is_ambiguous_number(text: str) -> bool:
    """``12.500`` can be German 12500 or English 12.5: exactly one point, three digits."""
    return bool(_AMBIGUOUS.match(text))


def parse_decimal_strict(value: Any) -> Decimal:
    """Parse German or plain decimal input; reject ambiguous text and non finite values.

    Floats (Excel cells) are taken by their shortest representation and rounded half up to
    eight decimals, so floating point residue (0.1 + 0.2) does not reach the record (GAI-206).
    """
    if isinstance(value, bool):
        raise ValueError("Zahl nicht lesbar (Wahrheitswert)")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"Zahl {value!r} nicht lesbar")
        return round_to(repr(value), INTERMEDIATE).normalize() + Decimal(0)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"Zahl {value!r} nicht lesbar")
        return value
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    text = text.removesuffix("EUR").removesuffix("€").removesuffix("%")
    if is_ambiguous_number(text):
        raise ValueError(
            f"Zahl {value!r} mehrdeutig (Tausenderpunkt oder Dezimalpunkt): "
            "bitte mit Dezimalkomma (z. B. 12,500 oder 12.500,00) angeben"
        )
    try:
        if _GROUPED.match(text) or _COMMA.match(text):
            return Decimal(text.replace(".", "").replace(",", "."))
        if _POINT.match(text):
            return Decimal(text)
    except InvalidOperation:
        pass
    raise ValueError(f"Zahl {value!r} nicht lesbar")


def json_number(value: Decimal) -> int | float:
    """Decimal as JSON number for external APIs that require numbers (GAI-207, GAI-208).

    The conversion is only allowed when it is lossless: the float's shortest representation
    must equal the decimal value. Otherwise ``ValueError``; nothing is silently rounded.
    """
    if not value.is_finite():
        raise ValueError("non finite decimal")
    if value == value.to_integral_value():
        return int(value)
    number = float(value)
    if Decimal(repr(number)) != value:
        raise ValueError(f"{value} is not exactly representable as JSON number")
    return number
