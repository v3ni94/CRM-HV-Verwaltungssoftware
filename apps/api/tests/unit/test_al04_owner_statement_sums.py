"""AL04 (GAI-215 rest of AK01): sum invariants of the owner statement ``build_results``.

Predefined cent amounts with odd values; every block total must equal the sum of its lines,
income must equal rent plus advances plus other, the fee gross must equal net plus VAT, free
liquidity and the operating result must follow their documented formulas exactly. One fixed
case is computed by hand (rule 0.1.8):

rent 333,33 + 0,01; advances 166,67; other 0,99 -> income 501,00. Expenses 100,01 + 99,99 =
200,00. Fee 16,81 net, 3,19 VAT monthly over 01.04.2025 to 30.06.2025 -> 3 intervals ->
50,43 / 9,57 / 60,00. Operating result 501,00 - 200,00 - 60,00 = 241,00. Bank 1.000,01
free + 700,00 deposit, deposits held 700,00, payables 0,01 -> free 1.700,01 - 700,00 - 0,01 =
1.000,00.
"""

from decimal import Decimal
from typing import Any

import pytest

from mhvp.billing.owner_statement import build_results

D = Decimal


def _inputs(
    rents: list[str],
    advances: list[str],
    others: list[str],
    expenses: list[str],
    fee: tuple[str, str] | None,
    bank_free: list[str],
    deposit: str,
    payables: list[str],
    receivables: list[str],
) -> dict[str, Any]:
    income = (
        [
            {"account_number": f"0600{i}", "payment_type_codes": ["rent"], "amount": a}
            for i, a in enumerate(rents)
        ]
        + [
            {
                "account_number": f"0610{i}",
                "payment_type_codes": ["operating_cost_advance"],
                "amount": a,
            }
            for i, a in enumerate(advances)
        ]
        + [
            {"account_number": f"0281{i}", "payment_type_codes": [], "amount": a}
            for i, a in enumerate(others)
        ]
    )
    return {
        "period": ["2025-04-01", "2025-06-30"],
        "kind": "rental_owner",
        "owner_party_id": "al04-p",
        "income": income,
        "expenses": [{"account_number": f"0401{i}", "amount": a} for i, a in enumerate(expenses)],
        "admin_fee": (
            []
            if fee is None
            else [
                {
                    "setting_id": "al04-f",
                    "interval": "monthly",
                    "start_date": "2025-01-01",
                    "end_date": None,
                    "unit_counts": {},
                    "net": fee[0],
                    "vat_percent": "19",
                    "vat": fee[1],
                    "gross": str(D(fee[0]) + D(fee[1])),
                }
            ]
        ),
        "payouts": [{"account_number": "070000", "amount": "12.34"}],
        "open_receivables": [
            {"contract_id": "c", "component": "rent", "remaining": r} for r in receivables
        ],
        "open_payables": [{"account_number": "070100", "remaining": p} for p in payables],
        "bank": [
            {"number": f"0012{i}", "kind": "free", "balance": b} for i, b in enumerate(bank_free)
        ]
        + [{"number": "001299", "kind": "deposit", "balance": deposit}],
        "deposits": [{"deposit_id": "d", "amount_due": deposit, "balance": deposit}],
        "draft_entries_in_period": 0,
    }


def _sum(values: list[str]) -> Decimal:
    return sum((D(v) for v in values), D("0.00"))


CASES = [
    (
        ["333.33", "0.01"],
        ["166.67"],
        ["0.99"],
        ["100.01", "99.99"],
        ("16.81", "3.19"),
        ["1000.01"],
        "700.00",
        ["0.01"],
        ["0.01", "999.99"],
    ),
    (["0.01"] * 7, ["0.03", "0.07"], [], ["0.01"] * 3, ("0.01", "0.00"), ["0.00"], "0.00", [], []),
    (
        ["1234.56", "7890.12"],
        ["345.67"],
        ["-0.01"],
        ["9999.99"],
        None,
        ["-50.00", "75.55"],
        "1500.00",
        ["40.00", "0.05"],
        ["1.10"],
    ),
    (
        ["833.34", "833.33", "833.33"],
        ["0.00"],
        ["12.5"],
        ["33.333"],
        ("29.99", "5.70"),
        ["2500.00"],
        "3000.00",
        ["99.99"],
        ["0.50", "0.50"],
    ),
]


@pytest.mark.parametrize("case", CASES)
def test_owner_statement_blocks_add_up(case: tuple[Any, ...]) -> None:
    rents, advances, others, _exp, _fee, _bank, deposit, payables, receivables = case
    results, findings = build_results(_inputs(*case))
    assert not [f for f in findings if f["level"] == "error"], findings

    inc = results["income"]
    assert D(inc["rent"]) == _sum(rents)
    assert D(inc["advances"]) == _sum(advances)
    assert D(inc["other"]) == _sum(others)
    assert D(inc["total"]) == D(inc["rent"]) + D(inc["advances"]) + D(inc["other"])
    assert D(inc["total"]) == _sum([line["amount"] for line in inc["lines"]])

    exp = results["expenses"]
    assert D(exp["total"]) == _sum([line["amount"] for line in exp["lines"]])

    fee_block = results["admin_fee"]
    assert D(fee_block["gross"]) == D(fee_block["net"]) + D(fee_block["vat"])
    assert D(fee_block["gross"]) == _sum([line["gross"] for line in fee_block["lines"]])
    for line in fee_block["lines"]:
        assert line["intervals"] == 3
        assert D(line["net"]) == D(line["net_per_interval"]) * 3

    assert D(results["open_receivables"]["total"]) == _sum(receivables)
    assert D(results["open_payables"]["total"]) == _sum(payables)

    liq = results["liquidity"]
    assert D(liq["bank_total"]) == _sum([a["balance"] for a in liq["accounts"]])
    assert D(liq["free"]) == D(liq["bank_total"]) - D(liq["deposits_held"]) - D(
        liq["open_payables"]
    )
    op = results["operating_result"]
    assert D(op["result"]) == D(op["income"]) - D(op["expenses"]) - D(op["admin_fee_gross"])
    assert op["income"] == inc["total"]
    assert op["expenses"] == exp["total"]
    assert op["admin_fee_gross"] == fee_block["gross"]
    assert results["deposits"]["difference"] == "0.00"
    assert D(results["deposits"]["held"]) == D(deposit)
    # Every amount carries exactly two places (Decimal string, no float).
    for value in (inc["total"], exp["total"], fee_block["gross"], liq["free"], op["result"]):
        assert D(value).as_tuple().exponent == -2


def test_owner_statement_fixed_case_by_hand() -> None:
    results, _ = build_results(_inputs(*CASES[0]))
    assert results["income"]["total"] == "501.00"
    assert results["expenses"]["total"] == "200.00"
    fee = results["admin_fee"]
    assert (fee["net"], fee["vat"], fee["gross"]) == ("50.43", "9.57", "60.00")
    assert results["operating_result"]["result"] == "241.00"
    assert results["liquidity"]["free"] == "1000.00"


def test_owner_statement_sub_cent_inputs_round_half_up() -> None:
    """Inputs with three places are rounded per line (ROUND_HALF_UP) before summing."""
    results, _ = build_results(_inputs(*CASES[3]))
    assert results["expenses"]["lines"][0]["amount"] == "33.33"
    assert results["income"]["other"] == "12.50"
    case = list(CASES[3])
    case[3] = ["0.005", "0.005"]
    results, _ = build_results(_inputs(*case))
    assert results["expenses"]["total"] == "0.02"
