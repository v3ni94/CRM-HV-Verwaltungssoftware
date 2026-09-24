"""WEG: economic plan, resolutions, owners' meeting and statements (6.5, 6.9.3, 7.8, M24, M25)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.billing.status import StatementStatus
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


class PlanItem(IdMixin, TenantMixin, Base):
    __tablename__ = "economic_plan_item"

    plan_id: Mapped[uuid.UUID] = _fk("economic_plan.id", nullable=False, ondelete="CASCADE")
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    component: Mapped[str] = mapped_column(String(16), nullable=False)  # hoa_fee, reserve
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)  # annual
    allocation_key_id: Mapped[uuid.UUID] = _fk("allocation_key.id", nullable=False)
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id")


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


class HoaCostItem(IdMixin, TenantMixin, Base):
    __tablename__ = "hoa_cost_item"

    statement_id: Mapped[uuid.UUID] = _fk("hoa_statement.id", nullable=False, ondelete="CASCADE")
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    allocation_key_id: Mapped[uuid.UUID] = _fk("allocation_key.id", nullable=False)
    basis: Mapped[str] = mapped_column(Text, nullable=False)  # Gemeinschaftsordnung / Beschluss
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id")


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


class Attendance(IdMixin, TenantMixin, Base):
    __tablename__ = "meeting_attendance"

    meeting_id: Mapped[uuid.UUID] = _fk("owners_meeting.id", nullable=False, ondelete="CASCADE")
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)  # ownership = voting unit
    present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    proxy_contact_id: Mapped[uuid.UUID | None] = _fk("contact.id")
    proxy_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Vote(IdMixin, TenantMixin, Base):
    __tablename__ = "meeting_vote"

    agenda_item_id: Mapped[uuid.UUID] = _fk(
        "meeting_agenda_item.id", nullable=False, ondelete="CASCADE"
    )
    contract_id: Mapped[uuid.UUID] = _fk("contract.id", nullable=False)
    choice: Mapped[str] = mapped_column(String(8), nullable=False)  # yes, no, abstain
    excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # Stimmrechtsausschluss
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
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


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
