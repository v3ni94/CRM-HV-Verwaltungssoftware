"""Shared lifecycle helpers of the statement objects (6.9.3, E03, S69-01).

The transition table lives in :mod:`mhvp.billing.status`; this module adds what owner
statements and reserve statements share with the Hausgeldabrechnung: the four eyes rule on the
internal approval, the status log and the check of the referenced postings for ``posted``.
``posted`` never creates an entry here: it only records entries that were posted in the
ledger of the statement (7.1 B05, no overwriting), which keeps the step traceable.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.billing.status import StatementStatus

# Statuses from which the output (PDF) exists; recalculation stays limited to draft and
# calculated (a change after the approval needs a new statement, 6.9.3).
APPROVED_OR_LATER = frozenset(
    {
        StatementStatus.INTERNALLY_APPROVED,
        StatementStatus.BOARD_REVIEWED,
        StatementStatus.RESOLVED,
        StatementStatus.ISSUED,
        StatementStatus.DUE,
        StatementStatus.POSTED,
        StatementStatus.LOCKED,
    }
)
RECALCULABLE = frozenset({StatementStatus.DRAFT, StatementStatus.CALCULATED})
# Targets that make a statement legally relevant towards third parties or the ledger; they
# stay behind the release gate of the statement kind (G3 rental, G4 WEG).
GATED_TARGETS = frozenset({StatementStatus.ISSUED, StatementStatus.DUE, StatementStatus.POSTED})


def four_eyes_violated(actor: uuid.UUID | None, *makers: uuid.UUID | None) -> bool:
    """True when the approving person also created or calculated the statement (6.9.9)."""
    return actor is None or actor in {m for m in makers if m is not None}


def log_entry(
    current: StatementStatus, target: StatementStatus, actor: uuid.UUID | None, note: str | None
) -> dict[str, Any]:
    return {
        "from": current.value,
        "to": target.value,
        "by": str(actor) if actor else None,
        "at": datetime.now(tz=UTC).isoformat(),
        "note": note,
    }


async def posted_entries_of_ledger(
    session: AsyncSession, ledger_id: uuid.UUID, entry_ids: list[uuid.UUID]
) -> list[str] | None:
    """Return the ids when every entry is posted in ``ledger_id``, else ``None``."""
    from mhvp.accounting.models import EntryStatus, JournalEntry

    if not entry_ids:
        return None
    found = set(
        (
            await session.scalars(
                select(JournalEntry.id).where(
                    JournalEntry.id.in_(entry_ids),
                    JournalEntry.ledger_id == ledger_id,
                    JournalEntry.status == EntryStatus.POSTED,
                )
            )
        ).all()
    )
    if found != set(entry_ids):
        return None
    return sorted(str(e) for e in found)
