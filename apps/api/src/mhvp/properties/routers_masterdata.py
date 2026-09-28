"""Master data maintained in the CRM (package C2, 28.09.2026): contact persons, meters and
maintenance items of a property get partial updates and a completion action, so the property
page can maintain them without import or raw API calls (docs/handbuch/anleitung-stammdaten.md).

Permissions equal the existing write routes (``properties:update``). Meter numbers are not
patched here: a replaced device is a Zählerwechsel (``POST /meters/{id}/changes``). Custom
field values of a property are written with ``PATCH /properties/{id}`` (routers_patch.py),
their definitions with ``/custom-fields`` (routers_catalogs.py); nothing is duplicated here.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import select

from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, tenant_tx
from mhvp.core.events import diff, emit
from mhvp.core.problems import ErrorCodes, ProblemError, body_validation_error
from mhvp.properties import schemas as s
from mhvp.properties import services as svc
from mhvp.properties.models import (
    MaintenanceItem,
    Meter,
    PropertyContact,
    ServiceProviderRelation,
    Unit,
)
from mhvp.properties.routers import UPDATE, _get, _nf, maintenance_out

router = APIRouter(tags=["Objekte"])


async def contact_out(session: Any, row: PropertyContact) -> s.PropertyContactOut:
    name = await session.scalar(select(Contact.display_name).where(Contact.id == row.contact_id))
    return s.PropertyContactOut.model_validate(row).model_copy(update={"contact_name": name})


async def _unit_of_property(
    session: Any, unit_id: uuid.UUID | None, property_id: uuid.UUID
) -> None:
    if unit_id is not None and (await _get(session, Unit, unit_id)).property_id != property_id:
        raise svc.invalid("Die Einheit gehört nicht zu diesem Objekt.")


def _merge(base: type[Any], row: Any, patch: Any) -> Any:
    """Current values of ``row`` overlaid with the set fields of ``patch`` and validated with
    the full input schema again, so its field rules (period order, patterns) still apply."""
    current = base.model_validate(row, from_attributes=True).model_dump()
    try:
        return base.model_validate(current | patch.model_dump(exclude_unset=True))
    except ValidationError as exc:
        raise body_validation_error(exc) from None


# Contact persons ----------------------------------------------------------------------------


@router.patch(
    "/properties/{property_id}/contacts/{assignment_id}",
    summary="Ansprechpartner ändern (Kategorie, Zeitraum, Portalsichtbarkeit)",
)
async def patch_property_contact(
    property_id: uuid.UUID,
    assignment_id: uuid.UUID,
    body: s.PropertyContactPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.PropertyContactOut:
    async with tenant_tx(request, principal) as session:
        row = await _get(session, PropertyContact, assignment_id)
        if row.property_id != property_id:
            raise _nf()
        merged: s.PropertyContactIn = _merge(s.PropertyContactIn, row, body)
        if merged.category_code != row.category_code:
            await svc.check_catalog(session, "property_contact_category", merged.category_code)
        before = s.PropertyContactIn.model_validate(row, from_attributes=True).model_dump(
            mode="json"
        )
        for key, value in merged.model_dump().items():
            setattr(row, key, value)
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="property.contact_updated",
            entity_type="property",
            entity_id=property_id,
            actor_user_id=principal.user_id,
            payload={"assignment_id": str(assignment_id)},
            changes=diff(before, merged.model_dump(mode="json")),
        )
        return await contact_out(session, row)


# Meters -------------------------------------------------------------------------------------


@router.patch("/meters/{meter_id}", summary="Zähler ändern (ohne Nummer, siehe Zählerwechsel)")
async def patch_meter(
    meter_id: uuid.UUID,
    body: s.MeterPatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.MeterOut:
    async with tenant_tx(request, principal) as session:
        meter = await _get(session, Meter, meter_id)
        merged: s.MeterIn = _merge(s.MeterIn, meter, body)
        await _unit_of_property(session, merged.unit_id, meter.property_id)
        if merged.meter_type_code != meter.meter_type_code:
            await svc.check_catalog(session, "meter_type", merged.meter_type_code)
        before = s.MeterIn.model_validate(meter, from_attributes=True).model_dump(mode="json")
        for key, value in merged.model_dump().items():
            setattr(meter, key, value)
        meter.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="meter.updated",
            entity_type="meter",
            entity_id=meter_id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(body.model_dump(exclude_unset=True))},
            changes=diff(before, merged.model_dump(mode="json")),
        )
        return s.MeterOut.model_validate(meter)


# Maintenance --------------------------------------------------------------------------------


async def _check_maintenance_refs(
    session: Any, item: MaintenanceItem, merged: s.MaintenanceIn
) -> None:
    await _unit_of_property(session, merged.unit_id, item.property_id)
    if merged.provider_relation_id is not None:
        relation = await _get(session, ServiceProviderRelation, merged.provider_relation_id)
        if relation.property_id != item.property_id:
            raise svc.invalid("Das Dienstleisterverhältnis gehört nicht zu diesem Objekt.")


@router.patch("/maintenance/{item_id}", summary="Wartung ändern")
async def patch_maintenance(
    item_id: uuid.UUID,
    body: s.MaintenancePatch,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.MaintenanceOut:
    async with tenant_tx(request, principal) as session:
        item = await _get(session, MaintenanceItem, item_id)
        merged: s.MaintenanceIn = _merge(s.MaintenanceIn, item, body)
        await _check_maintenance_refs(session, item, merged)
        before = s.MaintenanceIn.model_validate(item, from_attributes=True).model_dump(mode="json")
        for key, value in merged.model_dump().items():
            setattr(item, key, value)
        item.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="maintenance.updated",
            entity_type="maintenance_item",
            entity_id=item_id,
            actor_user_id=principal.user_id,
            payload={"fields": sorted(body.model_dump(exclude_unset=True))},
            changes=diff(before, merged.model_dump(mode="json")),
        )
        return maintenance_out(item)


@router.post("/maintenance/{item_id}/done", summary="Wartung als erledigt erfassen")
async def complete_maintenance(
    item_id: uuid.UUID,
    body: s.MaintenanceDoneIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> s.MaintenanceDoneOut:
    """Records the completion date. With ``interval_months`` the item stays open and its due
    date moves to ``done_on`` plus the interval (rule C2-01); without an interval the item is
    closed and a second completion is refused (409 ``MHVP-PROP-0005``). The interval is an
    operator entry; no inspection cycle is assumed by the platform."""
    async with tenant_tx(request, principal) as session:
        item = await _get(session, MaintenanceItem, item_id)
        if item.status == "done":
            raise ProblemError(ErrorCodes.PROPERTY_MAINTENANCE_ALREADY_DONE)
        previous_due = item.due_date
        item.done_at = svc.done_at_for(body.done_on)
        next_due = None
        if item.interval_months:
            next_due = svc.add_months(body.done_on, item.interval_months)
            item.due_date = next_due
        else:
            item.status = "done"
        item.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="maintenance.done",
            entity_type="maintenance_item",
            entity_id=item_id,
            actor_user_id=principal.user_id,
            payload={
                "done_on": body.done_on.isoformat(),
                "previous_due_date": previous_due.isoformat() if previous_due else None,
                "next_due_date": next_due.isoformat() if next_due else None,
                "status": item.status,
            },
        )
        return s.MaintenanceDoneOut(item=maintenance_out(item), next_due_date=next_due)
