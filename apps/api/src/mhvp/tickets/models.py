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
    Index,
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
    description: Mapped[str | None] = mapped_column(Text)
    # Checklist item shape: {"key": str, "label": str, "required": bool}. Extra field shape:
    # {"key": str, "label": str, "type": "text|iban|date|number|select", "required": bool,
    # "options": list[str] | None} (M19 ticket templates with checklists, 25.09.2026).
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    extra_fields: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    default_priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "ticket_priority"), nullable=False, default=Priority.NORMAL
    )
    # Thema der Vorlage (operator 25.09.2026): ein Code aus dem Kompetenzkatalog
    # (``mhvp.tickets.competences``). Steuert die Zusatz-Zuweisung nach Kompetenz.
    topic: Mapped[str | None] = mapped_column(String(32))
    default_team_id: Mapped[uuid.UUID | None] = _fk("team.id")
    default_assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class Ticket(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ticket"
    # Ticketnummer: mandantenweite fortlaufende Nummer (``mhvp.core.numbering``, Sequenz
    # ``ticket``), eindeutig je Mandant; Grundlage der Kennung ``TNR#<nummer>`` im Betreff
    # (``mhvp.tickets.tnr``, Migration 0119).
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_ticket_tenant_number"),
        # Listing by status (M4): ordered by number, and the assignee filter.
        Index("ix_ticket_status_number", "tenant_id", "status", "number"),
        Index("ix_ticket_assignee", "tenant_id", "assignee_user_id"),
    )

    number: Mapped[int] = mapped_column(Integer, nullable=False)
    property_id: Mapped[uuid.UUID | None] = _fk("property.id")
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id")
    # Kontakt-Link (operator 25.09.2026): Sichtbarkeit unter Kontakte/{id}; wird beim
    # Mail-Ingest aus dem Absender gesetzt, im Ticket änderbar. Bewusst getrennt vom
    # ``initiator_contact_id`` (der Ersteller bleibt unverändert, auch nach einer Korrektur).
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id")
    template_id: Mapped[uuid.UUID | None] = _fk("ticket_template.id")
    category: Mapped[str | None] = mapped_column(String(100))
    # Thema (operator 25.09.2026): Code aus dem Kompetenzkatalog, s. TicketTemplate.topic.
    topic: Mapped[str | None] = mapped_column(String(32))
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
    # Checklist item shape: {"key", "label", "required", "done", "done_by", "done_at"}.
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # Extra field values keyed by the template's field key, e.g. {"iban": "DE..."}.
    extra_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_spent_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    merged_into_ticket_id: Mapped[uuid.UUID | None] = _fk("ticket.id")
    # Erledigungsnotiz beim Abschluss (Betreiberauftrag 26.09.2026, mhvp.tickets.status):
    # Art aus ResolutionKind, Freitext, abschließender Nutzer.
    resolution_kind: Mapped[str | None] = mapped_column(String(32))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class TicketAssignee(IdMixin, TenantMixin, Base):
    """Additional assignee of a ticket (operator 25.09.2026, mail auto assignment M20): the
    primary assignee stays ``Ticket.assignee_user_id``; every user added here or as primary
    keeps the reason it was assigned for ("Anschrift", "Signatur", "Kompetenz <Thema>",
    "Verlauf", "manuell"), shown on the ticket. Never assigns the operator globally by
    default; a rule only ever names a concrete member."""

    __tablename__ = "ticket_assignee"
    __table_args__ = (UniqueConstraint("ticket_id", "user_id", name="uq_ticket_assignee"),)

    ticket_id: Mapped[uuid.UUID] = _fk("ticket.id", nullable=False, ondelete="CASCADE")
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class TicketComment(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ticket_comment"
    __table_args__ = (Index("ix_ticket_comment_ticket", "tenant_id", "ticket_id"),)

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
    __table_args__ = (Index("ix_ticket_event_ticket", "tenant_id", "ticket_id"),)

    ticket_id: Mapped[uuid.UUID] = _fk("ticket.id", nullable=False, ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class WorkOrder(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "work_order"
    __table_args__ = (Index("ix_work_order_ticket", "tenant_id", "ticket_id"),)

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


class ProposalStatus(StrEnum):
    """Status of an appointment proposal (A58): open until the resident accepts one; the
    others of the same round are declined, a new round supersedes the old one."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    SUPERSEDED = "superseded"


class WorkOrderAppointmentProposal(IdMixin, TimestampMixin, TenantMixin, Base):
    """Terminvorschlag eines Dienstleisters zum Arbeitsauftrag (14, M22, A58): up to three
    proposals per round, the affected resident (initiator of the ticket or occupant of the
    ticket's unit) accepts one in the portal, which sets ``WorkOrder.scheduled_at``. Never a
    contract or money relevant declaration; the management sees the confirmed appointment on
    the order."""

    __tablename__ = "work_order_appointment_proposal"
    __table_args__ = (
        Index("ix_work_order_appointment_proposal_order", "tenant_id", "work_order_id"),
    )

    work_order_id: Mapped[uuid.UUID] = _fk("work_order.id", nullable=False, ondelete="CASCADE")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ProposalStatus.PROPOSED.value,
        server_default=text("'proposed'"),
    )
    proposed_by_contact_id: Mapped[uuid.UUID | None] = _fk("contact.id")
    decided_by_contact_id: Mapped[uuid.UUID | None] = _fk("contact.id")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TicketReplyTemplate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Vorgefertigte Antwort für Tickets (operator 26.09.2026): Betreff und Text mit
    Platzhaltern (``mhvp.tickets.reply_templates.PLACEHOLDERS``), optionale Standardanhänge
    als Verweise auf Dokumente des Dokumentenmoduls und ein Thema aus dem Kompetenzkatalog.
    Der Versand läuft immer über den bestehenden Antwortweg des Tickets (Entwurf, Freigabe,
    Postfach des Tickets) und nur nach ausdrücklicher Bestätigung, nie automatisch."""

    __tablename__ = "ticket_reply_template"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_ticket_reply_template_name"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(32))
    attachment_document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default=text("'{}'")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
