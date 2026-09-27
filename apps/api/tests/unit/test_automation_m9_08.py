"""M9-08 unit tests: computed ticket condition fields (Ticketalter, Fristbezug) and the
``create_task`` action schema (Aufgabe anlegen)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from mhvp.automation.rules import evaluate
from mhvp.automation.schemas import CreateTaskAction, parse_actions
from mhvp.automation.services import ticket_context
from mhvp.tickets.models import Priority, Ticket, TicketSource


def _ticket(**overrides: object) -> Ticket:
    values: dict[str, object] = {
        "tenant_id": uuid.uuid4(),
        "number": "T-1",
        "title": "Testticket",
        "priority": Priority.NORMAL,
        "source": TicketSource.MANUAL,
    }
    values.update(overrides)
    ticket = Ticket(**values)
    created_at = overrides.get("created_at", datetime.now(UTC) - timedelta(days=3))
    assert isinstance(created_at, datetime)
    ticket.created_at = created_at
    return ticket


def test_age_days_and_due_in_days_are_computed() -> None:
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    ticket = _ticket(created_at=now - timedelta(days=10), sla_due_at=now + timedelta(days=2))
    context = {"entity": ticket_context(ticket, now=now)}
    assert context["entity"]["age_days"] == 10
    assert context["entity"]["due_in_days"] == 2


def test_due_in_days_is_none_without_a_deadline() -> None:
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    ticket = _ticket(created_at=now, sla_due_at=None)
    context = {"entity": ticket_context(ticket, now=now)}
    assert context["entity"]["due_in_days"] is None


def test_condition_reads_computed_fields_with_gt_lt() -> None:
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    ticket = _ticket(created_at=now - timedelta(days=31), sla_due_at=now - timedelta(days=1))
    context = {"entity": ticket_context(ticket, now=now)}
    # Ticketalter: mehr als 30 Tage.
    assert evaluate({"field": "entity.age_days", "op": "gt", "value": 30}, context) is True
    # Fristbezug: bereits überfällig (negativer Wert).
    assert evaluate({"field": "entity.due_in_days", "op": "lt", "value": 0}, context) is True


def test_create_task_action_parses_and_rejects_bad_priority() -> None:
    [action] = parse_actions(
        [{"type": "create_task", "title": "Rückruf einplanen", "due_in_days": 3}]
    )
    assert isinstance(action, CreateTaskAction)
    assert action.due_in_days == 3
    with pytest.raises(ValidationError):
        CreateTaskAction(type="create_task", title="x", priority="not-a-priority")
