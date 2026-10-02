"""Object period lock check for the banking verifier (GAE-02, AE20, rule P06-02).

Before an automatic posting the properties of the settled open items are resolved from the
lines of their originating entries. When the tenant runs ``object_period`` and an active lock
of one of these properties covers the booking date, the verifier skips the case (same result
as the ledger wide lock). Read only, nothing is booked here.
"""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import period_lock
from mhvp.accounting.models import Ledger, OpenItem, PeriodLock


def settled_item_ids(proposals: list[dict[str, Any]]) -> set[uuid.UUID]:
    """Open item ids named by the splits of all proposals."""
    found: set[uuid.UUID] = set()
    for proposal in proposals:
        for split in proposal.get("splits") or []:
            ref = split.get("open_item_id")
            if ref:
                try:
                    found.add(uuid.UUID(str(ref)))
                except ValueError:
                    continue
    return found


async def object_locked(
    session: AsyncSession, ledger: Ledger, day: date | None, item_ids: set[uuid.UUID]
) -> bool:
    """True when an active property lock covers ``day`` for the properties of the items."""
    if day is None:
        return False
    setting = await period_lock.get_setting(session)
    if setting is None or setting.lock_mode != "object_period":
        return False
    property_ids: set[uuid.UUID] = set()
    if ledger.property_id is not None:
        property_ids.add(ledger.property_id)
    if item_ids:
        entries = (
            await session.scalars(
                select(OpenItem.journal_entry_id).where(OpenItem.id.in_(item_ids))
            )
        ).all()
        for entry_id in set(entries):
            property_ids |= await period_lock.property_ids_of_lines(session, ledger, entry_id)
    if not property_ids:
        return False
    hit = await session.scalar(
        select(PeriodLock.id)
        .where(
            PeriodLock.ledger_id == ledger.id,
            PeriodLock.property_id.in_(property_ids),
            PeriodLock.released_at.is_(None),
            PeriodLock.period_from <= day,
            PeriodLock.period_to >= day,
        )
        .limit(1)
    )
    return hit is not None
