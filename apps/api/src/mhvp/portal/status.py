"""Persistent status model of the portal account (Masterprompt 6.2, GA02-07, AB08).

Stored values (check constraint ``ck_portal_account_status``, migration 0310):
``not_invited``, ``invited``, ``active``, ``locked``, ``expired``, ``revoked``.

Transitions (the only writers; see the module README):

* creation without invitation -> ``not_invited``; creation with invitation -> ``invited``
* ``not_invited`` / ``expired`` -> ``invited`` when an invitation is sent
* ``invited`` -> ``active`` on acceptance (``activated_at`` set)
* ``invited`` -> ``expired`` by the beat job once ``invitation_expires_at`` has passed
* ``active`` -> ``locked`` while the platform user is locked or deactivated (beat job)
* ``locked`` -> ``active`` when the lock is lifted (beat job), only for an activated account
* any -> ``revoked`` when access is withdrawn; ``revoked`` is final for the job
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.events import emit
from mhvp.portal.models import PortalAccount

STATUSES = ("not_invited", "invited", "active", "locked", "expired", "revoked")
LOGIN_STATUSES = ("active", "locked")  # locked accounts log in again once the lock lapses


def user_locked(user: Any, now: datetime) -> bool:
    return bool(not user.active or (user.locked_until is not None and user.locked_until > now))


def target_status(account: PortalAccount, user: Any, now: datetime) -> str:
    """Status the account has to carry at ``now`` (pure, no write)."""
    status = account.status
    if status == "invited" and (
        account.invitation_expires_at is not None and account.invitation_expires_at < now
    ):
        return "expired"
    if status == "active" and user_locked(user, now):
        return "locked"
    if status == "locked" and account.activated_at is not None and not user_locked(user, now):
        return "active"
    return status


async def sync_statuses(
    session: AsyncSession, tenant_id: uuid.UUID, now: datetime | None = None
) -> dict[str, int]:
    """Writes the status transitions that are due; idempotent (a second run changes nothing).
    Runs in a tenant transaction."""
    from mhvp.platform.models import User

    moment = now or datetime.now(UTC)
    counts = {"expired": 0, "locked": 0, "unlocked": 0}
    rows = (
        await session.execute(
            select(PortalAccount, User)
            .join(User, User.id == PortalAccount.user_id)
            .where(PortalAccount.status.in_(("invited", "active", "locked")))
            .with_for_update(of=PortalAccount)
        )
    ).all()
    for account, user in rows:
        new = target_status(account, user, moment)
        if new == account.status:
            continue
        old, account.status = account.status, new
        key = "expired" if new == "expired" else "locked" if new == "locked" else "unlocked"
        counts[key] += 1
        await emit(
            session,
            tenant_id=tenant_id,
            type=f"portal_account.{'unlocked' if key == 'unlocked' else new}",
            entity_type="portal_account",
            entity_id=account.id,
            actor_user_id=None,
            payload={"from": old, "to": new},
        )
    return counts
