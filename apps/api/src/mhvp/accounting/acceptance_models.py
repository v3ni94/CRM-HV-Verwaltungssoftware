"""Register of independent expected results per annex D case (V16, AE01, migration 0357).

``acceptance_expected`` keeps versions of the expected result of a case: inputs, expected
values, source and calculation, entered as a draft by one person and released by a second
person holding ``acceptance:approve`` (annex D.3: an expected value is fixed before the
comparison and never adjusted to the actual result). A released version is never changed; a
new version supersedes it. ``acceptance_result`` records the acceptance outcome per released
version (append only). Neither table opens a gate or replaces a domain check (ADR 0003).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
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


class AcceptanceExpectedStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class AcceptanceOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class AcceptanceExpected(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "acceptance_expected"
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "version"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'rejected', 'superseded')",
            name="status",
        ),
        CheckConstraint(
            "approved_by_user_id IS NULL OR approved_by_user_id <> author_user_id",
            name="second_person",
        ),
        Index(
            "uq_acceptance_expected_one_approved",
            "tenant_id",
            "case_id",
            unique=True,
            postgresql_where=text("status = 'approved'"),
        ),
    )

    case_id: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expected: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    calculation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(12),
        nullable=False,
        default=AcceptanceExpectedStatus.DRAFT.value,
        server_default="draft",
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by_name: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class AcceptanceResult(IdMixin, TenantMixin, Base):
    __tablename__ = "acceptance_result"
    __table_args__ = (CheckConstraint("outcome IN ('passed', 'failed')", name="outcome"),)

    expected_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("acceptance_expected.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    software_version: Mapped[str] = mapped_column(String(40), nullable=False)
    commit_ref: Mapped[str | None] = mapped_column(String(64))
    actual: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_by_name: Mapped[str] = mapped_column(String(200), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
