"""Persistent tenant switches of the calculation rules (AK01, GAI-202, GAI-214, GAI-204).

Three columns of ``tenant_settings`` (migration 0447), each with the conservative default of
the previous behaviour; no row or no value means the default:

* ``heating_negative_costs_mode``: ``legacy_warn`` (negative heating cost parts are not
  distributed, a warning is shown) or ``distribute`` (signed distribution), AJ01-01.
* ``hoa_remainder_mode``: ``report_only`` (twelve equal monthly rates, difference reported),
  ``first_month`` or ``last_month``, AJ01-02.
* ``check_amounts_tolerance_cents``: 0 or 1 cent tolerance of the gross check, AJ02-01.

The switches change calculation drafts only; nothing is booked, sent or released. Statements
stay behind G3/G4.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.platform.models import TenantSettings

NEGATIVE_COSTS_MODES = ("legacy_warn", "distribute")
REMAINDER_MODES = ("report_only", "first_month", "last_month")
TOLERANCE_CENTS = (0, 1)


@dataclass(frozen=True)
class CalcSettings:
    heating_negative_costs_mode: str = "legacy_warn"
    hoa_remainder_mode: str = "report_only"
    check_amounts_tolerance_cents: int = 1

    @property
    def check_amounts_tolerance(self) -> Decimal:
        return Decimal(self.check_amounts_tolerance_cents) / 100


async def load(session: AsyncSession) -> CalcSettings:
    """Switches of the tenant of the session (RLS scoped); defaults without a row."""
    row = (
        await session.execute(
            select(
                TenantSettings.heating_negative_costs_mode,
                TenantSettings.hoa_remainder_mode,
                TenantSettings.check_amounts_tolerance_cents,
            )
        )
    ).first()
    if row is None:
        return CalcSettings()
    default = CalcSettings()
    return CalcSettings(
        heating_negative_costs_mode=row[0] or default.heating_negative_costs_mode,
        hoa_remainder_mode=row[1] or default.hoa_remainder_mode,
        check_amounts_tolerance_cents=(
            default.check_amounts_tolerance_cents if row[2] is None else int(row[2])
        ),
    )


async def check_amounts_tolerance(session: AsyncSession) -> Decimal:
    return (await load(session)).check_amounts_tolerance
