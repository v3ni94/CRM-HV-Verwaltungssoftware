"""Beiratsbeteiligung an Tickets und Aufträgen (M19-02, docs/rules/M19-02-beiratsbeteiligung.md).

For a WEG property (``legal_entity.kind = hoa``) the management can submit a ticket, or the
work order behind it, to the Verwaltungsbeirat for information (``info``) or for an opinion
(``consent``). Board members are the property contacts with the category ``board``
(``property_contact.category_code``, section 6.2); their contact ids are frozen on the
submission so the protocol shows who was asked. Members answer in the portal (approve, reject
or comment) until the deadline; the management can record an answer received by other means
in the CRM. Every answer stays on the ticket as protocol.

The board vote is information only: the release of a work order stays with the management
(``POST /tickets/work-orders/{id}/steps`` with ``tickets:approve``) and no payment ever
follows from a submission (Produktschutz, M19-02, G2 closed). A policy per tenant
(``ticket_board_policy``) only *recommends* a submission above an amount or for configured
categories; it never blocks or releases anything.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.portal.models import PortalAccount
from mhvp.tickets.models import Ticket, TicketEvent, WorkOrder

BOARD_CONTACT_CATEGORY = "board"  # properties.defaults.PROPERTY_CONTACT_CATEGORIES
SUBMISSION_KINDS = ("info", "consent")
VOTES = ("approve", "reject", "comment")
STATUS_OPEN, STATUS_CLOSED = "open", "closed"
DEFAULT_CATEGORIES = ["instandhaltung"]


def _fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class BoardPolicy(IdMixin, TimestampMixin, TenantMixin, Base):
    """Per tenant: when a submission is *recommended*. Never a lock, never a release."""

    __tablename__ = "ticket_board_policy"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list, server_default=text("'{}'::varchar[]")
    )
    default_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="info", server_default="info"
    )
    default_deadline_days: Mapped[int] = mapped_column(
        nullable=False, default=14, server_default="14"
    )


class BoardSubmission(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ticket_board_submission"
    __table_args__ = (Index("ix_ticket_board_submission_ticket", "tenant_id", "ticket_id"),)

    ticket_id: Mapped[uuid.UUID] = _fk("ticket.id", nullable=False, ondelete="CASCADE")
    work_order_id: Mapped[uuid.UUID | None] = _fk("work_order.id", ondelete="SET NULL")
    property_id: Mapped[uuid.UUID] = _fk("property.id", nullable=False)
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    due_on: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_OPEN, server_default=STATUS_OPEN
    )
    member_contact_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closing_note: Mapped[str | None] = mapped_column(Text)


class BoardVote(IdMixin, TenantMixin, Base):
    """Append only: one row per answer; a member may answer again, the protocol keeps all."""

    __tablename__ = "ticket_board_vote"
    __table_args__ = (Index("ix_ticket_board_vote_submission", "tenant_id", "submission_id"),)

    submission_id: Mapped[uuid.UUID] = _fk(
        "ticket_board_submission.id", nullable=False, ondelete="CASCADE"
    )
    contact_id: Mapped[uuid.UUID] = _fk("contact.id", nullable=False)
    vote: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # portal, crm
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )


# --- Schemas ---------------------------------------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BoardPolicyIn(_In):
    threshold_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    categories: list[str] = Field(default_factory=lambda: list(DEFAULT_CATEGORIES), max_length=50)
    default_kind: str = Field(default="info", pattern="^(info|consent)$")
    default_deadline_days: int = Field(default=14, ge=1, le=90)


class BoardSubmissionIn(_In):
    kind: str = Field(default="info", pattern="^(info|consent)$")
    due_on: date
    work_order_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=4000)


class BoardVoteIn(_In):
    vote: str = Field(pattern="^(approve|reject|comment)$")
    comment: str | None = Field(default=None, max_length=4000)


class CrmVoteIn(BoardVoteIn):
    contact_id: uuid.UUID


class CloseIn(_In):
    closing_note: str | None = Field(default=None, max_length=4000)


# --- Helpers ---------------------------------------------------------------------------


async def get_policy(session: AsyncSession, tenant_id: uuid.UUID) -> BoardPolicy:
    row = await session.scalar(select(BoardPolicy).where(BoardPolicy.tenant_id == tenant_id))
    if row is None:
        row = BoardPolicy(tenant_id=tenant_id, categories=list(DEFAULT_CATEGORIES))
        session.add(row)
        await session.flush()
    return row


def _policy_out(row: BoardPolicy) -> dict[str, Any]:
    return {
        "threshold_amount": row.threshold_amount,
        "categories": row.categories,
        "default_kind": row.default_kind,
        "default_deadline_days": row.default_deadline_days,
    }


async def hoa_entity_id(session: AsyncSession, property_id: uuid.UUID) -> uuid.UUID | None:
    from mhvp.properties.models import LegalEntity, LegalEntityKind

    row: uuid.UUID | None = await session.scalar(
        select(LegalEntity.id).where(
            LegalEntity.property_id == property_id, LegalEntity.kind == LegalEntityKind.HOA
        )
    )
    return row


async def board_member_contact_ids(
    session: AsyncSession, property_id: uuid.UUID, today: date
) -> list[uuid.UUID]:
    """Current board members of the property: ``property_contact`` with category ``board``
    valid today (existing role from section 6.2, no separate role table)."""
    from mhvp.properties.models import PropertyContact

    rows = await session.scalars(
        select(PropertyContact.contact_id)
        .where(
            PropertyContact.property_id == property_id,
            PropertyContact.category_code == BOARD_CONTACT_CATEGORY,
            PropertyContact.valid_from <= today,
            (PropertyContact.valid_to.is_(None)) | (PropertyContact.valid_to >= today),
        )
        .order_by(PropertyContact.valid_from)
    )
    return list(dict.fromkeys(rows.all()))


def recommendation(policy: BoardPolicy, ticket: Ticket, amount: Decimal | None) -> dict[str, Any]:
    """Whether the policy *recommends* a submission (category or amount). Information only."""
    by_category = bool(ticket.category) and ticket.category in policy.categories
    by_amount = (
        policy.threshold_amount is not None
        and amount is not None
        and amount >= policy.threshold_amount
    )
    return {
        "recommended": by_category or by_amount,
        "by_category": by_category,
        "by_amount": by_amount,
        "kind": policy.default_kind,
        "deadline_days": policy.default_deadline_days,
    }


async def _contact_names(
    session: AsyncSession, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, str]:
    from mhvp.contacts.models import Contact

    if not contact_ids:
        return {}
    rows = await session.execute(
        select(Contact.id, Contact.display_name).where(Contact.id.in_(contact_ids))
    )
    return {row[0]: row[1] for row in rows.all()}


def _vote_out(v: BoardVote, names: dict[uuid.UUID, str]) -> dict[str, Any]:
    return {
        "id": v.id,
        "contact_id": v.contact_id,
        "contact_name": names.get(v.contact_id),
        "vote": v.vote,
        "comment": v.comment,
        "source": v.source,
        "created_at": v.created_at,
    }


async def _submission_out(
    session: AsyncSession, s: BoardSubmission, *, today: date
) -> dict[str, Any]:
    votes = (
        await session.scalars(
            select(BoardVote).where(BoardVote.submission_id == s.id).order_by(BoardVote.created_at)
        )
    ).all()
    names = await _contact_names(
        session, list({*s.member_contact_ids, *(v.contact_id for v in votes)})
    )
    tally = {k: sum(1 for v in votes if v.vote == k) for k in VOTES}
    return {
        "id": s.id,
        "ticket_id": s.ticket_id,
        "work_order_id": s.work_order_id,
        "property_id": s.property_id,
        "legal_entity_id": s.legal_entity_id,
        "kind": s.kind,
        "title": s.title,
        "note": s.note,
        "amount": s.amount,
        "due_on": s.due_on,
        "overdue": s.status == STATUS_OPEN and s.due_on < today,
        "status": s.status,
        "members": [{"contact_id": c, "name": names.get(c)} for c in s.member_contact_ids],
        "votes": [_vote_out(v, names) for v in votes],
        "tally": tally,
        "closed_at": s.closed_at,
        "closing_note": s.closing_note,
        "created_at": s.created_at,
    }


def _today() -> date:
    from mhvp.workspace.services import local_today

    return local_today()


async def _protocol(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    tenant_id: uuid.UUID,
    kind: str,
    user: uuid.UUID | None,
    data: dict[str, Any],
) -> None:
    session.add(
        TicketEvent(tenant_id=tenant_id, ticket_id=ticket_id, kind=kind, user_id=user, data=data)
    )


# --- CRM router: paths under /tickets; the literal segment "board" avoids /tickets/{ticket_id}

router = APIRouter(tags=["Tickets und Aufträge"])
READ = require_permission("tickets:read")
UPDATE = require_permission("tickets:update")
APPROVE = require_permission("tickets:approve")


@router.get(
    "/tickets/board/policy", summary="Beiratsbeteiligung: Empfehlungsregel des Mandanten (M19-02)"
)
async def read_policy(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        return _policy_out(await get_policy(session, principal.tenant_id))


@router.put(
    "/tickets/board/policy", summary="Beiratsbeteiligung: Empfehlungsregel ändern (tickets:approve)"
)
async def write_policy(
    body: BoardPolicyIn, request: Request, principal: TenantPrincipal = Depends(APPROVE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        policy = await get_policy(session, principal.tenant_id)
        policy.threshold_amount = body.threshold_amount
        policy.categories = [c.strip() for c in body.categories if c.strip()]
        policy.default_kind = body.default_kind
        policy.default_deadline_days = body.default_deadline_days
        policy.updated_by = principal.user_id
        await session.flush()
        return _policy_out(policy)


@router.get(
    "/tickets/{ticket_id}/board-submissions", summary="Beiratsvorlagen eines Tickets mit Protokoll"
)
async def list_submissions(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    """Also reports whether the ticket belongs to a WEG, its current board members and the
    policy recommendation (largest quote of the ticket's work orders as amount)."""
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        today = _today()
        hoa = await hoa_entity_id(session, ticket.property_id) if ticket.property_id else None
        members = (
            await board_member_contact_ids(session, ticket.property_id, today)
            if ticket.property_id and hoa
            else []
        )
        names = await _contact_names(session, members)
        amounts = [
            a
            for a in (
                await session.scalars(
                    select(WorkOrder.quote_amount).where(WorkOrder.ticket_id == ticket.id)
                )
            ).all()
            if a is not None
        ]
        policy = await get_policy(session, principal.tenant_id)
        rows = (
            await session.scalars(
                select(BoardSubmission)
                .where(BoardSubmission.ticket_id == ticket.id)
                .order_by(BoardSubmission.created_at.desc())
            )
        ).all()
        return {
            "is_hoa": hoa is not None,
            "legal_entity_id": hoa,
            "members": [{"contact_id": c, "name": names.get(c)} for c in members],
            "recommendation": recommendation(policy, ticket, max(amounts) if amounts else None),
            "submissions": [await _submission_out(session, s, today=today) for s in rows],
        }


@router.post(
    "/tickets/{ticket_id}/board-submissions",
    status_code=201,
    summary="Ticket oder Auftrag dem Verwaltungsbeirat vorlegen (Kenntnis oder Zustimmung)",
)
async def create_submission(
    ticket_id: uuid.UUID,
    body: BoardSubmissionIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        ticket = await session.get(Ticket, ticket_id)
        if ticket is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        today = _today()
        if body.due_on < today:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Die Frist liegt in der Vergangenheit."
            )
        if ticket.property_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Das Ticket hat kein Objekt.")
        hoa = await hoa_entity_id(session, ticket.property_id)
        if hoa is None:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Beiratsvorlagen gibt es nur bei WEG-Objekten."
            )
        members = await board_member_contact_ids(session, ticket.property_id, today)
        if not members:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Für dieses Objekt ist kein Verwaltungsbeirat als Ansprechpartner "
                "(Kategorie Beirat) hinterlegt.",
            )
        order: WorkOrder | None = None
        if body.work_order_id is not None:
            order = await session.get(WorkOrder, body.work_order_id)
            if order is None or order.ticket_id != ticket.id:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Der Auftrag gehört nicht zu diesem Ticket."
                )
        submission = BoardSubmission(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            ticket_id=ticket.id,
            work_order_id=order.id if order else None,
            property_id=ticket.property_id,
            legal_entity_id=hoa,
            kind=body.kind,
            title=ticket.title,
            note=body.note,
            amount=order.quote_amount if order else None,
            due_on=body.due_on,
            member_contact_ids=members,
        )
        session.add(submission)
        if order is not None and body.kind == "consent":
            # Vermerkpflicht bei der Freigabe (bestehende Regel im Auftragsschritt approved).
            order.requires_board_approval = True
        await session.flush()
        await _protocol(
            session,
            ticket.id,
            principal.tenant_id,
            "board_submission",
            principal.user_id,
            {
                "submission_id": str(submission.id),
                "kind": body.kind,
                "due_on": body.due_on.isoformat(),
                "members": len(members),
            },
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ticket.board_submitted",
            entity_type="ticket",
            entity_id=ticket.id,
            actor_user_id=principal.user_id,
            payload={"submission_id": str(submission.id), "kind": body.kind},
        )
        return await _submission_out(session, submission, today=today)


@router.post(
    "/tickets/board/submissions/{submission_id}/votes",
    status_code=201,
    summary="Rückmeldung eines Beiratsmitglieds im CRM erfassen (z. B. per Telefon oder Brief)",
)
async def record_vote(
    submission_id: uuid.UUID,
    body: CrmVoteIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        submission = await session.get(BoardSubmission, submission_id)
        if submission is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if submission.status != STATUS_OPEN:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Vorlage ist abgeschlossen.")
        if body.contact_id not in submission.member_contact_ids:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Der Kontakt gehört nicht zum vorgelegten Beirat."
            )
        vote = BoardVote(
            tenant_id=principal.tenant_id,
            submission_id=submission.id,
            contact_id=body.contact_id,
            vote=body.vote,
            comment=body.comment,
            source="crm",
            recorded_by=principal.user_id,
        )
        session.add(vote)
        await session.flush()
        await _protocol(
            session,
            submission.ticket_id,
            principal.tenant_id,
            "board_vote",
            principal.user_id,
            {
                "submission_id": str(submission.id),
                "contact_id": str(body.contact_id),
                "vote": body.vote,
                "source": "crm",
            },
        )
        return await _submission_out(session, submission, today=_today())


@router.post(
    "/tickets/board/submissions/{submission_id}/close",
    summary="Beiratsvorlage abschließen (Ergebnis ist Information, keine Freigabe)",
)
async def close_submission(
    submission_id: uuid.UUID,
    body: CloseIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        submission = await session.get(BoardSubmission, submission_id)
        if submission is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if submission.status == STATUS_OPEN:
            submission.status = STATUS_CLOSED
            submission.closed_at = datetime.now(UTC)
            submission.closed_by = principal.user_id
            submission.closing_note = body.closing_note
            submission.updated_by = principal.user_id
            await session.flush()
            await _protocol(
                session,
                submission.ticket_id,
                principal.tenant_id,
                "board_submission_closed",
                principal.user_id,
                {"submission_id": str(submission.id), "closing_note": body.closing_note},
            )
        return await _submission_out(session, submission, today=_today())


# --- Portal router --------------------------------------------------------------------

portal_router = APIRouter(prefix="/portal/board/submissions", tags=["Portal Beirat"])


async def _portal_ctx(request: Request) -> Any:
    from mhvp.portal.routers import portal_user

    return await portal_user(request)


def _portal_out(
    s: BoardSubmission, votes: list[BoardVote], own: uuid.UUID, today: date
) -> dict[str, Any]:
    """Portal view: no internal notes of other members beyond their vote, no CRM user ids."""
    mine = [v for v in votes if v.contact_id == own]
    return {
        "id": s.id,
        "kind": s.kind,
        "title": s.title,
        "note": s.note,
        "amount": s.amount,
        "due_on": s.due_on,
        "status": s.status,
        "overdue": s.status == STATUS_OPEN and s.due_on < today,
        "can_vote": s.status == STATUS_OPEN and s.due_on >= today,
        "tally": {k: sum(1 for v in votes if v.vote == k) for k in VOTES},
        "member_count": len(s.member_contact_ids),
        "my_votes": [
            {"id": v.id, "vote": v.vote, "comment": v.comment, "created_at": v.created_at}
            for v in mine
        ],
        "created_at": s.created_at,
    }


async def _own_submission(
    session: AsyncSession, account: PortalAccount, submission_id: uuid.UUID
) -> BoardSubmission:
    s = await session.get(BoardSubmission, submission_id)
    if s is None or account.contact_id not in s.member_contact_ids:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)  # no hint whether it exists
    return s


@portal_router.get("", summary="Vorlagen an den eigenen Verwaltungsbeirat")
async def portal_list(request: Request, ctx: Any = Depends(_portal_ctx)) -> list[dict[str, Any]]:
    principal, account = ctx
    today = _today()
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(BoardSubmission)
                .where(BoardSubmission.member_contact_ids.any(account.contact_id))
                .order_by(BoardSubmission.status.desc(), BoardSubmission.due_on)
            )
        ).all()
        out = []
        for s in rows:
            votes = (
                await session.scalars(select(BoardVote).where(BoardVote.submission_id == s.id))
            ).all()
            out.append(_portal_out(s, list(votes), account.contact_id, today))
        return out


@portal_router.get("/{submission_id}", summary="Vorlage lesen (nur Beirat der eigenen GdWE)")
async def portal_read(
    submission_id: uuid.UUID, request: Request, ctx: Any = Depends(_portal_ctx)
) -> dict[str, Any]:
    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        s = await _own_submission(session, account, submission_id)
        votes = (
            await session.scalars(select(BoardVote).where(BoardVote.submission_id == s.id))
        ).all()
        return _portal_out(s, list(votes), account.contact_id, _today())


@portal_router.post(
    "/{submission_id}/votes",
    status_code=201,
    summary="Rückmeldung abgeben (Zustimmung, Ablehnung, Kommentar; bis zur Frist)",
)
async def portal_vote(
    submission_id: uuid.UUID,
    body: BoardVoteIn,
    request: Request,
    ctx: Any = Depends(_portal_ctx),
) -> dict[str, Any]:
    principal, account = ctx
    today = _today()
    async with tenant_tx(request, principal) as session:
        s = await _own_submission(session, account, submission_id)
        if s.status != STATUS_OPEN:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Vorlage ist abgeschlossen.")
        if s.due_on < today:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Die Frist ist abgelaufen.")
        if body.vote == "comment" and not (body.comment or "").strip():
            raise ProblemError(ErrorCodes.VALIDATION, detail="Ein Kommentar braucht einen Text.")
        vote = BoardVote(
            tenant_id=principal.tenant_id,
            submission_id=s.id,
            contact_id=account.contact_id,
            vote=body.vote,
            comment=body.comment,
            source="portal",
            recorded_by=None,
        )
        session.add(vote)
        await session.flush()
        await _protocol(
            session,
            s.ticket_id,
            principal.tenant_id,
            "board_vote",
            None,
            {
                "submission_id": str(s.id),
                "contact_id": str(account.contact_id),
                "vote": body.vote,
                "source": "portal",
            },
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ticket.board_vote",
            entity_type="ticket",
            entity_id=s.ticket_id,
            actor_user_id=None,
            payload={"submission_id": str(s.id), "vote": body.vote},
        )
        votes = (
            await session.scalars(select(BoardVote).where(BoardVote.submission_id == s.id))
        ).all()
        return _portal_out(s, list(votes), account.contact_id, today)
