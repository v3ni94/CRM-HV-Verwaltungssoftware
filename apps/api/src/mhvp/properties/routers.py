"""Property endpoints (/api/v1/properties, units, buildings, meters; catalogues and custom
fields live in routers_catalogs.py)."""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import account_selection
from mhvp.banking.routers import BankAccountListOut, account_list_out
from mhvp.contacts.models import Contact, ContactBankAccount, Party, PartyMember
from mhvp.contacts.services import recompute_for_party
from mhvp.contacts.validation import mask_iban
from mhvp.core import crypto
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.auth.scope import (
    ensure_session_property_allowed,
    property_path_guard,
    session_allowed_property_ids,
)
from mhvp.core.bulk import BULK_MAX_ITEMS, BulkResultOut, run_bulk
from mhvp.core.events import diff, emit
from mhvp.core.listparams import (
    LIST_PARAMS_DOC,
    ListParams,
    apply_filters,
    apply_sort,
    check_include,
    embed,
    list_params,
    strict_query,
    valid_on,
)
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document
from mhvp.properties import schemas as s
from mhvp.properties import services as svc
from mhvp.properties.models import (
    AllocationKey,
    AllocationKeyTemplate,
    BankAccountKind,
    Building,
    LegalEntity,
    MaintenanceItem,
    ManagementType,
    Meter,
    MeterChange,
    MeterReading,
    Property,
    PropertyBankAccount,
    PropertyBillingPeriod,
    PropertyContact,
    PropertyOwner,
    PropertyPortalDocument,
    PropertyStatus,
    ServiceProviderRelation,
    SubCommunity,
    Unit,
    UnitAllocationValue,
    UnitVacancyAllocationValue,
    UnitVatOption,
)

router = APIRouter(tags=["Objekte"], dependencies=[Depends(property_path_guard)])
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]
READ = require_permission("properties:read")
CREATE = require_permission("properties:create")
UPDATE = require_permission("properties:update")


def _nf() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


async def _check_energy_document(session: Any, document_id: uuid.UUID | None) -> None:
    """GA02-03: the energy certificate document must exist in the tenant (reference only)."""
    if document_id is not None:
        await svc.check_documents_exist(session, [document_id], "Energieausweis")


async def _get(session: Any, model: Any, entity_id: uuid.UUID) -> Any:
    row = await session.get(model, entity_id)
    if row is None:
        raise _nf()
    # M2-02/S16-02: property assignment of the membership (404 outside it).
    if model is Property:
        ensure_session_property_allowed(session, row.id)
    elif isinstance(getattr(row, "property_id", None), uuid.UUID):
        ensure_session_property_allowed(session, row.property_id)
    return row


def _check_version(if_match: str | None, version: int) -> None:
    if if_match is not None and if_match.strip('"') != str(version):
        raise ProblemError(ErrorCodes.VERSION_CONFLICT)


async def _unique(session: Any, message: str) -> None:
    try:
        await session.flush()
    except IntegrityError:
        raise ProblemError(ErrorCodes.CONFLICT, detail=message) from None


async def _property_out(session: Any, prop: Property) -> s.PropertyOut:
    await session.flush()
    await session.refresh(prop)
    entities = (
        await session.scalars(
            select(LegalEntity).where(LegalEntity.property_id == prop.id).order_by(LegalEntity.kind)
        )
    ).all()
    out = s.PropertyOut.model_validate(prop)
    out.legal_entities = [s.LegalEntityOut.model_validate(e) for e in entities]
    return out


# Properties ----------------------------------------------------------------------------


_PROPERTY_FILTERS = {
    "status": Property.status,
    "management_type": Property.management_type,
    "management_mode": Property.management_mode,
    "property_type_code": Property.property_type_code,
    "city": Property.city,
    "postal_code": Property.postal_code,
    "manager_user_id": Property.manager_user_id,
    "source_system": Property.source_system,
}
_PROPERTY_SORT = {
    "number": Property.number,
    "name": Property.name,
    "city": Property.city,
    "postal_code": Property.postal_code,
    "status": Property.status,
    "managed_from": Property.managed_from,
    "created_at": Property.created_at,
    "updated_at": Property.updated_at,
}


@router.get(
    "/properties",
    summary="Objekte",
    response_model=s.PropertyPage,
    description=LIST_PARAMS_DOC
    + " include: legal_entities (Rechtsträger des Objekts und der Objekteigentümer).",
    dependencies=[Depends(strict_query)],
)
async def list_properties(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    status: PropertyStatus | None = None,
    management_type: ManagementType | None = None,
    sev_only: bool = Query(
        default=False,
        description="Nur WEG-Objekte mit SEV, für die Mietverträge hinterlegt sind",
    ),
    without_owner: bool = Query(
        default=False,
        description="Nur Mietverwaltungsobjekte ohne aktiven Objekteigentümer",
    ),
    include_terminated: bool = Query(
        default=False,
        description=(
            "Deaktivierte Objekte (Status terminated) mit ausgeben. Nur für den Superadmin "
            "wirksam, für alle anderen ohne Wirkung (operator 27.09.2026)."
        ),
    ),
    page: Page = 1,
    page_size: PageSize = 50,
    params: ListParams = Depends(list_params),
    principal: TenantPrincipal = Depends(READ),
) -> Any:
    from mhvp.contracts.models import Contract

    includes = check_include(params, ("legal_entities",))

    today = datetime.now(ZoneInfo("Europe/Berlin")).date()
    owned = select(PropertyOwner.property_id).where(svc.active_owner_filter(today))
    # Terminated properties are hidden by default; only the superadmin sees them, either via
    # include_terminated or an explicit status filter.
    show_terminated = principal.is_superadmin and (
        include_terminated or status is PropertyStatus.TERMINATED
    )
    async with tenant_tx(request, principal) as session:
        query = apply_filters(select(Property), params, _PROPERTY_FILTERS)
        allowed = session_allowed_property_ids(session)
        if allowed is not None:
            query = query.where(Property.id.in_(list(allowed)))
        if without_owner:
            query = query.where(
                Property.management_type == ManagementType.RENTAL, Property.id.not_in(owned)
            )
        if status:
            query = query.where(Property.status == status)
        if not show_terminated:
            query = query.where(Property.status != PropertyStatus.TERMINATED)
        if management_type:
            query = query.where(Property.management_type == management_type)
        if sev_only:
            tenancy = (
                select(Unit.property_id)
                .join(Contract, Contract.unit_id == Unit.id)
                .where(Contract.kind == "tenancy")
            )
            query = query.where(
                Property.management_type == ManagementType.HOA_WITH_SEV,
                Property.id.in_(tenancy),
            )
        if q:
            like = f"%{q.strip()}%"
            query = query.where(
                or_(
                    Property.number.like(like),
                    Property.name.ilike(like),
                    Property.street.ilike(like),
                    Property.city.ilike(like),
                )
            )
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = (
            await session.scalars(
                apply_sort(query, params, _PROPERTY_SORT, (Property.number, Property.id))
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        rental = [r.id for r in rows if r.management_type is ManagementType.RENTAL]
        with_owner = (
            set(
                (
                    await session.scalars(
                        owned.where(PropertyOwner.property_id.in_(rental)).distinct()
                    )
                ).all()
            )
            if rental
            else set()
        )
        items = []
        for r in rows:
            item = s.PropertySummary.model_validate(r)
            item.owner_missing = r.management_type is ManagementType.RENTAL and (
                r.id not in with_owner
            )
            items.append(item)
        embedded: dict[str, Any] = {}
        if "legal_entities" in includes:
            from mhvp.properties.refs import legal_entity_refs_by_property

            entities = await legal_entity_refs_by_property(session, [r.id for r in rows])
            embedded["legal_entities"] = lambda item: entities.get(uuid.UUID(item["id"]), [])
        return embed(
            s.PropertyPage(items=items, total=total, page=page, page_size=page_size),
            params,
            s.PropertySummary,
            embedded,
        )


class PropertyBulkIn(BaseModel):
    """Bulk action on properties (S12-05): ``set_consumption_info`` switches the monthly
    consumption information (rule H03) per property on or off."""

    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX_ITEMS)
    action: Literal["set_consumption_info"]
    value: bool


@router.post(
    "/properties/bulk",
    summary="Massenaktion Objekte mit Teilerfolgsbericht",
    response_model=BulkResultOut,
)
async def bulk_properties(
    body: PropertyBulkIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> BulkResultOut:
    """Each property on its own (savepoint); a property outside the tenant or the object
    assignment of the membership is reported as not found."""
    async with tenant_tx(request, principal) as session:

        async def act(property_id: uuid.UUID) -> None:
            prop = await _get(session, Property, property_id)
            if prop.consumption_info_enabled is body.value:
                return
            before = {"consumption_info_enabled": prop.consumption_info_enabled}
            prop.consumption_info_enabled = body.value
            await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="property.updated",
                entity_type="property",
                entity_id=prop.id,
                actor_user_id=principal.user_id,
                payload={"bulk": body.action},
                changes=diff(before, {"consumption_info_enabled": body.value}),
            )

        return await run_bulk(body.ids, act, savepoint=session.begin_nested)


class UnitBulkIn(BaseModel):
    """Bulk action on units (GAB-16, section 12): sets one descriptive field on many units.
    Master data only; no field with money effect (areas, allocation values, VAT) is offered."""

    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(min_length=1, max_length=BULK_MAX_ITEMS)
    action: Literal["set_floor", "set_location", "set_features"]
    value: str | None = Field(default=None, max_length=1000)


_UNIT_BULK_FIELD = {
    "set_floor": ("floor", 20),
    "set_location": ("location", 100),
    "set_features": ("features", 1000),
}


@router.post(
    "/units/bulk",
    summary="Massenaktion Einheiten mit Teilerfolgsbericht",
    response_model=BulkResultOut,
)
async def bulk_units(
    body: UnitBulkIn, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> BulkResultOut:
    """Each unit on its own (savepoint); a unit outside the tenant or the object assignment of
    the membership is reported as not found, an overlong value as a validation problem."""
    field, limit = _UNIT_BULK_FIELD[body.action]
    value = (body.value or "").strip() or None
    if value is not None and len(value) > limit:
        raise svc.invalid(f"Wert zu lang (höchstens {limit} Zeichen).")
    async with tenant_tx(request, principal) as session:

        async def act(unit_id: uuid.UUID) -> None:
            unit = await _get(session, Unit, unit_id)
            if getattr(unit, field) == value:
                return
            before = {field: getattr(unit, field)}
            setattr(unit, field, value)
            unit.version += 1
            unit.updated_by = principal.user_id
            await session.flush()
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="unit.updated",
                entity_type="unit",
                entity_id=unit.id,
                actor_user_id=principal.user_id,
                payload={"bulk": body.action},
                changes=diff(before, {field: value}),
            )

        return await run_bulk(body.ids, act, savepoint=session.begin_nested)


@router.post("/properties", status_code=201, summary="Objekt anlegen")
async def create_property(
    body: s.PropertyIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.PropertyOut:
    async with tenant_tx(request, principal) as session:
        svc.check_postcode(body.country, body.postal_code)
        await svc.check_catalog(session, "property_type", body.property_type_code)
        await svc.check_documents_exist(session, body.images, "Bilder")
        data = body.model_dump()
        data["custom_fields"] = await svc.check_custom_fields(
            session,
            "property",
            body.custom_fields,
            management_type=body.management_type,
            create=True,
        )
        prop = Property(tenant_id=principal.tenant_id, created_by=principal.user_id, **data)
        session.add(prop)
        await _unique(session, f"Objektnummer {body.number} ist bereits vergeben.")
        await svc.ensure_hoa_entity(session, prop)
        await svc.copy_key_templates(session, prop)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.created",
            entity_type="property",
            entity_id=prop.id,
            actor_user_id=principal.user_id,
            payload={"number": prop.number, "management_type": prop.management_type.value},
        )
        return await _property_out(session, prop)


@router.get("/properties/{property_id}", summary="Objekt lesen")
async def get_property(
    property_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
) -> s.PropertyOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        response.headers["ETag"] = f'"{prop.version}"'
        return await _property_out(session, prop)


@router.put("/properties/{property_id}", summary="Objekt ändern")
async def update_property(
    property_id: uuid.UUID,
    body: s.PropertyIn,
    request: Request,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PropertyOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        _check_version(if_match, prop.version)
        if (body.postal_code, body.country) != (prop.postal_code, prop.country):
            svc.check_postcode(body.country, body.postal_code)
        if body.management_type != prop.management_type:
            raise svc.invalid(
                "Die Verwaltungsart kann nach Anlage nicht geändert werden (Rechtsträger, 6.9.1)."
            )
        await svc.check_custom_fields(
            session,
            "property",
            body.custom_fields,
            management_type=prop.management_type,
            entity_id=prop.id,
        )
        await svc.check_documents_exist(session, body.images, "Bilder")
        before = s.PropertyIn.model_validate(prop, from_attributes=True).model_dump(mode="json")
        for key, value in body.model_dump().items():
            setattr(prop, key, value)
        prop.version += 1
        prop.updated_by = principal.user_id
        await _unique(session, f"Objektnummer {body.number} ist bereits vergeben.")
        changes = diff(before, body.model_dump(mode="json"))
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.updated",
            entity_type="property",
            entity_id=prop.id,
            actor_user_id=principal.user_id,
            changes=changes,
        )
        return await _property_out(session, prop)


@router.post("/properties/{property_id}/status", summary="Objektstatus ändern")
async def change_status(
    property_id: uuid.UUID,
    body: s.StatusChange,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PropertyOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        if body.status not in svc.ALLOWED_TRANSITIONS[prop.status]:
            raise svc.invalid(
                f"Statuswechsel von {prop.status.value} nach {body.status.value} "
                "ist nicht zulässig."
            )
        if body.status is PropertyStatus.ACTIVE:
            units = await session.scalar(
                select(func.count()).where(
                    Unit.property_id == prop.id, Unit.is_fictional.is_(False)
                )
            )
            if not units:
                raise svc.invalid(
                    "Ein Objekt kann erst mit mindestens einer Einheit aktiviert werden."
                )
        if body.status is PropertyStatus.TERMINATED and prop.managed_to is None:
            raise svc.invalid(
                "Für die Beendigung muss das Ende der Verwaltung (managed_to) gesetzt sein."
            )
        old = prop.status.value
        prop.status = body.status
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.activated"
            if body.status is PropertyStatus.ACTIVE
            else "property.status_changed",
            entity_type="property",
            entity_id=prop.id,
            actor_user_id=principal.user_id,
            changes={"status": {"old": old, "new": body.status.value}},
        )
        return await _property_out(session, prop)


# Buildings and units -------------------------------------------------------------------


@router.get(
    "/properties/{property_id}/buildings", summary="Gebäude", dependencies=[Depends(strict_query)]
)
async def list_buildings(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.BuildingOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(Building).where(Building.property_id == property_id).order_by(Building.name)
            )
        ).all()
        return [s.BuildingOut.model_validate(b) for b in rows]


@router.post("/properties/{property_id}/buildings", status_code=201, summary="Gebäude anlegen")
async def create_building(
    property_id: uuid.UUID,
    body: s.BuildingIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.BuildingOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        await _check_energy_document(session, body.energy_certificate_document_id)
        data = body.model_dump()
        data["custom_fields"] = await svc.check_custom_fields(
            session,
            "building",
            body.custom_fields,
            management_type=prop.management_type,
            create=True,
        )
        building = Building(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            created_by=principal.user_id,
            **data,
        )
        session.add(building)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="building.created",
            entity_type="building",
            entity_id=building.id,
            actor_user_id=principal.user_id,
            payload={"property_id": str(property_id)},
        )
        await session.refresh(building)
        return s.BuildingOut.model_validate(building)


@router.get("/buildings/{building_id}", summary="Gebäude lesen")
async def get_building(
    building_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(READ),
) -> s.BuildingOut:
    async with tenant_tx(request, principal) as session:
        building = await _get(session, Building, building_id)
        response.headers["ETag"] = f'"{building.version}"'
        return s.BuildingOut.model_validate(building)


@router.put("/buildings/{building_id}", summary="Gebäude ändern (If-Match)")
async def update_building(
    building_id: uuid.UUID,
    body: s.BuildingIn,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.BuildingOut:
    async with tenant_tx(request, principal) as session:
        building = await _get(session, Building, building_id)
        _check_version(if_match, building.version)
        prop = await _get(session, Property, building.property_id)
        await _check_energy_document(session, body.energy_certificate_document_id)
        await svc.check_custom_fields(
            session,
            "building",
            body.custom_fields,
            management_type=prop.management_type,
            entity_id=building.id,
        )
        before = s.BuildingIn.model_validate(building, from_attributes=True).model_dump(mode="json")
        for key, value in body.model_dump().items():
            setattr(building, key, value)
        building.version += 1
        building.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="building.updated",
            entity_type="building",
            entity_id=building.id,
            actor_user_id=principal.user_id,
            changes=diff(before, body.model_dump(mode="json")),
        )
        await session.refresh(building)
        response.headers["ETag"] = f'"{building.version}"'
        return s.BuildingOut.model_validate(building)


async def _unit_out(session: Any, unit: Unit, as_of: date | None) -> s.UnitOut:
    await session.refresh(unit)
    return (await _units_out(session, [unit], as_of))[0]


async def _units_out(session: Any, units: Sequence[Unit], as_of: date | None) -> list[s.UnitOut]:
    """Allocation values and VAT options of all units in two queries instead of two per unit
    (performance review 26.09.2026)."""
    if not units:
        return []
    ids = [u.id for u in units]
    query = (
        select(UnitAllocationValue, AllocationKey.code, AllocationKey.name)
        .join(AllocationKey, AllocationKey.id == UnitAllocationValue.allocation_key_id)
        .where(UnitAllocationValue.unit_id.in_(ids))
    )
    vat = select(UnitVatOption).where(UnitVatOption.unit_id.in_(ids))
    if as_of is not None:
        query = query.where(svc.valid_at(UnitAllocationValue, as_of))
        vat = vat.where(svc.valid_at(UnitVatOption, as_of))
    values: dict[uuid.UUID, list[s.AllocationValueOut]] = {}
    for v, code, name in (
        await session.execute(
            query.order_by(AllocationKey.sort_order, UnitAllocationValue.valid_from)
        )
    ).all():
        values.setdefault(v.unit_id, []).append(
            s.AllocationValueOut.model_validate(v).model_copy(
                update={"key_code": code, "key_name": name}
            )
        )
    # Latest option per unit: rows come newest first, the first one per unit wins.
    options: dict[uuid.UUID, Any] = {}
    for o in (await session.scalars(vat.order_by(UnitVatOption.valid_from.desc()))).all():
        options.setdefault(o.unit_id, o.option)
    out = []
    for unit in units:
        row = s.UnitOut.model_validate(unit)
        row.allocation_values = values.get(unit.id, [])
        row.vat_option = options.get(unit.id)
        out.append(row)
    return out


async def _occupants(
    session: Any, unit_ids: list[uuid.UUID], as_of: date
) -> dict[uuid.UUID, list[tuple[s.OccupantOut, bool]]]:
    """All contracts of the given units with party members and current rent.

    One query for contracts, one for members and one for payments, independent of the number
    of units. Returns per unit a list of (occupant, is_current_at_as_of), newest first.
    """
    from mhvp.contracts.models import Contract, ContractPayment

    result: dict[uuid.UUID, list[tuple[s.OccupantOut, bool]]] = {u: [] for u in unit_ids}
    if not unit_ids:
        return result
    rows = (
        await session.execute(
            select(Contract, Party.name)
            .join(Party, Party.id == Contract.party_id)
            .where(Contract.unit_id.in_(unit_ids))
            .order_by(Contract.start_date.desc())
        )
    ).all()
    party_ids = {c.party_id for c, _ in rows}
    members: dict[uuid.UUID, list[s.OccupantMemberOut]] = {}
    if party_ids:
        for m, name in (
            await session.execute(
                select(PartyMember, Contact.display_name)
                .join(Contact, Contact.id == PartyMember.contact_id)
                .where(PartyMember.party_id.in_(party_ids))
                .order_by(Contact.display_name)
            )
        ).all():
            members.setdefault(m.party_id, []).append(
                s.OccupantMemberOut(
                    contact_id=m.contact_id, display_name=name, share_percent=m.share_percent
                )
            )
    rent: dict[uuid.UUID, Decimal] = {}
    tenancy_ids = [c.id for c, _ in rows if str(c.kind) == "tenancy"]
    if tenancy_ids:
        for p in (
            await session.scalars(
                select(ContractPayment).where(
                    ContractPayment.contract_id.in_(tenancy_ids),
                    svc.valid_at(ContractPayment, as_of),
                )
            )
        ).all():
            rent[p.contract_id] = rent.get(p.contract_id, Decimal(0)) + p.gross
    for c, party_name in rows:
        current = c.start_date <= as_of and (c.end_date is None or c.end_date >= as_of)
        occ = s.OccupantOut(
            contract_id=c.id,
            contract_number=c.number,
            kind=str(c.kind),
            party_id=c.party_id,
            party_name=party_name,
            start_date=c.start_date,
            end_date=c.end_date,
            members=members.get(c.party_id, []),
            rent_gross=rent.get(c.id),
        )
        result[c.unit_id].append((occ, current))
    return result


def _today() -> date:
    return datetime.now(ZoneInfo("Europe/Berlin")).date()


def _current(entries: list[tuple[s.OccupantOut, bool]], kind: str) -> s.OccupantOut | None:
    return next((o for o, cur in entries if cur and o.kind == kind), None)


@router.get(
    "/properties/{property_id}/units",
    summary="Einheiten, optional zum Stichtag",
    dependencies=[Depends(strict_query)],
)
async def list_units(
    property_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    with_occupants: bool = False,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.UnitOut]:
    """Units in natural order of their number ("1" < "2" < "10", "WE1" < "WE10").

    With ``with_occupants=true`` each unit carries its current owner and tenant (at ``as_of``,
    default today), loaded in one batch for the whole property.
    """
    async with tenant_tx(request, principal) as session:
        units = sorted(
            (await session.scalars(select(Unit).where(Unit.property_id == property_id))).all(),
            key=lambda u: svc.natural_key(u.number),
        )
        out = await _units_out(session, units, as_of)
        if with_occupants:
            occ = await _occupants(session, [u.id for u in units], as_of or _today())
            for o in out:
                o.owner = _current(occ[o.id], "ownership")
                o.tenant = _current(occ[o.id], "tenancy")
        return out


@router.get("/units/{unit_id}/occupants", summary="Eigentümer, Mieter und Vertragshistorie")
async def get_unit_occupants(
    unit_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> s.UnitOccupantsOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Unit, unit_id)
        day = as_of or _today()
        entries = (await _occupants(session, [unit_id], day))[unit_id]
        return s.UnitOccupantsOut(
            owner=_current(entries, "ownership"),
            tenant=_current(entries, "tenancy"),
            history=[o for o, cur in entries if not cur and o.start_date <= day],
        )


@router.post("/properties/{property_id}/units", status_code=201, summary="Einheit anlegen")
async def create_unit(
    property_id: uuid.UUID,
    body: s.UnitIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.UnitOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        building = await _get(session, Building, body.building_id)
        if building.property_id != property_id:
            raise svc.invalid("Das Gebäude gehört nicht zu diesem Objekt.")
        await svc.check_sub_community(session, body.sub_community_id, property_id)
        data = body.model_dump()
        data["custom_fields"] = await svc.check_custom_fields(
            session,
            "unit",
            body.custom_fields,
            management_type=prop.management_type,
            create=True,
        )
        unit = Unit(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            created_by=principal.user_id,
            **data,
        )
        session.add(unit)
        await _unique(
            session, f"Einheitennummer {body.number} ist in diesem Objekt bereits vergeben."
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="unit.created",
            entity_type="unit",
            entity_id=unit.id,
            actor_user_id=principal.user_id,
            payload={"property_id": str(property_id), "number": unit.number},
        )
        return await _unit_out(session, unit, None)


@router.get("/units/{unit_id}", summary="Einheit lesen, optional zum Stichtag")
async def get_unit(
    unit_id: uuid.UUID,
    request: Request,
    response: Response,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> s.UnitOut:
    async with tenant_tx(request, principal) as session:
        unit = await _get(session, Unit, unit_id)
        response.headers["ETag"] = f'"{unit.version}"'
        return await _unit_out(session, unit, as_of)


@router.put("/units/{unit_id}", summary="Einheit ändern (If-Match)")
async def update_unit(
    unit_id: uuid.UUID,
    body: s.UnitIn,
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.UnitOut:
    async with tenant_tx(request, principal) as session:
        unit = await _get(session, Unit, unit_id)
        _check_version(if_match, unit.version)
        building = await _get(session, Building, body.building_id)
        if building.property_id != unit.property_id:
            raise svc.invalid("Das Gebäude gehört nicht zu diesem Objekt.")
        await svc.check_sub_community(session, body.sub_community_id, unit.property_id)
        prop = await _get(session, Property, unit.property_id)
        await svc.check_custom_fields(
            session,
            "unit",
            body.custom_fields,
            management_type=prop.management_type,
            entity_id=unit.id,
        )
        before = s.UnitIn.model_validate(unit, from_attributes=True).model_dump(mode="json")
        for key, value in body.model_dump().items():
            setattr(unit, key, value)
        unit.version += 1
        unit.updated_by = principal.user_id
        response.headers["ETag"] = f'"{unit.version}"'
        await _unique(
            session, f"Einheitennummer {body.number} ist in diesem Objekt bereits vergeben."
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="unit.updated",
            entity_type="unit",
            entity_id=unit.id,
            actor_user_id=principal.user_id,
            changes=diff(before, body.model_dump(mode="json")),
        )
        return await _unit_out(session, unit, None)


# Allocation keys and values ------------------------------------------------------------


@router.get(
    "/properties/{property_id}/allocation-keys",
    summary="Umlageschlüssel",
    dependencies=[Depends(strict_query)],
)
async def list_keys(
    property_id: uuid.UUID,
    request: Request,
    as_of: date | None = Query(
        default=None,
        description="Stichtag: nur Schlüssel mit einem am Tag gültigen Einheitenwert",
    ),
    principal: TenantPrincipal = Depends(READ),
) -> list[s.AllocationKeyOut]:
    async with tenant_tx(request, principal) as session:
        query = select(AllocationKey).where(AllocationKey.property_id == property_id)
        if as_of is not None:
            in_force = valid_on(
                select(UnitAllocationValue.id).where(
                    UnitAllocationValue.allocation_key_id == AllocationKey.id
                ),
                as_of,
                UnitAllocationValue.valid_from,
                UnitAllocationValue.valid_to,
            )
            query = query.where(in_force.exists())
        rows = (await session.scalars(query.order_by(AllocationKey.sort_order))).all()
        return [s.AllocationKeyOut.model_validate(k) for k in rows]


@router.post(
    "/properties/{property_id}/allocation-keys", status_code=201, summary="Umlageschlüssel anlegen"
)
async def create_key(
    property_id: uuid.UUID,
    body: s.AllocationKeyIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.AllocationKeyOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        await svc.check_catalog(session, "meter_type", body.meter_type_code)
        await _check_key_document(session, body.source_document_id)
        key = AllocationKey(
            tenant_id=principal.tenant_id, property_id=property_id, **body.model_dump()
        )
        session.add(key)
        await _unique(session, f"Schlüssel {body.code} existiert bereits.")
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="allocation_key.created",
            entity_type="allocation_key",
            entity_id=key.id,
            actor_user_id=principal.user_id,
            payload={"code": key.code},
        )
        await session.refresh(key)
        return s.AllocationKeyOut.model_validate(key)


@router.patch(
    "/properties/{property_id}/allocation-keys/{key_id}", summary="Umlageschlüssel ändern"
)
async def update_key(
    property_id: uuid.UUID,
    key_id: uuid.UUID,
    body: s.AllocationKeyPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.AllocationKeyOut:
    """Name, unit, kind, sort order and the operator entered ``expected_total`` (C1). The code
    stays immutable; the sum check against ``expected_total`` is a warning in the CRM only."""
    async with tenant_tx(request, principal) as session:
        key = await _get(session, AllocationKey, key_id)
        if key.property_id != property_id:
            raise _nf()
        changes = body.model_dump(exclude_unset=True)
        if "meter_type_code" in changes:
            await svc.check_catalog(session, "meter_type", changes["meter_type_code"])
        if "source_document_id" in changes:
            await _check_key_document(session, changes["source_document_id"])
        before = s.AllocationKeyOut.model_validate(key).model_dump(mode="json")
        source_changed = any(
            f in changes and changes[f] != getattr(key, f) for f in s.ALLOCATION_KEY_SOURCE_FIELDS
        )
        for field, value in changes.items():
            setattr(key, field, value)
        if source_changed:
            # GAM-108: a changed source needs a new confirmation.
            key.confirmed_at = None
            key.confirmed_by = None
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="allocation_key.updated",
            entity_type="allocation_key",
            entity_id=key.id,
            actor_user_id=principal.user_id,
            changes=diff(before, s.AllocationKeyOut.model_validate(key).model_dump(mode="json")),
        )
        await session.refresh(key)
        return s.AllocationKeyOut.model_validate(key)


async def _check_key_document(session: AsyncSession, document_id: uuid.UUID | None) -> None:
    if document_id is not None and await session.get(Document, document_id) is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Dokument der Quelle nicht gefunden.")


@router.put(
    "/properties/{property_id}/allocation-keys/{key_id}/confirmation",
    summary="Quelle des Umlageschlüssels bestätigen oder Bestätigung aufheben (GAM-108)",
)
async def confirm_key(
    property_id: uuid.UUID,
    key_id: uuid.UUID,
    body: s.AllocationKeyConfirmationIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.AllocationKeyOut:
    """A person confirms the recorded source (kind, start of validity and a reference or a
    document). The confirmation records who and when; it states that the source was checked,
    not that the key is legally effective (M17-01 stays open)."""
    async with tenant_tx(request, principal) as session:
        key = await _get(session, AllocationKey, key_id)
        if key.property_id != property_id:
            raise _nf()
        if body.confirmed:
            if key.source_kind is None or key.source_valid_from is None:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Bestätigung braucht Art der Quelle und Geltungsbeginn.",
                )
            if not (key.source_reference or key.source_document_id):
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Bestätigung braucht eine Fundstelle oder ein Dokument.",
                )
            key.confirmed_at = datetime.now(UTC)
            key.confirmed_by = principal.user_id
        else:
            key.confirmed_at = None
            key.confirmed_by = None
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="allocation_key.confirmed" if body.confirmed else "allocation_key.unconfirmed",
            entity_type="allocation_key",
            entity_id=key.id,
            actor_user_id=principal.user_id,
            payload={
                "code": key.code,
                "source_kind": key.source_kind,
                "source_valid_from": (
                    key.source_valid_from.isoformat() if key.source_valid_from else None
                ),
            },
        )
        await session.refresh(key)
        return s.AllocationKeyOut.model_validate(key)


@router.get(
    "/properties/{property_id}/allocation-summary",
    summary="Schlüsselwerte aller Einheiten zum Stichtag mit Summen je Schlüssel",
)
async def allocation_summary(
    property_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> s.AllocationSummaryOut:
    """Matrix for the CRM (C1): every key of the property with the sum of the unit values valid
    at ``as_of`` (default today, Europe/Berlin), the units in natural order and the single
    values. ``difference`` is ``total - expected_total`` for information only; a deviation is
    shown as a warning and never blocks an entry."""
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        day = as_of or _today()
        keys = (
            await session.scalars(
                select(AllocationKey)
                .where(AllocationKey.property_id == property_id)
                .order_by(AllocationKey.sort_order, AllocationKey.code)
            )
        ).all()
        units = sorted(
            (await session.scalars(select(Unit).where(Unit.property_id == property_id))).all(),
            key=lambda u: svc.natural_key(u.number),
        )
        values: list[UnitAllocationValue] = []
        if units:
            values = list(
                (
                    await session.scalars(
                        select(UnitAllocationValue)
                        .where(
                            UnitAllocationValue.unit_id.in_([u.id for u in units]),
                            svc.valid_at(UnitAllocationValue, day),
                        )
                        .order_by(UnitAllocationValue.valid_from)
                    )
                ).all()
            )
        totals: dict[uuid.UUID, Decimal] = {}
        counted: dict[uuid.UUID, set[uuid.UUID]] = {}
        for v in values:
            totals[v.allocation_key_id] = totals.get(v.allocation_key_id, Decimal(0)) + v.value
            counted.setdefault(v.allocation_key_id, set()).add(v.unit_id)
        key_rows = []
        for k in keys:
            total = totals.get(k.id, Decimal(0))
            with_value = len(counted.get(k.id, set()))
            key_rows.append(
                s.AllocationSummaryKeyOut(
                    id=k.id,
                    code=k.code,
                    name=k.name,
                    unit_of_measure=k.unit_of_measure,
                    kind=k.kind,
                    expected_total=k.expected_total,
                    total=total,
                    units_with_value=with_value,
                    units_without_value=len(units) - with_value,
                    difference=None if k.expected_total is None else total - k.expected_total,
                )
            )
        return s.AllocationSummaryOut(
            as_of=day,
            keys=key_rows,
            units=[
                s.AllocationSummaryUnitOut(
                    id=u.id, number=u.number, label=u.label, is_fictional=u.is_fictional
                )
                for u in units
            ],
            values=[
                s.AllocationSummaryValueOut.model_validate(v, from_attributes=True) for v in values
            ],
        )


@router.get(
    "/units/{unit_id}/allocation-values",
    summary="Schlüsselwerte, Historie oder Stichtag",
    dependencies=[Depends(strict_query)],
)
async def list_values(
    unit_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.AllocationValueOut]:
    async with tenant_tx(request, principal) as session:
        return (
            await _unit_out(session, await _get(session, Unit, unit_id), as_of)
        ).allocation_values


@router.post(
    "/units/{unit_id}/allocation-values",
    status_code=201,
    summary="Schlüsselwert mit Zeitraum erfassen",
)
async def add_value(
    unit_id: uuid.UUID,
    body: s.AllocationValueIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.AllocationValueOut:
    async with tenant_tx(request, principal) as session:
        unit = await _get(session, Unit, unit_id)
        key = await _get(session, AllocationKey, body.allocation_key_id)
        if key.property_id != unit.property_id:
            raise svc.invalid("Der Schlüssel gehört nicht zum Objekt der Einheit.")
        try:
            async with session.begin_nested():
                row, previous = await svc.add_allocation_value(
                    session,
                    principal.tenant_id,
                    unit_id,
                    key.id,
                    body.value,
                    body.valid_from,
                    body.valid_to,
                    body.source,
                )
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Der Zeitraum überschneidet sich mit einem vorhandenen Wert.",
            ) from None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="unit.allocation_value_added",
            entity_type="unit",
            entity_id=unit_id,
            actor_user_id=principal.user_id,
            payload={
                "key": key.code,
                "value": str(body.value),
                "valid_from": body.valid_from.isoformat(),
                "closed_previous_until": previous.valid_to.isoformat()
                if previous and previous.valid_to
                else None,
            },
        )
        return s.AllocationValueOut.model_validate(row).model_copy(update={"key_code": key.code})


@router.post(
    "/units/{unit_id}/vat-options", status_code=201, summary="Umsatzsteueroption mit Zeitraum"
)
async def add_vat_option(
    unit_id: uuid.UUID,
    body: s.VatOptionIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.UnitOut:
    async with tenant_tx(request, principal) as session:
        unit = await _get(session, Unit, unit_id)
        try:
            async with session.begin_nested():
                session.add(
                    UnitVatOption(
                        tenant_id=principal.tenant_id, unit_id=unit_id, **body.model_dump()
                    )
                )
                await session.flush()
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Zeitraum überschneidet sich."
            ) from None
        # Recorded as master data only; tax treatment needs a released rule (S01, D45).
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="unit.vat_option_added",
            entity_type="unit",
            entity_id=unit_id,
            actor_user_id=principal.user_id,
            payload={"option": body.option.value, "valid_from": body.valid_from.isoformat()},
        )
        return await _unit_out(session, unit, body.valid_from)


# Owners, legal entities, bank accounts --------------------------------------------------


@router.post(
    "/properties/{property_id}/owners", status_code=201, summary="Objekteigentümer (Mietverwaltung)"
)
async def add_owner(
    property_id: uuid.UUID,
    body: s.OwnerIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.OwnerOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        if prop.management_type.value != "rental":
            raise svc.invalid(
                "Objekteigentümer werden nur bei Mietverwaltung erfasst; "
                "WEG-Eigentum folgt über Eigentumsverträge (M5)."
            )
        await _get(session, Party, body.party_id)
        await _check_owner_details(session, property_id, body)
        problems = await svc.owner_period_problems(
            session,
            property_id,
            body.party_id,
            body.valid_from,
            body.valid_to,
            body.share_percent,
        )
        if problems:
            raise svc.invalid(" ".join(problems))
        owner = PropertyOwner(
            tenant_id=principal.tenant_id, property_id=property_id, **body.model_dump()
        )
        session.add(owner)
        entity_id = await svc.owner_entity(session, prop, body.party_id)
        await session.flush()
        await recompute_for_party(session, body.party_id)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.owner_added",
            entity_type="property",
            entity_id=property_id,
            actor_user_id=principal.user_id,
            payload={"party_id": str(body.party_id), "legal_entity_id": str(entity_id)},
        )
        return s.OwnerOut(id=owner.id, legal_entity_id=entity_id, **body.model_dump())


async def _check_owner_details(session: Any, property_id: uuid.UUID, body: Any) -> None:
    await svc.check_ledger_account(
        session, body.clearing_account_id, property_id, "Das Verrechnungskonto"
    )
    if body.power_of_attorney_document_id is not None:
        await _get(session, Document, body.power_of_attorney_document_id)
    if body.tax_advisor_contact_id is not None:
        await _get(session, Contact, body.tax_advisor_contact_id)


@router.put(
    "/properties/{property_id}/owners/{owner_id}/details",
    summary="Verrechnungskonto, Vollmacht und Steuerberater eines Objekteigentümers",
)
async def set_owner_details(
    property_id: uuid.UUID,
    owner_id: uuid.UUID,
    body: s.OwnerDetailsIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.OwnerOut:
    async with tenant_tx(request, principal) as session:
        owner = await _get(session, PropertyOwner, owner_id)
        if owner.property_id != property_id:
            raise _nf()
        await _check_owner_details(session, property_id, body)
        before = s.OwnerDetailsIn.model_validate(owner, from_attributes=True).model_dump(
            mode="json"
        )
        for key, value in body.model_dump().items():
            setattr(owner, key, value)
        owner.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.owner_updated",
            entity_type="property",
            entity_id=property_id,
            actor_user_id=principal.user_id,
            changes=diff(before, body.model_dump(mode="json")),
        )
        entity = await svc.owner_entity(
            session, await _get(session, Property, property_id), owner.party_id
        )
        out = s.OwnerOut.model_validate(owner)
        out.legal_entity_id = entity
        return out


def _berlin_today() -> date:
    return datetime.now(ZoneInfo("Europe/Berlin")).date()


@router.get(
    "/properties/{property_id}/owners",
    summary="Aktuelle Objekteigentümer",
    dependencies=[Depends(strict_query)],
)
async def list_owners(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.CurrentOwnerOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        rows = await svc.owner_rows(session, property_id, _berlin_today())
        return [s.CurrentOwnerOut(**r) for r in rows]


@router.post("/properties/{property_id}/owner", summary="Eigentümer festlegen (Mietverwaltung)")
async def set_owner(
    property_id: uuid.UUID,
    body: s.OwnerSetIn,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.OwnerSetOut:
    """Owner of a rental property from a contact: party (single member, role primary) and
    legal entity rental_owner are used or created. Idempotent: the same active owner is
    reported unchanged, another active owner is never overwritten unless ``replace`` is set,
    which ends the previous entries the day before the new start."""
    from mhvp.imports.zuordnung import party_for

    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        if prop.management_type is not ManagementType.RENTAL:
            raise svc.invalid(
                "Eigentümer werden nur bei Mietverwaltung je Objekt geführt; "
                "bei WEG-Objekten wird das Eigentum je Einheit geführt."
            )
        await _get(session, Contact, body.contact_id)
        today = _berlin_today()
        start = body.valid_from or svc.default_owner_start(prop, today)
        party, _ = await party_for(session, principal.tenant_id, principal.user_id, body.contact_id)
        current = (
            await session.scalars(
                select(PropertyOwner)
                .where(PropertyOwner.property_id == property_id, svc.owner_open_filter(today))
                .order_by(PropertyOwner.valid_from)
            )
        ).all()
        same = next((o for o in current if o.party_id == party.id), None)
        if same is not None:
            view = await svc.owner_view(session, same, party.name)
            return s.OwnerSetOut(status="unchanged", owner=s.CurrentOwnerOut(**view))
        others = [o for o in current if o.party_id != party.id]
        if others and not body.replace:
            names = ", ".join(
                [(await svc.owner_view(session, o, ""))["contact_name"] or "" for o in others]
            )
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=(
                    f"Das Objekt hat bereits einen aktiven Eigentümer ({names}). "
                    "Zum Ersetzen replace setzen."
                ),
            )
        ended: list[s.CurrentOwnerOut] = []
        end = start - timedelta(days=1)
        for old in current:
            if old.valid_from > end:
                raise svc.invalid(
                    "Der neue Eigentümer muss nach dem Beginn des bisherigen Eigentümers beginnen."
                )
            old.valid_to = end
            old_name = await session.scalar(select(Party.name).where(Party.id == old.party_id))
            ended.append(s.CurrentOwnerOut(**await svc.owner_view(session, old, old_name or "")))
        owner = PropertyOwner(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            party_id=party.id,
            share_percent=body.share_percent,
            valid_from=start,
        )
        session.add(owner)
        entity_id = await svc.owner_entity(session, prop, party.id)
        await session.flush()
        for party_id in {party.id, *(o.party_id for o in current)}:
            await recompute_for_party(session, party_id)
        status = "replaced" if current else "created"
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.owner_set",
            entity_type="property",
            entity_id=property_id,
            actor_user_id=principal.user_id,
            payload={
                "party_id": str(party.id),
                "contact_id": str(body.contact_id),
                "legal_entity_id": str(entity_id),
                "valid_from": start.isoformat(),
                "status": status,
                "ended": [str(o.id) for o in current],
            },
        )
        response.status_code = 200 if current else 201
        view = await svc.owner_view(session, owner, party.name)
        return s.OwnerSetOut(status=status, owner=s.CurrentOwnerOut(**view), ended=ended)


@router.get(
    "/properties/{property_id}/legal-entities",
    summary="Rechtsträger des Objekts",
    dependencies=[Depends(strict_query)],
)
async def list_entities(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.LegalEntityOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(select(LegalEntity).where(LegalEntity.property_id == property_id))
        ).all()
        return [s.LegalEntityOut.model_validate(e) for e in rows]


def _account_out(a: PropertyBankAccount) -> s.BankAccountOut:
    return s.BankAccountOut(
        id=a.id,
        legal_entity_id=a.legal_entity_id,
        kind=a.kind,
        iban_masked=mask_iban(a.iban),
        bic=a.bic,
        bank_name=a.bank_name,
        holder=a.holder,
        segregated=a.segregated,
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        notes=a.notes,
        ledger_account_id=a.ledger_account_id,
        bank_connection_id=a.bank_connection_id,
        is_default=a.is_default,
    )


async def _set_default_account(session: AsyncSession, account: PropertyBankAccount) -> None:
    """Flag ``account`` as the default payment account of its legal entity (M16-13): at most
    one per legal entity, never a deposit account."""
    if account.kind is BankAccountKind.DEPOSIT:
        raise svc.invalid("Ein Kautionskonto kann nicht Standardkonto sein (M16-13, D56).")
    others = (
        await session.scalars(
            select(PropertyBankAccount).where(
                PropertyBankAccount.legal_entity_id == account.legal_entity_id,
                PropertyBankAccount.is_default.is_(True),
                PropertyBankAccount.id != account.id,
            )
        )
    ).all()
    for other in others:
        other.is_default = False
    await session.flush()
    account.is_default = True
    await session.flush()


@router.get(
    "/properties/{property_id}/bank-accounts",
    summary="Bankkonten",
    dependencies=[Depends(strict_query)],
)
async def list_accounts(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.BankAccountOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(PropertyBankAccount).where(PropertyBankAccount.property_id == property_id)
            )
        ).all()
        return [_account_out(a) for a in rows]


@router.post(
    "/properties/{property_id}/bank-accounts",
    status_code=201,
    summary="Bankkonto eines Rechtsträgers anlegen",
)
async def add_account(
    property_id: uuid.UUID,
    body: s.BankAccountIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.BankAccountOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        entity = await _get(session, LegalEntity, body.legal_entity_id)
        if entity.property_id != property_id:
            raise svc.invalid("Der Rechtsträger gehört nicht zu diesem Objekt.")
        if entity.kind not in svc.ACCOUNT_OWNERS[body.kind]:
            raise svc.invalid(
                f"Ein Konto der Art {body.kind.value} kann nicht dem Rechtsträger "
                f"{entity.kind.value} gehören (6.9.1)."
            )
        await svc.check_ledger_account(
            session, body.ledger_account_id, property_id, "Das Sachkonto"
        )
        await svc.check_bank_connection(session, body.bank_connection_id)
        account = PropertyBankAccount(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            iban_suffix=body.iban[-4:],
            iban_fingerprint=crypto.fingerprint(body.iban),
            segregated=body.kind is BankAccountKind.DEPOSIT,
            created_by=principal.user_id,
            **body.model_dump(exclude={"is_default"}),
        )
        session.add(account)
        await session.flush()
        if body.is_default:
            await _set_default_account(session, account)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property_bank_account.created",
            entity_type="property_bank_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={"kind": body.kind.value, "legal_entity_id": str(entity.id)},
        )
        return _account_out(account)


@router.post(
    "/properties/{property_id}/bank-accounts/{account_id}/default",
    summary="Bankkonto als Standardkonto des Rechtsträgers kennzeichnen (Zahlungsziel im Brief)",
)
async def set_default_account(
    property_id: uuid.UUID,
    account_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.BankAccountOut:
    async with tenant_tx(request, principal) as session:
        account = await _get(session, PropertyBankAccount, account_id)
        if account.property_id != property_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await _set_default_account(session, account)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property_bank_account.default_set",
            entity_type="property_bank_account",
            entity_id=account.id,
            actor_user_id=principal.user_id,
            payload={"legal_entity_id": str(account.legal_entity_id)},
        )
        return _account_out(account)


@router.get(
    "/properties/{property_id}/bank-account-options",
    summary="Auswählbare Bankkonten des Objekts (Stammkonten und zugeordnete Konten)",
    dependencies=[Depends(strict_query)],
)
async def list_account_options(
    property_id: uuid.UUID,
    request: Request,
    legal_entity_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=100),
    principal: TenantPrincipal = Depends(READ),
) -> list[BankAccountListOut]:
    """Bankkontenauswahl on the property page. Balance and latest transactions are only
    included for principals with accounting:read; the assignment itself is organisation."""
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        items = await account_selection.list_accounts(
            session,
            property_id=property_id,
            legal_entity_id=legal_entity_id,
            q=q,
            with_money=principal.has("accounting:read"),
        )
        return [account_list_out(i) for i in items]


# Contacts, meters, providers, maintenance -----------------------------------------------


@router.get(
    "/properties/{property_id}/contacts",
    summary="Ansprechpartner",
    dependencies=[Depends(strict_query)],
)
async def list_property_contacts(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.PropertyContactOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.execute(
                select(PropertyContact, Contact.display_name)
                .join(Contact, Contact.id == PropertyContact.contact_id)
                .where(PropertyContact.property_id == property_id)
                .order_by(PropertyContact.category_code, PropertyContact.valid_from)
            )
        ).all()
        return [
            s.PropertyContactOut.model_validate(c).model_copy(update={"contact_name": name})
            for c, name in rows
        ]


@router.post(
    "/properties/{property_id}/contacts", status_code=201, summary="Ansprechpartner zuordnen"
)
async def add_property_contact(
    property_id: uuid.UUID,
    body: s.PropertyContactIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PropertyContactOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        contact = await _get(session, Contact, body.contact_id)
        await svc.check_catalog(session, "property_contact_category", body.category_code)
        row = PropertyContact(
            tenant_id=principal.tenant_id, property_id=property_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.contact_added",
            entity_type="property",
            entity_id=property_id,
            actor_user_id=principal.user_id,
            payload={"contact_id": str(body.contact_id), "category": body.category_code},
        )
        return s.PropertyContactOut.model_validate(row).model_copy(
            update={"contact_name": contact.display_name}
        )


@router.get(
    "/properties/{property_id}/meters", summary="Zähler", dependencies=[Depends(strict_query)]
)
async def list_meters(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.MeterOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(Meter).where(Meter.property_id == property_id).order_by(Meter.number)
            )
        ).all()
        return [s.MeterOut.model_validate(m) for m in rows]


@router.post("/properties/{property_id}/meters", status_code=201, summary="Zähler anlegen")
async def add_meter(
    property_id: uuid.UUID,
    body: s.MeterIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.MeterOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        if body.unit_id and (await _get(session, Unit, body.unit_id)).property_id != property_id:
            raise svc.invalid("Die Einheit gehört nicht zu diesem Objekt.")
        await svc.check_catalog(session, "meter_type", body.meter_type_code)
        meter = Meter(tenant_id=principal.tenant_id, property_id=property_id, **body.model_dump())
        session.add(meter)
        await session.flush()
        return s.MeterOut.model_validate(meter)


@router.get(
    "/meters/{meter_id}/readings", summary="Zählerstände", dependencies=[Depends(strict_query)]
)
async def list_readings(
    meter_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.ReadingOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(MeterReading)
                .where(MeterReading.meter_id == meter_id)
                .order_by(MeterReading.read_at)
            )
        ).all()
        return [s.ReadingOut.model_validate(r) for r in rows]


@router.post("/meters/{meter_id}/readings", status_code=201, summary="Zählerstand erfassen")
async def add_reading(
    meter_id: uuid.UUID,
    body: s.ReadingIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.ReadingOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Meter, meter_id)
        if body.photo_document_id is not None:
            await svc.check_documents_exist(session, [body.photo_document_id], "Zählerfoto")
        implausible = await svc.reading_is_implausible(session, meter_id, body.read_at, body.value)
        reading = MeterReading(
            tenant_id=principal.tenant_id, meter_id=meter_id, **body.model_dump()
        )
        session.add(reading)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meter_reading.created",
            entity_type="meter",
            entity_id=meter_id,
            actor_user_id=principal.user_id,
            payload={"read_at": body.read_at.isoformat(), "implausible": implausible},
        )
        return s.ReadingOut.model_validate(reading).model_copy(update={"implausible": implausible})


@router.get(
    "/properties/{property_id}/service-providers",
    summary="Dienstleisterverhältnisse",
    dependencies=[Depends(strict_query)],
)
async def list_providers(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.ProviderOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(ServiceProviderRelation).where(
                    ServiceProviderRelation.property_id == property_id
                )
            )
        ).all()
        return [s.ProviderOut.model_validate(r) for r in rows]


@router.post(
    "/properties/{property_id}/service-providers",
    status_code=201,
    summary="Dienstleisterverhältnis anlegen",
)
async def add_provider(
    property_id: uuid.UUID,
    body: s.ProviderIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.ProviderOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        await _get(session, Contact, body.contact_id)
        await svc.check_catalog(session, "provider_contract_type", body.contract_type_code)
        provider_fields = await svc.check_custom_fields(
            session,
            "service_provider_relation",
            body.custom_fields,
            management_type=prop.management_type,
            create=True,
        )
        if body.contact_bank_account_id:
            account = await _get(session, ContactBankAccount, body.contact_bank_account_id)
            if account.contact_id != body.contact_id:
                raise svc.invalid("Die Bankverbindung gehört nicht zum Dienstleister.")
        await svc.check_ledger_account(
            session, body.creditor_account_id, property_id, "Das Kreditorenkonto"
        )
        await svc.check_documents_exist(session, body.documents, "Dokumente")
        row = ServiceProviderRelation(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            **(body.model_dump() | {"custom_fields": provider_fields}),
        )
        session.add(row)
        await session.flush()
        # 7.2 / M10-05: creditor account 07xxxx per provider relation in every ledger of the
        # property; account master data only, no posting.
        from mhvp.accounting.ledger_ops import ensure_creditor_for_relation

        await ensure_creditor_for_relation(session, row)
        # GA02-05: default bank rule as proposal (state proposed, no posting, G1 locked).
        from mhvp.accounting.provider_rule import propose_default_rule

        await propose_default_rule(session, row)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="service_provider_relation.created",
            entity_type="service_provider_relation",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"contract_type": body.contract_type_code},
        )
        return s.ProviderOut.model_validate(row)


@router.get(
    "/properties/{property_id}/maintenance",
    summary="Wartung und Prüfpflichten",
    dependencies=[Depends(strict_query)],
)
async def list_maintenance(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.MaintenanceOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(MaintenanceItem)
                .where(MaintenanceItem.property_id == property_id)
                .order_by(MaintenanceItem.due_date)
            )
        ).all()
        return [maintenance_out(m) for m in rows]


@router.post("/properties/{property_id}/maintenance", status_code=201, summary="Wartung anlegen")
async def add_maintenance(
    property_id: uuid.UUID,
    body: s.MaintenanceIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.MaintenanceOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        await svc.check_documents_exist(session, body.documents, "Dokumente")
        row = MaintenanceItem(
            tenant_id=principal.tenant_id, property_id=property_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return maintenance_out(row)


def maintenance_out(item: MaintenanceItem) -> s.MaintenanceOut:
    """Maintenance row with the last completion as a Berlin calendar day (C2)."""
    out = s.MaintenanceOut.model_validate(item)
    return out.model_copy(update={"last_done_on": svc.last_done_on(item.done_at)})


# P1 additions (Ergänzung CRM 4.2 to 4.4): billing periods, sub communities, Objektmappe,
# vacancy key values, meter changes ---------------------------------------------------------


async def _emit_simple(
    session: Any,
    principal: TenantPrincipal,
    type_: str,
    entity_type: str,
    entity_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type=type_,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=principal.user_id,
        payload=payload,
    )


@router.get(
    "/properties/{property_id}/billing-periods",
    summary="Abrechnungszeiträume",
    dependencies=[Depends(strict_query)],
)
async def list_billing_periods(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.BillingPeriodOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(PropertyBillingPeriod)
                .where(PropertyBillingPeriod.property_id == property_id)
                .order_by(PropertyBillingPeriod.kind, PropertyBillingPeriod.valid_from)
            )
        ).all()
        return [s.BillingPeriodOut.model_validate(r) for r in rows]


@router.post(
    "/properties/{property_id}/billing-periods",
    status_code=201,
    summary="Abrechnungszeitraum je Abrechnungsart anlegen",
)
async def add_billing_period(
    property_id: uuid.UUID,
    body: s.BillingPeriodIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.BillingPeriodOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        row = PropertyBillingPeriod(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await _unique(
            session,
            f"Der Abrechnungszeitraum {body.kind.value} überschneidet sich mit einem bestehenden.",
        )
        await _emit_simple(
            session,
            principal,
            "property.billing_period_added",
            "property",
            property_id,
            {"kind": body.kind.value, "valid_from": body.valid_from.isoformat()},
        )
        return s.BillingPeriodOut.model_validate(row)


@router.delete(
    "/properties/{property_id}/billing-periods/{period_id}",
    status_code=204,
    summary="Abrechnungszeitraum löschen",
)
async def delete_billing_period(
    property_id: uuid.UUID,
    period_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, PropertyBillingPeriod, period_id)
        if row.property_id != property_id:
            raise _nf()
        if row.status == "closed":  # GA02-01: closed periods are locked
            raise ProblemError(ErrorCodes.PROPERTY_BILLING_PERIOD_CLOSED)
        await session.delete(row)
        await _emit_simple(
            session,
            principal,
            "property.billing_period_removed",
            "property",
            property_id,
            {"kind": row.kind.value, "valid_from": row.valid_from.isoformat()},
        )
        return Response(status_code=204)


@router.get(
    "/properties/{property_id}/sub-communities",
    summary="Untergemeinschaften",
    dependencies=[Depends(strict_query)],
)
async def list_sub_communities(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.SubCommunityOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(SubCommunity)
                .where(SubCommunity.property_id == property_id)
                .order_by(SubCommunity.code)
            )
        ).all()
        return [s.SubCommunityOut.model_validate(r) for r in rows]


@router.post(
    "/properties/{property_id}/sub-communities",
    status_code=201,
    summary="Untergemeinschaft anlegen (Mehrhausanlage)",
)
async def add_sub_community(
    property_id: uuid.UUID,
    body: s.SubCommunityIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.SubCommunityOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        if prop.management_type is ManagementType.RENTAL:
            raise svc.invalid("Untergemeinschaften gibt es nur bei WEG-Verwaltung.")
        row = SubCommunity(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await _unique(session, f"Untergemeinschaft {body.code} ist bereits vergeben.")
        await _emit_simple(
            session,
            principal,
            "sub_community.created",
            "sub_community",
            row.id,
            {"property_id": str(property_id), "code": body.code},
        )
        return s.SubCommunityOut.model_validate(row)


@router.put(
    "/properties/{property_id}/sub-communities/{sub_community_id}",
    summary="Untergemeinschaft ändern",
)
async def update_sub_community(
    property_id: uuid.UUID,
    sub_community_id: uuid.UUID,
    body: s.SubCommunityIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.SubCommunityOut:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, SubCommunity, sub_community_id)
        if row.property_id != property_id:
            raise _nf()
        before = s.SubCommunityIn.model_validate(row, from_attributes=True).model_dump(mode="json")
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await _unique(session, f"Untergemeinschaft {body.code} ist bereits vergeben.")
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="sub_community.updated",
            entity_type="sub_community",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            changes=diff(before, body.model_dump(mode="json")),
        )
        return s.SubCommunityOut.model_validate(row)


@router.delete(
    "/properties/{property_id}/sub-communities/{sub_community_id}",
    status_code=204,
    summary="Untergemeinschaft löschen (Einheiten werden gelöst)",
)
async def delete_sub_community(
    property_id: uuid.UUID,
    sub_community_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, SubCommunity, sub_community_id)
        if row.property_id != property_id:
            raise _nf()
        units = (await session.scalars(select(Unit).where(Unit.sub_community_id == row.id))).all()
        for unit in units:
            unit.sub_community_id = None
        await session.delete(row)
        await _emit_simple(
            session,
            principal,
            "sub_community.deleted",
            "sub_community",
            row.id,
            {"property_id": str(property_id), "code": row.code, "units_detached": len(units)},
        )
        return Response(status_code=204)


@router.get(
    "/properties/{property_id}/portal-documents",
    summary="Objektmappe",
    dependencies=[Depends(strict_query)],
)
async def list_portal_documents(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.PortalDocumentOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(PropertyPortalDocument)
                .where(PropertyPortalDocument.property_id == property_id)
                .order_by(PropertyPortalDocument.sort_order, PropertyPortalDocument.created_at)
            )
        ).all()
        return [s.PortalDocumentOut.model_validate(r) for r in rows]


@router.post(
    "/properties/{property_id}/portal-documents",
    status_code=201,
    summary="Dokument in die Objektmappe aufnehmen",
)
async def add_portal_document(
    property_id: uuid.UUID,
    body: s.PortalDocumentIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PortalDocumentOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        await _get(session, Document, body.document_id)
        row = PropertyPortalDocument(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        await _unique(session, "Das Dokument ist bereits in der Objektmappe.")
        await _emit_simple(
            session,
            principal,
            "property.portal_document_added",
            "property",
            property_id,
            {"document_id": str(body.document_id), "visible_for": body.visible_for},
        )
        return s.PortalDocumentOut.model_validate(row)


@router.delete(
    "/properties/{property_id}/portal-documents/{entry_id}",
    status_code=204,
    summary="Dokument aus der Objektmappe entfernen (Dokument bleibt erhalten)",
)
async def delete_portal_document(
    property_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> Response:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, PropertyPortalDocument, entry_id)
        if row.property_id != property_id:
            raise _nf()
        await session.delete(row)
        await _emit_simple(
            session,
            principal,
            "property.portal_document_removed",
            "property",
            property_id,
            {"document_id": str(row.document_id)},
        )
        return Response(status_code=204)


def _vacancy_value_out(
    v: UnitVacancyAllocationValue, key: AllocationKey | None
) -> s.VacancyAllocationValueOut:
    return s.VacancyAllocationValueOut(
        id=v.id,
        unit_id=v.unit_id,
        allocation_key_id=v.allocation_key_id,
        key_code=key.code if key else None,
        key_name=key.name if key else None,
        value=v.value,
        valid_from=v.valid_from,
        valid_to=v.valid_to,
    )


@router.get(
    "/units/{unit_id}/vacancy-allocation-values",
    summary="Umlagewerte für Leerstandszeiten, Historie oder Stichtag",
    dependencies=[Depends(strict_query)],
)
async def list_vacancy_values(
    unit_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.VacancyAllocationValueOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Unit, unit_id)
        query = (
            select(UnitVacancyAllocationValue, AllocationKey)
            .join(AllocationKey, AllocationKey.id == UnitVacancyAllocationValue.allocation_key_id)
            .where(UnitVacancyAllocationValue.unit_id == unit_id)
            .order_by(AllocationKey.sort_order, UnitVacancyAllocationValue.valid_from)
        )
        if as_of is not None:
            query = query.where(svc.valid_at(UnitVacancyAllocationValue, as_of))
        rows = (await session.execute(query)).all()
        return [_vacancy_value_out(v, k) for v, k in rows]


@router.post(
    "/units/{unit_id}/vacancy-allocation-values",
    status_code=201,
    summary="Umlagewert für Leerstandszeiten erfassen (Vorwert wird beendet)",
)
async def add_vacancy_value(
    unit_id: uuid.UUID,
    body: s.VacancyAllocationValueIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.VacancyAllocationValueOut:
    async with tenant_tx(request, principal) as session:
        unit = await _get(session, Unit, unit_id)
        key = await _get(session, AllocationKey, body.allocation_key_id)
        if key.property_id != unit.property_id:
            raise svc.invalid("Der Umlageschlüssel gehört nicht zum Objekt der Einheit.")
        try:
            row = await svc.add_vacancy_allocation_value(
                session,
                principal.tenant_id,
                unit_id,
                key.id,
                body.value,
                body.valid_from,
                body.valid_to,
            )
        except IntegrityError:
            raise ProblemError(
                ErrorCodes.CONFLICT, detail="Der Zeitraum überschneidet sich mit einem Vorwert."
            ) from None
        await _emit_simple(
            session,
            principal,
            "unit.vacancy_allocation_value_added",
            "unit",
            unit_id,
            {"key": key.code, "value": str(body.value), "valid_from": body.valid_from.isoformat()},
        )
        return _vacancy_value_out(row, key)


@router.get(
    "/meters/{meter_id}/changes", summary="Zählerwechsel", dependencies=[Depends(strict_query)]
)
async def list_meter_changes(
    meter_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.MeterChangeOut]:
    async with tenant_tx(request, principal) as session:
        await _get(session, Meter, meter_id)
        rows = (
            await session.scalars(
                select(MeterChange)
                .where(MeterChange.meter_id == meter_id)
                .order_by(MeterChange.changed_on, MeterChange.created_at)
            )
        ).all()
        return [s.MeterChangeOut.model_validate(r) for r in rows]


@router.post(
    "/meters/{meter_id}/changes",
    status_code=201,
    summary="Zählerwechsel erfassen (Endstand alt, Anfangsstand neu)",
)
async def add_meter_change(
    meter_id: uuid.UUID,
    body: s.MeterChangeIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.MeterChangeOut:
    """Records the change; the meter row keeps its id (readings before the change belong to
    the old device, identified by ``old_number``). No reading rows are written: consumption
    across a change is computed from the change record by the statement modules."""
    async with tenant_tx(request, principal) as session:
        meter = await _get(session, Meter, meter_id)
        if body.changed_on < meter.valid_from:
            raise svc.invalid("Der Wechsel liegt vor dem Beginn des Zählers.")
        row = MeterChange(
            tenant_id=principal.tenant_id,
            meter_id=meter_id,
            old_number=meter.number,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(row)
        if body.new_number and body.new_number != meter.number:
            meter.number = body.new_number
            meter.updated_by = principal.user_id
        await session.flush()
        await _emit_simple(
            session,
            principal,
            "meter.changed",
            "meter",
            meter_id,
            {
                "changed_on": body.changed_on.isoformat(),
                "old_number": row.old_number,
                "new_number": body.new_number,
                "old_final_value": str(body.old_final_value),
                "new_initial_value": str(body.new_initial_value),
            },
        )
        return s.MeterChangeOut.model_validate(row)


# Templates (catalogues and custom fields: routers_catalogs.py) ----------------------------


@router.get(
    "/allocation-key-templates",
    summary="Muster Umlageschlüssel",
    dependencies=[Depends(strict_query)],
)
async def list_templates(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.AllocationKeyIn]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(AllocationKeyTemplate).order_by(AllocationKeyTemplate.sort_order)
            )
        ).all()
        return [
            s.AllocationKeyIn(
                code=t.code,
                name=t.name,
                unit_of_measure=t.unit_of_measure,
                kind=t.kind,
                meter_type_code=t.meter_type_code,
                sort_order=t.sort_order,
            )
            for t in rows
        ]
