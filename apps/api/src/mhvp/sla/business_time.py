"""Geschäftszeitenberechnung (docs/mail/04-status-und-sla.md, Abschnitt 7).

Alle Berechnungen laufen in der Zeitzone des Kalenders (Standard Europe/Berlin) und werden vor
der Speicherung nach UTC umgerechnet. Kalenderzeit-Uhren (``ClockType.CALENDAR``) laufen rund um
die Uhr und benutzen diese Funktionen nicht.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from mhvp.sla.models import WorkCalendar


def _tz(calendar: WorkCalendar) -> ZoneInfo:
    return ZoneInfo(calendar.timezone or "Europe/Berlin")


def _is_working_day(calendar: WorkCalendar, day: date) -> bool:
    if day.weekday() not in calendar.weekdays:
        return False
    return day.isoformat() not in calendar.holidays


def _window(calendar: WorkCalendar, day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, calendar.opens_at, tzinfo=tz)
    end = datetime.combine(day, calendar.closes_at, tzinfo=tz)
    return start, end


def add_business_minutes(calendar: WorkCalendar, start: datetime, minutes: int) -> datetime:
    """Addiert Arbeitsminuten auf ``start`` unter Berücksichtigung von Wochentagen, Öffnungszeiten
    und Feiertagen. Liegt ``start`` außerhalb der Arbeitszeit, beginnt die Zählung mit dem
    nächsten Arbeitsbeginn."""
    tz = _tz(calendar)
    cursor = start.astimezone(tz)
    remaining = minutes
    day = cursor.date()
    while True:
        if not _is_working_day(calendar, day):
            day = day + timedelta(days=1)
            cursor = datetime.combine(day, calendar.opens_at, tzinfo=tz)
            continue
        window_start, window_end = _window(calendar, day, tz)
        if cursor < window_start:
            cursor = window_start
        if cursor >= window_end:
            day = day + timedelta(days=1)
            cursor = datetime.combine(day, calendar.opens_at, tzinfo=tz)
            continue
        available = int((window_end - cursor).total_seconds() // 60)
        if remaining <= available:
            return (cursor + timedelta(minutes=remaining)).astimezone(start.tzinfo or tz)
        remaining -= available
        day = day + timedelta(days=1)
        cursor = datetime.combine(day, calendar.opens_at, tzinfo=tz)


def business_minutes_between(calendar: WorkCalendar, start: datetime, end: datetime) -> int:
    """Anzahl der Arbeitsminuten zwischen zwei Zeitpunkten (für die Ampelberechnung: wie viele
    Minuten der Zielzeit sind bereits verstrichen)."""
    if end <= start:
        return 0
    tz = _tz(calendar)
    cursor = start.astimezone(tz)
    stop = end.astimezone(tz)
    total = 0
    day = cursor.date()
    while day <= stop.date():
        if _is_working_day(calendar, day):
            window_start, window_end = _window(calendar, day, tz)
            lo = max(window_start, cursor if day == cursor.date() else window_start)
            hi = min(window_end, stop if day == stop.date() else window_end)
            if hi > lo:
                total += int((hi - lo).total_seconds() // 60)
        day = day + timedelta(days=1)
    return total
