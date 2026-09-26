"""Schwarzes Brett je Objekt (14, M21-01, A54): notices of the management with a validity
period and an audience (tenant, owner, all). Maintained in the CRM at the property, shown in the
portal to tenants and owners of that property only within the validity period and for the
matching audience (access matrix 6.9.6, D29 to D31)."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

AUDIENCES = ("tenant", "owner", "all")


class PropertyNotice(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "property_notice"
    __table_args__ = (Index("ix_property_notice_property", "tenant_id", "property_id"),)

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    audience: Mapped[str] = mapped_column(
        String(16), nullable=False, default="all", server_default="all"
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
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
    return notice.audience == "all" or notice.audience in roles
