"""Properties, buildings, units, allocation keys, meters, providers, bank accounts (6.2, 6.9.1).

Legal entities (6.9.1, E01) are created here because bank accounts, deposits and later ledgers
belong to a legal entity, never to "the property": a GdWE, the owner of a rental property, each
SEV owner, or the management company.
"""

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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

AREA = Numeric(20, 8)  # areas, shares, quotas, consumption (6.9.8)


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


def _fk(
    target: str, *, nullable: bool = False, ondelete: str = "RESTRICT", index: bool = True
) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index
    )


class ManagementType(StrEnum):
    RENTAL = "rental"
    HOA = "hoa"
    HOA_WITH_SEV = "hoa_with_sev"


class ManagementMode(StrEnum):
    OWN = "own"
    THIRD_PARTY = "third_party"


class PropertyStatus(StrEnum):
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    TERMINATED = "terminated"


class LegalEntityKind(StrEnum):
    HOA = "hoa"  # Gemeinschaft der Wohnungseigentümer (GdWE)
    RENTAL_OWNER = "rental_owner"
    SEV_OWNER = "sev_owner"
    MANAGER = "manager"


class UnitType(StrEnum):
    APARTMENT = "apartment"
    COMMERCIAL = "commercial"
    OFFICE = "office"
    PARKING = "parking"
    GARAGE = "garage"
    STORAGE = "storage"
    GARDEN = "garden"
    OTHER = "other"


class AllocationKind(StrEnum):
    STATIC = "static"
    CONSUMPTION = "consumption"
    FIXED_AMOUNT = "fixed_amount"
    FIXED_SHARE = "fixed_share"


class ValueSource(StrEnum):
    MANUAL = "manual"
    CONTRACT = "contract"
    IMPORT = "import"
    AI = "ai"


class VatOption(StrEnum):
    NONE = "none"
    COMMERCIAL_NO_VAT = "commercial_no_vat"
    COMMERCIAL_FULL_VAT = "commercial_full_vat"
    COMMERCIAL_REDUCED_VAT = "commercial_reduced_vat"


class Occupant(StrEnum):
    VACANCY = "vacancy"
    CONTRACT = "contract"


class MeterConnection(StrEnum):
    MAIN = "main"
    SUB = "sub"


class ReadingSource(StrEnum):
    MANUAL = "manual"
    PORTAL = "portal"
    PROVIDER_IMPORT = "provider_import"
    AI = "ai"


class MaintenanceKind(StrEnum):
    MODERNIZATION = "modernization"
    MAINTENANCE = "maintenance"
    INSPECTION = "inspection"
    WARRANTY = "warranty"


class BankAccountKind(StrEnum):
    RENT = "rent"
    HOA = "hoa"
    RESERVE = "reserve"
    DEPOSIT = "deposit"
    HOA_FEE = "hoa_fee"
    OTHER = "other"


class CatalogEntry(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant catalogues (5.2): meter types, provider contract types, contact categories, ..."""

    __tablename__ = "catalog_entry"
    __table_args__ = (UniqueConstraint("tenant_id", "catalog", "code"),)

    catalog: Mapped[str] = mapped_column(String(63), nullable=False)
    code: Mapped[str] = mapped_column(String(63), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CustomFieldDefinition(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "custom_field_definition"
    __table_args__ = (UniqueConstraint("tenant_id", "entity_type", "key"),)

    entity_type: Mapped[str] = mapped_column(String(63), nullable=False)
    key: Mapped[str] = mapped_column(String(63), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[str] = mapped_column(String(16), nullable=False)  # text, number, date, bool
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AllocationKeyTemplate(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant pattern for allocation keys copied into new properties (5.2 Muster, annex A.2)."""

    __tablename__ = "allocation_key_template"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[AllocationKind] = mapped_column(
        _enum(AllocationKind, "allocation_kind"), nullable=False
    )
    meter_type_code: Mapped[str | None] = mapped_column(String(63))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Property(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "property"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number"),
        CheckConstraint("number ~ '^[0-9]{3}$'", name="number_format"),
        Index("ix_property_tenant_status", "tenant_id", "status", "management_type"),
        Index(
            "uq_property_source",
            "tenant_id",
            "source_system",
            "source_id",
            unique=True,
            postgresql_where=text("source_system IS NOT NULL AND source_id IS NOT NULL"),
        ),
    )

    number: Mapped[str] = mapped_column(String(3), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    management_type: Mapped[ManagementType] = mapped_column(
        _enum(ManagementType, "management_type"), nullable=False
    )
    management_mode: Mapped[ManagementMode] = mapped_column(
        _enum(ManagementMode, "management_mode"), nullable=False, default=ManagementMode.THIRD_PARTY
    )
    property_type_code: Mapped[str | None] = mapped_column(String(63))
    street: Mapped[str | None] = mapped_column(String(200))
    house_number: Mapped[str | None] = mapped_column(String(20))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="DE")
    municipality_code: Mapped[str | None] = mapped_column(String(20))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    land_registry_district: Mapped[str | None] = mapped_column(String(100))
    land_registry_sheet: Mapped[str | None] = mapped_column(String(50))
    parcel: Mapped[str | None] = mapped_column(String(200))
    built_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    unbuilt_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    sealed_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    garden_use: Mapped[str | None] = mapped_column(String(16))
    garden_notes: Mapped[str | None] = mapped_column(Text)
    renovation_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    renovation_notes: Mapped[str | None] = mapped_column(Text)
    allocation_loss_risk_percent: Mapped[Decimal | None] = mapped_column(AREA)
    notes: Mapped[str | None] = mapped_column(Text)
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[PropertyStatus] = mapped_column(
        _enum(PropertyStatus, "property_status"), nullable=False, default=PropertyStatus.ONBOARDING
    )
    managed_from: Mapped[date | None] = mapped_column(Date)
    managed_to: Mapped[date | None] = mapped_column(Date)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))
    # Energieausweis des Objekts (A63, M26-03): values are entered from the certificate
    # document, never derived. Listings copy them on creation (mhvp.letting) and the exposé
    # draft and OpenImmo completeness check read them; no legal claim about Pflichtangaben.
    energy_certificate_type: Mapped[str | None] = mapped_column(String(16))  # verbrauch, bedarf
    energy_certificate_value: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))  # kWh/(m²a)
    energy_certificate_source: Mapped[str | None] = mapped_column(String(32))  # Energieträger
    energy_certificate_construction_year: Mapped[int | None] = mapped_column(Integer)
    energy_certificate_issued_on: Mapped[date | None] = mapped_column(Date)
    energy_certificate_valid_until: Mapped[date | None] = mapped_column(Date)
    energy_certificate_class: Mapped[str | None] = mapped_column(String(4))


class LegalEntity(IdMixin, TimestampMixin, TenantMixin, Base):
    """Owner of receivables, funds, reserves and deposits (6.9.1, B01)."""

    __tablename__ = "legal_entity"
    __table_args__ = (
        Index(
            "uq_legal_entity_hoa_per_property",
            "tenant_id",
            "property_id",
            unique=True,
            postgresql_where=text("kind = 'hoa'"),
        ),
    )

    kind: Mapped[LegalEntityKind] = mapped_column(
        _enum(LegalEntityKind, "legal_entity_kind"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(400), nullable=False)
    party_id: Mapped[uuid.UUID | None] = _fk("party.id", nullable=True)
    property_id: Mapped[uuid.UUID | None] = _fk("property.id", nullable=True)
    # SEPA creditor identifier of this legal entity as creditor of direct debits (M15-02,
    # pain.008). Entered by the operator from the Bundesbank document; never derived.
    # Format rules are not verified in code (docs/OPEN_QUESTIONS.md M15-01).
    sepa_creditor_id: Mapped[str | None] = mapped_column(String(35))


class PropertyOwner(IdMixin, TimestampMixin, TenantMixin, Base):
    """Owner of a rental property (Mietverwaltung) with period."""

    __tablename__ = "property_owner"

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    party_id: Mapped[uuid.UUID] = _fk("party.id")
    share_percent: Mapped[Decimal | None] = mapped_column(AREA)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)


class PropertyContact(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "property_contact"

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    category_code: Mapped[str] = mapped_column(String(63), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    visible_in_portal_for: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )


class Building(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "building"

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    street: Mapped[str | None] = mapped_column(String(200))
    house_number: Mapped[str | None] = mapped_column(String(20))
    built_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    sealed_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    roof_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    construction_year: Mapped[int | None] = mapped_column(Integer)
    renovation_level: Mapped[str | None] = mapped_column(String(100))
    construction_type_code: Mapped[str | None] = mapped_column(String(63))
    building_type_code: Mapped[str | None] = mapped_column(String(63))
    floors: Mapped[int | None] = mapped_column(Integer)
    windows: Mapped[int | None] = mapped_column(Integer)
    total_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    living_commercial_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    heated_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    window_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    hallway_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    gross_floor_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    elevator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cellar_rooms: Mapped[int | None] = mapped_column(Integer)
    heritage_protection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    heritage_notes: Mapped[str | None] = mapped_column(Text)
    energy_certificate_type: Mapped[str | None] = mapped_column(String(32))
    energy_certificate_value: Mapped[Decimal | None] = mapped_column(AREA)
    energy_certificate_valid_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Unit(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "unit"
    __table_args__ = (
        UniqueConstraint("tenant_id", "property_id", "number"),
        Index(
            "uq_unit_source",
            "tenant_id",
            "source_system",
            "source_id",
            unique=True,
            postgresql_where=text("source_system IS NOT NULL AND source_id IS NOT NULL"),
        ),
    )

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    building_id: Mapped[uuid.UUID] = _fk("building.id")
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(100))
    unit_type: Mapped[UnitType] = mapped_column(_enum(UnitType, "unit_type"), nullable=False)
    internal_name: Mapped[str | None] = mapped_column(String(200))
    rooms: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    total_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    living_area_sqm: Mapped[Decimal | None] = mapped_column(AREA)
    floor: Mapped[str | None] = mapped_column(String(20))
    last_modernization_year: Mapped[int | None] = mapped_column(Integer)
    is_fictional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cellar_number: Mapped[str | None] = mapped_column(String(20))
    features: Mapped[str | None] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(String(200))
    house_number: Mapped[str | None] = mapped_column(String(20))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_system: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))


class AllocationKey(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "allocation_key"
    __table_args__ = (UniqueConstraint("tenant_id", "property_id", "code"),)

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(16), nullable=False)
    default_value: Mapped[Decimal | None] = mapped_column(AREA)
    kind: Mapped[AllocationKind] = mapped_column(
        _enum(AllocationKind, "allocation_kind"), nullable=False
    )
    meter_type_code: Mapped[str | None] = mapped_column(String(63))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_template_derived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class UnitAllocationValue(IdMixin, TimestampMixin, TenantMixin, Base):
    """Time valid key value per unit; periods of one unit and key never overlap (6.2, 2.4)."""

    __tablename__ = "unit_allocation_value"
    __table_args__ = (
        ExcludeConstraint(
            ("unit_id", "="),
            ("allocation_key_id", "="),
            (text("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_unit_allocation_value_period",
            using="gist",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period_order"),
    )

    unit_id: Mapped[uuid.UUID] = _fk("unit.id", ondelete="CASCADE")
    allocation_key_id: Mapped[uuid.UUID] = _fk("allocation_key.id", ondelete="CASCADE")
    value: Mapped[Decimal] = mapped_column(AREA, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[ValueSource] = mapped_column(
        _enum(ValueSource, "value_source"), nullable=False, default=ValueSource.MANUAL
    )


class UnitVatOption(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "unit_vat_option"
    __table_args__ = (
        ExcludeConstraint(
            ("unit_id", "="),
            (text("daterange(valid_from, valid_to, '[]')"), "&&"),
            name="ex_unit_vat_option_period",
            using="gist",
        ),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period_order"),
    )

    unit_id: Mapped[uuid.UUID] = _fk("unit.id", ondelete="CASCADE")
    option: Mapped[VatOption] = mapped_column(_enum(VatOption, "vat_option"), nullable=False)
    occupant: Mapped[Occupant] = mapped_column(_enum(Occupant, "vat_occupant"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)


class Meter(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "meter"

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", nullable=True)
    meter_type_code: Mapped[str] = mapped_column(String(63), nullable=False)
    number: Mapped[str] = mapped_column(String(100), nullable=False)
    malo_id: Mapped[str | None] = mapped_column(String(33))
    name: Mapped[str | None] = mapped_column(String(200))
    connection: Mapped[MeterConnection] = mapped_column(
        _enum(MeterConnection, "meter_connection"), nullable=False, default=MeterConnection.SUB
    )
    location: Mapped[str | None] = mapped_column(String(200))
    calibration_due_date: Mapped[date | None] = mapped_column(Date)
    remote_readable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class MeterReading(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "meter_reading"

    meter_id: Mapped[uuid.UUID] = _fk("meter.id", ondelete="CASCADE")
    read_at: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal] = mapped_column(AREA, nullable=False)
    estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source: Mapped[ReadingSource] = mapped_column(
        _enum(ReadingSource, "reading_source"), nullable=False, default=ReadingSource.MANUAL
    )
    photo_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text)


class ServiceProviderRelation(IdMixin, TimestampMixin, TenantMixin, Base):
    """Provider contract of a property. The creditor account follows with the ledger (M10)."""

    __tablename__ = "service_provider_relation"

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    contract_type_code: Mapped[str] = mapped_column(String(63), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notice_period: Mapped[str | None] = mapped_column(String(100))
    contact_bank_account_id: Mapped[uuid.UUID | None] = _fk(
        "contact_bank_account.id", nullable=True
    )
    create_default_bank_rule: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class PropertyBankAccount(IdMixin, TimestampMixin, TenantMixin, Base):
    """Bank account of a legal entity (6.9.1). Deposit accounts are segregated (D56)."""

    __tablename__ = "property_bank_account"
    __table_args__ = (
        CheckConstraint("kind <> 'deposit' OR segregated", name="deposit_segregated"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="period_order"),
    )

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    kind: Mapped[BankAccountKind] = mapped_column(
        _enum(BankAccountKind, "bank_account_kind"), nullable=False
    )
    iban: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    iban_suffix: Mapped[str] = mapped_column(String(4), nullable=False)
    iban_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    bic: Mapped[str | None] = mapped_column(String(11))
    bank_name: Mapped[str | None] = mapped_column(String(200))
    holder: Mapped[str] = mapped_column(String(200), nullable=False)
    segregated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)


class MaintenanceItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "maintenance_item"
    __table_args__ = (
        Index("ix_maintenance_item_tenant_status_due", "tenant_id", "status", "due_date"),
    )

    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", nullable=True)
    kind: Mapped[MaintenanceKind] = mapped_column(
        _enum(MaintenanceKind, "maintenance_kind"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    remind_before: Mapped[str | None] = mapped_column(String(8))  # 14d, 1m, 3m, 6m
    interval_months: Mapped[int | None] = mapped_column(Integer)
    provider_relation_id: Mapped[uuid.UUID | None] = _fk(
        "service_provider_relation.id", nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
