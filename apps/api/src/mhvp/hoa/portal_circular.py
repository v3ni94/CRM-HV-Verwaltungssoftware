"""Circular resolution in the owner portal (AG07 / GAF-32, section 14 owner phase 4).

A circular resolution procedure is an owners' meeting of kind ``circular_resolution`` that was
invited and whose agenda items carry the resolution texts. Owners see the running procedures of
their own units and cast one vote per unit and item (channel circular). The evidence of each
vote is its time stamp, the portal user and the SHA-256 of the item text voted on.

Behind the tenant switch ``portal_circular_resolution_enabled`` (default off, 403 MHVP-HOA-0037)
and release gate G4 for the vote (403, nothing is stored). The majority check stays unchanged
(``hoa.majority`` and the result determination in the CRM); the admissibility of the text form
in the portal is not decided by the system (open question AE31-01)."""

import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.hoa.models import AgendaItem, HoaOnlineMeetingSetting, Meeting, Resolution, Vote
from mhvp.hoa.property_scope import HOA_GUARD
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

crm_router = APIRouter(prefix="/hoa", tags=["hoa"], dependencies=[Depends(HOA_GUARD)])
portal_router = APIRouter(prefix="/portal", tags=["Portal"])
READ = require_permission("accounting:read")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")
RUNNING = ("invited", "held")
NOTE = (
    "Stimmabgabe im Umlaufverfahren in Textform. Die Verwaltung stellt das Ergebnis fest; "
    "die Zulässigkeit der Stimmabgabe im Portal ist rechtlich zu prüfen (AE31-01)."
)


class HoaPortalCircularSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class PortalCircularVoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agenda_item_id: uuid.UUID
    contract_id: uuid.UUID
    choice: str = Field(pattern="^(yes|no|abstain)$")


def wording_hash(item: AgendaItem) -> str:
    """SHA-256 of the item text the owner votes on (title, line feed, proposal)."""
    text = f"{item.title}\n{item.proposal or ''}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def circular_enabled(session: AsyncSession) -> bool:
    """RLS limits the query to the session tenant; no row means off."""
    return bool(
        await session.scalar(select(HoaOnlineMeetingSetting.portal_circular_resolution_enabled))
    )


async def _announced(session: AsyncSession, item_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not item_ids:
        return set()
    rows = await session.scalars(
        select(Resolution.subject_id).where(
            Resolution.subject_type == "agenda_item", Resolution.subject_id.in_(item_ids)
        )
    )
    return {r for r in rows.all() if r is not None}


def _vote_out(v: Vote) -> dict[str, Any]:
    return {
        "id": v.id,
        "agenda_item_id": v.agenda_item_id,
        "contract_id": v.contract_id,
        "choice": v.choice,
        "cast_at": v.created_at,
        "portal_user_id": v.portal_user_id,
        "wording_sha256": v.wording_sha256,
    }


# CRM -------------------------------------------------------------------------------------


@crm_router.get(
    "/portal-circular-settings", summary="Umlaufbeschluss im Eigentümerportal (Schalter)"
)
async def get_setting(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return {"enabled": await circular_enabled(session), "note": NOTE}


class HoaPortalCircularSettingOut(BaseModel):
    """AK11 (GAI-304): typed response, ``extra="allow"`` keeps later fields."""

    model_config = ConfigDict(extra="allow")
    enabled: bool
    note: str


@crm_router.put(
    "/portal-circular-settings",
    summary="Umlaufbeschluss im Eigentümerportal setzen",
    response_model=HoaPortalCircularSettingOut,
)
async def put_setting(
    body: HoaPortalCircularSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> dict[str, Any]:
    """Operator decision after legal review (AE31-01); the vote additionally needs G4."""
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(HoaOnlineMeetingSetting).with_for_update())
        if row is None:
            row = HoaOnlineMeetingSetting(tenant_id=principal.tenant_id, enabled=False)
            session.add(row)
        row.portal_circular_resolution_enabled = body.enabled
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_portal_circular_setting.updated",
            entity_type="hoa_online_meeting_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled},
        )
        return {"enabled": body.enabled, "note": NOTE}


@crm_router.get(
    "/meetings/{meeting_id}/portal-circular-votes",
    summary="Portalstimmen eines Umlaufverfahrens (lesend)",
    dependencies=[Depends(strict_query)],
)
async def portal_votes(
    meeting_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        meeting = await session.get(Meeting, meeting_id)
        if meeting is None or meeting.kind != "circular_resolution":
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = await session.scalars(
            select(Vote)
            .join(AgendaItem, AgendaItem.id == Vote.agenda_item_id)
            .where(AgendaItem.meeting_id == meeting.id, Vote.portal_user_id.is_not(None))
            .order_by(Vote.created_at)
        )
        return [_vote_out(v) for v in rows.all()]


@crm_router.get(
    "/portal-circular-votes",
    summary="Portalstimmen laufender Umlaufverfahren einer Gemeinschaft (lesend)",
    dependencies=[Depends(strict_query)],
)
async def portal_votes_by_entity(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.execute(
            select(Vote, AgendaItem.title, Meeting.id)
            .join(AgendaItem, AgendaItem.id == Vote.agenda_item_id)
            .join(Meeting, Meeting.id == AgendaItem.meeting_id)
            .where(
                Meeting.legal_entity_id == legal_entity_id,
                Meeting.kind == "circular_resolution",
                Vote.portal_user_id.is_not(None),
            )
            .order_by(Vote.created_at)
        )
        return [
            _vote_out(v) | {"item_title": title, "meeting_id": mid} for v, title, mid in rows.all()
        ]


# Portal ----------------------------------------------------------------------------------


async def _scope(session: AsyncSession, account: Any) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    from mhvp.portal.owner import _owner_scope

    return await _owner_scope(session, account, local_today())


async def _eligible(session: AsyncSession, meeting: Meeting, own: set[uuid.UUID]) -> set[uuid.UUID]:
    from mhvp.hoa.meetings import _hoa_property, _members

    prop = await _hoa_property(session, meeting.legal_entity_id)
    return own & {c.id for c in await _members(session, prop, meeting.scheduled_at.date())}


@portal_router.get(
    "/circular-resolutions",
    summary="Laufende Umlaufbeschlüsse der eigenen Einheiten (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def list_circulars(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        hoa_ids, own = await _scope(session, account)
        enabled = await circular_enabled(session)
        out: list[dict[str, Any]] = []
        if enabled:
            meetings = await session.scalars(
                select(Meeting)
                .where(
                    Meeting.legal_entity_id.in_(hoa_ids),
                    Meeting.kind == "circular_resolution",
                    Meeting.status.in_(RUNNING),
                )
                .order_by(Meeting.scheduled_at)
            )
            for m in meetings.all():
                units = await _eligible(session, m, own)
                if not units:
                    continue
                items = (
                    await session.scalars(
                        select(AgendaItem)
                        .where(AgendaItem.meeting_id == m.id)
                        .order_by(AgendaItem.position)
                    )
                ).all()
                announced = await _announced(session, [i.id for i in items])
                votes = (
                    await session.scalars(
                        select(Vote).where(
                            Vote.agenda_item_id.in_([i.id for i in items]),
                            Vote.contract_id.in_(units),
                        )
                    )
                ).all()
                out.append(
                    {
                        "id": m.id,
                        "legal_entity_id": m.legal_entity_id,
                        "deadline": m.scheduled_at,
                        "description": m.public_description,
                        "own_contract_ids": sorted(str(u) for u in units),
                        "items": [
                            {
                                "id": i.id,
                                "position": i.position,
                                "title": i.title,
                                "proposal": i.proposal,
                                "wording_sha256": wording_hash(i),
                                "open": i.id not in announced
                                and i.result not in ("deferred", "no_vote"),
                                "own_votes": [
                                    _vote_out(v) for v in votes if v.agenda_item_id == i.id
                                ],
                            }
                            for i in items
                        ],
                    }
                )
        return {"enabled": enabled, "note": NOTE, "circulars": out}


@portal_router.post(
    "/circular-resolutions/{meeting_id}/vote",
    status_code=201,
    summary="Stimme im Umlaufverfahren abgeben (Eigentümer, G4)",
)
async def cast_vote(
    meeting_id: uuid.UUID,
    body: PortalCircularVoteIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    """One vote per own unit and item; a second vote is 409. Proxies are not accepted here."""
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        if not await circular_enabled(session):
            raise ProblemError(ErrorCodes.HOA_PORTAL_CIRCULAR_DISABLED)
        await ensure_release_gate_open(
            ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
        )
        hoa_ids, own = await _scope(session, account)
        meeting = await session.get(Meeting, meeting_id)
        if (
            meeting is None
            or meeting.legal_entity_id not in hoa_ids
            or meeting.kind != "circular_resolution"
        ):
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if meeting.status not in RUNNING:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Umlaufverfahren läuft nicht.")
        item = await session.get(AgendaItem, body.agenda_item_id, with_for_update=True)
        if item is None or item.meeting_id != meeting.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.contract_id not in await _eligible(session, meeting, own):
            raise ProblemError(
                ErrorCodes.FORBIDDEN, detail="Keine eigene stimmberechtigte Einheit."
            )
        if item.id in await _announced(session, [item.id]) or item.result in (
            "deferred",
            "no_vote",
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ergebnis bereits festgestellt.")
        digest = wording_hash(item)
        row = Vote(
            tenant_id=principal.tenant_id,
            agenda_item_id=item.id,
            contract_id=body.contract_id,
            choice=body.choice,
            excluded=False,
            channel="circular",
            cast_source="own",
            portal_user_id=principal.user_id,
            wording_sha256=digest,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Stimme bereits abgegeben.") from exc
        await session.refresh(row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting_vote.cast_circular_portal",
            entity_type="meeting_vote",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "agenda_item_id": str(item.id),
                "contract_id": str(body.contract_id),
                "wording_sha256": digest,
            },
        )
        return _vote_out(row)
