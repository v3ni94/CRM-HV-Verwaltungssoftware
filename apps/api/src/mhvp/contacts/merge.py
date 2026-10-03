"""Contact merge (M3-03, rule M3-03-kontakt-merge): proposal, check, four eyes, execution.

Every reference to the source contact is re-pointed to the target by a registry derived from
the SQLAlchemy metadata (each foreign key to ``contact.id``), so a table added later is covered
without touching this module. A row that would violate a unique constraint on the target stays
on the source and is reported as a conflict (nothing is deleted, nothing is overwritten). The
source row is marked as merged and hidden, never removed. Booked content is not touched: only
the contact reference of a record moves, amounts and posting lines stay as they are.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.contacts.models import Contact, ContactMerge
from mhvp.core.db.base import Base
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

# Tables that keep pointing at the source: the merge record itself and the erasure history.
_KEEP = {"contact_merge", "privacy_erasure_request"}
# Child tables with one primary row per contact (AM14, GAJ-610): moved rows lose the primary
# flag when the target already has a primary row, so the target keeps exactly one.
_PRIMARY_CHILDREN = ("contact_address", "contact_phone", "contact_email")
# Scalar fields of the target that are filled from the source when empty.
FILL_FIELDS = (
    "salutation",
    "letter_salutation",
    "title",
    "legal_form",
    "position",
    "date_of_birth",
    "preferred_channel",
    "is_consumer",
)


# Polymorphic links without a foreign key: (table, type column, id column, type value).
POLYMORPHIC = (("document_link", "entity_type", "entity_id", "contact"),)


def reference_registry() -> list[tuple[str, str]]:
    """(table, column) of every foreign key to ``contact.id`` that a merge re-points."""
    found: list[tuple[str, str]] = []
    for table in Base.metadata.sorted_tables:
        if table.name in _KEEP:
            continue
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name != "contact" or fk.column.name != "id":
                    continue
                if table.name == "contact" and column.name == "merged_into_id":
                    continue
                found.append((table.name, column.name))
    return found


async def _existing_registry(session: AsyncSession) -> list[tuple[str, str]]:
    """Registry limited to tables of the connected schema (a model ahead of its migration
    must not break a merge)."""
    rows = await session.execute(
        text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()"
        )
    )
    present = {r[0] for r in rows.all()}
    return [(t, c) for t, c in reference_registry() if t in present]


async def check(
    session: AsyncSession, source: Contact, target: Contact
) -> dict[str, list[dict[str, str]]]:
    """Blockers stop the merge, warnings need attention of the reviewer."""
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if source.id == target.id:
        blockers.append({"code": "same_contact", "detail": "Quelle und Ziel sind identisch."})
    for label, c in (("Quelle", source), ("Ziel", target)):
        if c.deleted_at is not None or c.merged_into_id is not None:
            blockers.append(
                {
                    "code": "not_active",
                    "detail": f"{label} ist gelöscht oder bereits zusammengeführt.",
                }
            )
        if c.display_name.startswith("Anonymisiert"):
            blockers.append({"code": "anonymized", "detail": f"{label} ist anonymisiert."})
    if source.kind != target.kind:
        blockers.append(
            {
                "code": "kind_differs",
                "detail": "Person und Firma werden nicht zusammengeführt.",
            }
        )
    open_erasure = await session.scalar(
        text(
            "SELECT count(*) FROM privacy_erasure_request WHERE status IN "
            "('requested', 'approved') AND contact_id IN (:a, :b)"
        ),
        {"a": source.id, "b": target.id},
    )
    if open_erasure:
        blockers.append(
            {
                "code": "erasure_open",
                "detail": "Für einen der Kontakte läuft ein Löschantrag.",
            }
        )
    pending = await session.scalar(
        text(
            "SELECT count(*) FROM contact_bank_account WHERE contact_id = :a "
            "AND approval_status = 'pending'"
        ),
        {"a": source.id},
    )
    if pending:
        blockers.append(
            {
                "code": "bank_account_pending",
                "detail": "Die Quelle hat Bankkonten in laufender Freigabe (Vier-Augen).",
            }
        )
    if (
        source.date_of_birth
        and target.date_of_birth
        and target.date_of_birth != source.date_of_birth
    ):
        warnings.append(
            {"code": "birth_date_differs", "detail": "Geburtsdaten weichen voneinander ab."}
        )
    if source.blocked != target.blocked:
        warnings.append(
            {"code": "blocked_differs", "detail": "Sperrkennzeichen weichen voneinander ab."}
        )
    if source.display_name.strip().lower() != target.display_name.strip().lower():
        warnings.append({"code": "name_differs", "detail": "Die Anzeigenamen weichen ab."})
    counts: dict[str, int] = {}
    for table, column in await _existing_registry(session):
        if table == "contact":
            continue
        n = await session.scalar(
            text(f'SELECT count(*) FROM "{table}" WHERE "{column}" = :c'),  # noqa: S608
            {"c": source.id},
        )
        if n:
            counts[f"{table}.{column}"] = int(n)
    for table, type_col, id_col, value in POLYMORPHIC:
        n = await session.scalar(
            text(
                f'SELECT count(*) FROM "{table}" WHERE "{type_col}" = :v AND "{id_col}" = :c'  # noqa: S608
            ),
            {"v": value, "c": source.id},
        )
        if n:
            counts[f"{table}.{id_col}"] = int(n)
    return {"blockers": blockers, "warnings": warnings, "references": counts}  # type: ignore[dict-item]


async def propose(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    reason: str | None,
    user_id: uuid.UUID | None,
) -> ContactMerge:
    if source_id == target_id:
        raise ProblemError(
            ErrorCodes.CONTACT_MERGE_INVALID, detail="Quelle und Ziel sind identisch."
        )
    source = await session.get(Contact, source_id)
    target = await session.get(Contact, target_id)
    if source is None or target is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    duplicate = await session.scalar(
        select(ContactMerge.id).where(
            ContactMerge.status == "proposed",
            ContactMerge.source_id == source_id,
        )
    )
    if duplicate is not None:
        raise ProblemError(
            ErrorCodes.CONTACT_MERGE_STATE, detail="Für die Quelle liegt schon ein Vorschlag vor."
        )
    result = await check(session, source, target)
    row = ContactMerge(
        tenant_id=tenant_id,
        source_id=source_id,
        target_id=target_id,
        reason=reason,
        check_result=dict(result),
        proposed_by=user_id,
        created_by=user_id,
    )
    session.add(row)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="contact.merge_proposed",
        entity_type="contact",
        entity_id=target_id,
        actor_user_id=user_id,
        payload={"merge_id": str(row.id), "source_id": str(source_id)},
    )
    return row


async def reject(
    session: AsyncSession, row: ContactMerge, *, user_id: uuid.UUID | None, note: str | None
) -> ContactMerge:
    _require_proposed(row)
    row.status = "rejected"
    row.decided_by = user_id
    row.decided_at = datetime.now(UTC)
    row.decision_note = note
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="contact.merge_rejected",
        entity_type="contact",
        entity_id=row.target_id,
        actor_user_id=user_id,
        payload={"merge_id": str(row.id)},
    )
    return row


def _require_proposed(row: ContactMerge) -> None:
    if row.status != "proposed":
        raise ProblemError(ErrorCodes.CONTACT_MERGE_STATE)


async def execute(
    session: AsyncSession, row: ContactMerge, *, user_id: uuid.UUID | None, note: str | None
) -> ContactMerge:
    """Re-checks, then moves all references. Needs a second person than the proposer."""
    _require_proposed(row)
    if row.proposed_by is not None and row.proposed_by == user_id:
        raise ProblemError(ErrorCodes.CONTACT_MERGE_FOUR_EYES)
    source = await session.get(Contact, row.source_id)
    target = await session.get(Contact, row.target_id)
    if source is None or target is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    result = await check(session, source, target)
    row.check_result = dict(result)
    if result["blockers"]:
        raise ProblemError(
            ErrorCodes.CONTACT_MERGE_INVALID,
            detail="Die Prüfung meldet Sperren.",
            extensions={"blockers": result["blockers"]},
        )
    moved: dict[str, int] = {}
    conflicts: dict[str, int] = {}
    target_has_primary: set[str] = set()
    for child in _PRIMARY_CHILDREN:
        found = await session.execute(
            text(f'SELECT 1 FROM "{child}" WHERE contact_id = :t AND is_primary LIMIT 1'),  # noqa: S608
            {"t": target.id},
        )
        if found.first() is not None:
            target_has_primary.add(child)
    for table, column in await _existing_registry(session):
        if table == "contact":
            continue
        ids = (
            (
                await session.execute(
                    text(f'SELECT id FROM "{table}" WHERE "{column}" = :c'),  # noqa: S608
                    {"c": source.id},
                )
            )
            .scalars()
            .all()
        )
        for row_id in ids:
            try:
                async with session.begin_nested():
                    await session.execute(
                        text(f'UPDATE "{table}" SET "{column}" = :t WHERE id = :i'),  # noqa: S608
                        {"t": target.id, "i": row_id},
                    )
                    if table in target_has_primary and column == "contact_id":
                        await session.execute(
                            text(f'UPDATE "{table}" SET is_primary = false WHERE id = :i'),  # noqa: S608
                            {"i": row_id},
                        )
                moved[f"{table}.{column}"] = moved.get(f"{table}.{column}", 0) + 1
            except IntegrityError:
                conflicts[f"{table}.{column}"] = conflicts.get(f"{table}.{column}", 0) + 1
    for table, type_col, id_col, value in POLYMORPHIC:
        ids = (
            (
                await session.execute(
                    text(
                        f'SELECT id FROM "{table}" WHERE "{type_col}" = :v AND "{id_col}" = :c'  # noqa: S608
                    ),
                    {"v": value, "c": source.id},
                )
            )
            .scalars()
            .all()
        )
        for row_id in ids:
            key = f"{table}.{id_col}"
            try:
                async with session.begin_nested():
                    await session.execute(
                        text(f'UPDATE "{table}" SET "{id_col}" = :t WHERE id = :i'),  # noqa: S608
                        {"t": target.id, "i": row_id},
                    )
                moved[key] = moved.get(key, 0) + 1
            except IntegrityError:
                conflicts[key] = conflicts.get(key, 0) + 1
    filled: list[str] = []
    for name in FILL_FIELDS:
        if getattr(target, name) in (None, "") and getattr(source, name) not in (None, ""):
            setattr(target, name, getattr(source, name))
            filled.append(name)
    target.roles = sorted(set(target.roles or []) | set(source.roles or []))
    target.external_ids = {**(source.external_ids or {}), **(target.external_ids or {})}
    tokens = dict.fromkeys(f"{target.search_text} {source.search_text}".split())
    target.search_text = " ".join(tokens)
    target.updated_by = user_id
    now = datetime.now(UTC)
    source.merged_into_id = target.id
    source.merged_at = now
    source.deleted_at = now
    source.updated_by = user_id
    row.status = "executed"
    row.decided_by = user_id
    row.decided_at = now
    row.decision_note = note
    row.result = {"moved": moved, "conflicts": conflicts, "filled_fields": filled}
    await emit(
        session,
        tenant_id=row.tenant_id,
        type="contact.merged",
        entity_type="contact",
        entity_id=target.id,
        actor_user_id=user_id,
        payload={"merge_id": str(row.id), "source_id": str(source.id), **row.result},
    )
    return row


def to_dict(row: ContactMerge) -> dict[str, Any]:
    return {
        "id": row.id,
        "source_id": row.source_id,
        "target_id": row.target_id,
        "status": row.status,
        "reason": row.reason,
        "check_result": row.check_result,
        "proposed_by": row.proposed_by,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "decision_note": row.decision_note,
        "result": row.result,
        "created_at": row.created_at,
    }
