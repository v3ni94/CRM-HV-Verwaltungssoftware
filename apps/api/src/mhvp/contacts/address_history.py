"""Address history of contacts (AN05, GAJ-610, OPEN_QUESTIONS AM14-01).

Tenant switch ``contacts.address_history`` in ``tenant_settings.sources`` (default off, which is
the behaviour before AN05: a full replace deletes and rewrites the addresses). When on, a
replace keeps unchanged addresses, closes removed or changed ones (``valid_to`` the day before
today, at the earliest ``valid_from``, ``superseded_at`` now, no longer primary) and starts new
ones with ``valid_from`` today. Retention and erasure of former addresses are not decided
(AM14-01): erasure removes every row of the contact as before, nothing is deleted on a timer.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import ADDRESS_HISTORY_OPTION, ContactAddress
from mhvp.core.clock import local_today

SWITCH_KEY = "contacts.address_history"
_CONTENT = (
    "label",
    "street",
    "house_number",
    "postal_code",
    "city",
    "state",
    "country",
    "addition",
)


def enabled_from(sources: dict[str, Any] | None) -> bool:
    return bool((sources or {}).get(SWITCH_KEY) is True)


async def is_enabled(session: AsyncSession) -> bool:
    from mhvp.platform.models import TenantSettings

    return enabled_from(await session.scalar(select(TenantSettings.sources)))


def _key(item: Any) -> tuple[Any, ...]:
    return tuple(getattr(item, field) for field in _CONTENT)


def closing_date(valid_from: date | None, today: date) -> date:
    """Last day of a replaced address: yesterday, never before its own start (CHECK)."""
    end = today - timedelta(days=1)
    return max(end, valid_from) if valid_from is not None else end


async def replace_with_history(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    contact_id: uuid.UUID,
    addresses: list[Any],
) -> None:
    """Replace the current addresses keeping the former ones as closed history rows."""
    today = local_today()
    now = datetime.now(UTC)
    current = list(
        (
            await session.scalars(
                select(ContactAddress).where(ContactAddress.contact_id == contact_id)
            )
        ).all()
    )
    unmatched = {row.id: row for row in current}
    for address in addresses:
        match = next((r for r in unmatched.values() if _key(r) == _key(address)), None)
        if match is not None:
            del unmatched[match.id]
            match.is_primary = address.is_primary
            continue
        session.add(
            ContactAddress(
                tenant_id=tenant_id,
                contact_id=contact_id,
                valid_from=today,
                **address.model_dump(exclude={"valid_from", "valid_to", "superseded_at"}),
            )
        )
    for row in unmatched.values():
        row.valid_to = closing_date(row.valid_from, today)
        row.superseded_at = now
        row.is_primary = False


async def addresses_as_of(
    session: AsyncSession, contact_id: uuid.UUID, as_of: date | None, include_history: bool
) -> list[ContactAddress]:
    """Addresses valid on ``as_of`` (valid_from empty or on/before it, valid_to empty or on/after
    it), or with ``include_history`` every row including closed ones."""
    query = select(ContactAddress).where(ContactAddress.contact_id == contact_id)
    if as_of is not None:
        query = query.where(
            or_(ContactAddress.valid_from.is_(None), ContactAddress.valid_from <= as_of),
            or_(ContactAddress.valid_to.is_(None), ContactAddress.valid_to >= as_of),
        )
    elif not include_history:
        query = query.where(and_(ContactAddress.superseded_at.is_(None)))
    query = query.order_by(
        ContactAddress.valid_from.desc().nulls_last(), ContactAddress.created_at
    ).execution_options(**{ADDRESS_HISTORY_OPTION: True})
    return list((await session.scalars(query)).all())
