"""API schemas for the AI gateway, conversations, proposals and import runs."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mhvp.ai.models import (
    AiKnowledgeKind,
    AiKnowledgeSource,
    AiKnowledgeStatus,
    AiProvider,
    AiTask,
    Decision,
    ImportStatus,
    RunStatus,
)
from mhvp.contacts.models import ContactRoleCode
from mhvp.contacts.validation import InvalidValueError, normalise_iban


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class TierModel(_In):
    model: str = Field(min_length=1, max_length=100)
    input_eur_per_mtok: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    output_eur_per_mtok: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    # Output limit of the model as published by the provider (max_tokens of one call). Empty
    # means the platform default (gateway.DEFAULT_MAX_OUTPUT_TOKENS); never invented here.
    max_output_tokens: int | None = Field(default=None, ge=1, le=1_000_000)


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


class TierTestOut(BaseModel):
    """Result of one minimal call per configured tier (connection test, no release check)."""

    tier: Literal["small", "large"]
    model: str
    ok: bool
    duration_ms: int
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_eur: Decimal = Decimal(0)


class ProviderTestOut(BaseModel):
    provider: AiProvider
    tiers: list[TierTestOut]


RoutingStrategy = Literal[
    "anthropic_first", "openai_first", "alternate", "anthropic_only", "openai_only"
]


class RoutingIn(_In):
    strategy: RoutingStrategy


class RoutingOut(BaseModel):
    strategy: RoutingStrategy


class FastTableImportIn(_In):
    enabled: bool


class FastTableImportOut(BaseModel):
    enabled: bool


class AiAutomationIn(_In):
    """Tenant switches of the automatic AI runs (package R09); missing keys stay unchanged."""

    rent_increase_check: bool | None = None
    batch_mail_classification: bool | None = None


class AutomationOut(BaseModel):
    rent_increase_check: bool
    batch_mail_classification: bool
    provider_released: bool
    blocked_reason: str | None = None


class InvoiceIntakeAutoIn(_In):
    enabled: bool


class InvoiceIntakeAutoOut(BaseModel):
    enabled: bool


class PostingEnabledIn(_In):
    enabled: bool


class PostingEnabledOut(BaseModel):
    enabled: bool
    blocked_reason: str | None = None


class UsageOut(BaseModel):
    month: str
    spent_eur: Decimal
    budget_eur: Decimal
    warning: bool
    blocked: bool
    by_task: dict[str, Decimal]
    # M7-09 (9.1 Kosten, 9.3 Dashboard): runs and tokens per task in the same month.
    runs_by_task: dict[str, int] = Field(default_factory=dict)
    tokens_in_by_task: dict[str, int] = Field(default_factory=dict)
    tokens_out_by_task: dict[str, int] = Field(default_factory=dict)


class ConversationIn(_In):
    context_type: Literal["global", "property", "contact"] = "global"
    context_id: uuid.UUID | None = None
    title: str = Field(default="Assistent", min_length=1, max_length=200)


class ChatLink(BaseModel):
    """Record or page link of a platform lookup answer (mhvp.ai.lookup, rule AI-LOOKUP-01).
    Produced by the platform from permission checked queries, never by the model."""

    type: Literal[
        "contact",
        "property",
        "unit",
        "contract",
        "ticket",
        "page",
        "handbook",
        "calendar_entry",
        "deadline",
        "document",
        "resolution",
        "meeting",
        "rent_increase",
        "work_order",
        "bank_transaction",
        "open_items",
    ]
    id: str
    label: str
    href: str = Field(description="CRM path, e.g. /kontakte/{id}")
    detail: str = ""


class MessageOut(_Out):
    id: uuid.UUID
    role: str
    content: str
    document_ids: list[uuid.UUID]
    task_run_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    links: list[ChatLink] = Field(default_factory=list)
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
    # Page context of the CRM chat bubble (answer_question): the record open on the page, so
    # the lookup starts from it and the answer stays on it (rule AI-LOOKUP-01).
    context_entity_type: (
        Literal[
            "contact",
            "property",
            "hoa",
            "unit",
            "contract",
            "ticket",
            "handover",
            "mail",
            "document",
            "meeting",
            "rent_increase",
            "work_order",
            "calendar_entry",
            "invoice",
            "order",
            "ledger",
            "statement",
            "dunning_run",
            "import_run",
            "settings",
        ]
        | None
    ) = None
    context_entity_id: uuid.UUID | None = None
    page: str | None = Field(default=None, max_length=200, description="Seitenname im CRM")
    # Menu item and sub page open in the CRM (chat-suggestions.ts): select the area tools of
    # the lookup (``mhvp.ai.lookup_tools.AREA_MAP``) and reach the model as context.
    area: str | None = Field(default=None, max_length=40, pattern=r"^[a-z][a-zA-Z]*$")
    sub_area: str | None = Field(default=None, max_length=40, pattern=r"^[a-z][a-zA-Z0-9]*$")


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
    # The provider that answered (M7-02); differs from the preferred one after a fallback.
    provider_used: str | None = None
    # Character count per document that entered the run (debug: why a run was too large).
    input_stats: dict[str, int] = Field(default_factory=dict)
    # Current worker progress; updated per chunk (stage text plus i/n).
    progress: dict[str, Any] | None = None
    # Set when the "large" tier was chosen automatically because the input would not fit the
    # configured tier's context window ("Großes Modell wegen Umfang gewählt").
    model_tier_reason: str | None = None
    # Cascade small to large (9.3, M7-08): one entry per stage with its own tokens and cost.
    cascade: list[dict[str, Any]] = Field(default_factory=list)
    # Staff feedback on the answer ("helpful" / "unhelpful"), audit 29.09.2026.
    feedback: str | None = None
    # Knowledge entries that fed the answer (ids), for the proof and the feedback propagation.
    knowledge_ids: list[uuid.UUID] = Field(default_factory=list)
    # Non fatal notices, e.g. a chunk that could not be processed or a row/result count mismatch.
    warnings: list[str] = Field(default_factory=list)
    # answer_question: links of the platform lookup and the deterministic hit list text (the
    # answer without AI when no provider is released or the budget is exhausted).
    links: list[ChatLink] = Field(default_factory=list)
    lookup_answer: str | None = None


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
    rejection_reason: str | None


class RejectProposalIn(_In):
    """POST /ai/proposals/{id}/reject (M34 Nachtrag 27.09.2026, 9.4 Erklärbarkeit)."""

    reason: str | None = Field(default=None, max_length=2000)


class ContactChoice(_In):
    index: int = Field(ge=0)
    action: Literal["create", "link", "skip"] = "create"
    contact_id: uuid.UUID | None = Field(default=None, description="bei link: vorhandener Kontakt")
    contact: dict[str, Any] | None = Field(
        default=None, description="geänderte Angaben (ContactIn)"
    )


class OnboardingBankAccountChoice(_In):
    """Bank account entered by the reviewer in the onboarding dialog (R03, M7-02); the AI
    proposal never carries bank data."""

    kind: Literal["rent", "hoa", "reserve", "deposit", "hoa_fee", "other"]
    iban: str = Field(min_length=15, max_length=40)
    bic: str | None = Field(default=None, pattern=r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
    bank_name: str | None = Field(default=None, max_length=200)
    holder: str = Field(min_length=2, max_length=200)
    is_default: bool = False
    valid_from: date | None = Field(default=None, description="ohne Angabe: Gültig ab des Objekts")

    @field_validator("iban")
    @classmethod
    def _iban(cls, value: str) -> str:
        try:
            return normalise_iban(value)
        except InvalidValueError as exc:
            raise ValueError(str(exc)) from None


class OnboardingAllocationKeyChoice(_In):
    """Allocation key of any kind with optional unit values (R03, M7-02). An existing code
    (copied template key, MEA) only receives values; a new code creates the key."""

    code: str = Field(pattern=r"^[A-Z0-9_]{1,32}$")
    name: str | None = Field(default=None, min_length=2, max_length=200)
    unit_of_measure: str | None = Field(default=None, min_length=1, max_length=16)
    kind: Literal["static", "consumption", "fixed_amount", "fixed_share"] | None = None
    meter_type_code: str | None = Field(default=None, max_length=63)
    expected_total: Decimal | None = Field(default=None, ge=0)
    values: dict[str, Decimal] = Field(
        default_factory=dict,
        max_length=2000,
        description="Wert je Einheitennummer; nicht für Verbrauchsschlüssel (Zähler)",
    )


class PropertyChoice(_In):
    number: str | None = Field(default=None, pattern=r"^[0-9]{3}$")
    name: str | None = Field(default=None, max_length=200)
    management_type: Literal["rental", "hoa", "hoa_with_sev"] | None = None
    as_of: date = Field(description="Gültig ab für Miteigentumsanteile")
    vat_percent_by_payment_type: dict[str, Decimal] = Field(
        default_factory=dict, description="bestätigter Steuersatz je Zahlungsart"
    )
    bank_accounts: list[OnboardingBankAccountChoice] = Field(default_factory=list, max_length=20)
    allocation_keys: list[OnboardingAllocationKeyChoice] = Field(
        default_factory=list, max_length=50
    )
    create_debtor_accounts: bool = Field(
        default=False,
        description=(
            "Debitorenkonten der Verträge ins Kontenbuch übernehmen; fehlt der Buchungskreis, "
            "wird er aus der Kontenvorlage (Entwurf) angelegt. Es wird nichts gebucht."
        ),
    )
    link_source_documents: bool = Field(
        default=True, description="Quelldokumente des Vorschlags mit dem Objekt verknüpfen"
    )
    document_ids: list[uuid.UUID] = Field(
        default_factory=list, max_length=100, description="weitere Dokumente (Ablage) zum Objekt"
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


class ChatActionApplyIn(_In):
    """Confirmation of a chat action proposal; the texts may be edited before confirming."""

    note: str | None = Field(default=None, max_length=20_000)
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    # calendar_create and deadline_create: the confirmer may correct date and time.
    entry_date: date | None = None
    entry_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    # property_create (M7-03): number and name may be corrected before confirming.
    property_number: str | None = Field(default=None, pattern=r"^[0-9]{3}$")
    property_name: str | None = Field(default=None, min_length=2, max_length=200)
    # letter_create (M7-03): another active template may be chosen before confirming.
    template_id: uuid.UUID | None = None


class ApplyIn(_In):
    contacts: list[ContactChoice] | None = None
    property: PropertyChoice | None = None
    invoice: InvoiceApplyIn | None = None
    chat_action: ChatActionApplyIn | None = None


class ApplyRoleIn(_In):
    role: ContactRoleCode = Field(description="Rolle, die allen angelegten Kontakten ergänzt wird")


class ApplyRoleOut(_Out):
    import_run_id: uuid.UUID
    role: ContactRoleCode
    contacts_changed: int


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
    valid_from: date | None = None
    valid_until: date | None = None
    source_document_id: uuid.UUID | None = None


class KnowledgeEntryOut(_Out):
    id: uuid.UUID
    property_id: uuid.UUID | None
    kind: AiKnowledgeKind
    title: str
    content: str
    source: AiKnowledgeSource
    status: AiKnowledgeStatus
    group_id: uuid.UUID
    version: int
    superseded_at: datetime | None
    valid_from: date | None
    valid_until: date | None
    source_document_id: uuid.UUID | None
    submitted_by: uuid.UUID | None
    submitted_at: datetime | None
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    withdrawn_by: uuid.UUID | None
    withdrawn_at: datetime | None
    rejected_by: uuid.UUID | None
    rejected_at: datetime | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None
    # Usage and feedback counters (audit 29.09.2026) and the stale hint (approved entry not
    # touched for ``knowledge.STALE_AFTER_DAYS``; no legal meaning).
    usage_count: int = 0
    last_used_at: datetime | None = None
    helpful_count: int = 0
    unhelpful_count: int = 0
    stale: bool = False


class FeedbackIn(_In):
    """POST /ai/runs/{id}/feedback, /ai/knowledge/{id}/feedback, /mail/playbooks/{id}/feedback."""

    helpful: bool


class KnowledgeRejectIn(_In):
    """POST /ai/knowledge/{id}/reject (M34-01 Kleinbefund 27.09.2026)."""

    reason: str = Field(min_length=1, max_length=2000)


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


class EmbeddingStatusOut(_Out):
    """Counters of the embedding index (M7-03): sources with text, embedded, pending per kind."""

    enabled: bool
    reason: str | None
    model: str | None
    documents_total: int
    documents_embedded: int
    documents_pending: int
    knowledge_total: int
    knowledge_embedded: int
    knowledge_pending: int
    chunks: int
    last_run_at: datetime | None
    last_run_status: str | None
    last_run_error: str | None
    last_run_report: dict[str, Any] | None
    queued: bool = False


class EmbeddingReindexIn(_In):
    # full: drop every stored vector of the tenant first (model change); otherwise only missing
    # or changed sources are embedded.
    full: bool = False
