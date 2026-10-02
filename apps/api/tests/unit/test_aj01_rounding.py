"""AJ01 (GAI-101, 201, 202, 213, 214, 613, 614): sign symmetric distribution, exact sums,
half up cent rounding. Expected values are computed by hand (rule 0.1.8)."""

import random
from datetime import date
from decimal import Decimal

import pytest

from mhvp.billing import heating_calc as hc
from mhvp.billing.calc import Share, distribute
from mhvp.billing.owner_statement import _d
from mhvp.hoa.calc import monthly_rates
from mhvp.hoa.reserve_split import split_by_plan_ratio

D = Decimal


def _shares(*weights: str) -> list[Share]:
    return [Share((f"{i:02d}", f"p{i}"), D(w)) for i, w in enumerate(weights, 1)]


def test_d08_positive_unchanged() -> None:
    assert list(distribute(D("100.00"), _shares("1", "1", "1")).values()) == [
        D("33.34"),
        D("33.33"),
        D("33.33"),
    ]


def test_negative_total_is_mirror_of_positive() -> None:
    # -100,00 / 3: -33,34 first (stable key), sum exactly -100,00 (previously -99,97).
    res = distribute(D("-100.00"), _shares("1", "1", "1"))
    assert list(res.values()) == [D("-33.34"), D("-33.33"), D("-33.33")]
    assert sum(res.values()) == D("-100.00")


def test_negative_rest_goes_to_largest_remainder() -> None:
    # -10,00 at 1:2: exact -3,333.. and -6,666..; rest cent to the larger remainder (02).
    res = distribute(D("-10.00"), _shares("1", "2"))
    assert res == {("01", "p1"): D("-3.33"), ("02", "p2"): D("-6.67")}


def test_property_sum_exact_random() -> None:
    rng = random.Random(4711)  # noqa: S311
    for _ in range(2000):
        total = D(rng.randint(-(10**7), 10**7)) / 100
        shares = _shares(*[str(D(rng.randint(1, 10**6)) / 1000) for _ in range(rng.randint(1, 9))])
        res = distribute(total, shares)
        assert sum(res.values(), D(0)) == total
        assert all(v == v.quantize(D("0.01")) for v in res.values())
        if total:
            assert all(v * total >= 0 for v in res.values())


def test_reserve_split_property_sum_exact() -> None:
    rng = random.Random(815)  # noqa: S311
    for _ in range(2000):
        amount = D(rng.randint(-(10**6), 10**6)) / 100
        planned = {f"r{i}": D(rng.randint(0, 10**6)) / 100 for i in range(rng.randint(1, 6))}
        parts = split_by_plan_ratio(amount, planned)
        if parts:
            assert sum(parts.values(), D(0)) == amount


def test_reserve_split_half_up() -> None:
    # 0,05 at 1:1 exact 0,025 each: half up 0,03 + 0,03 = 0,06, rest -0,01 to r1.
    assert split_by_plan_ratio(D("0.05"), {"r1": D(1), "r2": D(1)}) == {
        "r1": D("0.02"),
        "r2": D("0.03"),
    }


def test_owner_statement_rounds_half_up() -> None:
    assert _d("0.125") == D("0.13")
    assert _d("-0.125") == D("-0.13")


@pytest.mark.parametrize(
    ("annual", "mode", "expected"),
    [
        ("100.00", "report_only", ["8.33"] * 12),
        ("100.00", "last_month", ["8.33"] * 11 + ["8.37"]),
        ("100.00", "first_month", ["8.37"] + ["8.33"] * 11),
        ("-100.00", "last_month", ["-8.33"] * 11 + ["-8.37"]),
    ],
)
def test_monthly_rates(annual: str, mode: str, expected: list[str]) -> None:
    rates = monthly_rates(D(annual), mode)
    assert rates == [D(x) for x in expected]
    if mode != "report_only":
        assert sum(rates) == D(annual)


def test_monthly_rates_unknown_mode() -> None:
    with pytest.raises(ValueError, match="Restcentregel"):
        monthly_rates(D("1.00"), "x")


def _occs() -> list[hc.Occupant]:
    y0, y1 = date(2025, 1, 1), date(2025, 12, 31)
    return [
        hc.Occupant("contract:a", "u01", "01", y0, y1, D(50)),
        hc.Occupant("contract:b", "u02", "02", y0, y1, D(50)),
    ]


def test_negative_component_legacy_warns() -> None:
    res = hc._component(
        "Heizung", D("-100.00"), 70, _occs(), {"contract:a": D(1), "contract:b": D(3)}, {}
    )
    assert res["warning"]
    assert "GAI-202" in res["warning"]
    assert all(v["total"] == "0.00" for v in res["per_occupant"].values())


def test_negative_component_distribute_switch() -> None:
    # -100,00: consumption 70 % = -70,00 at 1:3 -> -17,50 / -52,50; basic -30,00 at 50:50.
    res = hc._component(
        "Heizung",
        D("-100.00"),
        70,
        _occs(),
        {"contract:a": D(1), "contract:b": D(3)},
        {},
        "distribute",
    )
    assert res["warning"] is None
    assert res["per_occupant"]["contract:a"]["total"] == "-32.50"
    assert res["per_occupant"]["contract:b"]["total"] == "-67.50"
