"""Per user workspace tables (M9): notifications, calendar entries and saved list filters."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


def _user_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )


class Notification(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_user_unread", "tenant_id", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CalendarEntry(IdMixin, TimestampMixin, TenantMixin, Base):
    """Manual appointments and, since migration 0151 (P1 AP7, spec 4.10), the appointments
    generated from date fields of the master data (calibration date, energy certificate,
    contract end, move in and out, maintenance, follow up, meeting, ticket deadline).

    Generated entries have no owner (``owner_user_id`` NULL), are shared and carry their
    source (``source_type``, ``source_id``) and ``category`` (a ``DEADLINE_KINDS`` value).
    The deadline job (``jobs.calendar_sync``) upserts them idempotently per (source_type,
    source_id, category) and deletes them when the source row or its date disappears. Manual
    entries keep ``source_type`` "manual" and ``category`` "appointment".
    """

    __tablename__ = "calendar_entry"
    __table_args__ = (
        Index("ix_calendar_entry_source", "tenant_id", "source_type", "source_id"),
        Index(
            "uq_calendar_entry_generated",
            "tenant_id",
            "source_type",
            "source_id",
            "category",
            unique=True,
            postgresql_where=text("owner_user_id IS NULL"),
        ),
    )

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="SET NULL")
    )
    # manual | contract | meter | building | maintenance_item | contact_note | owners_meeting |
    # ticket | ... (entity types of ``workspace.links``); the source row is the truth.
    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="manual", server_default=text("'manual'")
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # appointment (manual) or a deadline kind of ``jobs.DEADLINE_KINDS``.
    category: Mapped[str] = mapped_column(
        String(48), nullable=False, default="appointment", server_default=text("'appointment'")
    )
    # Reminder codes before the start (spec B.30): "0", "5min", "1h", "1d", "14d", "1m",
    # "3m", "6m"; the deadline job (``jobs.notify_reminders``) turns each code into one
    # notification when its offset is reached.
    reminders: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Codes already notified as "<code>@<occurrence date>" (migration 0157): idempotency of
    # the reminder notifications, per occurrence for recurring entries.
    reminders_sent: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # None or {"frequency": weekly|monthly|yearly, "interval": n, "until": "JJJJ-MM-TT"};
    # manual entries only, expanded on read (``jobs.expand_occurrences``), never persisted.
    recurrence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class CalendarEvent(IdMixin, TimestampMixin, TenantMixin, Base):
    """Link between a Google Calendar event and its CRM origin (M23-02 bidirectional sync).

    One row per event created or tracked from the CRM. ``etag`` is Google's event etag as of
    the last successful read or write; the read path compares it to the live event and marks
    the row stale (``is_stale``) instead of overwriting either side automatically (rule
    M23-05, "keine stillen externen Änderungen").
    """

    __tablename__ = "calendar_event"
    __table_args__ = (
        UniqueConstraint("tenant_id", "mailbox_id", "google_event_id"),
        Index("ix_calendar_event_source", "tenant_id", "source_type", "source_id"),
    )

    mailbox_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mailbox.id", ondelete="CASCADE"), nullable=False
    )
    google_event_id: Mapped[str] = mapped_column(String(512), nullable=False)
    # ticket | handover | manual
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(500))
    # [{"email": "...", "name": "..."}], never sent to Google until invite_confirmed_at is set.
    attendees: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    # draft (attendees not yet sent) | invited (sendUpdates=all was sent)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    invite_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    invite_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    etag: Mapped[str | None] = mapped_column(String(200))
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = _user_fk()


class SavedFilter(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "saved_filter"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "resource", "name"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class WorkspaceJobSettings(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant switches of the daily jobs (A40, A41): digest mail (default off, section 15.1)
    and the lead time of the deadline list. The lead time is a product setting with a
    documented default, not a legal deadline (rule M1-09, docs/plans/M9.md)."""

    __tablename__ = "workspace_job_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_workspace_job_settings_tenant"),)

    digest_mail_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    deadline_lead_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default=text("30")
    )


class DigestRun(IdMixin, TenantMixin, Base):
    """One row per tenant, user and local day: idempotency marker of ``tasks.digest`` (A40).
    Stores counts only; the content is the notification itself."""

    __tablename__ = "digest_run"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "digest_date", name="uq_digest_run_day"),
    )

    user_id: Mapped[uuid.UUID] = _user_fk()
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    mail_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_sent")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class ComplianceDeadline(IdMixin, TimestampMixin, TenantMixin, Base):
    """Deadline list of ``compliance.deadlines`` (A41): derived from contracts, meters, bank
    consents and document retention; the source row stays the single source of truth, this
    table is refreshed idempotently per (kind, source, date). Dates are orientation only and
    marked "zu prüfen" in the UI; the legal deadline calculation is open (M1-09)."""

    __tablename__ = "compliance_deadline"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "kind", "source_id", "due_on", name="uq_compliance_deadline_source"
        ),
        Index("ix_compliance_deadline_due", "tenant_id", "status", "due_on"),
    )

    # contract_end | contract_termination | meter_calibration | bank_consent |
    # document_retention_end | service_contract_notice
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reference: Mapped[str] = mapped_column(String(300), nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False)
    # open | done (done when the source no longer carries the date or it lies in the past)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeadlineType(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant catalogue of deadline types (rule WS-01, handbook gaps Verwalterwechsel,
    Mieterwechsel, Mieterhöhung): name, trigger, duration entered by the operator and the
    responsible role. The duration has no default and no legal claim; the UI labels every
    computed date "zu verifizieren". Three system types are seeded per tenant without a
    duration (``deadlines.SYSTEM_TYPES``)."""

    __tablename__ = "deadline_type"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_deadline_type_code"),)

    code: Mapped[str] = mapped_column(String(63), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # termination_received | handover_done | rent_increase_access | management_start |
    # management_end | contract_end | manual (``deadlines.TRIGGERS``)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_months: Mapped[int | None] = mapped_column(Integer)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    # Role code of the tenant (``role.code``) that is responsible by default; free text so a
    # renamed role does not break the type.
    responsible_role: Mapped[str | None] = mapped_column(String(63))
    # Where the operator took the duration from (contract clause, legal advice); shown with
    # the label "zu verifizieren".
    source_note: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class DeadlineEntry(IdMixin, TimestampMixin, TenantMixin, Base):
    """Deadline created by a user from a ticket, contract, unit, property or rent increase
    case with a deadline type and a responsible person (ES-10). The entry is the source row;
    the job mirrors it into ``compliance_deadline`` (kind ``custom_deadline``) and the
    calendar like every other dated field."""

    __tablename__ = "deadline_entry"
    __table_args__ = (
        Index("ix_deadline_entry_due", "tenant_id", "status", "due_on"),
        Index("ix_deadline_entry_source", "tenant_id", "source_type", "source_id"),
    )

    type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deadline_type.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    trigger_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    # True when ``due_on`` was computed from the type's duration, False when entered.
    due_computed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="SET NULL")
    )
    # ticket | contract | unit | property | rent_increase_case
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="SET NULL")
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    contract_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    # open | done
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PropertyChecklist(IdMixin, TimestampMixin, TenantMixin, Base):
    """Checklist started per property from a template (``deadlines.CHECKLIST_TEMPLATES``,
    today only ``manager_change`` from the handbook page Verwalterwechsel). ``items`` is a
    list of ``{code, label, done_at, done_by, done_by_name}``; ticking records date and user.
    One open checklist per property and kind (partial unique index)."""

    __tablename__ = "property_checklist"
    __table_args__ = (
        Index("ix_property_checklist_property", "tenant_id", "property_id"),
        Index(
            "uq_property_checklist_open",
            "tenant_id",
            "property_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # open | done
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    items: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    note: Mapped[str | None] = mapped_column(Text)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
