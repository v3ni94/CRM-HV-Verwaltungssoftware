"""Bank connections, statements, transactions and sync runs (6.4, 6.9.7, 8).

Identity for re-import is the bank reference per account (6.9.7); the content hash only flags a
possible duplicate and never discards a transaction (D05). Counterpart IBANs are encrypted.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, text
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
