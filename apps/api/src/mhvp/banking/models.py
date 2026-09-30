"""Bank connections, statements, transactions and sync runs (6.4, 6.9.7, 8).

Identity for re-import is the bank reference per account (6.9.7); the content hash only flags a
possible duplicate and never discards a transaction (D05). Counterpart IBANs are encrypted.
"""

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
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = False) -> Any:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target), nullable=nullable)


class Connector(StrEnum):
    EBICS = "ebics"
    AGGREGATOR_FINAPI = "aggregator_finapi"
    AGGREGATOR_GOCARDLESS = "aggregator_gocardless"
    FINTS = "fints"
    FILE_IMPORT = "file_import"


class ConnectionStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    ACTIVE = "active"
    ERROR = "error"
    CONSENT_EXPIRED = "consent_expired"
    DISABLED = "disabled"
    # finAPI (M11-finapi): a WebForm is open (created / web_form_pending), or a re-authorization
    # is required (update_required). "active" doubles as the connector agnostic "connected".
    WEB_FORM_PENDING = "web_form_pending"
    UPDATE_REQUIRED = "update_required"


class TransactionStatus(StrEnum):
    NEW = "new"
    NEEDS_REVIEW = "needs_review"  # possible duplicate without bank reference
    PROPOSED = "proposed"
    BOOKED = "booked"
    IGNORED = "ignored"
    SPLIT = "split"


class BankConnection(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "bank_connection"

    connector: Mapped[Connector] = mapped_column(_enum(Connector, "bank_connector"), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bic: Mapped[str | None] = mapped_column(String(11))
    credentials: Mapped[str | None] = mapped_column(EncryptedText())
    consent_valid_until: Mapped[date | None] = mapped_column(Date)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_schedule: Mapped[str] = mapped_column(String(32), nullable=False, default="daily_0600")
    status: Mapped[ConnectionStatus] = mapped_column(
        _enum(ConnectionStatus, "bank_connection_status"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)


class BankSyncRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """Protocol per run (8.2): new, duplicates, possible duplicates, errors."""

    __tablename__ = "bank_sync_run"

    connection_id: Mapped[uuid.UUID | None] = _fk("bank_connection.id", nullable=True)
    property_bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "property_bank_account.id", nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False, default=dict)
    errors: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class BankStatement(IdMixin, TimestampMixin, TenantMixin, Base):
    """Account statement with bank balances for reconciliation (B09)."""

    __tablename__ = "bank_statement"
    __table_args__ = (
        Index(
            "uq_bank_statement_ref",
            "tenant_id",
            "property_bank_account_id",
            "statement_ref",
            unique=True,
        ),
    )

    property_bank_account_id: Mapped[uuid.UUID] = _fk("property_bank_account.id")
    sync_run_id: Mapped[uuid.UUID | None] = _fk("bank_sync_run.id", nullable=True)
    statement_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    from_date: Mapped[date | None] = mapped_column(Date)
    to_date: Mapped[date | None] = mapped_column(Date)
    opening_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    closing_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    closing_date: Mapped[date | None] = mapped_column(Date)


class BankTransaction(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "bank_transaction"
    __table_args__ = (
        Index(
            "uq_bank_transaction_reference",
            "tenant_id",
            "property_bank_account_id",
            "bank_reference",
            unique=True,
            postgresql_where=text("bank_reference IS NOT NULL"),
        ),
        Index("ix_bank_transaction_hash", "tenant_id", "property_bank_account_id", "hash"),
    )

    property_bank_account_id: Mapped[uuid.UUID] = _fk("property_bank_account.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    statement_id: Mapped[uuid.UUID | None] = _fk("bank_statement.id", nullable=True)
    sync_run_id: Mapped[uuid.UUID | None] = _fk("bank_sync_run.id", nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(140))
    booking_date: Mapped[date] = mapped_column(Date, nullable=False)
    value_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)  # signed: credit > 0
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    counterpart_name: Mapped[str | None] = mapped_column(String(200))
    counterpart_iban: Mapped[str | None] = mapped_column(EncryptedText())
    counterpart_iban_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    counterpart_bic: Mapped[str | None] = mapped_column(String(11))
    purpose: Mapped[str | None] = mapped_column(Text)
    end_to_end_id: Mapped[str | None] = mapped_column(String(140))
    mandate_reference: Mapped[str | None] = mapped_column(String(140))
    creditor_id: Mapped[str | None] = mapped_column(String(64))
    transaction_code: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    possible_duplicate_of_id: Mapped[uuid.UUID | None] = _fk("bank_transaction.id", nullable=True)
    transfer_pair_id: Mapped[uuid.UUID | None] = _fk("bank_transaction.id", nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[TransactionStatus] = mapped_column(
        _enum(TransactionStatus, "bank_transaction_status"), nullable=False
    )
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    ai_proposal_id: Mapped[uuid.UUID | None] = _fk("ai_proposal.id", nullable=True)
    matched_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RuleState(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    ACTIVE = "active"
    DISABLED = "disabled"


class BankRule(IdMixin, TimestampMixin, TenantMixin, Base):
    """Controlled automation (6.9.4): only active rules may post; AI or learning only proposes."""

    __tablename__ = "bank_rule"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True)
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)
    # {counterpart_iban_fingerprint, name_contains, purpose_regex, amount_min, amount_max}
    match: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # {kind: debtor_payment|posting, account_id}
    action: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    learned_from_ai: Mapped[bool] = mapped_column(nullable=False, default=False)
    learned_from_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approval_state: Mapped[RuleState] = mapped_column(
        _enum(RuleState, "bank_rule_state"), nullable=False, default=RuleState.PROPOSED
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    test_evidence_document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    # Learned rules (plan M12 S5, migration 0241): the accepted proposal the rule was created
    # from, contradictions observed while active (reversal with reason code automation_error,
    # other account for the same key) and the learned rule that replaced this one
    # (``bank_rule.superseded``). A rule change is always a new row.
    learned_from_proposal_id: Mapped[uuid.UUID | None] = _fk("bank_rule_proposal.id", nullable=True)
    contradiction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class RuleProposalStatus(StrEnum):
    """Life cycle of a learned rule proposal (plan M12 3.3, S5)."""

    PROPOSED = "proposed"
    WITHDRAWN = "withdrawn"  # a contradiction ended the streak
    ACCEPTED = "accepted"  # a person created the BankRule (state proposed) from it
    REJECTED = "rejected"  # a person rejected it; proposed again at twice the evidence
    SUPERSEDED = "superseded"  # an equivalent rule already exists


class BankRuleProposal(IdMixin, TimestampMixin, TenantMixin, Base):
    """Rule proposal from repeated identical decisions of persons (ADR 0014, plan M12 S5).

    Pattern key per legal entity (B01): direction, counterparty (IBAN fingerprint or creditor
    id) and the account persons booked against. The row carries the evidence (decision ids,
    transactions, period, amount band, purpose tokens, persons) and the derived match. A
    proposal books nothing and activates nothing: acceptance creates a ``BankRule`` in state
    ``proposed`` that then walks the existing four eyes path (approve by another person,
    activate with amount cap and test evidence). Contains payer data (fingerprints, tokens),
    written only with ``learning_bookkeeper_enabled``."""

    __tablename__ = "bank_rule_proposal"
    __table_args__ = (
        Index(
            "uq_bank_rule_proposal_open",
            "tenant_id",
            "pattern_key",
            unique=True,
            postgresql_where=text("status = 'proposed'"),
        ),
        Index("ix_bank_rule_proposal_key", "tenant_id", "pattern_key"),
    )

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    pattern_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=RuleProposalStatus.PROPOSED.value,
        server_default="proposed",
    )
    direction: Mapped[str] = mapped_column(String(6), nullable=False)  # credit | debit
    case_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    counterpart_iban_fingerprint: Mapped[str | None] = mapped_column(String(64))
    creditor_id: Mapped[str | None] = mapped_column(String(64))
    account_number: Mapped[str] = mapped_column(String(6), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_min: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    amount_max: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    purpose_tokens: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    recurring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    evidence_count: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    rejected_evidence_count: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    reason: Mapped[str | None] = mapped_column(Text)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    anonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LevelRequestStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"


class BookkeepingLevelRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    """Raising the automation level of one case class (plan M12 3.4, S4), pattern
    ``release_gate_request``: requested by one person with the eligibility report as evidence,
    approved or rejected by another person (never a platform admin). Lowering a level needs
    no request. Approval writes ``tenant_settings.bookkeeping_automation`` and emits
    ``bookkeeping_level.changed``; nothing here opens a gate."""

    __tablename__ = "bookkeeping_level_request"
    __table_args__ = (
        Index("ix_bookkeeping_level_request_class", "tenant_id", "case_kind", "status"),
    )

    case_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    level_from: Mapped[str] = mapped_column(String(4), nullable=False)
    level_to: Mapped[str] = mapped_column(String(4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=LevelRequestStatus.REQUESTED.value,
        server_default="requested",
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)


class ReviewStatus(StrEnum):
    OPEN = "open"
    OK = "ok"
    CORRECTED = "corrected"
    CANCELLED = "cancelled"


class ReviewKind(StrEnum):
    DAILY = "daily"  # L2: every automatic posting, due next working day
    SAMPLE = "sample"  # L3: deterministic sample (debtor_full, transfer_pair only)
    RETURN = "return"  # a returned payment of an automatically posted transaction


class AutoPostingReview(IdMixin, TimestampMixin, TenantMixin, Base):
    """Review queue of automatic postings (7.4 no. 4, plan M12 S6): one item per automatic
    posting (L2 daily, L3 sample) or returned payment, due on a date; an overdue item blocks
    the class in the runner until a person with ``accounting:review`` closed it (ok, corrected
    by reversal plus new posting, cancelled by reversal only)."""

    __tablename__ = "auto_posting_review"
    __table_args__ = (
        Index("ix_auto_posting_review_open", "tenant_id", "status", "due_on"),
        Index("ix_auto_posting_review_decision", "tenant_id", "posting_decision_id"),
    )

    posting_decision_id: Mapped[uuid.UUID] = _fk("posting_decision.id")
    bank_transaction_id: Mapped[uuid.UUID] = _fk("bank_transaction.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    case_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(8), nullable=False, default=ReviewKind.DAILY.value, server_default="daily"
    )
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default=ReviewStatus.OPEN.value, server_default="open"
    )
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Kind ``return``: the returned payment (Rücklastschrift) that opened the item.
    return_transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ClarificationStatus(StrEnum):
    """Clarification status of an unposted bank movement (B05 evidence chain)."""

    OPEN = "open"
    IN_CLARIFICATION = "in_clarification"
    RECEIPT_REQUESTED = "receipt_requested"  # document asked for (migration 0248)
    NO_DOCUMENT_REQUIRED = "no_document_required"  # decided by a person with a reason
    RESOLVED = "resolved"  # document linked


CLARIFICATION_STATUSES = tuple(s.value for s in ClarificationStatus)


class BankClarification(IdMixin, TimestampMixin, TenantMixin, Base):
    """Evidence chain of an unposted bank movement (B05, rule M12-05): the runner opens a
    row when the deterministic verifier of ``recurring_expense`` finds neither a linked
    posted invoice nor a person's decision that no document is required; a person moves it
    to ``in_clarification``, closes it as ``no_document_required`` with a reason or as
    ``resolved`` with the document. A responsible ticket is created with the row. The list
    "Buchungen ohne Beleg" shows every open row of a ledger before the period lock; the
    audit export carries the rows. One row per transaction (unique)."""

    __tablename__ = "bank_clarification"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "bank_transaction_id", name="uq_bank_clarification_transaction"
        ),
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in CLARIFICATION_STATUSES)),
            name="ck_bank_clarification_status",
        ),
        Index("ix_bank_clarification_status", "tenant_id", "legal_entity_id", "status"),
    )

    bank_transaction_id: Mapped[uuid.UUID] = _fk("bank_transaction.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=ClarificationStatus.OPEN.value,
        server_default=text("'open'"),
    )
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ticket.id", ondelete="SET NULL"), nullable=True
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrderStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    EXPORTED = "exported"
    SUBMITTED = "submitted"
    ACCEPTED_BY_BANK = "accepted_by_bank"
    EXECUTED = "executed"
    PARTIALLY_EXECUTED = "partially_executed"
    REJECTED = "rejected"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class PaymentBatch(IdMixin, TimestampMixin, TenantMixin, Base):
    """pain.001 file of approved transfers of one bank account; export requires G2."""

    __tablename__ = "payment_batch"

    property_bank_account_id: Mapped[uuid.UUID] = _fk("property_bank_account.id")
    message_id: Mapped[str] = mapped_column(String(35), nullable=False, unique=True)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="exported")
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    submitted_via: Mapped[str | None] = mapped_column(String(16))
    bank_response: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    # M15-01: count and control sum of the file, checksum of the stored bytes, manual submission.
    transaction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    control_sum: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal(0), server_default="0"
    )
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    submission_channel: Mapped[str | None] = mapped_column(String(16))
    submission_reference: Mapped[str | None] = mapped_column(String(140))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PaymentOrder(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "payment_order"

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    property_bank_account_id: Mapped[uuid.UUID] = _fk("property_bank_account.id")
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="transfer")
    invoice_id: Mapped[uuid.UUID | None] = _fk("invoice.id", nullable=True)
    open_item_id: Mapped[uuid.UUID | None] = _fk("open_item.id", nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    discount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal(0))
    counterpart_name: Mapped[str] = mapped_column(String(140), nullable=False)
    counterpart_iban: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    counterpart_iban_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(140), nullable=False)
    end_to_end_id: Mapped[str] = mapped_column(String(35), nullable=False)
    execution_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        _enum(OrderStatus, "payment_order_status"), nullable=False, default=OrderStatus.DRAFT
    )
    executed_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    batch_id: Mapped[uuid.UUID | None] = _fk("payment_batch.id", nullable=True)
    bank_transaction_id: Mapped[uuid.UUID | None] = _fk("bank_transaction.id", nullable=True)
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    # M15-07: payout without invoice (owner payout, statement credit, deposit refund); the
    # payee IBAN comes from a released bank account of the contact.
    contact_bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "contact_bank_account.id", nullable=True
    )
    payout_reason: Mapped[str | None] = mapped_column(String(32))
    # M15-02: last ISO 20022 status reason code reported by the bank (pain.002, camt.054).
    bank_status_reason_code: Mapped[str | None] = mapped_column(String(8))


class PaymentApproval(IdMixin, TenantMixin, Base):
    """Approval bound to a snapshot of payment relevant fields (6.9.9)."""

    __tablename__ = "payment_approval"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_order.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentBankConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    """Format and submission channel agreed with the bank of one ordering account (M15-01).
    The versions are operator input confirmed with the bank; nothing here opens G2."""

    __tablename__ = "payment_bank_config"
    __table_args__ = (
        UniqueConstraint("property_bank_account_id", name="uq_payment_bank_config_account"),
    )

    property_bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_bank_account.id"), nullable=False
    )
    pain001_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pain.001.001.09", server_default="pain.001.001.09"
    )
    pain008_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pain.008.001.02", server_default="pain.008.001.02"
    )
    submission_channel: Mapped[str] = mapped_column(
        String(16), nullable=False, default="file", server_default="file"
    )
    confirmed_with_bank_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    # M15-04: limits agreed with the bank per ordering account (operator input, zu verifizieren).
    single_order_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    daily_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    # M15-06: submission lead days per sequence type and pre-notification days as agreed with
    # the bank and in the mandate; no legal default is derived (zu verifizieren).
    dd_lead_days_frst: Mapped[int | None] = mapped_column(Integer)
    dd_lead_days_rcur: Mapped[int | None] = mapped_column(Integer)
    pre_notification_days: Mapped[int | None] = mapped_column(Integer)


class PaymentFileDownload(IdMixin, TenantMixin, Base):
    """Every hand-out of a payment file (who, when, checksum); never deleted (M15-01)."""

    __tablename__ = "payment_file_download"
    __table_args__ = (Index("ix_payment_file_download_batch", "tenant_id", "batch_id"),)

    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_batch.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(32), nullable=False, default="download", server_default="download"
    )
    client_ip: Mapped[str | None] = mapped_column(String(64))


# --- finAPI (M11-finapi, read only) ----------------------------------------------------


class FinApiTenantConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    """Provider credentials of one tenant (docs/integrations/finapi.md). One row per tenant."""

    __tablename__ = "finapi_tenant_config"
    __table_args__ = (Index("uq_finapi_tenant_config_tenant", "tenant_id", unique=True),)

    client_id: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    client_secret: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    mandator_id: Mapped[str | None] = mapped_column(String(64))
    base_url: Mapped[str] = mapped_column(String(300), nullable=False)
    sandbox: Mapped[bool] = mapped_column(nullable=False, default=True)
    # M11-finapi Stage 2: scheduled daily fetch, per tenant, default off (operator decision
    # 25.09.2026). A manual click (POST .../fetch) is unaffected by this flag.
    auto_fetch_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)


class FinApiConnection(IdMixin, TimestampMixin, TenantMixin, Base):
    """finAPI specific state of one bank_connection (state machine, docs/integrations/finapi.md)."""

    __tablename__ = "finapi_connection"
    __table_args__ = (
        Index("uq_finapi_connection_bank_connection", "bank_connection_id", unique=True),
    )

    bank_connection_id: Mapped[uuid.UUID] = _fk("bank_connection.id")
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    finapi_user_id: Mapped[str | None] = mapped_column(EncryptedText())
    # finAPI user identity of this connection (technical user created via ``POST /users``,
    # auto update off). The password is a provider generated secret for the OAuth2 password
    # grant (user token), never a bank credential (rule M11-04). Encrypted like the client
    # credentials (migration 0141).
    finapi_user_password: Mapped[str | None] = mapped_column(EncryptedText())
    finapi_bank_connection_id: Mapped[str | None] = mapped_column(String(64))
    web_form_id: Mapped[str | None] = mapped_column(String(64))
    web_form_url: Mapped[str | None] = mapped_column(Text)
    web_form_status: Mapped[str | None] = mapped_column(String(32))
    last_update_task_id: Mapped[str | None] = mapped_column(String(64))
    last_update_status: Mapped[str | None] = mapped_column(String(32))
    auto_update_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    consent_valid_until: Mapped[date | None] = mapped_column(Date)
    last_error: Mapped[str | None] = mapped_column(Text)


class InvoiceMatchBasis(StrEnum):
    AMOUNT_AND_NUMBER = "amount_and_number"
    AMOUNT_AND_IBAN = "amount_and_iban"


class InvoiceBankTransactionLink(IdMixin, TimestampMixin, TenantMixin, Base):
    """Evidence that a bank transaction settles a payable invoice (M11-finapi Stage 3,
    section 4 of the operator's rebuild prompt). Never posts anything by itself: booking still
    goes through `mhvp.banking.matching.book_payment`/`mhvp.banking.payments.record_execution`
    (four-eyes/gate rules unchanged); this table only records the automatic *finding* so a
    person can review and book it (rule 0.1.6, AI/automation proposes, never posts alone)."""

    __tablename__ = "invoice_bank_transaction_link"
    __table_args__ = (
        Index(
            "uq_invoice_bank_transaction_link",
            "tenant_id",
            "invoice_id",
            "bank_transaction_id",
            unique=True,
        ),
    )

    invoice_id: Mapped[uuid.UUID] = _fk("invoice.id")
    bank_transaction_id: Mapped[uuid.UUID] = _fk("bank_transaction.id")
    match_basis: Mapped[InvoiceMatchBasis] = mapped_column(
        _enum(InvoiceMatchBasis, "invoice_match_basis"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)


class FinApiAccountLink(IdMixin, TimestampMixin, TenantMixin, Base):
    """External finAPI account reference linked to at most one internal bank account (6.9.7)."""

    __tablename__ = "finapi_account_link"
    __table_args__ = (
        Index(
            "uq_finapi_account_link_ref",
            "tenant_id",
            "finapi_connection_id",
            "finapi_account_id",
            unique=True,
        ),
    )

    finapi_connection_id: Mapped[uuid.UUID] = _fk("finapi_connection.id")
    finapi_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    property_bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "property_bank_account.id", nullable=True
    )
    iban_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    account_holder_name: Mapped[str | None] = mapped_column(String(200))
    account_type: Mapped[str | None] = mapped_column(String(64))
    account_name: Mapped[str | None] = mapped_column(String(200))
    balance_booked: Mapped[Decimal | None] = mapped_column(MONEY)
    balance_available: Mapped[Decimal | None] = mapped_column(MONEY)
    balance_currency: Mapped[str | None] = mapped_column(String(3))
    balance_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    balance_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_transactions_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Incremental sync cursor (migration 0141): booking date and provider transaction id of
    # the newest transaction imported so far. The next fetch asks from this date on (with an
    # overlap, see ``tasks._finapi_fetch_once``); dedup by ``bank_reference`` (D05) keeps the
    # overlap idempotent.
    last_synced_booking_date: Mapped[date | None] = mapped_column(Date)
    last_synced_transaction_id: Mapped[str | None] = mapped_column(String(64))


# --- Bank account selection (Bankkontenauswahl, read only plus assignment; G2 stays closed) ---


class AccountPurpose(StrEnum):
    """Purpose of a bank account within one property: Hausgeld (WEG), Miete (rental) or
    general. The default account per property is unique per purpose."""

    HAUSGELD = "hausgeld"
    MIETE = "miete"
    GENERAL = "general"


class BankAccountAssignment(IdMixin, TimestampMixin, TenantMixin, Base):
    """Selectable link between a bank account and a property or a legal entity.

    Exactly one of ``property_id`` / ``legal_entity_id`` is set:
    - property rows make the account selectable for that property (the account's home
      property from ``property_bank_account.property_id`` stays untouched) and may mark the
      default account per purpose (Hausgeld/Miete);
    - legal entity rows only mark the default account of that legal entity; the legal entity
      must be the account's owner (B01, 6.9.1), an account is never re-assigned to another
      legal entity here.
    Pure organisation: no money moves, no posting, no payment (G2).
    """

    __tablename__ = "bank_account_assignment"
    __table_args__ = (
        CheckConstraint(
            "(property_id IS NOT NULL) <> (legal_entity_id IS NOT NULL)",
            name="exactly_one_scope",
        ),
        Index(
            "uq_bank_account_assignment_property",
            "tenant_id",
            "property_bank_account_id",
            "property_id",
            unique=True,
            postgresql_where=text("property_id IS NOT NULL"),
        ),
        Index(
            "uq_bank_account_assignment_legal_entity",
            "tenant_id",
            "property_bank_account_id",
            "legal_entity_id",
            unique=True,
            postgresql_where=text("legal_entity_id IS NOT NULL"),
        ),
        Index(
            "uq_bank_account_assignment_property_default",
            "tenant_id",
            "property_id",
            "purpose",
            unique=True,
            postgresql_where=text("is_default AND property_id IS NOT NULL"),
        ),
        Index(
            "uq_bank_account_assignment_legal_entity_default",
            "tenant_id",
            "legal_entity_id",
            unique=True,
            postgresql_where=text("is_default AND legal_entity_id IS NOT NULL"),
        ),
    )

    property_bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("property_bank_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property.id", ondelete="CASCADE"), nullable=True
    )
    legal_entity_id: Mapped[uuid.UUID | None] = _fk("legal_entity.id", nullable=True)
    purpose: Mapped[AccountPurpose] = mapped_column(
        _enum(AccountPurpose, "bank_account_purpose"),
        nullable=False,
        default=AccountPurpose.GENERAL,
        server_default="general",
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


# --- FinTS/HBCI PIN/TAN (M11-01 addendum 27.09.2026, docs/integrations/fints.md) ------------


class FinTsSessionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_TAN = "awaiting_tan"
    AWAITING_DECOUPLED = "awaiting_decoupled"
    DONE = "done"
    FAILED = "failed"


class FinTsConnection(IdMixin, TimestampMixin, TenantMixin, Base):
    """FinTS specific state of one `bank_connection` (connector `fints`). Login, PIN and the
    python-fints client state (`deconstruct(including_private=True)`: system id, bank and
    user parameter data, account numbers) are stored encrypted with the master key
    (`EncryptedText`, like mailbox secrets). The PIN never leaves the server, is never logged
    and never returned by the API. Read only: no payment (G2)."""

    __tablename__ = "fints_connection"
    __table_args__ = (
        Index("uq_fints_connection_bank_connection", "bank_connection_id", unique=True),
    )

    bank_connection_id: Mapped[uuid.UUID] = _fk("bank_connection.id")
    blz: Mapped[str] = mapped_column(String(8), nullable=False)
    fints_url: Mapped[str] = mapped_column(String(300), nullable=False)
    login: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    pin: Mapped[str | None] = mapped_column(EncryptedText())
    # base64 of the opaque python-fints blob; None until the first successful dialog
    client_data: Mapped[str | None] = mapped_column(EncryptedText())
    tan_mechanism: Mapped[str | None] = mapped_column(String(3))
    tan_mechanisms: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    tan_medium: Mapped[str | None] = mapped_column(String(32))
    # last successful strong customer authentication (TAN); PSD2: due again after 90 days
    last_sca_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # After a rejected login the stored PIN is not reused automatically (bank locks after
    # three failures); the next attempt needs a fresh PIN entry.
    pin_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_code: Mapped[str | None] = mapped_column(String(20))


class FinTsAccountLink(IdMixin, TimestampMixin, TenantMixin, Base):
    """One SEPA account the bank reported for a FinTS connection, linked to at most one
    internal `property_bank_account` (6.9.7). Unassigned accounts import nothing."""

    __tablename__ = "fints_account_link"
    __table_args__ = (
        Index(
            "uq_fints_account_link_iban",
            "tenant_id",
            "fints_connection_id",
            "iban_fingerprint",
            unique=True,
        ),
    )

    fints_connection_id: Mapped[uuid.UUID] = _fk("fints_connection.id")
    iban: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    iban_suffix: Mapped[str] = mapped_column(String(4), nullable=False)
    iban_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bic: Mapped[str | None] = mapped_column(String(11))
    account_number: Mapped[str | None] = mapped_column(String(30))
    subaccount: Mapped[str | None] = mapped_column(String(30))
    property_bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "property_bank_account.id", nullable=True
    )
    balance_booked: Mapped[Decimal | None] = mapped_column(MONEY)
    balance_currency: Mapped[str | None] = mapped_column(String(3))
    balance_as_of: Mapped[date | None] = mapped_column(Date)
    balance_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_transactions_fetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_booking_date: Mapped[date | None] = mapped_column(Date)


class FinTsSession(IdMixin, TimestampMixin, TenantMixin, Base):
    """State of one asynchronous FinTS dialog (connect or refresh) that may pause for a TAN.
    python-fints is blocking, so the worker (queue `bank`) runs each step and writes the
    result here; the API only reads the status and hands in the TAN. The pending TAN request,
    the paused dialog and the client state are opaque python-fints blobs, stored encrypted
    (base64 in `EncryptedText`); a TAN itself is never stored. The challenge image
    (photoTAN/matrix) is kept as bytes for display only."""

    __tablename__ = "bank_fints_session"
    __table_args__ = (
        Index(
            "ix_bank_fints_session_connection_status",
            "tenant_id",
            "fints_connection_id",
            "status",
        ),
    )

    fints_connection_id: Mapped[uuid.UUID] = _fk("fints_connection.id")
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)  # connect | refresh
    status: Mapped[FinTsSessionStatus] = mapped_column(
        _enum(FinTsSessionStatus, "bank_fints_session_status"), nullable=False
    )
    tan_mechanism: Mapped[str | None] = mapped_column(String(3))
    challenge_text: Mapped[str | None] = mapped_column(Text)
    challenge_hhduc: Mapped[str | None] = mapped_column(Text)
    challenge_image_mime: Mapped[str | None] = mapped_column(String(64))
    challenge_image: Mapped[bytes | None] = mapped_column(LargeBinary)
    challenge_decoupled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    retry_data: Mapped[str | None] = mapped_column(EncryptedText())
    dialog_data: Mapped[str | None] = mapped_column(EncryptedText())
    client_data: Mapped[str | None] = mapped_column(EncryptedText())
    # JSON of `fints.Progress` (accounts, balances, transactions collected so far); encrypted
    # because it carries IBANs and transaction texts
    progress: Mapped[str | None] = mapped_column(EncryptedText())
    # a submitted TAN waits here only until the worker picks the step up, then it is cleared
    pending_tan: Mapped[str | None] = mapped_column(EncryptedText())
    sync_run_id: Mapped[uuid.UUID | None] = _fk("bank_sync_run.id", nullable=True)
    since: Mapped[date | None] = mapped_column(Date)
    until: Mapped[date | None] = mapped_column(Date)
    error_code: Mapped[str | None] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Bank specific CSV import (M11-02, docs/integrations/bank-csv.md) ----------------------


class BankCsvMapping(IdMixin, TimestampMixin, TenantMixin, Base):
    """A user defined column mapping for the generic CSV import path, stored per account so
    it does not have to be re-entered on every import (8.1). Recognised bank formats
    (`mhvp.banking.csv_formats.KNOWN_FORMATS`) need no row here; this only holds mappings the
    operator built by hand for a format this module does not recognise from its header."""

    __tablename__ = "bank_csv_mapping"
    __table_args__ = (
        Index(
            "uq_bank_csv_mapping_account_label",
            "tenant_id",
            "property_bank_account_id",
            "label",
            unique=True,
        ),
    )

    # a hand built mapping has no meaning without its account: removed with it (no money)
    property_bank_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("property_bank_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


# --- Learning bookkeeper: decision log (ADR 0014, rule M12-04, plan M12 S1) -------------------


class PostingDecisionStatus(StrEnum):
    """States of one decision round of a bank transaction. ``pending`` is the stored proposal
    snapshot; every other state closes the round. The closed list of the plan (3.1 no. 1):
    ``auto_posted`` is written by the runner of step S6 only, never here."""

    PENDING = "pending"
    ACCEPTED_UNCHANGED = "accepted_unchanged"  # exactly the chosen proposal was booked
    MODIFIED = "modified"  # booked with a diff against the chosen proposal
    REJECTED = "rejected"  # proposals rejected with a mandatory reason, transaction stays open
    IGNORED = "ignored"  # transaction ignored with reason (reopenable)
    AUTO_POSTED = "auto_posted"  # reserved for the runner (S6)
    EXPIRED = "expired"  # superseded by a fresh snapshot (features changed)
    REVERSED = "reversed"  # the booked entry was reversed (counter example, watermark job)


POSTING_DECISION_STATUSES = tuple(s.value for s in PostingDecisionStatus)


class PostingDecision(IdMixin, TimestampMixin, TenantMixin, Base):
    """Proposal and decision log per bank transaction and round (ADR 0014, M12-04).

    Append only in the sense of B03: a row is inserted as ``pending`` (snapshot of all stage 1
    proposals, engine and rule version, ``features_hash``) or directly in a closed state when a
    person decides before the snapshot job ran; a pending row is closed exactly once (the
    decision columns are filled, the snapshot columns never change); closed rows are immutable
    and nothing is ever deleted (DB trigger ``mhvp_posting_decision_guard``, migration 0232).
    At most one pending row per transaction (partial unique index). Learning (S3, S5) reads
    only decisions of persons on postings that were not reversed (7.4 no. 6); ``reversed`` rows
    are the counter examples. Contains payer data (fingerprints, purpose tokens): rows exist
    only while ``tenant_settings.learning_bookkeeper_enabled`` is on."""

    __tablename__ = "posting_decision"
    __table_args__ = (
        CheckConstraint(
            "status IN ({})".format(", ".join(f"'{s}'" for s in POSTING_DECISION_STATUSES)),
            name="posting_decision_status",
        ),
        CheckConstraint("round >= 1", name="posting_decision_round"),
        Index(
            "uq_posting_decision_pending",
            "tenant_id",
            "bank_transaction_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_posting_decision_transaction",
            "tenant_id",
            "bank_transaction_id",
            "round",
        ),
        Index(
            "ix_posting_decision_journal_entry",
            "tenant_id",
            "journal_entry_id",
            postgresql_where=text("journal_entry_id IS NOT NULL"),
        ),
        Index("ix_posting_decision_entity_status", "tenant_id", "legal_entity_id", "status"),
    )

    bank_transaction_id: Mapped[uuid.UUID] = _fk("bank_transaction.id")
    # B01: the legal entity of the transaction's bank account; every key of the learning
    # bookkeeper carries it, nothing is read across legal entities.
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    sync_run_id: Mapped[uuid.UUID | None] = _fk("bank_sync_run.id", nullable=True)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=PostingDecisionStatus.PENDING.value
    )
    # Bulk confirmations count as evidence with lower weight (plan 3.3).
    bulk: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    features_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Minimised feature summary (no names, no full purpose, no plain IBAN).
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Snapshot of all stage 1 proposals as shown (``posting_proposal.Proposal.as_dict``).
    proposals: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    case_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    level: Mapped[str] = mapped_column(String(4), nullable=False, default="L0")
    best_source: Mapped[str | None] = mapped_column(String(16))
    best_confidence: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    # Decision (filled once when the row is closed).
    chosen_index: Mapped[int | None] = mapped_column(Integer)
    final: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    journal_entry_id: Mapped[uuid.UUID | None] = _fk("journal_entry.id", nullable=True)
    ai_proposal_id: Mapped[uuid.UUID | None] = _fk("ai_proposal.id", nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = _fk("posting_decision.id", nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Runner (S6): fingerprint of the deterministic verification at posting time and the day
    # the review is due; both only on ``auto_posted`` rows.
    verifier_fingerprint: Mapped[str | None] = mapped_column(String(64))
    review_due_on: Mapped[date | None] = mapped_column(Date)
    # Retention run (operator decision M12-06, 24 months): payer fingerprint and proposal
    # evidence nulled, outcome kept; the guard trigger allows exactly this update once.
    anonymised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BankingEventWatermark(IdMixin, TenantMixin, Base):
    """Position of the banking event consumer in ``domain_event`` per tenant (occurred_at, id),
    pattern ``automation_watermark`` (``mhvp.banking.events_consumer``)."""

    __tablename__ = "banking_event_watermark"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_banking_event_watermark_tenant"),)

    last_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class BankSyncSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Per tenant configuration of the daily bank sync (8.2, M11-05). Without a row the
    default hour 06:00 local time applies (beat entries ``banking-sync-all`` and
    ``banking-finapi-scheduled-fetch``); with a row the hourly beat ``banking-sync-due``
    runs the tenant at ``sync_hour`` instead."""

    __tablename__ = "bank_sync_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_bank_sync_setting_tenant"),
        CheckConstraint("sync_hour BETWEEN 0 AND 23", name="bank_sync_setting_hour"),
    )

    sync_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, default=6, server_default=text("6")
    )


class AutoPostingDigest(IdMixin, TimestampMixin, TenantMixin, Base):
    """Weekly digest of level L3 per legal entity (plan M12 S10, 7.4 no. 4, M12-02).

    Counts the automatic postings and sampled reviews of one ISO week and the monthly bank
    reconciliation B09 of the previous month as completeness check. A person must confirm
    the digest before the next week without daily review: while a digest of an earlier week
    is unconfirmed, the runner blocks the sampled classes at L3. Confirmation requires a
    reconciliation without difference (``reconciliation_ok``)."""

    __tablename__ = "auto_posting_digest"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "legal_entity_id", "week_start", name="uq_auto_posting_digest_week"
        ),
    )

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    auto_posted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    sampled: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    reviews_open: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    findings: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    reconciliation: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    reconciliation_ok: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
