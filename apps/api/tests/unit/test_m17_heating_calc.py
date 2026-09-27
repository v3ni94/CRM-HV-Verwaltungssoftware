"""M17-02 draft heating statement, expected values computed by hand (annex D cases D25 to D27
carry no figures; the examples here are DRAFT model cases, not accepted rules).

Case A (D25): 2025, units 01 and 02 with 50 m2 each. Unit 01 one tenant all year, 1.000
consumption units. Unit 02: tenant B 01.01. to 31.03. (90 days) 600 units from an
intermediate reading, tenant C 01.04. to 31.12. (275 days) 400 units. Costs 3.000,00 EUR,
70/30, no hot water, CO2 declared not applicable. Consumption part 2.100,00: A 1.050,00,
B 630,00, C 420,00. Basic part 900,00 by area x days (18.250 / 4.500 / 13.750 of 36.500):
A 450,00, B 110,9589 -> 110,96 (rest cent), C 339,0410 -> 339,04. Totals A 1.500,00,
B 740,96, C 759,04. With the draft degree day table (Jan 170, Feb 150, Mar 130, Apr 80, May 40,
Jun 10, Jul 0, Aug 0, Sep 30, Oct 90, Nov 130, Dec 170 promille) the basic weights are
50.000 / 22.500 / 27.500: A 450,00, B 202,50, C 247,50 -> B 832,50, C 667,50.

Case B (D10 style CO2): costs 3.000,00 including CO2 costs 100,00; residential, 1.200 kg on
100 m2 = 12 kg/m2 -> tenant 90 %, landlord 10,00; allocable 2.990,00. Hot water flat 20 %:
598,00 hot water, 2.392,00 heating. Two units 50 m2 all year, heating 600/400, hot water
30/10. Heating: consumption 1.674,40 (1.004,64 / 669,76), basic 717,60 (358,80 each).
Hot water: consumption 418,60 (313,95 / 104,65), basic 179,40 (89,70 each).
Totals A 1.767,09, B 1.222,91, sum 2.990,00.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from mhvp.billing import heating_calc as hc

D = Decimal
Y0, Y1 = date(2025, 1, 1), date(2025, 12, 31)
DEGREE_DAYS = {
    1: D(170), 2: D(150), 3: D(130), 4: D(80), 5: D(40), 6: D(10),
    7: D(0), 8: D(0), 9: D(30), 10: D(90), 11: D(130), 12: D(170),
}  # fmt: skip
STEPS = tuple((D(b), p) for b, p in [(0, 100), (12, 90), (17, 80), (22, 70), (27, 60)])
NA = hc.Co2Input(mode="not_applicable", reason="Testfall ohne CO2-Angaben")


def _occ(
    key: str, unit: str, start: date, end: date, heat: str, hot: str | None = None
) -> hc.Occupant:
    return hc.Occupant(
        key=key,
        unit_id=f"u{unit}",
        unit_number=unit,
        start=start,
        end=end,
        area=D(50),
        heating=D(heat),
        hot_water=None if hot is None else D(hot),
        heating_kind="actual",
        hot_water_kind="missing" if hot is None else "actual",
    )


CASE_A = [
    _occ("contract:a", "01", Y0, Y1, "1000"),
    _occ("contract:b", "02", Y0, date(2025, 3, 31), "600"),
    _occ("contract:c", "02", date(2025, 4, 1), Y1, "400"),
]


def _run(occupants: list[hc.Occupant], **kw: Any) -> dict[str, Any]:
    settings = kw.pop("settings", hc.HeatingSettings(hot_water_flat_percent=D(0)))
    co2 = kw.pop("co2", NA)
    return hc.calculate(
        period_from=Y0, period_to=Y1, total_costs=D("3000.00"),
        settings=settings, co2=co2, occupants=occupants, **kw,
    )  # fmt: skip


def test_d25_user_change_time_share_and_notice() -> None:
    r = _run(CASE_A)
    per = r["per_occupant"]
    assert {k: v["total"] for k, v in per.items()} == {
        "contract:a": "1500.00",
        "contract:b": "740.96",
        "contract:c": "759.04",
    }
    assert r["allocable_costs"] == "3000.00"
    assert any("Gradtagstabelle" in n for n in r["notes"])
    assert r["co2"]["status"] == "nicht_anwendbar"


def test_d25_user_change_degree_days() -> None:
    s = hc.HeatingSettings(hot_water_flat_percent=D(0), degree_days=DEGREE_DAYS)
    r = _run(CASE_A, settings=s)
    per = r["per_occupant"]
    assert per["contract:b"]["total"] == "832.50"
    assert per["contract:c"]["total"] == "667.50"
    assert per["contract:a"]["total"] == "1500.00"
    assert not any("Gradtagstabelle" in n for n in r["notes"])


def test_d25_unit_total_without_intermediate_reading_is_split_and_flagged() -> None:
    occ = [
        CASE_A[0],
        hc.Occupant("contract:b", "u02", "02", Y0, date(2025, 3, 31), D(50)),
        hc.Occupant("contract:c", "u02", "02", date(2025, 4, 1), Y1, D(50)),
    ]
    s = hc.HeatingSettings(hot_water_flat_percent=D(0), degree_days=DEGREE_DAYS)
    r = _run(occ, settings=s, unit_totals={"u02": {"heating": D(1000), "hot_water": None}})
    comp = r["components"][0]
    assert comp["consumption_values"]["contract:b"] == "450"  # 1000 x 450 / 1000
    assert comp["consumption_values"]["contract:c"] == "550"
    assert r["estimated_keys"] == ["contract:b", "contract:c"]
    assert any("§ 12" in n for n in r["notes"])


def test_missing_consumption_refuses() -> None:
    occ = [CASE_A[0], hc.Occupant("contract:b", "u02", "02", Y0, Y1, D(50))]
    with pytest.raises(hc.HeatingCalcError, match="Verbrauch fehlt"):
        _run(occ)


def test_share_outside_50_70_refuses() -> None:
    with pytest.raises(hc.HeatingCalcError, match="50 und 70"):
        _run(
            CASE_A,
            settings=hc.HeatingSettings(consumption_share_percent=40, hot_water_flat_percent=D(0)),
        )


def test_co2_residential_with_hot_water() -> None:
    occ = [
        _occ("contract:a", "01", Y0, Y1, "600", "30"),
        _occ("contract:b", "02", Y0, Y1, "400", "10"),
    ]
    co2 = hc.Co2Input(
        building_kind="residential", costs=D("100.00"), emissions_kg=D(1200),
        reference_area_m2=D(100), steps=STEPS, steps_source="Test",
    )  # fmt: skip
    r = _run(occ, settings=hc.HeatingSettings(hot_water_flat_percent=D(20)), co2=co2)
    assert r["co2"]["status"] == "berechnet"
    assert r["co2"]["tenant_percent"] == 90
    assert r["landlord_co2_share"] == "10.00"
    assert r["allocable_costs"] == "2990.00"
    assert r["hot_water_split"]["hot_water_costs"] == "598.00"
    heat, hot = r["components"]
    assert heat["per_occupant"]["contract:a"] == {
        "consumption": "1004.64",
        "basic": "358.80",
        "total": "1363.44",
    }
    assert hot["per_occupant"]["contract:b"] == {
        "consumption": "104.65",
        "basic": "89.70",
        "total": "194.35",
    }
    per = r["per_occupant"]
    assert per["contract:a"]["total"] == "1767.09"
    assert per["contract:b"]["total"] == "1222.91"


def test_d27_unresolved_co2_stays_review_without_zero() -> None:
    occ = [_occ("contract:a", "01", Y0, Y1, "600")]
    missing = hc.Co2Input(building_kind="residential", costs=D("100.00"), steps=STEPS)
    r = _run(occ, co2=missing)
    assert r["co2"]["status"] == "pruefen"
    assert r["co2"]["missing"] == ["emissions_kg", "reference_area_m2"]
    assert r["landlord_co2_share"] == "0.00"
    assert r["allocable_costs"] == "3000.00"
    assert any("Prüfstatus" in n for n in r["notes"])
    other = hc.Co2Input(
        building_kind="self_supply",
        costs=D("100.00"),
        emissions_kg=D(1),
        reference_area_m2=D(1),
        steps=STEPS,
    )
    assert _run(occ, co2=other)["co2"]["status"] == "pruefen"
    empty = hc.Co2Input(
        building_kind="residential", costs=D("100.00"), emissions_kg=D(1), reference_area_m2=D(1)
    )
    assert _run(occ, co2=empty)["co2"]["status"] == "pruefen"
    with pytest.raises(hc.HeatingCalcError, match="Begründung"):
        _run(occ, co2=hc.Co2Input(mode="not_applicable"))


def test_hot_water_formula_and_measured() -> None:
    s = hc.HeatingSettings(
        hot_water_method="formula", hot_water_volume_m3=D(100), hot_water_temperature_c=D(60),
        total_energy_kwh=D(50000),
    )  # fmt: skip
    heating, hot, trace = hc.split_hot_water(D("3000.00"), s)
    assert trace["hot_water_energy_kwh"] == "12500.0"  # 2,5 x 100 x 50
    assert (heating, hot) == (D("2250.00"), D("750.00"))
    m = hc.HeatingSettings(
        hot_water_method="measured", heating_energy_kwh=D(30000), hot_water_energy_kwh=D(10000)
    )
    assert hc.split_hot_water(D("3000.00"), m)[1] == D("750.00")


def test_tables_validation() -> None:
    with pytest.raises(hc.HeatingCalcError, match="1000"):
        hc.validate_degree_days({m: D(100) for m in range(1, 13)})
    with pytest.raises(hc.HeatingCalcError, match="Monate"):
        hc.validate_degree_days({1: D(1000)})
    with pytest.raises(hc.HeatingCalcError, match="bei 0"):
        hc.validate_co2_steps(((D(12), 90),))
    assert hc.time_weight(date(2025, 1, 15), date(2025, 2, 14), DEGREE_DAYS) == (
        D(170) * 17 / 31 + D(150) * 14 / 28,
        "degree_days",
    )
