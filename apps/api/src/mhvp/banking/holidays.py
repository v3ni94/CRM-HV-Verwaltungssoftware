"""German public holidays for the review due date (rule M12-05, assumption A-088).

Deterministic table without an external service: the nationwide holidays plus the holidays
of Nordrhein-Westfalen (seat of both tenants). Easter is computed with the Gregorian
algorithm of Gauss as refined by Lichtenberg, which is exact for the Gregorian calendar.
Used only for "next working day" of the review queue; no legal deadline is computed here
(deadlines of the legal case register are outside this module).
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday (Gauss, Lichtenberg's form)."""
    k = year // 100
    m = 15 + (3 * k + 3) // 4 - (8 * k + 13) // 25
    s = 2 - (3 * k + 3) // 4
    a = year % 19
    d = (19 * a + m) % 30
    r = (d + a // 11) // 29
    og = 21 + d - r
    sz = 7 - (year + year // 4 + s) % 7
    oe = 7 - (og - sz) % 7
    march_day = og + oe  # day in March, may exceed 31
    return date(year, 3, 1) + timedelta(days=march_day - 1)


@lru_cache(maxsize=64)
def holidays(year: int, *, state: str = "NW") -> dict[date, str]:
    """Holidays of ``year``: nationwide plus the state (only ``NW`` is tabled)."""
    easter = easter_sunday(year)
    out = {
        date(year, 1, 1): "Neujahr",
        easter - timedelta(days=2): "Karfreitag",
        easter + timedelta(days=1): "Ostermontag",
        date(year, 5, 1): "Tag der Arbeit",
        easter + timedelta(days=39): "Christi Himmelfahrt",
        easter + timedelta(days=50): "Pfingstmontag",
        date(year, 10, 3): "Tag der Deutschen Einheit",
        date(year, 12, 25): "1. Weihnachtstag",
        date(year, 12, 26): "2. Weihnachtstag",
    }
    if state == "NW":
        out[easter + timedelta(days=60)] = "Fronleichnam"
        out[date(year, 11, 1)] = "Allerheiligen"
    return out


def is_holiday(day: date, *, state: str = "NW") -> bool:
    return day in holidays(day.year, state=state)


def is_working_day(day: date, *, state: str = "NW") -> bool:
    return day.weekday() < 5 and not is_holiday(day, state=state)


def next_working_day(day: date, *, state: str = "NW") -> date:
    """First Monday to Friday after ``day`` that is no holiday."""
    out = day + timedelta(days=1)
    while not is_working_day(out, state=state):
        out += timedelta(days=1)
    return out
