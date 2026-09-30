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
    PURPOSE_END = "purpose_end"  # portal and applicant data: after the purpose ended (M6-04)


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
    # M6-09 (migration 0266): Paperless tag that documents of this category receive.
    paperless_tag: Mapped[str | None] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # M35 Stufe 2: objektakte `documents_documentcategory` takeover key (docs/rules/M35-01.md
    # pattern reused for the category catalog, so a repeated import matches instead of
    # duplicating a category already created from an earlier run). Restored 25.09.2026 after a
    # concurrent edit reset this file to an older revision (see git history / other agents'
    # sessions); verify against migration 0060 if this looks wrong again.
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))
    # Retention matrix (M6-04, migration 0175): the profile that documents of this category
    # receive when they are stored or recategorised; None keeps the document unassigned.
    retention_profile_id: Mapped[uuid.UUID | None] = _fk("retention_profile.id", nullable=True)


class RetentionProfile(IdMixin, TimestampMixin, TenantMixin, Base):
    """Retention per document class and legal entity kind (6.9.5, E05, S04, S05).

    A profile is a draft until ``released_at`` is set; deletion needs a released profile. The
    standard profiles of the operator decision M6-04 (26.09.2026) are seeded per tenant as
    drafts with ``review_note`` "Entwurf, Prüfung Steuerberatung offen" (V17 stays open).
    ``permanent`` marks classes that are never deleted (WEG minutes and resolutions); the
    period is ``retention_years`` plus ``retention_months``.
    """

    __tablename__ = "retention_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_class", "legal_entity_kind"),
        CheckConstraint(
            "retention_years >= 0 AND retention_months >= 0 AND retention_months < 12",
            name="period_non_negative",
        ),
        CheckConstraint(
            "permanent OR retention_years > 0 OR retention_months > 0", name="period_defined"
        ),
        CheckConstraint("(released_at IS NULL) = (released_by IS NULL)", name="release_complete"),
    )

    document_class: Mapped[str] = mapped_column(String(63), nullable=False)
    legal_entity_kind: Mapped[str | None] = mapped_column(String(32))
    legal_basis: Mapped[str] = mapped_column(Text, nullable=False)
    retention_years: Mapped[int] = mapped_column(Integer, nullable=False)
    retention_months: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    permanent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    start_rule: Mapped[RetentionStart] = mapped_column(
        _enum(RetentionStart, "retention_start"), nullable=False
    )
    review_note: Mapped[str | None] = mapped_column(String(200))
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
        Index("ix_document_tenant_created_at", "tenant_id", "created_at"),
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
    # Start of the period for rules that do not begin with the creation year (contract end,
    # last entry, statement issued, purpose end); without it the period cannot be computed
    # and the document stays locked (M6-04, migration 0175).
    retention_base_on: Mapped[date | None] = mapped_column(Date)
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
    # M6-06 (migration 0266): metadata changed in the index, the mirror job pushes it (update_meta).
    meta_dirty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )


class MirrorDeletionAction(StrEnum):
    DELETE = "delete"  # Google Drive: permanent delete, fallback trash
    TAG = "tag"  # Paperless: document kept, tag "gelöscht" assigned


class MirrorDeletionStatus(StrEnum):
    OPEN = "open"  # "offen": the mirror step has not succeeded yet
    DONE = "done"


class DocumentMirrorDeletion(IdMixin, TimestampMixin, TenantMixin, Base):
    """One mirror step of a platform deletion (A43, 6.9.5, operator decision 26.09.2026,
    M6-03). The document row is gone when the step runs, so ``document_id`` has no foreign
    key. The deletion of a document counts as "offen" until every step is ``done``."""

    __tablename__ = "document_mirror_deletion"
    __table_args__ = (
        UniqueConstraint("tenant_id", "document_id", "kind"),
        Index("ix_document_mirror_deletion_status", "tenant_id", "status"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[StorageKind] = mapped_column(_enum(StorageKind, "storage_kind"), nullable=False)
    action: Mapped[MirrorDeletionAction] = mapped_column(
        _enum(MirrorDeletionAction, "mirror_deletion_action"), nullable=False
    )
    external_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[MirrorDeletionStatus] = mapped_column(
        _enum(MirrorDeletionStatus, "mirror_deletion_status"),
        nullable=False,
        default=MirrorDeletionStatus.OPEN,
    )
    # deleted, trashed, already_gone (Drive); tagged, already_gone (Paperless)
    result: Mapped[str | None] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class DeletionProposalStatus(StrEnum):
    OPEN = "open"  # proposed, waiting for the four eyes approval
    APPROVED = "approved"  # approved, waiting for execution by a second person
    EXECUTED = "executed"
    REJECTED = "rejected"


class DeletionItemStatus(StrEnum):
    PROPOSED = "proposed"
    DELETED = "deleted"
    SKIPPED = "skipped"  # kept at execution time: hold, period not expired, profile changed


class DeletionProposal(IdMixin, TimestampMixin, TenantMixin, Base):
    """Monthly (or manually started) list of documents whose retention period expired
    (M6-04, 6.9.5, D46). Approval and execution are two separate persons; the items are the
    deletion log (hash, category, class, time, approver) and stay after the documents are gone."""

    __tablename__ = "deletion_proposal"
    __table_args__ = (
        Index("ix_deletion_proposal_tenant_id", "tenant_id"),
        Index("ix_deletion_proposal_status", "tenant_id", "status"),
    )

    status: Mapped[DeletionProposalStatus] = mapped_column(
        _enum(DeletionProposalStatus, "deletion_proposal_status"),
        nullable=False,
        default=DeletionProposalStatus.OPEN,
    )
    reference_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # None: job
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(500))


class DeletionProposalItem(IdMixin, TimestampMixin, TenantMixin, Base):
    """One document of a deletion proposal; no foreign key to ``document`` because the row is
    removed on execution and the item is the log entry that must survive it."""

    __tablename__ = "deletion_proposal_item"
    __table_args__ = (
        UniqueConstraint("tenant_id", "proposal_id", "document_id"),
        Index("ix_deletion_proposal_item_tenant_id", "tenant_id"),
        Index("ix_deletion_proposal_item_document", "tenant_id", "document_id"),
    )

    proposal_id: Mapped[uuid.UUID] = _fk("deletion_proposal.id", ondelete="CASCADE")
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    category_code: Mapped[str | None] = mapped_column(String(63))
    document_class: Mapped[str] = mapped_column(String(63), nullable=False)
    retention_until: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[DeletionItemStatus] = mapped_column(
        _enum(DeletionItemStatus, "deletion_item_status"),
        nullable=False,
        default=DeletionItemStatus.PROPOSED,
    )
    skip_reason: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    mirror_deletions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
