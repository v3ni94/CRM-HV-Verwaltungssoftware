"""Deletion journal for restores (D47, M9-03, 6.9.5).

A backup restored after a lawful deletion contains documents that were deleted in between.
The journal is derived from the append-only domain events (``document.deleted``,
``document.deletion_refused``, ``document.hold_set``, ``document.hold_cleared``) and exported
before the restore; afterwards it is replayed against the restored database.

Replay rules (conservative by design, rule 0.1.3):

* Only ``document.deleted`` entries are applied. Refusals and holds are carried along for the
  record and never delete anything.
* A document that is absent after the restore needs nothing.
* A document under a deletion hold is never deleted (evidence stays), whatever the journal
  says; the same applies when :func:`mhvp.documents.services.deletion_blocker` names any
  other reason (profile not released, retention not expired).
* The stored hash must equal the hash recorded at the original deletion; otherwise the row is
  not the document that was deleted and stays for manual review.
* Documents with a non pending DMS mirror stay until the mirror deletion is confirmed
  (A42/A43 in ``mhvp.documents``); replay only reports them.
* Every applied deletion and every refusal is recorded as a domain event again, so the
  restored event log is complete.

The store itself (``mhvp.documents.store``, blobs, routers) is not changed here.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import DomainEvent, emit
from mhvp.documents import services as svc
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentMirror, MirrorStatus
from mhvp.platform.models import Tenant

JOURNAL_VERSION = 1
DELETED = "document.deleted"
REFUSED = "document.deletion_refused"
JOURNAL_EVENT_TYPES: tuple[str, ...] = (
    DELETED,
    REFUSED,
    "document.hold_set",
    "document.hold_cleared",
)

# Outcomes of one journal entry during replay.
OUTCOME_DELETED = "deleted"  # applied (only with apply=True)
OUTCOME_WOULD_DELETE = "would_delete"  # dry run
OUTCOME_ABSENT = "absent"  # document not in the restored database
OUTCOME_KEPT_HOLD = "kept_hold"  # deletion hold: evidence is never deleted
OUTCOME_KEPT_BLOCKED = "kept_blocked"  # profile or retention period block the deletion
OUTCOME_KEPT_HASH = "kept_hash_mismatch"  # not the document that was deleted
OUTCOME_KEPT_MIRROR = "kept_mirrored"  # external mirror open (A42/A43)
OUTCOME_SKIPPED = "skipped"  # entry type that is not applied (refusal, hold)
OUTCOME_INVALID = "invalid"  # malformed entry


@dataclass(frozen=True)
class JournalEntry:
    tenant_id: str
    event_id: str
    type: str
    document_id: str | None
    occurred_at: str
    actor_user_id: str | None
    payload: dict[str, Any]

    @classmethod
    def from_event(cls, event: DomainEvent) -> JournalEntry:
        return cls(
            tenant_id=str(event.tenant_id),
            event_id=str(event.id),
            type=event.type,
            document_id=str(event.entity_id) if event.entity_id else None,
            occurred_at=event.occurred_at.astimezone(UTC).isoformat(),
            actor_user_id=str(event.actor_user_id) if event.actor_user_id else None,
            payload=dict(event.payload or {}),
        )


@dataclass
class ReplayResult:
    tenant_id: str
    event_id: str
    document_id: str | None
    outcome: str
    reason: str | None = None


@dataclass
class ReplayReport:
    apply: bool
    results: list[ReplayResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return dict(sorted(Counter(r.outcome for r in self.results).items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "apply": self.apply,
            "counts": self.counts,
            "results": [asdict(r) for r in self.results],
        }


def parse_since(value: str) -> datetime:
    """``YYYY-MM-DD`` (start of day, UTC) or an ISO 8601 timestamp."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


async def export_journal(
    factory: async_sessionmaker[AsyncSession],
    *,
    since: datetime,
    tenant_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Collect the journal events of all (or the given) tenants since ``since``."""
    if tenant_ids is None:
        async with platform_transaction(factory) as session:
            tenant_ids = list(await session.scalars(select(Tenant.id).order_by(Tenant.id)))
    entries: list[JournalEntry] = []
    for tenant_id in tenant_ids:
        async with tenant_transaction(factory, tenant_id) as session:
            rows = (
                await session.scalars(
                    select(DomainEvent)
                    .where(
                        DomainEvent.type.in_(JOURNAL_EVENT_TYPES),
                        DomainEvent.occurred_at >= since,
                    )
                    .order_by(DomainEvent.occurred_at, DomainEvent.id)
                )
            ).all()
            entries.extend(JournalEntry.from_event(e) for e in rows)
    entries.sort(key=lambda e: (e.occurred_at, e.event_id))
    return {
        "version": JOURNAL_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "since": since.isoformat(),
        "tenants": [str(t) for t in tenant_ids],
        "entries": [asdict(e) for e in entries],
    }


def write_journal(journal: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(journal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_journal(path: Path) -> dict[str, Any]:
    journal = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(journal, dict) or journal.get("version") != JOURNAL_VERSION:
        raise ValueError("Unbekanntes Journalformat: version fehlt oder wird nicht unterstützt.")
    if not isinstance(journal.get("entries"), list):
        raise ValueError("Unbekanntes Journalformat: entries fehlt.")
    return journal


def _entry(raw: dict[str, Any]) -> JournalEntry | None:
    try:
        return JournalEntry(
            tenant_id=str(uuid.UUID(str(raw["tenant_id"]))),
            event_id=str(uuid.UUID(str(raw["event_id"]))),
            type=str(raw["type"]),
            document_id=str(uuid.UUID(str(raw["document_id"]))) if raw.get("document_id") else None,
            occurred_at=str(raw.get("occurred_at", "")),
            actor_user_id=str(raw["actor_user_id"]) if raw.get("actor_user_id") else None,
            payload=dict(raw.get("payload") or {}),
        )
    except (KeyError, ValueError, TypeError):
        return None


async def _replay_one(
    session: AsyncSession, entry: JournalEntry, blobs: BlobStore, *, apply: bool, today: date
) -> ReplayResult:
    assert entry.document_id is not None  # noqa: S101 - checked by caller
    tenant_id = uuid.UUID(entry.tenant_id)
    document_id = uuid.UUID(entry.document_id)
    document = await session.get(Document, document_id)
    if document is None:
        return ReplayResult(entry.tenant_id, entry.event_id, entry.document_id, OUTCOME_ABSENT)

    async def refuse(outcome: str, reason: str) -> ReplayResult:
        if apply:
            await emit(
                session,
                tenant_id=tenant_id,
                type=REFUSED,
                entity_type="document",
                entity_id=document_id,
                actor_user_id=None,
                payload={"reason": reason, "replay": True, "journal_event_id": entry.event_id},
            )
        return ReplayResult(entry.tenant_id, entry.event_id, entry.document_id, outcome, reason)

    if document.retention_hold_reason:
        return await refuse(OUTCOME_KEPT_HOLD, f"Löschungssperre: {document.retention_hold_reason}")
    blocker = await svc.deletion_blocker(session, document, today)
    if blocker is not None:
        return await refuse(OUTCOME_KEPT_BLOCKED, blocker)
    recorded = entry.payload.get("sha256")
    if recorded and recorded != document.sha256:
        return await refuse(
            OUTCOME_KEPT_HASH,
            "Der gespeicherte Inhalt weicht vom protokollierten Löschvorgang ab.",
        )
    mirrored = await session.scalar(
        select(DocumentMirror.id).where(
            DocumentMirror.document_id == document.id,
            DocumentMirror.status != MirrorStatus.PENDING,
        )
    )
    if mirrored is not None:
        return await refuse(
            OUTCOME_KEPT_MIRROR,
            "Das Dokument ist in einem externen DMS gespiegelt; die Löschung dort ist offen.",
        )
    if not apply:
        return ReplayResult(
            entry.tenant_id, entry.event_id, entry.document_id, OUTCOME_WOULD_DELETE
        )
    blobs.delete(document.storage_ref)
    await emit(
        session,
        tenant_id=tenant_id,
        type=DELETED,
        entity_type="document",
        entity_id=document_id,
        actor_user_id=None,
        payload={
            "sha256": document.sha256,
            "profile": str(document.retention_profile_id)
            if document.retention_profile_id
            else None,
            "replay": True,
            "journal_event_id": entry.event_id,
            "original_occurred_at": entry.occurred_at,
        },
    )
    await session.delete(document)
    await session.flush()
    return ReplayResult(entry.tenant_id, entry.event_id, entry.document_id, OUTCOME_DELETED)


async def replay_journal(
    factory: async_sessionmaker[AsyncSession],
    journal: dict[str, Any],
    blobs: BlobStore,
    *,
    apply: bool,
    today: date | None = None,
) -> ReplayReport:
    """Apply (or, without ``apply``, only report) the journal against the current database.

    Each deletion runs in its own tenant transaction, so one refusal or error never rolls back
    the others (6.9.13)."""
    today = today or datetime.now(UTC).date()
    report = ReplayReport(apply=apply)
    seen: set[tuple[str, str]] = set()
    for raw in journal["entries"]:
        entry = _entry(raw) if isinstance(raw, dict) else None
        if entry is None:
            report.results.append(ReplayResult("", "", None, OUTCOME_INVALID, "Eintrag unlesbar."))
            continue
        if entry.type != DELETED or entry.document_id is None:
            report.results.append(
                ReplayResult(
                    entry.tenant_id, entry.event_id, entry.document_id, OUTCOME_SKIPPED, entry.type
                )
            )
            continue
        key = (entry.tenant_id, entry.document_id)
        if key in seen:
            report.results.append(
                ReplayResult(
                    entry.tenant_id,
                    entry.event_id,
                    entry.document_id,
                    OUTCOME_SKIPPED,
                    "Dokument bereits in diesem Lauf behandelt.",
                )
            )
            continue
        seen.add(key)
        async with tenant_transaction(factory, uuid.UUID(entry.tenant_id)) as session:
            report.results.append(
                await _replay_one(session, entry, blobs, apply=apply, today=today)
            )
    return report
