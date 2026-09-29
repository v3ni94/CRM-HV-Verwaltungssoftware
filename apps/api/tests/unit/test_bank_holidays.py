"""German holidays for the review due date (rule M12-05, assumption A-088): fixed dates,
Easter, NRW holidays and the next working day over weekends and holidays (rule 0.1.8)."""

from __future__ import annotations

from datetime import date

import pytest

from mhvp.banking import holidays, review


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
        (2027, date(2027, 3, 28)),
    ],
)
def test_easter_sunday(year: int, expected: date) -> None:
    assert holidays.easter_sunday(year) == expected


def test_holidays_2026_nationwide_and_nrw() -> None:
    table = holidays.holidays(2026)
    assert table[date(2026, 4, 3)] == "Karfreitag"
    assert table[date(2026, 4, 6)] == "Ostermontag"
    assert table[date(2026, 5, 14)] == "Christi Himmelfahrt"
    assert table[date(2026, 5, 25)] == "Pfingstmontag"
    assert table[date(2026, 6, 4)] == "Fronleichnam"
    assert table[date(2026, 11, 1)] == "Allerheiligen"
    assert table[date(2026, 10, 3)] == "Tag der Deutschen Einheit"
    assert len(table) == 11
    assert date(2026, 6, 4) not in holidays.holidays(2026, state="BE")
    assert holidays.is_holiday(date(2026, 12, 26))
    assert not holidays.is_holiday(date(2026, 12, 24))


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 29), date(2026, 9, 30)),  # Tuesday to Wednesday
        (date(2026, 10, 2), date(2026, 10, 5)),  # Friday to Monday
        (date(2026, 4, 2), date(2026, 4, 7)),  # Thursday before Karfreitag to the Tuesday
        (date(2025, 10, 2), date(2025, 10, 6)),  # Thursday, Friday is 3.10.
        (date(2027, 10, 29), date(2027, 11, 2)),  # Friday, Monday is Allerheiligen (NRW)
        (date(2026, 12, 24), date(2026, 12, 28)),  # 25.12. Friday, 26.12. Saturday
    ],
)
def test_next_working_day_skips_weekends_and_holidays(day: date, expected: date) -> None:
    assert holidays.next_working_day(day) == expected
    assert review.next_working_day(day) == expected


def test_due_for_daily_and_sample() -> None:
    assert review.due_for("daily", date(2026, 4, 2)) == date(2026, 4, 7)
    assert review.due_for("sample", date(2026, 4, 2)) == date(2026, 4, 9)
