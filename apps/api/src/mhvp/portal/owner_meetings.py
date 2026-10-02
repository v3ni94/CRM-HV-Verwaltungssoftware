"""Owner portal: owners' meetings of the own community with dial-in data (M25-03, V13).

Read only. Requires the portal role ``owner`` (active grant with legal basis
``hoa_member_right``, 6.9.6, same scope rule as ``mhvp.portal.owner``); tenants, providers
and staff accounts are answered with 403. Dial-in data (link, access data) are shown only
for hybrid or virtual meetings of a community the account is an owner of, and only once the
invitation was recorded; the CRM never prints them into the invitation letter."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.release_gates import ReleaseGate, ensure_release_gate_open
from mhvp.hoa import meeting_rules, online_meeting
from mhvp.portal.owner import _owner_scope, _votes_summary
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


# AD06 / GA11-03: online meeting in the owner portal ------------------------------------------
# Behind the tenant switch hoa_online_meeting_setting (default off, 403 MHVP-HOA-0031). Proxy
# grant and vote are legally effective steps and additionally need release gate G4. The
# admissibility of a purely virtual meeting is not checked here (note only, AD06-01).


class PortalMeetingParticipationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)


class PortalSpeakerRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agenda_item_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class PortalMeetingProxyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grantor_contract_id: uuid.UUID
    proxy_kind: str = Field(pattern="^(owner|manager)$")
    proxy_contract_id: uuid.UUID | None = None
    meeting_id: uuid.UUID | None = None
    valid_from: date
    valid_to: date | None = None
    document_id: uuid.UUID


class PortalMeetingVoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: uuid.UUID
    choice: str = Field(pattern="^(yes|no|abstain)$")


async def _own_meeting(
    session: AsyncSession, account: Any, meeting_id: uuid.UUID
) -> tuple[Any, set[uuid.UUID]]:
    """Meeting of an own community (else 404) and the own ownership units entitled to vote on
    the meeting day."""
    from mhvp.hoa.meetings import _hoa_property, _members
    from mhvp.hoa.models import Meeting

    hoa_ids, own = await _owner_scope(session, account, local_today())
    meeting = await session.get(Meeting, meeting_id)
    if meeting is None or meeting.legal_entity_id not in hoa_ids or meeting.status == "planned":
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    prop = await _hoa_property(session, meeting.legal_entity_id)
    members = {c.id for c in await _members(session, prop, meeting.scheduled_at.date())}
    return meeting, own & members


async def _active_proxies_to(
    session: AsyncSession, meeting: Any, own_units: set[uuid.UUID]
) -> list[Any]:
    from mhvp.hoa.models import MeetingProxy

    if not own_units:
        return []
    rows = await session.scalars(
        select(MeetingProxy).where(
            MeetingProxy.legal_entity_id == meeting.legal_entity_id,
            MeetingProxy.proxy_kind == "owner",
            MeetingProxy.proxy_contract_id.in_(own_units),
            or_(MeetingProxy.meeting_id.is_(None), MeetingProxy.meeting_id == meeting.id),
        )
    )
    day = meeting.scheduled_at.date()
    return [p for p in rows.all() if online_meeting.proxy_active(p, day)]


async def _unit_labels(session: AsyncSession, meeting: Any) -> list[tuple[uuid.UUID, str]]:
    from mhvp.hoa.meetings import _hoa_property, _members
    from mhvp.properties.models import Unit

    prop = await _hoa_property(session, meeting.legal_entity_id)
    members = await _members(session, prop, meeting.scheduled_at.date())
    if not members:
        return []
    units = await session.scalars(select(Unit).where(Unit.id.in_([c.unit_id for c in members])))
    numbers = {u.id: u.number for u in units.all()}
    return [(c.id, numbers.get(c.unit_id, "")) for c in members]


@router.get(
    "/meetings/{meeting_id}",
    summary="Versammlung mit Tagesordnung und Online-Teilnahme (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def meeting_detail(
    meeting_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """Invitation view. Results only after the announcement; while voting, only whether the
    own units have voted (never a running tally)."""
    from mhvp.hoa.models import AgendaItem, Attendance, MeetingSpeakerRequest, Vote

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        meeting, own = await _own_meeting(session, account, meeting_id)
        enabled = await online_meeting.online_enabled(session)
        items = (
            await session.scalars(
                select(AgendaItem)
                .where(AgendaItem.meeting_id == meeting.id)
                .order_by(AgendaItem.position)
            )
        ).all()
        announced = await online_meeting.announced_items(session, [i.id for i in items])
        proxies = await _active_proxies_to(session, meeting, own)
        votable = own | {p.grantor_contract_id for p in proxies}
        voted: dict[uuid.UUID, list[uuid.UUID]] = {}
        if votable and items:
            for v in (
                await session.scalars(
                    select(Vote).where(
                        Vote.agenda_item_id.in_([i.id for i in items]),
                        Vote.contract_id.in_(votable),
                    )
                )
            ).all():
                voted.setdefault(v.agenda_item_id, []).append(v.contract_id)
        confirmed = (
            await session.scalars(
                select(Attendance.contract_id).where(
                    Attendance.meeting_id == meeting.id,
                    Attendance.contract_id.in_(own) if own else Attendance.id.is_(None),
                    Attendance.portal_confirmed_at.is_not(None),
                )
            )
        ).all()
        speakers = (
            await session.scalars(
                select(MeetingSpeakerRequest)
                .where(
                    MeetingSpeakerRequest.meeting_id == meeting.id,
                    MeetingSpeakerRequest.created_by == account.user_id,
                )
                .order_by(MeetingSpeakerRequest.requested_at)
            )
        ).all()
        candidates = await _unit_labels(session, meeting)
        show_link = (
            enabled
            and meeting.mode in ("hybrid", "virtual")
            and meeting.status
            in (
                "invited",
                "held",
            )
        )
        out_items = []
        for i in items:
            res = announced.get(i.id)
            out_items.append(
                {
                    "id": i.id,
                    "position": i.position,
                    "title": i.title,
                    "proposal": i.proposal,
                    "voting_state": online_meeting.voting_state(i, res is not None),
                    "voted_contract_ids": sorted(voted.get(i.id, []), key=str),
                    "result": (
                        {"status": res.status, "votes": _votes_summary(res.votes or {})}
                        if res is not None
                        else None
                    ),
                }
            )
        return {
            "id": meeting.id,
            "mode": meeting.mode,
            "mode_label": MODE_LABEL.get(meeting.mode, meeting.mode),
            "status": meeting.status,
            "scheduled_at": meeting.scheduled_at,
            "location": meeting.location,
            "public_description": meeting.public_description,
            "online_enabled": enabled,
            "online_note": online_meeting.ONLINE_NOTE,
            "conference_url": meeting.dial_in_url if show_link else None,
            "conference_access": meeting.dial_in_access if show_link else None,
            "own_contract_ids": sorted(own, key=str),
            "confirmed_contract_ids": sorted(confirmed, key=str),
            "represented_contract_ids": sorted({p.grantor_contract_id for p in proxies}, key=str),
            # Units only, no names of other owners (data minimisation).
            "units": [
                {"contract_id": cid, "unit_number": num, "own": cid in own}
                for cid, num in candidates
            ],
            "items": out_items,
            "speaker_requests": [online_meeting.speaker_out(r) for r in speakers],
        }


@router.post(
    "/meetings/{meeting_id}/participation",
    status_code=201,
    summary="Online-Teilnahme zusagen (Eigentümer)",
)
async def confirm_participation(
    meeting_id: uuid.UUID,
    body: PortalMeetingParticipationIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    """Records the online participation (channel online) of the own units; the attendance
    itself (present) is still confirmed by the manager during the meeting."""
    from mhvp.hoa.models import Attendance

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await online_meeting.ensure_online_enabled(session)
        meeting, own = await _own_meeting(session, account, meeting_id)
        online_meeting.ensure_online_meeting(meeting)
        wanted = set(body.contract_ids) if body.contract_ids else own
        if not wanted or not wanted <= own:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine eigene Einheit zum Termin.")
        stamp = online_meeting.now()
        for cid in sorted(wanted, key=str):
            row = await session.scalar(
                select(Attendance).where(
                    Attendance.meeting_id == meeting.id, Attendance.contract_id == cid
                )
            )
            if row is None:
                row = Attendance(
                    tenant_id=principal.tenant_id,
                    meeting_id=meeting.id,
                    contract_id=cid,
                    present=False,
                    online=True,
                )
                session.add(row)
            row.online = True
            row.portal_confirmed_at = row.portal_confirmed_at or stamp
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting.online_participation_confirmed",
            entity_type="owners_meeting",
            entity_id=meeting.id,
            actor_user_id=principal.user_id,
            payload={"contract_ids": sorted(str(c) for c in wanted)},
        )
        await session.flush()
        return {"confirmed_contract_ids": sorted(wanted, key=str), "confirmed_at": stamp}


@router.post(
    "/meetings/{meeting_id}/speaker-requests",
    status_code=201,
    summary="Wortmeldung (Eigentümer)",
)
async def request_to_speak(
    meeting_id: uuid.UUID,
    body: PortalSpeakerRequestIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    from mhvp.hoa.models import AgendaItem, MeetingSpeakerRequest

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await online_meeting.ensure_online_enabled(session)
        meeting, own = await _own_meeting(session, account, meeting_id)
        online_meeting.ensure_online_meeting(meeting)
        if not own:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Keine eigene Einheit zum Termin.")
        if body.agenda_item_id is not None:
            item = await session.get(AgendaItem, body.agenda_item_id)
            if item is None or item.meeting_id != meeting.id:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if await session.scalar(
            select(MeetingSpeakerRequest.id).where(
                MeetingSpeakerRequest.meeting_id == meeting.id,
                MeetingSpeakerRequest.created_by == account.user_id,
                MeetingSpeakerRequest.status == "open",
            )
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Wortmeldung bereits offen.")
        row = MeetingSpeakerRequest(
            tenant_id=principal.tenant_id,
            meeting_id=meeting.id,
            agenda_item_id=body.agenda_item_id,
            contract_id=sorted(own, key=str)[0],
            requested_at=online_meeting.now(),
            note=body.note,
            status="open",
            created_by=account.user_id,
        )
        session.add(row)
        await session.flush()
        return online_meeting.speaker_out(row)


@router.get(
    "/meeting-proxies",
    summary="Erteilte und erhaltene Vollmachten (Eigentümer)",
    dependencies=[Depends(strict_query)],
)
async def list_proxies(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    from mhvp.hoa.models import MeetingProxy

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, own = await _owner_scope(session, account, local_today())
        rows = (
            (
                await session.scalars(
                    select(MeetingProxy)
                    .where(
                        or_(
                            MeetingProxy.grantor_contract_id.in_(own),
                            MeetingProxy.proxy_contract_id.in_(own),
                        )
                    )
                    .order_by(MeetingProxy.created_at)
                )
            ).all()
            if own
            else []
        )
        today = local_today()
        return {
            "items": [
                online_meeting.proxy_out(p)
                | {
                    "direction": "granted" if p.grantor_contract_id in own else "received",
                    "active": online_meeting.proxy_active(p, today),
                }
                for p in rows
            ],
            "note": online_meeting.ONLINE_NOTE,
        }


@router.post(
    "/meeting-proxies",
    status_code=201,
    summary="Vollmacht erteilen (Eigentümer, G4)",
)
async def grant_proxy(
    body: PortalMeetingProxyIn, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """Proxy of an own unit to another owner of the same community or to the manager; the
    text form document is an own upload (POST /portal/uploads)."""
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.hoa.models import Meeting, MeetingProxy
    from mhvp.portal.routers import _own_uploads

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await online_meeting.ensure_online_enabled(session)
        await ensure_release_gate_open(
            ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
        )
        hoa_ids, own = await _owner_scope(session, account, local_today())
        if body.grantor_contract_id not in own:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        grantor = await session.get(Contract, body.grantor_contract_id)
        if grantor is None or grantor.legal_entity_id not in hoa_ids:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if body.valid_to is not None and body.valid_to < body.valid_from:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ende vor Beginn der Vollmacht.")
        if body.proxy_kind == "owner":
            target = (
                await session.get(Contract, body.proxy_contract_id)
                if body.proxy_contract_id
                else None
            )
            if (
                target is None
                or target.kind != ContractKind.OWNERSHIP
                or target.legal_entity_id != grantor.legal_entity_id
            ):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Bevollmächtigter muss Eigentümer derselben Gemeinschaft sein.",
                )
            if target.party_id == grantor.party_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Vollmacht an sich selbst nicht möglich."
                )
        elif body.proxy_contract_id is not None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Vollmacht an den Verwalter ohne Einheit."
            )
        if body.meeting_id is not None:
            meeting = await session.get(Meeting, body.meeting_id)
            if meeting is None or meeting.legal_entity_id != grantor.legal_entity_id:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _own_uploads(session, account, [body.document_id])
        row = MeetingProxy(
            tenant_id=principal.tenant_id,
            legal_entity_id=grantor.legal_entity_id,
            created_by=account.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting_proxy.granted",
            entity_type="meeting_proxy",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"grantor_contract_id": str(row.grantor_contract_id), "kind": row.proxy_kind},
        )
        return online_meeting.proxy_out(row) | {"direction": "granted", "active": True}


@router.post(
    "/meeting-proxies/{proxy_id}/revoke",
    summary="Vollmacht widerrufen (Eigentümer)",
)
async def revoke_proxy(
    proxy_id: uuid.UUID, request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """The revocation is always possible (also with gate G4 closed); the row stays as
    evidence with the time of revocation. Votes cast before stay unchanged."""
    from mhvp.hoa.models import MeetingProxy

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await online_meeting.ensure_online_enabled(session)
        _, own = await _owner_scope(session, account, local_today())
        row = await session.get(MeetingProxy, proxy_id, with_for_update=True)
        if row is None or row.grantor_contract_id not in own:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.revoked_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Vollmacht bereits widerrufen.")
        row.revoked_at = online_meeting.now()
        row.revoked_by = account.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting_proxy.revoked",
            entity_type="meeting_proxy",
            entity_id=row.id,
            actor_user_id=principal.user_id,
        )
        await session.flush()
        return online_meeting.proxy_out(row) | {"direction": "granted", "active": False}


@router.post(
    "/meetings/{meeting_id}/agenda/{item_id}/votes",
    status_code=201,
    summary="Online abstimmen (Eigentümer, G4)",
)
async def cast_online_vote(
    meeting_id: uuid.UUID,
    item_id: uuid.UUID,
    body: PortalMeetingVoteIn,
    request: Request,
    ctx: Portal = Depends(portal_user),
) -> dict[str, Any]:
    """One vote per unit and item, channel online, only while the manager has opened the
    voting of the item. Own units and units represented by an active proxy to an own unit;
    the voter must have confirmed the online participation. No result before the
    announcement."""
    from mhvp.hoa.models import AgendaItem, Attendance, Vote

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        await online_meeting.ensure_online_enabled(session)
        await ensure_release_gate_open(
            ReleaseGate.G4, principal.tenant_id, request.app.state.release_gate_resolver
        )
        meeting, own = await _own_meeting(session, account, meeting_id)
        if meeting.status in ("closing", "closed"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Protokoll im Abschluss: gesperrt.")
        if meeting.status == "disrupted":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Versammlung gestört.")
        online_meeting.ensure_online_meeting(meeting)
        # Row lock on the item serialises concurrent votes of the item (one vote per unit).
        item = await session.get(AgendaItem, item_id, with_for_update=True)
        if item is None or item.meeting_id != meeting.id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        proxy_id = None
        if body.contract_id not in own:
            proxy = next(
                (
                    p
                    for p in await _active_proxies_to(session, meeting, own)
                    if p.grantor_contract_id == body.contract_id
                ),
                None,
            )
            if proxy is None:
                raise ProblemError(
                    ErrorCodes.FORBIDDEN, detail="Keine eigene Einheit und keine Vollmacht."
                )
            proxy_id = proxy.id
        if not own or not await session.scalar(
            select(Attendance.id).where(
                Attendance.meeting_id == meeting.id,
                Attendance.contract_id.in_(own),
                Attendance.online.is_(True),
                Attendance.portal_confirmed_at.is_not(None),
            )
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Online-Teilnahme erst zusagen.")
        announced = await online_meeting.announced_items(session, [item.id])
        if online_meeting.voting_state(item, bool(announced)) != "open":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Abstimmung zum TOP nicht geöffnet.")
        if item.result in ("deferred", "no_vote"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="TOP vertagt oder ohne Abstimmung.")
        source = "proxy" if proxy_id else "own"
        existing = await session.scalar(
            select(Vote).where(Vote.agenda_item_id == item.id, Vote.contract_id == body.contract_id)
        )
        if existing is not None:
            # AE31: the same source twice stays 409; owner against proxy holder follows the
            # tenant rule (hoa_online_meeting_setting.proxy_conflict_mode, default flag).
            return await online_meeting.handle_second_vote(
                session,
                tenant_id=principal.tenant_id,
                meeting=meeting,
                item=item,
                existing=existing,
                source=source,
                choice=body.choice,
                proxy_id=proxy_id,
                channel="online",
                actor_user_id=principal.user_id,
            )
        row = Vote(
            tenant_id=principal.tenant_id,
            agenda_item_id=item.id,
            contract_id=body.contract_id,
            choice=body.choice,
            excluded=False,
            channel="online",
            proxy_id=proxy_id,
            cast_source=source,
        )
        # AF08 (GAE-14): the unique index (agenda item, unit) closes the race of a parallel
        # CRM and portal vote; the loser gets 409 and may retry into the AE31 conflict path.
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Stimme bereits erfasst.") from exc
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting_vote.cast_online",
            entity_type="meeting_vote",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "agenda_item_id": str(item.id),
                "contract_id": str(body.contract_id),
                "proxy_id": str(proxy_id) if proxy_id else None,
            },
        )
        return {
            "id": row.id,
            "channel": "online",
            "proxy_id": proxy_id,
            "counted": True,
            "conflict": False,
        }
