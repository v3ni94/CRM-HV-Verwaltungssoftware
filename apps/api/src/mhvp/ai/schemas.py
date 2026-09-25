"""API schemas for the AI gateway, conversations, proposals and import runs."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from mhvp.ai.models import (
    AiKnowledgeKind,
    AiKnowledgeSource,
    AiProvider,
    AiTask,
    Decision,
    ImportStatus,
    RunStatus,
)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class TierModel(_In):
    model: str = Field(min_length=1, max_length=100)
    input_eur_per_mtok: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    output_eur_per_mtok: Decimal = Field(ge=0, max_digits=20, decimal_places=8)


class ProviderIn(_In):
    api_key: str | None = Field(default=None, max_length=500, description="nur schreibbar")
    models: dict[Literal["small", "large", "embedding"], TierModel] = Field(default_factory=dict)
    task_tiers: dict[AiTask, Literal["small", "large"]] = Field(default_factory=dict)
    monthly_budget_eur: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    data_processing_agreement_signed: bool = False
    dpa_document_id: uuid.UUID | None = None
    training_opt_out_confirmed: bool = False
    endpoint_region: str | None = Field(default=None, max_length=32)
    enabled: bool = False


class ProviderOut(_Out):
    provider: AiProvider
    has_api_key: bool
    models: dict[str, Any]
    task_tiers: dict[str, str]
    monthly_budget_eur: Decimal
    data_processing_agreement_signed: bool
    dpa_document_id: uuid.UUID | None
    training_opt_out_confirmed: bool
    endpoint_region: str | None
    enabled: bool
    released_at: datetime | None
    released_by: uuid.UUID | None


RoutingStrategy = Literal[
    "anthropic_first", "openai_first", "alternate", "anthropic_only", "openai_only"
]


class RoutingIn(_In):
    strategy: RoutingStrategy


class RoutingOut(BaseModel):
    strategy: RoutingStrategy


class UsageOut(BaseModel):
    month: str
    spent_eur: Decimal
    budget_eur: Decimal
    warning: bool
    blocked: bool
    by_task: dict[str, Decimal]


class ConversationIn(_In):
    context_type: Literal["global", "property", "contact"] = "global"
    context_id: uuid.UUID | None = None
    title: str = Field(default="Assistent", min_length=1, max_length=200)


class MessageOut(_Out):
    id: uuid.UUID
    role: str
    content: str
    document_ids: list[uuid.UUID]
    task_run_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    created_at: datetime


class ConversationOut(_Out):
    id: uuid.UUID
    context_type: str
    context_id: uuid.UUID | None
    title: str
    created_by: uuid.UUID | None = None
    created_by_name: str | None = None
    created_at: datetime
    message_count: int = 0
    last_message_at: datetime | None = None
    messages: list[MessageOut] = Field(default_factory=list)


class MessageIn(_In):
    content: str = Field(min_length=1, max_length=10_000)
    task: Literal[
        "extract_contacts", "extract_property", "extract_invoice", "answer_question", "summarize"
    ]
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class RunOut(_Out):
    id: uuid.UUID
    task: AiTask
    status: RunStatus
    provider: AiProvider | None
    model: str | None
    prompt_version: str
    output: dict[str, Any] | None
    confidence: Decimal | None
    tokens_in: int
    tokens_out: int
    cost_eur: Decimal
    duration_ms: int
    error: str | None
    proposal_id: uuid.UUID | None = None
    # Providers skipped before the answering one (budget exhausted or provider error, M7-02).
    fallback: list[str] = Field(default_factory=list)
    # Character count per document that entered the run (debug: why a run was too large).
    input_stats: dict[str, int] = Field(default_factory=dict)
    # Current worker progress; updated per chunk (stage text plus i/n).
    progress: dict[str, Any] | None = None
    # Set when the "large" tier was chosen automatically because the input would not fit the
    # configured tier's context window ("Großes Modell wegen Umfang gewählt").
    model_tier_reason: str | None = None
    # Non fatal notices, e.g. a chunk that could not be processed or a row/result count mismatch.
    warnings: list[str] = Field(default_factory=list)


class ProposalOut(_Out):
    id: uuid.UUID
    task_run_id: uuid.UUID
    entity_type: str
    context_id: uuid.UUID | None
    proposed: dict[str, Any]
    decision: Decision
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    import_run_id: uuid.UUID | None


class ContactChoice(_In):
    index: int = Field(ge=0)
    action: Literal["create", "link", "skip"] = "create"
    contact_id: uuid.UUID | None = Field(default=None, description="bei link: vorhandener Kontakt")
    contact: dict[str, Any] | None = Field(
        default=None, description="geänderte Angaben (ContactIn)"
    )


class PropertyChoice(_In):
    number: str | None = Field(default=None, pattern=r"^[0-9]{3}$")
    name: str | None = Field(default=None, max_length=200)
    management_type: Literal["rental", "hoa", "hoa_with_sev"] | None = None
    as_of: date = Field(description="Gültig ab für Miteigentumsanteile")
    vat_percent_by_payment_type: dict[str, Decimal] = Field(
        default_factory=dict, description="bestätigter Steuersatz je Zahlungsart"
    )


class InvoiceApplyLineIn(_In):
    account_id: uuid.UUID
    net: Decimal
    vat_percent: Decimal = Decimal(0)
    vat: Decimal = Decimal(0)
    text: str | None = Field(default=None, max_length=500)


class InvoiceApplyIn(_In):
    """Every field is what the reviewer confirmed in the review form (rule 0.1.6, 0.1.7); the
    AI proposal is never applied by itself, only a human choice reusing it as a starting point."""

    ledger_id: uuid.UUID
    provider_contact_id: uuid.UUID
    number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None
    net: Decimal
    vat: Decimal
    gross: Decimal
    discount_percent: Decimal | None = Field(default=None, ge=0, le=100)
    discount_until: date | None = None
    payee_iban: str | None = Field(default=None, max_length=34)
    document_id: uuid.UUID | None = None
    order_reference: str | None = Field(default=None, max_length=100)
    currency: str = Field(default="EUR", max_length=3, description="nur EUR wird unterstützt")
    lines: list[InvoiceApplyLineIn] = Field(min_length=1, max_length=200)


class ApplyIn(_In):
    contacts: list[ContactChoice] | None = None
    property: PropertyChoice | None = None
    invoice: InvoiceApplyIn | None = None


class ImportItemOut(_Out):
    sequence: int
    entity_type: str
    entity_id: uuid.UUID
    undone: bool
    kept_reason: str | None


class ImportOut(_Out):
    id: uuid.UUID
    source: str
    status: ImportStatus
    summary: dict[str, Any]
    created_at: datetime
    undone_at: datetime | None
    items: list[ImportItemOut] = Field(default_factory=list)


# Knowledge base (Welle 3 item 14) --------------------------------------------------------


class KnowledgeEntryIn(_In):
    property_id: uuid.UUID | None = None
    kind: AiKnowledgeKind
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class KnowledgeEntryOut(_Out):
    id: uuid.UUID
    property_id: uuid.UUID | None
    kind: AiKnowledgeKind
    title: str
    content: str
    source: AiKnowledgeSource
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None


# Mail preparation (Welle 3 item 14) -------------------------------------------------------


class DocumentRef(_Out):
    document_id: uuid.UUID
    title: str
    source: str  # "dms" or "local"
    matched_keyword: str | None = None


class PreparationOut(_Out):
    message_id: uuid.UUID
    contact_id: uuid.UUID | None
    unit_id: uuid.UUID | None
    property_id: uuid.UUID | None
    role: str | None = Field(default=None, description="owner, tenant oder unbekannt")
    documents: list[DocumentRef] = Field(default_factory=list)
    draft: str | None = None
    confidence: Decimal | None = None
    reasons: list[str] = Field(default_factory=list)
    status: str  # ready, skipped, failed, none
    computed_at: datetime | None = None


class PreparationCorrectionIn(_In):
    contact_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    note: str = Field(min_length=1, description="Was war falsch, was ist richtig")
