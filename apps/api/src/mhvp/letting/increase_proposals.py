"""Computation core of rent increase proposals (AN18, GAK-203, partial).

Pure functions for a later daily job that prepares graduated steps and index adjustments as
draft ``rent_increase_case`` rows (never applied, switch ``rent_increase_proposals`` default
``off``). The structured contract agreement (index clause, step table) and the maintained
consumer price index table need a schema change that is reported as open point; until then the
functions are used only with explicitly passed values. No waiting period, index source or
notice form is fixed here (question AN18-01, Rechtsanwalt, G1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from mhvp.core.money import round_cents


@dataclass(frozen=True)
class GraduatedStep:
    valid_from: date
    net: Decimal


@dataclass(frozen=True)
class IncreaseProposal:
    basis: str
    effective_date: date
    current_rent: Decimal
    target_rent: Decimal
    reason: str


def due_graduated_steps(
    steps: list[GraduatedStep],
    existing_starts: set[date],
    today: date,
    horizon_days: int,
    current_rent: Decimal,
) -> list[IncreaseProposal]:
    """Steps starting within ``horizon_days`` from ``today`` without a rent line yet."""
    until = today + timedelta(days=horizon_days)
    out: list[IncreaseProposal] = []
    previous = current_rent
    for step in sorted(steps, key=lambda s: s.valid_from):
        if step.valid_from in existing_starts or not today <= step.valid_from <= until:
            previous = step.net if step.valid_from <= today else previous
            continue
        out.append(
            IncreaseProposal(
                "graduated",
                step.valid_from,
                previous,
                step.net,
                f"Staffelstufe ab {step.valid_from.strftime('%d.%m.%Y')} laut Vertrag.",
            )
        )
        previous = step.net
    return out


def index_adjustment(
    current_rent: Decimal,
    base_index: Decimal,
    current_index: Decimal,
    effective_date: date,
) -> IncreaseProposal | None:
    """Rent changed in the ratio of the index values (rounded half up); None without a rise.

    Whether and when an adjustment may be declared is not decided here (AN18-01)."""
    if base_index <= 0 or current_index <= base_index:
        return None
    target = round_cents(current_rent * current_index / base_index)
    change = round_cents((current_index / base_index - 1) * 100)
    return IncreaseProposal(
        "index",
        effective_date,
        current_rent,
        target,
        f"Indexänderung {base_index} auf {current_index} ({change} Prozent), nur Vorschlag.",
    )
