"""M14-02/03/04 arithmetic with precomputed values (docs/rules/M14-02.md, M14-03.md,
M14-04.md): deductible input tax by revenue key, construction withholding proposal, exemption
validity, role limits and the § 35a labour share per kind."""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.accounting import tax

D = Decimal


def test_deductible_input_tax_by_revenue_key() -> None:
    # 190,00 input tax, revenue key 60 % -> 114,00; rest 76,00 stays cost.
    assert tax.deductible_input_tax(D("190.00"), opted=True, revenue_key_percent=D("60")) == (
        D("60"),
        D("114.00"),
    )
    # 33,33 % of 190,00 = 63,327 -> 63,33 (half up).
    assert tax.deductible_input_tax(D("190.00"), opted=True, revenue_key_percent=D("33.33"))[
        1
    ] == D("63.33")
    # Without option or without a determined key nothing is deducted.
    assert tax.deductible_input_tax(D("190.00"), opted=False, revenue_key_percent=D("100")) == (
        None,
        D("0.00"),
    )
    assert tax.deductible_input_tax(D("190.00"), opted=True, revenue_key_percent=None) == (
        None,
        D("0.00"),
    )
    with pytest.raises(ValueError, match="out of range"):
        tax.deductible_input_tax(D("1"), opted=True, revenue_key_percent=D("101"))


def test_withholding_proposal_15_percent_of_gross() -> None:
    # 1.190,00 gross at 15 % -> 178,50; 2.345,67 -> 351,85 (351,8505 half up).
    assert tax.withholding_proposal(
        D("1190.00"), construction_service=True, exemption_valid=False, percent=D("15")
    ) == D("178.50")
    assert tax.withholding_proposal(
        D("2345.67"), construction_service=True, exemption_valid=False, percent=D("15")
    ) == D("351.85")
    assert tax.withholding_proposal(
        D("1190.00"), construction_service=True, exemption_valid=True, percent=D("15")
    ) == D("0.00")
    assert tax.withholding_proposal(
        D("1190.00"), construction_service=False, exemption_valid=False, percent=D("15")
    ) == D("0.00")


def test_exemption_validity_needs_document_and_period() -> None:
    day = date(2026, 3, 15)
    assert tax.exemption_valid_on(day, date(2026, 1, 1), date(2026, 12, 31), True)
    assert tax.exemption_valid_on(day, date(2026, 1, 1), None, True)
    assert not tax.exemption_valid_on(day, date(2026, 1, 1), date(2026, 3, 14), True)
    assert not tax.exemption_valid_on(day, date(2026, 4, 1), None, True)
    assert not tax.exemption_valid_on(day, date(2026, 1, 1), None, False)
    assert not tax.exemption_valid_on(day, None, None, True)


def test_role_limits_highest_wins() -> None:
    limits = [
        {"role_code": "standard", "limit_amount": "500.00"},
        {"role_code": "accountant_no_banking", "limit_amount": "5000.00"},
    ]
    assert tax.role_limit(("standard",), limits) == D("500.00")
    assert tax.role_limit(("standard", "accountant_no_banking"), limits) == D("5000.00")
    assert tax.role_limit(("tenant_admin",), limits) is None
    assert tax.needs_second_approval(D("500.00"), ("standard",), limits) == (False, D("500.00"))
    assert tax.needs_second_approval(D("500.01"), ("standard",), limits) == (True, D("500.00"))
    # Credit notes count by absolute amount; roles without a limit need no second approval.
    assert tax.needs_second_approval(D("-600.00"), ("standard",), limits) == (True, D("500.00"))
    assert tax.needs_second_approval(D("99999"), ("tenant_admin",), limits) == (False, None)


def test_section35a_share_by_kind() -> None:
    summary = tax.Section35aSummary(
        lines=[
            tax.Section35aLine("R1", date(2026, 2, 1), "craftsman", D("1000.00"), D("400.00")),
            tax.Section35aLine("R2", date(2026, 3, 1), "craftsman", D("250.00"), D("0.00")),
            tax.Section35aLine("R3", date(2026, 4, 1), "household_service", D("300.00"), D("0.00")),
        ],
        share_percent=D("12.5"),
    )
    assert summary.labor_total == D("1550.00")
    assert summary.material_total == D("400.00")
    # 1.250,00 craftsman labour at 12,5 % -> 156,25; 300,00 household at 12,5 % -> 37,50.
    assert summary.share_by_kind() == {"craftsman": D("156.25"), "household_service": D("37.50")}
