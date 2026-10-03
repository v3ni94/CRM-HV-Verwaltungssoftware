"""Draft heating statement per operating cost statement (M17-02): inputs, consumption import
from mhvp.metering, calculation trace, feed into the statement as an external cost item
(H01 path stays: the fed item carries ``external_amounts`` per occupancy). Issuing the
statement remains behind G3; nothing here posts or creates receivables."""

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing import calc, calc_settings, heating_calc, services
from mhvp.billing.models import (
    HeatingRuleTable,
    HeatingRuleTableKind,
    Statement,
    StatementCostItem,
    StatementHeating,
)
from mhvp.billing.status import StatementStatus
from mhvp.core.problems import ErrorCodes, ProblemError

AREA_KEY_CODE = "WFL"
CO2_FALLBACK_SOURCE = (
    "Code-Fassung mhvp.billing.calc.CO2_RESIDENTIAL_STEPS (Abruf 23.09.2026), "
    "gegen die amtliche Anlage zum CO2KostAufG zu prüfen (R15, M17-02)"
)


def _dec(value: Any, name: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise ProblemError(ErrorCodes.VALIDATION, detail=f"{name}: keine Zahl.") from None


async def get_or_create(
    session: AsyncSession, statement: Statement, user_id: uuid.UUID | None
) -> StatementHeating:
    row = await session.scalar(
        select(StatementHeating).where(StatementHeating.statement_id == statement.id)
    )
    if row is None:
        row = StatementHeating(
            tenant_id=statement.tenant_id,
            created_by=user_id,
            statement_id=statement.id,
            settings={
                "consumption_share_percent": heating_calc.CONSUMPTION_SHARE_DEFAULT,
                "hot_water_method": "flat_percent",
            },
            co2={"mode": "apply", "building_kind": "unknown"},
        )
        session.add(row)
        await session.flush()
    return row


async def rule_table(
    session: AsyncSession, kind: HeatingRuleTableKind, as_of: date
) -> HeatingRuleTable | None:
    row: HeatingRuleTable | None = await session.scalar(
        select(HeatingRuleTable)
        .where(HeatingRuleTable.kind == kind.value, HeatingRuleTable.valid_from <= as_of)
        .order_by(HeatingRuleTable.valid_from.desc())
        .limit(1)
    )
    return row


def co2_steps_from_rows(rows: Any) -> tuple[tuple[Decimal, int], ...]:
    steps = []
    for r in rows or []:
        bound = _dec(r.get("from_kg_m2"), "from_kg_m2")
        percent = r.get("tenant_percent")
        if bound is None or not isinstance(percent, int):
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="CO2-Stufe braucht from_kg_m2 und tenant_percent."
            )
        steps.append((bound, percent))
    steps.sort(key=lambda s: s[0])
    return tuple(steps)


def degree_days_from_rows(rows: Any) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for k, v in (rows or {}).items():
        try:
            month = int(k)
        except ValueError:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Monat {k!r} ungültig.") from None
        value = _dec(v, f"Gradtage Monat {k}")
        if value is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail=f"Gradtage Monat {k} fehlen.")
        out[month] = value
    return out


async def effective_tables(session: AsyncSession, as_of: date) -> dict[str, Any]:
    """CO2 steps (fallback: code table with source 'zu prüfen') and degree days (default
    empty with a hint); both as data with source and review status."""
    co2_row = await rule_table(session, HeatingRuleTableKind.CO2_STEPS, as_of)
    dd_row = await rule_table(session, HeatingRuleTableKind.DEGREE_DAYS, as_of)
    if co2_row is not None:
        co2 = {
            "rows": co2_row.rows,
            "source": co2_row.source,
            "review_status": co2_row.review_status,
            "valid_from": co2_row.valid_from.isoformat(),
        }
    else:
        co2 = {
            "rows": [
                {"from_kg_m2": str(b), "tenant_percent": p} for b, p in calc.CO2_RESIDENTIAL_STEPS
            ],
            "source": CO2_FALLBACK_SOURCE,
            "review_status": "zu_pruefen",
            "valid_from": None,
        }
    dd = (
        {
            "rows": dd_row.rows,
            "source": dd_row.source,
            "review_status": dd_row.review_status,
            "valid_from": dd_row.valid_from.isoformat(),
        }
        if dd_row is not None
        else {
            "rows": {},
            "source": "",
            "review_status": "fehlt",
            "valid_from": None,
            "hint": "Keine Gradtagstabelle hinterlegt; Nutzerwechsel werden nach Zeitanteil "
            "verteilt und als zu prüfen gekennzeichnet (§ 9b HeizkostenV).",
        }
    )
    return {"co2_steps": co2, "degree_days": dd}


async def _areas(
    session: AsyncSession, statement: Statement, occ: list[dict[str, Any]]
) -> dict[str, Decimal]:
    from mhvp.properties.models import AllocationKey, UnitAllocationValue

    key = await session.scalar(
        select(AllocationKey).where(
            AllocationKey.property_id == statement.property_id,
            AllocationKey.code == AREA_KEY_CODE,
        )
    )
    if key is None:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Umlageschlüssel WFL (Wohnfläche) fehlt am Objekt."
        )
    areas: dict[str, Decimal] = {}
    for o in occ:
        values = (
            await session.scalars(
                select(UnitAllocationValue).where(
                    UnitAllocationValue.unit_id == o["unit_id"],
                    UnitAllocationValue.allocation_key_id == key.id,
                )
            )
        ).all()
        hits = [v for v in values if calc.overlap(o["from"], o["to"], v.valid_from, v.valid_to)]
        if len(hits) != 1:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"Wohnfläche für Einheit {o['unit_number']} im Zeitraum nicht eindeutig.",
            )
        areas[o["key"]] = Decimal(hits[0].value)
    return areas


async def build_occupants(
    session: AsyncSession, statement: Statement, heating: StatementHeating
) -> list[heating_calc.Occupant]:
    occ = await services.occupants(session, statement)
    areas = await _areas(session, statement, occ)
    out = []
    for o in occ:
        c = heating.consumptions.get(o["key"], {})
        out.append(
            heating_calc.Occupant(
                key=o["key"],
                unit_id=str(o["unit_id"]),
                unit_number=o["unit_number"],
                start=o["from"],
                end=o["to"],
                area=areas[o["key"]],
                heating=_dec(c.get("heating"), "heating"),
                hot_water=_dec(c.get("hot_water"), "hot_water"),
                heating_kind=c.get("heating_kind", "missing"),
                hot_water_kind=c.get("hot_water_kind", "missing"),
                source=c.get("source", "manual"),
            )
        )
    return out


def _settings(
    row: StatementHeating, tables: dict[str, Any], negative_costs_mode: str = "legacy_warn"
) -> heating_calc.HeatingSettings:
    s = row.settings
    return heating_calc.HeatingSettings(
        consumption_share_percent=int(
            s.get("consumption_share_percent", heating_calc.CONSUMPTION_SHARE_DEFAULT)
        ),
        hot_water_method=s.get("hot_water_method", "flat_percent"),
        hot_water_flat_percent=_dec(s.get("hot_water_flat_percent"), "hot_water_flat_percent"),
        hot_water_volume_m3=_dec(s.get("hot_water_volume_m3"), "hot_water_volume_m3"),
        hot_water_temperature_c=_dec(s.get("hot_water_temperature_c"), "hot_water_temperature_c"),
        hot_water_formula_factor=_dec(s.get("hot_water_formula_factor"), "factor")
        or heating_calc.HOT_WATER_FORMULA_FACTOR_DEFAULT,
        total_energy_kwh=_dec(s.get("total_energy_kwh"), "total_energy_kwh"),
        heating_energy_kwh=_dec(s.get("heating_energy_kwh"), "heating_energy_kwh"),
        hot_water_energy_kwh=_dec(s.get("hot_water_energy_kwh"), "hot_water_energy_kwh"),
        degree_days=degree_days_from_rows(tables["degree_days"]["rows"]),
        degree_days_source=tables["degree_days"]["source"],
        # AK01 (GAI-202): tenant switch, default legacy_warn.
        negative_costs_mode=negative_costs_mode,
    )


def _co2(row: StatementHeating, tables: dict[str, Any]) -> heating_calc.Co2Input:
    c = row.co2
    return heating_calc.Co2Input(
        mode=c.get("mode", "apply"),
        building_kind=c.get("building_kind", "unknown"),
        costs=_dec(c.get("costs"), "co2.costs"),
        emissions_kg=_dec(c.get("emissions_kg"), "co2.emissions_kg"),
        reference_area_m2=_dec(c.get("reference_area_m2"), "co2.reference_area_m2"),
        reason=c.get("reason"),
        steps=co2_steps_from_rows(tables["co2_steps"]["rows"]),
        steps_source=tables["co2_steps"]["source"],
    )


def _unit_totals(row: StatementHeating) -> dict[str, dict[str, Decimal | None]]:
    return {
        unit_id: {
            "heating": _dec(v.get("heating"), "heating"),
            "hot_water": _dec(v.get("hot_water"), "hot_water"),
        }
        for unit_id, v in row.unit_totals.items()
    }


async def calculate(
    session: AsyncSession, statement: Statement, row: StatementHeating
) -> dict[str, Any]:
    if row.total_costs is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Gesamtkosten fehlen.")
    tables = await effective_tables(session, statement.period_from)
    occupants = await build_occupants(session, statement, row)
    try:
        result = heating_calc.calculate(
            period_from=statement.period_from,
            period_to=statement.period_to,
            total_costs=Decimal(row.total_costs),
            settings=_settings(
                row, tables, (await calc_settings.load(session)).heating_negative_costs_mode
            ),
            co2=_co2(row, tables),
            occupants=occupants,
            unit_totals=_unit_totals(row),
        )
    except heating_calc.HeatingCalcError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from None
    result["tables"] = tables
    row.result = result
    row.result_hash = hashlib.sha256(
        json.dumps(result, sort_keys=True, default=str).encode()
    ).hexdigest()
    await session.flush()
    return result


async def apply(
    session: AsyncSession, statement: Statement, row: StatementHeating, user_id: uuid.UUID | None
) -> StatementCostItem:
    """Feed the draft result as one external heating position (H01 path). Refused when the
    statement is no longer a draft, the CO2 status is unresolved or the result is stale."""
    if statement.status is not StatementStatus.DRAFT:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Nach der Berechnung nur über eine neue Version änderbar."
        )
    if row.result is None or row.result_hash is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Erst Heizkosten berechnen.")
    if row.result["co2"]["status"] == "pruefen":
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="CO2-Aufteilung im Prüfstatus; Übernahme erst nach Klärung (D27).",
        )
    if row.applied_item_id is not None:
        existing = await session.get(StatementCostItem, row.applied_item_id)
        if existing is not None:
            await session.delete(existing)
            await session.flush()
    amounts = {k: Decimal(v["total"]) for k, v in row.result["per_occupant"].items()}
    total = sum(amounts.values(), Decimal("0.00"))
    item = StatementCostItem(
        tenant_id=statement.tenant_id,
        created_by=user_id,
        statement_id=statement.id,
        label="Heiz- und Warmwasserkosten (Entwurf HeizkostenV)",
        amount=total,
        external_amounts={k: str(v) for k, v in amounts.items()},
        basis=(
            f"Eigene Heizkostenberechnung als Entwurf, Regelversion "
            f"{row.result['rule_version']}, Rechenweg {row.result_hash[:16]}; "
            "fachliche Freigabe M17-02 offen."
        ),
        heating=True,
    )
    session.add(item)
    await session.flush()
    row.applied_item_id = item.id
    await session.flush()
    return item


async def import_from_metering(
    session: AsyncSession,
    statement: Statement,
    row: StatementHeating,
    *,
    heating_kinds: tuple[str, ...] = ("heating",),
    hot_water_kinds: tuple[str, ...] = ("hot_water",),
) -> dict[str, Any]:
    """Take period consumptions from mhvp.metering for the statement period. A value whose
    period equals one occupancy goes to that occupancy; a value covering the whole statement
    period of a unit with several occupancies becomes a unit total (split later by degree
    days or days, D25). Missing values stay missing (never zero)."""
    from mhvp.metering.models import (
        MeteringConsumptionValue,
        MeteringPropertyAssignment,
        MeteringUnitAssignment,
    )

    assignments = (
        await session.scalars(
            select(MeteringPropertyAssignment).where(
                MeteringPropertyAssignment.property_id == statement.property_id
            )
        )
    ).all()
    if not assignments:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Kein Messdienst am Objekt zugeordnet.")
    occ = await services.occupants(session, statement)
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for o in occ:
        by_unit.setdefault(str(o["unit_id"]), []).append(o)
    consumptions = dict(row.consumptions)
    unit_totals = dict(row.unit_totals)
    taken = 0
    skipped: list[str] = []
    for pa in assignments:
        unit_map = {
            ua.id: str(ua.unit_id)
            for ua in (
                await session.scalars(
                    select(MeteringUnitAssignment).where(
                        MeteringUnitAssignment.property_assignment_id == pa.id
                    )
                )
            ).all()
        }
        values = (
            await session.scalars(
                select(MeteringConsumptionValue).where(
                    MeteringConsumptionValue.property_assignment_id == pa.id,
                    MeteringConsumptionValue.reading_type == "period_consumption",
                    MeteringConsumptionValue.period_from >= statement.period_from,
                    MeteringConsumptionValue.period_to <= statement.period_to,
                )
            )
        ).all()
        for v in values:
            component = (
                "heating"
                if v.kind in heating_kinds
                else "hot_water"
                if v.kind in hot_water_kinds
                else None
            )
            unit_id = unit_map.get(v.unit_assignment_id) if v.unit_assignment_id else None
            if component is None or unit_id is None or unit_id not in by_unit:
                skipped.append(str(v.id))
                continue
            if v.value_kind == "missing" or v.value is None:
                skipped.append(str(v.id))
                continue
            kind = "estimated" if v.value_kind == "estimated" else "actual"
            match = [
                o for o in by_unit[unit_id] if o["from"] == v.period_from and o["to"] == v.period_to
            ]
            if match:
                entry = dict(consumptions.get(match[0]["key"], {}))
                entry[component] = str(v.value)
                entry[f"{component}_kind"] = kind
                entry["source"] = f"metering:{v.source}"
                entry[f"{component}_ref"] = str(v.id)
                consumptions[match[0]["key"]] = entry
                taken += 1
            elif v.period_from == statement.period_from and v.period_to == statement.period_to:
                entry = dict(unit_totals.get(unit_id, {}))
                entry[component] = str(v.value)
                entry[f"{component}_kind"] = kind
                entry["source"] = f"metering:{v.source}"
                unit_totals[unit_id] = entry
                taken += 1
            else:
                skipped.append(str(v.id))
    row.consumptions = consumptions
    row.unit_totals = unit_totals
    row.result = None
    row.result_hash = None
    await session.flush()
    return {"taken": taken, "skipped": skipped}


async def consumption_info(
    session: AsyncSession, statement: Statement, row: StatementHeating
) -> list[dict[str, Any]]:
    """Consumption information per occupancy (§ 6a HeizkostenV, H03, D26): values, their
    origin and the draft cost share. The delivery process is documented, not automated."""
    occupants = await build_occupants(session, statement, row)
    result = row.result or {}
    per = result.get("per_occupant", {})
    out = []
    for o in occupants:
        if o.is_vacancy:
            continue
        out.append(
            {
                "key": o.key,
                "unit_number": o.unit_number,
                "from": o.start.isoformat(),
                "to": o.end.isoformat(),
                "heating": _serial(o.heating),
                "heating_kind": o.heating_kind,
                "hot_water": _serial(o.hot_water),
                "hot_water_kind": o.hot_water_kind,
                "source": o.source,
                "cost_share": per.get(o.key, {}).get("total"),
                "status": "entwurf",
            }
        )
    return out


def _serial(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


async def comparison(
    session: AsyncSession,
    statement: Statement,
    row: StatementHeating,
    *,
    tolerance_abs: Decimal,
    tolerance_percent: Decimal,
) -> dict[str, Any]:
    """External heating items (all except the fed own item) against the last own result.
    Read only (AB10-01 / M17-02)."""
    from mhvp.billing import heating_compare
    from mhvp.billing.models import StatementCostItem

    items = (
        await session.scalars(
            select(StatementCostItem).where(
                StatementCostItem.statement_id == statement.id,
                StatementCostItem.heating.is_(True),
            )
        )
    ).all()
    external = [
        heating_compare.ExternalItem(i.label, dict(i.external_amounts or {}))
        for i in items
        if i.id != row.applied_item_id and i.external_amounts
    ]
    occupants = await build_occupants(session, statement, row) if row.result else []
    return heating_compare.compare(
        result=row.result,
        key_to_unit={o.key: o.unit_id for o in occupants},
        external=external,
        tolerance_abs=tolerance_abs,
        tolerance_percent=tolerance_percent,
    )
