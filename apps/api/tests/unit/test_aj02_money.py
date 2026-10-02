"""AJ02: central cent rounding, exact distribution, strict parsing, lossless JSON numbers.

Expected values are computed by hand (rule 0.1.8)."""

import json
import random
from decimal import Decimal

import pytest

from mhvp.contracts.services import check_amounts
from mhvp.core.money import (
    distribute_cents,
    json_number,
    parse_decimal_strict,
    round_cents,
)
from mhvp.core.problems import ProblemError
from mhvp.hoa.reserve_split import split_by_plan_ratio
from mhvp.imports.fields import parse_decimal
from mhvp.integrations.lexoffice_ext.payloads import json_ready, quantity

D = Decimal


def test_round_cents_half_up() -> None:
    # GAI-203: 11,50 EUR plus 15 Prozent = 13,225 -> 13,23 (half even would give 13,22).
    assert round_cents(D("11.50") * (1 + D("15") / 100)) == D("13.23")
    assert round_cents(D("-13.225")) == D("-13.23")
    assert round_cents(D("0.005")) == D("0.01")
    assert round_cents(D("2.675")) == D("2.68")
    assert quantity(D("0.00005")) == D("0.0001")


def test_distribute_hand_examples() -> None:
    assert distribute_cents(D("100.00"), [1, 1, 1]) == [D("33.34"), D("33.33"), D("33.33")]
    assert distribute_cents(D("-100.00"), [1, 1, 1]) == [D("-33.34"), D("-33.33"), D("-33.33")]
    assert distribute_cents(D("0.00"), [1, 2]) == [D("0.00"), D("0.00")]
    assert distribute_cents(D("10.00"), [D("0"), D("3")]) == [D("0.00"), D("10.00")]
    assert distribute_cents(D("0.01"), [1, 1]) == [D("0.01"), D("0.00")]


@pytest.mark.parametrize("bad", [[], [0, 0], [1, -1]])
def test_distribute_rejects_bad_weights(bad: list[int]) -> None:
    with pytest.raises(ValueError, match="weights"):
        distribute_cents(D("1.00"), bad)


def test_distribute_rejects_sub_cent_total() -> None:
    with pytest.raises(ValueError, match="whole cent"):
        distribute_cents(D("1.005"), [1])


def test_distribute_sum_property() -> None:
    """GAI-215: sum of the parts equals the total for positive, negative and zero totals."""
    rng = random.Random(4711)  # noqa: S311 (deterministic test data)
    for _ in range(500):
        total = D(rng.randint(-10_000_000, 10_000_000)) / 100
        weights = [D(rng.randint(0, 50_000)) / 1000 for _ in range(rng.randint(1, 12))]
        if not any(weights):
            weights[0] = D(1)
        parts = distribute_cents(total, weights)
        assert sum(parts, D(0)) == total
        assert all((p <= 0) if total < 0 else (p >= 0) for p in parts)
        assert all(p == p.quantize(D("0.01")) for p in parts)


def test_reserve_split_sum_negative_and_zero() -> None:
    """GAI-215: reserve split keeps the sum; zero amount gives no proposal."""
    rng = random.Random(815)  # noqa: S311 (deterministic test data)
    for _ in range(200):
        amount = D(rng.randint(1, 1_000_000)) / 100
        plan = {f"r{i}": D(rng.randint(1, 500_000)) / 100 for i in range(rng.randint(1, 6))}
        assert sum(split_by_plan_ratio(amount, plan).values(), D(0)) == amount
    assert split_by_plan_ratio(D("0.00"), {"a": D("1.00")}) == {}


def test_parse_strict() -> None:
    assert parse_decimal_strict("1.234,56") == D("1234.56")
    assert parse_decimal_strict("1.234.567") == D("1234567")
    assert parse_decimal_strict("12,500") == D("12.500")
    assert parse_decimal_strict("71.35") == D("71.35")
    assert parse_decimal_strict("650,00 EUR") == D("650.00")
    assert parse_decimal_strict("1234") == D("1234")
    # GAI-206: Excel float residue is removed (eight decimals, half up).
    assert parse_decimal_strict(0.1 + 0.2) == D("0.3")
    assert parse_decimal_strict(71.35) == D("71.35")
    assert parse_decimal(1 / 3) == D("0.33333333")


@pytest.mark.parametrize("bad", ["12.500", "1.234", "-1.000", "NaN", "1E+3", "abc", "", True])
def test_parse_strict_rejects(bad: object) -> None:
    # GAI-205: "12.500" may be 12500 or 12.5; it is rejected instead of guessed.
    with pytest.raises(ValueError, match="Zahl"):
        parse_decimal(bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), D("NaN")])
def test_parse_strict_rejects_non_finite(bad: object) -> None:
    with pytest.raises(ValueError, match="nicht lesbar"):
        parse_decimal_strict(bad)


def test_json_number_lossless() -> None:
    assert json_number(D("12.50")) == 12.5
    assert json_number(D("450000.00")) == 450000
    assert isinstance(json_number(D("3")), int)
    with pytest.raises(ValueError, match="exactly"):
        json_number(D("0.12345678901234567890"))
    body = json_ready({"a": [D("19.99"), D("1234567.89")]})
    assert json.loads(json.dumps(body)) == {"a": [19.99, 1234567.89]}


def test_check_amounts_half_up_and_tolerance() -> None:
    # 10,25 net at 7 % = 10,9675 -> 10,97 half up.
    check_amounts("rent", D("10.25"), D("7"), D("10.97"))
    check_amounts("rent", D("10.25"), D("7"), D("10.96"))  # 1 cent tolerance (AJ02-01)
    with pytest.raises(ProblemError):
        check_amounts("rent", D("10.25"), D("7"), D("10.96"), tolerance=D("0"))
    with pytest.raises(ProblemError):
        check_amounts("rent", D("10.25"), D("7"), D("10.99"))
