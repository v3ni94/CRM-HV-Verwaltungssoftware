"""Minimaler iCalendar-Parser (UID, SUMMARY, DTSTART, DTEND, LOCATION, DESCRIPTION), selbst
implementiert (Regel 8: keine neuen Pakete). Ein VCALENDAR kann mehrere VEVENT enthalten."""

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class ParsedEvent:
    uid: str | None = None
    summary: str | None = None
    dtstart: datetime | None = None
    dtend: datetime | None = None
    location: str | None = None
    description: str | None = None
    raw: str = ""


def _unfold(raw: str) -> list[str]:
    lines: list[str] = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        elif line.strip():
            lines.append(line)
    return lines


def _parse_dt(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    return None


def parse_ical(raw: str) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    current: ParsedEvent | None = None
    current_lines: list[str] = []
    for line in _unfold(raw):
        stripped = line.strip()
        if stripped == "BEGIN:VEVENT":
            current = ParsedEvent()
            current_lines = [line]
            continue
        if stripped == "END:VEVENT":
            if current is not None:
                current_lines.append(line)
                current.raw = "\n".join(current_lines)
                events.append(current)
            current = None
            continue
        if current is None:
            continue
        current_lines.append(line)
        if ":" not in line:
            continue
        name_part, _, value = line.partition(":")
        name = name_part.split(";", 1)[0].upper()
        if name == "UID":
            current.uid = value.strip()
        elif name == "SUMMARY":
            current.summary = value.strip()
        elif name == "DTSTART":
            current.dtstart = _parse_dt(value)
        elif name == "DTEND":
            current.dtend = _parse_dt(value)
        elif name == "LOCATION":
            current.location = value.strip()
        elif name == "DESCRIPTION":
            current.description = value.strip()
    return events
