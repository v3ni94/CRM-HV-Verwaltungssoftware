"""Calculation helpers for operating cost statements (6.9.8, B06, D08, D10, A04, A05).

Rounding happens only when forming the posting amount (half up); remaining cents are assigned
in a stable order (unit number, party id), never by screen order (D08).
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
RULE_VERSION = "operating-costs-v1"
# Rule versions by first day of validity (A01, D28): a version applies to statements whose
# period starts on or after its date. The snapshot keeps the version used (A-045); a later
# entry never changes an already calculated or issued statement.
RULE_VERSIONS: tuple[tuple[date, str], ...] = ((date.min, RULE_VERSION),)


@dataclass(frozen=True)
class Share:
    key: tuple[str, str]  # stable sort key: (unit number, party id or "vacancy")
    weight: Decimal


def distribute(total: Decimal, shares: list[Share]) -> dict[tuple[str, str], Decimal]:
    """Largest remainder on cents; ties resolved by the stable key (D08: 100 / 3 -> 33.34 first)."""
    ordered = sorted(shares, key=lambda s: s.key)
    weight_sum = sum((s.weight for s in ordered), Decimal(0))
    if weight_sum <= 0:
        raise ValueError("Verteilungsgewichte ergeben null")
    exact = {s.key: total * s.weight / weight_sum for s in ordered}
    floored = {k: v.quantize(CENT, rounding=ROUND_DOWN) for k, v in exact.items()}
    rest = int(((total - sum(floored.values(), Decimal(0))) / CENT).to_integral_value())
    order = sorted(ordered, key=lambda s: (-(exact[s.key] - floored[s.key]), s.key))
    for s in order[:rest]:
        floored[s.key] += CENT
    return floored


def rule_version(period_from: date) -> str:
    """Version whose validity starts latest but not after the period start (D28)."""
    applicable = [v for valid_from, v in RULE_VERSIONS if valid_from <= period_from]
    if not applicable:
        raise ValueError("Keine Regelversion für den Zeitraum")
    return applicable[-1]


def days(start: date, end: date) -> int:
    return (end - start).days + 1


def overlap(a0: date, a1: date, b0: date, b1: date | None) -> tuple[date, date] | None:
    start, stop = max(a0, b0), min(a1, b1 or a1)
    return (start, stop) if start <= stop else None


def deadline(period_to: date) -> date:
    """Orientation only: end of the twelfth month after the period (§ 556 Abs. 3 BGB, R06).
    To be verified per case; access of the statement counts, not the PDF (A04)."""
    month = period_to.month + 12
    year = period_to.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    return date(year, month, calendar.monthrange(year, month)[1])


# CO2KostAufG, annex (residential buildings): lower bound of specific emissions
# (kg CO2 per m2 and year) -> tenant share in percent. Rule version as retrieved 23.09.2026
# (annex C R15); rounding of the input value and later rules (H05) are not applied here.
CO2_RESIDENTIAL_STEPS: tuple[tuple[Decimal, int], ...] = (
    (Decimal("0"), 100),
    (Decimal("12"), 90),
    (Decimal("17"), 80),
    (Decimal("22"), 70),
    (Decimal("27"), 60),
    (Decimal("32"), 50),
    (Decimal("37"), 40),
    (Decimal("42"), 30),
    (Decimal("47"), 20),
    (Decimal("52"), 5),
)
CO2_RULE_VERSION = "CO2KostAufG-Anlage-residential-2026-09-23"


def co2_split(specific_emissions: Decimal, costs: Decimal) -> dict[str, Decimal | int]:
    """D10: 12,0 kg/m2/a and 100,00 EUR -> tenant 90,00, landlord 10,00. No early rounding."""
    if specific_emissions < 0 or costs < 0:
        raise ValueError("Werte dürfen nicht negativ sein")
    tenant_percent = next(
        p for bound, p in reversed(CO2_RESIDENTIAL_STEPS) if specific_emissions >= bound
    )
    tenant = (costs * tenant_percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    return {"tenant_percent": tenant_percent, "tenant": tenant, "landlord": costs - tenant}
