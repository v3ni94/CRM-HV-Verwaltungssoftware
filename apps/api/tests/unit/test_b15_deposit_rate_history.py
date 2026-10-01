"""Rule B15: interest of a deposit from its own rate history (hand computed, rule 0.1.8).

Payment 1.200,00 on 01.01.2025, rate 1,00 % from 01.01.2025 and 2,00 % from 01.07.2025.
2025: 01.01. to 30.06. = 181 days: 1.200 x 0,01 x 181/365 = 5,9506849...
      01.07. to 31.12. = 184 days: 1.200 x 0,02 x 184/365 = 12,0986301...
      sum 18,0493150... rounded once per year = 18,05 (365 days, rate varies, so None).
"""

from datetime import date
from decimal import Decimal

import pytest

from mhvp.contracts.deposit_settlement import (
    BalanceChange,
    DepositInterestMode,
    SettlementError,
    compute_settlement,
    interest_by_rate_history,
)

D = Decimal
PAY = [BalanceChange(date(2025, 1, 1), D("1200.00"))]


def test_rate_change_inside_year() -> None:
    history = [(date(2025, 1, 1), D("1.00000")), (date(2025, 7, 1), D("2.00000"))]
    [year] = interest_by_rate_history(PAY, history, date(2025, 12, 31))
    assert (year.year, year.days, year.amount, year.rate) == (2025, 365, D("18.05"), None)


def test_single_rate_is_reported() -> None:
    [year] = interest_by_rate_history(PAY, [(date(2024, 6, 1), D("1.50000"))], date(2025, 12, 31))
    # 1.200 x 0,015 = 18,00 for a full year.
    assert (year.amount, year.rate) == (D("18.00"), D("1.50000"))


def test_missing_rate_is_refused() -> None:
    with pytest.raises(SettlementError, match=r"01\.01\.2025"):
        interest_by_rate_history(PAY, [(date(2025, 3, 1), D("1.0"))], date(2025, 12, 31))


def test_single_year_selection_and_offset() -> None:
    changes = [*PAY, BalanceChange(date(2026, 4, 1), D("-200.00"))]
    history = [(date(2025, 1, 1), D("1.00000")), (date(2026, 1, 1), D("0.50000"))]
    [year] = interest_by_rate_history(changes, history, date(2026, 12, 31), [2026])
    # 90 days at 1.200 and 275 days at 1.000: 1,4794520 + 3,7671232 = 5,2465753 -> 5,25.
    assert (year.year, year.days, year.amount) == (2026, 365, D("5.25"))


def test_settlement_mode_deposit_rates() -> None:
    result = compute_settlement(
        settlement_date=date(2025, 12, 31),
        interest_mode=DepositInterestMode.DEPOSIT_RATES,
        payments=[(date(2025, 1, 1), D("1200.00"))],
        offsets=[],
        payouts=[],
        interest_recorded=D("0.00"),
        deductions=[],
        rate_history=[(date(2025, 1, 1), D("1.00000")), (date(2025, 7, 1), D("2.00000"))],
    )
    assert result.interest_total == D("18.05")
    assert result.payout_amount == D("1218.05")


def test_settlement_mode_without_history_is_refused() -> None:
    with pytest.raises(SettlementError):
        compute_settlement(
            settlement_date=date(2025, 12, 31),
            interest_mode=DepositInterestMode.DEPOSIT_RATES,
            payments=[(date(2025, 1, 1), D("1200.00"))],
            offsets=[],
            payouts=[],
            interest_recorded=D("0.00"),
            deductions=[],
        )
