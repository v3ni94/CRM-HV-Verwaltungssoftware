"""AI gateway tables (6.8, 9, 10): provider config, task runs, proposals, examples, import runs,
conversations. AI output is a proposal; nothing here writes domain data on its own."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

EUR = Numeric(14, 2)
RATE = Numeric(20, 8)


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = False, ondelete: str = "RESTRICT") -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


class AiProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class AiTask(StrEnum):
    EXTRACT_CONTACTS = "extract_contacts"
    EXTRACT_PROPERTY = "extract_property"
    MAP_COLUMNS = "map_columns"
    CLASSIFY_EMAIL = "classify_email"
    PROPOSE_POSTING = "propose_posting"
    EXTRACT_INVOICE = "extract_invoice"
    DRAFT_REPLY = "draft_reply"
    CHECK_STATEMENT = "check_statement"
    ANSWER_QUESTION = "answer_question"
    SUMMARIZE = "summarize"
    CLASSIFY_DOCUMENT = "classify_document"
    # Stammdatenänderung aus einer Ticket-Mail (Betreiberauftrag 26.09.2026): nur Vorschlag,
    # nie IBAN (rule 0.1.6); Entscheidung in mhvp.tickets.proposals.
    CONTACT_MASTER_DATA_CHANGE = "contact_master_data_change"
    # Gesprächsprotokoll der KI-Telefonassistenz (Hallo Heidi, 26.09.2026): Anrufer, Objekt,
    # Einheit, Anliegen; nur Vorschlag, Entscheidung in mhvp.tickets.call_assistant.
    CALL_SUMMARY = "call_summary"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"  # budget, missing release or configuration


class Decision(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    MODIFIED = "modified"
    REJECTED = "rejected"


class ImportStatus(StrEnum):
    APPLIED = "applied"
    UNDONE = "undone"
    PARTIALLY_UNDONE = "partially_undone"


class AiProviderConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    """Provider per tenant (6.8, 9.1). Usable only after a four eyes release with DPA evidence."""

    __tablename__ = "ai_provider_config"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider"),
        CheckConstraint("monthly_budget_eur >= 0", name="budget_positive"),
        CheckConstraint("(released_at IS NULL) = (released_by IS NULL)", name="release_complete"),
    )

    provider: Mapped[AiProvider] = mapped_column(_enum(AiProvider, "ai_provider"), nullable=False)
    api_key: Mapped[str | None] = mapped_column(EncryptedText())
    # Tier -> {"model", "input_eur_per_mtok", "output_eur_per_mtok"}, entered by the operator.
    models: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Task -> tier (9.3); unmapped tasks use "large".
    task_tiers: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    monthly_budget_eur: Mapped[Decimal] = mapped_column(EUR, nullable=False, default=Decimal(0))
    data_processing_agreement_signed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    dpa_document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    training_opt_out_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    endpoint_region: Mapped[str | None] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class AiConversation(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ai_conversation"

    context_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # global, property, contact
    context_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(200), nullable=False)


class AiTaskRun(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ai_task_run"
    __table_args__ = (Index("ix_ai_task_run_input_hash", "tenant_id", "task", "input_hash"),)

    task: Mapped[AiTask] = mapped_column(_enum(AiTask, "ai_task"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = _fk("ai_conversation.id", nullable=True)
    provider: Mapped[AiProvider | None] = mapped_column(_enum(AiProvider, "ai_provider"))
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_ref: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[Decimal | None] = mapped_column(RATE)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_eur: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal(0))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "ai_run_status"), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


class ImportRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """Entities created from a confirmed proposal (10.1 step 5); undo within 10.1 limits."""

    __tablename__ = "import_run"

    source: Mapped[str] = mapped_column(String(63), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        _enum(ImportStatus, "import_status"), nullable=False
    )
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    undone_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ImportRunItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "import_run_item"

    import_run_id: Mapped[uuid.UUID] = _fk("import_run.id", ondelete="CASCADE")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(63), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    undone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kept_reason: Mapped[str | None] = mapped_column(Text)


class AiProposal(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ai_proposal"

    task_run_id: Mapped[uuid.UUID] = _fk("ai_task_run.id")
    entity_type: Mapped[str] = mapped_column(String(63), nullable=False)
    context_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    proposed: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    decision: Mapped[Decision] = mapped_column(
        _enum(Decision, "ai_decision"), nullable=False, default=Decision.PENDING
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    import_run_id: Mapped[uuid.UUID | None] = _fk("import_run.id", nullable=True)


class AiExample(IdMixin, TimestampMixin, TenantMixin, Base):
    """Confirmed result per tenant and task, used as few-shot context (9.1)."""

    __tablename__ = "ai_example"

    task: Mapped[AiTask] = mapped_column(_enum(AiTask, "ai_task"), nullable=False, index=True)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    proposal_id: Mapped[uuid.UUID | None] = _fk("ai_proposal.id", nullable=True)


class AiMessage(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ai_message"

    conversation_id: Mapped[uuid.UUID] = _fk("ai_conversation.id", ondelete="CASCADE")
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    task_run_id: Mapped[uuid.UUID | None] = _fk("ai_task_run.id", nullable=True)
    proposal_id: Mapped[uuid.UUID | None] = _fk("ai_proposal.id", nullable=True)


class AiKnowledgeKind(StrEnum):
    FILING_RULE = "filing_rule"
    WORKFLOW = "workflow"
    CORRECTION = "correction"
    FACT = "fact"


class AiKnowledgeSource(StrEnum):
    MANUAL = "manual"
    LEARNED = "learned"


class AiKnowledgeEntry(IdMixin, TimestampMixin, TenantMixin, Base):
    """Knowledge base per tenant, optionally scoped to one property (Welle 3 item 14). Read only
    context handed to AI runs (mail preparation, chat); never written by AI on its own (rule
    0.1.6), only through a manual entry or a recorded correction (source ``learned``)."""

    __tablename__ = "ai_knowledge_entry"
    __table_args__ = (
        Index("ix_ai_knowledge_entry_tenant_property", "tenant_id", "property_id"),
        Index("ix_ai_knowledge_entry_tenant_kind", "tenant_id", "kind"),
    )

    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True, ondelete="CASCADE")
    kind: Mapped[AiKnowledgeKind] = mapped_column(
        _enum(AiKnowledgeKind, "ai_knowledge_kind"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[AiKnowledgeSource] = mapped_column(
        _enum(AiKnowledgeSource, "ai_knowledge_source"),
        nullable=False,
        default=AiKnowledgeSource.MANUAL,
        server_default=AiKnowledgeSource.MANUAL.value,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
