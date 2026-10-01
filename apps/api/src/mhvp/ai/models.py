"""AI gateway tables (6.8, 9, 10): provider config, task runs, proposals, examples, import runs,
conversations. AI output is a proposal; nothing here writes domain data on its own."""

import uuid
from datetime import date, datetime
from decimal import Decimal
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
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.ai.vector import Vector
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
    # Erledigung eines Tickets (Betreiberauftrag 26.09.2026): nur Lernbeispiel (AiExample),
    # kein eigener KI-Lauf; Vorschläge in mhvp.communication.suggest lesen die Historie.
    TICKET_RESOLUTION = "ticket_resolution"
    # Gesprächsprotokoll der KI-Telefonassistenz (Hallo Heidi, 26.09.2026): Anrufer, Objekt,
    # Einheit, Anliegen; nur Vorschlag, Entscheidung in mhvp.tickets.call_assistant.
    CALL_SUMMARY = "call_summary"
    # Einbettungen für die Ähnlichkeitssuche (M7-03, Betreiberentscheidung 26.09.2026): kein
    # Vorschlag, nur Vektoren je Mandant; Budgetzählung wie jeder andere Lauf.
    EMBED = "embed"
    # KI-Plausibilität eines Mieterhöhungsfalls (M26-01, 6.3 ai_check_id): nur Hinweise mit
    # Schweregrad, nie Freigabe, nie Rechtsprüfung; Ablauf in mhvp.ai.rent_increase_check.
    RENT_INCREASE_CHECK = "rent_increase_check"
    # Antwortentwurf zu einer Mail mit eigenem Anbieterschema (T12, 9.2 draft_reply, R09-02):
    # Tonfall, Platzhalter, Stil aus den Mandanten-Stilvorgaben; nur Vorschlag mit Freigabe
    # durch einen Menschen, nie Versand. ``draft_reply`` bleibt der Playbook-Entwurf.
    REPLY_DRAFT = "reply_draft"


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
    # Staff feedback on the answer ("helpful" / "unhelpful", audit 29.09.2026); propagated to
    # the knowledge entries the run used (input_ref["knowledge_ids"]).
    feedback: Mapped[str | None] = mapped_column(String(16))


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
    __table_args__ = (
        # Intake list and start page: pending proposals per entity type, newest first.
        Index(
            "ix_ai_proposal_tenant_entity_decision",
            "tenant_id",
            "entity_type",
            "decision",
            "created_at",
        ),
    )

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
    # M34 Nachtrag 27.09.2026 (9.4 Erklärbarkeit): reason recorded on reject, stored as a
    # learning example (ai_example) so the same mistake is less likely next time (ADR 0010).
    rejection_reason: Mapped[str | None] = mapped_column(Text)


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
    # Record links of a platform lookup answer (mhvp.ai.lookup): produced by the platform from
    # permission checked queries, never by the model; kept with the message for the audit.
    links: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )


class AiKnowledgeKind(StrEnum):
    FILING_RULE = "filing_rule"
    WORKFLOW = "workflow"
    CORRECTION = "correction"
    FACT = "fact"


class AiKnowledgeSource(StrEnum):
    MANUAL = "manual"
    LEARNED = "learned"


class AiKnowledgeStatus(StrEnum):
    """Release workflow (M34-01, Produktschutz): a knowledge entry moves draft -> in_review ->
    approved, or to withdrawn from any state. Only ``approved`` feeds AI runs."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    WITHDRAWN = "withdrawn"


class AiKnowledgeEntry(IdMixin, TimestampMixin, TenantMixin, Base):
    """Knowledge base per tenant, optionally scoped to one property (Welle 3 item 14). Read only
    context handed to AI runs (mail preparation, chat); never written by AI on its own (rule
    0.1.6), only through a manual entry or a recorded correction (source ``learned``).

    M34-01 release workflow: every change to an approved or in-review entry creates a new row
    (same ``group_id``, ``version`` + 1) instead of an in place edit; the previous row is marked
    ``superseded_at`` and stays readable (version history, diff). Release needs four eyes: the
    approver (``approved_by``) must differ from the author (``created_by``) of that version.
    Only ``status=approved``, not superseded, not withdrawn, not deleted and, if set, currently
    inside ``valid_from``/``valid_until`` feeds an AI run as context (``ai_knowledge_context``
    view/query in ``mhvp.communication.preparation``)."""

    __tablename__ = "ai_knowledge_entry"
    __table_args__ = (
        Index("ix_ai_knowledge_entry_tenant_property", "tenant_id", "property_id"),
        Index("ix_ai_knowledge_entry_tenant_kind", "tenant_id", "kind"),
        Index("ix_ai_knowledge_entry_group", "tenant_id", "group_id"),
        # Partial index on the rows the context query reads (mhvp.ai.knowledge), migration 0237.
        Index(
            "ix_ai_knowledge_entry_live_approved",
            "tenant_id",
            "property_id",
            postgresql_where=text(
                "status = 'approved' AND superseded_at IS NULL AND deleted_at IS NULL"
            ),
        ),
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
    status: Mapped[AiKnowledgeStatus] = mapped_column(
        _enum(AiKnowledgeStatus, "ai_knowledge_status"),
        nullable=False,
        default=AiKnowledgeStatus.DRAFT,
        server_default=AiKnowledgeStatus.DRAFT.value,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    source_document_id: Mapped[uuid.UUID | None] = _fk(
        "document.id", nullable=True, ondelete="SET NULL"
    )
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Reject (M34-01 Kleinbefund 27.09.2026): in_review -> draft with a reason, four eyes like
    # approve (the rejecter must not be the author of this version). Kept alongside
    # submitted_by/approved_by so the last review decision stays visible after the entry is
    # edited and resubmitted.
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Usage and feedback (audit 29.09.2026, mhvp.ai.knowledge): how often the entry entered a
    # run and how staff rated the answers it fed. Counters only, no automatic consequence.
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    helpful_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    unhelpful_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class EmbeddingSourceKind(StrEnum):
    DOCUMENT = "document"
    KNOWLEDGE_ENTRY = "knowledge_entry"
    AI_EXAMPLE = "ai_example"  # GA04-12: learning example, similarity based few-shot selection


EMBEDDING_DIMENSIONS = 1536  # OpenAI text-embedding-3-small (M7-03)


class AiEmbedding(IdMixin, TimestampMixin, TenantMixin, Base):
    """One embedded chunk of a document text or knowledge entry (9.1 RAG, M7-03). Holds no
    text: the masked chunk is sent to the provider and discarded; the source row keeps the
    content. ``content_hash`` is the hash of the whole masked source text, so a changed source
    is detected by comparing ``updated_at`` and re-embedded as a whole. No FK on ``source_id``
    (two source tables); orphans are removed by the index job."""

    __tablename__ = "ai_embedding"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_kind", "source_id", "chunk_index"),
        Index("ix_ai_embedding_tenant_source", "tenant_id", "source_kind", "source_id"),
        # ANN index for the cosine search (``<=>``), migration 0156 (created CONCURRENTLY).
        Index(
            "ix_ai_embedding_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    source_kind: Mapped[EmbeddingSourceKind] = mapped_column(
        _enum(EmbeddingSourceKind, "ai_embedding_source_kind"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)


class OnboardingMatchSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Per tenant thresholds of the person match in the property onboarding (10.2 step 4)."""

    __tablename__ = "onboarding_match_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_onboarding_match_setting_tenant"),
        CheckConstraint(
            "suggest_threshold > 0 AND link_threshold <= 1 AND link_threshold >= suggest_threshold",
            name="thresholds",
        ),
    )

    link_threshold: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("0.90"), server_default="0.90"
    )
    suggest_threshold: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("0.60"), server_default="0.60"
    )
