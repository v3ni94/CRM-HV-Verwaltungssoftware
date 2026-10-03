"""GAJ-303 and GAJ-304 (Welle 23, AM12): half up cent rounding in the accounting and banking
helpers and invariant B06 (order independent cent results, section 7.1).

Expected values are computed by hand (rule 0.1.8): 2,345 EUR rounds half up to 2,35 EUR
(Bankers Rounding would give 2,34 EUR); 0,125 EUR to 0,13 EUR; 100,00 EUR split 1:1:1 gives
33,34 + 33,33 + 33,33."""

from decimal import Decimal
from itertools import permutations
from types import SimpleNamespace

from mhvp.accounting.dunning_letters import fmt_eur
from mhvp.accounting.rent_invoice import _money
from mhvp.banking.fints import _apply_balance
from mhvp.core.money import distribute_cents, round_cents


def test_rent_invoice_money_rounds_half_up() -> None:
    assert _money("2.345") == Decimal("2.35")
    assert _money("0.125") == Decimal("0.13")
    assert _money("-2.345") == Decimal("-2.35")
    assert _money(None) == Decimal("0.00")


def test_dunning_letter_amount_rounds_half_up() -> None:
    assert fmt_eur(Decimal("1234.565")) == "1.234,57 EUR"
    assert fmt_eur(Decimal("0.125")) == "0,13 EUR"
    assert fmt_eur(Decimal("-2.345")) == "-2,35 EUR"


def test_fints_balance_rounds_half_up() -> None:
    target: dict[str, object] = {}
    _apply_balance(target, SimpleNamespace(amount=SimpleNamespace(amount="10.005", currency="EUR")))
    assert target["balance"] == "10.01"


def test_b06_sum_of_cent_results_is_order_independent() -> None:
    """B06: the same posting lines in any order give the same cent totals."""
    lines = [Decimal("12.345"), Decimal("0.005"), Decimal("-3.335"), Decimal("99.994")]
    # Line by line rounded: 12,35 + 0,01 - 3,34 + 99,99 = 109,01.
    totals = {sum((round_cents(x) for x in order), Decimal(0)) for order in permutations(lines)}
    assert totals == {Decimal("109.01")}


def test_b06_distribution_follows_the_weights_not_their_order() -> None:
    """With distinct remainders every share depends only on its own weight; the parts always
    add up exactly to the total."""
    weights = [Decimal("1"), Decimal("2"), Decimal("4")]  # 100,00 / 7: 14,29 / 28,57 / 57,14
    expected = {
        Decimal("1"): Decimal("14.29"),
        Decimal("2"): Decimal("28.57"),
        Decimal("4"): Decimal("57.14"),
    }
    for order in permutations(weights):
        parts = distribute_cents(Decimal("100.00"), list(order))
        assert sum(parts, Decimal(0)) == Decimal("100.00")
        assert dict(zip(order, parts, strict=True)) == expected
    assert distribute_cents(Decimal("100.00"), [1, 1, 1]) == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]
