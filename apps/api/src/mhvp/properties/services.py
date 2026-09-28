"""Property services: legal entities, templates, custom fields, periods, plausibility."""

import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact, Party, PartyMember, PartyRole
from mhvp.core.problems import ErrorCodes, FieldError, ProblemError
from mhvp.dataquality.rules import postcode_error
from mhvp.properties.models import (
    AllocationKey,
    AllocationKeyTemplate,
    BankAccountKind,
    Building,
    CatalogEntry,
    CustomFieldDefinition,
    LegalEntity,
    LegalEntityKind,
    ManagementType,
    MeterReading,
    Property,
    PropertyOwner,
    PropertyStatus,
    ServiceProviderRelation,
    SubCommunity,
    Unit,
    UnitAllocationValue,
    UnitVacancyAllocationValue,
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


def check_postcode(country: str | None, postal_code: str | None) -> None:
    """ES-01 (docs/rules/ES-erfassungsstandards.md): hard check of the German postcode on the
    API. Endpoints call it on create and when postcode or country change, so stored legacy
    values stay readable and editable in their other fields."""
    error = postcode_error(country, postal_code)
    if error:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail=error,
            errors=[
                FieldError(
                    location=["body", "postal_code"],
                    field="postal_code",
                    code="postcode_invalid",
                    message=error,
                )
            ],
        )


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


def _field_error(key: str, label: str, code: str, message: str) -> ProblemError:
    """422 with a field error for ``custom_fields.<key>`` (ADR 0004)."""
    return ProblemError(
        ErrorCodes.VALIDATION,
        detail=f"Zusatzfeld {label}: {message}",
        errors=[
            FieldError(
                location=["body", "custom_fields", key],
                field=f"custom_fields.{key}",
                code=code,
                message=message,
            )
        ],
    )


# Entities whose custom field values live in a JSONB column; uniqueness is checked there.
_CUSTOM_FIELD_TABLES: dict[str, type[Any]] = {
    "property": Property,
    "building": Building,
    "unit": Unit,
    "service_provider_relation": ServiceProviderRelation,
}


async def check_custom_fields(
    session: AsyncSession,
    entity_type: str,
    values: dict[str, Any],
    *,
    management_type: ManagementType | str | None = None,
    contract_kind: str | None = None,
    entity_id: uuid.UUID | None = None,
    create: bool = False,
) -> dict[str, Any]:
    """Checks the values of the custom fields of one entity (4.11, B.28) and returns the
    values to store. Rules: only defined keys; validity per management type and contract kind
    (a value for a field that is not valid in this context is refused, a required field that
    is not valid is not required); default value on create when the key is missing; required;
    type; minimum and maximum (value bounds for numbers, length bounds for texts); choice
    options; uniqueness within the tenant per entity type (``uniqueness`` other than
    ``none``), ignoring the entity itself. Every refusal is a 422 with a field error."""
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
        raise _field_error(
            unknown[0], unknown[0], "unknown", f"Unbekannte Zusatzfelder: {', '.join(unknown)}."
        )
    mt = management_type.value if isinstance(management_type, ManagementType) else management_type
    result = dict(values)
    for key, definition in definitions.items():
        applies = _definition_applies(definition, mt, contract_kind)
        present = key in result and result[key] is not None
        if not applies:
            if present:
                raise _field_error(
                    key, definition.label, "not_applicable", "gilt nicht für diesen Kontext."
                )
            continue
        if create and key not in result and definition.default_value is not None:
            result[key] = definition.default_value
        value = result.get(key)
        if value is None:
            if definition.required:
                raise _field_error(key, definition.label, "required", "ist Pflicht.")
            continue
        if not _custom_value_ok(definition, value):
            raise _field_error(key, definition.label, "type", "hat den falschen Typ.")
        if definition.field_type in _NUMERIC_TYPES:
            number = Decimal(str(value))
            if definition.min_value is not None and number < definition.min_value:
                raise _field_error(key, definition.label, "min", "unterschreitet das Minimum.")
            if definition.max_value is not None and number > definition.max_value:
                raise _field_error(key, definition.label, "max", "überschreitet das Maximum.")
        elif definition.field_type in _TEXT_TYPES and isinstance(value, str):
            length = Decimal(len(value))
            if definition.min_value is not None and length < definition.min_value:
                raise _field_error(key, definition.label, "min", "ist zu kurz.")
            if definition.max_value is not None and length > definition.max_value:
                raise _field_error(key, definition.label, "max", "ist zu lang.")
        elif definition.field_type == "choice" and value not in definition.options:
            raise _field_error(key, definition.label, "choice", "unbekannter Auswahlwert.")
        if definition.uniqueness != "none" and not await _unique_value_free(
            session, entity_type, key, value, entity_id
        ):
            raise _field_error(
                key, definition.label, "unique", "ist bereits bei einem anderen Datensatz vergeben."
            )
    return result


def _definition_applies(
    definition: CustomFieldDefinition, management_type: str | None, contract_kind: str | None
) -> bool:
    """A definition without restriction applies everywhere; a restriction is only checked
    when the context is known (management type of the property, kind of the contract)."""
    if (
        definition.valid_for_management_types
        and management_type is not None
        and management_type not in definition.valid_for_management_types
    ):
        return False
    return not (
        definition.valid_for_contract_kinds
        and contract_kind is not None
        and contract_kind not in definition.valid_for_contract_kinds
    )


async def _unique_value_free(
    session: AsyncSession,
    entity_type: str,
    key: str,
    value: Any,
    entity_id: uuid.UUID | None,
) -> bool:
    """True when no other row of the entity type (tenant scoped by RLS) holds the value."""
    model = _CUSTOM_FIELD_TABLES.get(entity_type)
    if model is None:
        return True
    stmt = select(model.id).where(model.custom_fields[key] == cast(value, JSONB))
    if entity_id is not None:
        stmt = stmt.where(model.id != entity_id)
    return (await session.scalar(stmt.limit(1))) is None


# B.28 field types (catalogs.CUSTOM_FIELD_TYPES). Minimum and maximum apply to numeric
# types as value bounds and to text types as length bounds.
_NUMERIC_TYPES = frozenset({"integer", "number", "amount"})
_TEXT_TYPES = frozenset({"string", "text", "rich_text", "url"})
_REF_TYPES = frozenset({"contact_ref", "document_ref", "property_ref"})


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return True
    if isinstance(value, str):
        try:
            Decimal(value)
        except ArithmeticError:
            return False
        return True
    return False


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def _is_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _custom_value_ok(definition: CustomFieldDefinition, value: Any) -> bool:
    kind = definition.field_type
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind in _NUMERIC_TYPES:
        return _is_number(value)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "date":
        return isinstance(value, str) and _is_date(value)
    if kind == "datetime":
        return _is_datetime(value)
    if kind in _TEXT_TYPES or kind == "choice":
        return isinstance(value, str)
    if kind in _REF_TYPES:
        return _is_uuid(value)
    return False


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


_NUM_CHUNK = re.compile(r"(\d+)")


def natural_key(number: str) -> tuple[tuple[int, int | str], ...]:
    """Sort key so that "1" < "2" < "10" and "WE1" < "WE2" < "WE10"."""
    parts = _NUM_CHUNK.split(number.strip())
    return tuple((0, int(p)) if p.isdigit() else (1, p.casefold()) for p in parts if p != "")


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


async def add_vacancy_allocation_value(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    unit_id: uuid.UUID,
    key_id: uuid.UUID,
    value: Decimal,
    valid_from: date,
    valid_to: date | None,
) -> UnitVacancyAllocationValue:
    """Vacancy key value (4.4); an open ended earlier value is closed the day before."""
    previous = await session.scalar(
        select(UnitVacancyAllocationValue).where(
            UnitVacancyAllocationValue.unit_id == unit_id,
            UnitVacancyAllocationValue.allocation_key_id == key_id,
            UnitVacancyAllocationValue.valid_to.is_(None),
            UnitVacancyAllocationValue.valid_from < valid_from,
        )
    )
    if previous is not None:
        previous.valid_to = valid_from - timedelta(days=1)
        await session.flush()
    row = UnitVacancyAllocationValue(
        tenant_id=tenant_id,
        unit_id=unit_id,
        allocation_key_id=key_id,
        value=value,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    session.add(row)
    await session.flush()
    return row


async def check_ledger_account(
    session: AsyncSession, account_id: uuid.UUID | None, property_id: uuid.UUID, label: str
) -> None:
    """An assigned ledger account must exist in the tenant and belong to a ledger of a legal
    entity of this property (6.9.1: accounts never cross legal entities). Reference only."""
    if account_id is None:
        return
    from mhvp.accounting.models import Ledger, LedgerAccount

    row = (
        await session.execute(
            select(Ledger.property_id, LegalEntity.property_id)
            .join(LedgerAccount, LedgerAccount.ledger_id == Ledger.id)
            .join(LegalEntity, LegalEntity.id == Ledger.legal_entity_id)
            .where(LedgerAccount.id == account_id)
        )
    ).first()
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail=f"{label} nicht gefunden.")
    if property_id not in row:
        raise invalid(f"{label} gehört nicht zu einem Rechtsträger dieses Objekts.")


async def check_sub_community(
    session: AsyncSession, sub_community_id: uuid.UUID | None, property_id: uuid.UUID
) -> None:
    if sub_community_id is None:
        return
    row = await session.get(SubCommunity, sub_community_id)
    if row is None:
        raise ProblemError(
            ErrorCodes.RESOURCE_NOT_FOUND, detail="Untergemeinschaft nicht gefunden."
        )
    if row.property_id != property_id:
        raise invalid("Die Untergemeinschaft gehört nicht zu diesem Objekt.")


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


def active_owner_filter(as_of: date) -> Any:
    """Property owner rows active on ``as_of`` (open ended or ending on or after the day)."""
    return and_(
        PropertyOwner.valid_from <= as_of,
        or_(PropertyOwner.valid_to.is_(None), PropertyOwner.valid_to >= as_of),
    )


def owner_open_filter(as_of: date) -> Any:
    """Property owner rows not yet ended on ``as_of`` (includes a start in the future)."""
    return or_(PropertyOwner.valid_to.is_(None), PropertyOwner.valid_to >= as_of)


def default_owner_start(prop: Property, today: date) -> date:
    """Start of an owner entry without date: management start, else 1 January of the year
    (the default start of the import assignment, so that tenancies find their landlord)."""
    return prop.managed_from or date(today.year, 1, 1)


async def owner_rows(
    session: AsyncSession, property_id: uuid.UUID, as_of: date
) -> list[dict[str, Any]]:
    """Owners of a rental property not ended on ``as_of`` with party, contact and entity."""
    rows = (
        await session.execute(
            select(PropertyOwner, Party.name)
            .join(Party, Party.id == PropertyOwner.party_id)
            .where(PropertyOwner.property_id == property_id, owner_open_filter(as_of))
            .order_by(PropertyOwner.valid_from, PropertyOwner.id)
        )
    ).all()
    return [await owner_view(session, o, name) for o, name in rows]


async def owner_view(
    session: AsyncSession, owner: PropertyOwner, party_name: str
) -> dict[str, Any]:
    contact = (
        await session.execute(
            select(Contact.id, Contact.display_name)
            .join(PartyMember, PartyMember.contact_id == Contact.id)
            .where(PartyMember.party_id == owner.party_id)
            .order_by(PartyMember.role != PartyRole.PRIMARY, PartyMember.created_at)
            .limit(1)
        )
    ).first()
    entity = await session.scalar(
        select(LegalEntity.id).where(
            LegalEntity.property_id == owner.property_id,
            LegalEntity.party_id == owner.party_id,
            LegalEntity.kind == LegalEntityKind.RENTAL_OWNER,
        )
    )
    return {
        "id": owner.id,
        "party_id": owner.party_id,
        "party_name": party_name,
        "contact_id": contact[0] if contact else None,
        "contact_name": contact[1] if contact else None,
        "share_percent": owner.share_percent,
        "valid_from": owner.valid_from,
        "valid_to": owner.valid_to,
        "legal_entity_id": entity,
        "clearing_account_id": owner.clearing_account_id,
        "power_of_attorney_document_id": owner.power_of_attorney_document_id,
        "tax_advisor_contact_id": owner.tax_advisor_contact_id,
    }
