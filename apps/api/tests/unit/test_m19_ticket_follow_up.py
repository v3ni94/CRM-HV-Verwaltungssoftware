"""Regel M19-10: reopening window in calendar days, auto reply detection from headers and the
preset of a follow-up ticket. Expected results are fixed dates, not computed by the rule."""

import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from types import SimpleNamespace
from typing import Any, cast

import pytest

from mhvp.communication import mail
from mhvp.tickets.follow_up import closed_at, preset, within_reopen_window


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("closed", "now", "window", "expected"),
    [
        # Abschluss am 28.08.2026, Mail am 27.09.2026: 30 Kalendertage, Grenze inklusive.
        ("2026-08-28T10:00:00", "2026-09-27T09:00:00", 30, True),
        # 27.08.2026 22:00 Uhr Berlin bis 27.09.2026: 31 Tage.
        ("2026-08-27T20:00:00", "2026-09-27T09:00:00", 30, False),
        # 27.08.2026 22:30 UTC ist in Berlin bereits der 28.08.2026 (00:30 Uhr): 30 Tage.
        ("2026-08-27T22:30:00", "2026-09-27T09:00:00", 30, True),
        ("2026-09-17T12:00:00", "2026-09-27T12:00:00", 30, True),  # 10 Tage
        ("2026-08-18T12:00:00", "2026-09-27T12:00:00", 30, False),  # 40 Tage
        ("2026-09-27T01:00:00", "2026-09-27T20:00:00", 0, True),  # gleicher Tag, Fenster 0
        ("2026-09-26T20:00:00", "2026-09-27T08:00:00", 0, False),  # Vortag, Fenster 0
        ("2026-08-18T12:00:00", "2026-09-27T12:00:00", 60, True),  # 40 Tage, Fenster 60
    ],
)
def test_within_reopen_window(closed: str, now: str, window: int, expected: bool) -> None:
    assert within_reopen_window(_utc(closed), _utc(now), window) is expected


def test_closed_at_falls_back_to_the_last_change() -> None:
    resolved = _utc("2026-08-01T08:00:00")
    updated = _utc("2026-09-01T08:00:00")
    ticket = cast(Any, SimpleNamespace(resolved_at=resolved, updated_at=updated))
    assert closed_at(ticket) == resolved
    ticket.resolved_at = None
    assert closed_at(ticket) == updated


def _headers(**headers: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"], msg["Subject"] = "a@example.com", "Abwesend"
    for name, value in headers.items():
        msg[name.replace("_", "-")] = value
    msg.set_content("Ich bin bis 05.10.2026 nicht im Büro.")
    return msg


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Auto_Submitted": "auto-replied"}, True),
        ({"Auto_Submitted": "auto-generated"}, True),
        ({"Auto_Submitted": "auto-notified; owner-email=a@example.com"}, True),
        ({"Auto_Submitted": "no"}, False),
        ({"Auto_Submitted": "No"}, False),
        ({"X_Autoreply": "yes"}, True),
        ({"X_Autorespond": "Abwesenheit"}, True),
        ({"Precedence": "auto_reply"}, True),
        ({"Precedence": "bulk"}, False),
        ({}, False),
    ],
)
def test_auto_submitted_from_headers_only(headers: dict[str, str], expected: bool) -> None:
    assert mail.is_auto_submitted(_headers(**headers)) is expected
    assert mail.parse(bytes(_headers(**headers)))["auto_submitted"] is expected


def test_preset_takes_the_assignment_of_the_predecessor() -> None:
    pred_id, prop, unit, contact = (uuid.uuid4() for _ in range(4))
    mail_contact, mail_property = uuid.uuid4(), uuid.uuid4()
    predecessor = cast(
        Any, SimpleNamespace(id=pred_id, property_id=prop, unit_id=unit, contact_id=contact)
    )
    assert preset(predecessor, contact_id=mail_contact, property_id=mail_property) == {
        "contact_id": contact,
        "property_id": prop,
        "unit_id": unit,
        "follow_up_of_ticket_id": pred_id,
    }
    # Ohne Zuordnung am Vorgänger füllt die Mail die Lücken; eine Einheit nie ohne Objekt.
    empty = cast(Any, SimpleNamespace(id=pred_id, property_id=None, unit_id=unit, contact_id=None))
    assert preset(empty, contact_id=mail_contact, property_id=mail_property) == {
        "contact_id": mail_contact,
        "property_id": mail_property,
        "unit_id": None,
        "follow_up_of_ticket_id": pred_id,
    }
