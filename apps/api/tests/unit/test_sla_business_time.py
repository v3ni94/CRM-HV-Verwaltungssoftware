"""Geschäftszeitenberechnung (M21, docs/mail/04-status-und-sla.md Abschnitt 7)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from mhvp.sla.business_time import add_business_minutes, business_minutes_between
from mhvp.sla.models import WorkCalendar

BERLIN = ZoneInfo("Europe/Berlin")


def _calendar(**overrides: object) -> WorkCalendar:
    from datetime import time

    calendar = WorkCalendar(
        weekdays=[0, 1, 2, 3, 4],
        opens_at=time(8, 0),
        closes_at=time(16, 30),
        timezone="Europe/Berlin",
        holidays=[],
    )
    for key, value in overrides.items():
        setattr(calendar, key, value)
    return calendar


def test_add_business_minutes_within_same_day() -> None:
    calendar = _calendar()
    start = datetime(2026, 9, 21, 9, 0, tzinfo=BERLIN)  # Montag
    result = add_business_minutes(calendar, start, 60)
    assert result == datetime(2026, 9, 21, 10, 0, tzinfo=BERLIN)


def test_add_business_minutes_rolls_over_to_next_working_day() -> None:
    calendar = _calendar()
    start = datetime(2026, 9, 21, 16, 0, tzinfo=BERLIN)  # Montag, 30 Min bis Feierabend
    result = add_business_minutes(calendar, start, 90)
    # 30 Minuten am Montag verbraucht, 60 Minuten am Dienstag ab 08:00
    assert result == datetime(2026, 9, 22, 9, 0, tzinfo=BERLIN)


def test_add_business_minutes_skips_weekend() -> None:
    calendar = _calendar()
    start = datetime(2026, 9, 25, 16, 0, tzinfo=BERLIN)  # Freitag, 30 Min bis Feierabend
    result = add_business_minutes(calendar, start, 90)
    # Wochenende übersprungen, weiter am Montag
    assert result == datetime(2026, 9, 28, 9, 0, tzinfo=BERLIN)


def test_add_business_minutes_skips_holiday() -> None:
    calendar = _calendar(holidays=["2026-10-03"])  # Tag der Deutschen Einheit (Samstag in 2026,
    # daher zusätzlich ein Werktagsfeiertag zum Testen)
    calendar.holidays = ["2026-09-22"]
    start = datetime(2026, 9, 21, 16, 0, tzinfo=BERLIN)
    result = add_business_minutes(calendar, start, 90)
    # Dienstag ist Feiertag, also Mittwoch
    assert result == datetime(2026, 9, 23, 9, 0, tzinfo=BERLIN)


def test_add_business_minutes_starts_outside_hours_at_next_opening() -> None:
    calendar = _calendar()
    start = datetime(2026, 9, 21, 20, 0, tzinfo=BERLIN)
    result = add_business_minutes(calendar, start, 30)
    assert result == datetime(2026, 9, 22, 8, 30, tzinfo=BERLIN)


def test_business_minutes_between_same_day() -> None:
    calendar = _calendar()
    start = datetime(2026, 9, 21, 9, 0, tzinfo=BERLIN)
    end = datetime(2026, 9, 21, 11, 30, tzinfo=BERLIN)
    assert business_minutes_between(calendar, start, end) == 150


def test_business_minutes_between_across_weekend_excludes_it() -> None:
    calendar = _calendar()
    start = datetime(2026, 9, 25, 16, 0, tzinfo=BERLIN)  # Freitag
    end = datetime(2026, 9, 28, 9, 30, tzinfo=BERLIN)  # Montag
    # 30 Min Freitag (16:00-16:30) + 90 Min Montag (08:00-09:30), Wochenende ausgeklammert
    assert business_minutes_between(calendar, start, end) == 120


def test_business_minutes_between_end_before_start_is_zero() -> None:
    calendar = _calendar()
    start = datetime(2026, 9, 21, 11, 0, tzinfo=BERLIN)
    end = datetime(2026, 9, 21, 9, 0, tzinfo=BERLIN)
    assert business_minutes_between(calendar, start, end) == 0


def test_dst_spring_forward_four_hours_stays_four_business_hours() -> None:
    # Umstellung auf Sommerzeit: 29.03.2026 (Sonntag). Dienstag 24.03. bis Mittwoch 25.03.2026
    # bleibt unberührt von der Umstellung, daher ein Werktag mit Wechsel im gleichen Zeitraum:
    # Freitag 27.03. auf Montag 30.03.2026 überspannt die Umstellungsnacht.
    calendar = _calendar()
    start = datetime(2026, 3, 27, 15, 0, tzinfo=BERLIN)  # Freitag, 90 Min bis Feierabend
    result = add_business_minutes(calendar, start, 240)
    # 90 Minuten Freitag, 150 Minuten Montag ab 08:00 -> 10:30, unabhängig von der Zeitumstellung
    assert result == datetime(2026, 3, 30, 10, 30, tzinfo=BERLIN)
