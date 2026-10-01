"""Owner portal: owners' meetings of the own community with dial-in data (M25-03, V13).

Read only. Requires the portal role ``owner`` (active grant with legal basis
``hoa_member_right``, 6.9.6, same scope rule as ``mhvp.portal.owner``); tenants, providers
and staff accounts are answered with 403. Dial-in data (link, access data) are shown only
for hybrid or virtual meetings of a community the account is an owner of, and only once the
invitation was recorded; the CRM never prints them into the invitation letter."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.hoa import meeting_rules
from mhvp.portal.owner import _owner_scope
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal", tags=["Portal"])

MODE_LABEL = {"presence": "Präsenz", "hybrid": "Hybrid", "virtual": "Virtuell"}
DIAL_IN_NOTE = (
    "Zugangsdaten nur für Eigentümer dieser Gemeinschaft. Bitte nicht weitergeben. "
    "Technische Störungen bitte der Verwaltung melden; sie werden im Protokoll vermerkt."
)


@router.get(
    "/meetings",
    summary="Eigentümerversammlungen der eigenen Gemeinschaft (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def meetings(request: Request, ctx: Portal = Depends(portal_user)) -> list[dict[str, Any]]:
    from mhvp.hoa.models import Meeting, Resolution
    from mhvp.properties.models import LegalEntity

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, _ = await _owner_scope(session, account, local_today())
        names: dict[uuid.UUID, str] = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(LegalEntity.id, LegalEntity.name).where(LegalEntity.id.in_(hoa_ids))
                )
            ).all()
        }
        rows = (
            await session.scalars(
                select(Meeting)
                .where(Meeting.legal_entity_id.in_(hoa_ids), Meeting.status != "planned")
                .order_by(Meeting.scheduled_at.desc())
            )
        ).all()
        out: list[dict[str, Any]] = []
        for m in rows:
            basis = (
                await session.get(Resolution, m.virtual_basis_resolution_id)
                if m.virtual_basis_resolution_id
                else None
            )
            show_dial_in = m.mode in ("hybrid", "virtual") and m.status in ("invited", "held")
            out.append(
                {
                    "id": m.id,
                    "legal_entity_name": names.get(m.legal_entity_id),
                    "kind": m.kind,
                    "mode": m.mode,
                    "mode_label": MODE_LABEL.get(m.mode, m.mode),
                    "scheduled_at": m.scheduled_at,
                    "location": m.location,
                    # GA03-01: only the public description reaches the portal
                    "public_description": m.public_description,
                    "ends_at": m.ends_at,
                    "status": m.status,
                    "invited_at": m.invited_at,
                    "notice": meeting_rules.invitation_notice(m, basis),
                    "dial_in_url": m.dial_in_url if show_dial_in else None,
                    "dial_in_access": m.dial_in_access if show_dial_in else None,
                    "dial_in_note": DIAL_IN_NOTE if show_dial_in else None,
                }
            )
        return out
