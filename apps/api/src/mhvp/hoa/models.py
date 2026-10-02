"""WEG: economic plan, resolutions, owners' meeting and statements (6.5, 6.9.3, 7.8, M24, M25)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.billing.status import StatementStatus
from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)
RATE = Numeric(20, 8)


def _fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


def _status() -> Any:
    return mapped_column(
        Enum(
            StatementStatus,
            name="statement_status",
            values_callable=lambda e: [m.value for m in e],
            create_type=False,
        ),
        nullable=False,
        default=StatementStatus.DRAFT,
    )


class Resolution(IdMixin, TimestampMixin, TenantMixin, Base):
    """Resolution of the owners (W06): basis, version reference, status with validity."""

    __tablename__ = "resolution"

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    agenda_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    decided_on: Mapped[date] = mapped_column(Date, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    wording: Mapped[str] = mapped_column(Text, nullable=False)
    # positive, negative, final (bestandskräftig), contested, annulled, legally_binding, void
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="meeting"
    )  # meeting, circular, court, external
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    subject_type: Mapped[str | None] = mapped_column(
        String(32)
    )  # economic_plan, hoa_statement, special_levy
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    votes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    majority_basis: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    # Beschlussgegenstand für die Mehrheitsprüfung (M25-01, migration 0125); the stored check is
    # a protocol note only and never changes the status.
    subject_kind: Mapped[str | None] = mapped_column(String(32))
    majority_check: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Umlaufbeschluss mit abgesenkter Mehrheit (M25-02, migration 0166): admitted majority
    # (unanimous, simple), the prior admitting resolution and the end of the voting period.
    allowed_majority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unanimous", server_default="unanimous"
    )
    enabling_resolution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("resolution.id", ondelete="RESTRICT")
    )
    vote_deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # GA03-03 (migration 0308): place of the decision, court notes (contest, annulment) and the
    # time of entry into the Beschluss-Sammlung as evidence of the prompt entry; the entry is
    # never deleted physically, status deleted or irrelevant is a note only.
    location: Mapped[str | None] = mapped_column(String(300))
    court_notes: Mapped[str | None] = mapped_column(Text)
    entered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


class EconomicPlan(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "economic_plan"

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[StatementStatus] = _status()
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = _fk("economic_plan.id")
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M24-04 (7.8 W02, migration 0256): master data of the plan and comparison basis.
    title: Mapped[str | None] = mapped_column(String(200))
    as_of_date: Mapped[date | None] = mapped_column(Date)
    basis_statement_id: Mapped[uuid.UUID | None] = _fk("hoa_statement.id")
    basis_plan_id: Mapped[uuid.UUID | None] = _fk("economic_plan.id")
    payment_rhythm: Mapped[str] = mapped_column(
        String(16), nullable=False, default="monthly", server_default="monthly"
    )
    due_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    continues_until_new_plan: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Obsolete marker: the shared statement_status enum has no value obsolete; a plan replaced
    # by a newer version or plan gets this timestamp instead (M24-04).
    obsolete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HoaReserve(IdMixin, TimestampMixin, TenantMixin, Base):
    """Earmarked reserve of a GdWE (7.8 W08, 6.5 reserve, M24-01, migration 0256)."""

    __tablename__ = "hoa_reserve"
    __table_args__ = (Index("ix_hoa_reserve_ledger", "tenant_id", "ledger_id"),)

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id")
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # M24-01 (migration 0294): bank investment of the reserve (account of the ledger's legal
    # entity) and the entered opening balance at the start of ``opening_year`` (takeover or
    # first year); later openings chain from the prior year's development.
    bank_account_id: Mapped[uuid.UUID | None] = _fk("property_bank_account.id", ondelete="SET NULL")
    opening_balance: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal(0), server_default=text("0")
    )
    opening_year: Mapped[int | None] = mapped_column(Integer)


class HoaReserveMovement(IdMixin, TenantMixin, Base):
    """Use of funds, taxes, fees and interest per reserve and statement year (W08, M24-01).
    Information for the reserve statement; entered by the manager with receipt or entry."""

    __tablename__ = "hoa_reserve_movement"
    __table_args__ = (Index("ix_hoa_reserve_movement_statement", "tenant_id", "statement_id"),)

    statement_id: Mapped[uuid.UUID] = _fk("hoa_statement.id", nullable=False, ondelete="CASCADE")
    reserve_id: Mapped[uuid.UUID] = _fk("hoa_reserve.id", nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # withdrawal, tax, fee, interest
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id")
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")


class PlanItem(IdMixin, TenantMixin, Base):
    __tablename__ = "economic_plan_item"

    plan_id: Mapped[uuid.UUID] = _fk("economic_plan.id", nullable=False, ondelete="CASCADE")
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    component: Mapped[str] = mapped_column(String(16), nullable=False)  # hoa_fee, reserve
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)  # annual
    allocation_key_id: Mapped[uuid.UUID] = _fk("allocation_key.id", nullable=False)
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id")
    # M24-04: basis of the planned amount (prior year cost or prior plan) for the deviation.
    basis_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    # M24-01: target reserve of a reserve component.
    reserve_id: Mapped[uuid.UUID | None] = _fk("hoa_reserve.id")


class HoaStatement(IdMixin, TimestampMixin, TenantMixin, Base):
    """Annual statement of a GdWE (W04 to W08, W11, W12). Result per unit against resolved
    advances; arrears separately; reserve development; asset report."""

    __tablename__ = "hoa_statement"

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[StatementStatus] = _status()
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = _fk("hoa_statement.id")
    reserve_opening: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    reserve_withdrawals: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    reserve_interest: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    addressing_rule_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="owner-at-resolution-v1"
    )
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    posted_entry_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # W04 (A60): explained differences of the cash flow reconciliation entered by the manager
    # [{code, amount, note}]; automatic explanations are computed, an unexplained rest blocks.
    reconciliation_notes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # M24-03: loans shown in the statement, entered by the manager with the legal basis
    # [{loan_id, allocation_key_id, components, basis, source}]; information only, the shares
    # never enter the result (open decision M24-03, migration 0171).
    loan_allocation: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # P02 (AE11, migration 0367): why this version corrects its predecessor.
    correction_reason: Mapped[str | None] = mapped_column(String(32))
    correction_basis: Mapped[str | None] = mapped_column(Text)
    correction_resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")


class HoaCostItem(IdMixin, TenantMixin, Base):
    __tablename__ = "hoa_cost_item"

    statement_id: Mapped[uuid.UUID] = _fk("hoa_statement.id", nullable=False, ondelete="CASCADE")
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    allocation_key_id: Mapped[uuid.UUID] = _fk("allocation_key.id", nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)  # Gemeinschaftsordnung / Beschluss
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id")
    # M24-02 (W12, PÜ07): posted entry and receipt behind the position (drilldown).
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id")
    document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    # M24-05: documented labour share for the § 35a EStG statement (information only).
    labour_cost_35a: Mapped[Decimal | None] = mapped_column(MONEY)
    # M24-06 (W03): structured source of the scope (resolution or document).
    basis_resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    basis_document_id: Mapped[uuid.UUID | None] = _fk("document.id")


class Meeting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Owners' meeting (M25): invitation, attendance, proxies, votes, minutes."""

    __tablename__ = "owners_meeting"

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="ordinary")
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="presence"
    )  # presence, hybrid, virtual
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str | None] = mapped_column(String(300))
    invited_at: Mapped[date | None] = mapped_column(Date)
    voting_principle: Mapped[str] = mapped_column(
        String(16), nullable=False, default="head"
    )  # head, mea, unit
    voting_principle_basis: Mapped[str | None] = mapped_column(Text)
    virtual_basis_resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="planned"
    )  # planned, invited, held, closed
    chair_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    minutes_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    # A62: generated draft of the minutes (PDF on the tenant letterhead); never replaces the
    # signed minutes linked in minutes_document_id.
    minutes_draft_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    # Resolution deadline of a virtual meeting (M9-07): entered with its source (resolution
    # or community rules with reference); never computed, shown in the deadline list (A41).
    resolution_deadline_at: Mapped[date | None] = mapped_column(Date)
    resolution_deadline_source: Mapped[str | None] = mapped_column(Text)
    # M25-03 / V13: validity end of the resolution that admits virtual meetings (entered from
    # the resolution wording, never computed), dial-in data of a hybrid or virtual meeting
    # (encrypted at rest, shown to owners of the community in the portal only) and the
    # short-notice record of the invitation (minutes note).
    virtual_basis_valid_until: Mapped[date | None] = mapped_column(Date)
    dial_in_url: Mapped[str | None] = mapped_column(EncryptedText())
    dial_in_access: Mapped[str | None] = mapped_column(EncryptedText())
    invitation_short_notice: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    invitation_short_notice_reason: Mapped[str | None] = mapped_column(Text)
    # R07-01: closing of the minutes with four eyes. The first person requests the closing
    # with the signed minutes document; a second person confirms (status closed). After the
    # closing, agenda, attendance, votes and announcements are locked (409).
    close_requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    close_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # GA03-01 (migration 0308): end of the meeting, reference to the original meeting of a
    # repeat or continuation meeting, templates of invitation, proxy and ballot, and the
    # public (owner portal) and internal description.
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin_meeting_id: Mapped[uuid.UUID | None] = _fk("owners_meeting.id", ondelete="RESTRICT")
    invitation_template_id: Mapped[uuid.UUID | None] = _fk(
        "document_template.id", ondelete="SET NULL"
    )
    proxy_template_id: Mapped[uuid.UUID | None] = _fk("document_template.id", ondelete="SET NULL")
    ballot_template_id: Mapped[uuid.UUID | None] = _fk("document_template.id", ondelete="SET NULL")
    public_description: Mapped[str | None] = mapped_column(Text)
    internal_description: Mapped[str | None] = mapped_column(Text)


class AgendaItem(IdMixin, TenantMixin, Base):
    __tablename__ = "meeting_agenda_item"

    meeting_id: Mapped[uuid.UUID] = _fk("owners_meeting.id", nullable=False, ondelete="CASCADE")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    proposal: Mapped[str | None] = mapped_column(Text)
    majority: Mapped[str] = mapped_column(
        String(32), nullable=False, default="simple"
    )  # simple, qualified, unanimous
    subject_type: Mapped[str | None] = mapped_column(String(32))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rule_id: Mapped[uuid.UUID | None] = _fk("majority_rule.id")
    # GA03-02 (migration 0308): result per item (accepted, rejected from the announcement;
    # deferred, no_vote recorded), minutes text and a voting principle that takes precedence
    # over the meeting's principle (with documented basis).
    result: Mapped[str | None] = mapped_column(String(16))
    minutes_text: Mapped[str | None] = mapped_column(Text)
    voting_principle: Mapped[str | None] = mapped_column(String(16))
    voting_principle_basis: Mapped[str | None] = mapped_column(Text)
    # AD06 / GA11-03 (migration 0351): online voting window of the item, opened and closed
    # by the manager in the CRM; portal votes are accepted only while it is open.
    voting_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voting_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attendance(IdMixin, TenantMixin, Base):
    __tablename__ = "meeting_attendance"

    meeting_id: Mapped[uuid.UUID] = _fk("owners_meeting.id", nullable=False, ondelete="CASCADE")
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)  # ownership = voting unit
    present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    proxy_contact_id: Mapped[uuid.UUID | None] = _fk("contact.id")
    proxy_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # AD06 (migration 0351): time the owner confirmed the online participation in the portal.
    portal_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Vote(IdMixin, TenantMixin, Base):
    __tablename__ = "meeting_vote"
    __table_args__ = (
        CheckConstraint(
            "cast_source IS NULL OR cast_source IN ('own', 'proxy')", name="cast_source"
        ),
        # AF08 (GAE-14, migration 0402): one counted vote per agenda item and unit; a second
        # vote of the other source goes to meeting_vote_conflict (AE31).
        Index(
            "uq_meeting_vote_item_contract",
            "tenant_id",
            "agenda_item_id",
            "contract_id",
            unique=True,
        ),
    )

    agenda_item_id: Mapped[uuid.UUID] = _fk(
        "meeting_agenda_item.id", nullable=False, ondelete="CASCADE"
    )
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    choice: Mapped[str] = mapped_column(String(8), nullable=False)  # yes, no, abstain
    excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # Stimmrechtsausschluss
    # GA03-04 (migration 0308): channel of the vote, set from the attendance (presence,
    # online) or circular for a meeting of kind circular_resolution.
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="presence", server_default="presence"
    )
    # AE31 (migration 0387): proxy (meeting_proxy) the vote was cast under in the portal; null
    # for the owner's own vote. ``cast_source`` (own, proxy) is the source of the vote for the
    # "proxy against own vote" rule; null on votes recorded before the migration (own).
    proxy_id: Mapped[uuid.UUID | None] = _fk("meeting_proxy.id", ondelete="SET NULL")
    cast_source: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class AuditEngagement(IdMixin, TimestampMixin, TenantMixin, Base):
    """Board audit (6.9.12, PÜ06 to PÜ09): scope, population, sample, snapshot reference."""

    __tablename__ = "audit_engagement"

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    statement_id: Mapped[uuid.UUID | None] = _fk("hoa_statement.id")
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    auditor_contact_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sampling: Mapped[str] = mapped_column(
        String(16), nullable=False, default="sample"
    )  # sample, full
    population: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # M25-08: proof of authority (board resolution or mandate) and the data cut-off date.
    authorization_text: Mapped[str | None] = mapped_column(Text)
    data_as_of: Mapped[date | None] = mapped_column(Date)


class AuditItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "audit_item"

    engagement_id: Mapped[uuid.UUID] = _fk(
        "audit_engagement.id", nullable=False, ondelete="CASCADE"
    )
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id")
    document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open"
    )  # open, checked, query, objection, outdated
    note: Mapped[str | None] = mapped_column(Text)
    question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    risk_note: Mapped[str | None] = mapped_column(Text)  # M25-02
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AuditItemEvent(IdMixin, TenantMixin, Base):
    """Append-only history of an audit item (M25-05, PÜ08): one row per change with the
    old and new value of each changed field. Notes and answers are never overwritten
    without a trace."""

    __tablename__ = "audit_item_event"
    __table_args__ = (Index("ix_audit_item_event_item", "tenant_id", "item_id"),)

    item_id: Mapped[uuid.UUID] = _fk("audit_item.id", nullable=False, ondelete="CASCADE")
    item_version: Mapped[int] = mapped_column(Integer, nullable=False)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditReport(IdMixin, TenantMixin, Base):
    __tablename__ = "audit_report"

    engagement_id: Mapped[uuid.UUID] = _fk(
        "audit_engagement.id", nullable=False, ondelete="CASCADE"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    # M25-03 (PÜ09): optional confirmation of exactly this report version, set once.
    confirmed_by_name: Mapped[str | None] = mapped_column(String(200))
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_note: Mapped[str | None] = mapped_column(Text)


class SpecialLevy(IdMixin, TimestampMixin, TenantMixin, Base):
    """Special levy (W09): purpose, total, key, affected units, instalments, resolution binding.
    Funds stay earmarked; they are not free current HOA fees."""

    __tablename__ = "special_levy"

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    allocation_key_id: Mapped[uuid.UUID] = _fk("allocation_key.id", nullable=False)
    unit_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    first_due: Mapped[date] = mapped_column(Date, nullable=False)  # first day of a month
    instalments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id")  # use of funds
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    supersedes_id: Mapped[uuid.UUID | None] = _fk("special_levy.id")
    difference_due: Mapped[date | None] = mapped_column(Date)  # W09-01 amendment month
    change_reason: Mapped[str | None] = mapped_column(Text)


class MajorityRule(IdMixin, TimestampMixin, TenantMixin, Base):
    """Majority rule of one community for a subject (M25-01, decided 24.09.2026). The values
    come from the community's documents with their source; the system only evaluates them."""

    __tablename__ = "majority_rule"

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    principle: Mapped[str] = mapped_column(String(16), nullable=False)  # head, mea, unit
    share_of_votes_cast: Mapped[Decimal | None] = mapped_column(RATE)  # e.g. 0.5, 0.66666667
    strictly_greater: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_mea_share_of_all: Mapped[Decimal | None] = mapped_column(RATE)
    unanimous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)


# W10 (A59): loans, insurance claims and larger measures. None of these tables carries a balance
# of its own: amounts become financial facts only through the referenced journal entry.


class HoaMeasure(IdMixin, TimestampMixin, TenantMixin, Base):
    """Larger measure of a community (W10): resolution reference, cost frame, financing from
    reserve, special levy or loan. The kind (maintenance or structural change) is set from the
    facts and the legal basis named in `kind_basis`, never from an AI account proposal alone."""

    __tablename__ = "hoa_measure"

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(
        String(24), nullable=False, default="undecided"
    )  # maintenance, structural_change, undecided
    kind_basis: Mapped[str | None] = mapped_column(Text)  # facts and legal basis of the kind
    cost_frame: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="planned"
    )  # planned, resolved, in_progress, completed, cancelled
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id")
    note: Mapped[str | None] = mapped_column(Text)


class HoaLoan(IdMixin, TimestampMixin, TenantMixin, Base):
    """Loan of a community (W10): lender, principal, rate, term, instalment. Disbursement,
    repayment, interest and fees are separate items with a journal entry reference."""

    __tablename__ = "hoa_loan"

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    lender: Mapped[str] = mapped_column(String(200), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100))
    principal: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    interest_rate_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    term_months: Mapped[int | None] = mapped_column(Integer)
    instalment: Mapped[Decimal | None] = mapped_column(MONEY)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    measure_id: Mapped[uuid.UUID | None] = _fk("hoa_measure.id")
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id")  # loan account
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft"
    )  # draft, active, repaid, closed
    note: Mapped[str | None] = mapped_column(Text)


class HoaLoanItem(IdMixin, TenantMixin, Base):
    """Loan position (W10): disbursement, repayment, interest or fee, each with its own amount
    and the journal entry that carries it. Items without a posted entry are planned only."""

    __tablename__ = "hoa_loan_item"

    loan_id: Mapped[uuid.UUID] = _fk("hoa_loan.id", nullable=False, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class HoaMeasureFinancing(IdMixin, TenantMixin, Base):
    """Financing share of a measure: reserve, special levy, loan or other (W10)."""

    __tablename__ = "hoa_measure_financing"

    measure_id: Mapped[uuid.UUID] = _fk("hoa_measure.id", nullable=False, ondelete="CASCADE")
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    special_levy_id: Mapped[uuid.UUID | None] = _fk("special_levy.id")
    loan_id: Mapped[uuid.UUID | None] = _fk("hoa_loan.id")
    note: Mapped[str | None] = mapped_column(Text)


class HoaInsuranceClaim(IdMixin, TimestampMixin, TenantMixin, Base):
    """Insurance claim (W10): damage, insurer, claim number, deductible, benefit, recourse.
    Amounts are items with a journal entry reference; documents hang on DocumentLink with
    entity_type `hoa_insurance_claim`."""

    __tablename__ = "hoa_insurance_claim"

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    damage_date: Mapped[date] = mapped_column(Date, nullable=False)
    reported_on: Mapped[date | None] = mapped_column(Date)
    insurer: Mapped[str | None] = mapped_column(String(200))
    policy_reference: Mapped[str | None] = mapped_column(String(100))
    claim_number: Mapped[str | None] = mapped_column(String(100))
    deductible: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="reported"
    )  # reported, accepted, rejected, settled, closed
    regress_party: Mapped[str | None] = mapped_column(String(200))
    measure_id: Mapped[uuid.UUID | None] = _fk("hoa_measure.id")
    # A79: structured link to the resolution of the same community (migration 0128).
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    note: Mapped[str | None] = mapped_column(Text)


class HoaInsuranceClaimItem(IdMixin, TenantMixin, Base):
    """Claim position: damage cost, benefit, deductible, recourse or payment to one owner."""

    __tablename__ = "hoa_insurance_claim_item"

    claim_id: Mapped[uuid.UUID] = _fk("hoa_insurance_claim.id", nullable=False, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id")
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id")  # owner receiving a payment
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class HoaMajorityRule(IdMixin, TimestampMixin, TenantMixin, Base):
    """Majority rule per subject kind (M25-01, migration 0125): tenant default with optional
    override for one community (legal_entity_id). Values need a source and a functional release
    (approved_by); the system only evaluates them and never treats them as legal advice."""

    __tablename__ = "hoa_majority_rule"

    legal_entity_id: Mapped[uuid.UUID | None] = _fk("legal_entity.id")
    subject_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    majority_type: Mapped[str] = mapped_column(String(16), nullable=False)
    custom_numerator: Mapped[int | None] = mapped_column(Integer)
    custom_denominator: Mapped[int | None] = mapped_column(Integer)
    counting_basis: Mapped[str] = mapped_column(String(8), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# M24-02: asset report of a community per reporting date (W11, § 28 Abs. 4 WEG as estimate).


class HoaAssetReport(IdMixin, TimestampMixin, TenantMixin, Base):
    """Asset report of a GdWE as of a date: reserve (Soll, Ist, use), bank balances per
    account of the legal entity, receivables against owners, liabilities, loans and manual
    other community assets, reconciled against the ledger. Draft behind G4; the snapshot is
    recomputable and hashed, manual items are listed apart from the ledger figures."""

    __tablename__ = "hoa_asset_report"
    __table_args__ = (
        Index("ix_hoa_asset_report_tenant_id", "tenant_id"),
        Index("ix_hoa_asset_report_ledger_as_of", "ledger_id", "as_of"),
    )

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id", nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft"
    )  # draft, calculated, issued
    reserve_opening: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    reserve_withdrawals: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    reserve_interest: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    # [{label, amount, note}] other community assets without a ledger account (manual)
    manual_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class HoaAssetReportProvision(IdMixin, TimestampMixin, TenantMixin, Base):
    """Provision log of an issued asset report per owner (GA07-02, 7.8 W11): one row when an
    owner opens or downloads the report in the portal, per ownership contract of the owner.
    Indication of the retrieval only, no delivery and no legally assessed receipt."""

    __tablename__ = "hoa_asset_report_provision"
    __table_args__ = (
        Index("ix_hoa_asset_report_provision_report", "tenant_id", "report_id", "occurred_at"),
        CheckConstraint("kind IN ('opened', 'downloaded')", name="kind_values"),
    )

    report_id: Mapped[uuid.UUID] = _fk("hoa_asset_report.id", nullable=False)
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HoaAcquisitionRelease(IdMixin, TimestampMixin, TenantMixin, Base):
    """Four eyes release of a special acquisition in the statement year (GA07-03, 7.8 W07):
    inheritance, forced sale, gift, other acquisition or special succession liability block the
    statement package until a second person released it. Holds only a proposal for the
    allocation, never a legal rule (OPEN_QUESTIONS AA07-01)."""

    __tablename__ = "hoa_acquisition_release"
    __table_args__ = (
        Index("ix_hoa_acquisition_release_tenant_id", "tenant_id"),
        UniqueConstraint(
            "statement_id",
            "contract_id",
            name="uq_hoa_acquisition_release_statement_id_contract_id",
        ),
        CheckConstraint("released_by IS NULL OR released_by <> requested_by", name="four_eyes"),
    )

    statement_id: Mapped[uuid.UUID] = _fk("hoa_statement.id", nullable=False)
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    acquisition_kind: Mapped[str | None] = mapped_column(String(32))
    special_succession_liability: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    allocation_proposal: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_note: Mapped[str | None] = mapped_column(Text)
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_note: Mapped[str | None] = mapped_column(Text)


class HoaAcquisitionRule(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE10 / AA07-01 (migration 0366): per tenant allocation variant for the statement result
    on an owner change, per acquisition kind. No row means ``manual_release`` (the standing
    assumption M24-01 plus four eyes release). The legal rule per kind is open (P01)."""

    __tablename__ = "hoa_acquisition_rule"
    __table_args__ = (
        Index("ix_hoa_acquisition_rule_tenant_id", "tenant_id"),
        UniqueConstraint("tenant_id", "acquisition_kind", name="uq_hoa_acquisition_rule_kind"),
        CheckConstraint(
            "allocation_variant IN ('manual_release', 'by_due_date', 'by_resolution_date')",
            name="allocation_variant_values",
        ),
    )

    acquisition_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    allocation_variant: Mapped[str] = mapped_column(
        String(24), nullable=False, default="manual_release", server_default="manual_release"
    )
    source_note: Mapped[str | None] = mapped_column(Text)


class HoaOnlineMeetingSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """AD06 / GA11-03 (migration 0351): per tenant switch for the online meeting in the owner
    portal, default off. One row per tenant; no row means off."""

    __tablename__ = "hoa_online_meeting_setting"

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # AE31 (migration 0387, AD06-02/03): rule when a unit receives a vote of the owner and a
    # vote of the proxy holder. flag (default): the first vote stays counted, the second is
    # stored as a conflict for review, nothing is discarded; first_vote: the second is refused;
    # proxy_priority / own_priority: the preferred source replaces the other one (the replaced
    # vote stays in the conflict record).
    proxy_conflict_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="flag", server_default="flag"
    )
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint(
            "proxy_conflict_mode IN ('flag', 'first_vote', 'proxy_priority', 'own_priority')",
            name="proxy_conflict_mode",
        ),
    )


class MeetingProxy(IdMixin, TimestampMixin, TenantMixin, Base):
    """AD06 (migration 0351): proxy of an ownership unit granted in the owner portal to
    another owner of the same community or to the manager, with period, text form document
    (own portal upload) and revocation. Never deleted; a revocation sets revoked_at."""

    __tablename__ = "meeting_proxy"
    __table_args__ = (
        CheckConstraint("proxy_kind IN ('owner', 'manager')", name="kind"),
        CheckConstraint(
            "(proxy_kind = 'owner') = (proxy_contract_id IS NOT NULL)",
            name="target",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period"),
        Index("ix_meeting_proxy_grantor", "tenant_id", "grantor_contract_id"),
    )

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", nullable=False)
    grantor_contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    proxy_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    proxy_contract_id: Mapped[uuid.UUID | None] = _fk("contract.id")
    meeting_id: Mapped[uuid.UUID | None] = _fk("owners_meeting.id")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    document_id: Mapped[uuid.UUID] = _fk("document.id", nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class MeetingSpeakerRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    """AD06 (migration 0351): request to speak of an owner (portal), with time stamp, handled
    by the manager in the CRM (status open, done, withdrawn)."""

    __tablename__ = "meeting_speaker_request"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'done', 'withdrawn')", name="status"),
        Index("ix_meeting_speaker_request_meeting", "tenant_id", "meeting_id", "requested_at"),
    )

    meeting_id: Mapped[uuid.UUID] = _fk("owners_meeting.id", nullable=False, ondelete="CASCADE")
    agenda_item_id: Mapped[uuid.UUID | None] = _fk("meeting_agenda_item.id", ondelete="SET NULL")
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class MeetingVoteConflict(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE31 (migration 0387, AD06-02/03): second vote of a unit that was cast by the other
    source (owner against proxy holder). The first vote stays in ``meeting_vote``; the record
    keeps both choices so that no vote is lost. ``open`` is a review note for the meeting
    chair; the decision (keep_first, apply_second) is traceable here and never deletes a row.
    ``rule_second`` marks a replacement made by the tenant rule (proxy_priority or
    own_priority)."""

    __tablename__ = "meeting_vote_conflict"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved')", name="status"),
        CheckConstraint("first_source IN ('own', 'proxy')", name="first_source"),
        CheckConstraint("second_source IN ('own', 'proxy')", name="second_source"),
        CheckConstraint(
            "resolution IS NULL OR resolution IN ('keep_first', 'apply_second', 'rule_second')",
            name="resolution",
        ),
        Index("ix_meeting_vote_conflict_item", "tenant_id", "agenda_item_id"),
    )

    meeting_id: Mapped[uuid.UUID] = _fk("owners_meeting.id", nullable=False, ondelete="CASCADE")
    agenda_item_id: Mapped[uuid.UUID] = _fk(
        "meeting_agenda_item.id", nullable=False, ondelete="CASCADE"
    )
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    vote_id: Mapped[uuid.UUID] = _fk("meeting_vote.id", nullable=False, ondelete="CASCADE")
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    first_source: Mapped[str] = mapped_column(String(8), nullable=False)
    first_choice: Mapped[str] = mapped_column(String(8), nullable=False)
    second_source: Mapped[str] = mapped_column(String(8), nullable=False)
    second_choice: Mapped[str] = mapped_column(String(8), nullable=False)
    second_proxy_id: Mapped[uuid.UUID | None] = _fk("meeting_proxy.id", ondelete="SET NULL")
    second_channel: Mapped[str] = mapped_column(String(16), nullable=False)
    attempted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    resolution: Mapped[str | None] = mapped_column(String(16))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class HoaPlanChangeSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE09 (M24-08, P07-01, M12-L2, migration 0365): per tenant variant for the difference of
    months already posted when a plan takes effect within the year. ``notice`` (default)
    only shows the difference; ``due_now`` proposes it due in the month after the
    resolution; ``next_instalment`` proposes to settle it with the next instalment. No row
    means ``notice``. Nothing is posted by any variant."""

    __tablename__ = "hoa_plan_change_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint("mode IN ('notice', 'due_now', 'next_instalment')", name="mode"),
    )

    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="notice", server_default="notice"
    )


class HoaPlanDifference(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE09: draft of a difference (claim or credit) per unit, contract, component and
    posted month of a plan changed within the year. Draft until approved by a second person
    with gate G4; the approval posts nothing (posting is a later step behind G1)."""

    __tablename__ = "hoa_plan_difference"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "contract_id",
            "payment_type_code",
            "period_month",
            name="uq_hoa_plan_difference_month",
        ),
        CheckConstraint("mode IN ('due_now', 'next_instalment')", name="mode"),
        CheckConstraint("status IN ('draft', 'approved', 'rejected')", name="status"),
        Index("ix_hoa_plan_difference_plan", "tenant_id", "plan_id"),
    )

    plan_id: Mapped[uuid.UUID] = _fk("economic_plan.id", nullable=False, ondelete="CASCADE")
    unit_id: Mapped[uuid.UUID] = _fk("unit.id", nullable=False)
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    payment_type_code: Mapped[str] = mapped_column(String(63), nullable=False)
    period_month: Mapped[date] = mapped_column(Date, nullable=False)
    posted_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    new_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    difference: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    proposed_due: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HoaReservePlan(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE07 / M24-01 (migration 0363): planned contribution (Soll) of one reserve and year with
    economic plan and resolution reference. A resolved row is frozen; a change goes through a
    new row that supersedes it. The tax classification is a placeholder with release status
    (not released by default); the system decides no tax treatment."""

    __tablename__ = "hoa_reserve_plan"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'resolved', 'superseded')", name="status"),
        CheckConstraint(
            "tax_classification_status IN ('not_released', 'released')", name="tax_status"
        ),
        CheckConstraint("year BETWEEN 1990 AND 2100", name="year"),
        CheckConstraint("status = 'draft' OR resolution_id IS NOT NULL", name="resolution"),
        Index("ix_hoa_reserve_plan_reserve", "tenant_id", "reserve_id", "year"),
        Index(
            "uq_hoa_reserve_plan_resolved",
            "tenant_id",
            "reserve_id",
            "year",
            unique=True,
            postgresql_where=text("status = 'resolved'"),
        ),
    )

    reserve_id: Mapped[uuid.UUID] = _fk("hoa_reserve.id", nullable=False, ondelete="CASCADE")
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    economic_plan_id: Mapped[uuid.UUID | None] = _fk("economic_plan.id", ondelete="SET NULL")
    planned_contribution: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal(0), server_default=text("0")
    )
    resolution_id: Mapped[uuid.UUID | None] = _fk("resolution.id")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    tax_classification: Mapped[str | None] = mapped_column(String(64))
    tax_classification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="not_released", server_default="not_released"
    )
    note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HoaReservePolicy(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE07 / V01-01 (migration 0363): per tenant handling of opening balance changes after a
    calculated statement. No row means ``locked`` (product protection, current rule)."""

    __tablename__ = "hoa_reserve_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint("opening_lock_mode IN ('locked', 'logged', 'four_eyes')", name="mode"),
    )

    opening_lock_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="locked", server_default="locked"
    )


class HoaReserveOpeningChange(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE07 / V01-01 (migration 0363): logged or requested change of opening balance or opening
    year of a reserve after a calculated statement. Never deleted."""

    __tablename__ = "hoa_reserve_opening_change"
    __table_args__ = (
        CheckConstraint("status IN ('applied', 'pending', 'rejected')", name="status"),
        Index("ix_hoa_reserve_opening_change_reserve", "tenant_id", "reserve_id"),
    )

    reserve_id: Mapped[uuid.UUID] = _fk("hoa_reserve.id", nullable=False, ondelete="CASCADE")
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HoaCorrectionReportSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """AF08 / GAE-13 (AE11, P02, migration 0402): tenant switch for the correction report
    ``GET /hoa/statements/{id}/correction-report``. Default off (no row means off); display
    only, no posting, no claim, no dispatch."""

    __tablename__ = "hoa_correction_report_setting"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class HoaReservePaymentSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE08 / P07-02 (migration 0364): per tenant variant how reserve payments are shown per
    earmarked reserve. ``bound_only`` (default, no row means it): only payments on items bound
    to a reserve count. ``plan_ratio_proposal``: the unbound rest is split by the planned
    contributions as a proposal; nothing is posted, items stay unchanged (G4 stays closed)."""

    __tablename__ = "hoa_reserve_payment_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint("mode IN ('bound_only', 'plan_ratio_proposal')", name="mode"),
    )

    mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="bound_only", server_default="bound_only"
    )
