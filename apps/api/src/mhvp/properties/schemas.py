"""API schemas for properties, buildings, units and related master data (6.2, 6.9.1)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from mhvp.contacts.validation import InvalidValueError, normalise_iban
from mhvp.properties.models import (
    AllocationKind,
    BankAccountKind,
    LegalEntityKind,
    MaintenanceKind,
    ManagementMode,
    ManagementType,
    MeterConnection,
    Occupant,
    PropertyStatus,
    ReadingSource,
    UnitType,
    ValueSource,
    VatOption,
)

Qty = Decimal  # NUMERIC(20,8) in the database (6.9.8)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _Period(_In):
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to liegt vor valid_from")
        return self


class PropertyIn(_In):
    number: str = Field(pattern=r"^[0-9]{3}$", description="Objektnummer NNN")
    name: str = Field(min_length=2, max_length=200)
    management_type: ManagementType
    management_mode: ManagementMode = ManagementMode.THIRD_PARTY
    property_type_code: str | None = None
    street: str | None = Field(default=None, max_length=200)
    house_number: str | None = Field(default=None, max_length=20)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = None
    country: str = Field(default="DE", pattern=r"^[A-Z]{2}$")
    municipality_code: str | None = None
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    land_registry_district: str | None = None
    land_registry_sheet: str | None = None
    parcel: str | None = None
    built_area_sqm: Qty | None = Field(default=None, ge=0)
    unbuilt_area_sqm: Qty | None = Field(default=None, ge=0)
    sealed_area_sqm: Qty | None = Field(default=None, ge=0)
    garden_use: str | None = Field(default=None, pattern=r"^(none|yes|partial)$")
    garden_notes: str | None = None
    renovation_flag: bool = False
    renovation_notes: str | None = None
    allocation_loss_risk_percent: Qty | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    manager_user_id: uuid.UUID | None = None
    managed_from: date | None = None
    managed_to: date | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    # Energieausweis (A63): entered from the certificate, no derivation. Values are used by
    # listings (prefill), the exposé draft and the OpenImmo completeness check.
    energy_certificate_type: str | None = Field(default=None, pattern=r"^(verbrauch|bedarf)$")
    energy_certificate_value: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    energy_certificate_source: str | None = Field(default=None, max_length=32)
    energy_certificate_construction_year: int | None = Field(default=None, ge=1500, le=2100)
    energy_certificate_issued_on: date | None = None
    energy_certificate_valid_until: date | None = None
    energy_certificate_class: str | None = Field(default=None, max_length=4)

    @model_validator(mode="after")
    def _energy_certificate_dates(self) -> Self:
        issued, valid = self.energy_certificate_issued_on, self.energy_certificate_valid_until
        if issued is not None and valid is not None and valid < issued:
            raise ValueError("Gültigkeit des Energieausweises liegt vor dem Ausstellungsdatum.")
        return self


class LegalEntityOut(_Out):
    id: uuid.UUID
    kind: LegalEntityKind
    name: str
    party_id: uuid.UUID | None


class PropertyOut(PropertyIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    status: PropertyStatus
    version: int
    legal_entities: list[LegalEntityOut] = Field(default_factory=list)


class PropertySummary(_Out):
    id: uuid.UUID
    number: str
    name: str
    management_type: ManagementType
    status: PropertyStatus
    city: str | None
    street: str | None
    house_number: str | None


class PropertyPage(BaseModel):
    items: list[PropertySummary]
    total: int
    page: int
    page_size: int


class StatusChange(_In):
    status: PropertyStatus


class BuildingIn(_In):
    name: str = Field(min_length=1, max_length=200)
    street: str | None = None
    house_number: str | None = None
    built_area_sqm: Qty | None = Field(default=None, ge=0)
    sealed_area_sqm: Qty | None = Field(default=None, ge=0)
    roof_area_sqm: Qty | None = Field(default=None, ge=0)
    construction_year: int | None = Field(default=None, ge=1000, le=2100)
    renovation_level: str | None = None
    construction_type_code: str | None = None
    building_type_code: str | None = None
    floors: int | None = Field(default=None, ge=0, le=200)
    windows: int | None = Field(default=None, ge=0)
    total_area_sqm: Qty | None = Field(default=None, ge=0)
    living_commercial_area_sqm: Qty | None = Field(default=None, ge=0)
    heated_area_sqm: Qty | None = Field(default=None, ge=0)
    window_area_sqm: Qty | None = Field(default=None, ge=0)
    hallway_area_sqm: Qty | None = Field(default=None, ge=0)
    gross_floor_area_sqm: Qty | None = Field(default=None, ge=0)
    elevator: bool = False
    cellar_rooms: int | None = Field(default=None, ge=0)
    heritage_protection: bool = False
    heritage_notes: str | None = None
    energy_certificate_type: str | None = None
    energy_certificate_value: Qty | None = None
    energy_certificate_valid_until: date | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class BuildingOut(BuildingIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    property_id: uuid.UUID


class UnitIn(_In):
    building_id: uuid.UUID
    number: str = Field(min_length=1, max_length=20)
    label: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    unit_type: UnitType
    internal_name: str | None = None
    rooms: Decimal | None = Field(default=None, ge=0, max_digits=4, decimal_places=1)
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: int | None = Field(default=None, ge=0)
    total_area_sqm: Qty | None = Field(default=None, ge=0)
    living_area_sqm: Qty | None = Field(default=None, ge=0)
    floor: str | None = None
    last_modernization_year: int | None = Field(default=None, ge=1000, le=2100)
    is_fictional: bool = False
    cellar_number: str | None = None
    features: str | None = None
    street: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    city: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class AllocationValueIn(_Period):
    allocation_key_id: uuid.UUID
    value: Qty = Field(ge=0)
    source: ValueSource = ValueSource.MANUAL


class AllocationValueOut(_Out):
    id: uuid.UUID
    unit_id: uuid.UUID
    allocation_key_id: uuid.UUID
    key_code: str | None = None
    value: Qty
    valid_from: date
    valid_to: date | None
    source: ValueSource


class UnitOut(UnitIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    property_id: uuid.UUID
    allocation_values: list[AllocationValueOut] = Field(default_factory=list)
    vat_option: VatOption | None = None


class AllocationKeyIn(_In):
    code: str = Field(pattern=r"^[A-Z0-9_]{1,32}$")
    name: str = Field(min_length=2, max_length=200)
    unit_of_measure: str = Field(min_length=1, max_length=16)
    default_value: Qty | None = None
    kind: AllocationKind
    meter_type_code: str | None = None
    sort_order: int = 0


class AllocationKeyOut(AllocationKeyIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    is_template_derived: bool


class VatOptionIn(_Period):
    option: VatOption
    occupant: Occupant


class OwnerIn(_Period):
    party_id: uuid.UUID
    share_percent: Qty | None = Field(default=None, ge=0, le=100)


class OwnerOut(_Out):
    id: uuid.UUID
    party_id: uuid.UUID
    share_percent: Qty | None
    valid_from: date
    valid_to: date | None
    legal_entity_id: uuid.UUID | None = None


class BankAccountIn(_Period):
    legal_entity_id: uuid.UUID
    kind: BankAccountKind
    iban: str
    bic: str | None = Field(default=None, pattern=r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
    bank_name: str | None = None
    holder: str = Field(min_length=2, max_length=200)
    notes: str | None = None

    @field_validator("iban")
    @classmethod
    def _iban(cls, value: str) -> str:
        try:
            return normalise_iban(value)
        except InvalidValueError as exc:
            raise ValueError(str(exc)) from None


class BankAccountOut(_Out):
    id: uuid.UUID
    legal_entity_id: uuid.UUID
    kind: BankAccountKind
    iban_masked: str
    bic: str | None
    bank_name: str | None
    holder: str
    segregated: bool
    valid_from: date
    valid_to: date | None


class PropertyContactIn(_Period):
    contact_id: uuid.UUID
    category_code: str
    visible_in_portal_for: list[str] = Field(default_factory=list)

    @field_validator("visible_in_portal_for")
    @classmethod
    def _audience(cls, value: list[str]) -> list[str]:
        if not set(value) <= {"tenant", "owner", "provider"}:
            raise ValueError("erlaubt: tenant, owner, provider")
        return sorted(set(value))


class PropertyContactOut(PropertyContactIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID


class MeterIn(_Period):
    unit_id: uuid.UUID | None = None
    meter_type_code: str
    number: str = Field(min_length=1, max_length=100)
    malo_id: str | None = Field(default=None, max_length=33)
    name: str | None = None
    connection: MeterConnection = MeterConnection.SUB
    location: str | None = None
    calibration_due_date: date | None = None
    remote_readable: bool = False
    notes: str | None = None


class MeterOut(MeterIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID


class ReadingIn(_In):
    read_at: date
    value: Qty = Field(ge=0)
    estimated: bool = False
    source: ReadingSource = ReadingSource.MANUAL
    notes: str | None = None


class ReadingOut(ReadingIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    meter_id: uuid.UUID
    implausible: bool = False


class ProviderIn(_Period):
    contact_id: uuid.UUID
    contract_type_code: str
    notice_period: str | None = None
    contact_bank_account_id: uuid.UUID | None = None
    create_default_bank_rule: bool = False
    categories: list[str] = Field(default_factory=list)
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ProviderOut(ProviderIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID


class MaintenanceIn(_In):
    unit_id: uuid.UUID | None = None
    kind: MaintenanceKind
    title: str = Field(min_length=2, max_length=200)
    due_date: date | None = None
    remind_before: str | None = Field(default=None, pattern=r"^(14d|1m|3m|6m)$")
    interval_months: int | None = Field(default=None, ge=1, le=240)
    provider_relation_id: uuid.UUID | None = None


class MaintenanceOut(MaintenanceIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    status: str


class CatalogEntryIn(_In):
    code: str = Field(pattern=r"^[a-z0-9_]{1,63}$")
    label: str = Field(min_length=1, max_length=200)
    sort_order: int = 0


class CatalogEntryOut(CatalogEntryIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    catalog: str
    active: bool


class CustomFieldIn(_In):
    entity_type: str = Field(pattern=r"^(property|building|unit|service_provider_relation)$")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    label: str = Field(min_length=1, max_length=200)
    field_type: str = Field(pattern=r"^(text|number|date|bool)$")
    required: bool = False


class CustomFieldOut(CustomFieldIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
