"""M36 ticket merge rules (pure): mergeability, request validation, assignee carry over and
the origin entry written to the target's history."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mhvp.core.problems import ProblemError
from mhvp.tickets.merge import (
    MERGE_ASSIGNEE_REASON,
    assert_mergeable,
    assignees_to_carry,
    origin_data,
)
from mhvp.tickets.models import Ticket, TicketStatus
from mhvp.tickets.routers import TicketMergeIn

TENANT = uuid.uuid4()


def _ticket(number: int, **kw: object) -> Ticket:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": TENANT,
        "number": number,
        "title": f"Ticket {number}",
        "status": TicketStatus.NEW,
        "merged_into_ticket_id": None,
        "created_at": datetime(2026, 9, 25, tzinfo=UTC),
    }
    values.update(kw)
    return Ticket(**values)


def test_open_tickets_of_one_tenant_are_mergeable() -> None:
    assert_mergeable([_ticket(1)], _ticket(2))
    assert_mergeable([_ticket(1), _ticket(2)])


@pytest.mark.parametrize(
    "source",
    [
        _ticket(1, status=TicketStatus.CLOSED),
        _ticket(1, merged_into_ticket_id=uuid.uuid4()),
    ],
)
def test_closed_or_merged_source_is_refused(source: Ticket) -> None:
    with pytest.raises(ProblemError):
        assert_mergeable([source], _ticket(2))


def test_merged_target_is_refused() -> None:
    with pytest.raises(ProblemError):
        assert_mergeable([_ticket(1)], _ticket(2, merged_into_ticket_id=uuid.uuid4()))


def test_target_among_sources_and_foreign_tenant_are_refused() -> None:
    target = _ticket(2)
    with pytest.raises(ProblemError):
        assert_mergeable([target], target)
    with pytest.raises(ProblemError):
        assert_mergeable([_ticket(1, tenant_id=uuid.uuid4())], target)


def test_request_needs_two_sources_or_a_target() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValidationError):
        TicketMergeIn(ticket_ids=[a, a])
    assert TicketMergeIn(ticket_ids=[a, b]).target_ticket_id is None
    assert TicketMergeIn(ticket_ids=[a], target_ticket_id=b).target_ticket_id == b
    with pytest.raises(ValidationError):
        TicketMergeIn(ticket_ids=[a], target_ticket_id=a)


def test_assignees_are_appended_once_and_existing_ones_stay() -> None:
    kept, new1, new2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    carried = assignees_to_carry([kept], [None, kept, new1, new2, new1])
    assert [c.user_id for c in carried] == [new1, new2]
    assert {c.reason for c in carried} == {MERGE_ASSIGNEE_REASON}


def test_origin_entry_names_the_source_and_moved_counts() -> None:
    source = _ticket(7)
    data = origin_data(source, comments=2, messages=3, events=4)
    assert data == {
        "ticket_id": str(source.id),
        "number": 7,
        "title": "Ticket 7",
        "moved": {"comments": 2, "messages": 3, "events": 4},
    }
