"""AI01 (GAH-102, GAH-105): statement chain check and number range rule of the chart of
accounts, pure functions with recomputable expected values."""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from mhvp.accounting.chart_rules import account_range_problem
from mhvp.banking.services import _chain_check, _statement_status


def _st(opening: str | None, closing: str | None, start: str | None, end: str | None) -> Any:
    return SimpleNamespace(
        opening_balance=Decimal(opening) if opening else None,
        closing_balance=Decimal(closing) if closing else None,
        from_date=date.fromisoformat(start) if start else None,
        to_date=date.fromisoformat(end) if end else None,
        closing_date=date.fromisoformat(end) if end else None,
    )


def test_first_statement_has_no_predecessor() -> None:
    out = _chain_check(None, _st("1.00", "2.00", "2026-01-01", "2026-01-31"))
    assert out["chain_status"] == "first"
    assert out["period_status"] == "first"


def test_chain_ok_and_continuous_period() -> None:
    jan = _st("1000.00", "1100.00", "2026-01-01", "2026-01-31")
    feb = _st("1100.00", "1200.00", "2026-02-01", "2026-02-28")
    out = _chain_check(jan, feb)
    assert out["chain_status"] == "ok"
    assert out["chain_difference"] == Decimal("0.00")
    assert out["period_status"] == "ok"


def test_chain_break_and_gap() -> None:
    # 1.150,00 opening against 1.100,00 closing: break of 50,00; March is missing.
    jan = _st("1000.00", "1100.00", "2026-01-01", "2026-01-31")
    apr = _st("1150.00", "1200.00", "2026-04-01", "2026-04-30")
    out = _chain_check(jan, apr)
    assert out["chain_status"] == "break"
    assert out["chain_difference"] == Decimal("50.00")
    assert out["period_status"] == "gap"
    assert out["gap_from"] == date(2026, 2, 1)
    assert out["gap_to"] == date(2026, 3, 31)


def test_overlap_and_not_checkable() -> None:
    jan = _st("1000.00", "1100.00", "2026-01-01", "2026-01-31")
    assert (
        _chain_check(jan, _st("1100.00", None, "2026-01-15", "2026-02-15"))["period_status"]
        == "overlap"
    )
    csv = _st(None, None, None, None)
    out = _chain_check(jan, csv)
    assert out["chain_status"] == "not_checkable"
    assert out["period_status"] == "not_checkable"
    assert _chain_check(csv, jan)["chain_status"] == "not_checkable"


def test_statement_status() -> None:
    assert _statement_status(None, None) == "not_checkable"
    assert _statement_status(Decimal("0.00"), None) == "ok"
    assert _statement_status(Decimal("0.00"), Decimal("0.00")) == "ok"
    assert _statement_status(Decimal("0.01"), None) == "difference"
    assert _statement_status(Decimal("0.00"), Decimal("-3.00")) == "difference"


def test_account_range_rule() -> None:
    bank = uuid.uuid4()
    assert account_range_problem("001210", "bank", bank) is None
    assert account_range_problem("001300", "cash", None) is None
    assert account_range_problem("001360", "transit", None) is None  # Geldtransit, A.1
    assert account_range_problem("001400", "technical", None) is None  # default chart
    assert account_range_problem("001500", "cost", None)
    assert account_range_problem("001999", "debtor", None)
    assert account_range_problem("002000", "cost", None) is None  # outside the range
    assert account_range_problem("008100", "reserve", bank)  # link only on bank or cash
    assert account_range_problem("001360", "transit", bank)
