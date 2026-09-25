"""Per user workspace tables (M9): notifications, calendar entries and saved list filters."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
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
    """Manual appointments; derived dates (maintenance, contract ends) are computed on read."""

    __tablename__ = "calendar_entry"

    owner_user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date | None] = mapped_column(Date)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="SET NULL")
    )


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
