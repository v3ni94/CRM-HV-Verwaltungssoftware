"""GA07-01: three year term of the enabling resolution of virtual meetings (notice only)."""

from datetime import date

from mhvp.hoa.meeting_rules import basis_term_limit, basis_term_notice


def test_limit_is_decision_date_plus_three_years() -> None:
    assert basis_term_limit(date(2026, 3, 1)) == date(2029, 3, 1)
    assert basis_term_limit(date(2024, 2, 29)) == date(2027, 2, 28)


def test_notice_only_when_term_exceeded() -> None:
    assert basis_term_notice(date(2026, 3, 1), date(2029, 3, 1)) is None
    assert basis_term_notice(date(2026, 3, 1), None) is None
    notice = basis_term_notice(date(2026, 3, 1), date(2029, 3, 2))
    assert notice is not None
    for part in ("02.03.2029", "01.03.2029", "AA06-02"):
        assert part in notice
