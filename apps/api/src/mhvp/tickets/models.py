"""Tickets and work orders (6.6, M19)."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class TicketStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    DONE = "done"
    CLOSED = "closed"
    REJECTED = "rejected"


class Priority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    IMMEDIATE = "immediate"


class TicketSource(StrEnum):
    MANUAL = "manual"
    EMAIL = "email"
    PORTAL = "portal"
    CHAT = "chat"
    PHONE = "phone"
    AI = "ai"
    FORM = "form"


class OrderStatus(StrEnum):
    DRAFT = "draft"
    REQUESTED = "requested"
    QUOTED = "quoted"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    INVOICED = "invoiced"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Team(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "team"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    member_user_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )


class TicketTemplate(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ticket_template"
    __table_args__ = (UniqueConstraint("tenant_id", "category"),)

    category: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    checklist: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    default_priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "ticket_priority"), nullable=False, default=Priority.NORMAL
    )
    default_team_id: Mapped[uuid.UUID | None] = _fk("team.id")
    default_assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    # Configurable extra fields the template demands on creation, e.g. an IBAN on a deposit
    # ticket: [{"key", "label", "kind": "text"|"iban", "required": bool}].
    required_fields: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )


class Ticket(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ticket"

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    property_id: Mapped[uuid.UUID | None] = _fk("property.id")
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id")
    template_id: Mapped[uuid.UUID | None] = _fk("ticket_template.id")
    category: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    public_description: Mapped[str | None] = mapped_column(Text)
    internal_description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(
        _enum(TicketStatus, "ticket_status"), nullable=False, default=TicketStatus.NEW
    )
    priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "ticket_priority"), nullable=False, default=Priority.NORMAL
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    team_id: Mapped[uuid.UUID | None] = _fk("team.id")
    initiator_contact_id: Mapped[uuid.UUID | None] = _fk("contact.id")
    parent_ticket_id: Mapped[uuid.UUID | None] = _fk("ticket.id")
    source: Mapped[TicketSource] = mapped_column(
        _enum(TicketSource, "ticket_source"), nullable=False, default=TicketSource.MANUAL
    )
    visible_for: Mapped[list[str]] = mapped_column(ARRAY(String(16)), nullable=False, default=list)
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_spent_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    merged_into_ticket_id: Mapped[uuid.UUID | None] = _fk("ticket.id")
    extra_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class TicketComment(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ticket_comment"

    ticket_id: Mapped[uuid.UUID] = _fk("ticket.id", nullable=False, ondelete="CASCADE")
    internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    author_contact_id: Mapped[uuid.UUID | None] = _fk("contact.id")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )


class TicketEvent(IdMixin, TenantMixin, Base):
    __tablename__ = "ticket_event"

    ticket_id: Mapped[uuid.UUID] = _fk("ticket.id", nullable=False, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class WorkOrder(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "work_order"

    ticket_id: Mapped[uuid.UUID | None] = _fk("ticket.id")
    property_id: Mapped[uuid.UUID] = _fk("property.id", nullable=False)
    provider_contact_id: Mapped[uuid.UUID] = _fk("contact.id", nullable=False)
    provider_relation_id: Mapped[uuid.UUID | None] = _fk("service_provider_relation.id")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    budget_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    requires_board_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[OrderStatus] = mapped_column(
        _enum(OrderStatus, "work_order_status"), nullable=False, default=OrderStatus.DRAFT
    )
    quote_document_id: Mapped[uuid.UUID | None] = _fk("document.id")
    quote_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_report: Mapped[str | None] = mapped_column(Text)
    photo_document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    invoice_id: Mapped[uuid.UUID | None] = _fk("invoice.id")
    rating: Mapped[int | None] = mapped_column(Integer)
    rating_comment: Mapped[str | None] = mapped_column(Text)


class WorkOrderEvent(IdMixin, TenantMixin, Base):
    __tablename__ = "work_order_event"

    work_order_id: Mapped[uuid.UUID] = _fk("work_order.id", nullable=False, ondelete="CASCADE")
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
