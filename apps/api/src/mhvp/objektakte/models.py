"""M35 objektakte takeover, Stufe 1 (docs/plans/M35-objektakte-uebernahme.md section 4).

New tables for the takeover of the `objektakte` application (Django/MariaDB, ~26,000 documents
with Google Drive Sechs-Ordner-Struktur, review center, owner/tenant lists). This stage only
lays down the data model and migration scaffold; classification, review UI and letters are
Stufe 3/4 (out of scope here).

`DriveNode` mirrors `apps.drive.models.DriveNode` of objektakte: the persistent cache of a
property's Google Drive folder tree (six top level folders, owner/tenant subfolders, yearly
accounting folders). `DocumentReviewCase`/`DocumentReviewDecision` mirror the minimal fields of
`apps.review.models.ReviewCase`/`ReviewDecision` needed to carry over open review work as a
starting inventory; the review center itself (queues, bulk actions) is Stufe 3.

`ObjektakteAssignment` is a staging table for `parties.OwnerUnitAssignment` rows that the
importer could not map to an existing CRM contract-like model (M35 Stufe 1 note): tenant and
owner assignments alike land here, keyed by their objektakte source ids, until Stufe 2/3 decide
the target model.

IBAN handling (docs/rules/M35-01.md): only `iban_last4` and `iban_hash` are ever copied from
objektakte; `iban_encrypted` plaintext is never read, decrypted or stored by this importer. A
CRM re-encryption of the objektakte IBAN plaintext, if ever done, is a separate, explicitly
authorized migration step (section 3.1 of the plan), not part of Stufe 1.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.properties.models import ManagementType


def _enum_col(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = False, ondelete: str = "RESTRICT") -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


class DriveNodeKind(StrEnum):
    DATA_ROOT = "data_root"
    OBJECT_ROOT = "object_root"
    MAIN_FOLDER = "main_folder"
    SUBFOLDER = "subfolder"
    OWNER_FILE_FOLDER = "owner_file_folder"
    OWNER_FILE_SUBFOLDER = "owner_file_subfolder"
    TENANT_FILE_FOLDER = "tenant_file_folder"
    TENANT_FILE_SUBFOLDER = "tenant_file_subfolder"
    LIST_FILE = "list_file"
    YEAR_FOLDER = "year_folder"


class DriveNodeStatus(StrEnum):
    ACTIVE = "active"
    MISSING = "missing"
    TRASHED = "trashed"


class DriveListType(StrEnum):
    OWNER_LIST = "owner_list"
    TENANT_LIST = "tenant_list"


class DriveNode(IdMixin, TimestampMixin, TenantMixin, Base):
    """Google Drive folder/file tree per property (objektakte `drive_nodes`, D 5.1/5.2).

    `property_id` is nullable because objektakte also has drive roots with no matched object yet
    (the technical inbox, or a takeover source not yet linked); such nodes stay unassigned until
    a later stage links them.
    """

    __tablename__ = "objektakte_drive_node"
    __table_args__ = (
        UniqueConstraint("tenant_id", "drive_file_id"),
        Index(
            "ux_objektakte_drive_node_source",
            "tenant_id",
            "source_system",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
    )

    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True, ondelete="SET NULL")
    parent_node_id: Mapped[uuid.UUID | None] = _fk(
        "objektakte_drive_node.id", nullable=True, ondelete="SET NULL"
    )
    node_kind: Mapped[DriveNodeKind] = mapped_column(
        _enum_col(DriveNodeKind, "objektakte_drive_node_kind"), nullable=False
    )
    list_type: Mapped[DriveListType | None] = mapped_column(
        _enum_col(DriveListType, "objektakte_drive_list_type"), nullable=True
    )
    year: Mapped[int | None] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drive_file_id: Mapped[str] = mapped_column(String(128), nullable=False)
    drive_parent_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[DriveNodeStatus] = mapped_column(
        _enum_col(DriveNodeStatus, "objektakte_drive_node_status"),
        nullable=False,
        default=DriveNodeStatus.ACTIVE,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="objektakte")
    source_id: Mapped[str | None] = mapped_column(String(64))


class ReviewCaseStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class DocumentReviewCase(IdMixin, TimestampMixin, TenantMixin, Base):
    """Minimal mirror of objektakte `review_cases` (D 8.1): carries over the open review
    inventory as a starting point for the CRM review center (Stufe 3); this stage only stores
    the fields, no queue or bulk-decision logic yet."""

    __tablename__ = "objektakte_document_review_case"
    __table_args__ = (
        Index(
            "ux_objektakte_document_review_case_source",
            "tenant_id",
            "source_system",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
    )

    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True, ondelete="SET NULL")
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    candidates: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    proposed_action: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100)
    status: Mapped[ReviewCaseStatus] = mapped_column(
        _enum_col(ReviewCaseStatus, "objektakte_review_case_status"),
        nullable=False,
        default=ReviewCaseStatus.OPEN,
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="objektakte")
    source_id: Mapped[str | None] = mapped_column(String(64))


class DocumentReviewDecision(IdMixin, TimestampMixin, TenantMixin, Base):
    """Minimal mirror of objektakte `review_decisions` (D 8.1): before/after snapshot of a
    review decision, carried over read-only with the case."""

    __tablename__ = "objektakte_document_review_decision"
    __table_args__ = (
        Index(
            "ux_objektakte_document_review_decision_source",
            "tenant_id",
            "source_system",
            "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
    )

    review_case_id: Mapped[uuid.UUID] = _fk(
        "objektakte_document_review_case.id", ondelete="CASCADE"
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="objektakte")
    source_id: Mapped[str | None] = mapped_column(String(64))


class PartyAssignmentRole(StrEnum):
    OWNER = "owner"
    TENANT = "tenant"


class ObjektakteAssignment(IdMixin, TimestampMixin, TenantMixin, Base):
    """Staging table for objektakte `parties.OwnerUnitAssignment` rows (owner and tenant unit
    assignments alike) that the importer could not place on an existing CRM contract-like model
    (M35 Stufe 1 note in the plan, section 4). Kept by source ids so Stufe 2/3 can resolve them
    onto the eventual target model without re-parsing the dump."""

    __tablename__ = "objektakte_party_assignment"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_system", "source_id"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_from <= valid_to",
            name="objektakte_assignment_period",
        ),
    )

    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", nullable=True, ondelete="SET NULL")
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", nullable=True, ondelete="SET NULL")
    role: Mapped[PartyAssignmentRole] = mapped_column(
        _enum_col(PartyAssignmentRole, "objektakte_party_assignment_role"), nullable=False
    )
    valid_from: Mapped[Any] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Any] = mapped_column(Date, nullable=True)
    share: Mapped[Any] = mapped_column(Numeric(9, 6), nullable=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="objektakte")
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_unit_id: Mapped[str | None] = mapped_column(String(64))
    source_contact_id: Mapped[str | None] = mapped_column(String(64))


class ObjektakteDocumentClass(IdMixin, TimestampMixin, TenantMixin, Base):
    """Mirror of one objektakte `documents_document_types` row (Stufe 2, plan section 4 item 1).

    `mhvp.documents.models.DocumentCategory` is a flat per tenant catalog and cannot hold
    objektakte's extra `subfolder`/`document_type` levels, so this table keeps them as plain
    fields next to the resolved CRM category, keyed by the objektakte `document_type` id
    (`source_id`). The document importer looks a row's `document_type_id` (or, failing that,
    its `category_code`) up here to get the CRM `category_id` to file the document under.
    """

    __tablename__ = "objektakte_document_class"
    __table_args__ = (UniqueConstraint("tenant_id", "source_system", "source_id"),)

    category_id: Mapped[uuid.UUID | None] = _fk(
        "document_category.id", nullable=True, ondelete="SET NULL"
    )
    subfolder_source_id: Mapped[str | None] = mapped_column(String(64))
    subfolder_name: Mapped[str | None] = mapped_column(String(200))
    type_code: Mapped[str | None] = mapped_column(String(64))
    type_name: Mapped[str | None] = mapped_column(String(200))
    requires_period: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_tenant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="objektakte")
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)


class ClassificationPatternType(StrEnum):
    """M35 Stufe 3 (docs/plans/M35-objektakte-uebernahme.md section 4, rule stage): the four
    pattern kinds the task requires. Only `FILENAME_REGEX` and `TEXT_KEYWORD` have a matching
    seed from the objektakte reference rules (docs/rules/M35-02.md); `SENDER_DOMAIN` and
    `DRIVE_FOLDER` are supported by the schema and service but unseeded until a tenant, or a
    later stage, adds one."""

    FILENAME_REGEX = "filename_regex"
    TEXT_KEYWORD = "text_keyword"
    SENDER_DOMAIN = "sender_domain"
    DRIVE_FOLDER = "drive_folder"


class ObjektakteClassificationRule(IdMixin, TimestampMixin, TenantMixin, Base):
    """Stufe 1 of the three stage document classification (M35 Stufe 3, rule stage). A per
    tenant, priority ordered rule: a pattern of one of `ClassificationPatternType`, matched
    against the document's filename, extracted text, sender/domain (`source_meta`) or Drive
    folder path, with a target document class (`target_category_id`) and optional free-text
    `target_document_type` code (the objektakte subfolder/type level, `ObjektakteDocumentClass`
    is the takeover mirror, this table is the live rule catalog).

    `pattern_value` is always matched as a case-insensitive regular expression, including for
    `TEXT_KEYWORD`: the two objektakte reference rules this stage could seed one-to-one
    (docs/rules/M35-02.md) join several alternatives with `|`, so a plain literal-substring
    keyword would have silently dropped alternatives. A tenant adding a rule can still enter a
    single literal word, since every literal string is also a valid regex.
    """

    __tablename__ = "objektakte_classification_rule"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_system", "source_id"),
        Index("ix_objektakte_classification_rule_tenant_priority", "tenant_id", "priority"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    pattern_type: Mapped[ClassificationPatternType] = mapped_column(
        _enum_col(ClassificationPatternType, "objektakte_classification_pattern_type"),
        nullable=False,
    )
    pattern_value: Mapped[str] = mapped_column(String(1000), nullable=False)
    target_category_id: Mapped[uuid.UUID | None] = _fk(
        "document_category.id", nullable=True, ondelete="SET NULL"
    )
    target_document_type: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=100, server_default="100"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Confidence contributed by a match of this rule (0..1); the tenant threshold in
    # `TenantSettings.objektakte_classification["auto_apply_threshold"]` decides whether the
    # best candidate becomes a proposal or a review case (docs/rules/M35-02.md).
    confidence: Mapped[Any] = mapped_column(
        Numeric(4, 3), nullable=False, default=0.8, server_default="0.8"
    )
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))


class ObjektakteRequiredDocument(IdMixin, TimestampMixin, TenantMixin, Base):
    """M35 Stufe 3 part 4 (docs/plans/M35-objektakte-uebernahme.md section 4, completeness
    check): a per tenant required document set per management type, mirroring the CRM's own
    `mhvp.properties.models.ManagementType` (`rental`, `hoa`, `hoa_with_sev`) rather than
    inventing a parallel "weg"/"rental" vocabulary, so a property's `management_type` compares
    directly against `management_type` here without a translation table.

    `document_category_id` is the CRM category a property must have at least one filed
    document in; `mandatory` lets a tenant record an optional/informational class without it
    ever appearing as "missing" in the completeness check.
    """

    __tablename__ = "objektakte_required_document"
    __table_args__ = (UniqueConstraint("tenant_id", "management_type", "document_category_id"),)

    management_type: Mapped[ManagementType] = mapped_column(
        _enum_col(ManagementType, "management_type"), nullable=False
    )
    document_category_id: Mapped[uuid.UUID] = _fk(
        "document_category.id", nullable=False, ondelete="CASCADE"
    )
    mandatory: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class ObjektakteSyncStatus(StrEnum):
    NEVER = "never"
    OK = "ok"
    FAILED = "failed"


class ObjektakteSyncState(IdMixin, TimestampMixin, TenantMixin, Base):
    """M35 Stufe 5 (docs/plans/M35-objektakte-uebernahme.md section 4, paralleler Betrieb):
    the per tenant water mark and last report of the daily differential import.

    `enabled` is the tenant flag for the Celery beat job (`mhvp.objektakte.tasks`, default off,
    never a global override, ADR 0003); `dump_path` is the absolute path of the full mysqldump
    export that objektakte writes for this tenant (a `.sql` file on the worker file system, no
    URL: the CRM never connects to the objektakte database itself). `last_source_updated_at`
    is the largest source `updated_at` seen so far (the water mark): a run only considers rows
    at or after it, so an unchanged export changes nothing and a corrected row is picked up
    once. `last_report` is the last run's `ImportResult` plus the run meta data; `last_error`
    the message of a failed run (never the dump content).
    """

    __tablename__ = "objektakte_sync_state"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    dump_path: Mapped[str | None] = mapped_column(String(500))
    last_source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[ObjektakteSyncStatus] = mapped_column(
        _enum_col(ObjektakteSyncStatus, "objektakte_sync_status"),
        nullable=False,
        default=ObjektakteSyncStatus.NEVER,
        server_default="never",
    )
    last_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(String(1000))


class ObjektakteSourceDeletion(IdMixin, TimestampMixin, TenantMixin, Base):
    """A source row (table + objektakte id) that a complete export no longer contains although
    the CRM holds its takeover (M35 Stufe 5). The CRM row itself is never deleted (rule 0.1.7,
    retention): this marker records the deletion, and `resolved_at` is set when the source row
    reappears in a later export."""

    __tablename__ = "objektakte_source_deletion"
    __table_args__ = (UniqueConstraint("tenant_id", "source_table", "source_id"),)

    source_table: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ObjektakteAiCall(IdMixin, TimestampMixin, TenantMixin, Base):
    """M35 Stufe 4 (docs/plans/M35-objektakte-uebernahme.md section 4, docs/rules/M35-03.md):
    read-only mirror of one objektakte `ai_calls` row (`apps.ai.models.AiCall`), the protocol
    of the old application's external AI calls, kept for cost evaluation and as evidence of
    masking. Only ever written by the importer; new AI calls of the CRM run through `mhvp.ai`
    (`AiTaskRun`) and are never recorded here.

    As in objektakte, no prompt or answer text is stored: `prompt_hash`, `prompt_chars` and
    `masked_entities_count` are the masking evidence, `response_summary` the structured
    (already masked) result summary objektakte kept. `document_id`/`property_id` point at the
    taken over CRM rows when the importer could resolve them; the objektakte ids stay in
    `source_document_id`/`source_object_id` so an unresolved reference is not lost.
    """

    __tablename__ = "objektakte_ai_call"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_system", "source_id"),
        Index("ix_objektakte_ai_call_tenant_requested_at", "tenant_id", "requested_at"),
    )

    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True, ondelete="SET NULL")
    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True, ondelete="SET NULL")
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(255))
    region: Mapped[str | None] = mapped_column(String(40))
    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    prompt_chars: Mapped[int | None] = mapped_column(Integer)
    masked_entities_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_eur: Mapped[Any] = mapped_column(Numeric(12, 6), nullable=True)
    price_list_version: Mapped[str | None] = mapped_column(String(24))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    response_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, default="objektakte")
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(String(64))
    source_object_id: Mapped[str | None] = mapped_column(String(64))
