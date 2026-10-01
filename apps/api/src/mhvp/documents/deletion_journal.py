"""Deletion journal for restores (D47, M9-03, 6.9.5).

A backup restored after a lawful deletion contains documents that were deleted in between.
The journal is derived from the append-only domain events (``document.deleted``,
``document.deletion_refused``, ``document.hold_set``, ``document.hold_cleared`` and, since
AE33, ``document.trashed`` and ``document.restored``) and exported before the restore;
afterwards it is replayed against the restored database.

Replay rules (conservative by design, rule 0.1.3):

* ``document.deleted`` entries are applied. Refusals and holds are carried along for the
  record and never delete anything.
* AE33: ``document.trashed`` and ``document.restored`` entries are applied only when they are
  the last statement about the document in the journal (trashed: move the restored row to the
  trash again with the recorded purge date; restored: take a row that the backup holds in the
  trash out of it). A hold or any other blocker keeps the document where it is, exactly as for
  a deletion, and the hash must match.
* A document that is absent after the restore needs nothing.
* A document under a deletion hold is never deleted (evidence stays), whatever the journal
  says; the same applies when :func:`mhvp.documents.services.deletion_blocker` names any
  other reason (profile not released, retention not expired).
* The stored hash must equal the hash recorded at the original deletion; otherwise the row is
  not the document that was deleted and stays for manual review.
* Documents with a non pending DMS mirror are deleted like any other; their mirror steps
  (Drive delete, Paperless tag ``gelöscht``, operator decision 26.09.2026, M6-03) are
  journaled in the same transaction and queued after it, exactly as in the API deletion
  (``mhvp.documents.mirror_deletion``).
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
from mhvp.documents import mirror_deletion, trash
from mhvp.documents import services as svc
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, DocumentMirror, MirrorStatus
from mhvp.platform.models import Tenant

JOURNAL_VERSION = 1
DELETED = "document.deleted"
REFUSED = "document.deletion_refused"
TRASHED = "document.trashed"
RESTORED = "document.restored"
JOURNAL_EVENT_TYPES: tuple[str, ...] = (
    DELETED,
    REFUSED,
    "document.hold_set",
    "document.hold_cleared",
    TRASHED,
    RESTORED,
)
_LIFECYCLE = (DELETED, TRASHED, RESTORED)

# Outcomes of one journal entry during replay.
OUTCOME_DELETED = "deleted"  # applied (only with apply=True)
OUTCOME_WOULD_DELETE = "would_delete"  # dry run
OUTCOME_TRASHED = "trashed"  # AE33: moved to the trash again (only with apply=True)
OUTCOME_WOULD_TRASH = "would_trash"  # dry run
OUTCOME_UNTRASHED = "restored"  # AE33: taken out of the trash again (only with apply=True)
OUTCOME_WOULD_UNTRASH = "would_restore"  # dry run
OUTCOME_ABSENT = "absent"  # document not in the restored database
OUTCOME_KEPT_HOLD = "kept_hold"  # deletion hold: evidence is never deleted
OUTCOME_KEPT_BLOCKED = "kept_blocked"  # profile or retention period block the deletion
OUTCOME_KEPT_HASH = "kept_hash_mismatch"  # not the document that was deleted
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
    session: AsyncSession,
    entry: JournalEntry,
    blobs: BlobStore,
    *,
    apply: bool,
    today: date,
    pending_jobs: list[mirror_deletion.MirrorDeletionJob],
) -> ReplayResult:
    assert entry.document_id is not None  # noqa: S101 - checked by caller
    tenant_id = uuid.UUID(entry.tenant_id)
    document_id = uuid.UUID(entry.document_id)
    with trash.trashed_visible(session):
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
    if not apply:
        return ReplayResult(
            entry.tenant_id, entry.event_id, entry.document_id, OUTCOME_WOULD_DELETE
        )
    mirrors = (
        await session.scalars(
            select(DocumentMirror).where(
                DocumentMirror.document_id == document.id,
                DocumentMirror.status != MirrorStatus.PENDING,
            )
        )
    ).all()
    jobs = await mirror_deletion.request(
        session,
        tenant_id=tenant_id,
        document_id=document_id,
        mirrors=list(mirrors),
        actor_user_id=None,
    )
    pending_jobs.extend(jobs)
    blobs.delete(document.storage_ref)
    # AC07 (GA08-08): derivatives restored with the backup go again (embeddings, AI extracts).
    from mhvp.documents.deletion_checklist import purge_derivatives

    purged = await purge_derivatives(session, document_id)
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
            "mirror_deletions": len(jobs),
            "storage_ref": document.storage_ref,
            "derivatives": purged,
        },
    )
    await session.delete(document)
    await session.flush()
    return ReplayResult(entry.tenant_id, entry.event_id, entry.document_id, OUTCOME_DELETED)


async def _replay_lifecycle(
    session: AsyncSession, entry: JournalEntry, *, apply: bool, today: date
) -> ReplayResult:
    """AE33: re-apply the last ``document.trashed`` or ``document.restored`` entry."""
    assert entry.document_id is not None  # noqa: S101 - checked by caller
    tenant_id = uuid.UUID(entry.tenant_id)
    document_id = uuid.UUID(entry.document_id)

    def result(outcome: str, reason: str | None = None) -> ReplayResult:
        return ReplayResult(entry.tenant_id, entry.event_id, entry.document_id, outcome, reason)

    with trash.trashed_visible(session):
        document = await session.get(Document, document_id)
        if document is None:
            return result(OUTCOME_ABSENT)
        in_trash = document.deleted_at is not None
        if entry.type == RESTORED:
            if not in_trash:
                return result(OUTCOME_SKIPPED, "Dokument ist nicht im Papierkorb.")
            if not apply:
                return result(OUTCOME_WOULD_UNTRASH)
            await trash.restore(
                session,
                document,
                tenant_id=tenant_id,
                actor_user_id=None,
                reason="Wiederherstellung aus dem Löschjournal",
                extra={"replay": True, "journal_event_id": entry.event_id},
            )
            return result(OUTCOME_UNTRASHED)
        if in_trash:
            return result(OUTCOME_SKIPPED, "Dokument ist bereits im Papierkorb.")
        blocker = await svc.deletion_blocker(session, document, today)
        reason: str | None = None
        outcome = OUTCOME_KEPT_BLOCKED
        if document.retention_hold_reason:
            reason, outcome = (
                f"Löschungssperre: {document.retention_hold_reason}",
                OUTCOME_KEPT_HOLD,
            )
        elif blocker is not None:
            reason = blocker
        elif (recorded := entry.payload.get("sha256")) and recorded != document.sha256:
            reason, outcome = (
                "Der gespeicherte Inhalt weicht vom protokollierten Vorgang ab.",
                OUTCOME_KEPT_HASH,
            )
        if reason is not None:
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
            return result(outcome, reason)
        if not apply:
            return result(OUTCOME_WOULD_TRASH)
        recorded_purge = entry.payload.get("purge_at")
        days = int(entry.payload.get("retention_days") or trash.PROPOSED_DAYS)
        await trash.move_to_trash(
            session,
            document,
            tenant_id=tenant_id,
            actor_user_id=None,
            days=days,
            extra={"replay": True, "journal_event_id": entry.event_id},
        )
        if recorded_purge:
            document.purge_at = datetime.fromisoformat(str(recorded_purge))
        await session.flush()
        return result(OUTCOME_TRASHED)


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
    the others (6.9.13). Mirror steps of deleted documents are queued after each commit
    (``mhvp.documents.mirror_deletion.enqueue``)."""
    today = today or datetime.now(UTC).date()
    report = ReplayReport(apply=apply)
    seen: set[tuple[str, str]] = set()
    # AE33: the last lifecycle statement per document decides whether a trash entry applies.
    last_lifecycle: dict[tuple[str, str], str] = {}
    for raw in journal["entries"]:
        first = _entry(raw) if isinstance(raw, dict) else None
        if first is not None and first.document_id is not None and first.type in _LIFECYCLE:
            last_lifecycle[(first.tenant_id, first.document_id)] = first.event_id
    for raw in journal["entries"]:
        entry = _entry(raw) if isinstance(raw, dict) else None
        if entry is None:
            report.results.append(ReplayResult("", "", None, OUTCOME_INVALID, "Eintrag unlesbar."))
            continue
        if entry.type in (TRASHED, RESTORED) and entry.document_id is not None:
            if last_lifecycle.get((entry.tenant_id, entry.document_id)) != entry.event_id:
                report.results.append(
                    ReplayResult(
                        entry.tenant_id,
                        entry.event_id,
                        entry.document_id,
                        OUTCOME_SKIPPED,
                        "Später wiederhergestellt, in den Papierkorb gelegt oder gelöscht.",
                    )
                )
                continue
            async with tenant_transaction(factory, uuid.UUID(entry.tenant_id)) as session:
                report.results.append(
                    await _replay_lifecycle(session, entry, apply=apply, today=today)
                )
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
        jobs: list[mirror_deletion.MirrorDeletionJob] = []
        async with tenant_transaction(factory, uuid.UUID(entry.tenant_id)) as session:
            report.results.append(
                await _replay_one(
                    session, entry, blobs, apply=apply, today=today, pending_jobs=jobs
                )
            )
        # Mirror steps (M6-03) only after the commit, like the API deletion.
        mirror_deletion.enqueue(jobs)
    return report
