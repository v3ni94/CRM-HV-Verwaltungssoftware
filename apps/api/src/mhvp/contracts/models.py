"""Contracts, payments, schedules, SEPA mandates, deposits, debtor accounts (6.3, 6.9)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

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
from sqlalchemy.dialects.postgresql import UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)  # booked amounts (6.9.8)
RATE = Numeric(20, 8)  # rates, shares


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(target: str, *, nullable: bool = False, ondelete: str = "RESTRICT") -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True
    )


class ContractKind(StrEnum):
    TENANCY = "tenancy"
    OWNERSHIP = "ownership"


class AcquisitionKind(StrEnum):
    PURCHASE = "purchase"
    FIRST_ACQUISITION = "first_acquisition"
    INHERITANCE = "inheritance"
    FORECLOSURE = "foreclosure"
    GIFT = "gift"
    OTHER = "other"


class ContractVatOption(StrEnum):
    NONE = "none"
    COMMERCIAL_NO_VAT = "commercial_no_vat"
    COMMERCIAL_FULL_VAT = "commercial_full_vat"
    COMMERCIAL_REDUCED_VAT = "commercial_reduced_vat"


class PaymentReason(StrEnum):
    INITIAL = "initial"
    INDEX = "index"
    GRADUATED = "graduated"
    INCREASE = "increase"
    ADJUSTMENT_FROM_STATEMENT = "adjustment_from_statement"
    OTHER = "other"


class PaymentInterval(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"


class DueDayRule(StrEnum):
    DAY = "day"
    WORKDAY = "workday"
    LAST_DAY = "last_day"
    DAY_NEXT_MONTH = "day_next_month"


class MandateType(StrEnum):
    CORE = "core"
    B2B = "b2b"


class MandateSequence(StrEnum):
    FIRST = "first"
    RECURRING = "recurring"
    ONE_OFF = "one_off"


class MandateStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class DepositKind(StrEnum):
    CASH = "cash"
    SAVINGS_BOOK = "savings_book"
    INSURANCE = "insurance"
    GUARANTEE = "guarantee"
    FIXED_DEPOSIT = "fixed_deposit"
    LETTER_OF_COMFORT = "letter_of_comfort"
    OTHER = "other"


class DepositMovementKind(StrEnum):
    PAYMENT = "payment"
    INTEREST = "interest"
    PAYOUT = "payout"
    OFFSET = "offset"


_PERIOD = "daterange(start_date, end_date, '[]')"


class Contract(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenancy or ownership of a unit. At most one active of each kind per unit (6.3, 6.9.2)."""

    __tablename__ = "contract"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", "version"),
        ExcludeConstraint(
            ("unit_id", "="),
            ("kind", "="),
            (text(_PERIOD), "&&"),
            name="ex_contract_unit_kind_period",
            using="gist",
        ),
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="period_order"),
        CheckConstraint(
            "kind <> 'ownership' OR "
            "(title_transfer_date IS NOT NULL AND title_transfer_date <= start_date)",
            name="ownership_title_transfer",
        ),
        CheckConstraint("kind = 'ownership' OR NOT sev_enabled", name="sev_only_ownership"),
        # Start page tiles and derived dates filter by end and termination date, lists by kind
        # (performance review 26.09.2026).
        Index("ix_contract_tenant_end_date", "tenant_id", "end_date"),
        Index("ix_contract_tenant_termination_date", "tenant_id", "termination_date"),
        Index("ix_contract_tenant_kind", "tenant_id", "kind"),
    )

    kind: Mapped[ContractKind] = mapped_column(_enum(ContractKind, "contract_kind"), nullable=False)
    property_id: Mapped[uuid.UUID] = _fk("property.id")
    unit_id: Mapped[uuid.UUID] = _fk("unit.id")
    party_id: Mapped[uuid.UUID] = _fk("party.id")
    # Creditor of the claims under this contract (6.9.1): GdWE for ownership, landlord for tenancy.
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    debtor_account_id: Mapped[uuid.UUID] = _fk("debtor_account_reservation.id")
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    termination_date: Mapped[date | None] = mapped_column(Date)
    termination_reason: Mapped[str | None] = mapped_column(Text)
    direct_debit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sepa_mandate_id: Mapped[uuid.UUID | None] = _fk("sepa_mandate.id", nullable=True)
    dunning_block: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dunning_block_reason: Mapped[str | None] = mapped_column(Text)
    rent_increase_block_until: Mapped[date | None] = mapped_column(Date)
    user_change_fee: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allocation_loss_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vat_option: Mapped[ContractVatOption] = mapped_column(
        _enum(ContractVatOption, "contract_vat_option"),
        nullable=False,
        default=ContractVatOption.NONE,
    )
    sev_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 6.9.11: the owner pays the SEV fee; the recipient is always the management tenant.
    sev_fee_debtor_party_id: Mapped[uuid.UUID | None] = _fk("party.id", nullable=True)
    title_transfer_date: Mapped[date | None] = mapped_column(Date)
    benefit_burden_date: Mapped[date | None] = mapped_column(Date)
    acquisition_kind: Mapped[AcquisitionKind | None] = mapped_column(
        _enum(AcquisitionKind, "acquisition_kind")
    )
    special_succession_liability: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)


class DebtorAccountReservation(IdMixin, TimestampMixin, TenantMixin, Base):
    """Debtor account per party and unit in the creditor's books (6.9.2, D15).

    Created with the contract; postings start with the ledger (M10), which adopts these numbers.
    """

    __tablename__ = "debtor_account_reservation"
    __table_args__ = (
        UniqueConstraint("tenant_id", "legal_entity_id", "party_id", "unit_id"),
        UniqueConstraint("tenant_id", "legal_entity_id", "number"),
    )

    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    party_id: Mapped[uuid.UUID] = _fk("party.id")
    unit_id: Mapped[uuid.UUID] = _fk("unit.id")
    number: Mapped[str] = mapped_column(String(6), nullable=False)
    name: Mapped[str] = mapped_column(String(400), nullable=False)


class ContractPayment(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "contract_payment"
    __table_args__ = (
        ExcludeConstraint(
            ("contract_id", "="),
            ("payment_type_code", "="),
            (text("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_contract_payment_period",
            using="gist",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period_order"),
    )

    contract_id: Mapped[uuid.UUID] = _fk("contract.id", ondelete="CASCADE")
    payment_type_code: Mapped[str] = mapped_column(String(63), nullable=False)
    net: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    vat_percent: Mapped[Decimal] = mapped_column(RATE, nullable=False, default=Decimal(0))
    gross: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[PaymentReason] = mapped_column(
        _enum(PaymentReason, "payment_reason"), nullable=False
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PaymentSchedule(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "payment_schedule"
    __table_args__ = (
        ExcludeConstraint(
            ("contract_id", "="),
            (text("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_payment_schedule_period",
            using="gist",
        ),
        CheckConstraint("due_day BETWEEN 1 AND 31", name="due_day_range"),
    )

    contract_id: Mapped[uuid.UUID] = _fk("contract.id", ondelete="CASCADE")
    interval: Mapped[PaymentInterval] = mapped_column(
        _enum(PaymentInterval, "payment_interval"), nullable=False
    )
    due_day_rule: Mapped[DueDayRule] = mapped_column(
        _enum(DueDayRule, "due_day_rule"), nullable=False
    )
    due_day: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)


class SepaMandate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Recorded mandate with evidence. Collecting is locked until release gate G2."""

    __tablename__ = "sepa_mandate"
    __table_args__ = (
        UniqueConstraint("tenant_id", "creditor_id", "reference"),
        Index("ix_sepa_mandate_tenant_status", "tenant_id", "status"),
    )

    party_id: Mapped[uuid.UUID] = _fk("party.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    contact_bank_account_id: Mapped[uuid.UUID] = _fk("contact_bank_account.id")
    reference: Mapped[str] = mapped_column(String(35), nullable=False)
    creditor_id: Mapped[str] = mapped_column(String(35), nullable=False)
    signed_at: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[MandateType] = mapped_column(_enum(MandateType, "mandate_type"), nullable=False)
    sequence: Mapped[MandateSequence] = mapped_column(
        _enum(MandateSequence, "mandate_sequence"), nullable=False
    )
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[MandateStatus] = mapped_column(
        _enum(MandateStatus, "mandate_status"), nullable=False, default=MandateStatus.ACTIVE
    )
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Deposit(IdMixin, TimestampMixin, TenantMixin, Base):
    """Rental deposit on a segregated account of the landlord (6.9.1, D56, annex C)."""

    __tablename__ = "deposit"

    contract_id: Mapped[uuid.UUID] = _fk("contract.id")
    kind: Mapped[DepositKind] = mapped_column(_enum(DepositKind, "deposit_kind"), nullable=False)
    amount_due: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    installments: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    property_bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "property_bank_account.id", nullable=True
    )
    interest_rule: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")


class DepositMovement(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "deposit_movement"

    deposit_id: Mapped[uuid.UUID] = _fk("deposit.id", ondelete="CASCADE")
    date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    kind: Mapped[DepositMovementKind] = mapped_column(
        _enum(DepositMovementKind, "deposit_movement_kind"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text)
    # Set by the ledger from M10; until then movements are records, not postings.
    posting_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
