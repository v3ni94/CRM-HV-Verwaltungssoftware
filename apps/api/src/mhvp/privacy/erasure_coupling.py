"""Which references block a contact erasure (GAM-405, AP13).

Tenant switch ``privacy.erasure_coupling`` in ``tenant_settings.sources`` (default off, the
behaviour before AP13: every row with a foreign key to the contact blocks). When on, references
from communication, call and dispatch tables (``COUPLED_TABLES``) no longer block; they are
listed as non blocking entries (``blocking: false``) and recorded in the request result as
``coupled`` for a separate deletion of those rows under their own profile. Booking, contract
and every other reference keeps blocking. Which references may be coupled is open
(OPEN_QUESTIONS AP13-02); the coupled rows are not deleted by this switch.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

SWITCH_KEY = "privacy.erasure_coupling"
COUPLED_TABLES: frozenset[str] = frozenset({"message", "call_log", "dispatch", "postal_job"})


def enabled_from(sources: dict[str, Any] | None) -> bool:
    return bool((sources or {}).get(SWITCH_KEY) is True)


async def is_enabled(session: AsyncSession) -> bool:
    from mhvp.platform.models import TenantSettings

    return enabled_from(await session.scalar(select(TenantSettings.sources)))


def reference_class(table: str) -> str:
    return "communication" if table in COUPLED_TABLES else "business"


def blocking(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries that block; entries with ``blocking: false`` are information only."""
    return [b for b in found if b.get("blocking", True) is not False]
