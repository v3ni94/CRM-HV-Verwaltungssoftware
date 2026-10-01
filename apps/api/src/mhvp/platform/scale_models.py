"""Scale monitoring tables of the platform (AE36, AC09-01, ADR 0021).

Platform tables without RLS (section 5.3): one settings row with the operator thresholds for the
partitioning triggers and one snapshot per calendar week. The thresholds are proposals of
ADR 0021 and not decided (docs/OPEN_QUESTIONS.md AC09-01); they only drive an alarm, nothing is
rebuilt, moved or deleted by them.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TimestampMixin

# Defaults = proposals of ADR 0021 section Auslöser (values are operator proposals, no rules).
DEFAULT_ROWS_THRESHOLD = 20_000_000
DEFAULT_SIZE_GB_THRESHOLD = 50
DEFAULT_P95_MS_THRESHOLD = 300
DEFAULT_P95_DEEP_MS_THRESHOLD = 1000
DEFAULT_P95_WEEKS = 3
DEFAULT_RESTORE_SECONDS_THRESHOLD = 4 * 3600
DEFAULT_TENANTS_REVIEW_THRESHOLD = 20


class PlatformScaleSetting(IdMixin, TimestampMixin, Base):
    """Thresholds of the partitioning triggers (exactly one row, created on first read)."""

    __tablename__ = "platform_scale_setting"
    __table_args__ = (
        CheckConstraint(
            "rows_threshold > 0 AND size_gb_threshold > 0 AND p95_ms_threshold > 0 "
            "AND p95_deep_ms_threshold > 0 AND p95_weeks BETWEEN 1 AND 52 "
            "AND restore_seconds_threshold > 0 AND tenants_review_threshold > 0",
            name="positive",
        ),
    )

    rows_threshold: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=DEFAULT_ROWS_THRESHOLD, server_default="20000000"
    )
    size_gb_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_SIZE_GB_THRESHOLD, server_default="50"
    )
    p95_ms_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_P95_MS_THRESHOLD, server_default="300"
    )
    p95_deep_ms_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_P95_DEEP_MS_THRESHOLD, server_default="1000"
    )
    p95_weeks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_P95_WEEKS, server_default="3"
    )
    restore_seconds_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_RESTORE_SECONDS_THRESHOLD, server_default="14400"
    )
    tenants_review_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_TENANTS_REVIEW_THRESHOLD, server_default="20"
    )
    # With the switch off the weekly job still measures, but sends no notification.
    alarm_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class PlatformScaleSnapshot(IdMixin, TimestampMixin, Base):
    """Weekly measurement (job ``mhvp.ops.scale_snapshot`` or manual), one row per ISO week."""

    __tablename__ = "platform_scale_snapshot"

    iso_week: Mapped[str] = mapped_column(String(8), nullable=False, unique=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tables: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    latency: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    restore_seconds: Mapped[int | None] = mapped_column(Integer)
    tenants_productive: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tenants_demo: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    triggers: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="job", server_default="job"
    )
