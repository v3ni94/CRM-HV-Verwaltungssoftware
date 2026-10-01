"""Default team and assignee for the tickets of the property takeover checklist (V06-01).

Stored under the key ``takeover_tickets`` of the JSON document
``TenantSettings.objektakte_classification`` (same pattern as ``mhvp.ai.automation``), so no
migration is needed. Empty values mean "no assignment", which is also the behaviour without a
settings row. The setting only routes internal tasks; it posts nothing and decides nothing legal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Membership, MembershipStatus, TenantSettings
from mhvp.tickets.models import Team

KEY = "takeover_tickets"


@dataclass(frozen=True)
class TakeoverTicketDefaults:
    team_id: uuid.UUID | None = None
    assignee_user_id: uuid.UUID | None = None


def _parse(raw: Any) -> TakeoverTicketDefaults:
    data = raw if isinstance(raw, dict) else {}

    def one(name: str) -> uuid.UUID | None:
        try:
            return uuid.UUID(str(data[name])) if data.get(name) else None
        except ValueError:
            return None

    return TakeoverTicketDefaults(one("team_id"), one("assignee_user_id"))


async def load(session: AsyncSession) -> TakeoverTicketDefaults:
    document = await session.scalar(select(TenantSettings.objektakte_classification))
    return _parse((document or {}).get(KEY))


async def validate(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    team_id: uuid.UUID | None,
    assignee_user_id: uuid.UUID | None,
) -> None:
    """Team and assignee must belong to the tenant (422 otherwise)."""
    if team_id is not None and await session.get(Team, team_id) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Das Team gehört nicht zum Mandanten.")
    if assignee_user_id is not None:
        member = await session.scalar(
            select(Membership.id).where(
                Membership.tenant_id == tenant_id,
                Membership.user_id == assignee_user_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if member is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Der Zuständige ist kein aktives Mitglied des Mandanten.",
            )


async def save(
    session: AsyncSession, settings: TenantSettings, values: TakeoverTicketDefaults
) -> TakeoverTicketDefaults:
    document: dict[str, Any] = dict(settings.objektakte_classification or {})
    document[KEY] = {
        "team_id": str(values.team_id) if values.team_id else None,
        "assignee_user_id": str(values.assignee_user_id) if values.assignee_user_id else None,
    }
    settings.objektakte_classification = document  # reassigned, so the JSONB change is tracked
    await session.flush()
    return values
