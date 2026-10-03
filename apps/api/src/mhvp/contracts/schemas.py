"""API schemas for contracts (6.3, 6.9.2, 6.9.11)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Self

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


class ProrationMethod(StrEnum):
    """M13-01: contract rule for a start, end or amount change within a month."""

    CALENDAR_DAYS = "calendar_days"
    THIRTY_360 = "thirty_360"
    FULL_MONTH = "full_month"


class PaymentMode(StrEnum):
    """M13-02: instalment due in advance or in arrears."""

    ADVANCE = "advance"
    ARREARS = "arrears"


class AmountBasis(StrEnum):
    """M13-02: contract amount per month or per instalment."""

    PER_MONTH = "per_month"
    PER_INSTALMENT = "per_instalment"


class ContractIn(_In):
    kind: ContractKind
    unit_id: uuid.UUID
    party_id: uuid.UUID | None = Field(
        default=None, description="Vertragspartei; alternativ contact_id (genau eines)"
    )
    contact_id: uuid.UUID | None = Field(
        default=None,
        description="Kontakt statt Partei: wird auf die eigene Partei des Kontakts aufgelöst",
    )
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
    proration_method: ProrationMethod | None = Field(
        default=None,
        description="Zeitanteilsregel des Vertrags (M13-01); leer: Standard des Mandanten",
    )
    sev_enabled: bool = False
    sev_fee_debtor_party_id: uuid.UUID | None = None
    sev_fee_debtor_contact_id: uuid.UUID | None = Field(
        default=None, description="Alternative zu sev_fee_debtor_party_id (Kontakt)"
    )
    title_transfer_date: date | None = None
    benefit_burden_date: date | None = None
    acquisition_kind: AcquisitionKind | None = None
    special_succession_liability: bool = False
    notes: str | None = None
    move_in_on: date | None = Field(default=None, description="Kalendertermin Einzug")
    move_out_on: date | None = Field(default=None, description="Kalendertermin Auszug")
    custom_fields: dict[str, Any] = Field(default_factory=dict, description="Zusatzfelder (4.11)")

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if (self.party_id is None) == (self.contact_id is None):
            raise ValueError("Genau eine Angabe: party_id oder contact_id")
        if self.sev_fee_debtor_party_id is not None and self.sev_fee_debtor_contact_id is not None:
            raise ValueError(
                "Höchstens eine Angabe: sev_fee_debtor_party_id oder sev_fee_debtor_contact_id"
            )
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date liegt vor start_date")
        if (
            self.move_in_on is not None
            and self.move_out_on is not None
            and self.move_out_on < self.move_in_on
        ):
            raise ValueError("Auszug liegt vor dem Einzug")
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


class ContractNotesPatch(_In):
    """Inline editing of a contract (AP8, operator decision (c) 4): only remarks and the
    dunning block change in place; payments and terms stay versioned (7.4)."""

    notes: str | None = None
    dunning_block: bool | None = None
    dunning_block_reason: str | None = None


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
    proration_method: ProrationMethod | None = None
    notes: str | None = None
    move_in_on: date | None = None
    move_out_on: date | None = None


class TerminationReadingIn(_In):
    """Meter reading recorded with the termination (4.5 Aktionen)."""

    meter_id: uuid.UUID
    value: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    read_at: date | None = Field(default=None, description="Standard: Vertragsende")


class TerminationReadingOut(_Out):
    id: uuid.UUID
    contract_id: uuid.UUID
    meter_id: uuid.UUID
    meter_reading_id: uuid.UUID | None
    value: Decimal
    read_at: date


class TerminationIn(_In):
    end_date: date
    termination_date: date | None = Field(default=None, description="Datum der Kündigungserklärung")
    termination_reason: str | None = None
    move_out_on: date | None = Field(default=None, description="Kalendertermin Auszug")
    meter_readings: list[TerminationReadingIn] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _unique_meters(self) -> Self:
        meters = [r.meter_id for r in self.meter_readings]
        if len(meters) != len(set(meters)):
            raise ValueError("Je Zähler nur ein Zählerstand")
        return self


class ContractAllocationValueIn(_In):
    """Contract related allocation key value with period (4.5 Eigenschaften)."""

    allocation_key_id: uuid.UUID
    value: Decimal = Field(ge=0, max_digits=20, decimal_places=8)
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def _period(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to liegt vor valid_from")
        return self


class ContractAllocationValueOut(_Out):
    id: uuid.UUID
    contract_id: uuid.UUID
    allocation_key_id: uuid.UUID
    allocation_key_code: str | None = None
    allocation_key_name: str | None = None
    unit_of_measure: str | None = None
    value: Decimal
    valid_from: date
    valid_to: date | None


class OwnershipTransferIn(_In):
    """Eigentümerwechsel (D16, D17): either the party of the acquirer or a contact whose own
    party (single member, role primary) is looked up or created. The standing amounts of the
    current ownership (payments, payment schedule, allocation values valid on the title
    transfer date) are carried over to the new ownership as a factual copy from that date on
    when ``carry_over_amounts`` is set. Nothing here splits an annual statement between
    seller and acquirer (rule W07, release point P01 stay open)."""

    new_party_id: uuid.UUID | None = None
    new_contact_id: uuid.UUID | None = Field(
        default=None, description="Erwerber als Kontakt; die Vertragspartei wird ermittelt"
    )
    title_transfer_date: date
    benefit_burden_date: date | None = None
    acquisition_kind: AcquisitionKind
    special_succession_liability: bool = False
    sev_enabled: bool = False
    carry_over_amounts: bool = Field(
        default=True,
        description="Sollbeträge, Zahlungsplan und Umlagewerte ab dem Eigentumsübergang übernehmen",
    )
    notes: str | None = Field(default=None, max_length=10_000)
    document_id: uuid.UUID | None = Field(
        default=None,
        description="Nachweis (z. B. Grundbuchauszug), wird mit dem neuen Vertrag verknüpft",
    )

    @model_validator(mode="after")
    def _one_acquirer(self) -> Self:
        if (self.new_party_id is None) == (self.new_contact_id is None):
            raise ValueError("Genau eine Angabe: new_party_id oder new_contact_id")
        return self


class PaymentIn(_In):
    payment_type_code: str
    net: Money = Field(max_digits=14, decimal_places=2)
    vat_percent: Decimal = Field(default=Decimal(0), ge=0, le=100, max_digits=20, decimal_places=8)
    gross: Money = Field(max_digits=14, decimal_places=2)
    valid_from: date
    valid_to: date | None = None
    reason: PaymentReason = PaymentReason.INITIAL
    document_id: uuid.UUID | None = None
    revenue_account_id: uuid.UUID | None = Field(default=None, description="Ertragskonto (M5-01)")
    # AE08 (P07-02): earmarked reserve of a reserve component; one payment type per reserve.
    reserve_id: uuid.UUID | None = Field(
        default=None, description="Zweckrücklage der Rücklagenkomponente (P07-02)"
    )


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
    revenue_account_id: uuid.UUID | None = None
    reserve_id: uuid.UUID | None = None  # M24-01: earmarked reserve of the standing amount


class ScheduleIn(_In):
    # M13-01a: ``None`` übernimmt den Mandanten-Standard aus ``TenantSettings.receivable_rules
    # .payment_interval`` (Router ``add_schedule``), ohne Mandantenvorgabe monatlich.
    interval: PaymentInterval | None = None
    due_day_rule: DueDayRule = DueDayRule.DAY
    due_day: int = Field(default=3, ge=1, le=31)
    valid_from: date
    valid_to: date | None = None
    payment_mode: PaymentMode = PaymentMode.ADVANCE
    amount_basis: AmountBasis = AmountBasis.PER_MONTH


class ScheduleOut(ScheduleIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID


class OwnershipTransferPreviewOut(_Out):
    """What ``POST /contracts/{id}/ownership-transfer`` would do on the given date."""

    contract_id: uuid.UUID
    party_id: uuid.UUID
    party_name: str | None
    title_transfer_date: date
    old_end_date: date
    new_start_date: date
    payments: list[PaymentOut]
    schedules: list[ScheduleOut]
    allocation_values: list[ContractAllocationValueOut]
    # Rule W07 (statement split between seller and acquirer) is not released; P01 is open.
    statement_split: Literal["not_implemented"] = "not_implemented"


class DebtorAccountOut(_Out):
    id: uuid.UUID
    legal_entity_id: uuid.UUID
    number: str
    name: str


class ContractMemberOut(_Out):
    """Contact behind the contract party (tenant or owner), for the list display."""

    contact_id: uuid.UUID
    name: str
    role: str


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
    proration_method: ProrationMethod | None = None
    sev_enabled: bool
    sev_fee_debtor_party_id: uuid.UUID | None
    title_transfer_date: date | None
    benefit_burden_date: date | None
    acquisition_kind: AcquisitionKind | None
    special_succession_liability: bool
    notes: str | None
    move_in_on: date | None = None
    move_out_on: date | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    supersedes_contract_id: uuid.UUID | None
    source: str | None = None
    approval_status: str = "approved"
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    payments: list[PaymentOut] = Field(default_factory=list)
    schedules: list[ScheduleOut] = Field(default_factory=list)
    # Display context (operator feedback 28.09.2026): which property, unit and persons the
    # contract belongs to; read only, derived from the master data.
    property_number: str | None = None
    property_name: str | None = None
    property_address: str | None = None
    unit_number: str | None = None
    unit_label: str | None = None
    party_name: str | None = None
    members: list[ContractMemberOut] = Field(default_factory=list)


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
    document_id: uuid.UUID = Field(description="Nachweis des unterschriebenen Mandats (Pflicht)")
    payment_type_codes: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Ertragsarten (Katalog payment_type), die das Mandat abdeckt; leer = alle",
    )
    exclude_special_levy: bool = Field(
        default=False, description="Sonderumlagen vom Einzug über dieses Mandat ausschließen"
    )

    @field_validator("payment_type_codes")
    @classmethod
    def _codes(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Ertragsarten doppelt angegeben")
        return cleaned

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
    document_id: uuid.UUID
    payment_type_codes: list[str] = Field(default_factory=list)
    exclude_special_levy: bool = False
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class DepositIn(_In):
    kind: DepositKind
    amount_due: Money = Field(gt=0, max_digits=14, decimal_places=2)
    installments: int = Field(default=1, ge=1, le=12)
    valid_from: date
    valid_to: date | None = None
    property_bank_account_id: uuid.UUID | None = None
    interest_rule: str | None = None

    @model_validator(mode="after")
    def _period(self) -> Self:
        # AM02 / GAJ-604: same rule as the DB check ck_deposit_period_order (0449).
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to liegt vor valid_from")
        return self


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
    documents: list[str] = Field(default_factory=list)
    received: Money = Money("0.00")
    balance: Money = Money("0.00")
    outstanding: Money = Money("0.00")
    movements: list[DepositMovementOut] = Field(default_factory=list)
    # AI18 (GAH-111): non blocking review hints (switch deposit_limit_hint_enabled, default off).
    limit_hints: list[str] = Field(default_factory=list)


class DepositListRow(BaseModel):
    """Row of the deposit list ``GET /deposits`` (4.5 Kaution)."""

    id: uuid.UUID
    contract_id: uuid.UUID
    contract_number: str
    property_id: uuid.UUID
    property_number: str
    unit_id: uuid.UUID
    unit_number: str
    party_id: uuid.UUID
    party_name: str
    kind: DepositKind
    status: str
    amount_due: Money
    received: Money
    balance: Money
    outstanding: Money
    valid_from: date
    valid_to: date | None
    contract_end_date: date | None


class VacancyRow(BaseModel):
    """Vacant let unit as of a date (``GET /properties/{id}/vacancies``)."""

    unit_id: uuid.UUID
    unit_number: str
    unit_label: str | None
    unit_type: str
    vacant_since: date | None = Field(
        description="Tag nach dem letzten Mietende, leer = nie vermietet"
    )
    previous_contract_id: uuid.UUID | None
    ownership_contract_id: uuid.UUID | None
    owner_party: str | None


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


class PendingContractOut(BaseModel):
    """Imported contract awaiting management approval before the receivable run."""

    id: uuid.UUID
    number: str
    kind: ContractKind
    property_id: uuid.UUID
    property_number: str
    property_name: str
    unit_id: uuid.UUID
    unit_number: str
    party_id: uuid.UUID
    party_name: str
    start_date: date
    monthly_amount: Decimal = Field(description="Summe der am Beginn gültigen Zahlungen (brutto)")
    source: str | None
    notes: str | None


class ApproveIn(_In):
    """Either ``ids`` or ``all`` (optionally limited to one ``source``)."""

    ids: list[uuid.UUID] = Field(default_factory=list, max_length=5000)
    all: bool = False
    source: str | None = None

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        if bool(self.ids) == self.all:
            raise ValueError("Entweder ids oder all angeben")
        return self


class ApproveOut(BaseModel):
    approved: int
    ids: list[uuid.UUID]


class RejectImportIn(_In):
    reason: str | None = Field(default=None, max_length=500)


class RejectImportOut(BaseModel):
    id: uuid.UUID
    approval_status: Literal["rejected"]
    end_date: date


# Follow-up maintenance (package P16) ---------------------------------------------------


class ContractCustomFieldsPatch(_In):
    """In place update of the custom fields of a contract (M5-02); keys are merged, a key
    with ``null`` removes the value."""

    custom_fields: dict[str, Any]


class ContractPaymentPatch(_In):
    """Correction of a payment row (M5-07). Amounts, period and type only while no posted
    receivable uses the row; ``revenue_account_id`` and ``document_id`` always."""

    net: Money | None = Field(default=None, max_digits=14, decimal_places=2)
    vat_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=20, decimal_places=8)
    gross: Money | None = Field(default=None, max_digits=14, decimal_places=2)
    valid_from: date | None = None
    valid_to: date | None = None
    reason: PaymentReason | None = None
    document_id: uuid.UUID | None = None
    revenue_account_id: uuid.UUID | None = None


class ContractSchedulePatch(_In):
    """Correction of a payment plan (M5-07), only while no posted receivable uses it."""

    interval: PaymentInterval | None = None
    due_day_rule: DueDayRule | None = None
    due_day: int | None = Field(default=None, ge=1, le=31)
    valid_from: date | None = None
    valid_to: date | None = None
    payment_mode: PaymentMode | None = None
    amount_basis: AmountBasis | None = None


class DepositPatch(_In):
    """Change of a deposit (M5-06). Amount and instalments only while it has no movements."""

    amount_due: Money | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    installments: int | None = Field(default=None, ge=1, le=12)
    valid_to: date | None = None
    property_bank_account_id: uuid.UUID | None = None
    interest_rule: str | None = None
    documents: list[uuid.UUID] | None = Field(default=None, max_length=50)
    status: Literal["open", "active", "settled"] | None = None


class DepositHintSettingOut(BaseModel):
    """AI18 (GAH-111): tenant switch of the non blocking deposit hint (default off)."""

    deposit_limit_hint_enabled: bool = False
    factor_months: Decimal = Decimal(3)
    max_installments: int = 3
    rent_payment_codes: list[str] = Field(default_factory=lambda: ["rent"])


class DepositHintSettingIn(_In):
    deposit_limit_hint_enabled: bool
    factor_months: Decimal = Field(gt=0, le=24, max_digits=10, decimal_places=4)
    max_installments: int = Field(ge=1, le=12)
    rent_payment_codes: list[str] = Field(min_length=1, max_length=20)
