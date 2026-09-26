"""Documents, links, categories, retention profiles, DMS mirrors, templates (6.7, 6.9.5, 11)."""

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = False, ondelete: str = "RESTRICT") -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


class StorageKind(StrEnum):
    MINIO = "minio"  # S3 API object store (ADR 0005); name kept from 6.7
    PAPERLESS = "paperless"
    GOOGLE_DRIVE = "google_drive"


class DocumentSource(StrEnum):
    UPLOAD = "upload"
    GENERATED = "generated"
    EMAIL = "email"
    SCAN = "scan"
    PORTAL = "portal"
    IMPORT = "import"


class LinkRole(StrEnum):
    ATTACHMENT = "attachment"
    EVIDENCE = "evidence"
    ORIGINAL = "original"
    GENERATED = "generated"


class TextStatus(StrEnum):
    EXTRACTED = "extracted"  # text layer or plain text
    PENDING = "pending"  # needs OCR (Paperless or later pipeline)
    NONE = "none"  # no text expected (e.g. photos)


class RetentionStart(StrEnum):
    END_OF_YEAR_CREATED = "end_of_year_created"
    END_OF_YEAR_LAST_ENTRY = "end_of_year_last_entry"
    CONTRACT_END = "contract_end"
    STATEMENT_ISSUED = "statement_issued"


class MirrorStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"  # accepted by the DMS, id not yet known (Paperless consumer)
    DONE = "done"
    FAILED = "failed"


class DocumentCategory(IdMixin, TimestampMixin, TenantMixin, Base):
    """Category tree per tenant with mapping to Paperless document types and Drive folders."""

    __tablename__ = "document_category"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        Index(
            "uq_document_category_source",
            "tenant_id",
            "source_system",
            "source_id",
            unique=True,
            postgresql_where=sa_text("source_system IS NOT NULL AND source_id IS NOT NULL"),
        ),
    )

    parent_id: Mapped[uuid.UUID | None] = _fk("document_category.id", nullable=True)
    code: Mapped[str] = mapped_column(String(63), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    paperless_document_type: Mapped[str | None] = mapped_column(String(128))
    drive_folder: Mapped[str | None] = mapped_column(String(64))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # M35 Stufe 2: objektakte `documents_documentcategory` takeover key (docs/rules/M35-01.md
    # pattern reused for the category catalog, so a repeated import matches instead of
    # duplicating a category already created from an earlier run). Restored 25.09.2026 after a
    # concurrent edit reset this file to an older revision (see git history / other agents'
    # sessions); verify against migration 0060 if this looks wrong again.
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))


class RetentionProfile(IdMixin, TimestampMixin, TenantMixin, Base):
    """Retention per document class and legal entity kind (6.9.5, E05, S04, S05).

    No profile ships with values: the matrix is open (V17). Deletion needs a released profile.
    """

    __tablename__ = "retention_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_class", "legal_entity_kind"),
        CheckConstraint("retention_years > 0", name="years_positive"),
        CheckConstraint("(released_at IS NULL) = (released_by IS NULL)", name="release_complete"),
    )

    document_class: Mapped[str] = mapped_column(String(63), nullable=False)
    legal_entity_kind: Mapped[str | None] = mapped_column(String(32))
    legal_basis: Mapped[str] = mapped_column(Text, nullable=False)
    retention_years: Mapped[int] = mapped_column(Integer, nullable=False)
    start_rule: Mapped[RetentionStart] = mapped_column(
        _enum(RetentionStart, "retention_start"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Document(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "document"
    __table_args__ = (
        CheckConstraint("size >= 0", name="size_positive"),
        Index("ix_document_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "ix_document_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        Index("ix_document_tenant_sha256", "tenant_id", "sha256"),
        Index(
            "uq_document_source",
            "tenant_id",
            "source_system",
            "source_id",
            unique=True,
            postgresql_where=sa_text("source_system IS NOT NULL AND source_id IS NOT NULL"),
        ),
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage: Mapped[StorageKind] = mapped_column(
        _enum(StorageKind, "storage_kind"), nullable=False, default=StorageKind.MINIO
    )
    storage_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    category_id: Mapped[uuid.UUID | None] = _fk("document_category.id", nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text)
    text_status: Mapped[TextStatus] = mapped_column(
        _enum(TextStatus, "text_status"), nullable=False, default=TextStatus.NONE
    )
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('german', coalesce(title, '') || ' ' || coalesce(filename, '') "
            "|| ' ' || coalesce(ocr_text, ''))",
            persisted=True,
        ),
    )
    source: Mapped[DocumentSource] = mapped_column(
        _enum(DocumentSource, "document_source"), nullable=False
    )
    retention_profile_id: Mapped[uuid.UUID | None] = _fk("retention_profile.id", nullable=True)
    retention_until: Mapped[date | None] = mapped_column(Date)
    retention_hold_reason: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[list[str]] = mapped_column(ARRAY(String(16)), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))
    # M35 Stufe 2 (docs/plans/M35-objektakte-uebernahme.md section 4): a duplicate found by
    # objektakte's own pipeline (`Document.status == "duplicate"`), kept as a link rather than
    # dropped so the row stays traceable (rule 0.1.7).
    duplicate_of_id: Mapped[uuid.UUID | None] = _fk(
        "document.id", nullable=True, ondelete="SET NULL"
    )
    # Fields with no fitting CRM column (objektakte status, subfolder/type names, ocr_cache_key,
    # the row hash used for idempotent re-import) kept verbatim; never a legal/financial record
    # of its own, only import provenance. Restored 25.09.2026, see the note on
    # `DocumentCategory.source_system` above.
    source_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class DocumentLink(IdMixin, TimestampMixin, TenantMixin, Base):
    """Link of a document to any entity (6.7)."""

    __tablename__ = "document_link"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", "entity_type", "entity_id", "role"),
        Index("ix_document_link_entity", "tenant_id", "entity_type", "entity_id"),
    )

    document_id: Mapped[uuid.UUID] = _fk("document.id", ondelete="CASCADE")
    entity_type: Mapped[str] = mapped_column(String(63), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[LinkRole] = mapped_column(_enum(LinkRole, "link_role"), nullable=False)


class DmsConnection(IdMixin, TimestampMixin, TenantMixin, Base):
    """External DMS per tenant as mirror (11.1). Secrets are field encrypted."""

    __tablename__ = "dms_connection"
    __table_args__ = (UniqueConstraint("tenant_id", "kind"),)

    kind: Mapped[StorageKind] = mapped_column(_enum(StorageKind, "storage_kind"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    # Paperless: API token; Drive: OAuth client secret and refresh token as JSON.
    secret: Mapped[str | None] = mapped_column(EncryptedText())
    # Drive: root folder id, OAuth client id; Paperless: tag prefix.
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Paperless post-consume webhook (A30, 11.2/11.4): HMAC secret of this tenant, write only,
    # and the switch "Belegeingang aus Paperless automatisch" (M14-05, default off).
    webhook_secret: Mapped[str | None] = mapped_column(EncryptedText())
    auto_receipt_intake: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )


class DocumentMirror(IdMixin, TimestampMixin, TenantMixin, Base):
    """Copy of a document in an external DMS, processed by the mirror job."""

    __tablename__ = "document_mirror"
    __table_args__ = (UniqueConstraint("tenant_id", "document_id", "kind"),)

    document_id: Mapped[uuid.UUID] = _fk("document.id", ondelete="CASCADE")
    kind: Mapped[StorageKind] = mapped_column(_enum(StorageKind, "storage_kind"), nullable=False)
    status: Mapped[MirrorStatus] = mapped_column(
        _enum(MirrorStatus, "mirror_status"), nullable=False, default=MirrorStatus.PENDING
    )
    external_ref: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class DocumentTemplate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Letter template with placeholders; the letterhead comes from tenant settings."""

    __tablename__ = "document_template"
    __table_args__ = (UniqueConstraint("tenant_id", "code", "version"),)

    code: Mapped[str] = mapped_column(String(63), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID | None] = _fk("document_category.id", nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
