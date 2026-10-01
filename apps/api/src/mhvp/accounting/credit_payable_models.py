"""Payables from statement credits (P04-04, Q01-01, M15-07, AE22, rule AE22).

A credit from a rental operating cost statement, a payout from an owner statement or a deposit
refund from a released deposit settlement becomes a payable open item only through a proposal
and a release by a person. How the credit becomes a liability is an open booking rule
(OPEN_QUESTIONS Q01-01); the tenant chooses the variant in ``credit_payable_setting``:

* ``off`` (default): candidates are listed, nothing is created;
* ``subledger``: the release adds a payable open item on the debtor account to the posted
  credit line of the statement result entry; no new posting (rental statement only);
* ``reclass``: the release writes a draft entry of kind ``credit_reclass`` (debit source account,
  credit the creditor account entered by the operator); posting it on the regular path (G1)
  creates the payable open item.

The payout itself stays a payment order without invoice (``payment_run.order_for_payout``)
with two approvals; the payment file stays behind G2.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)

MODES = ("off", "subledger", "reclass")
SOURCE_TYPES = ("rent_statement", "owner_statement", "deposit_settlement")
STATUSES = ("proposed", "released", "withdrawn")
# Payout reason of the payment order per source (payment_run.PAYOUT_REASONS).
PAYOUT_REASON = {
    "rent_statement": "statement_credit",
    "owner_statement": "owner_payout",
    "deposit_settlement": "deposit_refund",
}


class CreditPayableSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant switch of the booking rule variant (Q01-01 open, default ``off``). Account
    numbers are operator input per tenant and looked up in the ledger of the source; no
    account is assumed."""

    __tablename__ = "credit_payable_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_credit_payable_setting_tenant"),
        CheckConstraint("mode IN ('off', 'subledger', 'reclass')", name="mode"),
        CheckConstraint(
            "creditor_account_number IS NULL OR creditor_account_number ~ '^[0-9]{6}$'",
            name="creditor_account_number",
        ),
        CheckConstraint(
            "owner_debit_account_number IS NULL OR owner_debit_account_number ~ '^[0-9]{6}$'",
            name="owner_debit_account_number",
        ),
        CheckConstraint(
            "deposit_debit_account_number IS NULL OR deposit_debit_account_number ~ '^[0-9]{6}$'",
            name="deposit_debit_account_number",
        ),
    )

    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="off", server_default="off"
    )
    four_eyes_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    creditor_account_number: Mapped[str | None] = mapped_column(String(6))
    owner_debit_account_number: Mapped[str | None] = mapped_column(String(6))
    deposit_debit_account_number: Mapped[str | None] = mapped_column(String(6))


class CreditPayable(IdMixin, TimestampMixin, TenantMixin, Base):
    """Proposal and release of one payable from a statement credit. ``created_by`` proposed it.
    Financial effects live in the open item and the journal entries; this row is the trail."""

    __tablename__ = "credit_payable"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(
            "source_type IN ('rent_statement', 'owner_statement', 'deposit_settlement')",
            name="source_type",
        ),
        CheckConstraint("variant IN ('subledger', 'reclass')", name="variant"),
        CheckConstraint("status IN ('proposed', 'released', 'withdrawn')", name="status"),
        Index("ix_credit_payable_tenant_ledger", "tenant_id", "ledger_id"),
        # One active proposal per source (contract); withdrawn rows stay for the trail.
        Index(
            "uq_credit_payable_active_source",
            "tenant_id",
            "source_key",
            unique=True,
            postgresql_where=text("status <> 'withdrawn'"),
        ),
    )

    ledger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ledger.id"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contract.id")
    )
    # Posted credit entry of the statement result (rental statement only).
    source_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entry.id")
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    variant: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed", server_default="proposed"
    )
    payout_reason: Mapped[str] = mapped_column(String(24), nullable=False)
    open_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("open_item.id")
    )
    # Draft entry of the reclass variant; a discarded draft sets it to NULL.
    reclass_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entry.id", ondelete="SET NULL")
    )
    reversal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entry.id")
    )
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdraw_reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    # [{"code": ..., "message": ...}] shown at proposal and release, never blocking.
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
