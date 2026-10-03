"""Owners' meeting, circular resolution and board audit (M25, R05, R03, PÜ06 to PÜ09).

The system counts and proposes; the chair announces the result. Only a simple majority of
yes over no votes (abstentions not counted) is computed; qualified and unanimous majorities
are flagged for a manual check with a documented basis (open question M25-01). Rules of the
individual community (Teilungserklärung, Vereinbarungen) are not known to the system."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, not_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import ensure_session_legal_entity_allowed
from mhvp.core.clock import local_today
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa import meeting_rules
from mhvp.hoa.majority import SUBJECT_PATTERN, check_resolution
from mhvp.hoa.models import (
    AgendaItem,
    Attendance,
    AuditEngagement,
    AuditItem,
    AuditItemEvent,
    AuditReport,
    HoaStatement,
    MajorityRule,
    Meeting,
    Resolution,
    Vote,
)
from mhvp.hoa.property_scope import HOA_GUARD

# M2-02/S16-02: WEG records outside the property assignment answer 404.
router = APIRouter(prefix="/hoa", tags=["hoa"], dependencies=[Depends(HOA_GUARD)])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
ZERO = Decimal("0")
# Invitation period: tenant setting in weeks (M25-03, meeting_rules.invitation_weeks); the
# module constant stays as the draft default of that setting.
INVITATION_WEEKS = meeting_rules.DEFAULT_INVITATION_WEEKS


class MeetingBaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeetingIn(MeetingBaseIn):
    legal_entity_id: uuid.UUID
    kind: str = Field(
        default="ordinary",
        pattern="^(ordinary|extraordinary|repeat|continuation|partial|circular_resolution)$",
    )
    mode: str = Field(default="presence", pattern="^(presence|hybrid|virtual)$")
    scheduled_at: datetime
    location: str | None = Field(default=None, max_length=300)
    voting_principle: str = Field(default="head", pattern="^(head|mea|unit)$")
    voting_principle_basis: str | None = Field(default=None, max_length=4000)
    virtual_basis_resolution_id: uuid.UUID | None = None
    virtual_basis_valid_until: date | None = None
    resolution_deadline_at: date | None = None
    resolution_deadline_source: str | None = Field(default=None, max_length=4000)
    # GA03-01
    ends_at: datetime | None = None
    origin_meeting_id: uuid.UUID | None = None
    invitation_template_id: uuid.UUID | None = None
    proxy_template_id: uuid.UUID | None = None
    ballot_template_id: uuid.UUID | None = None
    public_description: str | None = Field(default=None, max_length=20000)
    internal_description: str | None = Field(default=None, max_length=20000)


class MeetingPatch(MeetingBaseIn):
    """Resolution deadline of a virtual meeting (M9-07). ``null`` clears both fields.
    GA03-01: end, templates and descriptions; omitted fields stay unchanged."""

    resolution_deadline_at: date | None = None
    resolution_deadline_source: str | None = Field(default=None, max_length=4000)
    ends_at: datetime | None = None
    invitation_template_id: uuid.UUID | None = None
    proxy_template_id: uuid.UUID | None = None
    ballot_template_id: uuid.UUID | None = None
    public_description: str | None = Field(default=None, max_length=20000)
    internal_description: str | None = Field(default=None, max_length=20000)


MEETING_DETAIL_FIELDS = (
    "ends_at",
    "invitation_template_id",
    "proxy_template_id",
    "ballot_template_id",
    "public_description",
    "internal_description",
)
TEMPLATE_FIELDS = ("invitation_template_id", "proxy_template_id", "ballot_template_id")
ORIGIN_KINDS = frozenset({"repeat", "continuation"})


async def validate_meeting_details(
    session: AsyncSession,
    *,
    legal_entity_id: uuid.UUID,
    kind: str,
    scheduled_at: datetime,
    fields: dict[str, Any],
    meeting_id: uuid.UUID | None = None,
) -> None:
    """GA03-01: end after the start, templates of the tenant, origin meeting of the same
    community for a repeat or continuation meeting (and only there)."""
    from mhvp.documents.models import DocumentTemplate

    ends_at = fields.get("ends_at")
    if ends_at is not None and ends_at <= scheduled_at:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Ende muss nach dem Beginn liegen.")
    for name in TEMPLATE_FIELDS:
        ref = fields.get(name)
        if ref is not None and await session.get(DocumentTemplate, ref) is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Vorlage {name} nicht gefunden.")
    if "origin_meeting_id" not in fields:
        return
    origin_id = fields.get("origin_meeting_id")
    if kind in ORIGIN_KINDS:
        origin = await session.get(Meeting, origin_id) if origin_id else None
        if (
            origin is None
            or origin.legal_entity_id != legal_entity_id
            or origin.id == meeting_id
            or origin.scheduled_at >= scheduled_at
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Wiederholung oder Fortsetzung braucht eine frühere Ursprungsversammlung "
                "derselben GdWE.",
            )
    elif origin_id is not None:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Ursprungsversammlung nur bei Wiederholung oder Fortsetzung.",
        )


def validate_resolution_deadline(mode: str, deadline: date | None, source: str | None) -> None:
    """A resolution deadline is only kept for virtual meetings and always with its source
    (resolution or community rules with reference, M9-07). The date is entered, not
    computed; it is orientation only (M1-09)."""
    if deadline is None:
        if source and source.strip():
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Quelle ohne Beschlussfrist ist nicht zulässig."
            )
        return
    if mode != "virtual":
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Beschlussfrist nur für virtuelle Versammlungen.",
        )
    if source is None or len(source.strip()) < 3:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Beschlussfrist nur mit Quelle (Beschluss oder Gemeinschaftsordnung mit "
            "Fundstelle).",
        )


class AgendaIn(MeetingBaseIn):
    title: str = Field(min_length=3, max_length=300)
    proposal: str | None = Field(default=None, max_length=20000)
    majority: str = Field(
        default="simple", pattern="^(simple|qualified|unanimous|all_owners|rule)$"
    )
    subject_type: str | None = Field(
        default=None, pattern="^(economic_plan|hoa_statement|special_levy|other)$"
    )
    subject_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None
    # GA03-02: voting principle of this item (precedence over the meeting) and minutes text
    voting_principle: str | None = Field(default=None, pattern="^(head|mea|unit)$")
    voting_principle_basis: str | None = Field(default=None, max_length=4000)
    minutes_text: str | None = Field(default=None, max_length=50000)


class AgendaPatch(MeetingBaseIn):
    """GA03-02: result deferred or no_vote (accepted and rejected only by the announcement)
    and minutes text; ``result: null`` clears a recorded deferral."""

    result: str | None = Field(default=None, pattern="^(deferred|no_vote)$")
    minutes_text: str | None = Field(default=None, max_length=50000)


ITEM_RESULT = {"positive": "accepted", "negative": "rejected"}


def _validate_item_principle(principle: str | None, basis: str | None) -> None:
    if principle not in (None, "head") and not (basis and basis.strip()):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Abweichendes Stimmprinzip nur mit dokumentierter Grundlage.",
        )


class MajorityRuleIn(MeetingBaseIn):
    legal_entity_id: uuid.UUID
    label: str = Field(min_length=3, max_length=200)
    principle: str = Field(pattern="^(head|mea|unit)$")
    share_of_votes_cast: Decimal | None = Field(default=None, gt=0, lt=1)
    strictly_greater: bool = True
    min_mea_share_of_all: Decimal | None = Field(default=None, gt=0, le=1)
    unanimous: bool = False
    source: str = Field(min_length=3, max_length=4000)
    valid_from: date
    valid_to: date | None = None


class InviteIn(MeetingBaseIn):
    invited_at: date
    urgency_reason: str | None = Field(default=None, max_length=2000)


class AttendanceIn(MeetingBaseIn):
    contract_id: uuid.UUID
    present: bool = False
    online: bool = False
    proxy_contact_id: uuid.UUID | None = None
    proxy_document_id: uuid.UUID | None = None


class DisruptionIn(MeetingBaseIn):
    """Documented technical disruption of a hybrid or virtual meeting (D53)."""

    description: str = Field(min_length=1, max_length=4000)
    occurred_at: datetime
    resolved: bool = False
    affected_contract_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class VoteIn(MeetingBaseIn):
    contract_id: uuid.UUID
    choice: str = Field(pattern="^(yes|no|abstain)$")
    excluded: bool = False
    # GA03-04: only "circular" may be given (meeting kind circular_resolution); presence and
    # online are set from the attendance.
    channel: str | None = Field(default=None, pattern="^(presence|online|circular)$")


class AnnounceIn(MeetingBaseIn):
    outcome: str = Field(pattern="^(positive|negative)$")
    majority_basis: str = Field(min_length=3, max_length=4000)
    snapshot_hash: str | None = Field(default=None, max_length=64)
    subject_kind: str | None = Field(default=None, pattern=SUBJECT_PATTERN)


class MeetingConsentIn(MeetingBaseIn):
    """One text form vote (M25-02): choice, channel and time of receipt as evidence."""

    choice: str = Field(pattern="^(yes|no|abstain)$")
    channel: str = Field(default="email", pattern="^(email|portal|letter|other)$")
    received_at: datetime | None = None
    evidence_document_id: uuid.UUID | None = None


class CircularIn(MeetingBaseIn):
    legal_entity_id: uuid.UUID
    subject: str = Field(min_length=3, max_length=2000)
    wording: str = Field(min_length=3, max_length=20000)
    decided_on: date
    # ownership contract -> yes, no, abstain (plain) or a MeetingConsentIn with text form evidence
    consents: dict[uuid.UUID, str | MeetingConsentIn]
    evidence_document_id: uuid.UUID | None = None
    # M25-02: "simple" only with the tenant switch, a prior admitting resolution, a subject
    # kind (majority rule of the tenant) and a voting deadline.
    allowed_majority: str = Field(default="unanimous", pattern="^(unanimous|simple)$")
    enabling_resolution_id: uuid.UUID | None = None
    vote_deadline_at: datetime | None = None
    subject_kind: str | None = Field(default=None, pattern=SUBJECT_PATTERN)


class CircularSwitchIn(MeetingBaseIn):
    enabled: bool


class EngagementIn(MeetingBaseIn):
    legal_entity_id: uuid.UUID
    statement_id: uuid.UUID | None = None
    period_from: date
    period_to: date
    purpose: str = Field(min_length=3, max_length=4000)
    auditor_contact_ids: list[uuid.UUID] = Field(min_length=1)
    sampling: str = Field(default="sample", pattern="^(sample|full)$")
    accounts: list[str] = Field(default_factory=list)
    authorization_text: str | None = Field(default=None, max_length=4000)  # M25-08
    data_as_of: date | None = None  # M25-08


class AuditItemIn(MeetingBaseIn):
    journal_entry_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    amount: Decimal | None = None


class AuditItemPatch(MeetingBaseIn):
    status: str | None = Field(default=None, pattern="^(open|checked|query|objection)$")
    note: str | None = Field(default=None, max_length=4000)
    question: str | None = Field(default=None, max_length=4000)
    answer: str | None = Field(default=None, max_length=4000)
    risk_note: str | None = Field(default=None, max_length=4000)


class AuditReportConfirmIn(MeetingBaseIn):
    confirmed_by_name: str = Field(min_length=2, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class AuditReportIn(MeetingBaseIn):
    findings: str | None = Field(default=None, max_length=20000)
    recommendation: str | None = Field(default=None, max_length=4000)


async def _get(session: AsyncSession, model: Any, obj_id: uuid.UUID) -> Any:
    row = await session.get(model, obj_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def _hoa_property(session: AsyncSession, legal_entity_id: uuid.UUID) -> uuid.UUID:
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    entity = await _get(session, LegalEntity, legal_entity_id)
    if entity.kind is not LegalEntityKind.HOA or entity.property_id is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Nur für eine GdWE (W01).")
    return entity.property_id  # type: ignore[no-any-return]


async def _members(session: AsyncSession, property_id: uuid.UUID, day: date) -> list[Any]:
    """Ownership contracts of the community on a day (one per unit)."""
    from mhvp.contracts.models import Contract, ContractKind
    from mhvp.properties.models import Unit

    return list(
        (
            await session.scalars(
                select(Contract)
                .join(Unit, Unit.id == Contract.unit_id)
                .where(
                    Unit.property_id == property_id,
                    Contract.kind == ContractKind.OWNERSHIP,
                    Contract.start_date <= day,
                    or_(Contract.end_date.is_(None), Contract.end_date >= day),
                )
                .order_by(Unit.number)
            )
        ).all()
    )


async def _weight(
    session: AsyncSession, principle: str, contract: Any, property_id: uuid.UUID, day: date
) -> Decimal:
    if principle != "mea":
        return Decimal(1)
    from mhvp.properties.models import AllocationKey, UnitAllocationValue

    value = await session.scalar(
        select(UnitAllocationValue.value)
        .join(AllocationKey, AllocationKey.id == UnitAllocationValue.allocation_key_id)
        .where(
            AllocationKey.property_id == property_id,
            AllocationKey.code == "MEA",
            UnitAllocationValue.unit_id == contract.unit_id,
            UnitAllocationValue.valid_from <= day,
            or_(UnitAllocationValue.valid_to.is_(None), UnitAllocationValue.valid_to >= day),
        )
    )
    if value is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Miteigentumsanteil fehlt für Einheit.")
    return Decimal(value)


# Meetings --------------------------------------------------------------------------------


def _meeting_out(m: Meeting, *, weeks: int | None = None) -> dict[str, Any]:
    latest = (
        meeting_rules.latest_invitation_date(m.scheduled_at, weeks) if weeks is not None else None
    )
    return {
        "id": m.id,
        "legal_entity_id": m.legal_entity_id,
        "kind": m.kind,
        "mode": m.mode,
        "scheduled_at": m.scheduled_at,
        "location": m.location,
        "invited_at": m.invited_at,
        "voting_principle": m.voting_principle,
        "status": m.status,
        "minutes_document_id": m.minutes_document_id,
        "minutes_draft_document_id": m.minutes_draft_document_id,
        "resolution_deadline_at": m.resolution_deadline_at,
        "resolution_deadline_source": m.resolution_deadline_source,
        # M25-03 / V13
        "virtual_basis_resolution_id": m.virtual_basis_resolution_id,
        "virtual_basis_valid_until": m.virtual_basis_valid_until,
        "invitation_weeks": weeks,
        "latest_invitation_at": latest,
        "invitation_short_notice": m.invitation_short_notice,
        "invitation_short_notice_reason": m.invitation_short_notice_reason,
        "has_dial_in": bool(m.dial_in_url or m.dial_in_access),
        # R07-01
        # GA03-01
        "ends_at": m.ends_at,
        "origin_meeting_id": m.origin_meeting_id,
        "invitation_template_id": m.invitation_template_id,
        "proxy_template_id": m.proxy_template_id,
        "ballot_template_id": m.ballot_template_id,
        "public_description": m.public_description,
        "internal_description": m.internal_description,
        "close_requested_by": m.close_requested_by,
        "close_requested_at": m.close_requested_at,
        "closed_by": m.closed_by,
        "closed_at": m.closed_at,
    }


@router.post("/meetings", status_code=201, summary="Eigentümerversammlung anlegen")
async def create_meeting(
    body: MeetingIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _hoa_property(session, body.legal_entity_id)
        # Virtual form: tenant switch, enabling resolution with validity end (M25-03, V13).
        await meeting_rules.validate_virtual_basis(
            session,
            tenant_id=principal.tenant_id,
            legal_entity_id=body.legal_entity_id,
            mode=body.mode,
            scheduled_at=body.scheduled_at,
            basis_id=body.virtual_basis_resolution_id,
            valid_until=body.virtual_basis_valid_until,
        )
        if body.voting_principle != "head" and not body.voting_principle_basis:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Abweichendes Stimmprinzip nur mit dokumentierter Grundlage.",
            )
        validate_resolution_deadline(
            body.mode, body.resolution_deadline_at, body.resolution_deadline_source
        )
        await validate_meeting_details(
            session,
            legal_entity_id=body.legal_entity_id,
            kind=body.kind,
            scheduled_at=body.scheduled_at,
            fields=body.model_dump(),
        )
        basis = (
            await session.get(Resolution, body.virtual_basis_resolution_id)
            if body.virtual_basis_resolution_id
            else None
        )
        term_notice = (
            meeting_rules.basis_term_notice(basis.decided_on, body.virtual_basis_valid_until)
            if basis
            else None
        )
        row = Meeting(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        weeks = await meeting_rules.invitation_weeks(session, principal.tenant_id)
        return _meeting_out(row, weeks=weeks) | {"virtual_basis_term_notice": term_notice}


@router.patch("/meetings/{meeting_id}", summary="Beschlussfrist der Versammlung (M9-07)")
async def patch_meeting(
    meeting_id: uuid.UUID,
    body: MeetingPatch,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, Meeting, meeting_id)
        _ensure_not_closed(row)
        fields = body.model_dump(exclude_unset=True)
        deadline = fields.get("resolution_deadline_at", row.resolution_deadline_at)
        source = fields.get("resolution_deadline_source", row.resolution_deadline_source)
        if (
            "resolution_deadline_at" in fields
            and deadline is None
            and ("resolution_deadline_source" not in fields)
        ):
            source = None
        validate_resolution_deadline(row.mode, deadline, source)
        details = {k: v for k, v in fields.items() if k in MEETING_DETAIL_FIELDS}
        await validate_meeting_details(
            session,
            legal_entity_id=row.legal_entity_id,
            kind=row.kind,
            scheduled_at=row.scheduled_at,
            fields=details,
            meeting_id=row.id,
        )
        for key, value in details.items():
            setattr(row, key, value)
        row.resolution_deadline_at = deadline
        row.resolution_deadline_source = source.strip() if source else None
        await session.flush()
        return _meeting_out(row)


@router.post("/meetings/{meeting_id}/agenda", status_code=201, summary="Tagesordnungspunkt")
async def add_agenda(
    meeting_id: uuid.UUID,
    body: AgendaIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        if meeting.status != "planned":
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Tagesordnung nach Einladung nicht mehr änderbar."
            )
        count = len(
            (
                await session.scalars(
                    select(AgendaItem.id).where(AgendaItem.meeting_id == meeting.id)
                )
            ).all()
        )
        if body.rule_id is not None:
            rule = await session.get(MajorityRule, body.rule_id)
            if rule is None or rule.legal_entity_id != meeting.legal_entity_id:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Regel gehört nicht zur GdWE.")
        _validate_item_principle(body.voting_principle, body.voting_principle_basis)
        row = AgendaItem(
            tenant_id=principal.tenant_id,
            meeting_id=meeting.id,
            position=count + 1,
            **(body.model_dump() | {"majority": "rule" if body.rule_id else body.majority}),
        )
        session.add(row)
        await session.flush()
        return {
            "id": row.id,
            "position": row.position,
            "majority": row.majority,
            "voting_principle": row.voting_principle,
        }


@router.patch("/agenda/{item_id}", summary="Ergebnis vertagt/ohne Abstimmung, Protokolltext")
async def patch_agenda(
    item_id: uuid.UUID,
    body: AgendaPatch,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        item = await _get(session, AgendaItem, item_id)
        meeting = await _get(session, Meeting, item.meeting_id)
        _ensure_not_closed(meeting)
        fields = body.model_dump(exclude_unset=True)
        if "result" in fields:
            if item.result in ITEM_RESULT.values():
                raise ProblemError(ErrorCodes.CONFLICT, detail="Ergebnis bereits verkündet.")
            if fields["result"] is not None and await session.scalar(
                select(Vote.id).where(Vote.agenda_item_id == item.id).limit(1)
            ):
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Stimmen erfasst: Ergebnis nur durch Verkündung."
                )
            item.result = fields["result"]
        if "minutes_text" in fields:
            item.minutes_text = fields["minutes_text"]
        await session.flush()
        return {"id": item.id, "result": item.result, "minutes_text": item.minutes_text}


@router.post("/meetings/{meeting_id}/invite", summary="Einladung erfassen (Fristprüfung)")
async def invite(
    meeting_id: uuid.UUID,
    body: InviteIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        if meeting.status != "planned":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bereits eingeladen.")
        items = (
            await session.scalars(select(AgendaItem.id).where(AgendaItem.meeting_id == meeting.id))
        ).all()
        if not items:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Tagesordnung fehlt.")
        # Period per tenant setting (M25-03): warning and mandatory reason when the invitation
        # is recorded after the latest dispatch date; the reason is noted in the minutes.
        weeks = await meeting_rules.invitation_weeks(session, principal.tenant_id)
        latest, short = meeting_rules.invitation_check(meeting.scheduled_at, body.invited_at, weeks)
        if short and not (body.urgency_reason and body.urgency_reason.strip()):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"Einladungsfrist von {weeks} Wochen unterschritten (spätester Versand "
                    f"orientierend {latest:%d.%m.%Y}, zu verifizieren). Kürzere Frist nur mit "
                    "dokumentierter Dringlichkeit; der Grund wird im Protokoll vermerkt."
                ),
            )
        meeting.invited_at = body.invited_at
        meeting.status = "invited"
        meeting.invitation_short_notice = short
        meeting.invitation_short_notice_reason = (
            body.urgency_reason.strip() if short and body.urgency_reason else None
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting.invited",
            entity_type="owners_meeting",
            entity_id=meeting.id,
            actor_user_id=principal.user_id,
            payload={"short_notice": short, "urgency_reason": body.urgency_reason},
        )
        await session.flush()
        return _meeting_out(meeting, weeks=weeks) | {
            "short_notice": short,
            "latest_invitation_at": latest,
        }


@router.post("/meetings/{meeting_id}/attendance", status_code=201, summary="Anwesenheit/Vollmacht")
async def attendance(
    meeting_id: uuid.UUID,
    body: AttendanceIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        if meeting.status not in ("invited", "held"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Versammlung nicht eröffnet.")
        prop = await _hoa_property(session, meeting.legal_entity_id)
        members = {c.id for c in await _members(session, prop, meeting.scheduled_at.date())}
        if body.contract_id not in members:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Kein Eigentümer zum Termin.")
        if body.proxy_contact_id and not body.proxy_document_id:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Vollmacht nur mit Nachweis in Textform (R05)."
            )
        if body.online and meeting.mode == "presence":
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Online-Teilnahme hier nicht vorgesehen.",
            )
        row = await session.scalar(
            select(Attendance).where(
                Attendance.meeting_id == meeting.id, Attendance.contract_id == body.contract_id
            )
        )
        if row is None:
            row = Attendance(
                tenant_id=principal.tenant_id, meeting_id=meeting.id, **body.model_dump()
            )
            session.add(row)
        else:
            for key, value in body.model_dump().items():
                setattr(row, key, value)
        meeting.status = "held"
        await session.flush()
        return {"id": row.id, "represented": row.present or bool(row.proxy_contact_id)}


@router.post(
    "/meetings/{meeting_id}/disruptions", status_code=201, summary="Technische Störung (D53)"
)
async def disruption(
    meeting_id: uuid.UUID,
    body: DisruptionIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """A disruption is documented as an event, never silently dropped. While a disruption is
    open, votes and announcements are refused; a documented resumption reopens the meeting."""
    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        _ensure_not_closed(meeting)
        if meeting.mode == "presence":
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Störung nur bei hybrider oder virtueller Versammlung.",
            )
        if body.resolved:
            if meeting.status != "disrupted":
                raise ProblemError(ErrorCodes.CONFLICT, detail="Keine offene Störung.")
            meeting.status = "held"
        else:
            if meeting.status not in ("invited", "held"):
                raise ProblemError(ErrorCodes.CONFLICT, detail="Versammlung nicht eröffnet.")
            meeting.status = "disrupted"
        event = await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting.disruption_resolved" if body.resolved else "meeting.disruption",
            entity_type="owners_meeting",
            entity_id=meeting.id,
            actor_user_id=principal.user_id,
            payload={
                "description": body.description,
                "occurred_at": body.occurred_at.isoformat(),
                "affected_contract_ids": [str(c) for c in body.affected_contract_ids],
            },
        )
        await session.flush()
        return _meeting_out(meeting) | {"event_id": event.id}


async def _disruptions(session: AsyncSession, meeting_id: uuid.UUID) -> list[dict[str, Any]]:
    from mhvp.core.events import DomainEvent

    rows = await session.scalars(
        select(DomainEvent)
        .where(
            DomainEvent.entity_type == "owners_meeting",
            DomainEvent.entity_id == meeting_id,
            DomainEvent.type.in_(["meeting.disruption", "meeting.disruption_resolved"]),
        )
        .order_by(DomainEvent.occurred_at, DomainEvent.id)
    )
    return [
        {"id": e.id, "resolved": e.type == "meeting.disruption_resolved", **e.payload}
        for e in rows.all()
    ]


def _ensure_not_closed(meeting: Meeting) -> None:
    """R07-01: after the closing request (status closing) and the closing (status closed) the
    recorded meeting is locked; changes answer 409."""
    if meeting.status in CLOSING_STATUSES:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Protokoll im Abschluss oder abgeschlossen: keine Änderung mehr möglich.",
        )


def _ensure_not_disrupted(meeting: Meeting) -> None:
    _ensure_not_closed(meeting)
    if meeting.status == "disrupted":
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Versammlung gestört: erst Fortsetzung dokumentieren (D53).",
        )


@router.post("/agenda/{item_id}/votes", status_code=201, summary="Stimme erfassen")
async def cast_vote(
    item_id: uuid.UUID, body: VoteIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        item = await _get(session, AgendaItem, item_id)
        meeting = await _get(session, Meeting, item.meeting_id)
        _ensure_not_disrupted(meeting)
        att = await session.scalar(
            select(Attendance).where(
                Attendance.meeting_id == meeting.id, Attendance.contract_id == body.contract_id
            )
        )
        circular = meeting.kind == "circular_resolution"
        if body.channel == "circular" and not circular:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Kanal Umlauf nur bei Umlaufbeschlussverfahren."
            )
        if body.channel in ("presence", "online"):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Kanal wird aus der Anwesenheit gesetzt."
            )
        if not circular and (att is None or not (att.present or att.proxy_contact_id)):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Nicht anwesend oder vertreten.")
        if circular:
            prop = await _hoa_property(session, meeting.legal_entity_id)
            members = await _members(session, prop, meeting.scheduled_at.date())
            if body.contract_id not in {c.id for c in members}:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Kein stimmberechtigter Eigentümer."
                )
        if item.result in ("deferred", "no_vote"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="TOP vertagt oder ohne Abstimmung.")
        if await session.scalar(
            select(Resolution.id).where(
                Resolution.subject_type == "agenda_item", Resolution.subject_id == item.id
            )
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ergebnis bereits verkündet.")
        existing = await session.scalar(
            select(Vote).where(Vote.agenda_item_id == item.id, Vote.contract_id == body.contract_id)
        )
        if circular:
            channel = "circular"
        else:
            channel = "online" if att is not None and att.online else "presence"
        # AE31: source of the vote for the rule "proxy against own vote"
        source = "proxy" if att is not None and att.proxy_contact_id and not circular else "own"
        if existing is not None:
            if existing.excluded or body.excluded:
                raise ProblemError(ErrorCodes.CONFLICT, detail="Stimme bereits erfasst.")
            from mhvp.hoa import online_meeting

            # same source twice stays 409; owner against proxy holder follows the tenant rule
            await session.get(AgendaItem, item.id, with_for_update=True)
            return await online_meeting.handle_second_vote(
                session,
                tenant_id=principal.tenant_id,
                meeting=meeting,
                item=item,
                existing=existing,
                source=source,
                choice=body.choice,
                proxy_id=None,
                channel=channel,
                actor_user_id=principal.user_id,
            )
        row = Vote(
            tenant_id=principal.tenant_id,
            agenda_item_id=item.id,
            **(body.model_dump() | {"channel": channel, "cast_source": source}),
        )
        # AF08 (GAE-14): the unique index (agenda item, unit) closes the race of a parallel
        # CRM and portal vote; the loser gets 409 and may retry into the AE31 conflict path.
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError as exc:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Stimme bereits erfasst.") from exc
        return {"id": row.id, "channel": row.channel}


async def _tally(session: AsyncSession, item: AgendaItem, meeting: Meeting) -> dict[str, Any]:
    from mhvp.contracts.models import Contract

    prop = await _hoa_property(session, meeting.legal_entity_id)
    day = meeting.scheduled_at.date()
    rule = await session.get(MajorityRule, item.rule_id) if item.rule_id else None
    principle = rule.principle if rule else (item.voting_principle or meeting.voting_principle)
    votes = (await session.scalars(select(Vote).where(Vote.agenda_item_id == item.id))).all()
    sums = {"yes": ZERO, "no": ZERO, "abstain": ZERO}
    channels: dict[str, int] = {}
    for v in votes:
        channels[v.channel] = channels.get(v.channel, 0) + 1
    seen_heads: dict[uuid.UUID, str] = {}
    yes_contracts: set[uuid.UUID] = set()
    excluded = 0
    for v in votes:
        if v.excluded:
            excluded += 1
            continue
        contract = await _get(session, Contract, v.contract_id)
        if v.choice == "yes":
            yes_contracts.add(contract.id)
        if principle == "head":
            # one vote per owner person regardless of the number of units (§ 25 Abs. 2 WEG)
            if contract.party_id in seen_heads:
                if seen_heads[contract.party_id] != v.choice:
                    raise ProblemError(
                        ErrorCodes.CONFLICT, detail="Uneinheitliche Stimmabgabe eines Eigentümers."
                    )
                continue
            seen_heads[contract.party_id] = v.choice
        sums[v.choice] += await _weight(session, principle, contract, prop, day)
    proposal: str | None = None
    checks: dict[str, Any] = {}
    if rule is not None:
        cast = sums["yes"] + sums["no"]
        ok = True
        if rule.share_of_votes_cast is not None:
            share = sums["yes"] / cast if cast else ZERO
            passed = (
                share > rule.share_of_votes_cast
                if rule.strictly_greater
                else (share >= rule.share_of_votes_cast)
            )
            checks["share_of_votes_cast"] = {"value": f"{share:.4f}", "passed": passed}
            ok = ok and passed
        if rule.min_mea_share_of_all is not None:
            members = await _members(session, prop, day)
            total = sum([await _weight(session, "mea", c, prop, day) for c in members], ZERO)
            yes_mea = sum(
                [
                    await _weight(session, "mea", c, prop, day)
                    for c in members
                    if c.id in yes_contracts
                ],
                ZERO,
            )
            share = yes_mea / total if total else ZERO
            passed = share >= rule.min_mea_share_of_all
            checks["mea_share_of_all"] = {"value": f"{share:.4f}", "passed": passed}
            ok = ok and passed
        if rule.unanimous:
            members = await _members(session, prop, day)
            passed = bool(members) and all(c.id in yes_contracts for c in members)
            checks["unanimous"] = {"passed": passed}
            ok = ok and passed
        proposal = "positive" if ok else "negative"
    elif item.majority == "simple":
        proposal = "positive" if sums["yes"] > sums["no"] else "negative"
    elif item.majority == "all_owners":
        # GA03-02: consent of all owners entitled to vote, not only of those present
        members = await _members(session, prop, day)
        passed = bool(members) and all(c.id in yes_contracts for c in members)
        checks["all_owners"] = {
            "passed": passed,
            "members": len(members),
            "yes": len(yes_contracts),
        }
        proposal = "positive" if passed else "negative"
    return {
        "principle": principle,
        "yes": f"{sums['yes'].normalize():f}",
        "no": f"{sums['no'].normalize():f}",
        "abstain": f"{sums['abstain'].normalize():f}",
        "excluded": excluded,
        "majority": item.majority,
        "rule": {"id": str(rule.id), "label": rule.label, "source": rule.source} if rule else None,
        "checks": checks,
        "proposal": proposal,
        "manual_check": proposal is None,
        "channels": channels,
    }


@router.get("/agenda/{item_id}/tally", summary="Auszählung (Vorschlag, keine Verkündung)")
async def tally(
    item_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        item = await _get(session, AgendaItem, item_id)
        return await _tally(session, item, await _get(session, Meeting, item.meeting_id))


@router.post("/agenda/{item_id}/announce", status_code=201, summary="Ergebnis verkünden")
async def announce(
    item_id: uuid.UUID,
    body: AnnounceIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    from sqlalchemy import func

    async with tenant_tx(request, principal) as session:
        item = await _get(session, AgendaItem, item_id)
        meeting = await _get(session, Meeting, item.meeting_id)
        _ensure_not_disrupted(meeting)
        if item.result in ("deferred", "no_vote"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="TOP vertagt oder ohne Abstimmung.")
        result = await _tally(session, item, meeting)
        if result["proposal"] and result["proposal"] != body.outcome:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Verkündung weicht von der Auszählung ab."
            )
        if await session.scalar(
            select(Resolution.id).where(
                Resolution.subject_type == "agenda_item", Resolution.subject_id == item.id
            )
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ergebnis bereits verkündet.")
        number = int(
            await session.scalar(
                select(func.coalesce(func.max(Resolution.number), 0)).where(
                    Resolution.legal_entity_id == meeting.legal_entity_id
                )
            )
            or 0
        )
        row = Resolution(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            legal_entity_id=meeting.legal_entity_id,
            number=number + 1,
            decided_on=meeting.scheduled_at.date(),
            subject=item.title,
            wording=item.proposal or item.title,
            status=body.outcome,
            kind="meeting",
            snapshot_hash=body.snapshot_hash,
            subject_type="agenda_item",
            subject_id=item.id,
            majority_basis=body.majority_basis,
            votes=result,
            subject_kind=body.subject_kind,
            location=meeting.location,
        )
        session.add(row)
        item.result = ITEM_RESULT[body.outcome]
        await session.flush()
        check = await check_resolution(session, principal, row) if body.subject_kind else None
        return {
            "id": row.id,
            "number": row.number,
            "status": row.status,
            "votes": result,
            "majority_check": check,
        }


CIRCULAR_LEGAL_NOTE = (
    "Rechtsgrundlage der Absenkung zu prüfen (Einschätzung: § 23 Abs. 3 Satz 2 WEG, M25-02)"
)
ENABLING_STATUSES = {"positive", "final", "legally_binding"}


async def circular_lower_majority_enabled(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    from mhvp.platform.models import TenantSettings

    return bool(
        await session.scalar(
            select(TenantSettings.hoa_circular_lower_majority_enabled).where(
                TenantSettings.tenant_id == tenant_id
            )
        )
    )


def _consent(value: str | MeetingConsentIn) -> MeetingConsentIn:
    return value if isinstance(value, MeetingConsentIn) else MeetingConsentIn(choice=value)


def _late(consent: MeetingConsentIn, deadline: datetime | None) -> bool:
    return (
        deadline is not None and consent.received_at is not None and consent.received_at > deadline
    )


async def _enabling_resolution(session: AsyncSession, body: CircularIn) -> Resolution:
    """The prior resolution that admitted the lower majority: same community (RLS keeps other
    tenants invisible), positive and not younger than the circular resolution."""
    code = ErrorCodes.HOA_CIRCULAR_ENABLING_RESOLUTION
    if body.enabling_resolution_id is None:
        raise ProblemError(code, detail="Zulassender Beschluss (Absenkungsbeschluss) fehlt.")
    basis = await session.get(Resolution, body.enabling_resolution_id)
    if basis is None or basis.legal_entity_id != body.legal_entity_id:
        raise ProblemError(code, detail="Zulassender Beschluss nicht in dieser Gemeinschaft.")
    if basis.status not in ENABLING_STATUSES:
        raise ProblemError(code, detail="Zulassender Beschluss ist nicht positiv gefasst.")
    if basis.decided_on > body.decided_on:
        raise ProblemError(code, detail="Zulassender Beschluss liegt nach dem Umlaufbeschluss.")
    if basis.allowed_majority == "simple":
        raise ProblemError(
            code, detail="Absenkung nur durch einen Beschluss ohne abgesenkte Mehrheit."
        )
    return basis


async def _circular_tally(
    session: AsyncSession,
    prop: uuid.UUID,
    members: Sequence[Any],
    consents: dict[uuid.UUID, MeetingConsentIn],
    deadline: datetime | None,
    principle: str,
    day: date,
) -> dict[str, Any]:
    """Counts the text form votes received in time by head (one vote per owner person, § 25
    Abs. 2 WEG as in the meeting tally), by MEA or by unit; eligible is the total weight."""
    sums = {"yes": ZERO, "no": ZERO, "abstain": ZERO}
    eligible = ZERO
    seen_heads: dict[uuid.UUID, str | None] = {}
    late: list[str] = []
    for contract in members:
        weight = await _weight(session, principle, contract, prop, day)
        consent = consents.get(contract.id)
        choice: str | None = None
        if consent is not None:
            if _late(consent, deadline):
                late.append(str(contract.id))
            else:
                choice = consent.choice
        if principle == "head":
            if contract.party_id in seen_heads:
                previous = seen_heads[contract.party_id]
                if previous is None and choice is not None:
                    seen_heads[contract.party_id] = choice
                    sums[choice] += weight
                elif choice is not None and previous != choice:
                    raise ProblemError(
                        ErrorCodes.CONFLICT, detail="Uneinheitliche Stimmabgabe eines Eigentümers."
                    )
                continue
            seen_heads[contract.party_id] = choice
        eligible += weight
        if choice is not None:
            sums[choice] += weight
    return {
        "principle": principle,
        "yes": f"{sums['yes'].normalize():f}",
        "no": f"{sums['no'].normalize():f}",
        "abstain": f"{sums['abstain'].normalize():f}",
        "eligible": f"{eligible.normalize():f}",
        "late": late,
    }


@router.post("/circular-resolutions", status_code=201, summary="Umlaufbeschluss (Textform)")
async def circular(
    body: CircularIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Unanimous: positive only if every owner agreed in text form (§ 23 Abs. 3 WEG).
    Simple majority (M25-02, tenant switch, default off): only with a prior admitting
    resolution of the community for this subject, a voting deadline and the majority rule of
    the tenant for the subject kind (docs/rules/M25-02-umlaufbeschluss.md). The legal basis of
    the lowered majority is an assessment to be checked by a lawyer, not a rule of the system."""
    from sqlalchemy import func

    from mhvp.hoa.majority import BASIS_TO_PRINCIPLE, REACHED, evaluate, find_rule, spec_of

    async with tenant_tx(request, principal) as session:
        prop = await _hoa_property(session, body.legal_entity_id)
        members = await _members(session, prop, body.decided_on)
        member_ids = {c.id for c in members}
        consents = {k: _consent(v) for k, v in body.consents.items()}
        unknown = set(consents) - member_ids
        if unknown:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Zustimmung von Nichteigentümern.")
        if body.evidence_document_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Nachweis der Textform fehlt.")
        deadline = body.vote_deadline_at
        late = {k for k, c in consents.items() if _late(c, deadline)}
        missing = (member_ids - set(consents)) | late
        basis: Resolution | None = None
        check: dict[str, Any] | None = None
        tally: dict[str, Any] | None = None
        if body.allowed_majority == "simple":
            if not await circular_lower_majority_enabled(session, principal.tenant_id):
                raise ProblemError(ErrorCodes.HOA_CIRCULAR_LOWER_MAJORITY_DISABLED)
            basis = await _enabling_resolution(session, body)
            if deadline is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Fristende für die Stimmabgabe fehlt."
                )
            if body.subject_kind is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Beschlussgegenstand für die Mehrheitsregel fehlt.",
                )
            rule = await find_rule(session, body.legal_entity_id, body.subject_kind)
            spec = spec_of(rule)
            principle = BASIS_TO_PRINCIPLE[spec.counting_basis]
            tally = await _circular_tally(
                session, prop, members, consents, deadline, principle, body.decided_on
            )
            check = evaluate(spec, tally, body.subject_kind) | {
                "rule_id": str(rule.id) if rule else None,
                "checked_at": datetime.now(UTC).isoformat(),
            }
            if check["result"] not in {REACHED, "nicht erreicht"}:
                raise ProblemError(ErrorCodes.VALIDATION, detail=str(check.get("reason")))
            positive = check["result"] == REACHED
            majority_basis = (
                f"Einfache Mehrheit im Umlaufverfahren nach zulassendem Beschluss Nr. "
                f"{basis.number} vom {basis.decided_on.strftime('%d.%m.%Y')}; "
                f"{check['rule_text']}; {CIRCULAR_LEGAL_NOTE}"
            )
        else:
            positive = not missing and all(c.choice == "yes" for c in consents.values())
            majority_basis = "Allstimmigkeit in Textform (§ 23 Abs. 3 WEG)"
        number = int(
            await session.scalar(
                select(func.coalesce(func.max(Resolution.number), 0)).where(
                    Resolution.legal_entity_id == body.legal_entity_id
                )
            )
            or 0
        )
        now = datetime.now(UTC)
        row = Resolution(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            legal_entity_id=body.legal_entity_id,
            number=number + 1,
            decided_on=body.decided_on,
            subject=body.subject,
            wording=body.wording,
            status="positive" if positive else "negative",
            kind="circular",
            majority_basis=majority_basis,
            subject_kind=body.subject_kind,
            majority_check=check,
            allowed_majority=body.allowed_majority,
            enabling_resolution_id=basis.id if basis else None,
            vote_deadline_at=deadline,
            votes={
                "consents": {str(k): v.model_dump(mode="json") for k, v in consents.items()},
                "missing": sorted(str(m) for m in missing),
                "late": sorted(str(m) for m in late),
                "evidence_document_id": str(body.evidence_document_id),
                "allowed_majority": body.allowed_majority,
                "tally": tally,
                # Ergebnisfeststellung (protocol note in the resolution collection)
                "protocol": {
                    "determined_at": now.isoformat(),
                    "determined_by": str(principal.user_id),
                    "result": "positive" if positive else "negative",
                    "vote_deadline_at": deadline.isoformat() if deadline else None,
                    "enabling_resolution_id": str(basis.id) if basis else None,
                },
            },
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="resolution.circular_determined",
            entity_type="resolution",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={
                "status": row.status,
                "allowed_majority": body.allowed_majority,
                "enabling_resolution_id": str(basis.id) if basis else None,
            },
        )
        return {
            "id": row.id,
            "number": row.number,
            "status": row.status,
            "missing": len(missing),
            "late": len(late),
            "tally": tally,
            "majority_check": check,
            "majority_basis": majority_basis,
        }


SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")


@router.get("/circular-lower-majority", summary="Umlaufbeschluss mit einfacher Mehrheit (Schalter)")
async def get_circular_switch(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> dict[str, bool]:
    async with tenant_tx(request, principal) as session:
        return {"enabled": await circular_lower_majority_enabled(session, principal.tenant_id)}


class HoaCircularSwitchOut(BaseModel):
    """AK11 (GAI-304): typed response, ``extra="allow"`` keeps later fields."""

    model_config = ConfigDict(extra="allow")
    enabled: bool


@router.put(
    "/circular-lower-majority",
    summary="Umlaufbeschluss mit einfacher Mehrheit setzen",
    response_model=HoaCircularSwitchOut,
)
async def put_circular_switch(
    body: CircularSwitchIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS_UPDATE)
) -> dict[str, bool]:
    """Per tenant switch (M25-02), default off. Switching it on is an operator decision after
    legal review; the system does not assert the admissibility of the lowered majority."""
    from mhvp.platform.models import TenantSettings

    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TenantSettings).with_for_update())
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.hoa_circular_lower_majority_enabled = body.enabled
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa_circular_lower_majority.updated",
            entity_type="tenant_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": body.enabled},
        )
        return {"enabled": body.enabled}


# Board audit -----------------------------------------------------------------------------


@router.post("/audits", status_code=201, summary="Prüfauftrag (PÜ06)")
async def create_audit(
    body: EngagementIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.accounting.models import EntryStatus, JournalEntry, Ledger

    async with tenant_tx(request, principal) as session:
        # Legal entity scope of the membership (A37): a foreign community answers 404.
        ensure_session_legal_entity_allowed(session, body.legal_entity_id)
        await _hoa_property(session, body.legal_entity_id)
        if body.period_to < body.period_from:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig.")
        snapshot_hash = None
        if body.statement_id:
            st = await _get(session, HoaStatement, body.statement_id)
            # The board portal releases the cost items of this statement (PÜ07): only a
            # statement of the engagement's own community.
            st_ledger = await _get(session, Ledger, st.ledger_id)
            ensure_session_legal_entity_allowed(session, st_ledger.legal_entity_id)
            if st_ledger.legal_entity_id != body.legal_entity_id:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Die Abrechnung gehört nicht zur Gemeinschaft des Prüfauftrags.",
                )
            if st.snapshot_hash is None:
                raise ProblemError(ErrorCodes.CONFLICT, detail="Abrechnung nicht berechnet.")
            snapshot_hash = st.snapshot_hash
        entries = (
            await session.scalars(
                select(JournalEntry)
                .join(Ledger, Ledger.id == JournalEntry.ledger_id)
                .where(
                    Ledger.legal_entity_id == body.legal_entity_id,
                    JournalEntry.status == EntryStatus.POSTED,
                    JournalEntry.booking_date.between(body.period_from, body.period_to),
                )
            )
        ).all()
        population = {
            "entries": len(entries),
            "as_of": datetime.now(UTC).isoformat(),
            "accounts": body.accounts,
        }
        data = body.model_dump(exclude={"accounts", "auditor_contact_ids"})
        if data.get("data_as_of") is None:
            data["data_as_of"] = local_today()
        row = AuditEngagement(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            snapshot_hash=snapshot_hash,
            population=population,
            auditor_contact_ids=[str(a) for a in body.auditor_contact_ids],
            **data,
        )
        session.add(row)
        await session.flush()
        return {"id": row.id, "population": population, "snapshot_hash": snapshot_hash}


def _item_out(i: AuditItem) -> dict[str, Any]:
    return {
        "id": i.id,
        "journal_entry_id": i.journal_entry_id,
        "document_id": i.document_id,
        "amount": i.amount,
        "status": i.status,
        "note": i.note,
        "question": i.question,
        "answer": i.answer,
        "risk_note": i.risk_note,
        "version": i.version,
    }


@router.post("/audits/{audit_id}/items", status_code=201, summary="Prüfposition (PÜ07)")
async def add_audit_item(
    audit_id: uuid.UUID,
    body: AuditItemIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        eng = await _audit_engagement(session, audit_id)
        # Everything referenced here is released to the external board (portal.board): the
        # booking and the receipt must be records of the engagement's community, and the value
        # in the report is the booked figure, never a client supplied one.
        amount: Decimal | None
        if body.journal_entry_id is not None:
            amount = await _audit_entry_amount(session, eng, body.journal_entry_id)
            if body.document_id is not None:
                await _ensure_entry_document(session, body.journal_entry_id, body.document_id)
        elif body.document_id is not None:
            amount = await _audit_document_amount(session, eng, body.document_id, body.amount)
        else:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Buchung oder Beleg angeben.")
        if body.amount is not None and amount is not None and body.amount != amount:
            from mhvp.billing.letters import fmt_eur

            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Der Betrag weicht vom gebuchten Betrag {fmt_eur(amount)} ab.",
            )
        row = AuditItem(
            tenant_id=principal.tenant_id,
            engagement_id=eng.id,
            journal_entry_id=body.journal_entry_id,
            document_id=body.document_id,
            amount=amount,
        )
        session.add(row)
        await session.flush()
        return _item_out(row)


async def _audit_engagement(session: AsyncSession, audit_id: uuid.UUID) -> AuditEngagement:
    """Engagement with the legal entity scope of the membership (A37): a foreign community
    answers 404 like ``mhvp.hoa.board._engagement``."""
    eng: AuditEngagement = await _get(session, AuditEngagement, audit_id)
    ensure_session_legal_entity_allowed(session, eng.legal_entity_id)
    return eng


async def _entry_debit_total(session: AsyncSession, entry_id: uuid.UUID) -> Decimal:
    """Sum of the debit lines: the figure of the candidate list (``mhvp.hoa.board``) that the
    CRM picker submits and the report adds up as checked or unchecked value."""
    from sqlalchemy import func

    from mhvp.accounting.models import JournalLine

    total = await session.scalar(
        select(func.coalesce(func.sum(JournalLine.debit), 0)).where(
            JournalLine.journal_entry_id == entry_id
        )
    )
    return Decimal(total or 0)


async def _audit_entry_amount(
    session: AsyncSession, eng: AuditEngagement, entry_id: uuid.UUID
) -> Decimal:
    """A posted booking of the engagement's community inside the engagement period; a posting
    of the engagement's own statement (result per unit, booked on the resolution day) counts
    as inside. Returns the booked amount."""
    from mhvp.accounting.models import EntryStatus, JournalEntry, Ledger

    entry = await _get(session, JournalEntry, entry_id)
    ledger = await _get(session, Ledger, entry.ledger_id)
    ensure_session_legal_entity_allowed(session, ledger.legal_entity_id)
    if ledger.legal_entity_id != eng.legal_entity_id:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Die Buchung gehört nicht zur Gemeinschaft des Prüfauftrags.",
        )
    if entry.status is not EntryStatus.POSTED:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Nur gebuchte Buchungen sind prüfbar, keine Entwürfe."
        )
    if not eng.period_from <= entry.booking_date <= eng.period_to:
        statement = await session.get(HoaStatement, eng.statement_id) if eng.statement_id else None
        if statement is None or str(entry.id) not in (statement.posted_entry_ids or []):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Das Buchungsdatum liegt außerhalb des Prüfzeitraums.",
            )
    return await _entry_debit_total(session, entry.id)


async def _ensure_entry_document(
    session: AsyncSession, entry_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    """With a booking only its own receipt or the receipt of the invoice it booked."""
    from mhvp.accounting.models import Invoice, JournalEntry
    from mhvp.documents.models import Document

    await _get(session, Document, document_id)
    linked = await session.scalar(
        select(JournalEntry.id).where(
            JournalEntry.id == entry_id, JournalEntry.document_id == document_id
        )
    ) or await session.scalar(
        select(Invoice.id)
        .where(Invoice.journal_entry_id == entry_id, Invoice.document_id == document_id)
        .limit(1)
    )
    if linked is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Der Beleg gehört nicht zu dieser Buchung."
        )


async def _audit_document_amount(
    session: AsyncSession,
    eng: AuditEngagement,
    document_id: uuid.UUID,
    requested: Decimal | None,
) -> Decimal | None:
    """A receipt without booking: the receipt of an invoice or of a posted booking in a ledger
    of the engagement's community, nothing else of the tenant. Returns the booked figure
    (invoice gross, booking debit total); with several different figures the requested one
    must be among them."""
    from mhvp.accounting.models import EntryStatus, Invoice, JournalEntry, Ledger
    from mhvp.documents.models import Document

    await _get(session, Document, document_id)
    ledgers = select(Ledger.id).where(Ledger.legal_entity_id == eng.legal_entity_id)
    figures: set[Decimal] = set(
        (
            await session.scalars(
                select(Invoice.gross).where(
                    Invoice.document_id == document_id, Invoice.ledger_id.in_(ledgers)
                )
            )
        ).all()
    )
    for entry_id in (
        await session.scalars(
            select(JournalEntry.id).where(
                JournalEntry.document_id == document_id,
                JournalEntry.ledger_id.in_(ledgers),
                JournalEntry.status == EntryStatus.POSTED,
            )
        )
    ).all():
        figures.add(await _entry_debit_total(session, entry_id))
    if not figures:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Der Beleg gehört zu keiner Rechnung oder Buchung der Gemeinschaft des "
            "Prüfauftrags.",
        )
    if len(figures) == 1:
        return next(iter(figures))
    if requested is not None and requested in figures:
        return requested
    raise ProblemError(
        ErrorCodes.VALIDATION,
        detail="Der Beleg ist mehrfach mit unterschiedlichen Beträgen gebucht; bitte die "
        "Buchung auswählen.",
    )


@router.patch("/audit-items/{item_id}", summary="Vermerk, Rückfrage, Antwort (PÜ08)")
async def patch_audit_item(
    item_id: uuid.UUID,
    body: AuditItemPatch,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, AuditItem, item_id)
        await _audit_engagement(session, row.engagement_id)  # A37 scope of the community
        if row.status == "outdated":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Position zu alter Version.")
        changes: dict[str, Any] = {}
        for key, value in body.model_dump(exclude_none=True).items():
            old = getattr(row, key)
            if old != value:
                changes[key] = {"old": old, "new": value}
            setattr(row, key, value)
        if changes:
            row.version += 1
            session.add(
                AuditItemEvent(
                    tenant_id=principal.tenant_id,
                    item_id=row.id,
                    item_version=row.version,
                    changes=changes,
                    actor_user_id=principal.user_id,
                    occurred_at=datetime.now(UTC),
                )
            )
        await session.flush()
        return _item_out(row)


@router.get(
    "/audit-items/{item_id}/history",
    summary="Änderungshistorie der Prüfposition (PÜ08)",
    dependencies=[Depends(strict_query)],
)
async def audit_item_history(
    item_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, AuditItem, item_id)
        await _audit_engagement(session, row.engagement_id)
        events = (
            await session.scalars(
                select(AuditItemEvent)
                .where(AuditItemEvent.item_id == row.id)
                .order_by(AuditItemEvent.occurred_at, AuditItemEvent.item_version)
            )
        ).all()
        return [
            {
                "item_version": e.item_version,
                "changes": e.changes,
                "actor_user_id": e.actor_user_id,
                "occurred_at": e.occurred_at,
            }
            for e in events
        ]


@router.post(
    "/audits/{audit_id}/reports/{version}/confirm", summary="Prüfbericht bestätigen (PÜ09)"
)
async def confirm_report(
    audit_id: uuid.UUID,
    version: int,
    body: AuditReportConfirmIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    """Optional confirmation of one report version (M25-03). Never a resolution (PÜ09)."""
    async with tenant_tx(request, principal) as session:
        eng = await _audit_engagement(session, audit_id)
        row = await session.scalar(
            select(AuditReport).where(
                AuditReport.engagement_id == eng.id, AuditReport.version == version
            )
        )
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.confirmed_at is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Bericht bereits bestätigt.")
        row.confirmed_by_name = body.confirmed_by_name
        row.confirmed_by_user_id = principal.user_id
        row.confirmed_at = datetime.now(UTC)
        row.confirmation_note = body.note
        await session.flush()
        return {
            "version": row.version,
            "confirmed_by_name": row.confirmed_by_name,
            "confirmed_at": row.confirmed_at,
            "note": row.confirmation_note,
        }


@router.post("/audits/{audit_id}/reports", status_code=201, summary="Prüfbericht (PÜ09)")
async def create_report(
    audit_id: uuid.UUID,
    body: AuditReportIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from sqlalchemy import func

    async with tenant_tx(request, principal) as session:
        eng = await _audit_engagement(session, audit_id)
        outdated_reasons = await refresh_audit_items(session, eng)
        items = (
            await session.scalars(select(AuditItem).where(AuditItem.engagement_id == eng.id))
        ).all()
        checked = [i for i in items if i.status == "checked"]
        version = int(
            await session.scalar(
                select(func.coalesce(func.max(AuditReport.version), 0)).where(
                    AuditReport.engagement_id == eng.id
                )
            )
            or 0
        )
        content = {
            "sampling": eng.sampling,
            "population_entries": eng.population.get("entries"),
            "snapshot_hash": eng.snapshot_hash,
            "data_as_of": eng.data_as_of.isoformat() if eng.data_as_of else None,
            "authorization_text": eng.authorization_text,
            "selected": len(items),
            "checked_count": len(checked),
            "checked_value": _money(sum((i.amount or ZERO for i in checked), ZERO)),
            "unchecked_count": len(items) - len(checked),
            "unchecked_value": _money(
                sum((i.amount or ZERO for i in items if i.status != "checked"), ZERO)
            ),
            "open": [str(i.id) for i in items if i.status in ("open", "query")],
            "objections": [str(i.id) for i in items if i.status == "objection"],
            "outdated": [str(i.id) for i in items if i.status == "outdated"],
            "outdated_reasons": outdated_reasons,
            "overall_status": _overall_status(items),
            "scope_note": (
                "Vollprüfung der Population"
                if eng.sampling == "full"
                else "Stichprobe: geprüft sind nur die ausgewählten Positionen,"
                " nicht die gesamte Abrechnung (PÜ09)."
            ),
            "findings": body.findings,
            "recommendation": body.recommendation,
            "date": local_today().isoformat(),
        }
        row = AuditReport(
            tenant_id=principal.tenant_id,
            engagement_id=eng.id,
            version=version + 1,
            content=content,
            created_by=principal.user_id,
        )
        session.add(row)
        await session.flush()
        return {"id": row.id, "version": row.version, "content": content}


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _overall_status(items: Sequence[AuditItem]) -> str:
    """Never an unchanged green status once a checked item is outdated or objected (D33)."""
    if not items:
        return "keine Positionen ausgewählt"
    if any(i.status == "outdated" for i in items):
        return "eingeschränkt: Positionen nach Prüfung geändert"
    if any(i.status in ("objection", "open", "query") for i in items):
        return "eingeschränkt: offene Positionen oder Beanstandungen"
    return "Stichprobe geprüft"


async def refresh_audit_items(session: AsyncSession, eng: AuditEngagement) -> dict[str, str]:
    """Marks items outdated whose invoice or booking changed after the item was last worked on
    (D33): an invoice referencing the item's document with a later modification (new version
    via PUT), or a posted reversal of the item's journal entry. Returns reasons per item id."""
    from mhvp.accounting.models import EntryStatus, Invoice, JournalEntry

    reasons: dict[str, str] = {}
    items = (
        await session.scalars(
            select(AuditItem).where(
                AuditItem.engagement_id == eng.id, AuditItem.status != "outdated"
            )
        )
    ).all()
    for item in items:
        reason = None
        if item.document_id is not None:
            changed = await session.scalar(
                select(Invoice.id).where(
                    Invoice.document_id == item.document_id, Invoice.updated_at > item.updated_at
                )
            )
            if changed is not None:
                reason = "Rechnung nach Prüfung geändert"
        if reason is None and item.journal_entry_id is not None:
            reversed_ = await session.scalar(
                select(JournalEntry.id).where(
                    JournalEntry.reverses_id == item.journal_entry_id,
                    JournalEntry.status == EntryStatus.POSTED,
                )
            )
            if reversed_ is not None:
                reason = "Buchung nach Prüfung storniert"
        if reason is not None:
            item.status = "outdated"
            item.version += 1
            reasons[str(item.id)] = reason
    if reasons:
        await session.flush()
    return reasons


@router.get("/audits/{audit_id}", summary="Beiratsprüfung mit Positionen (PÜ07, D33)")
async def get_audit(
    audit_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    min_amount: Decimal | None = Query(default=None),
    max_amount: Decimal | None = Query(default=None),
    missing_document: bool | None = Query(default=None),
    has_risk: bool | None = Query(default=None),
    item_status: str | None = Query(
        default=None, pattern="^(open|checked|query|objection|outdated)$"
    ),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        eng = await _audit_engagement(session, audit_id)
        outdated_reasons = await refresh_audit_items(session, eng)
        stmt = select(AuditItem).where(AuditItem.engagement_id == eng.id)
        if min_amount is not None:
            stmt = stmt.where(AuditItem.amount >= min_amount)
        if max_amount is not None:
            stmt = stmt.where(AuditItem.amount <= max_amount)
        if missing_document is not None:
            stmt = stmt.where(
                AuditItem.document_id.is_(None)
                if missing_document
                else AuditItem.document_id.is_not(None)
            )
        if has_risk is not None:
            risk = and_(AuditItem.risk_note.is_not(None), AuditItem.risk_note != "")
            stmt = stmt.where(risk if has_risk else not_(risk))
        if item_status is not None:
            stmt = stmt.where(AuditItem.status == item_status)
        items = (await session.scalars(stmt.order_by(AuditItem.created_at, AuditItem.id))).all()
        all_items = (
            await session.scalars(select(AuditItem).where(AuditItem.engagement_id == eng.id))
        ).all()  # the overall status never depends on the filter
        return {
            "id": eng.id,
            "authorization_text": eng.authorization_text,
            "data_as_of": eng.data_as_of,
            "legal_entity_id": eng.legal_entity_id,
            "statement_id": eng.statement_id,
            "period_from": eng.period_from,
            "period_to": eng.period_to,
            "purpose": eng.purpose,
            "sampling": eng.sampling,
            "population": eng.population,
            "status": eng.status,
            "overall_status": _overall_status(all_items),
            "outdated_reasons": outdated_reasons,
            "items": [_item_out(i) for i in items],
        }


async def outdate_audit_items(session: AsyncSession, statement_id: uuid.UUID) -> None:
    """A new statement version marks audit items of the old version outdated (6.9.12)."""
    engagements = select(AuditEngagement.id).where(AuditEngagement.statement_id == statement_id)
    await session.execute(
        update(AuditItem)
        .where(AuditItem.engagement_id.in_(engagements), AuditItem.status != "outdated")
        .values(status="outdated")
    )


@router.get("/meetings", summary="Versammlungen einer GdWE", dependencies=[Depends(strict_query)])
async def list_meetings(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(Meeting)
            .where(Meeting.legal_entity_id == legal_entity_id)
            .order_by(Meeting.scheduled_at.desc())
        )
        weeks = await meeting_rules.invitation_weeks(session, principal.tenant_id)
        return [_meeting_out(m, weeks=weeks) for m in rows.all()]


@router.get("/meetings/{meeting_id}", summary="Versammlung mit Tagesordnung und Anwesenheit")
async def get_meeting(
    meeting_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        items = (
            await session.scalars(
                select(AgendaItem)
                .where(AgendaItem.meeting_id == meeting.id)
                .order_by(AgendaItem.position)
            )
        ).all()
        attendance = (
            await session.scalars(select(Attendance).where(Attendance.meeting_id == meeting.id))
        ).all()
        announced = {
            r.subject_id: {"id": r.id, "number": r.number, "status": r.status}
            for r in (
                await session.scalars(
                    select(Resolution).where(
                        Resolution.subject_type == "agenda_item",
                        Resolution.subject_id.in_([i.id for i in items] or [uuid.uuid4()]),
                    )
                )
            ).all()
        }
        weeks = await meeting_rules.invitation_weeks(session, principal.tenant_id)
        basis = (
            await session.get(Resolution, meeting.virtual_basis_resolution_id)
            if meeting.virtual_basis_resolution_id
            else None
        )
        return _meeting_out(meeting, weeks=weeks) | {
            "invitation_notice": meeting_rules.invitation_notice(meeting, basis),
            "short_notice_note": meeting_rules.short_notice_note(meeting, weeks),
            "virtual_basis": (
                {"id": basis.id, "number": basis.number, "decided_on": basis.decided_on}
                if basis
                else None
            ),
            # GA07-01: permanent notice, the lock itself stays behind the tenant switch
            "virtual_basis_term_notice": (
                meeting_rules.basis_term_notice(basis.decided_on, meeting.virtual_basis_valid_until)
                if basis
                else None
            ),
            # AE12: orientation values for the deadline notice (to be verified)
            "virtual_basis_deadlines": (
                meeting_rules.basis_deadlines(
                    basis.decided_on,
                    meeting.virtual_basis_valid_until,
                    await meeting_rules.virtual_basis_transition_date(session, principal.tenant_id),
                )
                if basis
                else None
            ),
            "agenda": [
                {
                    "id": i.id,
                    "position": i.position,
                    "title": i.title,
                    "proposal": i.proposal,
                    "majority": i.majority,
                    "resolution": announced.get(i.id),
                    "result": i.result,
                    "minutes_text": i.minutes_text,
                    "voting_principle": i.voting_principle,
                }
                for i in items
            ],
            "represented": sum(1 for a in attendance if a.present or a.proxy_contact_id),
            "proxies": sum(1 for a in attendance if a.proxy_contact_id),
            "disruptions": await _disruptions(session, meeting.id),
        }


@router.get(
    "/meetings/{meeting_id}/members",
    summary="Stimmberechtigte mit Anwesenheit und Stimmen",
    dependencies=[Depends(strict_query)],
)
async def meeting_members(
    meeting_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    """Ownership contracts on the meeting day with attendance and votes per agenda item."""
    from mhvp.contacts.models import Party
    from mhvp.properties.models import Unit

    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        prop = await _hoa_property(session, meeting.legal_entity_id)
        members = await _members(session, prop, meeting.scheduled_at.date())
        attendance = {
            a.contract_id: a
            for a in (
                await session.scalars(select(Attendance).where(Attendance.meeting_id == meeting.id))
            ).all()
        }
        items = [
            i.id
            for i in (
                await session.scalars(select(AgendaItem).where(AgendaItem.meeting_id == meeting.id))
            ).all()
        ]
        votes: dict[uuid.UUID, dict[str, str]] = {}
        vote_channels: dict[uuid.UUID, dict[str, str]] = {}
        if items:
            for v in (
                await session.scalars(select(Vote).where(Vote.agenda_item_id.in_(items)))
            ).all():
                votes.setdefault(v.contract_id, {})[str(v.agenda_item_id)] = v.choice
                vote_channels.setdefault(v.contract_id, {})[str(v.agenda_item_id)] = v.channel
        out = []
        for c in members:
            unit = await session.get(Unit, c.unit_id)
            party = await session.get(Party, c.party_id)
            att = attendance.get(c.id)
            out.append(
                {
                    "contract_id": c.id,
                    "unit_number": unit.number if unit else None,
                    "party_id": c.party_id,
                    "party_name": party.name if party else None,
                    "present": bool(att and att.present),
                    "proxy": bool(att and att.proxy_contact_id),
                    "channel": meeting_rules.attendance_channel(att),
                    "votes": votes.get(c.id, {}),
                    "vote_channels": vote_channels.get(c.id, {}),
                }
            )
        return out


@router.get(
    "/meetings/{meeting_id}/invitation-recipients",
    summary="Empfänger der Einladung (Parteimitglieder und Bevollmächtigte nach Zustellregel)",
    dependencies=[Depends(strict_query)],
)
async def invitation_recipients(
    meeting_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    """Per ownership contract on the meeting day: the party members and, following the
    delivery rule of authorised representatives (``mhvp.contacts.recipients``), who receives
    the invitation. A contact that owns several units or represents several owners appears
    once per contract; the caller deduplicates for the actual dispatch."""
    from mhvp.contacts.models import Contact, Party, PartyMember
    from mhvp.contacts.recipients import resolve_recipients
    from mhvp.properties.models import Unit

    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        prop = await _hoa_property(session, meeting.legal_entity_id)
        members = await _members(session, prop, meeting.scheduled_at.date())
        out = []
        for c in members:
            unit = await session.get(Unit, c.unit_id)
            party = await session.get(Party, c.party_id)
            member_ids = list(
                (
                    await session.scalars(
                        select(PartyMember.contact_id)
                        .where(PartyMember.party_id == c.party_id)
                        .order_by(PartyMember.created_at, PartyMember.id)
                    )
                ).all()
            )
            recipients = []
            for r in await resolve_recipients(session, member_ids):
                contact = await session.get(Contact, r.contact_id)
                represented = await session.get(Contact, r.represents) if r.represents else None
                recipients.append(
                    {
                        "contact_id": r.contact_id,
                        "display_name": contact.display_name if contact else None,
                        "channel": (
                            contact.preferred_channel.value
                            if contact and contact.preferred_channel
                            else "post"
                        ),
                        "represents_contact_id": r.represents,
                        "represents_name": represented.display_name if represented else None,
                    }
                )
            out.append(
                {
                    "contract_id": c.id,
                    "unit_number": unit.number if unit else None,
                    "party_id": c.party_id,
                    "party_name": party.name if party else None,
                    "member_contact_ids": member_ids,
                    "recipients": recipients,
                }
            )
        return out


@router.post(
    "/meetings/{meeting_id}/protocol-draft",
    status_code=201,
    summary="Protokollentwurf als PDF (A62, Entwurf ohne Rechtsfolge)",
)
async def protocol_draft(
    meeting_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Renders the minutes template (agenda, attendance with voting rights, resolution text,
    tally, announcement, signature lines) on the tenant letterhead and files it as a draft
    document linked to the meeting (`minutes_draft_document_id`). The signed minutes in
    `minutes_document_id` are never replaced. Permission: the write right of the HOA module
    (accounting:create, as for every other meeting action)."""
    from mhvp.documents import services as docs
    from mhvp.documents.blobs import BlobStore
    from mhvp.documents.models import DocumentSource, LinkRole
    from mhvp.hoa import protocol

    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        blobs = BlobStore(request.app.state.settings)
        head = await docs.letterhead(session, blobs)
        context, missing = await protocol.build_context(session, meeting)
        draft = protocol.compose(context, missing, local_today())
        pdf = protocol.render(head, draft)
        document = await docs.store_document(
            session,
            blobs,
            tenant_id=principal.tenant_id,
            data=pdf,
            title=draft.title,
            filename=draft.filename,
            mime_type="application/pdf",
            source=DocumentSource.GENERATED,
            category_id=None,
            links=[("legal_entity", meeting.legal_entity_id, LinkRole.GENERATED)],
            created_by=principal.user_id,
        )
        meeting.minutes_draft_document_id = document.id
        meeting.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa.meeting.protocol_draft",
            entity_type="owners_meeting",
            entity_id=meeting.id,
            actor_user_id=principal.user_id,
            changes={"document_id": str(document.id)},
        )
        return {
            "meeting_id": meeting.id,
            "document_id": document.id,
            "minutes_document_id": meeting.minutes_document_id,
            "title": draft.title,
            "filename": draft.filename,
            "status": "draft",
            "missing": draft.missing,
            "note": protocol.DRAFT_NOTICE,
        }


@router.post("/majority-rules", status_code=201, summary="Mehrheitsregel mit Fundstelle (M25-01)")
async def create_rule(
    body: MajorityRuleIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    if (
        body.share_of_votes_cast is None
        and body.min_mea_share_of_all is None
        and not body.unanimous
    ):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Regel ohne Schwelle.")
    async with tenant_tx(request, principal) as session:
        await _hoa_property(session, body.legal_entity_id)
        row = MajorityRule(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return {"id": row.id, **body.model_dump()}


@router.get(
    "/majority-rules", summary="Mehrheitsregeln einer GdWE", dependencies=[Depends(strict_query)]
)
async def list_rules(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(MajorityRule)
            .where(MajorityRule.legal_entity_id == legal_entity_id)
            .order_by(MajorityRule.label)
        )
        return [
            {
                "id": r.id,
                "label": r.label,
                "principle": r.principle,
                "share_of_votes_cast": r.share_of_votes_cast,
                "strictly_greater": r.strictly_greater,
                "min_mea_share_of_all": r.min_mea_share_of_all,
                "unanimous": r.unanimous,
                "source": r.source,
                "valid_from": r.valid_from,
                "valid_to": r.valid_to,
            }
            for r in rows.all()
        ]


# Closing of the minutes (R07-01) -----------------------------------------------------------

CLOSING_STATUSES = frozenset({"closing", "closed"})
# No statutory period is computed or enforced here (open question R07-01); the hint is shown
# with the closing and locks nothing.
MINUTES_PERIOD_NOTE = (
    "Hinweis: Eine Frist zur Erstellung oder Versendung des Protokolls ergibt sich aus "
    "Gesetz, Gemeinschaftsordnung oder Verwaltervertrag und ist im Einzelfall zu prüfen. "
    "Das System berechnet und sperrt keine Protokollfrist."
)


class MeetingCloseIn(MeetingBaseIn):
    minutes_document_id: uuid.UUID


class MeetingCloseConfirmIn(MeetingBaseIn):
    minutes_document_id: uuid.UUID


async def _minutes_document(
    session: AsyncSession, document_id: uuid.UUID, meeting: Meeting | None = None
) -> None:
    """Review W79: the minutes document lies inside the document scope of the membership
    (legal entity and property assignment, otherwise not found) and does not belong to another
    community: a document linked to legal entities or properties must be linked to the GdWE of
    the meeting or to its property. An unlinked upload stays allowed (DocumentPicker)."""
    from mhvp.documents.models import Document, DocumentLink
    from mhvp.documents.routers import _get as document_get
    from mhvp.properties.models import LegalEntity

    if await session.get(Document, document_id) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Protokolldokument nicht gefunden.")
    try:
        await document_get(session, Document, document_id)
    except ProblemError as exc:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Protokolldokument nicht gefunden."
        ) from exc
    if meeting is None:
        return
    links = (
        await session.execute(
            select(DocumentLink.entity_type, DocumentLink.entity_id).where(
                DocumentLink.document_id == document_id,
                DocumentLink.entity_type.in_(("legal_entity", "property")),
            )
        )
    ).all()
    if not links:
        return
    entity = await session.get(LegalEntity, meeting.legal_entity_id)
    own = {("legal_entity", meeting.legal_entity_id)}
    if entity is not None and entity.property_id is not None:
        own.add(("property", entity.property_id))
    if not own.intersection((kind, eid) for kind, eid in links):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Protokolldokument gehört zu einer anderen Gemeinschaft.",
        )


@router.post("/meetings/{meeting_id}/close", summary="Protokollabschluss beantragen (R07-01)")
async def request_close(
    meeting_id: uuid.UUID,
    body: MeetingCloseIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """First step of the four eyes closing: links the signed minutes and locks the meeting
    (status closing). A second person confirms with ``/close/confirm``."""
    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        await session.refresh(meeting, with_for_update=True)  # review W79: serialize steps
        if meeting.status in CLOSING_STATUSES:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Abschluss bereits beantragt.")
        if meeting.status != "held":
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Abschluss nur für eine durchgeführte Versammlung ohne offene Störung.",
            )
        await _minutes_document(session, body.minutes_document_id, meeting)
        meeting.minutes_document_id = body.minutes_document_id
        meeting.status = "closing"
        meeting.close_requested_by = principal.user_id
        meeting.close_requested_at = datetime.now(UTC)
        meeting.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa.meeting.close_requested",
            entity_type="owners_meeting",
            entity_id=meeting.id,
            actor_user_id=principal.user_id,
            changes={"minutes_document_id": str(body.minutes_document_id)},
        )
        await session.flush()
        return _meeting_out(meeting) | {"note": MINUTES_PERIOD_NOTE}


@router.post(
    "/meetings/{meeting_id}/close/confirm", summary="Protokollabschluss bestätigen (R07-01)"
)
async def confirm_close(
    meeting_id: uuid.UUID,
    body: MeetingCloseConfirmIn,
    request: Request,
    principal: TenantPrincipal = Depends(APPROVE),
) -> dict[str, Any]:
    """Second step: a different person confirms the same minutes document; status closed,
    event ``meeting.closed`` (webhook)."""
    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        await session.refresh(meeting, with_for_update=True)  # review W79: serialize steps
        if meeting.status != "closing":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Kein offener Abschlussantrag.")
        if meeting.close_requested_by == principal.user_id:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Vier-Augen-Prinzip: Bestätigung durch eine zweite Person.",
            )
        if body.minutes_document_id != meeting.minutes_document_id:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Protokolldokument weicht vom Antrag ab."
            )
        meeting.status = "closed"
        meeting.closed_by = principal.user_id
        meeting.closed_at = datetime.now(UTC)
        meeting.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meeting.closed",
            entity_type="owners_meeting",
            entity_id=meeting.id,
            actor_user_id=principal.user_id,
            payload={"minutes_document_id": str(meeting.minutes_document_id)},
        )
        await session.flush()
        return _meeting_out(meeting) | {"note": MINUTES_PERIOD_NOTE}


@router.post(
    "/meetings/{meeting_id}/close/withdraw", summary="Abschlussantrag zurückziehen (R07-01)"
)
async def withdraw_close(
    meeting_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Withdraws an open closing request (for example wrong document); a closed meeting stays
    closed."""
    async with tenant_tx(request, principal) as session:
        meeting = await _get(session, Meeting, meeting_id)
        await session.refresh(meeting, with_for_update=True)  # review W79: serialize steps
        if meeting.status != "closing":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Kein offener Abschlussantrag.")
        meeting.status = "held"
        meeting.close_requested_by = None
        meeting.close_requested_at = None
        meeting.minutes_document_id = None
        meeting.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="hoa.meeting.close_withdrawn",
            entity_type="owners_meeting",
            entity_id=meeting.id,
            actor_user_id=principal.user_id,
        )
        await session.flush()
        return _meeting_out(meeting)
