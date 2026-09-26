"""Orientation calculation of service provider contracts (M9-06, A41): month end, automatic
renewal, cancelled and open ended contracts. Expected dates are computed by hand."""

from datetime import date

from mhvp.contracts.service_contracts import add_months, compute_terms, notice_date_for


def _terms(**kw: object):  # type: ignore[no-untyped-def]
    base: dict[str, object] = {
        "starts_at": date(2024, 1, 1),
        "ends_at": date(2026, 12, 31),
        "notice_amount": 3,
        "notice_unit": "months",
        "auto_renewal_months": None,
        "cancelled_at": None,
        "today": date(2026, 9, 26),
    }
    base.update(kw)
    return compute_terms(**base)  # type: ignore[arg-type]


def test_add_months_keeps_month_end() -> None:
    assert add_months(date(2026, 6, 30), -3) == date(2026, 3, 31)
    assert add_months(date(2026, 2, 28), 12) == date(2027, 2, 28)
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 5, 15), -3) == date(2026, 2, 15)
    assert add_months(date(2026, 3, 30), -1) == date(2026, 2, 28)


def test_notice_date_month_end_and_days() -> None:
    assert notice_date_for(date(2026, 12, 31), 3, "months") == date(2026, 9, 30)
    assert notice_date_for(date(2026, 6, 30), 3, "months") == date(2026, 3, 31)
    assert notice_date_for(date(2026, 12, 31), 30, "days") == date(2026, 12, 1)


def test_running_contract_without_renewal() -> None:
    t = _terms()
    assert (t.status, t.next_end, t.notice_deadline) == (
        "running",
        date(2026, 12, 31),
        date(2026, 9, 30),
    )


def test_missed_notice_without_renewal_keeps_end_without_deadline() -> None:
    t = _terms(today=date(2026, 10, 1))
    assert (t.status, t.next_end, t.notice_deadline) == ("running", date(2026, 12, 31), None)


def test_automatic_renewal_moves_end() -> None:
    t = _terms(today=date(2026, 10, 1), auto_renewal_months=12)
    assert (t.next_end, t.notice_deadline) == (date(2027, 12, 31), date(2027, 9, 30))
    t = _terms(ends_at=date(2020, 6, 30), auto_renewal_months=12)
    assert (t.next_end, t.notice_deadline) == (date(2027, 6, 30), date(2027, 3, 31))


def test_expired_contract() -> None:
    t = _terms(ends_at=date(2025, 12, 31))
    assert (t.status, t.next_end, t.notice_deadline) == ("expired", None, None)


def test_cancelled_in_time_and_late() -> None:
    t = _terms(cancelled_at=date(2026, 9, 1), auto_renewal_months=12)
    assert (t.status, t.next_end, t.notice_deadline) == ("cancelled", date(2026, 12, 31), None)
    t = _terms(cancelled_at=date(2026, 10, 5), auto_renewal_months=12)
    assert (t.status, t.next_end, t.notice_deadline) == ("cancelled", date(2027, 12, 31), None)


def test_open_ended_contract() -> None:
    t = _terms(ends_at=None, notice_amount=14, notice_unit="days")
    assert (t.status, t.next_end, t.notice_deadline) == ("open_ended", date(2026, 10, 10), None)
    t = _terms(ends_at=None, cancelled_at=date(2026, 9, 15))
    assert (t.status, t.next_end) == ("cancelled", date(2026, 12, 15))
