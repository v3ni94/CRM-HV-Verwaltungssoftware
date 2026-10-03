"""Tenant switches of the rent increase process (AN18, GAK-202, GAK-203).

Stored as string values in ``tenant_settings.sources`` (no schema change). The platform fixes no
legal duration: without a value the system proposes no blocking date and creates no proposal.

* ``rent_increase_block_months.<basis>``: months from the effective date of an applied increase
  that the case proposes as ``rent_increase_block_until`` (basis mietspiegel, comparison,
  modernization, index, graduated). Empty means no proposal (question AN18-01).
* ``rent_increase_proposals``: ``off`` (default) or ``draft``. With ``draft`` the daily job
  prepares due graduated steps and index adjustments as draft cases, never applies them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.platform.models import TenantSettings

BASES = ("mietspiegel", "comparison", "modernization", "index", "graduated")
PROPOSAL_MODES = ("off", "draft")
_BLOCK = "rent_increase_block_months."
_PROPOSALS = "rent_increase_proposals"


@dataclass(frozen=True)
class IncreaseSettings:
    block_months: dict[str, int] = field(default_factory=dict)
    proposals: str = "off"


def parse(sources: dict[str, object] | None) -> IncreaseSettings:
    src = sources or {}
    months: dict[str, int] = {}
    for basis in BASES:
        raw = src.get(_BLOCK + basis)
        if isinstance(raw, str) and raw.isdigit() and 0 < int(raw) <= 120:
            months[basis] = int(raw)
    mode = src.get(_PROPOSALS)
    return IncreaseSettings(
        months, mode if isinstance(mode, str) and mode in PROPOSAL_MODES else "off"
    )


async def load(session: AsyncSession) -> IncreaseSettings:
    """Switches of the session tenant (RLS scoped); defaults without a row."""
    return parse(await session.scalar(select(TenantSettings.sources)))


def store(sources: dict[str, object] | None, value: IncreaseSettings) -> dict[str, object]:
    """New ``sources`` document with the switches replaced; other keys stay untouched."""
    out = {k: v for k, v in (sources or {}).items() if not k.startswith(_BLOCK)}
    out.update({_BLOCK + b: str(m) for b, m in value.block_months.items()})
    out[_PROPOSALS] = value.proposals
    return out


def add_months(day: date, months: int) -> date:
    """Same day ``months`` later, clamped to the month end (31.01. + 1 = 28./29.02.)."""
    y, m = divmod(day.month - 1 + months, 12)
    year, month = day.year + y, m + 1
    for d in (day.day, 30, 29, 28):
        try:
            return date(year, month, min(d, day.day))
        except ValueError:
            continue
    raise ValueError(day)  # pragma: no cover


def block_proposal(settings: IncreaseSettings, basis: str, effective: date) -> date | None:
    """Proposed blocking date after an applied increase, or None without a tenant value."""
    months = settings.block_months.get(basis)
    return None if months is None else add_months(effective, months)
