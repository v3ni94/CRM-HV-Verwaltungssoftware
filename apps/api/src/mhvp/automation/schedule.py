"""Schedule trigger (stage 2, A39): pure logic without database.

A schedule is ``{"frequency": "daily"|"weekly"|"monthly", "time": "HH:MM", "weekday": 0..6
(weekly, Monday = 0), "day": 1..28 (monthly)}`` in the operator time zone (Europe/Berlin).
``previous_due`` returns the latest due moment not after ``now``; the beat job fires a rule
once per due moment (watermark ``last_scheduled_at`` plus the unique run per rule and
window id). Days 29 to 31 are not offered so that a monthly rule fires in every month.
"""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from mhvp.automation.rules import RuleDefinitionError

FREQUENCIES: tuple[str, ...] = ("daily", "weekly", "monthly")
SCHEDULE_TZ = ZoneInfo("Europe/Berlin")
_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_NAMESPACE = uuid.UUID("6f1c2c8e-5d1a-4a7e-9d2b-3a0b7e5c1a39")


def validate_schedule(value: Any) -> dict[str, Any]:
    """Normalised schedule or ``RuleDefinitionError``."""
    if not isinstance(value, dict):
        raise RuleDefinitionError("Zeitplan muss ein Objekt sein.")
    frequency = value.get("frequency")
    if frequency not in FREQUENCIES:
        raise RuleDefinitionError("Zeitplan: Häufigkeit täglich, wöchentlich oder monatlich.")
    time_raw = value.get("time")
    match = _TIME.fullmatch(str(time_raw)) if time_raw is not None else None
    if match is None:
        raise RuleDefinitionError("Zeitplan: Uhrzeit im Format HH:MM angeben.")
    normalised: dict[str, Any] = {"frequency": frequency, "time": f"{match[1]}:{match[2]}"}
    if frequency == "weekly":
        weekday = value.get("weekday")
        if not isinstance(weekday, int) or isinstance(weekday, bool) or not 0 <= weekday <= 6:
            raise RuleDefinitionError("Zeitplan: Wochentag 0 (Montag) bis 6 (Sonntag) angeben.")
        normalised["weekday"] = weekday
    if frequency == "monthly":
        day = value.get("day")
        if not isinstance(day, int) or isinstance(day, bool) or not 1 <= day <= 28:
            raise RuleDefinitionError("Zeitplan: Tag des Monats 1 bis 28 angeben.")
        normalised["day"] = day
    unknown = set(value) - set(normalised)
    if unknown:
        raise RuleDefinitionError(f"Zeitplan: unbekannte Angaben {', '.join(sorted(unknown))}.")
    return normalised


def _at(day: datetime, hour: int, minute: int) -> datetime:
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)


def previous_due(schedule: dict[str, Any], now: datetime) -> datetime:
    """Latest due moment of ``schedule`` that is not after ``now`` (returned in UTC)."""
    hour, minute = (int(p) for p in str(schedule["time"]).split(":"))
    local = now.astimezone(SCHEDULE_TZ)
    frequency = schedule["frequency"]
    if frequency == "daily":
        due = _at(local, hour, minute)
        if due > local:
            due -= timedelta(days=1)
    elif frequency == "weekly":
        weekday = int(schedule["weekday"])
        due = _at(local - timedelta(days=(local.weekday() - weekday) % 7), hour, minute)
        if due > local:
            due -= timedelta(days=7)
    else:
        day = int(schedule["day"])
        due = _at(local.replace(day=day), hour, minute)
        if due > local:
            first = local.replace(day=1)
            previous_month = first - timedelta(days=1)
            due = _at(previous_month.replace(day=day), hour, minute)
    # Re-localise so that a DST change does not carry a stale UTC offset.
    due = due.replace(tzinfo=None).replace(tzinfo=SCHEDULE_TZ)
    return due.astimezone(UTC)


def window_event_id(rule_id: uuid.UUID, due: datetime) -> uuid.UUID:
    """Deterministic run id per rule and due moment (unique run constraint = idempotency)."""
    return uuid.uuid5(_NAMESPACE, f"{rule_id}:{due.astimezone(UTC).isoformat()}")
