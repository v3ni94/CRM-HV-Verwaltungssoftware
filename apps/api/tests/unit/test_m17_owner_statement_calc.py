"""A06 owner statement, pure calculation with hand computed expected values (rule 0.1.8).

Rental: rent 1.000,00 and advances 200,00 on separate accounts, other revenue 10,00;
expenses 150,00 + 50,00; fee setting 25,00 net per month plus 19 % (4,75) for 2025 -> 12
intervals -> 300,00 / 57,00 / 357,00; payouts 300,00; open receivables 500,00 + 100,00;
payables 40,00; deposits 1.500,00 held, segregated bank 1.500,00; bank 1.650,00 + 200,00 ->
free = 1.850,00 - 1.500,00 - 40,00 = 310,00; operating result 1.210,00 - 200,00 - 357,00 =
653,00.
SEV: WEG units cost share 1.500,00 + 800,00, Hausgeld resolved 1.200,00 + 700,00 -> result
300,00 + 100,00 = 400,00; tenant allocable 900,00 -> owner burden 2.300,00 - 900,00 = 1.400,00.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from mhvp.billing.owner_statement import (
    RULE_VERSION,
    build_results,
    digest,
    fee_intervals,
)


def _inputs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "period": ["2025-01-01", "2025-12-31"],
        "kind": "rental_owner",
        "owner_party_id": "p1",
        "income": [
            {"account_number": "060000", "payment_type_codes": ["rent"], "amount": "1000.00"},
            {
                "account_number": "061000",
                "payment_type_codes": ["operating_cost_advance", "heating_cost_advance"],
                "amount": "200.00",
            },
            {"account_number": "028100", "payment_type_codes": [], "amount": "10.00"},
        ],
        "expenses": [
            {"account_number": "040100", "amount": "150.00"},
            {"account_number": "043000", "amount": "50.00"},
        ],
        "admin_fee": [
            {
                "setting_id": "f1",
                "interval": "monthly",
                "start_date": "2024-01-01",
                "end_date": None,
                "unit_counts": {"apartment": 1},
                "net": "25.00",
                "vat_percent": "19",
                "vat": "4.75",
                "gross": "29.75",
            }
        ],
        "payouts": [{"account_number": "070000", "amount": "300.00"}],
        "open_receivables": [
            {"contract_id": "c1", "component": "rent", "remaining": "500.00"},
            {"contract_id": "c1", "component": "operating_cost_advance", "remaining": "100.00"},
        ],
        "open_payables": [{"account_number": "070100", "remaining": "40.00"}],
        "bank": [
            {"number": "001210", "kind": "free", "balance": "200.00"},
            {"number": "001220", "kind": "deposit", "balance": "1500.00"},
            {"number": "001300", "kind": "free", "balance": "150.00"},
        ],
        "deposits": [{"deposit_id": "d1", "amount_due": "1500.00", "balance": "1500.00"}],
        "draft_entries_in_period": 0,
    }
    base.update(overrides)
    return base


def test_rental_blocks_by_hand() -> None:
    results, findings = build_results(_inputs())
    assert results["income"] == {
        **results["income"],
        "rent": "1000.00",
        "advances": "200.00",
        "other": "10.00",
        "total": "1210.00",
    }
    assert results["expenses"]["total"] == "200.00"
    assert (results["admin_fee"]["net"], results["admin_fee"]["vat"]) == ("300.00", "57.00")
    assert results["admin_fee"]["gross"] == "357.00"
    assert results["admin_fee"]["lines"][0]["intervals"] == 12
    assert results["payouts"]["total"] == "300.00"
    assert results["open_receivables"]["total"] == "600.00"
    assert results["open_payables"]["total"] == "40.00"
    assert results["deposits"]["held"] == "1500.00"
    assert results["deposits"]["bank_segregated"] == "1500.00"
    assert results["liquidity"]["bank_total"] == "1850.00"
    assert results["liquidity"]["free"] == "310.00"
    assert results["operating_result"]["result"] == "653.00"
    assert "sev_reconciliation" not in results
    assert [f["code"] for f in findings] == []


def test_findings_for_mixed_account_deposit_difference_and_drafts() -> None:
    inputs = _inputs(
        income=[
            {
                "account_number": "060000",
                "payment_type_codes": ["rent", "operating_cost_advance"],
                "amount": "1200.00",
            }
        ],
        bank=[{"number": "001210", "kind": "free", "balance": "1850.00"}],
        draft_entries_in_period=2,
        admin_fee=[],
        payouts=[],
    )
    results, findings = build_results(inputs)
    codes = {f["code"]: f["level"] for f in findings}
    assert codes == {
        "INCOME-MIXED-ACCOUNT": "warning",
        "FEE-NOT-CONFIGURED": "info",
        "OWNER-ACCOUNT-MISSING": "info",
        "DEPOSIT-BANK-DIFFERENCE": "warning",
        "DRAFT-ENTRIES": "info",
    }
    assert results["income"]["other"] == "1200.00"  # never silently counted as rent
    assert results["income"]["rent"] == "0.00"
    assert results["liquidity"]["free"] == "310.00"  # deposits still deducted (never liquidity)


def test_owner_party_missing_and_unknown_fee_interval() -> None:
    fee: dict[str, Any] = dict(_inputs()["admin_fee"][0], interval="weekly")
    _, findings = build_results(_inputs(owner_party_id=None, admin_fee=[fee]))
    codes = {f["code"] for f in findings}
    assert {"OWNER-PARTY-MISSING", "FEE-INTERVAL-UNKNOWN"} <= codes


def test_fee_intervals() -> None:
    setting: dict[str, Any] = {
        "interval": "monthly",
        "start_date": "2025-03-15",
        "end_date": "2025-08-31",
    }
    assert fee_intervals(date(2025, 1, 1), date(2025, 12, 31), setting) == 5  # 04 to 08
    setting = {"interval": "quarterly", "start_date": "2020-01-01", "end_date": None}
    assert fee_intervals(date(2025, 1, 1), date(2025, 12, 31), setting) == 4
    setting = {"interval": "yearly", "start_date": "2025-06-01", "end_date": None}
    assert fee_intervals(date(2025, 1, 1), date(2025, 12, 31), setting) == 0
    assert fee_intervals(date(2025, 1, 1), date(2025, 12, 31), {"interval": "x"}) is None


def test_sev_reconciliation_by_hand() -> None:
    inputs = _inputs(
        kind="sev_owner",
        hoa_statement={
            "statement_id": "h1",
            "year": 2025,
            "version": 1,
            "status": "calculated",
            "units": [
                {
                    "unit_id": "u1",
                    "unit_number": "01",
                    "cost_share": "1500.00",
                    "advances_resolved": "1200.00",
                    "advances_paid": "1200.00",
                    "result": "300.00",
                    "arrears": "0.00",
                },
                {
                    "unit_id": "u2",
                    "unit_number": "02",
                    "cost_share": "800.00",
                    "advances_resolved": "700.00",
                    "advances_paid": "600.00",
                    "result": "100.00",
                    "arrears": "100.00",
                },
            ],
        },
        operating_cost_statements=[
            {
                "statement_id": "s1",
                "version": 1,
                "status": "calculated",
                "tenant_costs": "900.00",
                "vacancy_owner_share": "0.00",
                "advances_due": "100.00",
            }
        ],
    )
    results, findings = build_results(inputs)
    sev = results["sev_reconciliation"]
    assert sev["hoa_cost_share"] == "2300.00"
    assert sev["hausgeld_resolved"] == "1900.00"
    assert sev["hausgeld_paid"] == "1800.00"
    assert sev["hausgeld_open"] == "100.00"
    assert sev["hoa_result"] == "400.00"
    assert sev["tenant_allocable_costs"] == "900.00"
    assert sev["owner_burden"] == "1400.00"
    assert sev["hoa_statement"]["statement_id"] == "h1"
    assert [f["code"] for f in findings] == []
    # Income of the rental ledger stays apart from the Hausgeld (A06: no mixing).
    assert results["income"]["rent"] == "1000.00"


def test_sev_without_hoa_statement_reports_finding() -> None:
    results, findings = build_results(
        _inputs(kind="sev_owner", hoa_statement=None, operating_cost_statements=[])
    )
    assert results["sev_reconciliation"]["hoa_cost_share"] == "0.00"
    codes = {f["code"] for f in findings}
    assert {"SEV-HOA-STATEMENT-MISSING", "SEV-OPERATING-COST-STATEMENT-MISSING"} <= codes


def test_sum_check_of_hoa_result_is_a_finding() -> None:
    inputs = _inputs(
        kind="sev_owner",
        hoa_statement={
            "statement_id": "h1",
            "units": [
                {
                    "unit_id": "u1",
                    "cost_share": "1500.00",
                    "advances_resolved": "1200.00",
                    "advances_paid": "0.00",
                    "result": "999.00",
                }
            ],
        },
        operating_cost_statements=[],
    )
    _, findings = build_results(inputs)
    assert any(f["code"] == "SUM-HOA-RESULT" and f["level"] == "error" for f in findings)


def test_digest_is_stable_and_decimal_free() -> None:
    results, findings = build_results(_inputs())
    snapshot = {"rule_version": RULE_VERSION, "results": results, "findings": findings}
    assert digest(snapshot) == digest(dict(snapshot))
    assert Decimal(results["liquidity"]["free"]) == Decimal("310.00")
