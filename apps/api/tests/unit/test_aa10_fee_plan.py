"""GA03-06 fee fields (SE amount, due date, termination) and GA03-07 auto post defaults."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from mhvp.accounting import admin_fees, receivables
from mhvp.accounting.models import RecurringInvoicePlan
from mhvp.core.problems import ProblemError


def _fee(**kw: object) -> SimpleNamespace:
    fee = SimpleNamespace(
        amounts_per_unit_type={"apartment": "25.00"},
        min_amount=None,
        max_amount=None,
        vat_percent=Decimal("19"),
        invoice_debtor_party_id=None,
        sev_fee_amount=None,
        start_date=date(2026, 1, 1),
        end_date=None,
        termination_date=None,
        due_day_rule=None,
        due_day=None,
        interval="monthly",
    )
    vars(fee).update(kw)
    return fee


def test_sev_fee_amount_replaces_unit_type_amounts() -> None:
    # 3 units x 12,50 EUR = 37,50 EUR net, 19 % VAT 7,13 EUR (7,125 rounded half up).
    fee = _fee(invoice_debtor_party_id="p", sev_fee_amount=Decimal("12.50"))
    draft = receivables.admin_fee(fee, {"apartment": 3})
    assert (draft["net"], draft["vat"], draft["gross"]) == ("37.50", "7.13", "44.63")


def test_weg_fee_ignores_sev_fee_amount() -> None:
    fee = _fee(sev_fee_amount=Decimal("12.50"))
    assert receivables.admin_fee(fee, {"apartment": 2})["net"] == "50.00"  # 2 x 25,00


@pytest.mark.parametrize(
    ("rule", "day", "expected"),
    [
        ("day", 10, date(2026, 4, 10)),
        ("last_day", None, date(2026, 4, 30)),
        ("day_next_month", 5, date(2026, 5, 5)),
    ],
)
def test_fee_due_date(rule: str, day: int | None, expected: date) -> None:
    assert (
        admin_fees.fee_due_date(_fee(due_day_rule=rule, due_day=day), date(2026, 4, 1)) == expected
    )


def test_fee_due_date_without_rule() -> None:
    assert admin_fees.fee_due_date(_fee(), date(2026, 4, 1)) is None


def test_termination_limits_run() -> None:
    fee = _fee(end_date=date(2026, 12, 31), termination_date=date(2026, 6, 30))
    assert admin_fees.effective_end(fee) == date(2026, 6, 30)
    admin_fees.check_period(fee, date(2026, 4, 1), date(2026, 6, 30))
    with pytest.raises(ProblemError):
        admin_fees.check_period(fee, date(2026, 7, 1), date(2026, 7, 31))


def test_plan_auto_post_default_off() -> None:
    assert RecurringInvoicePlan.__table__.c.auto_post.server_default.arg == "false"  # type: ignore[union-attr]
    assert RecurringInvoicePlan.__table__.c.auto_post.nullable is False
