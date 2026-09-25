"""Pure rules of the ticket merge (M6, UI in M36): which tickets may be merged and what the
target inherits. Kept free of I/O so the rules are unit tested without a database."""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.tickets.models import Ticket, TicketStatus

MERGE_ASSIGNEE_REASON = "Zusammenführung"


def assert_mergeable(sources: Sequence[Ticket], target: Ticket | None = None) -> None:
    """Refuses closed or already merged tickets, mixed tenants and a target among the sources."""
    tickets = [*sources, *([target] if target is not None else [])]
    if len({t.tenant_id for t in tickets}) != 1:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Tickets gehören zu unterschiedlichen Mandanten."
        )
    if target is not None and any(t.id == target.id for t in sources):
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Ein Ticket kann nicht in sich selbst zusammengeführt werden.",
        )
    for t in tickets:
        if t.status is TicketStatus.CLOSED or t.merged_into_ticket_id is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail=f"Ticket {t.number} ist bereits geschlossen oder zusammengeführt.",
            )


@dataclass(frozen=True)
class AssigneeCarry:
    user_id: uuid.UUID
    reason: str


def assignees_to_carry(
    existing_user_ids: Iterable[uuid.UUID],
    source_assignees: Iterable[uuid.UUID | None],
) -> list[AssigneeCarry]:
    """Assignees of the sources the target does not have yet, in first seen order (append only,
    the target's own assignees stay untouched)."""
    seen = set(existing_user_ids)
    out: list[AssigneeCarry] = []
    for user_id in source_assignees:
        if user_id is None or user_id in seen:
            continue
        seen.add(user_id)
        out.append(AssigneeCarry(user_id=user_id, reason=MERGE_ASSIGNEE_REASON))
    return out


def origin_data(source: Ticket, *, comments: int, messages: int, events: int) -> dict[str, object]:
    """History entry on the target that records where moved entries came from."""
    return {
        "ticket_id": str(source.id),
        "number": source.number,
        "title": source.title,
        "moved": {"comments": comments, "messages": messages, "events": events},
    }
