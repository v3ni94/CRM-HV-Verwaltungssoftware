"""Owner portal: allocation properties and rental income per property (A.5, M21-06, SA-05).

* ``GET /portal/owner/allocation-properties``: per own unit the allocation keys of the property
  (code, name, unit of measure, kind) with the unit's key value valid today. Information about
  the master data; the keys that apply to a statement are the resolved ones (see the statement).
* ``GET /portal/owner/takeover-checklist`` (R03, M7-01): status of the takeover checklist of
  the own properties (label, status, due date, read only). Internal notes, documents and
  tickets of the management are not part of it.
* ``GET /portal/owner/rental-income``: for own units that the management administers for the
  owner (special property administration, ``sev_enabled`` on the ownership contract) the
  current agreed rent components of the active tenancy, summed per property. No tenant name,
  no payment status: only the agreed amounts (data minimisation). Without an enabled special
  property administration the list stays empty.

Scope comes from the active owner grants only, RLS applies through ``tenant_tx``; tenants,
providers and staff accounts get 403. No endpoint opens a gate and none posts anything."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select

from mhvp.core.auth.principal import tenant_tx
from mhvp.portal.owner import _owner_scope
from mhvp.portal.routers import Portal, portal_user
from mhvp.workspace.services import local_today

router = APIRouter(prefix="/portal/owner", tags=["Portal"])
ALLOCATION_NOTE = (
    "Stammdaten der Umlageschlüssel Ihrer Einheiten. Für eine Abrechnung gelten die "
    "beschlossenen Schlüssel."
)
INCOME_NOTE = (
    "Vereinbarte Miete der von uns für Sie verwalteten Einheiten (Sondereigentumsverwaltung). "
    "Keine Abrechnung und kein Zahlungsstatus."
)


@router.get("/allocation-properties", summary="Umlageeigenschaften der eigenen Einheiten")
async def allocation_properties(
    request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import AllocationKey, Property, Unit, UnitAllocationValue

    principal, account = ctx
    today = local_today()
    async with tenant_tx(request, principal) as session:
        _, ownership = await _owner_scope(session, account, today)
        items: list[dict[str, Any]] = []
        if not ownership:
            return {"items": items, "note": ALLOCATION_NOTE}
        rows = (
            await session.execute(
                select(Unit, Property)
                .join(Contract, Contract.unit_id == Unit.id)
                .join(Property, Property.id == Unit.property_id)
                .where(Contract.id.in_(ownership))
                .order_by(Property.number, Unit.number)
            )
        ).all()
        for unit, prop in rows:
            keys = (
                await session.execute(
                    select(AllocationKey, UnitAllocationValue.value)
                    .outerjoin(
                        UnitAllocationValue,
                        (UnitAllocationValue.allocation_key_id == AllocationKey.id)
                        & (UnitAllocationValue.unit_id == unit.id)
                        & (UnitAllocationValue.valid_from <= today)
                        & or_(
                            UnitAllocationValue.valid_to.is_(None),
                            UnitAllocationValue.valid_to >= today,
                        ),
                    )
                    .where(AllocationKey.property_id == prop.id)
                    .order_by(AllocationKey.sort_order, AllocationKey.code)
                )
            ).all()
            items.append(
                {
                    "unit_id": unit.id,
                    "unit_number": unit.number,
                    "property_name": prop.name,
                    "keys": [
                        {
                            "code": k.code,
                            "name": k.name,
                            "unit_of_measure": k.unit_of_measure,
                            "kind": k.kind.value,
                            "value": None if value is None else str(value),
                        }
                        for k, value in keys
                    ],
                }
            )
        return {"items": items, "note": ALLOCATION_NOTE}


@router.get("/rental-income", summary="Vereinbarte Mieterträge je Objekt (Kapitalanleger)")
async def rental_income(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    from mhvp.contracts.models import Contract, ContractKind, ContractPayment
    from mhvp.properties.models import Property, Unit

    principal, account = ctx
    today = local_today()
    async with tenant_tx(request, principal) as session:
        _, ownership = await _owner_scope(session, account, today)
        units: set[uuid.UUID] = set()
        if ownership:
            units = set(
                await session.scalars(
                    select(Contract.unit_id).where(
                        Contract.id.in_(ownership), Contract.sev_enabled.is_(True)
                    )
                )
            )
        per_property: dict[uuid.UUID, dict[str, Any]] = {}
        if units:
            tenancies = (
                await session.execute(
                    select(Contract, Unit, Property)
                    .join(Unit, Unit.id == Contract.unit_id)
                    .join(Property, Property.id == Unit.property_id)
                    .where(
                        Contract.unit_id.in_(units),
                        Contract.kind == ContractKind.TENANCY,
                        Contract.start_date <= today,
                        or_(Contract.end_date.is_(None), Contract.end_date >= today),
                    )
                    .order_by(Property.number, Unit.number)
                )
            ).all()
            for contract, unit, prop in tenancies:
                payments = (
                    await session.scalars(
                        select(ContractPayment).where(
                            ContractPayment.contract_id == contract.id,
                            ContractPayment.valid_from <= today,
                            or_(
                                ContractPayment.valid_to.is_(None),
                                ContractPayment.valid_to >= today,
                            ),
                        )
                    )
                ).all()
                gross = sum((p.gross for p in payments), Decimal("0.00"))
                entry = per_property.setdefault(
                    prop.id,
                    {
                        "property_id": prop.id,
                        "property_name": prop.name,
                        "units": [],
                        "total_gross": Decimal("0.00"),
                    },
                )
                entry["units"].append(
                    {
                        "unit_number": unit.number,
                        "components": [
                            {"payment_type_code": p.payment_type_code, "gross": str(p.gross)}
                            for p in sorted(payments, key=lambda p: p.payment_type_code)
                        ],
                        "gross": str(gross),
                    }
                )
                entry["total_gross"] += gross
        items = [{**v, "total_gross": str(v["total_gross"])} for v in per_property.values()]
        return {"items": items, "currency": "EUR", "note": INCOME_NOTE}


TAKEOVER_NOTE = (
    "Stand der Objektübernahme durch die Verwaltung. Die Anzeige dient der Information, "
    "Notizen und Unterlagen der Verwaltung sind nicht enthalten."
)
TAKEOVER_STATUS_LABELS = {
    "open": "offen",
    "requested": "angefordert",
    "received": "erhalten",
    "not_applicable": "nicht erforderlich",
}


@router.get("/takeover-checklist", summary="Checkliste der Objektübernahme (Eigentümer, lesend)")
async def takeover_checklist(
    request: Request, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    from mhvp.contracts.models import Contract
    from mhvp.properties.models import (
        TAKEOVER_CATEGORIES,
        Property,
        PropertyTakeoverItem,
    )
    from mhvp.properties.routers_takeover import LABELS

    principal, account = ctx
    async with tenant_tx(request, principal) as session:
        _, ownership = await _owner_scope(session, account, local_today())
        items: list[dict[str, Any]] = []
        if not ownership:
            return {"items": items, "note": TAKEOVER_NOTE}
        properties = (
            await session.scalars(
                select(Property)
                .where(
                    Property.id.in_(select(Contract.property_id).where(Contract.id.in_(ownership)))
                )
                .order_by(Property.number)
            )
        ).all()
        order = {c: i for i, c in enumerate(TAKEOVER_CATEGORIES)}
        for prop in properties:
            rows = (
                await session.scalars(
                    select(PropertyTakeoverItem).where(PropertyTakeoverItem.property_id == prop.id)
                )
            ).all()
            if not rows:
                continue
            points = [
                {
                    "category": r.category,
                    "label": LABELS[r.category],
                    "status": r.status,
                    "status_label": TAKEOVER_STATUS_LABELS[r.status],
                    "due_date": r.due_date,
                }
                for r in sorted(rows, key=lambda r: order[r.category])
            ]
            open_count = sum(1 for p in points if p["status"] in ("open", "requested"))
            items.append(
                {
                    "property_id": prop.id,
                    "property_name": prop.name,
                    "points": points,
                    "open_count": open_count,
                    "complete": open_count == 0,
                }
            )
        return {"items": items, "note": TAKEOVER_NOTE}
