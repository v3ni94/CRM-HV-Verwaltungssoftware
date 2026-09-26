"""Status model of all statements (6.9.3, E03, W06, A01). Tables follow in M17/M24.

draft -> calculated -> internally_approved -> [board_reviewed] -> [resolved (WEG only)] -> issued
-> due -> posted -> locked. ``posted`` is only reachable from ``due``; for WEG statements only with
a resolution in status positive, final or legally_binding. A change after ``calculated`` creates a
new version (supersedes_id) instead of moving back.
"""

from enum import StrEnum


class StatementStatus(StrEnum):
    DRAFT = "draft"
    CALCULATED = "calculated"
    INTERNALLY_APPROVED = "internally_approved"
    BOARD_REVIEWED = "board_reviewed"
    RESOLVED = "resolved"
    ISSUED = "issued"
    DUE = "due"
    POSTED = "posted"
    LOCKED = "locked"


RESOLUTION_STATUSES_FOR_POSTING = frozenset({"positive", "final", "legally_binding"})

_NEXT: dict[StatementStatus, set[StatementStatus]] = {
    StatementStatus.DRAFT: {StatementStatus.CALCULATED},
    StatementStatus.CALCULATED: {StatementStatus.INTERNALLY_APPROVED},
    StatementStatus.INTERNALLY_APPROVED: {
        StatementStatus.BOARD_REVIEWED,
        StatementStatus.RESOLVED,
        StatementStatus.ISSUED,
    },
    StatementStatus.BOARD_REVIEWED: {StatementStatus.RESOLVED, StatementStatus.ISSUED},
    StatementStatus.RESOLVED: {StatementStatus.ISSUED},
    StatementStatus.ISSUED: {StatementStatus.DUE},
    StatementStatus.DUE: {StatementStatus.POSTED},
    StatementStatus.POSTED: {StatementStatus.LOCKED},
    StatementStatus.LOCKED: set(),
}


class TransitionError(ValueError):
    pass


def check_transition(
    current: StatementStatus,
    target: StatementStatus,
    *,
    is_hoa: bool,
    resolution_status: str | None = None,
    resolution_snapshot_matches: bool = False,
) -> None:
    """Raise :class:`TransitionError` unless ``current -> target`` is allowed (6.9.3, D13, D14)."""
    if target not in _NEXT[current]:
        # Posting is only reachable from due; for WEG statements the rule D13 (no result claim
        # without a resolution) is named on every earlier refusal as well.
        rule = "D13, 6.9.3" if is_hoa and target is StatementStatus.POSTED else "6.9.3"
        raise TransitionError(f"{current.value} -> {target.value} is not allowed ({rule})")
    if is_hoa:
        if target is StatementStatus.ISSUED and current is not StatementStatus.RESOLVED:
            # A WEG result only becomes a claim through the resolution (W06); issuing before is
            # allowed only as draft information, which is not this status.
            raise TransitionError(
                "WEG statements are issued as result only after the resolution (W06)"
            )
        if target is StatementStatus.RESOLVED and not resolution_snapshot_matches:
            raise TransitionError("the resolution must refer to this snapshot version (D14)")
        if (
            target is StatementStatus.POSTED
            and resolution_status not in RESOLUTION_STATUSES_FOR_POSTING
        ):
            raise TransitionError(
                "posting needs a positive, final or legally binding resolution (D13)"
            )
    elif target is StatementStatus.RESOLVED:
        raise TransitionError("only WEG statements are resolved by the owners (6.9.3)")
