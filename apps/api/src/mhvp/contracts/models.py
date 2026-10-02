"""Contracts, payments, schedules, SEPA mandates, deposits, debtor accounts (6.3, 6.9)."""

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
from sqlalchemy.dialects.postgresql import JSONB, UUID, ExcludeConstraint
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


class DepositStatus(StrEnum):
    """Status model of a deposit (M5-06): ``open`` until the due amount is handled, ``active``
    while held, ``settled`` after the final settlement (no further changes)."""

    OPEN = "open"
    ACTIVE = "active"
    SETTLED = "settled"


class DepositMovementKind(StrEnum):
    PAYMENT = "payment"
    INTEREST = "interest"
    PAYOUT = "payout"
    OFFSET = "offset"


class ContractApprovalStatus(StrEnum):
    """Management approval of imported contracts before the first receivable run."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


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
        Index("ix_contract_tenant_approval_status", "tenant_id", "approval_status"),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="approval_status_values",
        ),
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
    # M13-01 (migration 0177): pro rata rule of this contract for a start, end or amount change
    # within a month (calendar_days, thirty_360, full_month); NULL uses the tenant default from
    # ``TenantSettings.receivable_rules``. Applied only when the tenant has released the rules.
    proration_method: Mapped[str | None] = mapped_column(String(16))
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
    # Calendar dates of the physical move (4.5, migration 0150); independent of start and end.
    move_in_on: Mapped[date | None] = mapped_column(Date)
    move_out_on: Mapped[date | None] = mapped_column(Date)
    # M5-02 (migration 0265): user defined fields (definitions per tenant, entity ``contract``).
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", nullable=True)
    # Origin and management approval (migration 0133): imported contracts start ``pending`` and
    # are skipped by the receivable run until approved; manual and existing ones are approved.
    source: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="approved", server_default="approved"
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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
    # M5-01 (migration 0265): revenue account of this component (reference to the ledger chart);
    # empty: the tenant mapping of the payment type applies.
    revenue_account_id: Mapped[uuid.UUID | None] = _fk(
        "ledger_account.id", nullable=True, ondelete="SET NULL"
    )
    # M24-01 (migration 0278): earmarked reserve the standing amount is bound to (Zweckbindung
    # der Sollstellung, 7.8 W08); the receivable item carries it on, payments follow the item.
    reserve_id: Mapped[uuid.UUID | None] = _fk("hoa_reserve.id", nullable=True, ondelete="SET NULL")


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
    # M13-02 (migration 0177): instalment due in advance (first month of the period) or in
    # arrears (last month); whether the contract amount is per month or per instalment.
    payment_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="advance", server_default="advance"
    )
    amount_basis: Mapped[str] = mapped_column(
        String(16), nullable=False, default="per_month", server_default="per_month"
    )


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
    # 4.5 (migration 0150): payment types the mandate covers (empty list = all types of the
    # contract) and whether special levies are excluded from the collection. Recording only;
    # the collection itself stays locked until G2.
    payment_type_codes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    exclude_special_levy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class ContractAllocationValue(IdMixin, TimestampMixin, TenantMixin, Base):
    """Contract related allocation key value with period, e.g. persons (4.5 Eigenschaften).

    Periods of one contract and key never overlap. Statements read these values only when
    the allocation logic of the statement modules picks them up; no financial effect here.
    """

    __tablename__ = "contract_allocation_value"
    __table_args__ = (
        ExcludeConstraint(
            ("contract_id", "="),
            ("allocation_key_id", "="),
            (text("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_contract_allocation_value_period",
            using="gist",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period_order"),
    )

    contract_id: Mapped[uuid.UUID] = _fk("contract.id", ondelete="CASCADE")
    allocation_key_id: Mapped[uuid.UUID] = _fk("allocation_key.id", ondelete="CASCADE")
    value: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)


class ContractTerminationReading(IdMixin, TimestampMixin, TenantMixin, Base):
    """Meter reading recorded with the termination of a contract (4.5 Aktionen).

    The value is also written as a ``meter_reading`` (source ``manual``); this row keeps the
    link between contract end and reading as evidence for the statement.
    """

    __tablename__ = "contract_termination_reading"
    __table_args__ = (UniqueConstraint("contract_id", "meter_id"),)

    contract_id: Mapped[uuid.UUID] = _fk("contract.id", ondelete="CASCADE")
    meter_id: Mapped[uuid.UUID] = _fk("meter.id", ondelete="CASCADE")
    meter_reading_id: Mapped[uuid.UUID | None] = _fk(
        "meter_reading.id", nullable=True, ondelete="SET NULL"
    )
    value: Mapped[Decimal] = mapped_column(RATE, nullable=False)
    read_at: Mapped[date] = mapped_column(Date, nullable=False)


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
    # M5-06 (migration 0265): document references (DMS ids) such as deposit agreement, proof of
    # payment, bank confirmation.
    documents: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class DepositHintSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """AI18 (GAH-111, migration 0443): non blocking review hint on residential deposits.
    Off by default (no row means off). ``factor_months`` monthly rents of the payment types in
    ``rent_payment_codes`` (default ``rent``, i.e. without operating costs) and
    ``max_installments`` instalments are configurable comparison values, not a legal rule;
    the hint never blocks saving (open decision, G3)."""

    __tablename__ = "deposit_hint_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint("factor_months > 0 AND factor_months <= 24", name="factor_months"),
        CheckConstraint("max_installments BETWEEN 1 AND 12", name="max_installments"),
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    factor_months: Mapped[Decimal] = mapped_column(
        RATE, nullable=False, default=Decimal(3), server_default="3"
    )
    max_installments: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    rent_payment_codes: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: ["rent"],
        server_default=text("""'["rent"]'::jsonb"""),
    )


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


class AllocationAgreement(IdMixin, TimestampMixin, TenantMixin, Base):
    """Agreement that a cost position (BetrKV catalogue type) is passed on to a tenancy, with the
    clause reference and the proof document (M17-01, AE17). The platform never infers it from
    account names; the legal validity of the clause stays a human review."""

    __tablename__ = "allocation_agreement"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period_order"),
        CheckConstraint("status IN ('agreed', 'excluded')", name="status_values"),
        CheckConstraint(
            "status = 'excluded' OR (clause_reference IS NOT NULL AND clause_reference <> '')",
            name="clause_required",
        ),
        ExcludeConstraint(
            ("contract_id", "="),
            ("operating_cost_type", "="),
            (text("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_allocation_agreement_period",
            using="gist",
        ),
    )

    contract_id: Mapped[uuid.UUID] = _fk("contract.id", ondelete="CASCADE")
    operating_cost_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="agreed")
    clause_reference: Mapped[str | None] = mapped_column(Text)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True, ondelete="SET NULL")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
