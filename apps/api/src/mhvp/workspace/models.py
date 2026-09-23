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


class SavedFilter(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "saved_filter"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "resource", "name"),)

    user_id: Mapped[uuid.UUID] = _user_fk()
    resource: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
