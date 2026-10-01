"""Partial updates of property, building and unit master data (Ergänzung CRM, AP8).

``PATCH`` carries only the fields the client changed (inline editing, autosave per field).
The server merges them into the current state, validates the result with the same schema as
the corresponding ``PUT`` route, checks ``If-Match`` against ``version`` (412 on a stale
version, ADR 0012) and writes the audit diff exactly like ``PUT``. Permissions equal the
``PUT`` routes (``properties:update``). Financial fields are not part of these schemas.
"""

import uuid
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, ValidationError, create_model

from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.auth.scope import property_path_guard
from mhvp.core.events import diff, emit
from mhvp.core.problems import body_validation_error
from mhvp.properties import schemas as s
from mhvp.properties import services as svc
from mhvp.properties.models import Building, Property, Unit
from mhvp.properties.routers import UPDATE, _check_version, _get, _property_out, _unique, _unit_out

# M2-02/S16-02: path ids outside the property assignment answer 404.
router = APIRouter(tags=["Objekte"], dependencies=[Depends(property_path_guard)])


def _partial(name: str, base: type[BaseModel]) -> type[BaseModel]:
    """Copy of ``base`` with every field optional (default ``None``); the merged result is
    validated against ``base`` again, so the field rules of ``base`` still apply."""
    fields: dict[str, Any] = {
        key: (Optional[field.annotation], None)  # noqa: UP045 - runtime union of a dynamic type
        for key, field in base.model_fields.items()
    }
    return create_model(name, __base__=s._In, **fields)


PropertyPatch = _partial("PropertyPatch", s.PropertyIn)
BuildingPatch = _partial("BuildingPatch", s.BuildingIn)
UnitPatch = _partial("UnitPatch", s.UnitIn)


def _merge(base: type[BaseModel], row: Any, patch: BaseModel) -> Any:
    current = base.model_validate(row, from_attributes=True).model_dump()
    try:
        return base.model_validate(current | patch.model_dump(exclude_unset=True))
    except ValidationError as exc:
        raise body_validation_error(exc) from None


def _changed(patch: BaseModel) -> list[str]:
    return sorted(patch.model_dump(exclude_unset=True))


@router.patch("/properties/{property_id}", summary="Objekt teilweise ändern (If-Match)")
async def patch_property(
    property_id: uuid.UUID,
    body: PropertyPatch,  # type: ignore[valid-type]
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PropertyOut:
    async with tenant_tx(request, principal) as session:
        prop = await _get(session, Property, property_id)
        _check_version(if_match, prop.version)
        merged: s.PropertyIn = _merge(s.PropertyIn, prop, body)
        if (merged.postal_code, merged.country) != (prop.postal_code, prop.country):
            svc.check_postcode(merged.country, merged.postal_code)
        if merged.management_type != prop.management_type:
            raise svc.invalid(
                "Die Verwaltungsart kann nach Anlage nicht geändert werden (Rechtsträger, 6.9.1)."
            )
        await svc.check_custom_fields(
            session,
            "property",
            merged.custom_fields,
            management_type=prop.management_type,
            entity_id=prop.id,
        )
        await svc.check_documents_exist(session, merged.images, "Bilder")
        before = s.PropertyIn.model_validate(prop, from_attributes=True).model_dump(mode="json")
        for key, value in merged.model_dump().items():
            setattr(prop, key, value)
        prop.version += 1
        prop.updated_by = principal.user_id
        await _unique(session, f"Objektnummer {merged.number} ist bereits vergeben.")
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.updated",
            entity_type="property",
            entity_id=prop.id,
            actor_user_id=principal.user_id,
            payload={"fields": _changed(body)},
            changes=diff(before, merged.model_dump(mode="json")),
        )
        out = await _property_out(session, prop)
        response.headers["ETag"] = f'"{out.version}"'
        return out


@router.patch("/buildings/{building_id}", summary="Gebäude teilweise ändern (If-Match)")
async def patch_building(
    building_id: uuid.UUID,
    body: BuildingPatch,  # type: ignore[valid-type]
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.BuildingOut:
    async with tenant_tx(request, principal) as session:
        building = await _get(session, Building, building_id)
        _check_version(if_match, building.version)
        merged: s.BuildingIn = _merge(s.BuildingIn, building, body)
        prop = await _get(session, Property, building.property_id)
        await svc.check_custom_fields(
            session,
            "building",
            merged.custom_fields,
            management_type=prop.management_type,
            entity_id=building.id,
        )
        before = s.BuildingIn.model_validate(building, from_attributes=True).model_dump(mode="json")
        for key, value in merged.model_dump().items():
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
            payload={"fields": _changed(body)},
            changes=diff(before, merged.model_dump(mode="json")),
        )
        await session.refresh(building)
        response.headers["ETag"] = f'"{building.version}"'
        return s.BuildingOut.model_validate(building)


@router.patch("/units/{unit_id}", summary="Einheit teilweise ändern (If-Match)")
async def patch_unit(
    unit_id: uuid.UUID,
    body: UnitPatch,  # type: ignore[valid-type]
    request: Request,
    response: Response,
    if_match: Annotated[str | None, Header()] = None,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.UnitOut:
    async with tenant_tx(request, principal) as session:
        unit = await _get(session, Unit, unit_id)
        _check_version(if_match, unit.version)
        merged: s.UnitIn = _merge(s.UnitIn, unit, body)
        building = await _get(session, Building, merged.building_id)
        if building.property_id != unit.property_id:
            raise svc.invalid("Das Gebäude gehört nicht zu diesem Objekt.")
        await svc.check_sub_community(session, merged.sub_community_id, unit.property_id)
        prop = await _get(session, Property, unit.property_id)
        await svc.check_custom_fields(
            session,
            "unit",
            merged.custom_fields,
            management_type=prop.management_type,
            entity_id=unit.id,
        )
        before = s.UnitIn.model_validate(unit, from_attributes=True).model_dump(mode="json")
        for key, value in merged.model_dump().items():
            setattr(unit, key, value)
        unit.version += 1
        unit.updated_by = principal.user_id
        await _unique(
            session, f"Einheitennummer {merged.number} ist in diesem Objekt bereits vergeben."
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="unit.updated",
            entity_type="unit",
            entity_id=unit.id,
            actor_user_id=principal.user_id,
            payload={"fields": _changed(body)},
            changes=diff(before, merged.model_dump(mode="json")),
        )
        out = await _unit_out(session, unit, None)
        response.headers["ETag"] = f'"{unit.version}"'
        return out
