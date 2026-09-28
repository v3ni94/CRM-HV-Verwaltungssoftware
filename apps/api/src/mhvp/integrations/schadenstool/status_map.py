"""Status mapping between local tickets and the claims adjuster (rule INT-SDT-01, A-072).

The contract draft names ``status`` but no value list. Until the adjuster confirms their list
(open question SDT-03) the outbound mapping below is an assumption. A local status without a
mapping is never pushed. Remote statuses are stored raw on the link and shown; a known value
gets a German label, an unknown value is shown as received. A remote status never changes the
local ticket status in v1.
"""

from __future__ import annotations

from mhvp.tickets.models import TicketStatus

LOCAL_TO_REMOTE: dict[TicketStatus, str] = {
    TicketStatus.NEW: "open",
    TicketStatus.IN_PROGRESS: "in_progress",
    TicketStatus.WAITING: "waiting",
    TicketStatus.DONE: "resolved",
    TicketStatus.CLOSED: "closed",
}

REMOTE_LABELS: dict[str, str] = {
    "open": "Offen",
    "in_progress": "In Bearbeitung",
    "waiting": "Wartet",
    "resolved": "Erledigt",
    "closed": "Geschlossen",
}


def remote_status_for(local: TicketStatus | str) -> str | None:
    try:
        return LOCAL_TO_REMOTE.get(TicketStatus(local))
    except ValueError:
        return None


def remote_status_label(remote: str | None) -> str | None:
    if remote is None:
        return None
    return REMOTE_LABELS.get(remote, remote)
