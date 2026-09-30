"""Portal feature switches per tenant and representation helpers (M21-08, M21-05).

The switches are a Produktschutz configuration, not a legal rule: every switch is off until the
management turns it on. Turning one on never opens a gate: the AI pre-qualification still needs
the approved AI provider with data processing agreement (see ``mhvp.portal.chat``) and the
support view still needs the consent of the portal user (see ``mhvp.portal.support``)."""

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.portal.models import PortalAccount, PortalFeatureSetting, PortalRepresentation
from mhvp.workspace.services import local_today

FEATURES = ("chat_enabled", "chat_ai_prequalification_enabled", "support_login_enabled")


async def get_or_default(session: AsyncSession) -> PortalFeatureSetting:
    """The tenant's row (RLS scoped) or an unsaved object with all switches off."""
    row = await session.scalar(select(PortalFeatureSetting))
    if row is not None:
        return row
    return PortalFeatureSetting(
        chat_enabled=False, chat_ai_prequalification_enabled=False, support_login_enabled=False
    )


def feature_dict(row: PortalFeatureSetting) -> dict[str, bool]:
    return {name: bool(getattr(row, name)) for name in FEATURES}


def _active(rep: PortalRepresentation, today: date) -> bool:
    return (
        rep.status == "active"
        and rep.valid_from <= today
        and (rep.valid_to is None or rep.valid_to >= today)
    )


async def active_representations(
    session: AsyncSession, account: PortalAccount
) -> list[dict[str, Any]]:
    today = local_today()
    rows = (
        await session.scalars(
            select(PortalRepresentation)
            .where(PortalRepresentation.account_id == account.id)
            .order_by(PortalRepresentation.valid_from)
        )
    ).all()
    return [
        {
            "id": r.id,
            "principal_contact_id": r.principal_contact_id,
            "valid_from": r.valid_from,
            "valid_to": r.valid_to,
        }
        for r in rows
        if _active(r, today)
    ]
