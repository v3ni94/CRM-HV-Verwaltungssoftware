"""Knowledge base context for AI runs (M34-01, audit 29.09.2026).

One place that decides which knowledge entries feed a run, shared by the mail preparation
(``mhvp.communication.preparation``) and the assistant chat (``mhvp.ai.gateway.build_input``):

* only ``approved``, not superseded, not withdrawn, not deleted, currently valid entries of
  the tenant and, when given, of the property (M34-01; the release workflow is untouched);
* one entry per ``group_id`` (the newest version), so a stale duplicate row can never double
  the same rule in a prompt;
* ranked by similarity when embeddings exist (``embeddings.rank_knowledge``), by recency
  otherwise; then capped by count and by characters (``MAX_CONTEXT_ENTRIES``,
  ``MAX_CONTEXT_CHARS``, ``MAX_ENTRY_CHARS``) so the knowledge base can grow without the
  prompt growing with it (input sizing, incident 29.09.2026);
* usage is recorded per entry (``usage_count``, ``last_used_at``) and the used ids are
  returned so the caller can attach them to the run (feedback, proof).

Stale hint (``is_stale``): an approved entry not touched for ``STALE_AFTER_DAYS`` is flagged in
the admin as "lange nicht geprüft". Produktschutz only, no legal meaning, no automatic change.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai.models import AiKnowledgeEntry, AiKnowledgeStatus

STALE_AFTER_DAYS = 180
MAX_CONTEXT_ENTRIES = 30
MAX_CONTEXT_CHARS = 20_000
MAX_ENTRY_CHARS = 2_000


@dataclass(frozen=True)
class UsedEntry:
    id: uuid.UUID
    group_id: uuid.UUID
    version: int
    title: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "group_id": str(self.group_id),
            "version": self.version,
            "title": self.title,
        }


def approved_query(property_id: uuid.UUID | None, today: date) -> Any:
    """Entries that may feed a run (M34-01): approved, live, valid today, of the tenant (RLS)
    and either tenant wide or of ``property_id``."""
    query = select(AiKnowledgeEntry).where(
        AiKnowledgeEntry.deleted_at.is_(None),
        AiKnowledgeEntry.status == AiKnowledgeStatus.APPROVED,
        AiKnowledgeEntry.superseded_at.is_(None),
        (AiKnowledgeEntry.valid_from.is_(None)) | (AiKnowledgeEntry.valid_from <= today),
        (AiKnowledgeEntry.valid_until.is_(None)) | (AiKnowledgeEntry.valid_until >= today),
    )
    if property_id is not None:
        return query.where(
            (AiKnowledgeEntry.property_id.is_(None)) | (AiKnowledgeEntry.property_id == property_id)
        )
    return query.where(AiKnowledgeEntry.property_id.is_(None))


def dedupe_by_group(rows: list[AiKnowledgeEntry]) -> list[AiKnowledgeEntry]:
    """One row per ``group_id`` (highest version wins), order of first appearance kept."""
    best: dict[uuid.UUID, AiKnowledgeEntry] = {}
    order: list[uuid.UUID] = []
    for row in rows:
        current = best.get(row.group_id)
        if current is None:
            order.append(row.group_id)
            best[row.group_id] = row
        elif row.version > current.version:
            best[row.group_id] = row
    return [best[g] for g in order]


def entry_line(row: AiKnowledgeEntry, max_entry_chars: int = MAX_ENTRY_CHARS) -> str:
    content = row.content if len(row.content) <= max_entry_chars else row.content[:max_entry_chars]
    cut = "" if len(row.content) <= max_entry_chars else " [gekürzt]"
    return f"- ({row.kind.value}) {row.title}: {content}{cut}"


def select_for_context(
    rows: list[AiKnowledgeEntry],
    *,
    max_entries: int = MAX_CONTEXT_ENTRIES,
    max_chars: int = MAX_CONTEXT_CHARS,
    max_entry_chars: int = MAX_ENTRY_CHARS,
) -> tuple[str, list[AiKnowledgeEntry]]:
    """Pure: dedupes by group, keeps the first ``max_entries`` whose lines fit ``max_chars``
    in the given (ranked) order. Returns the context text and the entries used."""
    lines: list[str] = []
    used: list[AiKnowledgeEntry] = []
    total = 0
    for row in dedupe_by_group(rows):
        if len(used) >= max_entries:
            break
        line = entry_line(row, max_entry_chars)
        if total + len(line) + 1 > max_chars:
            continue
        lines.append(line)
        used.append(row)
        total += len(line) + 1
    return "\n".join(lines), used


async def context(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    property_id: uuid.UUID | None,
    question: str | None,
    actor: uuid.UUID | None = None,
    max_entries: int = MAX_CONTEXT_ENTRIES,
    max_chars: int = MAX_CONTEXT_CHARS,
    record: bool = True,
) -> tuple[str, list[UsedEntry]]:
    """Context text ("-" when empty) and the entries used, ranked by similarity to
    ``question`` when embeddings exist, newest first otherwise. ``record`` bumps the usage
    counters of the used entries in the caller's transaction."""
    today = datetime.now(UTC).date()
    rows = list(
        await session.scalars(
            approved_query(property_id, today).order_by(AiKnowledgeEntry.created_at.desc())
        )
    )
    if not rows:
        return "-", []
    if question:
        from mhvp.ai import embeddings

        ranked = await embeddings.rank_knowledge(
            session, question, rows, tenant_id=tenant_id, actor=actor, limit=max_entries
        )
        if ranked:
            rows = ranked
    text, used = select_for_context(rows, max_entries=max_entries, max_chars=max_chars)
    if not used:
        return "-", []
    if record:
        await record_usage(session, [r.id for r in used])
    return text, [UsedEntry(r.id, r.group_id, r.version, r.title) for r in used]


async def record_usage(session: AsyncSession, entry_ids: list[uuid.UUID]) -> None:
    if not entry_ids:
        return
    await session.execute(
        update(AiKnowledgeEntry)
        .where(AiKnowledgeEntry.id.in_(entry_ids))
        .values(
            usage_count=AiKnowledgeEntry.usage_count + 1,
            last_used_at=func.now(),
            # Counters are no content change: ``updated_at`` (onupdate) stays, so the stale
            # hint keeps measuring the last edit, not the last use.
            updated_at=AiKnowledgeEntry.updated_at,
        )
        .execution_options(synchronize_session=False)
    )


async def record_feedback(
    session: AsyncSession, entry_ids: list[uuid.UUID], helpful: bool, *, undo: bool = False
) -> int:
    """Feedback "hilfreich / nicht hilfreich" per entry; ``undo`` takes an earlier vote back (never
    below zero). Returns the number of rows updated."""
    if not entry_ids:
        return 0
    column = AiKnowledgeEntry.helpful_count if helpful else AiKnowledgeEntry.unhelpful_count
    values = {
        column.key: func.greatest(column - 1, 0) if undo else column + 1,
        "updated_at": AiKnowledgeEntry.updated_at,
    }
    result = await session.execute(
        update(AiKnowledgeEntry)
        .where(AiKnowledgeEntry.id.in_(entry_ids))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def is_stale(row: AiKnowledgeEntry, now: datetime | None = None) -> bool:
    """Approved, live entry whose last change is older than ``STALE_AFTER_DAYS``. A hint for
    the admin ("lange nicht geprüft"), nothing else changes."""
    if row.status != AiKnowledgeStatus.APPROVED or row.superseded_at is not None:
        return False
    if row.deleted_at is not None:
        return False
    moment = now or datetime.now(UTC)
    reference = row.updated_at or row.created_at
    return reference < moment - timedelta(days=STALE_AFTER_DAYS)
