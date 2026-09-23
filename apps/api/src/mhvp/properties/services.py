"""Property services: legal entities, templates, custom fields, periods, plausibility."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Party
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties.models import (
    AllocationKey,
    AllocationKeyTemplate,
    BankAccountKind,
    CatalogEntry,
    CustomFieldDefinition,
    LegalEntity,
    LegalEntityKind,
    ManagementType,
    MeterReading,
    Property,
    PropertyStatus,
    UnitAllocationValue,
)

ALLOWED_TRANSITIONS: dict[PropertyStatus, set[PropertyStatus]] = {
    PropertyStatus.ONBOARDING: {PropertyStatus.ACTIVE, PropertyStatus.TERMINATED},
    PropertyStatus.ACTIVE: {PropertyStatus.TERMINATED},
    PropertyStatus.TERMINATED: set(),
}

# Which legal entity may hold which kind of account (6.9.1, D56).
ACCOUNT_OWNERS: dict[BankAccountKind, set[LegalEntityKind]] = {
    BankAccountKind.HOA: {LegalEntityKind.HOA},
    BankAccountKind.RESERVE: {LegalEntityKind.HOA},
    BankAccountKind.HOA_FEE: {LegalEntityKind.HOA},
    BankAccountKind.RENT: {LegalEntityKind.RENTAL_OWNER, LegalEntityKind.SEV_OWNER},
    BankAccountKind.DEPOSIT: {LegalEntityKind.RENTAL_OWNER, LegalEntityKind.SEV_OWNER},
    BankAccountKind.OTHER: set(LegalEntityKind),
}


def invalid(detail: str) -> ProblemError:
    return ProblemError(ErrorCodes.VALIDATION, detail=detail)


def hoa_name(prop: Property) -> str:
    """Designation of the GdWE with the plot address (R01); falls back to the property name."""
    address = " ".join(p for p in (prop.street, prop.house_number) if p)
    place = " ".join(p for p in (prop.postal_code, prop.city) if p)
    location = ", ".join(p for p in (address, place) if p)
    return f"Gemeinschaft der Wohnungseigentümer {location or prop.name}"


async def ensure_hoa_entity(session: AsyncSession, prop: Property) -> None:
    if prop.management_type not in (ManagementType.HOA, ManagementType.HOA_WITH_SEV):
        return
    exists = await session.scalar(
        select(LegalEntity.id).where(
            LegalEntity.property_id == prop.id, LegalEntity.kind == LegalEntityKind.HOA
        )
    )
    if exists is None:
        session.add(
            LegalEntity(
                tenant_id=prop.tenant_id,
                kind=LegalEntityKind.HOA,
                name=hoa_name(prop),
                property_id=prop.id,
            )
        )
        await session.flush()


async def owner_entity(session: AsyncSession, prop: Property, party_id: uuid.UUID) -> uuid.UUID:
    """Legal entity of the owner of a rental property (one per party and property)."""
    existing = await session.scalar(
        select(LegalEntity.id).where(
            LegalEntity.property_id == prop.id,
            LegalEntity.party_id == party_id,
            LegalEntity.kind == LegalEntityKind.RENTAL_OWNER,
        )
    )
    if existing is not None:
        return existing
    party = await session.get(Party, party_id)
    if party is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    entity = LegalEntity(
        tenant_id=prop.tenant_id,
        kind=LegalEntityKind.RENTAL_OWNER,
        name=party.name,
        party_id=party_id,
        property_id=prop.id,
    )
    session.add(entity)
    await session.flush()
    return entity.id


async def copy_key_templates(session: AsyncSession, prop: Property) -> None:
    templates = (
        await session.scalars(
            select(AllocationKeyTemplate).order_by(AllocationKeyTemplate.sort_order)
        )
    ).all()
    for t in templates:
        session.add(
            AllocationKey(
                tenant_id=prop.tenant_id,
                property_id=prop.id,
                code=t.code,
                name=t.name,
                unit_of_measure=t.unit_of_measure,
                kind=t.kind,
                meter_type_code=t.meter_type_code,
                sort_order=t.sort_order,
                is_template_derived=True,
            )
        )
    await session.flush()


async def check_catalog(session: AsyncSession, catalog: str, code: str | None) -> None:
    if code is None:
        return
    found = await session.scalar(
        select(CatalogEntry.id).where(
            CatalogEntry.catalog == catalog,
            CatalogEntry.code == code,
            CatalogEntry.active.is_(True),
        )
    )
    if found is None:
        raise invalid(f"Unbekannter Katalogeintrag {code!r} im Katalog {catalog}.")


async def check_custom_fields(
    session: AsyncSession, entity_type: str, values: dict[str, Any]
) -> None:
    definitions = {
        d.key: d
        for d in (
            await session.scalars(
                select(CustomFieldDefinition).where(
                    CustomFieldDefinition.entity_type == entity_type
                )
            )
        ).all()
    }
    unknown = sorted(set(values) - set(definitions))
    if unknown:
        raise invalid(f"Unbekannte Zusatzfelder: {', '.join(unknown)}.")
    for key, definition in definitions.items():
        value = values.get(key)
        if value is None:
            if definition.required:
                raise invalid(f"Zusatzfeld {definition.label} ist Pflicht.")
            continue
        ok = {
            "text": isinstance(value, str),
            "number": isinstance(value, int | float) and not isinstance(value, bool),
            "bool": isinstance(value, bool),
            "date": isinstance(value, str) and _is_date(value),
        }[definition.field_type]
        if not ok:
            raise invalid(f"Zusatzfeld {definition.label} hat den falschen Typ.")


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def valid_at(model: Any, as_of: date) -> Any:
    return and_(model.valid_from <= as_of, or_(model.valid_to.is_(None), model.valid_to >= as_of))


async def add_allocation_value(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    key_id: uuid.UUID,
    value: Decimal,
    valid_from: date,
    valid_to: date | None,
    source: Any,
) -> tuple[UnitAllocationValue, UnitAllocationValue | None]:
    """Add a value; an open ended earlier value is closed the day before (history kept)."""
    previous = await session.scalar(
        select(UnitAllocationValue).where(
            UnitAllocationValue.unit_id == unit_id,
            UnitAllocationValue.allocation_key_id == key_id,
            UnitAllocationValue.valid_to.is_(None),
            UnitAllocationValue.valid_from < valid_from,
        )
    )
    if previous is not None:
        previous.valid_to = valid_from - timedelta(days=1)
        await session.flush()
    row = UnitAllocationValue(
        tenant_id=tenant_id,
        unit_id=unit_id,
        allocation_key_id=key_id,
        value=value,
        valid_from=valid_from,
        valid_to=valid_to,
        source=source,
    )
    session.add(row)
    await session.flush()
    return row, previous


async def reading_is_implausible(
    session: AsyncSession, meter_id: uuid.UUID, read_at: date, value: Decimal
) -> bool:
    """Plausibility hint only: cumulative reading lower than an earlier one; never rejected."""
    earlier = await session.scalar(
        select(MeterReading.value)
        .where(MeterReading.meter_id == meter_id, MeterReading.read_at < read_at)
        .order_by(MeterReading.read_at.desc())
        .limit(1)
    )
    return earlier is not None and value < earlier
