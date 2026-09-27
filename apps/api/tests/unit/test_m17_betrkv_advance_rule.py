"""M17-01 catalogue and hints, M17-03 advance rule, M17-05 payout block: expected values by
hand (rule 0.1.8). Advance rule: 1.234,56 / 12 = 102,88; with 5 % surcharge
1.234,56 * 105 / 1.200 = 108,024 -> 108,02; 600,00 / 12 = 50,00; 0,00 -> 0,00.
Payout: income 12.000,00, expenses 3.000,00, fee gross 357,00, payouts made 6.000,00
-> operating result 8.643,00, payout 2.643,00."""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.billing import advance_rule, betrkv, owner_statement_pdf


def test_catalogue_has_the_17_positions_and_the_two_exclusions() -> None:
    items = betrkv.catalogue()
    numbers = [i["code"] for i in items if i["code"].isdigit()]
    assert numbers == [str(n) for n in range(1, 18)]
    by_code = {i["code"]: i for i in items}
    assert by_code["17"]["allocability"] == "agreement_only"
    assert by_code["V"]["allocability"] == "no"
    assert by_code["I"]["allocability"] == "no"
    assert all(by_code[str(n)]["allocability"] == "yes" for n in range(1, 17))
    assert by_code["14"]["reference"] == "§ 2 Nr. 14 BetrKV"
    assert by_code["I"]["reference"] == "§ 1 Abs. 2 Nr. 2 BetrKV"
    assert all(i["source"].startswith("R07") for i in items)


def test_suggestion_from_template_reference() -> None:
    assert betrkv.suggest_from_reference("§ 2 Nr. 14 Hauswart") == "14"
    assert betrkv.suggest_from_reference("§ 2 Nr. 3 Entwässerung") == "3"
    assert betrkv.suggest_from_reference("Instandsetzung, keine Betriebskosten") == "I"
    assert (
        betrkv.suggest_from_reference(
            "§ 2 Nr. 4 Heizung bei Zentralheizung, sonst Nr. 12 (zu prüfen)"
        )
        is None
    )
    assert betrkv.suggest_from_reference("Einordnung zu prüfen (Miete/Wartung)") is None
    assert betrkv.suggest_from_reference(None) is None
    assert betrkv.suggest_from_reference("§ 2 Nr. 99") is None


def test_position_hints() -> None:
    none = betrkv.position_hints(
        label="Hausmeister", type_code="14", allocation_category="allocable_other"
    )
    assert none == []
    unassigned = betrkv.position_hints(
        label="Hausmeister", type_code=None, allocation_category=None
    )
    assert [h["code"] for h in unassigned] == ["BETRKV-UNASSIGNED"]
    assert unassigned[0]["level"] == "info"
    conflict = betrkv.position_hints(
        label="Reparatur", type_code="I", allocation_category="allocable_other"
    )
    assert [h["code"] for h in conflict] == ["BETRKV-NOT-ALLOCABLE", "BETRKV-CATEGORY-CONFLICT"]
    assert all(h["level"] == "warning" for h in conflict)
    other = betrkv.position_hints(
        label="Dachrinne", type_code="17", allocation_category="allocable_other"
    )
    assert [h["code"] for h in other] == ["BETRKV-AGREEMENT-ONLY"]


@pytest.mark.parametrize(
    ("costs", "surcharge", "expected"),
    [
        ("1234.56", "0", "102.88"),
        ("1234.56", "5", "108.02"),
        ("600.00", "0", "50.00"),
        ("600.00", "10", "55.00"),
        ("0.00", "10", "0.00"),
        ("-20.00", "0", "0.00"),
        ("100.00", "0", "8.33"),  # 8,333.. rounds down
        ("101.00", "0", "8.42"),  # 8,4166.. rounds up
    ],
)
def test_advance_rule_values(costs: str, surcharge: str, expected: str) -> None:
    assert advance_rule.propose(Decimal(costs), Decimal(surcharge)) == Decimal(expected)


def test_advance_rule_rejects_surcharge_out_of_range() -> None:
    with pytest.raises(ValueError, match="surcharge_percent"):
        advance_rule.propose(Decimal("100"), Decimal("101"))
    with pytest.raises(ValueError, match="surcharge_percent"):
        advance_rule.propose(Decimal("100"), Decimal("-1"))


def test_build_proposals_from_snapshot() -> None:
    inputs = {"period": ["2025-01-01", "2025-12-31"]}
    results = {
        "results": [
            {
                "contract_id": "a",
                "unit_number": "01",
                "from": "2025-01-01",
                "to": "2025-12-31",
                "costs": "1234.56",
            },
            {
                "contract_id": "b",
                "unit_number": "02",
                "from": "2025-01-01",
                "to": "2025-06-30",
                "costs": "500.00",
            },
            {
                "contract_id": "c",
                "unit_number": "03",
                "from": "2025-07-01",
                "to": "2025-12-31",
                "costs": "600.00",
            },
        ]
    }
    rows = advance_rule.build_proposals(inputs, results, Decimal("5"))
    assert [r["unit_number"] for r in rows] == ["01", "03"]  # 02 ended within the period
    assert rows[0]["proposed_amount"] == Decimal("108.02")
    assert rows[0]["note"] is None
    assert rows[1]["proposed_amount"] == Decimal("52.50")
    assert rows[1]["note"] == "Nutzungszeitraum kürzer als der Abrechnungszeitraum."
    text = rows[0]["letter_text"]
    assert "108,02 EUR" in text
    assert "1.234,56 EUR" in text
    assert "Sicherheitsaufschlags von 5 Prozent" in text
    assert advance_rule.PROPOSAL_LABEL in text
    assert "gesondert erklärt" in text
    zero = advance_rule.build_proposals(inputs, results, Decimal("0"))
    assert "Sicherheitsaufschlag" not in zero[0]["letter_text"]
    assert zero[0]["proposed_amount"] == Decimal("102.88")


def test_letter_text_has_no_dashes() -> None:
    text = advance_rule.letter_text(
        previous_costs=Decimal("1200.00"),
        surcharge_percent=Decimal("2.50"),
        proposed_amount=Decimal("102.50"),
        period_from=date(2025, 1, 1),
        period_to=date(2025, 12, 31),
        shorter_period=True,
    )
    assert "\u2013" not in text
    assert "\u2014" not in text
    assert "2.5 Prozent" in text
    assert "01.01.2025 bis 31.12.2025" in text


def _results() -> dict[str, object]:
    return {
        "income": {
            "rent": "10000.00",
            "advances": "2000.00",
            "other": "0.00",
            "total": "12000.00",
            "lines": [],
        },
        "expenses": {
            "lines": [
                {"account_number": "040100", "account_name": "Hausmeister", "amount": "3000.00"}
            ],
            "total": "3000.00",
        },
        "admin_fee": {"net": "300.00", "vat": "57.00", "gross": "357.00", "lines": []},
        "payouts": {"lines": [], "total": "6000.00"},
        "liquidity": {"free": "1500.00"},
    }


def test_owner_statement_payout_block_by_hand() -> None:
    block = owner_statement_pdf.settlement(_results())
    assert block["operating_result"] == "8643.00"
    assert block["payout_amount"] == "2643.00"
    assert block["kind"] == "auszahlung"
    results = _results()
    results["payouts"] = {"lines": [], "total": "9000.00"}
    assert owner_statement_pdf.settlement(results)["kind"] == "nachschuss"
    assert owner_statement_pdf.settlement(results)["payout_amount"] == "-357.00"
