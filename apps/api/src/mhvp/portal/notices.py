"""Schwarzes Brett je Objekt (14, M21-01, A54): notices of the management with a validity
period and an audience (tenant, owner, all). Maintained in the CRM at the property, shown in the
portal to tenants and owners of that property only within the validity period and for the
matching audience (access matrix 6.9.6, D29 to D31)."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

AUDIENCES = ("tenant", "owner", "provider")
# Legacy single value "all" of the first version means tenant and owner.
LEGACY_ALL = ("tenant", "owner")
NOTICE_TYPES = ("neutral", "info", "warning", "danger")


class PropertyNotice(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "property_notice"
    __table_args__ = (
        Index("ix_property_notice_property", "tenant_id", "property_id"),
        CheckConstraint("type IN ('neutral', 'info', 'warning', 'danger')", name="type"),
        CheckConstraint(
            "cardinality(audiences) >= 1 AND audiences <@ ARRAY['tenant', 'owner', 'provider']"
            "::varchar[]",
            name="audiences",
        ),
    )

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    # 6.2 notice_board_post: catalogue code (notice_category), level (type) and audiences list.
    category: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="neutral", server_default="neutral"
    )
    audiences: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)),
        nullable=False,
        default=list(LEGACY_ALL),
        server_default=text("'{tenant,owner}'"),
    )
    # Several attachments (document ids); served through the notice, checked on write.
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default=text("'{}'")
    )
    # Set by "Beenden": the notice leaves the portal immediately, the record stays traceable.
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


def is_current(notice: PropertyNotice, today: date) -> bool:
    """Visible in the portal: not ended and today within valid_from and valid_to."""
    if notice.ended_at is not None or notice.valid_from > today:
        return False
    return notice.valid_to is None or notice.valid_to >= today


def audience_matches(notice: PropertyNotice, roles: set[str]) -> bool:
    return any(a in roles for a in notice.audiences)


def legacy_audience(audiences: list[str]) -> str:
    """Single value view of the audiences for older clients: all, tenant, owner or custom."""
    s = set(audiences)
    if s == set(LEGACY_ALL):
        return "all"
    return audiences[0] if len(s) == 1 else "custom"


class NoticeBoardRead(IdMixin, TimestampMixin, TenantMixin, Base):
    """Read confirmation of a portal account for one notice (6.2 notice_board_read). An
    indication only: no delivery, no legally assessed receipt, starts no deadline."""

    __tablename__ = "notice_board_read"
    __table_args__ = (
        UniqueConstraint("notice_id", "account_id", name="uq_notice_board_read_notice_account"),
    )

    notice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_notice.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portal_account.id", ondelete="CASCADE"), nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
