"""Online meeting in the owner portal, CRM side (AD06 / GA11-03, section 14 owner phase 4).

Technically prepared, behind the per tenant switch ``hoa_online_meeting_setting.enabled``
(default off). The manager opens and closes the online voting of an agenda item, handles the
requests to speak and sees confirmations, proxies and online votes. Legally effective portal
steps (proxy grant, vote) additionally need release gate G4 (portal side).

No legal rule is decided here: whether a purely virtual meeting is admissible (enabling
resolution, GA07-01, V13) is not checked by this module; the existing meeting rules
(``meeting_rules``) stay in force and the portal only shows a note. Video runs over the
external conference link the manager entered (``dial_in_url``); there is no own video stack."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import (
    AgendaItem,
    Attendance,
    HoaOnlineMeetingSetting,
    Meeting,
    MeetingProxy,
    MeetingSpeakerRequest,
    Resolution,
    Vote,
)
from mhvp.hoa.property_scope import HOA_GUARD

router = APIRouter(prefix="/hoa", tags=["hoa"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")

ONLINE_NOTE = (
    "Online-Versammlung technisch vorbereitet (AD06). Ob eine rein virtuelle Versammlung "
    "zulässig ist (Beschlussgrundlage, GA07-01), prüft das System nicht; Klärung durch "
    "Rechtsberatung (AD06-01). Stimmabgabe und Vollmacht im Portal nur mit Freigabestufe G4."
)
OPEN_STATUSES = ("invited", "held")


class HoaOnlineSettingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class HoaSpeakerHandleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(done|withdrawn)$")


def now() -> datetime:
    return datetime.now(UTC)


async def online_enabled(session: AsyncSession) -> bool:
    """Tenant switch (RLS limits the query to the tenant of the session); no row means off."""
    return bool(await session.scalar(select(HoaOnlineMeetingSetting.enabled)))


async def ensure_online_enabled(session: AsyncSession) -> None:
    if not await online_enabled(session):
        raise ProblemError(ErrorCodes.HOA_ONLINE_MEETING_DISABLED)


def ensure_online_meeting(meeting: Meeting) -> None:
    """Online participation only for a hybrid or virtual meeting that is invited or held."""
    if meeting.mode == "presence":
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Online-Teilnahme nur bei hybrider oder virtueller Form."
        )
    if meeting.status not in OPEN_STATUSES:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Versammlung nicht eingeladen oder beendet.")


def voting_state(item: AgendaItem, announced: bool) -> str:
    """not_opened, open, closed or announced (result visible)."""
    if announced:
        return "announced"
    if item.voting_opened_at is None:
        return "not_opened"
    if item.voting_closed_at is not None:
        return "closed"
    return "open"


async def announced_items(session: AsyncSession, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, Any]:
    if not item_ids:
        return {}
    rows = await session.scalars(
        select(Resolution).where(
            Resolution.subject_type == "agenda_item", Resolution.subject_id.in_(item_ids)
        )
    )
    return {r.subject_id: r for r in rows.all() if r.subject_id is not None}


def proxy_active(p: MeetingProxy, day: date, at: datetime | None = None) -> bool:
    if p.valid_from > day or (p.valid_to is not None and p.valid_to < day):
        return False
    return p.revoked_at is None or (at is not None and p.revoked_at > at)


def proxy_out(p: MeetingProxy) -> dict[str, Any]:
    return {
        "id": p.id,
        "legal_entity_id": p.legal_entity_id,
        "grantor_contract_id": p.grantor_contract_id,
        "proxy_kind": p.proxy_kind,
        "proxy_contract_id": p.proxy_contract_id,
        "meeting_id": p.meeting_id,
        "valid_from": p.valid_from,
        "valid_to": p.valid_to,
        "document_id": p.document_id,
        "revoked_at": p.revoked_at,
        "created_at": p.created_at,
    }


def speaker_out(r: MeetingSpeakerRequest) -> dict[str, Any]:
    return {
        "id": r.id,
        "meeting_id": r.meeting_id,
        "agenda_item_id": r.agenda_item_id,
        "contract_id": r.contract_id,
        "requested_at": r.requested_at,
        "note": r.note,
        "status": r.status,
        "handled_at": r.handled_at,
    }


async def _meeting(session: AsyncSession, meeting_id: uuid.UUID) -> Meeting:
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return meeting


async def _item(session: AsyncSession, meeting: Meeting, item_id: uuid.UUID) -> AgendaItem:
    item = await session.get(AgendaItem, item_id, with_for_update=True)
    if item is None or item.meeting_id != meeting.id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return item


# Settings ----------------------------------------------------------------------------------


@router.get("/online-meeting-settings", summary="Online-Versammlung im Portal (Schalter)")
async def get_online_setting(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return {"enabled": await online_enabled(session), "note": ONLINE_NOTE}


@router.put("/online-meeting-settings", summary="Online-Versammlung im Portal setzen")
async def put_online_setting(
    body: HoaOnlineSettingIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> dict[str, Any]:
    """Operator decision after legal review (AD06-01); the system asserts no admissibility."""
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(HoaOnlineMeetingSetting).with_for_update())
        if row is None:
            row = HoaOnlineMeetingSetting(tenant_id=principal.tenant_id, enabled=body.enabled)
            session.add(row)
        row.enabled = body.enabled
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_online_meeting_setting.updated",
            entity_type="hoa_online_meeting_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled},
        )
        return {"enabled": body.enabled, "note": ONLINE_NOTE}


# Voting window -----------------------------------------------------------------------------


async def _set_voting(
    request: Request, principal: TenantPrincipal, meeting_id: uuid.UUID, item_id: uuid.UUID, op: str
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await ensure_online_enabled(session)
        meeting = await _meeting(session, meeting_id)
        if meeting.status in ("closing", "closed"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Protokoll im Abschluss: gesperrt.")
        if meeting.status == "disrupted":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Versammlung gestört: erst Fortsetzung dokumentieren."
            )
        ensure_online_meeting(meeting)
        item = await _item(session, meeting, item_id)
        announced = bool(await announced_items(session, [item.id]))
        if announced:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ergebnis bereits verkündet.")
        if item.result in ("deferred", "no_vote"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="TOP vertagt oder ohne Abstimmung.")
        if op == "open":
            if item.voting_opened_at is not None:
                raise ProblemError(ErrorCodes.CONFLICT, detail="Abstimmung bereits geöffnet.")
            item.voting_opened_at = now()
        else:
            if item.voting_opened_at is None or item.voting_closed_at is not None:
                raise ProblemError(ErrorCodes.CONFLICT, detail="Abstimmung nicht geöffnet.")
            item.voting_closed_at = now()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"meeting_agenda_item.voting_{'opened' if op == 'open' else 'closed'}",
            entity_type="meeting_agenda_item",
            entity_id=item.id,
            actor_user_id=principal.user_id,
            payload={"meeting_id": str(meeting.id)},
        )
        await session.flush()
        return {
            "id": item.id,
            "voting_opened_at": item.voting_opened_at,
            "voting_closed_at": item.voting_closed_at,
            "voting_state": voting_state(item, False),
        }


@router.post(
    "/meetings/{meeting_id}/agenda/{item_id}/voting/open",
    summary="Online-Abstimmung des TOP öffnen",
)
async def open_voting(
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    return await _set_voting(request, principal, meeting_id, item_id, "open")


@router.post(
    "/meetings/{meeting_id}/agenda/{item_id}/voting/close",
    summary="Online-Abstimmung des TOP schließen",
)
async def close_voting(
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    return await _set_voting(request, principal, meeting_id, item_id, "close")


# Speaker requests --------------------------------------------------------------------------


@router.post(
    "/meetings/{meeting_id}/speaker-requests/{request_id}",
    summary="Wortmeldung abarbeiten",
)
async def handle_speaker_request(
    meeting_id: uuid.UUID,
    request_id: uuid.UUID,
    body: HoaSpeakerHandleIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(MeetingSpeakerRequest, request_id, with_for_update=True)
        if row is None or row.meeting_id != meeting_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status != "open":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Wortmeldung bereits abgearbeitet.")
        row.status = body.status
        row.handled_at = now()
        row.handled_by = principal.user_id
        await session.flush()
        return speaker_out(row)


# Overview ----------------------------------------------------------------------------------


@router.get(
    "/meetings/{meeting_id}/online",
    summary="Online-Teilnahme: Zusagen, Vollmachten, Wortmeldungen, Online-Stimmen",
    dependencies=[Depends(strict_query)],
)
async def online_overview(
    meeting_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        meeting = await _meeting(session, meeting_id)
        day = meeting.scheduled_at.date()
        confirmed = (
            await session.scalars(
                select(Attendance).where(
                    Attendance.meeting_id == meeting.id,
                    Attendance.portal_confirmed_at.is_not(None),
                )
            )
        ).all()
        proxies = (
            await session.scalars(
                select(MeetingProxy)
                .where(
                    MeetingProxy.legal_entity_id == meeting.legal_entity_id,
                    or_(MeetingProxy.meeting_id.is_(None), MeetingProxy.meeting_id == meeting.id),
                )
                .order_by(MeetingProxy.created_at)
            )
        ).all()
        speakers = (
            await session.scalars(
                select(MeetingSpeakerRequest)
                .where(MeetingSpeakerRequest.meeting_id == meeting.id)
                .order_by(MeetingSpeakerRequest.requested_at, MeetingSpeakerRequest.id)
            )
        ).all()
        items = (
            await session.scalars(
                select(AgendaItem)
                .where(AgendaItem.meeting_id == meeting.id)
                .order_by(AgendaItem.position)
            )
        ).all()
        announced = await announced_items(session, [i.id for i in items])
        online_votes: dict[uuid.UUID, int] = {}
        for v in (
            await session.scalars(
                select(Vote).where(
                    Vote.agenda_item_id.in_([i.id for i in items]), Vote.channel == "online"
                )
            )
        ).all():
            online_votes[v.agenda_item_id] = online_votes.get(v.agenda_item_id, 0) + 1
        return {
            "enabled": await online_enabled(session),
            "note": ONLINE_NOTE,
            "has_conference_link": bool(meeting.dial_in_url),
            "confirmations": [
                {"contract_id": a.contract_id, "confirmed_at": a.portal_confirmed_at}
                for a in confirmed
            ],
            "proxies": [proxy_out(p) | {"active": proxy_active(p, day)} for p in proxies],
            "speaker_requests": [speaker_out(r) for r in speakers],
            "items": [
                {
                    "id": i.id,
                    "position": i.position,
                    "title": i.title,
                    "voting_opened_at": i.voting_opened_at,
                    "voting_closed_at": i.voting_closed_at,
                    "voting_state": voting_state(i, i.id in announced),
                    "online_votes": online_votes.get(i.id, 0),
                }
                for i in items
            ],
        }
