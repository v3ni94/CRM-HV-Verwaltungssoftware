"""Scope of property marketing (AN19, GAK-208; section 1 Abgrenzung, 18 M26).

Section 1 limits letting to exposé and vacancy list; sale listings and their publication go
beyond that scope. Until the operator decides (question AN19-02, ADR per 0.3, no gate) they
stay behind the tenant switch ``letting.sale_marketing`` in ``tenant_settings.sources``
(default off). Off: sale listings can be drafted, but neither activated nor handed to a
broker provider. Rental listings and the vacancy list are unchanged.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError

SWITCH_KEY = "letting.sale_marketing"
LOCKED_DETAIL = (
    "Verkaufsinserate sind für diesen Mandanten nicht freigeschaltet "
    "(Schalter letting.sale_marketing, offene Frage AN19-02)."
)


def enabled_from(sources: dict[str, Any] | None) -> bool:
    return bool((sources or {}).get(SWITCH_KEY) is True)


async def is_enabled(session: AsyncSession) -> bool:
    from mhvp.platform.models import TenantSettings

    return enabled_from(await session.scalar(select(TenantSettings.sources)))


async def ensure_sale_allowed(session: AsyncSession, kind: str) -> None:
    """Refuse activation or publication of a sale listing while the switch is off."""
    if kind == "sale" and not await is_enabled(session):
        raise ProblemError(ErrorCodes.CONFLICT, detail=LOCKED_DETAIL)


async def set_enabled(session: AsyncSession, enabled: bool) -> bool:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings).with_for_update())
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    before = enabled_from(row.sources)
    row.sources = {**(row.sources or {}), SWITCH_KEY: bool(enabled)}
    await session.flush()
    return before
