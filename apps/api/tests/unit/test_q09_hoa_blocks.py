"""Package Q09: pure functions of the WEG blocks, expected values by hand.

Reserve "Dach": planned 1.200,00, paid 1.000,00 (bound), withdrawal 300,00, fee 10,00,
interest 25,00 -> planned change 1.200 - 300 - 10 + 25 = 915,00; paid change
1.000 - 300 - 10 + 25 = 715,00. Totals: plan hoa_fee 6.000,00 against previous 5.000,00 gives
1.000,00 or 20,00 %; against a statement with total costs 5.500,00 gives 500,00 or 9,09 %."""

from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from mhvp.hoa import calc, statement_pdf

RID = UUID("01920000-0000-7000-8000-0000000000a1")


def _reserve() -> SimpleNamespace:
    return SimpleNamespace(id=RID, name="Dach", purpose="Dachsanierung", account_id=None)


def test_reserve_positions_with_bound_payments() -> None:
    items = [SimpleNamespace(reserve_id=RID, amount=Decimal("1200.00"))]
    movements = [
        SimpleNamespace(
            reserve_id=RID,
            kind="withdrawal",
            amount=Decimal("300.00"),
            purpose="x",
            document_id=None,
            journal_entry_id=None,
        ),
        SimpleNamespace(
            reserve_id=RID,
            kind="fee",
            amount=Decimal("10.00"),
            purpose="y",
            document_id=None,
            journal_entry_id=None,
        ),
        SimpleNamespace(
            reserve_id=RID,
            kind="interest",
            amount=Decimal("25.00"),
            purpose="z",
            document_id=None,
            journal_entry_id=None,
        ),
    ]
    bound = calc.reserve_positions([_reserve()], items, movements, {str(RID): Decimal("1000.00")})[
        0
    ]
    assert bound["contributions_paid"] == "1000.00"
    assert bound["contributions_paid_bound"] is True
    assert bound["planned_change"] == "915.00"
    assert bound["paid_change"] == "715.00"
    unbound = calc.reserve_positions([_reserve()], items, movements)[0]
    assert unbound["contributions_paid"] == "0.00"
    assert unbound["contributions_paid_bound"] is False


def test_totals_comparison_plan_and_statement() -> None:
    totals = {"hoa_fee": "6000.00", "reserve": "1200.00"}
    against_plan = calc.totals_comparison(
        totals, {"totals": {"hoa_fee": "5000.00", "reserve": "1200.00"}}, "plan"
    )
    rows = {r["component"]: r for r in against_plan["rows"]}
    assert (rows["hoa_fee"]["deviation"], rows["hoa_fee"]["deviation_percent"]) == (
        "1000.00",
        "20.00",
    )
    assert rows["reserve"]["deviation"] == "0.00"
    against_statement = calc.totals_comparison(totals, {"total_costs": "5500.00"}, "statement")
    rows = {r["component"]: r for r in against_statement["rows"]}
    assert (rows["hoa_fee"]["deviation"], rows["hoa_fee"]["deviation_percent"]) == (
        "500.00",
        "9.09",
    )
    assert rows["reserve"]["basis_amount"] is None  # no reserve basis in a statement
    assert rows["reserve"]["deviation"] is None


def test_total_rows_sum_units_and_show_reserves() -> None:
    snapshot = {
        "total_costs": "1200.00",
        "positions": [{"label": "Bewirtschaftung", "basis": "MEA", "amount": "1200.00"}],
        "units": [
            {
                "unit_number": "01",
                "cost_share": "600.00",
                "advances_resolved": "500.00",
                "result": "100.00",
                "advances_paid": "400.00",
                "arrears": "100.00",
            },
            {
                "unit_number": "02",
                "cost_share": "600.00",
                "advances_resolved": "700.00",
                "result": "-100.00",
                "advances_paid": "700.00",
                "arrears": "0.00",
            },
        ],
        "reserve": {
            "opening": "0.00",
            "contributions_resolved": "400.00",
            "contributions_paid": "250.00",
            "withdrawals": "0.00",
            "interest": "0.00",
            "closing": "250.00",
            "bank_balance": "250.00",
            "bank_difference": "0.00",
            "positions": [
                {
                    "name": "Dach",
                    "contributions_planned": "200.00",
                    "contributions_paid": "200.00",
                    "withdrawals": "0.00",
                    "taxes": "0.00",
                    "fees": "0.00",
                    "interest": "0.00",
                }
            ],
        },
    }
    data = statement_pdf.total_rows(snapshot)
    assert data["positions"][-1] == ["Gesamtkosten", "", "1.200,00 EUR"]
    assert data["units"][-1] == [
        "Summe",
        "1.200,00 EUR",
        "1.200,00 EUR",
        "0,00 EUR",
        "1.100,00 EUR",
        "100,00 EUR",
    ]
    assert data["per_reserve"][0][0] == "Dach"
    assert ["Gezahlte Zuführungen (Ist)", "250,00 EUR"] in data["reserve"]
