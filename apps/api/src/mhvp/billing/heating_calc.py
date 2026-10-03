"""Heating and hot water cost distribution (HeizkostenV) as a DRAFT calculation (M17-02, H02,
H04; annex D cases D25 to D27). Pure functions on Decimal; every step is returned as JSON
serialisable "trace" so a person can recompute the result by hand.

Nothing in this module is a released legal rule: the consumption share, the hot water
formula factor, the CO2 step table and the degree day table are configuration with source
status "zu prüfen" (docs/rules/M17-02-heizkosten.md). Missing values are never coerced to
zero; the calculation refuses instead (rule 0.1.3).
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from mhvp.billing.calc import CENT, Share, distribute, overlap

HEATING_RULE_VERSION = "heating-costs-draft-v1"
CONSUMPTION_SHARE_MIN = 50
CONSUMPTION_SHARE_MAX = 70
CONSUMPTION_SHARE_DEFAULT = 70
HOT_WATER_METHODS = ("flat_percent", "measured", "formula")
CO2_BUILDING_KINDS = ("residential", "non_residential", "mixed", "self_supply", "unknown")
CO2_MODES = ("apply", "not_applicable")
VALUE_KINDS = ("actual", "interim", "estimated", "missing")
# Draft only: § 9 Abs. 2 HeizkostenV names a factor for the hot water energy formula; the
# value here is configuration to be verified against the official text (M17-02).
HOT_WATER_FORMULA_FACTOR_DEFAULT = Decimal("2.5")
HOT_WATER_FORMULA_BASE_TEMPERATURE = Decimal("10")


class HeatingCalcError(ValueError):
    """Input does not allow a traceable calculation (never silently zeroed)."""


@dataclass(frozen=True)
class Occupant:
    key: str  # occupancy key of billing.services.occupants (contract:.. or vacancy:..)
    unit_id: str
    unit_number: str
    start: date
    end: date
    area: Decimal
    heating: Decimal | None = None
    hot_water: Decimal | None = None
    heating_kind: str = "missing"
    hot_water_kind: str = "missing"
    source: str = "manual"

    @property
    def is_vacancy(self) -> bool:
        return self.key.startswith("vacancy:")


@dataclass(frozen=True)
class Co2Input:
    mode: str = "apply"  # apply | not_applicable (with reason)
    building_kind: str = "unknown"
    costs: Decimal | None = None  # CO2 cost component contained in the fuel costs
    emissions_kg: Decimal | None = None
    reference_area_m2: Decimal | None = None
    reason: str | None = None
    steps: tuple[tuple[Decimal, int], ...] = ()  # (lower bound kg/m2a, tenant percent)
    steps_source: str = ""


@dataclass(frozen=True)
class HeatingSettings:
    consumption_share_percent: int = CONSUMPTION_SHARE_DEFAULT
    hot_water_method: str = "flat_percent"
    hot_water_flat_percent: Decimal | None = None
    hot_water_volume_m3: Decimal | None = None
    hot_water_temperature_c: Decimal | None = None
    hot_water_formula_factor: Decimal = HOT_WATER_FORMULA_FACTOR_DEFAULT
    total_energy_kwh: Decimal | None = None
    heating_energy_kwh: Decimal | None = None
    hot_water_energy_kwh: Decimal | None = None
    degree_days: dict[int, Decimal] = field(default_factory=dict)  # month -> promille
    degree_days_source: str = ""
    # GAI-202: negative cost parts (credit, refund). "legacy_warn" keeps the previous result
    # (zero shares) and adds a warning; "distribute" splits them sign symmetric (AJ01-01).
    negative_costs_mode: str = "legacy_warn"


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _s(value: Decimal | int | None) -> str | None:
    return None if value is None else str(value)


def validate_degree_days(rows: dict[int, Decimal]) -> None:
    if not rows:
        return
    if set(rows) != set(range(1, 13)):
        raise HeatingCalcError("Gradtagstabelle braucht genau die Monate 1 bis 12.")
    total = sum(rows.values(), Decimal(0))
    if total != Decimal(1000):
        raise HeatingCalcError(f"Gradtagstabelle ergibt {total} statt 1000 Promille.")
    if any(v < 0 for v in rows.values()):
        raise HeatingCalcError("Gradtagswerte dürfen nicht negativ sein.")


def validate_co2_steps(steps: tuple[tuple[Decimal, int], ...]) -> None:
    if not steps:
        return
    bounds = [b for b, _ in steps]
    if bounds[0] != Decimal(0) or bounds != sorted(bounds) or len(set(bounds)) != len(bounds):
        raise HeatingCalcError("CO2-Stufen müssen bei 0 beginnen und aufsteigend sein.")
    if any(p < 0 or p > 100 for _, p in steps):
        raise HeatingCalcError("CO2-Mieteranteil muss zwischen 0 und 100 Prozent liegen.")


def time_weight(start: date, end: date, degree_days: dict[int, Decimal]) -> tuple[Decimal, str]:
    """Share of the year for an occupancy span: degree day promille per month (§ 9b, D25)
    when a table is configured, otherwise plain days. Returns (weight, method)."""
    if not degree_days:
        return Decimal((end - start).days + 1), "days"
    weight = Decimal(0)
    cursor = start
    while cursor <= end:
        last_day = calendar.monthrange(cursor.year, cursor.month)[1]
        stop = min(end, date(cursor.year, cursor.month, last_day))
        days_in_month = Decimal(last_day)
        covered = Decimal((stop - cursor).days + 1)
        weight += degree_days[cursor.month] * covered / days_in_month
        cursor = stop + timedelta(days=1)
    return weight, "degree_days"


def co2_split(co2: Co2Input, period_days: int) -> dict[str, Any]:
    """CO2KostAufG step model for residential buildings; everything else gets an explicit
    review status instead of an invented value (D27, H04)."""
    if co2.mode == "not_applicable":
        if not co2.reason:
            raise HeatingCalcError("CO2-Aufteilung 'nicht anwendbar' braucht eine Begründung.")
        return {
            "status": "nicht_anwendbar",
            "reason": co2.reason,
            "landlord": "0.00",
            "tenant": _s(co2.costs),
            "notes": ["Nichtanwendbarkeit vom Bearbeiter erklärt; fachlich zu prüfen (H04)."],
        }
    notes: list[str] = []
    missing = [
        name
        for name, value in (
            ("co2_costs", co2.costs),
            ("emissions_kg", co2.emissions_kg),
            ("reference_area_m2", co2.reference_area_m2),
        )
        if value is None
    ]
    if missing:
        return {
            "status": "pruefen",
            "missing": missing,
            "notes": ["Lieferangaben fehlen; keine Aufteilung und keine Nullkosten (D27)."],
        }
    if co2.building_kind != "residential":
        return {
            "status": "pruefen",
            "building_kind": co2.building_kind,
            "notes": [
                "Keine Regelgruppe hinterlegt (Nichtwohngebäude, gemischt, Selbstversorgung "
                "oder unbekannt); Einordnung durch fachkundige Person (H04, D27)."
            ],
        }
    if not co2.steps:
        return {
            "status": "pruefen",
            "notes": ["CO2-Stufentabelle ist leer; Pflege mit Quelle erforderlich (M17-02)."],
        }
    costs, emissions, area = co2.costs, co2.emissions_kg, co2.reference_area_m2
    if costs is None or emissions is None or area is None:  # pragma: no cover (checked above)
        raise HeatingCalcError("CO2-Angaben unvollständig.")
    if area <= 0 or costs < 0 or emissions < 0:
        raise HeatingCalcError("CO2-Angaben müssen positiv sein (Fläche größer null).")
    if period_days not in (365, 366):
        notes.append(
            "Abrechnungszeitraum ist kein volles Jahr; zeitliche Hochrechnung der Emissionen "
            "nicht umgesetzt, Einordnung zu prüfen (H04)."
        )
    specific = emissions / area  # kg per m2 and year, unrounded
    percent = next(p for bound, p in reversed(co2.steps) if specific >= bound)
    tenant = _q(costs * percent / 100)
    landlord = costs - tenant
    return {
        "status": "berechnet" if not notes else "pruefen",
        "specific_emissions_kg_m2": str(specific),
        "tenant_percent": percent,
        "tenant": str(tenant),
        "landlord": str(landlord),
        "steps_source": co2.steps_source,
        "notes": notes,
    }


def split_hot_water(
    allocable: Decimal, s: HeatingSettings
) -> tuple[Decimal, Decimal, dict[str, Any]]:
    """Separate hot water from heating costs: flat percent, measured energy or the formula
    (draft factor). Returns (heating, hot_water, trace)."""
    if s.hot_water_method == "flat_percent":
        if s.hot_water_flat_percent is None or not (0 <= s.hot_water_flat_percent <= 100):
            raise HeatingCalcError("Pauschaler Warmwasseranteil fehlt oder ungültig (0 bis 100).")
        hot = _q(allocable * s.hot_water_flat_percent / 100)
        trace: dict[str, Any] = {"method": "flat_percent", "percent": str(s.hot_water_flat_percent)}
    elif s.hot_water_method == "measured":
        if s.heating_energy_kwh is None or s.hot_water_energy_kwh is None:
            raise HeatingCalcError("Gemessene Energie für Heizung und Warmwasser fehlt.")
        total = s.heating_energy_kwh + s.hot_water_energy_kwh
        if total <= 0:
            raise HeatingCalcError("Gemessene Energiesumme ist null.")
        hot = _q(allocable * s.hot_water_energy_kwh / total)
        trace = {
            "method": "measured",
            "heating_energy_kwh": str(s.heating_energy_kwh),
            "hot_water_energy_kwh": str(s.hot_water_energy_kwh),
        }
    elif s.hot_water_method == "formula":
        if (
            s.hot_water_volume_m3 is None
            or s.hot_water_temperature_c is None
            or s.total_energy_kwh is None
        ):
            raise HeatingCalcError("Formel braucht Volumen, Temperatur und Gesamtenergie.")
        if s.total_energy_kwh <= 0:
            raise HeatingCalcError("Gesamtenergie muss größer null sein.")
        q_hot = (
            s.hot_water_formula_factor
            * s.hot_water_volume_m3
            * (s.hot_water_temperature_c - HOT_WATER_FORMULA_BASE_TEMPERATURE)
        )
        if q_hot < 0 or q_hot > s.total_energy_kwh:
            raise HeatingCalcError("Warmwasserenergie nach Formel übersteigt die Gesamtenergie.")
        hot = _q(allocable * q_hot / s.total_energy_kwh)
        trace = {
            "method": "formula",
            "factor": str(s.hot_water_formula_factor),
            "volume_m3": str(s.hot_water_volume_m3),
            "temperature_c": str(s.hot_water_temperature_c),
            "hot_water_energy_kwh": str(q_hot),
            "total_energy_kwh": str(s.total_energy_kwh),
            "note": "Formelfaktor ist Entwurf, gegen § 9 HeizkostenV zu prüfen (M17-02).",
        }
    else:
        raise HeatingCalcError(f"Unbekannte Warmwassermethode {s.hot_water_method!r}.")
    return allocable - hot, hot, trace


def _resolve_consumption(
    occupants: list[Occupant],
    unit_totals: dict[str, dict[str, Decimal | None]],
    degree_days: dict[int, Decimal],
    component: str,
) -> tuple[dict[str, Decimal], list[str], list[str]]:
    """Consumption per occupancy. An occupancy without its own value (no intermediate
    reading) takes its part of the unit total by degree days or days (D25); flagged."""
    values: dict[str, Decimal] = {}
    estimated: list[str] = []
    notes: list[str] = []
    by_unit: dict[str, list[Occupant]] = {}
    for o in occupants:
        by_unit.setdefault(o.unit_id, []).append(o)
    for unit_id, occs in by_unit.items():
        own = {o.key: getattr(o, component) for o in occs}
        kinds = {o.key: getattr(o, f"{component}_kind") for o in occs}
        for o in occs:
            if kinds[o.key] == "estimated" and own[o.key] is not None:
                estimated.append(o.key)
        if all(v is not None for v in own.values()):
            for k, v in own.items():
                if v is not None:
                    values[k] = v
            continue
        total = (unit_totals.get(unit_id) or {}).get(component)
        if total is None:
            missing = sorted(k for k, v in own.items() if v is None)
            raise HeatingCalcError(
                f"{component}: Verbrauch fehlt für {missing} und kein Einheitenwert vorhanden."
            )
        known = sum((v for v in own.values() if v is not None), Decimal(0))
        rest = total - known
        if rest < 0:
            raise HeatingCalcError(f"{component}: Einzelwerte übersteigen den Einheitenwert.")
        open_occs = [o for o in occs if own[o.key] is None]
        weights = {o.key: time_weight(o.start, o.end, degree_days)[0] for o in open_occs}
        wsum = sum(weights.values(), Decimal(0))
        for o in open_occs:
            values[o.key] = rest * weights[o.key] / wsum if wsum > 0 else Decimal(0)
            estimated.append(o.key)
        for k, v in own.items():
            if v is not None:
                values[k] = v
        method = "Gradtagen" if degree_days else "Zeitanteil"
        notes.append(
            f"{component}: Einheit {occs[0].unit_number} ohne Zwischenablesung, Verbrauch "
            f"{rest} nach {method} aufgeteilt (§ 9b HeizkostenV, zu prüfen)."
        )
    return values, estimated, notes


def _component(
    label: str,
    costs: Decimal,
    share_percent: int,
    occupants: list[Occupant],
    consumption: dict[str, Decimal],
    degree_days: dict[int, Decimal],
    negative_costs_mode: str = "legacy_warn",
) -> dict[str, Any]:
    consumption_part = _q(costs * share_percent / 100)
    basic_part = costs - consumption_part
    keys = {o.key: (o.unit_number, o.key) for o in occupants}
    signed = negative_costs_mode == "distribute"
    warning = None
    if (consumption_part < 0 or basic_part < 0) and not signed:
        warning = (
            f"{label}: negativer Kostenanteil ({costs}) nicht verteilt; Summe der Einheiten "
            "weicht vom Gesamtbetrag ab. Verteilung negativer Kosten ist nicht freigegeben "
            "(GAI-202, AJ01-01)."
        )
    cons_shares = [Share(keys[o.key], consumption.get(o.key, Decimal(0))) for o in occupants]
    if (consumption_part > 0 or (signed and consumption_part < 0)) and sum(
        (s.weight for s in cons_shares), Decimal(0)
    ) <= 0:
        raise HeatingCalcError(f"{label}: Verbrauchssumme ist null, keine Verteilung möglich.")
    cons_split = (
        distribute(consumption_part, cons_shares)
        if consumption_part > 0 or (signed and consumption_part < 0)
        else {k: Decimal("0.00") for k in keys.values()}
    )
    basic_shares = []
    basic_trace = {}
    for o in occupants:
        tw, method = time_weight(o.start, o.end, degree_days)
        basic_shares.append(Share(keys[o.key], o.area * tw))
        basic_trace[o.key] = {"area": str(o.area), "time_weight": str(tw), "method": method}
    basic_split = (
        distribute(basic_part, basic_shares)
        if basic_part > 0 or (signed and basic_part < 0)
        else {k: Decimal("0.00") for k in keys.values()}
    )
    return {
        "label": label,
        "costs": str(costs),
        "consumption_share_percent": share_percent,
        "consumption_part": str(consumption_part),
        "basic_part": str(basic_part),
        "consumption_values": {k: str(v) for k, v in consumption.items()},
        "basic_weights": basic_trace,
        "warning": warning,
        "per_occupant": {
            o.key: {
                "consumption": str(cons_split[keys[o.key]]),
                "basic": str(basic_split[keys[o.key]]),
                "total": str(cons_split[keys[o.key]] + basic_split[keys[o.key]]),
            }
            for o in occupants
        },
    }


def calculate(
    *,
    period_from: date,
    period_to: date,
    total_costs: Decimal,
    settings: HeatingSettings,
    co2: Co2Input,
    occupants: list[Occupant],
    unit_totals: dict[str, dict[str, Decimal | None]] | None = None,
) -> dict[str, Any]:
    """Draft heating statement. Result sums to ``total_costs`` minus the landlord CO2 share;
    the vacancy shares stay with the owner (A05). Raises HeatingCalcError."""
    if total_costs <= 0:
        raise HeatingCalcError("Gesamtkosten müssen größer null sein.")
    if not (CONSUMPTION_SHARE_MIN <= settings.consumption_share_percent <= CONSUMPTION_SHARE_MAX):
        raise HeatingCalcError("Verbrauchsanteil muss zwischen 50 und 70 Prozent liegen (§ 7).")
    if not occupants:
        raise HeatingCalcError("Keine Nutzer im Zeitraum.")
    if any(o.area <= 0 for o in occupants):
        raise HeatingCalcError("Fläche fehlt oder ist null für mindestens eine Einheit.")
    for o in occupants:
        if overlap(period_from, period_to, o.start, o.end) != (o.start, o.end):
            raise HeatingCalcError(f"Nutzungszeitraum {o.key} liegt außerhalb der Abrechnung.")
    validate_degree_days(settings.degree_days)
    validate_co2_steps(co2.steps)
    period_days = (period_to - period_from).days + 1
    notes: list[str] = []
    co2_result = co2_split(co2, period_days)
    landlord_co2 = Decimal(co2_result.get("landlord") or "0.00")
    if co2_result["status"] == "pruefen":
        notes.append("CO2-Aufteilung im Prüfstatus; Vermieteranteil noch nicht abgezogen (D27).")
    allocable = total_costs - landlord_co2
    heating_costs, hot_water_costs, hot_trace = split_hot_water(allocable, settings)
    totals = unit_totals or {}
    heat_values, heat_est, heat_notes = _resolve_consumption(
        occupants, totals, settings.degree_days, "heating"
    )
    notes.extend(heat_notes)
    components = [
        _component(
            "Heizung",
            heating_costs,
            settings.consumption_share_percent,
            occupants,
            heat_values,
            settings.degree_days,
            settings.negative_costs_mode,
        )
    ]
    hot_est: list[str] = []
    if hot_water_costs > 0:
        hot_values, hot_est, hot_notes = _resolve_consumption(
            occupants, totals, settings.degree_days, "hot_water"
        )
        notes.extend(hot_notes)
        components.append(
            _component(
                "Warmwasser",
                hot_water_costs,
                settings.consumption_share_percent,
                occupants,
                hot_values,
                settings.degree_days,
                settings.negative_costs_mode,
            )
        )
    notes.extend(str(c["warning"]) for c in components if c.get("warning"))
    estimated = sorted(set(heat_est) | set(hot_est))
    if estimated:
        notes.append(
            "Geschätzte oder aufgeteilte Verbräuche vorhanden; Kürzungsrecht nach § 12 "
            "HeizkostenV je Nutzer prüfen (Hinweis, keine Berechnung)."
        )
    user_change_units = {o.unit_id for o in occupants if not o.is_vacancy}
    multi = [
        u
        for u in user_change_units
        if len([o for o in occupants if o.unit_id == u and not o.is_vacancy]) > 1
    ]
    if multi and not settings.degree_days:
        notes.append(
            "Nutzerwechsel ohne Gradtagstabelle: Grundkosten nach Zeitanteil verteilt; "
            "Tabelle pflegen und Ergebnis prüfen (§ 9b, D25)."
        )
    per_occupant: dict[str, dict[str, str]] = {}
    for o in occupants:
        total = sum((Decimal(c["per_occupant"][o.key]["total"]) for c in components), Decimal(0))
        per_occupant[o.key] = {
            "unit_number": o.unit_number,
            "from": o.start.isoformat(),
            "to": o.end.isoformat(),
            "heating": components[0]["per_occupant"][o.key]["total"],
            "hot_water": (
                components[1]["per_occupant"][o.key]["total"] if len(components) > 1 else "0.00"
            ),
            "total": str(total),
            "vacancy": "true" if o.is_vacancy else "false",
            "estimated": "true" if o.key in estimated else "false",
        }
    owner_vacancy = sum(
        (Decimal(v["total"]) for k, v in per_occupant.items() if v["vacancy"] == "true"),
        Decimal("0.00"),
    )
    check = sum((Decimal(v["total"]) for v in per_occupant.values()), Decimal(0))
    if check != allocable:  # pragma: no cover (largest remainder keeps the sum)
        raise HeatingCalcError(f"Summenprüfung fehlgeschlagen: {check} statt {allocable}.")
    return {
        "rule_version": HEATING_RULE_VERSION,
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "total_costs": str(total_costs),
        "co2": co2_result,
        "landlord_co2_share": str(landlord_co2),
        "allocable_costs": str(allocable),
        "hot_water_split": {
            **hot_trace,
            "heating_costs": str(heating_costs),
            "hot_water_costs": str(hot_water_costs),
        },
        "components": components,
        "per_occupant": per_occupant,
        "vacancy_owner_share": str(owner_vacancy),
        "estimated_keys": estimated,
        "notes": notes,
        "status": "entwurf",
    }
