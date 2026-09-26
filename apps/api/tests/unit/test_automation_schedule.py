"""Unit tests of the rule engine stage 2 (A39): schedule logic and action schemas."""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from mhvp.automation.rules import RuleDefinitionError
from mhvp.automation.schedule import previous_due, validate_schedule, window_event_id
from mhvp.automation.schemas import AutomationRuleIn, dump_actions, parse_actions

BERLIN = ZoneInfo("Europe/Berlin")


def _local(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=BERLIN)


def test_validate_schedule_normalises_and_rejects() -> None:
    assert validate_schedule({"frequency": "daily", "time": "07:30"}) == {
        "frequency": "daily",
        "time": "07:30",
    }
    assert validate_schedule({"frequency": "weekly", "time": "08:00", "weekday": 0})["weekday"] == 0
    assert validate_schedule({"frequency": "monthly", "time": "06:00", "day": 28})["day"] == 28
    for bad in (
        {"frequency": "hourly", "time": "07:00"},
        {"frequency": "daily", "time": "7:00"},
        {"frequency": "daily", "time": "24:00"},
        {"frequency": "weekly", "time": "07:00"},
        {"frequency": "weekly", "time": "07:00", "weekday": 7},
        {"frequency": "monthly", "time": "07:00", "day": 31},
        {"frequency": "monthly", "time": "07:00", "day": True},
        {"frequency": "daily", "time": "07:00", "cron": "* * * * *"},
        "daily",
    ):
        with pytest.raises(RuleDefinitionError):
            validate_schedule(bad)


def test_previous_due_daily_weekly_monthly() -> None:
    daily = {"frequency": "daily", "time": "07:30"}
    assert previous_due(daily, _local(2026, 9, 26, 8, 0)) == _local(2026, 9, 26, 7, 30)
    assert previous_due(daily, _local(2026, 9, 26, 7, 30)) == _local(2026, 9, 26, 7, 30)
    assert previous_due(daily, _local(2026, 9, 26, 7, 29)) == _local(2026, 9, 25, 7, 30)
    # 26.09.2026 is a Saturday (weekday 5); weekly on Monday (0) 09:00.
    weekly = {"frequency": "weekly", "time": "09:00", "weekday": 0}
    assert previous_due(weekly, _local(2026, 9, 26, 8, 0)) == _local(2026, 9, 21, 9, 0)
    assert previous_due(weekly, _local(2026, 9, 21, 8, 59)) == _local(2026, 9, 14, 9, 0)
    assert previous_due(weekly, _local(2026, 9, 21, 9, 0)) == _local(2026, 9, 21, 9, 0)
    monthly = {"frequency": "monthly", "time": "06:00", "day": 5}
    assert previous_due(monthly, _local(2026, 9, 26, 8, 0)) == _local(2026, 9, 5, 6, 0)
    assert previous_due(monthly, _local(2026, 9, 5, 5, 59)) == _local(2026, 8, 5, 6, 0)
    assert previous_due(monthly, _local(2026, 3, 1, 0, 0)) == _local(2026, 2, 5, 6, 0)
    # Result is UTC; across the DST change the local wall clock time is kept.
    due = previous_due(daily, datetime(2026, 10, 25, 12, 0, tzinfo=UTC))
    assert due.tzinfo is UTC
    assert due.astimezone(BERLIN).hour == 7


def test_window_event_id_is_deterministic() -> None:
    rule_id = uuid.uuid4()
    due = _local(2026, 9, 26, 7, 30)
    assert window_event_id(rule_id, due) == window_event_id(rule_id, due.astimezone(UTC))
    assert window_event_id(rule_id, due) != window_event_id(uuid.uuid4(), due)
    assert window_event_id(rule_id, due) != window_event_id(rule_id, _local(2026, 9, 27, 7, 30))


def test_stage_two_actions_are_validated() -> None:
    actions = parse_actions(
        [
            {"type": "webhook", "url": "https://example.org/hook", "secret": "s" * 16},
            {"type": "mail_draft", "reply_template_id": str(uuid.uuid4())},
            {"type": "letter_draft", "template_id": str(uuid.uuid4()), "fields": {"text": "x"}},
            {
                "type": "ai_task",
                "task": "summarize",
                "instruction": "Fasse {entity.title} zusammen",
            },
        ]
    )
    assert [a.type for a in actions] == ["webhook", "mail_draft", "letter_draft", "ai_task"]
    dumped = dump_actions(actions)
    assert dumped[0] == {
        "type": "webhook",
        "url": "https://example.org/hook",
        "secret": "s" * 16,
        "extra": {},
    }
    with pytest.raises(ValueError, match="Geheimnis"):
        AutomationRuleIn(
            name="x",
            trigger_event_type="ticket.created",
            actions=[{"type": "webhook", "url": "https://example.org/hook"}],
        )
    with pytest.raises(ValueError, match="Zugangsdaten"):
        parse_actions([{"type": "webhook", "url": "https://u:p@example.org/h", "secret": "s" * 16}])
    with pytest.raises(ValueError, match="URL"):
        parse_actions([{"type": "webhook", "url": "ftp://example.org/hook", "secret": "s" * 16}])
    with pytest.raises(ValueError, match="KI-Aufgabe"):
        parse_actions([{"type": "ai_task", "task": "propose_posting", "instruction": "x"}])
    with pytest.raises(ValueError, match="Unbekannte Aktion"):
        parse_actions([{"type": "send_mail", "to": "x@example.org"}])


def test_rule_in_trigger_rules() -> None:
    rule = AutomationRuleIn(
        name="Wöchentlich",
        trigger_kind="schedule",
        schedule={"frequency": "weekly", "time": "08:00", "weekday": 0},
        actions=[{"type": "notify", "role_codes": ["caretaker"], "title": "Wochenstart"}],
    )
    assert rule.trigger_event_type is None
    assert rule.schedule == {"frequency": "weekly", "time": "08:00", "weekday": 0}
    with pytest.raises(ValueError, match="Zeitplan"):
        AutomationRuleIn(
            name="x",
            trigger_kind="schedule",
            actions=[{"type": "notify", "role_codes": ["caretaker"], "title": "t"}],
        )
    with pytest.raises(ValueError, match="nicht möglich"):
        AutomationRuleIn(
            name="x",
            trigger_kind="schedule",
            schedule={"frequency": "daily", "time": "08:00"},
            actions=[{"type": "set_ticket_field", "field": "priority", "value": "high"}],
        )
    with pytest.raises(ValueError, match="festen Empfänger"):
        AutomationRuleIn(
            name="x",
            trigger_kind="schedule",
            schedule={"frequency": "daily", "time": "08:00"},
            actions=[{"type": "letter_draft", "template_id": str(uuid.uuid4())}],
        )
    with pytest.raises(ValueError, match="Ereignistyp"):
        AutomationRuleIn(
            name="x", actions=[{"type": "notify", "role_codes": ["caretaker"], "title": "t"}]
        )
    with pytest.raises(ValueError, match="event oder schedule"):
        AutomationRuleIn(
            name="x",
            trigger_kind="cron",
            actions=[{"type": "notify", "role_codes": ["caretaker"], "title": "t"}],
        )
    # An event rule drops a schedule that was sent along.
    event_rule = AutomationRuleIn(
        name="x",
        trigger_event_type="ticket.created",
        schedule={"frequency": "daily", "time": "08:00"},
        actions=[{"type": "notify", "role_codes": ["caretaker"], "title": "t"}],
    )
    assert event_rule.schedule is None
