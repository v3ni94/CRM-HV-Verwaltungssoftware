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
from mhvp.core.listparams import strict_query
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


INCOME_LOCKED = (
    "Die Anzeige der Mieterträge ist für diesen Mandanten nicht freigegeben. "
    "Bitte wenden Sie sich an die Verwaltung."
)


@router.get("/rental-income", summary="Vereinbarte Mieterträge je Objekt (Kapitalanleger)")
async def rental_income(request: Request, ctx: Portal = Depends(portal_user)) -> dict[str, Any]:
    from mhvp.contracts.models import Contract, ContractKind, ContractPayment
    from mhvp.properties.models import Property, Unit

    principal, account = ctx
    today = local_today()
    async with tenant_tx(request, principal) as session:
        _, ownership = await _owner_scope(session, account, today)
        from mhvp.portal import features as portal_features

        # AE13: the investor view is a tenant switch, off by default (Q10-02 data protection).
        if not (await portal_features.get_or_default(session)).owner_rental_income_enabled:
            return {"items": [], "currency": "EUR", "note": INCOME_LOCKED, "enabled": False}
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
        return {"items": items, "currency": "EUR", "note": INCOME_NOTE, "enabled": True}


REPORTING_NOTE = (
    "Berichte zu den von uns für Sie verwalteten Einheiten: vereinbarte Miete, auf Mieter "
    "umlagefähige Kosten laut ausgegebener Betriebskostenabrechnung und Leerstandstage je "
    "Abrechnungszeitraum. Keine Mieternamen, kein Zahlungsstatus."
)
REPORTING_GATE_NOTE = (
    "Das Eigentümerreporting ist für diesen Mandanten noch nicht freigegeben "
    "(Freigabestufe G3). Bitte wenden Sie sich an die Verwaltung."
)
REPORTING_STATUSES = ("issued", "due", "posted", "locked")


def _days_between(start: str, end: str, period_from: Any, period_to: Any) -> int:
    from datetime import date as _date

    lo = max(_date.fromisoformat(start), period_from)
    hi = min(_date.fromisoformat(end), period_to)
    return int(max((hi - lo).days + 1, 0))


@router.get(
    "/rental-reporting",
    summary="Eigentümerreporting Kapitalanleger: Mieterträge, Umlagefähigkeit, Leerstand",
    dependencies=[Depends(strict_query)],
)
async def rental_reporting(
    request: Request, unit_id: uuid.UUID | None = None, ctx: Portal = Depends(portal_user)
) -> dict[str, Any]:
    """Read only report per own special-administration unit and settlement period (GAF-34).

    Off by default (``owner_rental_income_enabled``, question P13-01) and behind release gate
    G3. Amounts come from the issued operating cost statement snapshot; nothing is recomputed
    and nothing is posted. A foreign unit answers 404 without a hint."""
    from mhvp.billing.models import Statement, StatementSnapshot
    from mhvp.contracts.models import Contract, ContractKind, ContractPayment
    from mhvp.core.problems import ErrorCodes, ProblemError
    from mhvp.core.release_gates import (
        ReleaseGate,
        ReleaseGateClosedError,
        ensure_release_gate_open,
    )
    from mhvp.portal import features as portal_features
    from mhvp.properties.models import Property, Unit

    principal, account = ctx
    today = local_today()
    async with tenant_tx(request, principal) as session:
        _, ownership = await _owner_scope(session, account, today)
        flags = await portal_features.get_or_default(session)
        own_units: dict[uuid.UUID, Unit] = {}
        if ownership:
            rows = (
                await session.scalars(
                    select(Unit)
                    .join(Contract, Contract.unit_id == Unit.id)
                    .where(Contract.id.in_(ownership), Contract.sev_enabled.is_(True))
                )
            ).all()
            own_units = {u.id: u for u in rows}
        if unit_id is not None and unit_id not in own_units:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if not flags.owner_rental_income_enabled:
            return {"items": [], "note": INCOME_LOCKED, "enabled": False, "currency": "EUR"}
        try:
            await ensure_release_gate_open(
                ReleaseGate.G3, principal.tenant_id, request.app.state.release_gate_resolver
            )
        except ReleaseGateClosedError:
            return {"items": [], "note": REPORTING_GATE_NOTE, "enabled": False, "currency": "EUR"}
        items: list[dict[str, Any]] = []
        selected = [u for u in own_units.values() if unit_id in (None, u.id)]
        for unit in sorted(selected, key=lambda u: (str(u.property_id), u.number)):
            prop = await session.get(Property, unit.property_id)
            statements = (
                await session.scalars(
                    select(Statement)
                    .where(
                        Statement.property_id == unit.property_id,
                        Statement.snapshot_id.is_not(None),
                        Statement.status.in_(REPORTING_STATUSES),
                    )
                    .order_by(Statement.period_to.desc(), Statement.version.desc())
                )
            ).all()
            superseded = {r.supersedes_id for r in statements if r.supersedes_id}
            periods: list[dict[str, Any]] = []
            for st in statements:
                if st.id in superseded:
                    continue
                snap = await session.get(StatementSnapshot, st.snapshot_id)
                if snap is None:
                    continue
                costs = Decimal("0.00")
                for r in snap.results.get("results", []):
                    if r.get("unit_number") == unit.number:
                        costs += Decimal(r["costs"])
                vacancy_days = sum(
                    _days_between(o["from"], o["to"], st.period_from, st.period_to)
                    for o in snap.inputs.get("occupants", [])
                    if o.get("unit_id") == str(unit.id) and o.get("contract_id") is None
                )
                payments = (
                    await session.scalars(
                        select(ContractPayment)
                        .join(Contract, Contract.id == ContractPayment.contract_id)
                        .where(
                            Contract.unit_id == unit.id,
                            Contract.kind == ContractKind.TENANCY,
                            Contract.start_date <= st.period_to,
                            or_(Contract.end_date.is_(None), Contract.end_date >= st.period_to),
                            ContractPayment.valid_from <= st.period_to,
                            or_(
                                ContractPayment.valid_to.is_(None),
                                ContractPayment.valid_to >= st.period_to,
                            ),
                        )
                    )
                ).all()
                periods.append(
                    {
                        "statement_id": st.id,
                        "period_from": st.period_from,
                        "period_to": st.period_to,
                        "status": st.status.value,
                        "agreed_rent_monthly_gross": str(
                            sum((p.gross for p in payments), Decimal("0.00"))
                        ),
                        "allocable_costs_tenant": str(costs),
                        "allocable_costs_property": snap.results.get("total", "0.00"),
                        "vacancy_days": vacancy_days,
                        "vacancy_owner_share_property": snap.results.get(
                            "vacancy_owner_share", "0.00"
                        ),
                    }
                )
            items.append(
                {
                    "unit_id": unit.id,
                    "unit_number": unit.number,
                    "property_name": prop.name if prop else None,
                    "periods": periods,
                }
            )
        return {
            "items": items,
            "currency": "EUR",
            "enabled": True,
            "note": REPORTING_NOTE,
            "allocability_note": (
                "Nicht umlagefähige Kosten (zum Beispiel Verwaltung und Instandsetzung) sind "
                "nicht Teil der Betriebskostenabrechnung und werden hier nicht ausgewiesen."
            ),
        }


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
