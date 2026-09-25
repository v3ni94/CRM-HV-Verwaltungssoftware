"""API schemas for contracts (6.3, 6.9.2, 6.9.11)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mhvp.contracts.models import (
    AcquisitionKind,
    ContractKind,
    ContractVatOption,
    DepositKind,
    DepositMovementKind,
    DueDayRule,
    MandateSequence,
    MandateStatus,
    MandateType,
    PaymentInterval,
    PaymentReason,
)
from mhvp.contracts.validation import (
    InvalidSepaValueError,
    check_mandate_reference,
    normalise_creditor_id,
)

Money = Decimal


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class ContractIn(_In):
    kind: ContractKind
    unit_id: uuid.UUID
    party_id: uuid.UUID
    start_date: date
    end_date: date | None = None
    legal_entity_id: uuid.UUID | None = Field(
        default=None, description="Nur nötig, wenn der Vermieter nicht eindeutig ist"
    )
    direct_debit: bool = False
    sepa_mandate_id: uuid.UUID | None = None
    dunning_block: bool = False
    dunning_block_reason: str | None = None
    rent_increase_block_until: date | None = None
    user_change_fee: bool = False
    allocation_loss_risk: bool = False
    vat_option: ContractVatOption = ContractVatOption.NONE
    sev_enabled: bool = False
    sev_fee_debtor_party_id: uuid.UUID | None = None
    title_transfer_date: date | None = None
    benefit_burden_date: date | None = None
    acquisition_kind: AcquisitionKind | None = None
    special_succession_liability: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date liegt vor start_date")
        if self.kind is ContractKind.OWNERSHIP:
            if self.title_transfer_date is None:
                raise ValueError(
                    "Eigentum: title_transfer_date (Eigentumsübergang laut Grundbuch) ist Pflicht"
                )
            if self.title_transfer_date > self.start_date:
                raise ValueError("Eigentum: start_date darf nicht vor dem Eigentumsübergang liegen")
        else:
            for name in ("sev_enabled", "special_succession_liability"):
                if getattr(self, name):
                    raise ValueError(f"{name} gibt es nur bei Eigentumsverhältnissen")
            if self.title_transfer_date or self.benefit_burden_date or self.acquisition_kind:
                raise ValueError("Eigentumsangaben gibt es nur bei Eigentumsverhältnissen")
        if self.dunning_block and not self.dunning_block_reason:
            raise ValueError("Mahnsperre braucht eine Begründung")
        return self


class ContractVersionIn(_In):
    effective_date: date
    direct_debit: bool | None = None
    sepa_mandate_id: uuid.UUID | None = None
    dunning_block: bool | None = None
    dunning_block_reason: str | None = None
    rent_increase_block_until: date | None = None
    user_change_fee: bool | None = None
    allocation_loss_risk: bool | None = None
    vat_option: ContractVatOption | None = None
    notes: str | None = None


class TerminationIn(_In):
    end_date: date
    termination_date: date | None = Field(default=None, description="Datum der Kündigungserklärung")
    termination_reason: str | None = None


class OwnershipTransferIn(_In):
    new_party_id: uuid.UUID
    title_transfer_date: date
    benefit_burden_date: date | None = None
    acquisition_kind: AcquisitionKind
    special_succession_liability: bool = False
    sev_enabled: bool = False


class PaymentIn(_In):
    payment_type_code: str
    net: Money = Field(max_digits=14, decimal_places=2)
    vat_percent: Decimal = Field(default=Decimal(0), ge=0, le=100, max_digits=20, decimal_places=8)
    gross: Money = Field(max_digits=14, decimal_places=2)
    valid_from: date
    valid_to: date | None = None
    reason: PaymentReason = PaymentReason.INITIAL
    document_id: uuid.UUID | None = None


class PaymentOut(_Out):
    id: uuid.UUID
    contract_id: uuid.UUID
    payment_type_code: str
    net: Money
    vat_percent: Decimal
    gross: Money
    currency: str
    valid_from: date
    valid_to: date | None
    reason: PaymentReason


class ScheduleIn(_In):
    interval: PaymentInterval = PaymentInterval.MONTHLY
    due_day_rule: DueDayRule = DueDayRule.DAY
    due_day: int = Field(default=3, ge=1, le=31)
    valid_from: date
    valid_to: date | None = None


class ScheduleOut(ScheduleIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID


class DebtorAccountOut(_Out):
    id: uuid.UUID
    legal_entity_id: uuid.UUID
    number: str
    name: str


class ContractOut(_Out):
    id: uuid.UUID
    kind: ContractKind
    number: str
    version: int
    property_id: uuid.UUID
    unit_id: uuid.UUID
    party_id: uuid.UUID
    legal_entity_id: uuid.UUID
    debtor_account: DebtorAccountOut
    start_date: date
    end_date: date | None
    termination_date: date | None
    termination_reason: str | None
    direct_debit: bool
    sepa_mandate_id: uuid.UUID | None
    dunning_block: bool
    dunning_block_reason: str | None
    rent_increase_block_until: date | None
    user_change_fee: bool
    allocation_loss_risk: bool
    vat_option: ContractVatOption
    sev_enabled: bool
    sev_fee_debtor_party_id: uuid.UUID | None
    title_transfer_date: date | None
    benefit_burden_date: date | None
    acquisition_kind: AcquisitionKind | None
    special_succession_liability: bool
    notes: str | None
    supersedes_contract_id: uuid.UUID | None
    payments: list[PaymentOut] = Field(default_factory=list)
    schedules: list[ScheduleOut] = Field(default_factory=list)


class MandateIn(_In):
    party_id: uuid.UUID
    legal_entity_id: uuid.UUID
    contact_bank_account_id: uuid.UUID
    reference: str
    creditor_id: str
    signed_at: date
    type: MandateType = MandateType.CORE
    sequence: MandateSequence = MandateSequence.RECURRING
    valid_until: date | None = None
    document_id: uuid.UUID | None = Field(
        default=None, description="PDF-Nachweis des unterschriebenen Mandats"
    )
    evidence_channel: Literal["phone", "letter", "email", "other"] | None = Field(
        default=None, description="Weg der Erteilung, wenn kein PDF vorliegt"
    )
    evidence_note: str | None = Field(default=None, max_length=500)

    @field_validator("creditor_id")
    @classmethod
    def _ci(cls, value: str) -> str:
        try:
            return normalise_creditor_id(value)
        except InvalidSepaValueError as exc:
            raise ValueError(str(exc)) from None

    @field_validator("reference")
    @classmethod
    def _ref(cls, value: str) -> str:
        try:
            return check_mandate_reference(value)
        except InvalidSepaValueError as exc:
            raise ValueError(str(exc)) from None


class MandateOut(_Out):
    id: uuid.UUID
    party_id: uuid.UUID
    legal_entity_id: uuid.UUID
    contact_bank_account_id: uuid.UUID
    iban_masked: str | None = None
    reference: str
    creditor_id: str
    signed_at: date
    type: MandateType
    sequence: MandateSequence
    valid_until: date | None
    status: MandateStatus
    document_id: uuid.UUID | None
    evidence_channel: str | None
    evidence_note: str | None


class DepositIn(_In):
    kind: DepositKind
    amount_due: Money = Field(gt=0, max_digits=14, decimal_places=2)
    installments: int = Field(default=1, ge=1, le=12)
    valid_from: date
    valid_to: date | None = None
    property_bank_account_id: uuid.UUID | None = None
    interest_rule: str | None = None


class DepositMovementIn(_In):
    date: date
    amount: Money = Field(gt=0, max_digits=14, decimal_places=2)
    kind: DepositMovementKind
    reason: str | None = None

    @model_validator(mode="after")
    def _offset_reason(self) -> Self:
        if (
            self.kind in (DepositMovementKind.OFFSET, DepositMovementKind.PAYOUT)
            and not self.reason
        ):
            raise ValueError("Auszahlung und Verrechnung brauchen eine Begründung")
        return self


class DepositMovementOut(DepositMovementIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    review_required: bool = False


class DepositOut(_Out):
    id: uuid.UUID
    contract_id: uuid.UUID
    kind: DepositKind
    amount_due: Money
    installments: int
    valid_from: date
    valid_to: date | None
    property_bank_account_id: uuid.UUID | None
    interest_rule: str | None
    status: str
    received: Money = Money("0.00")
    balance: Money = Money("0.00")
    outstanding: Money = Money("0.00")
    movements: list[DepositMovementOut] = Field(default_factory=list)


class OccupancyRow(BaseModel):
    unit_id: uuid.UUID
    unit_number: str
    unit_label: str | None
    unit_type: str
    tenancy_contract_id: uuid.UUID | None
    tenant_party: str | None
    ownership_contract_id: uuid.UUID | None
    owner_party: str | None
    vacant: bool
