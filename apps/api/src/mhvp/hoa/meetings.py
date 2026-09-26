"""Owners' meeting, circular resolution and board audit (M25, R05, R03, PÜ06 to PÜ09).

The system counts and proposes; the chair announces the result. Only a simple majority of
yes over no votes (abstentions not counted) is computed; qualified and unanimous majorities
are flagged for a manual check with a documented basis (open question M25-01). Rules of the
individual community (Teilungserklärung, Vereinbarungen) are not known to the system."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.hoa.models import (
    AgendaItem,
    Attendance,
    AuditEngagement,
    AuditItem,
    AuditReport,
    HoaStatement,
    MajorityRule,
    Meeting,
    Resolution,
    Vote,
)

router = APIRouter(prefix="/hoa", tags=["hoa"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")
APPROVE = require_permission("accounting:approve")
ZERO = Decimal("0")
INVITATION_WEEKS = 3  # § 24 Abs. 4 WEG (R05); urgency exception is a manual decision


class MeetingBaseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MeetingIn(MeetingBaseIn):
    legal_entity_id: uuid.UUID
    kind: str = Field(default="ordinary", pattern="^(ordinary|extraordinary)$")
    mode: str = Field(default="presence", pattern="^(presence|hybrid|virtual)$")
    scheduled_at: datetime
    location: str | None = Field(default=None, max_length=300)
    voting_principle: str = Field(default="head", pattern="^(head|mea|unit)$")
    voting_principle_basis: str | None = Field(default=None, max_length=4000)
    virtual_basis_resolution_id: uuid.UUID | None = None
    resolution_deadline_at: date | None = None
    resolution_deadline_source: str | None = Field(default=None, max_length=4000)


class MeetingPatch(MeetingBaseIn):
    """Resolution deadline of a virtual meeting (M9-07). ``null`` clears both fields."""

    resolution_deadline_at: date | None = None
    resolution_deadline_source: str | None = Field(default=None, max_length=4000)


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
    majority: str = Field(default="simple", pattern="^(simple|qualified|unanimous|rule)$")
    subject_type: str | None = Field(
        default=None, pattern="^(economic_plan|hoa_statement|special_levy|other)$"
    )
    subject_id: uuid.UUID | None = None
    rule_id: uuid.UUID | None = None


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


class AnnounceIn(MeetingBaseIn):
    outcome: str = Field(pattern="^(positive|negative)$")
    majority_basis: str = Field(min_length=3, max_length=4000)
    snapshot_hash: str | None = Field(default=None, max_length=64)


class CircularIn(MeetingBaseIn):
    legal_entity_id: uuid.UUID
    subject: str = Field(min_length=3, max_length=2000)
    wording: str = Field(min_length=3, max_length=20000)
    decided_on: date
    consents: dict[uuid.UUID, str]  # ownership contract -> yes, no, abstain (text form)
    evidence_document_id: uuid.UUID | None = None


class EngagementIn(MeetingBaseIn):
    legal_entity_id: uuid.UUID
    statement_id: uuid.UUID | None = None
    period_from: date
    period_to: date
    purpose: str = Field(min_length=3, max_length=4000)
    auditor_contact_ids: list[uuid.UUID] = Field(min_length=1)
    sampling: str = Field(default="sample", pattern="^(sample|full)$")
    accounts: list[str] = Field(default_factory=list)


class AuditItemIn(MeetingBaseIn):
    journal_entry_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    amount: Decimal | None = None


class AuditItemPatch(MeetingBaseIn):
    status: str | None = Field(default=None, pattern="^(open|checked|query|objection)$")
    note: str | None = Field(default=None, max_length=4000)
    question: str | None = Field(default=None, max_length=4000)
    answer: str | None = Field(default=None, max_length=4000)


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


def _meeting_out(m: Meeting) -> dict[str, Any]:
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
        "resolution_deadline_at": m.resolution_deadline_at,
        "resolution_deadline_source": m.resolution_deadline_source,
    }


@router.post("/meetings", status_code=201, summary="Eigentümerversammlung anlegen")
async def create_meeting(
    body: MeetingIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        await _hoa_property(session, body.legal_entity_id)
        if body.mode == "virtual":
            basis = (
                await session.get(Resolution, body.virtual_basis_resolution_id)
                if body.virtual_basis_resolution_id
                else None
            )
            if basis is None or basis.status not in {"positive", "final", "legally_binding"}:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Virtuelle Versammlung nur mit Beschlussgrundlage (R05).",
                )
        if body.voting_principle != "head" and not body.voting_principle_basis:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Abweichendes Stimmprinzip nur mit dokumentierter Grundlage.",
            )
        validate_resolution_deadline(
            body.mode, body.resolution_deadline_at, body.resolution_deadline_source
        )
        row = Meeting(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return _meeting_out(row)


@router.patch("/meetings/{meeting_id}", summary="Beschlussfrist der Versammlung (M9-07)")
async def patch_meeting(
    meeting_id: uuid.UUID,
    body: MeetingPatch,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, Meeting, meeting_id)
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
        row = AgendaItem(
            tenant_id=principal.tenant_id,
            meeting_id=meeting.id,
            position=count + 1,
            **(body.model_dump() | {"majority": "rule" if body.rule_id else body.majority}),
        )
        session.add(row)
        await session.flush()
        return {"id": row.id, "position": row.position, "majority": row.majority}


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
        earliest = body.invited_at + timedelta(weeks=INVITATION_WEEKS)
        short = meeting.scheduled_at.date() < earliest
        if short and not body.urgency_reason:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=(
                    f"Einladungsfrist unterschritten (orientierend frühestens {earliest:%d.%m.%Y},"
                    " zu verifizieren). Kürzere Frist nur mit dokumentierter Dringlichkeit."
                ),
            )
        meeting.invited_at = body.invited_at
        meeting.status = "invited"
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
        return _meeting_out(meeting) | {"short_notice": short}


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


def _ensure_not_disrupted(meeting: Meeting) -> None:
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
        if att is None or not (att.present or att.proxy_contact_id):
            raise ProblemError(ErrorCodes.VALIDATION, detail="Nicht anwesend oder vertreten.")
        if await session.scalar(
            select(Resolution.id).where(
                Resolution.subject_type == "agenda_item", Resolution.subject_id == item.id
            )
        ):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Ergebnis bereits verkündet.")
        existing = await session.scalar(
            select(Vote).where(Vote.agenda_item_id == item.id, Vote.contract_id == body.contract_id)
        )
        if existing is not None:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Stimme bereits erfasst.")
        row = Vote(tenant_id=principal.tenant_id, agenda_item_id=item.id, **body.model_dump())
        session.add(row)
        await session.flush()
        return {"id": row.id}


async def _tally(session: AsyncSession, item: AgendaItem, meeting: Meeting) -> dict[str, Any]:
    from mhvp.contracts.models import Contract

    prop = await _hoa_property(session, meeting.legal_entity_id)
    day = meeting.scheduled_at.date()
    rule = await session.get(MajorityRule, item.rule_id) if item.rule_id else None
    principle = rule.principle if rule else meeting.voting_principle
    votes = (await session.scalars(select(Vote).where(Vote.agenda_item_id == item.id))).all()
    sums = {"yes": ZERO, "no": ZERO, "abstain": ZERO}
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
        )
        session.add(row)
        await session.flush()
        return {"id": row.id, "number": row.number, "status": row.status, "votes": result}


@router.post("/circular-resolutions", status_code=201, summary="Umlaufbeschluss (Textform)")
async def circular(
    body: CircularIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    """Positive only if every owner agreed in text form (§ 23 Abs. 3 WEG); a lower majority
    needs a prior resolution and is not implemented (open question M25-02)."""
    from sqlalchemy import func

    async with tenant_tx(request, principal) as session:
        prop = await _hoa_property(session, body.legal_entity_id)
        members = {c.id for c in await _members(session, prop, body.decided_on)}
        unknown = set(body.consents) - members
        if unknown:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Zustimmung von Nichteigentümern.")
        missing = members - set(body.consents)
        positive = not missing and all(c == "yes" for c in body.consents.values())
        if body.evidence_document_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Nachweis der Textform fehlt.")
        number = int(
            await session.scalar(
                select(func.coalesce(func.max(Resolution.number), 0)).where(
                    Resolution.legal_entity_id == body.legal_entity_id
                )
            )
            or 0
        )
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
            majority_basis="Allstimmigkeit in Textform (§ 23 Abs. 3 WEG)",
            votes={
                "consents": {str(k): v for k, v in body.consents.items()},
                "missing": sorted(str(m) for m in missing),
                "evidence_document_id": str(body.evidence_document_id),
            },
        )
        session.add(row)
        await session.flush()
        return {"id": row.id, "number": row.number, "status": row.status, "missing": len(missing)}


# Board audit -----------------------------------------------------------------------------


@router.post("/audits", status_code=201, summary="Prüfauftrag (PÜ06)")
async def create_audit(
    body: EngagementIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.accounting.models import EntryStatus, JournalEntry, Ledger

    async with tenant_tx(request, principal) as session:
        await _hoa_property(session, body.legal_entity_id)
        if body.period_to < body.period_from:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Zeitraum ungültig.")
        snapshot_hash = None
        if body.statement_id:
            st = await _get(session, HoaStatement, body.statement_id)
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
        eng = await _get(session, AuditEngagement, audit_id)
        if not body.journal_entry_id and not body.document_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Buchung oder Beleg angeben.")
        row = AuditItem(tenant_id=principal.tenant_id, engagement_id=eng.id, **body.model_dump())
        session.add(row)
        await session.flush()
        return _item_out(row)


@router.patch("/audit-items/{item_id}", summary="Vermerk, Rückfrage, Antwort (PÜ08)")
async def patch_audit_item(
    item_id: uuid.UUID,
    body: AuditItemPatch,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, AuditItem, item_id)
        if row.status == "outdated":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Position zu alter Version.")
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        row.version += 1
        await session.flush()
        return _item_out(row)


@router.post("/audits/{audit_id}/reports", status_code=201, summary="Prüfbericht (PÜ09)")
async def create_report(
    audit_id: uuid.UUID,
    body: AuditReportIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> dict[str, Any]:
    from sqlalchemy import func

    async with tenant_tx(request, principal) as session:
        eng = await _get(session, AuditEngagement, audit_id)
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
            "date": datetime.now(UTC).date().isoformat(),
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
    return str(value.quantize(Decimal("0.01")))


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
    audit_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        eng = await _get(session, AuditEngagement, audit_id)
        outdated_reasons = await refresh_audit_items(session, eng)
        items = (
            await session.scalars(
                select(AuditItem)
                .where(AuditItem.engagement_id == eng.id)
                .order_by(AuditItem.created_at, AuditItem.id)
            )
        ).all()
        return {
            "id": eng.id,
            "legal_entity_id": eng.legal_entity_id,
            "statement_id": eng.statement_id,
            "sampling": eng.sampling,
            "population": eng.population,
            "status": eng.status,
            "overall_status": _overall_status(items),
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


@router.get("/meetings", summary="Versammlungen einer GdWE")
async def list_meetings(
    legal_entity_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[dict[str, Any]]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(Meeting)
            .where(Meeting.legal_entity_id == legal_entity_id)
            .order_by(Meeting.scheduled_at.desc())
        )
        return [_meeting_out(m) for m in rows.all()]


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
        return _meeting_out(meeting) | {
            "agenda": [
                {
                    "id": i.id,
                    "position": i.position,
                    "title": i.title,
                    "proposal": i.proposal,
                    "majority": i.majority,
                    "resolution": announced.get(i.id),
                }
                for i in items
            ],
            "represented": sum(1 for a in attendance if a.present or a.proxy_contact_id),
            "proxies": sum(1 for a in attendance if a.proxy_contact_id),
            "disruptions": await _disruptions(session, meeting.id),
        }


@router.get(
    "/meetings/{meeting_id}/members", summary="Stimmberechtigte mit Anwesenheit und Stimmen"
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
        if items:
            for v in (
                await session.scalars(select(Vote).where(Vote.agenda_item_id.in_(items)))
            ).all():
                votes.setdefault(v.contract_id, {})[str(v.agenda_item_id)] = v.choice
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
                    "votes": votes.get(c.id, {}),
                }
            )
        return out


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


@router.get("/majority-rules", summary="Mehrheitsregeln einer GdWE")
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
