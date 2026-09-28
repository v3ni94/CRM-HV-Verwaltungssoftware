"""API schemas for properties, buildings, units and related master data (6.2, 6.9.1)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from mhvp.contacts.validation import InvalidValueError, normalise_iban
from mhvp.properties.catalogs import (
    CUSTOM_FIELD_ENTITIES,
    CUSTOM_FIELD_TYPES,
    CUSTOM_FIELD_UNIQUENESS,
)
from mhvp.properties.models import (
    AllocationKind,
    BankAccountKind,
    BillingPeriodKind,
    ExemptionCertStatus,
    LegalEntityKind,
    MaintenanceKind,
    ManagementMode,
    ManagementType,
    MeterConnection,
    Occupant,
    PropertyStatus,
    ReadingSource,
    TerminatedBy,
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
    owner_missing: bool = Field(
        default=False, description="Mietverwaltung ohne aktiven Objekteigentümer"
    )


class PropertyPage(BaseModel):
    items: list[PropertySummary]
    total: int
    page: int
    page_size: int


class StatusChange(_In):
    status: PropertyStatus


class PropertyTerminationIn(_In):
    """Beendigung des Verwaltungsverhältnisses (operator 27.09.2026)."""

    terminated_by: TerminatedBy
    notice_date: date = Field(description="Datum der Kündigung")
    effective_date: date = Field(description="Ende der Verwaltung")
    successor_manager_contact_id: uuid.UUID | None = None
    successor_owner_contact_id: uuid.UUID | None = None
    notice_document_id: uuid.UUID | None = Field(
        default=None, description="Kündigungsschreiben (Dokument)"
    )
    note: str | None = Field(default=None, max_length=4000)


class PropertyTerminationOut(_Out):
    id: uuid.UUID
    property_id: uuid.UUID
    terminated_by: TerminatedBy
    notice_date: date
    effective_date: date
    previous_status: PropertyStatus
    successor_manager_contact_id: uuid.UUID | None
    successor_manager_name: str | None = None
    successor_owner_contact_id: uuid.UUID | None
    successor_owner_name: str | None = None
    notice_document_id: uuid.UUID | None
    notice_document_title: str | None = None
    note: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    reactivated_at: datetime | None
    reactivated_by_user_id: uuid.UUID | None


class BuildingIn(_In):
    name: str = Field(min_length=1, max_length=200)
    street: str | None = None
    house_number: str | None = None
    address_addition: str | None = Field(default=None, max_length=200)
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
    # Energieausweis (4.3, A63): only on the building. Entered from the certificate, no
    # derivation. Listings copy the values on creation, the exposé draft reads them.
    energy_certificate_law: str | None = Field(default=None, pattern=r"^(geg|enev_2014)$")
    energy_certificate_type: str | None = Field(default=None, pattern=r"^(verbrauch|bedarf)$")
    energy_final_heat_kwh: Qty | None = Field(default=None, ge=0, description="kWh/(m²a)")
    energy_hot_water_included: bool = False
    energy_final_electricity_kwh: Qty | None = Field(default=None, ge=0, description="kWh/(m²a)")
    heating_type_code: str | None = Field(default=None, pattern=r"^(etage|ofen|zentral)$")
    energy_sources: list[str] = Field(default_factory=list, description="Energieträger (B.8)")
    energy_certificate_class: str | None = Field(default=None, max_length=4)
    energy_certificate_construction_year: int | None = Field(default=None, ge=1500, le=2100)
    energy_certificate_issued_on: date | None = None
    energy_certificate_valid_until: date | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("energy_sources")
    @classmethod
    def _sources(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        if any(len(v) > 63 for v in cleaned):
            raise ValueError("Energieträger höchstens 63 Zeichen")
        return list(dict.fromkeys(cleaned))

    @model_validator(mode="after")
    def _energy_certificate_dates(self) -> Self:
        issued, valid = self.energy_certificate_issued_on, self.energy_certificate_valid_until
        if issued is not None and valid is not None and valid < issued:
            raise ValueError("Gültigkeit des Energieausweises liegt vor dem Ausstellungsdatum.")
        return self


class BuildingOut(BuildingIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    property_id: uuid.UUID
    version: int


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
    # 4.4: sub community, commission, deposit amount and vacancy VAT option are informational;
    # no receivable or posting derives from them.
    sub_community_id: uuid.UUID | None = None
    commission: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    commission_note: str | None = None
    deposit_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    vacancy_vat_option: VatOption | None = None


class AllocationValueIn(_Period):
    allocation_key_id: uuid.UUID
    value: Qty = Field(ge=0)
    source: ValueSource = ValueSource.MANUAL


class AllocationValueOut(_Out):
    id: uuid.UUID
    unit_id: uuid.UUID
    allocation_key_id: uuid.UUID
    key_code: str | None = None
    key_name: str | None = None
    value: Qty
    valid_from: date
    valid_to: date | None
    source: ValueSource


class VacancyAllocationValueIn(_Period):
    allocation_key_id: uuid.UUID
    value: Qty = Field(ge=0)


class VacancyAllocationValueOut(_Out):
    id: uuid.UUID
    unit_id: uuid.UUID
    allocation_key_id: uuid.UUID
    key_code: str | None = None
    key_name: str | None = None
    value: Qty
    valid_from: date
    valid_to: date | None


class OccupantMemberOut(BaseModel):
    contact_id: uuid.UUID
    display_name: str
    share_percent: Decimal | None = None


class OccupantOut(BaseModel):
    """One ownership or tenancy contract of a unit with its party, for display."""

    contract_id: uuid.UUID
    contract_number: str
    kind: str
    party_id: uuid.UUID
    party_name: str
    start_date: date
    end_date: date | None
    members: list[OccupantMemberOut] = Field(default_factory=list)
    rent_gross: Decimal | None = None


class UnitOccupantsOut(BaseModel):
    owner: OccupantOut | None = None
    tenant: OccupantOut | None = None
    history: list[OccupantOut] = Field(default_factory=list)


class UnitOut(UnitIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    property_id: uuid.UUID
    version: int
    allocation_values: list[AllocationValueOut] = Field(default_factory=list)
    vat_option: VatOption | None = None
    # Only filled with ?with_occupants=true: current owner and tenant at the reference date.
    owner: OccupantOut | None = None
    tenant: OccupantOut | None = None


class AllocationKeyIn(_In):
    code: str = Field(pattern=r"^[A-Z0-9_]{1,32}$")
    name: str = Field(min_length=2, max_length=200)
    unit_of_measure: str = Field(min_length=1, max_length=16)
    default_value: Qty | None = None
    kind: AllocationKind
    meter_type_code: str | None = None
    sort_order: int = 0
    # Reference sum of the key in the property (C1); entered by the operator, no default. The
    # sum check of the unit values against it is a warning only, never a block.
    expected_total: Qty | None = Field(default=None, ge=0)


class AllocationKeyPatch(_In):
    """Editable fields of an allocation key; the code is immutable because rows and imports
    reference it (C1)."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    unit_of_measure: str | None = Field(default=None, min_length=1, max_length=16)
    default_value: Qty | None = None
    kind: AllocationKind | None = None
    meter_type_code: str | None = None
    sort_order: int | None = None
    expected_total: Qty | None = Field(default=None, ge=0)


class AllocationKeyOut(AllocationKeyIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    is_template_derived: bool


class AllocationSummaryKeyOut(BaseModel):
    """One key of the property with the sum of the unit values valid at the reference date."""

    id: uuid.UUID
    code: str
    name: str
    unit_of_measure: str
    kind: AllocationKind
    expected_total: Qty | None
    total: Qty
    units_with_value: int
    units_without_value: int
    # total minus expected_total; None without an expected total. Information only (C1).
    difference: Qty | None

    @field_serializer("total", "difference", "expected_total", when_used="json")
    def _plain(self, value: Decimal | None) -> str | None:
        # Plain notation ("0.00000000", never "0E-8") so the CRM formats sums like values.
        return None if value is None else f"{value:f}"


class AllocationSummaryValueOut(BaseModel):
    id: uuid.UUID
    unit_id: uuid.UUID
    allocation_key_id: uuid.UUID
    value: Qty
    valid_from: date
    valid_to: date | None
    source: ValueSource


class AllocationSummaryUnitOut(BaseModel):
    id: uuid.UUID
    number: str
    label: str | None
    is_fictional: bool


class AllocationSummaryOut(BaseModel):
    """Key values of all units of a property at one reference date, with sums per key
    (C1). The CRM shows a deviation from ``expected_total`` as a warning; the API never
    blocks on it."""

    as_of: date
    keys: list[AllocationSummaryKeyOut]
    units: list[AllocationSummaryUnitOut]
    values: list[AllocationSummaryValueOut]


class VatOptionIn(_Period):
    option: VatOption
    occupant: Occupant


class OwnerIn(_Period):
    party_id: uuid.UUID
    share_percent: Qty | None = Field(default=None, ge=0, le=100)
    clearing_account_id: uuid.UUID | None = Field(default=None, description="Verrechnungskonto")
    power_of_attorney_document_id: uuid.UUID | None = Field(
        default=None, description="Verwaltervollmacht (Dokument)"
    )
    tax_advisor_contact_id: uuid.UUID | None = Field(default=None, description="Steuerberater")


class OwnerOut(_Out):
    id: uuid.UUID
    party_id: uuid.UUID
    share_percent: Qty | None
    valid_from: date
    valid_to: date | None
    legal_entity_id: uuid.UUID | None = None
    clearing_account_id: uuid.UUID | None = None
    power_of_attorney_document_id: uuid.UUID | None = None
    tax_advisor_contact_id: uuid.UUID | None = None


class OwnerDetailsIn(_In):
    """Clearing account, power of attorney and tax advisor of an owner entry (4.2)."""

    clearing_account_id: uuid.UUID | None = None
    power_of_attorney_document_id: uuid.UUID | None = None
    tax_advisor_contact_id: uuid.UUID | None = None


class OwnerSetIn(_In):
    contact_id: uuid.UUID
    valid_from: date | None = Field(
        default=None, description="Beginn; ohne Angabe Verwaltungsbeginn oder 1. Januar des Jahres"
    )
    share_percent: Qty | None = Field(default=None, gt=0, le=100)
    replace: bool = Field(
        default=False, description="Bestehenden Eigentümer zum Vortag beenden und ersetzen"
    )


class CurrentOwnerOut(BaseModel):
    id: uuid.UUID
    party_id: uuid.UUID
    party_name: str
    contact_id: uuid.UUID | None
    contact_name: str | None
    share_percent: Qty | None
    valid_from: date
    valid_to: date | None
    legal_entity_id: uuid.UUID | None
    clearing_account_id: uuid.UUID | None = None
    power_of_attorney_document_id: uuid.UUID | None = None
    tax_advisor_contact_id: uuid.UUID | None = None


class OwnerSetOut(BaseModel):
    status: Literal["created", "unchanged", "replaced"]
    owner: CurrentOwnerOut
    ended: list[CurrentOwnerOut] = Field(default_factory=list)


class BankAccountIn(_Period):
    legal_entity_id: uuid.UUID
    kind: BankAccountKind
    iban: str
    bic: str | None = Field(default=None, pattern=r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
    bank_name: str | None = None
    holder: str = Field(min_length=2, max_length=200)
    notes: str | None = None
    ledger_account_id: uuid.UUID | None = Field(default=None, description="Zugeordnetes Sachkonto")
    is_default: bool = Field(
        default=False,
        description=(
            "Standardkonto des Rechtsträgers (höchstens eines je Rechtsträger); Zahlungsziel "
            "im Mahnschreiben (M16-13). Nicht für Kautionskonten."
        ),
    )

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
    notes: str | None = None
    ledger_account_id: uuid.UUID | None = None
    is_default: bool = False


class BillingPeriodIn(_In):
    kind: BillingPeriodKind
    valid_from: date
    valid_to: date
    board_online_audit: bool = Field(default=False, description="Online-Belegprüfung durch Beirat")
    notes: str | None = None

    @model_validator(mode="after")
    def _order(self) -> Self:
        if self.valid_to < self.valid_from:
            raise ValueError("valid_to liegt vor valid_from")
        return self


class BillingPeriodOut(BillingPeriodIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    property_id: uuid.UUID


class SubCommunityIn(_In):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    name: str = Field(min_length=1, max_length=200)
    notes: str | None = None


class SubCommunityOut(SubCommunityIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    property_id: uuid.UUID


class PortalDocumentIn(_In):
    document_id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)
    visible_for: list[str] = Field(default_factory=list, description="tenant, owner")
    sort_order: int = 0

    @field_validator("visible_for")
    @classmethod
    def _audience(cls, value: list[str]) -> list[str]:
        if not value or not set(value) <= {"tenant", "owner"}:
            raise ValueError("erlaubt: tenant, owner (mindestens einer)")
        return sorted(set(value))


class PortalDocumentOut(PortalDocumentIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    property_id: uuid.UUID


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


class MeterChangeIn(_In):
    changed_on: date
    old_final_value: Qty = Field(ge=0, description="Endstand des alten Zählers")
    new_initial_value: Qty = Field(ge=0, description="Anfangsstand des neuen Zählers")
    new_number: str | None = Field(default=None, min_length=1, max_length=100)
    notes: str | None = None


class MeterChangeOut(MeterChangeIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    meter_id: uuid.UUID
    old_number: str


class ProviderIn(_Period):
    contact_id: uuid.UUID
    contract_type_code: str
    notice_period: str | None = None
    contact_bank_account_id: uuid.UUID | None = None
    create_default_bank_rule: bool = False
    categories: list[str] = Field(default_factory=list)
    notes: str | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    customer_number: str | None = Field(default=None, max_length=50)
    exemption_cert_status: ExemptionCertStatus | None = Field(
        default=None, description="Freistellungsbescheinigung § 48b EStG, laut Bescheinigung"
    )
    exemption_cert_valid_until: date | None = None
    creditor_account_id: uuid.UUID | None = Field(default=None, description="Kreditorenkonto")

    @model_validator(mode="after")
    def _exemption(self) -> Self:
        if self.exemption_cert_valid_until is not None and self.exemption_cert_status is not (
            ExemptionCertStatus.VALID
        ):
            raise ValueError("Gültigkeitsdatum nur bei gültiger Freistellungsbescheinigung")
        return self


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


class CatalogEntryPatch(_In):
    """Partial update (AP4): system entries accept label, sort order and active only; the
    code of any entry is immutable because rows reference it."""

    label: str | None = Field(default=None, min_length=1, max_length=200)
    sort_order: int | None = None
    active: bool | None = None


class CatalogEntryOut(CatalogEntryIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
    catalog: str
    active: bool
    is_system: bool


class CatalogSummaryOut(_Out):
    catalog: str
    entries: int
    active: int
    system: int


_FIELD_TYPE = "|".join(sorted(CUSTOM_FIELD_TYPES))
_ENTITY = "|".join(CUSTOM_FIELD_ENTITIES)
_UNIQUENESS = "|".join(CUSTOM_FIELD_UNIQUENESS)


class _CustomFieldBase(_In):
    label: str = Field(min_length=1, max_length=200)
    required: bool = False
    group: str | None = Field(default=None, max_length=100)
    valid_for_management_types: list[str] = Field(default_factory=list)
    valid_for_contract_kinds: list[str] = Field(default_factory=list)
    uniqueness: str = Field(default="none", pattern=rf"^({_UNIQUENESS})$")
    visible_in_main: bool = False
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    default_value: Any | None = None
    options: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int = 0

    @field_validator("valid_for_management_types")
    @classmethod
    def _management_types(cls, value: list[str]) -> list[str]:
        allowed = {m.value for m in ManagementType}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"Unbekannte Verwaltungsart: {', '.join(unknown)}")
        return list(dict.fromkeys(value))

    @field_validator("valid_for_contract_kinds", "options")
    @classmethod
    def _codes(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value if v and v.strip()]
        if any(len(v) > 100 for v in cleaned):
            raise ValueError("Eintrag höchstens 100 Zeichen")
        return list(dict.fromkeys(cleaned))

    @model_validator(mode="after")
    def _range(self) -> Self:
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.max_value < self.min_value
        ):
            raise ValueError("Maximum darf nicht kleiner als Minimum sein")
        return self


class CustomFieldIn(_CustomFieldBase):
    entity_type: str = Field(pattern=rf"^({_ENTITY})$")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    field_type: str = Field(pattern=rf"^({_FIELD_TYPE})$")

    @model_validator(mode="after")
    def _choice_options(self) -> Self:
        if self.field_type == "choice" and not self.options:
            raise ValueError("Einzelauswahl benötigt Auswahlwerte")
        return self


class CustomFieldPatch(_In):
    """Partial update (AP4). Entity, key and field type are immutable: stored values depend
    on them."""

    label: str | None = Field(default=None, min_length=1, max_length=200)
    required: bool | None = None
    group: str | None = Field(default=None, max_length=100)
    valid_for_management_types: list[str] | None = None
    valid_for_contract_kinds: list[str] | None = None
    uniqueness: str | None = Field(default=None, pattern=rf"^({_UNIQUENESS})$")
    visible_in_main: bool | None = None
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    default_value: Any | None = None
    options: list[str] | None = None
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None


class CustomFieldOut(CustomFieldIn):
    model_config = ConfigDict(from_attributes=True, extra="ignore")
    id: uuid.UUID
