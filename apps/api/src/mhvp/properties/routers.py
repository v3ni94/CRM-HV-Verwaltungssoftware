"""Property endpoints (/api/v1/properties, units, buildings, meters, catalogues)."""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from mhvp.banking import account_selection
from mhvp.banking.routers import BankAccountListOut, account_list_out
from mhvp.contacts.models import Contact, ContactBankAccount, Party
from mhvp.contacts.services import recompute_for_party
from mhvp.contacts.validation import mask_iban
from mhvp.core import crypto
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import diff, emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.properties import schemas as s
from mhvp.properties import services as svc
from mhvp.properties.models import (
    AllocationKey,
    AllocationKeyTemplate,
    BankAccountKind,
    Building,
    CatalogEntry,
    CustomFieldDefinition,
    LegalEntity,
    MaintenanceItem,
    ManagementType,
    Meter,
    MeterReading,
    Property,
    PropertyBankAccount,
    PropertyContact,
    PropertyOwner,
    PropertyStatus,
    ServiceProviderRelation,
    Unit,
    UnitAllocationValue,
    UnitVatOption,
)

router = APIRouter(tags=["Objekte"])
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=200)]
READ = require_permission("properties:read")
CREATE = require_permission("properties:create")
UPDATE = require_permission("properties:update")


def _nf() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


async def _get(session: Any, model: Any, entity_id: uuid.UUID) -> Any:
    row = await session.get(model, entity_id)
    if row is None:
        raise _nf()
    return row


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


@router.get("/properties", summary="Objekte")
async def list_properties(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    status: PropertyStatus | None = None,
    management_type: ManagementType | None = None,
    sev_only: bool = Query(
        default=False,
        description="Nur WEG-Objekte mit SEV, für die Mietverträge hinterlegt sind",
    ),
    page: Page = 1,
    page_size: PageSize = 50,
    principal: TenantPrincipal = Depends(READ),
) -> s.PropertyPage:
    from mhvp.contracts.models import Contract

    async with tenant_tx(request, principal) as session:
        query = select(Property)
        if status:
            query = query.where(Property.status == status)
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
                query.order_by(Property.number).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return s.PropertyPage(
            items=[s.PropertySummary.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.post("/properties", status_code=201, summary="Objekt anlegen")
async def create_property(
    body: s.PropertyIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> s.PropertyOut:
    async with tenant_tx(request, principal) as session:
        await svc.check_catalog(session, "property_type", body.property_type_code)
        await svc.check_custom_fields(session, "property", body.custom_fields)
        prop = Property(
            tenant_id=principal.tenant_id, created_by=principal.user_id, **body.model_dump()
        )
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
        if if_match is not None and if_match.strip('"') != str(prop.version):
            raise ProblemError(ErrorCodes.VERSION_CONFLICT)
        if body.management_type != prop.management_type:
            raise svc.invalid(
                "Die Verwaltungsart kann nach Anlage nicht geändert werden (Rechtsträger, 6.9.1)."
            )
        await svc.check_custom_fields(session, "property", body.custom_fields)
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


@router.get("/properties/{property_id}/buildings", summary="Gebäude")
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
        await _get(session, Property, property_id)
        await svc.check_custom_fields(session, "building", body.custom_fields)
        building = Building(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            created_by=principal.user_id,
            **body.model_dump(),
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
        select(UnitAllocationValue, AllocationKey.code)
        .join(AllocationKey, AllocationKey.id == UnitAllocationValue.allocation_key_id)
        .where(UnitAllocationValue.unit_id.in_(ids))
    )
    vat = select(UnitVatOption).where(UnitVatOption.unit_id.in_(ids))
    if as_of is not None:
        query = query.where(svc.valid_at(UnitAllocationValue, as_of))
        vat = vat.where(svc.valid_at(UnitVatOption, as_of))
    values: dict[uuid.UUID, list[s.AllocationValueOut]] = {}
    for v, code in (
        await session.execute(
            query.order_by(AllocationKey.sort_order, UnitAllocationValue.valid_from)
        )
    ).all():
        values.setdefault(v.unit_id, []).append(
            s.AllocationValueOut.model_validate(v).model_copy(update={"key_code": code})
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


@router.get("/properties/{property_id}/units", summary="Einheiten, optional zum Stichtag")
async def list_units(
    property_id: uuid.UUID,
    request: Request,
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> list[s.UnitOut]:
    async with tenant_tx(request, principal) as session:
        units = (
            await session.scalars(
                select(Unit).where(Unit.property_id == property_id).order_by(Unit.number)
            )
        ).all()
        return await _units_out(session, units, as_of)


@router.post("/properties/{property_id}/units", status_code=201, summary="Einheit anlegen")
async def create_unit(
    property_id: uuid.UUID,
    body: s.UnitIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.UnitOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        building = await _get(session, Building, body.building_id)
        if building.property_id != property_id:
            raise svc.invalid("Das Gebäude gehört nicht zu diesem Objekt.")
        await svc.check_custom_fields(session, "unit", body.custom_fields)
        unit = Unit(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            created_by=principal.user_id,
            **body.model_dump(),
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
    as_of: date | None = None,
    principal: TenantPrincipal = Depends(READ),
) -> s.UnitOut:
    async with tenant_tx(request, principal) as session:
        return await _unit_out(session, await _get(session, Unit, unit_id), as_of)


@router.put("/units/{unit_id}", summary="Einheit ändern")
async def update_unit(
    unit_id: uuid.UUID,
    body: s.UnitIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.UnitOut:
    async with tenant_tx(request, principal) as session:
        unit = await _get(session, Unit, unit_id)
        building = await _get(session, Building, body.building_id)
        if building.property_id != unit.property_id:
            raise svc.invalid("Das Gebäude gehört nicht zu diesem Objekt.")
        await svc.check_custom_fields(session, "unit", body.custom_fields)
        before = s.UnitIn.model_validate(unit, from_attributes=True).model_dump(mode="json")
        for key, value in body.model_dump().items():
            setattr(unit, key, value)
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


@router.get("/properties/{property_id}/allocation-keys", summary="Umlageschlüssel")
async def list_keys(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.AllocationKeyOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(AllocationKey)
                .where(AllocationKey.property_id == property_id)
                .order_by(AllocationKey.sort_order)
            )
        ).all()
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


@router.get("/units/{unit_id}/allocation-values", summary="Schlüsselwerte, Historie oder Stichtag")
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


@router.get("/properties/{property_id}/legal-entities", summary="Rechtsträger des Objekts")
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
    )


@router.get("/properties/{property_id}/bank-accounts", summary="Bankkonten")
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
        account = PropertyBankAccount(
            tenant_id=principal.tenant_id,
            property_id=property_id,
            iban_suffix=body.iban[-4:],
            iban_fingerprint=crypto.fingerprint(body.iban),
            segregated=body.kind is BankAccountKind.DEPOSIT,
            created_by=principal.user_id,
            **body.model_dump(),
        )
        session.add(account)
        await session.flush()
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


@router.get(
    "/properties/{property_id}/bank-account-options",
    summary="Auswählbare Bankkonten des Objekts (Stammkonten und zugeordnete Konten)",
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


@router.get("/properties/{property_id}/contacts", summary="Ansprechpartner")
async def list_property_contacts(
    property_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.PropertyContactOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(PropertyContact).where(PropertyContact.property_id == property_id)
            )
        ).all()
        return [s.PropertyContactOut.model_validate(c) for c in rows]


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
        await _get(session, Contact, body.contact_id)
        await svc.check_catalog(session, "property_contact_category", body.category_code)
        row = PropertyContact(
            tenant_id=principal.tenant_id, property_id=property_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        return s.PropertyContactOut.model_validate(row)


@router.get("/properties/{property_id}/meters", summary="Zähler")
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


@router.get("/meters/{meter_id}/readings", summary="Zählerstände")
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


@router.get("/properties/{property_id}/service-providers", summary="Dienstleisterverhältnisse")
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
        await _get(session, Property, property_id)
        await _get(session, Contact, body.contact_id)
        await svc.check_catalog(session, "provider_contract_type", body.contract_type_code)
        await svc.check_custom_fields(session, "service_provider_relation", body.custom_fields)
        if body.contact_bank_account_id:
            account = await _get(session, ContactBankAccount, body.contact_bank_account_id)
            if account.contact_id != body.contact_id:
                raise svc.invalid("Die Bankverbindung gehört nicht zum Dienstleister.")
        row = ServiceProviderRelation(
            tenant_id=principal.tenant_id, property_id=property_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
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


@router.get("/properties/{property_id}/maintenance", summary="Wartung und Prüfpflichten")
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
        return [s.MaintenanceOut.model_validate(m) for m in rows]


@router.post("/properties/{property_id}/maintenance", status_code=201, summary="Wartung anlegen")
async def add_maintenance(
    property_id: uuid.UUID,
    body: s.MaintenanceIn,
    request: Request,
    principal: TenantPrincipal = Depends(CREATE),
) -> s.MaintenanceOut:
    async with tenant_tx(request, principal) as session:
        await _get(session, Property, property_id)
        row = MaintenanceItem(
            tenant_id=principal.tenant_id, property_id=property_id, **body.model_dump()
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return s.MaintenanceOut.model_validate(row)


# Catalogues, templates, custom fields ---------------------------------------------------


@router.get("/catalogs/{catalog}", summary="Katalog")
async def list_catalog(
    catalog: str, request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.CatalogEntryOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(CatalogEntry)
                .where(CatalogEntry.catalog == catalog)
                .order_by(CatalogEntry.sort_order)
            )
        ).all()
        return [s.CatalogEntryOut.model_validate(c) for c in rows]


@router.post("/catalogs/{catalog}", status_code=201, summary="Katalogeintrag anlegen")
async def add_catalog_entry(
    catalog: str,
    body: s.CatalogEntryIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> s.CatalogEntryOut:
    async with tenant_tx(request, principal) as session:
        row = CatalogEntry(tenant_id=principal.tenant_id, catalog=catalog, **body.model_dump())
        session.add(row)
        await _unique(session, f"Eintrag {body.code} existiert bereits.")
        await session.refresh(row)
        return s.CatalogEntryOut.model_validate(row)


@router.get("/allocation-key-templates", summary="Muster Umlageschlüssel")
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


@router.get("/custom-fields", summary="Zusatzfelder")
async def list_custom_fields(
    request: Request, principal: TenantPrincipal = Depends(READ)
) -> list[s.CustomFieldOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(CustomFieldDefinition).order_by(
                    CustomFieldDefinition.entity_type, CustomFieldDefinition.key
                )
            )
        ).all()
        return [s.CustomFieldOut.model_validate(c) for c in rows]


@router.post("/custom-fields", status_code=201, summary="Zusatzfeld definieren")
async def add_custom_field(
    body: s.CustomFieldIn,
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:update")),
) -> s.CustomFieldOut:
    async with tenant_tx(request, principal) as session:
        row = CustomFieldDefinition(tenant_id=principal.tenant_id, **body.model_dump())
        session.add(row)
        await _unique(session, f"Zusatzfeld {body.key} existiert bereits.")
        await session.refresh(row)
        return s.CustomFieldOut.model_validate(row)
