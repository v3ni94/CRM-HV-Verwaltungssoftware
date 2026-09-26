"""SEPA direct debit runs (pain.008, 7.5 SEPA, M15, rule M15-02).

A run collects due receivables (Sollstellungen) of one ledger and legal entity into one
collection file. Orders carry a snapshot of the mandate evidence taken from the contact bank
account (rule M3-02) at creation time. Two different persons approve the run; the generated
file is stored as a document and never transmitted to a bank; the download requires release
gate G2. Financial content is never overwritten: a run is cancelled, not edited.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, text
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


class DirectDebitRunStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    FILE_GENERATED = "file_generated"  # stored as document, not handed out (G2 closed)
    EXPORTED = "exported"  # file downloaded behind G2; counts as mandate use
    CANCELLED = "cancelled"


class SequenceType(StrEnum):
    """ISO 20022 ``SeqTp`` values used for SEPA Core Direct Debit."""

    FRST = "FRST"
    RCUR = "RCUR"


class DirectDebitRun(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "direct_debit_run"
    __table_args__ = (
        Index("ix_direct_debit_run_tenant_status_date", "tenant_id", "status", "collection_date"),
    )

    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    property_bank_account_id: Mapped[uuid.UUID] = _fk("property_bank_account.id")
    creditor_id: Mapped[str] = mapped_column(String(35), nullable=False)
    creditor_name: Mapped[str] = mapped_column(String(70), nullable=False)
    collection_date: Mapped[date] = mapped_column(Date, nullable=False)
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[str] = mapped_column(String(35), nullable=False, unique=True)
    format: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[DirectDebitRunStatus] = mapped_column(
        _enum(DirectDebitRunStatus, "direct_debit_run_status"),
        nullable=False,
        default=DirectDebitRunStatus.DRAFT,
        server_default="draft",
    )
    control_sum: Mapped[Decimal] = mapped_column(
        MONEY, nullable=False, default=Decimal(0), server_default="0"
    )
    transaction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    excluded: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exported_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class DirectDebitOrder(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "direct_debit_order"
    __table_args__ = (
        Index("ix_direct_debit_order_run_id", "run_id"),
        Index("ix_direct_debit_order_contact_bank_account_id", "contact_bank_account_id"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("direct_debit_run.id", ondelete="CASCADE"), nullable=False
    )
    open_item_id: Mapped[uuid.UUID] = _fk("open_item.id")
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)
    contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    contact_bank_account_id: Mapped[uuid.UUID] = _fk("contact_bank_account.id")
    mandate_reference: Mapped[str] = mapped_column(String(35), nullable=False)
    mandate_signed_on: Mapped[date] = mapped_column(Date, nullable=False)
    mandate_scheme: Mapped[str] = mapped_column(String(8), nullable=False)
    sequence_type: Mapped[SequenceType] = mapped_column(
        _enum(SequenceType, "direct_debit_sequence_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    debtor_name: Mapped[str] = mapped_column(String(140), nullable=False)
    debtor_iban: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    debtor_iban_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(140), nullable=False)
    end_to_end_id: Mapped[str] = mapped_column(String(35), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    pre_notification_document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True)
    pre_notification_dispatch_id: Mapped[uuid.UUID | None] = _fk("dispatch.id", nullable=True)


class DirectDebitApproval(IdMixin, TenantMixin, Base):
    """Approval bound to a snapshot of the run (6.9.9); a change invalidates it."""

    __tablename__ = "direct_debit_approval"
    __table_args__ = (Index("ix_direct_debit_approval_run_id", "run_id"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("direct_debit_run.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
