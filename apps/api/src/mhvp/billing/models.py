"""Statements with snapshots (6.9.3, A01) for operating costs of rentals (7.6, M17)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.billing.status import StatementStatus
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class StatementKind(StrEnum):
    OPERATING_COSTS = "operating_costs"


class Statement(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "statement"

    kind: Mapped[StatementKind] = mapped_column(
        Enum(
            StatementKind,
            name="statement_kind_type",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    ledger_id: Mapped[uuid.UUID] = _fk("ledger.id")
    property_id: Mapped[uuid.UUID] = _fk("property.id")
    period_from: Mapped[date] = mapped_column(Date, nullable=False)
    period_to: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[StatementStatus] = mapped_column(
        Enum(
            StatementStatus, name="statement_status", values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
        default=StatementStatus.DRAFT,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = _fk("statement.id", nullable=True)
    # Current snapshot; no FK because the snapshot references the statement (cycle).
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    delivered_at: Mapped[date | None] = mapped_column(Date)
    deadline_exception: Mapped[str | None] = mapped_column(Text)


class StatementCostItem(IdMixin, TimestampMixin, TenantMixin, Base):
    """A cost position chosen by a person with its contractual basis (A02); never inferred from
    the account name. Heating costs come as external amounts per unit (H01)."""

    __tablename__ = "statement_cost_item"

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    account_id: Mapped[uuid.UUID | None] = _fk("ledger_account.id", nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    allocation_key_id: Mapped[uuid.UUID | None] = _fk("allocation_key.id", nullable=True)
    # {unit_id: amount} for external calculations (heating, water); sum must equal amount.
    external_amounts: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    basis: Mapped[str] = mapped_column(Text, nullable=False)  # contract clause / source
    heating: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class StatementSnapshot(IdMixin, TenantMixin, Base):
    """Immutable result of a calculation: inputs, keys, rule version, results, hash (6.9.3)."""

    __tablename__ = "statement_snapshot"

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    results: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class StatementEvent(IdMixin, TenantMixin, Base):
    __tablename__ = "statement_event"

    statement_id: Mapped[uuid.UUID] = _fk("statement.id", ondelete="CASCADE")
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
