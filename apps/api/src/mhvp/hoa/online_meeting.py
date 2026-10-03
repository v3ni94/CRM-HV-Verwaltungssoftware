"""Online meeting in the owner portal, CRM side (AD06 / GA11-03, section 14 owner phase 4).

Technically prepared, behind the per tenant switch ``hoa_online_meeting_setting.enabled``
(default off). The manager opens and closes the online voting of an agenda item, handles the
requests to speak and sees confirmations, proxies and online votes. Legally effective portal
steps (proxy grant, vote) additionally need release gate G4 (portal side).

No legal rule is decided here: whether a purely virtual meeting is admissible (enabling
resolution, GA07-01, V13) is not checked by this module; the existing meeting rules
(``meeting_rules``) stay in force and the portal only shows a note. Video runs over the
external conference link the manager entered (``dial_in_url``); there is no own video stack.

AE31 (AD06-01 to AD06-03): the tenant rule for a proxy vote against the owner's own vote
(``proxy_conflict_mode``, default ``flag``: the conflict is marked for review and no vote is
discarded), the review decision of the meeting chair, and the checklist of recorded facts for
the form of the meeting (no legal statement, see ``online_rules``)."""

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
from mhvp.hoa import meeting_rules, online_rules
from mhvp.hoa.models import (
    AgendaItem,
    Attendance,
    HoaOnlineMeetingSetting,
    Meeting,
    MeetingProxy,
    MeetingSpeakerRequest,
    MeetingVoteConflict,
    Resolution,
    Vote,
)
from mhvp.hoa.property_scope import HOA_GUARD
from mhvp.hoa.raw_responses import (
    HoaOnlineMeetingCloseVotingOut,
    HoaOnlineMeetingGetOnlineSettingOut,
    HoaOnlineMeetingOnlineOverviewOut,
    HoaOnlineMeetingOpenVotingOut,
    HoaOnlineMeetingResolveVoteConflictOut,
)

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
    # AE31: omitted keeps the stored rule (default flag)
    proxy_conflict_mode: str | None = Field(
        default=None, pattern="^(flag|first_vote|proxy_priority|own_priority)$"
    )


class HoaVoteConflictResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(keep_first|apply_second)$")
    note: str | None = Field(default=None, max_length=500)


class HoaSpeakerHandleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(done|withdrawn)$")


def now() -> datetime:
    return datetime.now(UTC)


async def online_enabled(session: AsyncSession) -> bool:
    """Tenant switch (RLS limits the query to the tenant of the session); no row means off."""
    return bool(await session.scalar(select(HoaOnlineMeetingSetting.enabled)))


async def proxy_conflict_mode(session: AsyncSession) -> str:
    """Tenant rule for owner against proxy holder (RLS limits the query); no row means flag."""
    value = await session.scalar(select(HoaOnlineMeetingSetting.proxy_conflict_mode))
    return str(value) if value else online_rules.DEFAULT_PROXY_CONFLICT_MODE


def setting_out(enabled: bool, mode: str) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "proxy_conflict_mode": mode,
        "proxy_conflict_modes": [
            {"code": code, "label": online_rules.MODE_LABELS[code]}
            for code in online_rules.PROXY_CONFLICT_MODES
        ],
        "note": ONLINE_NOTE,
        "conflict_note": online_rules.CONFLICT_NOTE,
    }


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


@router.get(
    "/online-meeting-settings",
    summary="Online-Versammlung im Portal (Schalter)",
    response_model=HoaOnlineMeetingGetOnlineSettingOut,
)
async def get_online_setting(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return setting_out(await online_enabled(session), await proxy_conflict_mode(session))


class HoaOnlineModeOut(BaseModel):
    """AK11 (GAI-304): typed response, ``extra="allow"`` keeps later fields."""

    model_config = ConfigDict(extra="allow")
    code: str
    label: str


class HoaOnlineSettingOut(BaseModel):
    """AK11 (GAI-304): typed response, ``extra="allow"`` keeps later fields."""

    model_config = ConfigDict(extra="allow")
    enabled: bool
    proxy_conflict_mode: str
    proxy_conflict_modes: list[HoaOnlineModeOut]
    note: str


@router.put(
    "/online-meeting-settings",
    summary="Online-Versammlung im Portal setzen",
    response_model=HoaOnlineSettingOut,
)
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
        if body.proxy_conflict_mode is not None:
            row.proxy_conflict_mode = body.proxy_conflict_mode
        row.updated_by = principal.user_id
        await session.flush()
        mode = row.proxy_conflict_mode or online_rules.DEFAULT_PROXY_CONFLICT_MODE
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_online_meeting_setting.updated",
            entity_type="hoa_online_meeting_setting",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled, "proxy_conflict_mode": mode},
        )
        return setting_out(body.enabled, mode)


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
    response_model=HoaOnlineMeetingOpenVotingOut,
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
    response_model=HoaOnlineMeetingCloseVotingOut,
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


# Vote conflicts (AE31, AD06-02/03) ---------------------------------------------------------

REJECT_TEXT = {
    "first_vote": (
        "Für diese Einheit liegt bereits eine Stimme vor. Nach der Regel des Mandanten zählt die "
        "zuerst abgegebene Stimme."
    ),
    "proxy_priority": (
        "Für diese Einheit liegt die Stimme des Bevollmächtigten vor. Nach der Regel des "
        "Mandanten hat sie Vorrang."
    ),
    "own_priority": (
        "Für diese Einheit liegt die eigene Stimme des Eigentümers vor. Nach der Regel des "
        "Mandanten hat sie Vorrang."
    ),
}
REVIEW_HINT = (
    "Für diese Einheit lag bereits eine Stimme vor. Ihre Stimme ist gespeichert, wird aber "
    "nicht gezählt. Die Versammlungsleitung prüft den Konflikt."
)


def conflict_out(c: MeetingVoteConflict) -> dict[str, Any]:
    return {
        "id": c.id,
        "meeting_id": c.meeting_id,
        "agenda_item_id": c.agenda_item_id,
        "contract_id": c.contract_id,
        "vote_id": c.vote_id,
        "mode": c.mode,
        "first_source": c.first_source,
        "first_choice": c.first_choice,
        "second_source": c.second_source,
        "second_choice": c.second_choice,
        "second_proxy_id": c.second_proxy_id,
        "second_channel": c.second_channel,
        "attempted_at": c.attempted_at,
        "status": c.status,
        "resolution": c.resolution,
        "decision_note": c.decision_note,
        "decided_at": c.decided_at,
    }


async def handle_second_vote(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    meeting: Meeting,
    item: AgendaItem,
    existing: Vote,
    source: str,
    choice: str,
    proxy_id: uuid.UUID | None,
    channel: str,
    actor_user_id: uuid.UUID | None,
) -> dict[str, Any]:
    """A unit that already has a vote receives a second vote. Same source twice or a vote
    that is excluded from voting: 409. Owner against proxy holder: by the tenant rule the
    second vote is refused (409), stored as a conflict for review (``flag``) or replaces the
    first vote (``proxy_priority``, ``own_priority``); a replaced vote stays in the conflict
    record, so no vote is lost. The caller has checked that the item is not announced."""
    if existing.excluded:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für diese Einheit wurde bereits abgestimmt."
        )
    first_source = online_rules.vote_source(existing.proxy_id, cast_source=existing.cast_source)
    # A source that already took part in a conflict of this unit and item cannot vote again.
    used = {first_source}
    for earlier in (
        await session.scalars(
            select(MeetingVoteConflict).where(
                MeetingVoteConflict.agenda_item_id == item.id,
                MeetingVoteConflict.contract_id == existing.contract_id,
            )
        )
    ).all():
        used.update((earlier.first_source, earlier.second_source))
    if source in used:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für diese Einheit wurde bereits abgestimmt."
        )
    mode = await proxy_conflict_mode(session)
    decision = online_rules.decide_conflict(mode, first_source, source)
    if decision == online_rules.DUPLICATE:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für diese Einheit wurde bereits abgestimmt."
        )
    if decision == online_rules.REJECT:
        raise ProblemError(ErrorCodes.CONFLICT, detail=REJECT_TEXT[mode])
    stamp = now()
    replaced = decision == online_rules.REPLACE
    conflict = MeetingVoteConflict(
        tenant_id=tenant_id,
        meeting_id=meeting.id,
        agenda_item_id=item.id,
        contract_id=existing.contract_id,
        vote_id=existing.id,
        mode=mode,
        first_source=first_source,
        first_choice=existing.choice,
        second_source=source,
        second_choice=choice,
        second_proxy_id=proxy_id,
        second_channel=channel,
        attempted_by=actor_user_id,
        attempted_at=stamp,
        status="resolved" if replaced else "open",
        resolution="rule_second" if replaced else None,
        decided_at=stamp if replaced else None,
    )
    if replaced:
        existing.choice = choice
        existing.proxy_id = proxy_id
        existing.cast_source = source
        existing.channel = channel
    session.add(conflict)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="meeting_vote.conflict_replaced" if replaced else "meeting_vote.conflict_flagged",
        entity_type="meeting_vote_conflict",
        entity_id=conflict.id,
        actor_user_id=actor_user_id,
        payload={
            "agenda_item_id": str(item.id),
            "contract_id": str(existing.contract_id),
            "mode": mode,
            "first_source": first_source,
            "second_source": source,
        },
    )
    return {
        "id": existing.id,
        "channel": channel,
        "proxy_id": proxy_id,
        "counted": replaced,
        "conflict": True,
        "conflict_id": conflict.id,
        "conflict_status": conflict.status,
        "hint": None if replaced else REVIEW_HINT,
    }


@router.post(
    "/meetings/{meeting_id}/vote-conflicts/{conflict_id}/resolve",
    summary="Stimmkonflikt Vollmacht gegen eigene Stimme entscheiden (Versammlungsleitung)",
    response_model=HoaOnlineMeetingResolveVoteConflictOut,
)
async def resolve_vote_conflict(
    meeting_id: uuid.UUID,
    conflict_id: uuid.UUID,
    body: HoaVoteConflictResolveIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """keep_first confirms the counted vote; apply_second counts the second vote instead (only
    before the announcement). The other vote stays in the record; nothing is deleted. The
    decision is a statement of the meeting chair and legally relevant: the operator clarifies
    the rule with legal advice (AD06-02)."""
    async with tenant_tx(request, principal) as session:
        meeting = await _meeting(session, meeting_id)
        if meeting.status in ("closing", "closed"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Protokoll im Abschluss: gesperrt.")
        conflict = await session.get(MeetingVoteConflict, conflict_id, with_for_update=True)
        if conflict is None or conflict.meeting_id != meeting.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if conflict.status != "open":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Konflikt bereits entschieden.")
        item = await _item(session, meeting, conflict.agenda_item_id)
        if body.decision == "apply_second":
            if await announced_items(session, [item.id]):
                raise ProblemError(ErrorCodes.CONFLICT, detail="Ergebnis bereits verkündet.")
            vote = await session.get(Vote, conflict.vote_id, with_for_update=True)
            if vote is None:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
            vote.choice = conflict.second_choice
            vote.proxy_id = conflict.second_proxy_id
            vote.cast_source = conflict.second_source
            vote.channel = conflict.second_channel
        conflict.status = "resolved"
        conflict.resolution = body.decision
        conflict.decision_note = body.note.strip() if body.note else None
        conflict.decided_at = now()
        conflict.decided_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting_vote.conflict_resolved",
            entity_type="meeting_vote_conflict",
            entity_id=conflict.id,
            actor_user_id=principal.user_id,
            payload={"decision": body.decision, "agenda_item_id": str(item.id)},
        )
        return conflict_out(conflict)


async def open_conflict_counts(
    session: AsyncSession, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Open vote conflicts per agenda item (review notes)."""
    if not item_ids:
        return {}
    counts: dict[uuid.UUID, int] = {}
    rows = await session.scalars(
        select(MeetingVoteConflict.agenda_item_id).where(
            MeetingVoteConflict.agenda_item_id.in_(item_ids), MeetingVoteConflict.status == "open"
        )
    )
    for item_id in rows.all():
        counts[item_id] = counts.get(item_id, 0) + 1
    return counts


async def admissibility(session: AsyncSession, meeting: Meeting) -> dict[str, Any]:
    """Checklist of the recorded facts for the form of the meeting (AD06-01, GA07-01). No
    legal statement: the module only lists what is recorded."""
    basis = (
        await session.get(Resolution, meeting.virtual_basis_resolution_id)
        if meeting.virtual_basis_resolution_id
        else None
    )
    return online_rules.admissibility_checks(
        mode=meeting.mode,
        meeting_day=meeting.scheduled_at.date(),
        online_switch=await online_enabled(session),
        virtual_switch=await meeting_rules.virtual_meetings_enabled(session, meeting.tenant_id),
        basis_number=basis.number if basis else None,
        basis_decided_on=basis.decided_on if basis else None,
        basis_status=basis.status if basis else None,
        valid_until=meeting.virtual_basis_valid_until,
        transition_date=await meeting_rules.virtual_basis_transition_date(
            session, meeting.tenant_id
        ),
        has_conference_link=bool(meeting.dial_in_url),
        conflict_mode=await proxy_conflict_mode(session),
    )


# Overview ----------------------------------------------------------------------------------


@router.get(
    "/meetings/{meeting_id}/online",
    summary="Online-Teilnahme: Zusagen, Vollmachten, Wortmeldungen, Online-Stimmen",
    dependencies=[Depends(strict_query)],
    response_model=HoaOnlineMeetingOnlineOverviewOut,
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
        open_conflicts = await open_conflict_counts(session, [i.id for i in items])
        conflicts = (
            await session.scalars(
                select(MeetingVoteConflict)
                .where(MeetingVoteConflict.meeting_id == meeting.id)
                .order_by(MeetingVoteConflict.attempted_at, MeetingVoteConflict.id)
            )
        ).all()
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
                    "open_conflicts": open_conflicts.get(i.id, 0),
                }
                for i in items
            ],
            "proxy_conflict_mode": await proxy_conflict_mode(session),
            "conflict_note": online_rules.CONFLICT_NOTE,
            "vote_conflicts": [conflict_out(c) for c in conflicts],
            "admissibility": await admissibility(session, meeting),
        }
