"""Privacy tables (section 16, migration 0266).

* ``privacy_register_entry``: one register for processors, sub processors, responsibility
  roles and processing activities (S16-04, S711-10); basis of the generated draft of the
  Verarbeitungsverzeichnis. Content is an operator entry, never a legal finding (V13).
* ``privacy_deletion_profile``: retention period per data type outside documents (S16-05).
  Unreleased profiles never allow a deletion (rule 0.1.3).
  Migration 0388 (AE32, S711-10) adds the maintenance fields per activity (responsibility of
  GdWE, Verwalter and Betreiber, legal basis, processors used) and per provider (third country
  status, countries) plus ``source_key`` for entries taken over from the configuration
  (``mhvp.privacy.config_sources``). Every legal field starts open; nothing is preset.
* ``privacy_erasure_request``: request under Art. 17 GDPR for one contact with lock check and
  four eyes release (S711-08); execution anonymises, it never deletes booked content.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

REGISTER_KINDS = ("processor", "sub_processor", "processing_activity", "responsibility")
REGISTER_ROLES = ("verantwortlicher", "gdwe", "verwalter", "betreiber", "auftragsverarbeiter")
AVV_STATUSES = ("none", "requested", "confirmed", "not_required")
THIRD_COUNTRY_STATUSES = ("open", "no", "yes")
# Parties whose role is recorded per processing activity (S711-10) and the selectable roles.
# ``open`` is the default; the platform never fills in a role on its own.
RESPONSIBILITY_ACTORS = ("gdwe", "verwalter", "betreiber")
RESPONSIBILITY_ROLES = ("open", "controller", "joint_controller", "processor", "not_involved")
DATA_TYPES = ("contact", "portal_account", "communication", "ticket", "other")
ERASURE_STATUSES = ("requested", "approved", "rejected", "executed")


class PrivacyRegisterEntry(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "privacy_register_entry"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('processor', 'sub_processor', 'processing_activity', 'responsibility')",
            name="ck_privacy_register_entry_kind",
        ),
        CheckConstraint(
            "avv_status IN ('none', 'requested', 'confirmed', 'not_required')",
            name="ck_privacy_register_entry_avv_status",
        ),
        CheckConstraint(
            "legal_review_status IN ('open', 'reviewed')",
            name="ck_privacy_register_entry_review",
        ),
        Index("ix_privacy_register_entry_kind", "tenant_id", "kind"),
        CheckConstraint(
            "third_country_status IN ('open', 'no', 'yes')",
            name="third_country_status",
        ),
        Index(
            "uq_privacy_register_entry_source",
            "tenant_id",
            "source_key",
            unique=True,
            postgresql_where=text("source_key IS NOT NULL"),
        ),
    )

    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(24))
    purpose: Mapped[str | None] = mapped_column(Text)
    data_categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list, server_default=text("'{}'")
    )
    data_subjects: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, default=list, server_default=text("'{}'")
    )
    recipients: Mapped[str | None] = mapped_column(Text)
    third_country: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    third_country_note: Mapped[str | None] = mapped_column(Text)
    avv_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", server_default="none"
    )
    avv_confirmed_on: Mapped[date | None] = mapped_column(Date)
    avv_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document.id", ondelete="SET NULL")
    )
    retention_note: Mapped[str | None] = mapped_column(Text)
    legal_review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    legal_reviewed_on: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Migration 0388 (AE32). ``third_country`` stays as the derived flag (status ``yes``).
    third_country_status: Mapped[str] = mapped_column(
        String(8), nullable=False, default="open", server_default="open"
    )
    third_country_countries: Mapped[str | None] = mapped_column(String(300))
    legal_basis: Mapped[str | None] = mapped_column(Text)
    responsibilities: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    responsibility_note: Mapped[str | None] = mapped_column(Text)
    processor_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default=text("'{}'")
    )
    source_key: Mapped[str | None] = mapped_column(String(64))
    source_detail: Mapped[str | None] = mapped_column(Text)


class PrivacyDeletionProfile(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "privacy_deletion_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "data_type", name="uq_privacy_deletion_profile_type"),
        CheckConstraint(
            "data_type IN ('contact', 'portal_account', 'communication', 'ticket', 'other', "
            "'domain_event', 'platform_user', 'bank_raw')",
            name="ck_privacy_deletion_profile_type",
        ),
        CheckConstraint("retention_months >= 0", name="ck_privacy_deletion_profile_months"),
    )

    data_type: Mapped[str] = mapped_column(String(24), nullable=False)
    retention_months: Mapped[int] = mapped_column(Integer, nullable=False)
    start_rule: Mapped[str] = mapped_column(String(200), nullable=False)
    basis_note: Mapped[str | None] = mapped_column(Text)
    released: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Migration 0445 (AJ12, GAI-501): the nightly job creates deletion *proposals* for this
    # data type (``mhvp.privacy.proposals``); default off, never deletes anything.
    auto_propose: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class PrivacyErasureRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "privacy_erasure_request"
    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'requested', 'approved', 'rejected', 'executed')",
            name="ck_privacy_erasure_request_status",
        ),
        Index("ix_privacy_erasure_request_contact", "tenant_id", "contact_id"),
    )

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requested", server_default="requested"
    )
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    blockers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(1000))
    executed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
