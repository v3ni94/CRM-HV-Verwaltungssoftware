"""Invitation period and virtual form of the owners' meeting (M25-03, V13).

The invitation period is a tenant setting in weeks (draft default 3, source status "to be
verified"): the system computes the latest dispatch date of the invitation as orientation,
warns when the invitation is recorded later and requires a documented reason, which is noted
in the minutes. The legal period, its computation (dispatch or receipt) and the urgency
exception are an estimate only and are marked for verification by a lawyer
(docs/rules/M25-03-einladung-virtuell.md, docs/OPEN_QUESTIONS.md M25-03, V13).

A virtual meeting needs the per tenant switch ``hoa_virtual_meetings_enabled`` (default off)
and a resolution of the owners that admits virtual meetings, with its validity end entered
from the resolution wording. Dial-in data are stored encrypted and shown to owners of the
community in the portal only; the attendance list records the channel per owner (presence,
online, proxy)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.clock import local_today
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import Attendance, Meeting, Resolution
from mhvp.hoa.property_scope import HOA_GUARD
from mhvp.hoa.raw_responses import (
    HoaMeetingRulesAttendanceListOut,
    HoaMeetingRulesGetMeetingSettingsOut,
    HoaMeetingRulesPutDialInOut,
    HoaMeetingRulesPutMeetingSettingsOut,
)

# M2-02/S16-02: WEG records outside the property assignment answer 404.
router = APIRouter(prefix="/hoa", tags=["hoa"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")

DEFAULT_INVITATION_WEEKS = 3  # draft value, source status "to be verified" (M25-03)
MIN_INVITATION_WEEKS = 1
MAX_INVITATION_WEEKS = 12
ENABLING_STATUSES = frozenset({"positive", "final", "legally_binding"})
MODES = ("presence", "hybrid", "virtual")
CHANNELS = {"presence": "Präsenz", "online": "online", "proxy": "Vollmacht", "absent": "abwesend"}

INVITATION_NOTICE = {
    "presence": None,
    "hybrid": (
        "Die Versammlung findet als hybride Versammlung statt. Sie können vor Ort oder online "
        "teilnehmen. Die Zugangsdaten für die Online-Teilnahme sind im Eigentümerportal "
        "hinterlegt und werden nicht in dieser Einladung abgedruckt. Die Stimmabgabe erfolgt "
        "für beide Teilnahmewege in der Versammlung; eine Vertretung ist mit Vollmacht in "
        "Textform möglich."
    ),
    "virtual": (
        "Die Versammlung findet als virtuelle Versammlung ohne Versammlungsort statt. Grundlage "
        "ist der Beschluss der Eigentümer, der virtuelle Versammlungen zulässt (Beschluss "
        "Nr. {number} vom {decided_on}, gültig bis {valid_until}). Die Zugangsdaten sind im "
        "Eigentümerportal hinterlegt und werden nicht in dieser Einladung abgedruckt. Bitte "
        "prüfen Sie den Zugang rechtzeitig vor Beginn; technische Störungen werden im "
        "Protokoll vermerkt."
    ),
}
SHORT_NOTICE_TEMPLATE = (
    "Vermerk zur Einladungsfrist: Die Einladung vom {invited_at} unterschreitet die im System "
    "hinterlegte Frist von {weeks} Wochen (spätester Versand orientierend {latest}, zu "
    "verifizieren). Dokumentierter Grund: {reason}"
)


# Pure rules ---------------------------------------------------------------------------------


def latest_invitation_date(scheduled_at: datetime | date, weeks: int) -> date:
    """Latest dispatch date of the invitation: meeting day minus the configured weeks.
    Orientation only; receipt, day of dispatch and the counting of the period are not
    decided here (M25-03, to be verified)."""
    day = scheduled_at.date() if isinstance(scheduled_at, datetime) else scheduled_at
    return day - timedelta(weeks=weeks)


def invitation_check(
    scheduled_at: datetime | date, invited_at: date, weeks: int
) -> tuple[date, bool]:
    """(latest dispatch date, short notice) for an invitation recorded on ``invited_at``."""
    latest = latest_invitation_date(scheduled_at, weeks)
    return latest, invited_at > latest


def attendance_channel(att: Attendance | None) -> str:
    """Channel of participation for the attendance list: proxy, online, presence or absent."""
    if att is None:
        return "absent"
    if att.proxy_contact_id:
        return "proxy"
    if att.present and att.online:
        return "online"
    if att.present:
        return "presence"
    return "absent"


def invitation_notice(meeting: Meeting, basis: Resolution | None) -> str | None:
    """Text block for the invitation depending on the meeting form; ``None`` for presence."""
    template = INVITATION_NOTICE.get(meeting.mode)
    if template is None:
        return None
    if meeting.mode == "virtual":
        return template.format(
            number=basis.number if basis else "nicht erfasst",
            decided_on=f"{basis.decided_on:%d.%m.%Y}" if basis else "nicht erfasst",
            valid_until=(
                f"{meeting.virtual_basis_valid_until:%d.%m.%Y}"
                if meeting.virtual_basis_valid_until
                else "nicht erfasst"
            ),
        )
    return template


def short_notice_note(meeting: Meeting, weeks: int) -> str | None:
    """Minutes note when the invitation was recorded after the latest dispatch date."""
    if not meeting.invitation_short_notice or meeting.invited_at is None:
        return None
    latest = latest_invitation_date(meeting.scheduled_at, weeks)
    return SHORT_NOTICE_TEMPLATE.format(
        invited_at=f"{meeting.invited_at:%d.%m.%Y}",
        weeks=weeks,
        latest=f"{latest:%d.%m.%Y}",
        reason=meeting.invitation_short_notice_reason or "nicht erfasst",
    )


BASIS_TERM_YEARS = 3  # 7.8 W13 Satz 4; transition rule § 48 Abs. 6 WEG open (AA06-02)
BASIS_TERM_NOTE = (
    "Hinweis: Das Gültigkeitsende {valid_until} liegt mehr als drei Jahre nach dem "
    "Beschlussdatum {decided_on} (spätestens {limit}). Höchstdauer und Übergangsregel sind "
    "rechtlich zu prüfen (offene Frage AA06-02)."
)


def basis_term_limit(decided_on: date) -> date:
    """Latest validity end of an enabling resolution: decision date plus three years
    (29.02. maps to 28.02.)."""
    try:
        return decided_on.replace(year=decided_on.year + BASIS_TERM_YEARS)
    except ValueError:
        return decided_on.replace(year=decided_on.year + BASIS_TERM_YEARS, day=28)


def basis_term_notice(decided_on: date, valid_until: date | None) -> str | None:
    """Notice when the validity end exceeds the three year term, otherwise ``None``."""
    if valid_until is None:
        return None
    limit = basis_term_limit(decided_on)
    if valid_until <= limit:
        return None
    return BASIS_TERM_NOTE.format(
        valid_until=f"{valid_until:%d.%m.%Y}",
        decided_on=f"{decided_on:%d.%m.%Y}",
        limit=f"{limit:%d.%m.%Y}",
    )


TRANSITION_NOTE = (
    "Hinweis: Der Betreiber hat den Stichtag {transition} für die Übergangsregel hinterlegt, "
    "der zulassende Beschluss vom {decided_on} liegt {relation}. Inhalt und Wirkung der "
    "Übergangsregel sind rechtlich zu prüfen (offene Frage AA06-02); die Angabe ist keine "
    "Rechtsauskunft und ändert keine Sperre."
)


def transition_notice(decided_on: date, transition_date: date | None) -> str | None:
    """Orientation note relating the decision date to the operator's transition date."""
    if transition_date is None:
        return None
    relation = "vor dem Stichtag" if decided_on < transition_date else "am oder nach dem Stichtag"
    return TRANSITION_NOTE.format(
        transition=f"{transition_date:%d.%m.%Y}",
        decided_on=f"{decided_on:%d.%m.%Y}",
        relation=relation,
    )


def basis_deadlines(
    decided_on: date,
    valid_until: date | None,
    transition_date: date | None,
    today: date | None = None,
) -> dict[str, Any]:
    """Orientation values for the meeting detail (to be verified, no legal computation)."""
    today = today or local_today()
    return {
        "decided_on": decided_on,
        "term_limit": basis_term_limit(decided_on),
        "valid_until": valid_until,
        "days_until_valid_until": (valid_until - today).days if valid_until else None,
        "transition_date": transition_date,
        "transition_notice": transition_notice(decided_on, transition_date),
        "to_verify": True,
    }


async def virtual_basis_transition_date(session: AsyncSession, tenant_id: uuid.UUID) -> date | None:
    from mhvp.platform.models import TenantSettings

    return await session.scalar(
        select(TenantSettings.hoa_virtual_basis_transition_date).where(
            TenantSettings.tenant_id == tenant_id
        )
    )


# Tenant settings ----------------------------------------------------------------------------


async def invitation_weeks(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(
        select(TenantSettings.hoa_invitation_weeks).where(TenantSettings.tenant_id == tenant_id)
    )
    return int(value) if value else DEFAULT_INVITATION_WEEKS


async def virtual_meetings_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    from mhvp.platform.models import TenantSettings

    return bool(
        await session.scalar(
            select(TenantSettings.hoa_virtual_meetings_enabled).where(
                TenantSettings.tenant_id == tenant_id
            )
        )
    )


async def virtual_basis_term_lock_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    from mhvp.platform.models import TenantSettings

    return bool(
        await session.scalar(
            select(TenantSettings.hoa_virtual_basis_term_lock_enabled).where(
                TenantSettings.tenant_id == tenant_id
            )
        )
    )


async def validate_virtual_basis(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    legal_entity_id: uuid.UUID,
    mode: str,
    scheduled_at: datetime,
    basis_id: uuid.UUID | None,
    valid_until: date | None,
) -> Resolution | None:
    """Locks of the virtual form: tenant switch, enabling resolution of the same community
    (positive, final or legally binding) and a validity end on or after the meeting day."""
    if mode != "virtual":
        if basis_id is not None or valid_until is not None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Beschlussgrundlage nur für virtuelle Versammlungen.",
            )
        return None
    if not await virtual_meetings_enabled(session, tenant_id):
        raise ProblemError(ErrorCodes.HOA_VIRTUAL_MEETINGS_DISABLED)
    basis = await session.get(Resolution, basis_id) if basis_id else None
    if (
        basis is None
        or basis.legal_entity_id != legal_entity_id
        or basis.status not in ENABLING_STATUSES
    ):
        raise ProblemError(ErrorCodes.HOA_VIRTUAL_BASIS_RESOLUTION)
    if valid_until is None:
        raise ProblemError(
            ErrorCodes.HOA_VIRTUAL_BASIS_RESOLUTION,
            detail="Gültigkeitsende des zulassenden Beschlusses fehlt.",
        )
    if valid_until < scheduled_at.date():
        raise ProblemError(
            ErrorCodes.HOA_VIRTUAL_BASIS_RESOLUTION,
            detail=f"Zulassender Beschluss gilt nur bis {valid_until:%d.%m.%Y}.",
        )
    # GA07-01: three year term; a lock only behind the tenant switch, otherwise a notice.
    notice = basis_term_notice(basis.decided_on, valid_until)
    if notice and await virtual_basis_term_lock_enabled(session, tenant_id):
        raise ProblemError(ErrorCodes.HOA_VIRTUAL_BASIS_TERM, detail=notice)
    return basis


# Calendar source (mhvp.workspace.services.derived_dates) ------------------------------------


async def invitation_deadlines(
    session: AsyncSession, start: date, end: date
) -> list[dict[str, Any]]:
    """Calendar entries "Einladung spätestens" for planned meetings whose latest dispatch
    date falls in [start, end]. Uses the tenant setting of the meeting's tenant."""
    from mhvp.properties.models import LegalEntity

    rows = (
        await session.execute(
            select(Meeting, LegalEntity.name, LegalEntity.property_id)
            .join(LegalEntity, LegalEntity.id == Meeting.legal_entity_id)
            .where(Meeting.status == "planned")
        )
    ).all()
    if not rows:
        return []
    weeks_by_tenant: dict[uuid.UUID, int] = {}
    items: list[dict[str, Any]] = []
    for meeting, name, property_id in rows:
        weeks = weeks_by_tenant.get(meeting.tenant_id)
        if weeks is None:
            weeks = await invitation_weeks(session, meeting.tenant_id)
            weeks_by_tenant[meeting.tenant_id] = weeks
        latest = latest_invitation_date(meeting.scheduled_at, weeks)
        if start <= latest <= end:
            items.append(
                {
                    "kind": "hoa_invitation_deadline",
                    "title": (
                        f"Einladung spätestens: Versammlung {meeting.scheduled_at:%d.%m.%Y} {name}"
                    ),
                    "date": latest,
                    "entity_type": "owners_meeting",
                    "entity_id": meeting.id,
                    "property_id": property_id,
                }
            )
    return items


# API ---------------------------------------------------------------------------------------


class MeetingSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_weeks: int = Field(ge=MIN_INVITATION_WEEKS, le=MAX_INVITATION_WEEKS)
    virtual_meetings_enabled: bool
    # GA07-01: omitted keeps the stored value
    virtual_basis_term_lock_enabled: bool | None = None
    # AE12: omitted keeps the stored value, ``null`` clears it
    virtual_basis_transition_date: date | None = None


class DialInIn(BaseModel):
    """Dial-in data of a hybrid or virtual meeting; ``null`` clears a field."""

    model_config = ConfigDict(extra="forbid")

    dial_in_url: str | None = Field(default=None, max_length=1000)
    dial_in_access: str | None = Field(default=None, max_length=2000)


SETTINGS_NOTE = (
    "Einladungsfrist als Entwurfswert, Quellenstatus zu prüfen durch Rechtsanwalt (M25-03). "
    "Virtuelle Versammlungen nur nach Freigabe des Betreibers (V13)."
)


@router.get(
    "/meeting-settings",
    summary="Einladungsfrist und virtuelle Versammlung (Mandant)",
    response_model=HoaMeetingRulesGetMeetingSettingsOut,
)
async def get_meeting_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return {
            "invitation_weeks": await invitation_weeks(session, principal.tenant_id),
            "virtual_meetings_enabled": await virtual_meetings_enabled(
                session, principal.tenant_id
            ),
            "virtual_basis_term_lock_enabled": await virtual_basis_term_lock_enabled(
                session, principal.tenant_id
            ),
            "virtual_basis_transition_date": await virtual_basis_transition_date(
                session, principal.tenant_id
            ),
            "note": SETTINGS_NOTE,
        }


@router.put(
    "/meeting-settings",
    summary="Einladungsfrist und virtuelle Versammlung setzen",
    response_model=HoaMeetingRulesPutMeetingSettingsOut,
)
async def put_meeting_settings(
    body: MeetingSettingsIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS_UPDATE)
) -> dict[str, Any]:
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.hoa_invitation_weeks = body.invitation_weeks
        row.hoa_virtual_meetings_enabled = body.virtual_meetings_enabled
        if body.virtual_basis_term_lock_enabled is not None:
            row.hoa_virtual_basis_term_lock_enabled = body.virtual_basis_term_lock_enabled
        if "virtual_basis_transition_date" in body.model_fields_set:
            row.hoa_virtual_basis_transition_date = body.virtual_basis_transition_date
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_meeting_settings.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload=body.model_dump(mode="json"),
        )
        return body.model_dump(mode="json") | {
            "virtual_basis_term_lock_enabled": row.hoa_virtual_basis_term_lock_enabled,
            "virtual_basis_transition_date": row.hoa_virtual_basis_transition_date,
            "note": SETTINGS_NOTE,
        }


@router.put(
    "/meetings/{meeting_id}/dial-in",
    summary="Einwahldaten (nur Eigentümer im Portal)",
    response_model=HoaMeetingRulesPutDialInOut,
)
async def put_dial_in(
    meeting_id: uuid.UUID,
    body: DialInIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        meeting = await session.get(Meeting, meeting_id)
        if meeting is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if meeting.mode == "presence":
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Einwahldaten nur für hybride oder virtuelle Form."
            )
        if meeting.status == "closed":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Versammlung ist abgeschlossen.")
        meeting.dial_in_url = body.dial_in_url.strip() if body.dial_in_url else None
        meeting.dial_in_access = body.dial_in_access.strip() if body.dial_in_access else None
        meeting.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa.meeting.dial_in_updated",
            entity_type="owners_meeting",
            entity_id=meeting.id,
            actor_user_id=principal.user_id,
            payload={
                "has_url": bool(meeting.dial_in_url),
                "has_access": bool(meeting.dial_in_access),
            },
        )
        await session.flush()
        return {
            "id": meeting.id,
            "dial_in_url": meeting.dial_in_url,
            "dial_in_access": meeting.dial_in_access,
        }


@router.get(
    "/meetings/{meeting_id}/attendance-list",
    summary="Teilnahmenachweis mit Kanal (Präsenz, online, Vollmacht)",
    response_model=HoaMeetingRulesAttendanceListOut,
)
async def attendance_list(
    meeting_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.contacts.models import Contact, Party
    from mhvp.hoa.meetings import _hoa_property, _members
    from mhvp.properties.models import Unit

    async with tenant_tx(request, principal) as session:
        meeting = await session.get(Meeting, meeting_id)
        if meeting is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        prop = await _hoa_property(session, meeting.legal_entity_id)
        members = await _members(session, prop, meeting.scheduled_at.date())
        attendance = {
            a.contract_id: a
            for a in (
                await session.scalars(select(Attendance).where(Attendance.meeting_id == meeting.id))
            ).all()
        }
        rows = []
        counts = dict.fromkeys(CHANNELS, 0)
        for c in members:
            unit = await session.get(Unit, c.unit_id)
            party = await session.get(Party, c.party_id)
            att = attendance.get(c.id)
            channel = attendance_channel(att)
            counts[channel] += 1
            proxy = (
                await session.get(Contact, att.proxy_contact_id)
                if att and att.proxy_contact_id
                else None
            )
            rows.append(
                {
                    "contract_id": c.id,
                    "unit_number": unit.number if unit else None,
                    "party_name": party.name if party else None,
                    "channel": channel,
                    "channel_label": CHANNELS[channel],
                    "proxy_name": proxy.display_name if proxy else None,
                    "proxy_document_id": att.proxy_document_id if att else None,
                }
            )
        return {
            "meeting_id": meeting.id,
            "mode": meeting.mode,
            "counts": counts,
            "rows": rows,
        }
