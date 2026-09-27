"""Rule M5-02 (operator decision 26.09.2026): deposit settlement computation with hand
computed expected values (rule 0.1.8). Interest modes individual, reference rate and none;
day exact per calendar year on the balance basis; rounding once per year (ROUND_HALF_UP).

Hand computation for the reference rate case with an offset (D, see docs/rules/M5-02):
payment 1.200,00 on 01.01.2025, offset 200,00 on 01.04.2026, settlement 30.06.2026, rates
2025 = 1,00 %, 2026 = 0,50 %.
2025: 1.200,00 x 1,00 % x 365/365 = 12,00.
2026: 01.01. to 31.03. = 90 days at 1.200,00: 1.200 x 0,005 x 90/365 = 1,4794520...
      01.04. to 30.06. = 91 days at 1.000,00: 1.000 x 0,005 x 91/365 = 1,2465753...
      sum 2,7260273... rounded once per year = 2,73 (181 days).
Interest 14,73; balance before interest 1.000,00; deduction 150,00; payout 864,73.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from mhvp.contracts.deposit_settlement import (
    BalanceChange,
    Deduction,
    SettlementError,
    SettlementResult,
    balance_intervals,
    compute_settlement,
    interest_by_reference_rate,
)
from mhvp.contracts.deposit_settlement import (
    DepositInterestMode as Mode,
)

D = Decimal


def _settle(**kwargs: Any) -> SettlementResult:
    base: dict[str, Any] = {
        "settlement_date": date(2025, 12, 31),
        "interest_mode": Mode.NONE,
        "payments": [(date(2025, 1, 1), D("1200.00"))],
        "offsets": [],
        "payouts": [],
        "interest_recorded": D("0.00"),
        "deductions": [],
    }
    base.update(kwargs)
    return compute_settlement(**base)


def test_reference_rate_full_year() -> None:
    """1.200,00 x 1,00 % x 365/365 = 12,00."""
    result = _settle(interest_mode=Mode.REFERENCE_RATE, rates={2025: D("1.00000")})
    assert [(y.year, y.days, y.amount) for y in result.years] == [(2025, 365, D("12.00"))]
    assert result.interest_total == D("12.00")
    assert result.payout_amount == D("1212.00")


def test_reference_rate_two_years_with_offset_and_deduction() -> None:
    result = _settle(
        interest_mode=Mode.REFERENCE_RATE,
        settlement_date=date(2026, 6, 30),
        offsets=[(date(2026, 4, 1), D("200.00"))],
        rates={2025: D("1.00000"), 2026: D("0.50000")},
        deductions=[Deduction("Schaden Bad", D("150.00"))],
    )
    years = [(y.year, y.rate, y.days, y.amount) for y in result.years]
    assert years == [
        (2025, D("1.00000"), 365, D("12.00")),
        (2026, D("0.50000"), 181, D("2.73")),
    ]
    assert result.principal_paid == D("1200.00")
    assert result.offsets_recorded == D("200.00")
    assert result.balance_before_interest == D("1000.00")
    assert result.interest_total == D("14.73")
    assert result.deductions_total == D("150.00")
    assert result.payout_amount == D("864.73")


def test_reference_rate_leap_year_uses_366_days() -> None:
    """2024 is a leap year: 1.000,00 x 1 % x 366/366 = 10,00; until 29.02. (60 days) 1,64."""
    payments = [(date(2024, 1, 1), D("1000.00"))]
    full = _settle(
        interest_mode=Mode.REFERENCE_RATE,
        payments=payments,
        settlement_date=date(2024, 12, 31),
        rates={2024: D("1.00000")},
    )
    assert [(y.days, y.amount) for y in full.years] == [(366, D("10.00"))]
    partial = _settle(
        interest_mode=Mode.REFERENCE_RATE,
        payments=payments,
        settlement_date=date(2024, 2, 29),
        rates={2024: D("1.00000")},
    )
    # 10,00 x 60/366 = 1,639344... -> 1,64
    assert [(y.days, y.amount) for y in partial.years] == [(60, D("1.64"))]


def test_rounding_half_up_once_per_year() -> None:
    """1.000,00 x 0,1825 % = 1,825 exactly: commercial rounding gives 1,83 (not 1,82)."""
    result = _settle(
        interest_mode=Mode.REFERENCE_RATE,
        payments=[(date(2025, 1, 1), D("1000.00"))],
        rates={2025: D("0.18250")},
    )
    assert result.years[0].amount == D("1.83")


def test_reference_rate_installments_and_same_day_merge() -> None:
    """Three installments 400,00 on 01.01., 01.02., 01.03.2025 (1 %): 400 x 365 + 400 x 334 +
    400 x 306 days = 4 x (365 + 334 + 306) / 365 = 4 x 1005/365 = 11,0136... -> 11,01."""
    result = _settle(
        interest_mode=Mode.REFERENCE_RATE,
        payments=[
            (date(2025, 1, 1), D("400.00")),
            (date(2025, 2, 1), D("400.00")),
            (date(2025, 3, 1), D("400.00")),
        ],
        rates={2025: D("1.00000")},
    )
    assert result.years[0].amount == D("11.01")
    intervals = balance_intervals(
        [BalanceChange(date(2025, 1, 1), D("300")), BalanceChange(date(2025, 1, 1), D("100"))],
        date(2025, 1, 10),
    )
    assert intervals == [(date(2025, 1, 1), date(2025, 1, 11), D("400"))]


def test_reference_rate_missing_year_is_refused() -> None:
    with pytest.raises(SettlementError, match="2026"):
        interest_by_reference_rate(
            [BalanceChange(date(2025, 6, 1), D("500"))], {2025: D("1")}, date(2026, 1, 31)
        )


def test_individual_interest_per_year() -> None:
    result = _settle(
        interest_mode=Mode.INDIVIDUAL,
        payments=[(date(2025, 1, 5), D("800.00"))],
        settlement_date=date(2026, 3, 31),
        interest_recorded=D("3.10"),
        entered_interest={2025: D("3.10"), 2026: D("1.05")},
    )
    assert [(y.year, y.rate, y.amount) for y in result.years] == [
        (2025, None, D("3.10")),
        (2026, None, D("1.05")),
    ]
    assert result.interest_total == D("4.15")
    assert result.interest_recorded == D("3.10")
    # Recorded interest movements are shown, not added again: 800,00 + 4,15.
    assert result.payout_amount == D("804.15")
    with pytest.raises(SettlementError, match="2027"):
        _settle(
            interest_mode=Mode.INDIVIDUAL,
            settlement_date=date(2026, 3, 31),
            entered_interest={2027: D("1.00")},
        )


def test_no_interest_mode() -> None:
    result = _settle(
        payouts=[(date(2025, 6, 1), D("100.00"))],
        deductions=[Deduction("Endreinigung", D("80.00"))],
    )
    assert result.years == []
    assert result.balance_before_interest == D("1100.00")
    assert result.payout_amount == D("1020.00")


def test_refusals() -> None:
    with pytest.raises(SettlementError, match="keine Einzahlung"):
        _settle(payments=[])
    with pytest.raises(SettlementError, match="nach dem Abrechnungsdatum"):
        _settle(offsets=[(date(2026, 1, 2), D("10.00"))])
    with pytest.raises(SettlementError, match="übersteigen"):
        _settle(deductions=[Deduction("Schaden", D("1200.01"))])
    with pytest.raises(SettlementError, match="positiven Betrag"):
        _settle(deductions=[Deduction("Leer", D("0.00"))])
