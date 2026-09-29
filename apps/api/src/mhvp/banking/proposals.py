"""Decision log of the learning bookkeeper (ADR 0014, rule M12-04, plan M12 S1).

Writes ``posting_decision`` rows: a ``pending`` snapshot of the stage 1 proposals per bank
transaction (computed by the Celery task after every import, ``compute_for_run``), refreshed
when the facts changed (``features_hash``), and the closing decision of a person (booked
unchanged or modified with a diff, rejected with reason, ignored with reason). Automatic
postings (``auto_posted``) are not written here; that is the runner of step S6.

Everything is behind ``tenant_settings.learning_bookkeeper_enabled`` (default off): with the
switch off no row is written and the decision helpers are no-ops, so booking, ignoring and
rejecting work exactly as before. The switch never posts, pays or opens a gate; the log is the
ground truth for learning (7.4 no. 6), nothing more.

Concurrency: the import task and a person may work on the same transaction at the same time.
Both lock the transaction row (``SELECT ... FOR UPDATE``, ``matching.lock_for_booking``); the
task re-reads the status after the lock and skips a transaction that is no longer ``new``; the
partial unique index ``uq_posting_decision_pending`` makes a second pending row impossible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import decisions, features, posting_proposal
from mhvp.banking.models import (
    BankTransaction,
    PostingDecision,
    PostingDecisionStatus,
    TransactionStatus,
)
from mhvp.core.problems import ErrorCodes, ProblemError

LEVEL_L0 = "L0"


async def learning_enabled(session: AsyncSession) -> bool:
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(select(TenantSettings.learning_bookkeeper_enabled))
    return bool(value)


async def pending_for(session: AsyncSession, tx_id: uuid.UUID) -> PostingDecision | None:
    row = await session.scalar(
        select(PostingDecision).where(
            PostingDecision.bank_transaction_id == tx_id,
            PostingDecision.status == PostingDecisionStatus.PENDING.value,
        )
    )
    return row if isinstance(row, PostingDecision) else None


async def rounds_of(session: AsyncSession, tx_id: uuid.UUID) -> list[PostingDecision]:
    rows = await session.scalars(
        select(PostingDecision)
        .where(PostingDecision.bank_transaction_id == tx_id)
        .order_by(PostingDecision.round, PostingDecision.created_at)
    )
    return list(rows.all())


async def _next_round(session: AsyncSession, tx_id: uuid.UUID) -> int:
    last = await session.scalar(
        select(func.max(PostingDecision.round)).where(PostingDecision.bank_transaction_id == tx_id)
    )
    return int(last or 0) + 1


async def snapshot(
    session: AsyncSession, tx: BankTransaction
) -> tuple[features.Features, list[dict[str, Any]]]:
    collected = await features.collect(session, tx)
    proposals = posting_proposal.propose(
        collected.tx, collected.rules, collected.open_items, collected.payables
    )
    return collected, [p.as_dict() for p in proposals]


def _new_row(
    tx: BankTransaction,
    collected: features.Features,
    proposals: list[dict[str, Any]],
    *,
    round_no: int,
    status: str,
    sync_run_id: uuid.UUID | None = None,
    supersedes_id: uuid.UUID | None = None,
) -> PostingDecision:
    best = posting_proposal.best([posting_proposal.Proposal(**p) for p in proposals])
    return PostingDecision(
        tenant_id=tx.tenant_id,
        bank_transaction_id=tx.id,
        legal_entity_id=tx.legal_entity_id,
        sync_run_id=sync_run_id or tx.sync_run_id,
        round=round_no,
        status=status,
        engine_version=posting_proposal.ENGINE_VERSION,
        rule_version=collected.rule_version,
        features_hash=collected.hash(),
        features=collected.summary(),
        proposals=proposals,
        case_kind=best.kind if best is not None else posting_proposal.KIND_UNCLEAR,
        level=LEVEL_L0,
        best_source=best.source if best is not None else None,
        best_confidence=Decimal(str(best.confidence)) if best is not None else None,
        supersedes_id=supersedes_id,
    )


def _close(
    row: PostingDecision,
    *,
    status: str,
    user_id: uuid.UUID | None,
    reason: str | None = None,
    chosen_index: int | None = None,
    final: dict[str, Any] | None = None,
    changes: dict[str, Any] | None = None,
    journal_entry_id: uuid.UUID | None = None,
    ai_proposal_id: uuid.UUID | None = None,
    bulk: bool = False,
) -> PostingDecision:
    row.status = status
    row.decided_by = user_id
    row.decided_at = datetime.now(UTC)
    row.reason = reason
    row.chosen_index = chosen_index
    row.final = final
    row.diff = changes
    row.journal_entry_id = journal_entry_id
    row.ai_proposal_id = ai_proposal_id
    row.bulk = bulk
    row.updated_by = user_id
    return row


async def ensure_pending(
    session: AsyncSession, tx: BankTransaction, *, sync_run_id: uuid.UUID | None = None
) -> PostingDecision | None:
    """Pending snapshot for an open transaction: reused when the facts are unchanged,
    otherwise the old one is closed as ``expired`` and a fresh round is inserted. Returns
    ``None`` when the switch is off or the transaction is not open. The caller holds the
    transaction lock or runs inside a savepoint (``IntegrityError`` on a parallel insert)."""
    if tx.status is not TransactionStatus.NEW or not await learning_enabled(session):
        return None
    collected, proposals = await snapshot(session, tx)
    current = await pending_for(session, tx.id)
    digest = collected.hash()
    if current is not None and current.features_hash == digest:
        return current
    supersedes = None
    if current is not None:
        _close(
            current,
            status=PostingDecisionStatus.EXPIRED.value,
            user_id=None,
            reason="Merkmale geändert, neuer Snapshot",
        )
        supersedes = current.id
        await session.flush()
    row = _new_row(
        tx,
        collected,
        proposals,
        round_no=await _next_round(session, tx.id),
        status=PostingDecisionStatus.PENDING.value,
        sync_run_id=sync_run_id,
        supersedes_id=supersedes,
    )
    session.add(row)
    await session.flush()
    return row


async def compute_for_run(session: AsyncSession, run_id: uuid.UUID) -> dict[str, int]:
    """Snapshots for every still open transaction of one sync run, idempotent per run and
    transaction (same hash: no new row). Called by the Celery task after the import
    committed; never inside the import request (no N+1 there)."""
    counts = {"checked": 0, "computed": 0, "skipped": 0}
    if not await learning_enabled(session):
        return counts
    ids = list(
        await session.scalars(
            select(BankTransaction.id)
            .where(
                BankTransaction.sync_run_id == run_id,
                BankTransaction.status == TransactionStatus.NEW,
            )
            .order_by(BankTransaction.booking_date, BankTransaction.created_at)
        )
    )
    for tx_id in ids:
        counts["checked"] += 1
        nested = await session.begin_nested()
        try:
            # The lock serialises against a person booking the same transaction; after it the
            # status is re-read, a booked or ignored transaction gets no snapshot.
            tx = await session.get(
                BankTransaction, tx_id, with_for_update=True, populate_existing=True
            )
            if tx is None or tx.status is not TransactionStatus.NEW:
                counts["skipped"] += 1
                await nested.commit()
                continue
            before = await pending_for(session, tx.id)
            row = await ensure_pending(session, tx, sync_run_id=run_id)
            await nested.commit()
            if row is not None and (before is None or before.id != row.id):
                counts["computed"] += 1
            else:
                counts["skipped"] += 1
        except (IntegrityError, ProblemError):
            # Parallel pending insert or ledger not configured (no ledger, bank account without
            # ledger account): nothing to snapshot, the import stays untouched.
            await nested.rollback()
            counts["skipped"] += 1
    return counts


async def refresh_pending(session: AsyncSession) -> dict[str, int]:
    """Recompute every pending snapshot of the tenant (consumer: contact deleted, review kept).
    Rows whose facts did not change stay as they are."""
    counts = {"checked": 0, "refreshed": 0}
    if not await learning_enabled(session):
        return counts
    tx_ids = list(
        await session.scalars(
            select(PostingDecision.bank_transaction_id).where(
                PostingDecision.status == PostingDecisionStatus.PENDING.value
            )
        )
    )
    for tx_id in tx_ids:
        counts["checked"] += 1
        nested = await session.begin_nested()
        try:
            tx = await session.get(BankTransaction, tx_id, with_for_update=True)
            if tx is None:
                await nested.commit()
                continue
            before = await pending_for(session, tx.id)
            if tx.status is not TransactionStatus.NEW and before is not None:
                _close(
                    before,
                    status=PostingDecisionStatus.EXPIRED.value,
                    user_id=None,
                    reason="Umsatz nicht mehr offen",
                )
                counts["refreshed"] += 1
                await nested.commit()
                continue
            row = await ensure_pending(session, tx)
            await nested.commit()
            if row is not None and before is not None and before.id != row.id:
                counts["refreshed"] += 1
        except (IntegrityError, ProblemError):
            await nested.rollback()
    return counts


async def _open_round(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    proposal_id: uuid.UUID | None,
    status: str,
) -> PostingDecision:
    """The pending row of the transaction, or a fresh snapshot when none exists (a person
    decided before the job ran). A ``proposal_id`` that does not name the pending row is
    stale (409 ``MHVP-BANK-0021``)."""
    current = await pending_for(session, tx.id)
    if proposal_id is not None and (current is None or current.id != proposal_id):
        raise ProblemError(ErrorCodes.BANK_DECISION_STALE)
    if current is not None:
        return current
    collected, proposals = await snapshot(session, tx)
    row = _new_row(
        tx, collected, proposals, round_no=await _next_round(session, tx.id), status=status
    )
    session.add(row)
    await session.flush()
    return row


def _chosen(row: PostingDecision, chosen: int | None) -> int | None:
    try:
        return decisions.reference_index(row.proposals, chosen)
    except ValueError:
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Der gewählte Vorschlag existiert nicht."
        ) from None


async def record_booking(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    journal_entry_id: uuid.UUID,
    user_id: uuid.UUID | None,
    proposal_id: uuid.UUID | None,
    chosen: int | None,
    final: dict[str, Any],
    bulk: bool = False,
) -> PostingDecision | None:
    """Closes the round with ``accepted_unchanged`` or ``modified`` (diff against the chosen
    proposal). Called after ``matching.book_payment`` in the same transaction."""
    if not await learning_enabled(session):
        return None
    row = await _open_round(
        session, tx, proposal_id=proposal_id, status=PostingDecisionStatus.MODIFIED.value
    )
    index = _chosen(row, chosen)
    reference = row.proposals[index] if index is not None else None
    changes = decisions.diff(reference, final)
    return _close(
        row,
        status=decisions.outcome(changes),
        user_id=user_id,
        chosen_index=index,
        final=final,
        changes=changes,
        journal_entry_id=journal_entry_id,
        bulk=bulk,
    )


async def record_rejection(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    user_id: uuid.UUID | None,
    reason: str,
    proposal_id: uuid.UUID | None,
    chosen: int | None,
    ai_proposal_id: uuid.UUID | None = None,
) -> PostingDecision | None:
    """Closes the round as ``rejected`` (transaction stays open) and opens the next round."""
    if not await learning_enabled(session):
        return None
    row = await _open_round(
        session, tx, proposal_id=proposal_id, status=PostingDecisionStatus.REJECTED.value
    )
    index = _chosen(row, chosen)
    _close(
        row,
        status=PostingDecisionStatus.REJECTED.value,
        user_id=user_id,
        reason=reason,
        chosen_index=index,
        ai_proposal_id=ai_proposal_id,
    )
    await session.flush()
    await ensure_pending(session, tx)
    return row


async def record_ignore(
    session: AsyncSession,
    tx: BankTransaction,
    *,
    user_id: uuid.UUID | None,
    reason: str,
    proposal_id: uuid.UUID | None = None,
) -> PostingDecision | None:
    """Closes the round as ``ignored``. Called after the status change of the transaction, so
    ``_open_round`` must not require an open transaction: the snapshot is taken as is."""
    if not await learning_enabled(session):
        return None
    try:
        row = await _open_round(
            session, tx, proposal_id=proposal_id, status=PostingDecisionStatus.IGNORED.value
        )
    except ProblemError as exc:
        if exc.error is ErrorCodes.BANK_DECISION_STALE:
            raise
        # No ledger for the account: nothing to snapshot, ignoring stays possible.
        return None
    return _close(row, status=PostingDecisionStatus.IGNORED.value, user_id=user_id, reason=reason)


async def record_reversal(
    session: AsyncSession,
    *,
    entry_id: uuid.UUID,
    reversal_id: uuid.UUID | None,
    reason_code: str | None,
    reason: str | None,
    actor_user_id: uuid.UUID | None,
    occurred_at: datetime,
) -> list[PostingDecision]:
    """Counter examples for every closed decision that booked ``entry_id``: one ``reversed``
    row per decision (snapshot copied, ``supersedes_id`` links the original). Idempotent: a
    decision with an existing ``reversed`` successor gets no second one."""
    booked = list(
        await session.scalars(
            select(PostingDecision).where(
                PostingDecision.journal_entry_id == entry_id,
                PostingDecision.status.in_(
                    [
                        PostingDecisionStatus.ACCEPTED_UNCHANGED.value,
                        PostingDecisionStatus.MODIFIED.value,
                        PostingDecisionStatus.AUTO_POSTED.value,
                    ]
                ),
            )
        )
    )
    out: list[PostingDecision] = []
    for original in booked:
        existing = await session.scalar(
            select(PostingDecision.id).where(
                PostingDecision.supersedes_id == original.id,
                PostingDecision.status == PostingDecisionStatus.REVERSED.value,
            )
        )
        if existing is not None:
            continue
        row = PostingDecision(
            tenant_id=original.tenant_id,
            bank_transaction_id=original.bank_transaction_id,
            legal_entity_id=original.legal_entity_id,
            sync_run_id=original.sync_run_id,
            round=original.round,
            status=PostingDecisionStatus.REVERSED.value,
            bulk=original.bulk,
            engine_version=original.engine_version,
            rule_version=original.rule_version,
            features_hash=original.features_hash,
            features=original.features,
            proposals=original.proposals,
            case_kind=original.case_kind,
            level=original.level,
            best_source=original.best_source,
            best_confidence=original.best_confidence,
            chosen_index=original.chosen_index,
            final=original.final,
            diff=original.diff,
            reason=f"{reason_code or 'other'}: {reason or ''}".strip()[:2000],
            journal_entry_id=reversal_id,
            supersedes_id=original.id,
            decided_by=actor_user_id,
            decided_at=occurred_at,
        )
        session.add(row)
        out.append(row)
    await session.flush()
    return out


def decision_out(row: PostingDecision) -> dict[str, Any]:
    return {
        "id": row.id,
        "bank_transaction_id": row.bank_transaction_id,
        "legal_entity_id": row.legal_entity_id,
        "round": row.round,
        "status": row.status,
        "bulk": row.bulk,
        "engine_version": row.engine_version,
        "rule_version": row.rule_version,
        "features_hash": row.features_hash,
        "features": row.features,
        "proposals": row.proposals,
        "case_kind": row.case_kind,
        "level": row.level,
        "best_source": row.best_source,
        "best_confidence": row.best_confidence,
        "computed_at": row.computed_at,
        "chosen_index": row.chosen_index,
        "final": row.final,
        "diff": row.diff,
        "reason": row.reason,
        "journal_entry_id": row.journal_entry_id,
        "ai_proposal_id": row.ai_proposal_id,
        "supersedes_id": row.supersedes_id,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
    }
