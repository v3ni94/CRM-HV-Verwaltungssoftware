"""Banking event consumer: watermark job over ``domain_event`` (ADR 0014, plan M12 S0).

Pattern ``mhvp.automation.services.process_tenant``: the beat task reads new rows of
``domain_event`` since the tenant's watermark (``banking_event_watermark``, ordered by
``occurred_at, id``, with a short lag so a transaction that commits late is not skipped) and
handles the event types the learning bookkeeper cares about, each inside a savepoint, so one
failing event neither blocks the others nor the watermark. Accounting never imports banking;
this consumer is how a reversal in the ledger reaches the bank side (plan 3.1 no. 9).

Handled events:

* ``journal_entry.reversed`` (produced by ``POST /accounting/ledgers/{id}/entries/{id}/reverse``):
  the bank transaction(s) that carried the reversed posting are open again (status ``new``,
  the entry id stays as history, B03 Storno plus Neubuchung), every closed decision that booked
  the entry gets a ``reversed`` counter example row (``proposals.record_reversal``), a fresh
  pending snapshot is taken when the switch is on, and ``bank_transaction.posting_reversed``
  is emitted for the audit log and later learning (S3, S5).
* ``bank_transaction.reviewed``: ``ignore`` closes the pending round as ``ignored`` with the
  review reason; ``keep`` takes the pending snapshot.
* ``contact.deleted``: payer evidence (``ContactBankAccount``) changed, so every pending
  snapshot of the tenant is recomputed; closed rows are evidence and stay (retention concept
  is an open operator decision, OPEN_QUESTIONS M12-06).

Nothing here posts, pays or changes a closed decision.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import EntryStatus, JournalEntry
from mhvp.banking import event_types as ev
from mhvp.banking import proposals
from mhvp.banking.models import BankingEventWatermark, BankTransaction, TransactionStatus
from mhvp.core.events import DomainEvent, emit

log = logging.getLogger(__name__)

PROCESS_LAG = timedelta(seconds=5)
BATCH_LIMIT = 500
HANDLED_TYPES = (ev.JOURNAL_ENTRY_REVERSED, ev.BANK_TRANSACTION_REVIEWED, ev.CONTACT_DELETED)


async def process_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, *, now: datetime | None = None
) -> dict[str, int]:
    """Process new banking relevant events of one tenant since its watermark."""
    now = now or datetime.now(UTC)
    cutoff = now - PROCESS_LAG
    totals = {"events": 0, "handled": 0, "failed": 0}
    watermark = await session.scalar(
        select(BankingEventWatermark).where(BankingEventWatermark.tenant_id == tenant_id)
    )
    if watermark is None:
        # First run: start at the current cut-off; older events are history.
        watermark = BankingEventWatermark(
            tenant_id=tenant_id, last_occurred_at=cutoff, last_event_id=None
        )
        session.add(watermark)
        await session.flush()
        return totals
    query = (
        select(DomainEvent)
        .where(
            DomainEvent.tenant_id == tenant_id,
            DomainEvent.occurred_at <= cutoff,
            DomainEvent.type.in_(HANDLED_TYPES),
        )
        .order_by(DomainEvent.occurred_at, DomainEvent.id)
        .limit(BATCH_LIMIT)
    )
    if watermark.last_occurred_at is not None:
        last_at, last_id = watermark.last_occurred_at, watermark.last_event_id
        if last_id is None:
            query = query.where(DomainEvent.occurred_at > last_at)
        else:
            query = query.where(
                (DomainEvent.occurred_at > last_at)
                | ((DomainEvent.occurred_at == last_at) & (DomainEvent.id > last_id))
            )
    events = list(await session.scalars(query))
    for event in events:
        totals["events"] += 1
        nested = await session.begin_nested()
        try:
            await _handle(session, tenant_id, event)
            await nested.commit()
            totals["handled"] += 1
        except Exception:
            await nested.rollback()
            totals["failed"] += 1
            log.exception(
                "banking event consumer failed",
                extra={"tenant_id": str(tenant_id), "event_id": str(event.id)},
            )
    if events:
        watermark.last_occurred_at = events[-1].occurred_at
        watermark.last_event_id = events[-1].id
    watermark.updated_at = now
    await session.flush()
    return totals


async def _handle(session: AsyncSession, tenant_id: uuid.UUID, event: DomainEvent) -> None:
    if event.type == ev.JOURNAL_ENTRY_REVERSED:
        await _on_entry_reversed(session, tenant_id, event)
    elif event.type == ev.BANK_TRANSACTION_REVIEWED:
        await _on_transaction_reviewed(session, event)
    elif event.type == ev.CONTACT_DELETED:
        await proposals.refresh_pending(session)


async def _on_entry_reversed(
    session: AsyncSession, tenant_id: uuid.UUID, event: DomainEvent
) -> None:
    if event.entity_id is None:
        return
    entry = await session.get(JournalEntry, event.entity_id)
    if entry is None or entry.status is not EntryStatus.POSTED or entry.reversed_by_id is None:
        return  # not (or no longer) a reversed posting: nothing to do
    payload: dict[str, Any] = event.payload or {}
    reversal_id = _uuid(payload.get("reversal_id")) or entry.reversed_by_id
    reason_code = payload.get("reason_code")
    rows = await proposals.record_reversal(
        session,
        entry_id=entry.id,
        reversal_id=reversal_id,
        reason_code=reason_code,
        reason=payload.get("reason"),
        actor_user_id=event.actor_user_id,
        occurred_at=event.occurred_at,
    )
    # Every transaction that carried this posting (a transfer pair carries it on both halves)
    # is open again; the entry id stays as history and ``book_payment`` accepts a reversed
    # effective entry (B03 Storno plus Neubuchung).
    txs = list(
        await session.scalars(
            select(BankTransaction)
            .where(
                BankTransaction.journal_entry_id == entry.id,
                BankTransaction.status == TransactionStatus.BOOKED,
            )
            .with_for_update()
        )
    )
    for tx in txs:
        tx.status = TransactionStatus.NEW
        await session.flush()
        await proposals.ensure_pending(session, tx)
        await emit(
            session,
            tenant_id=tenant_id,
            type=ev.BANK_TRANSACTION_POSTING_REVERSED,
            entity_type="bank_transaction",
            entity_id=tx.id,
            actor_user_id=event.actor_user_id,
            payload={
                "journal_entry_id": str(entry.id),
                "reversal_id": str(reversal_id) if reversal_id else None,
                "reason_code": reason_code,
                "decision_ids": [str(r.id) for r in rows if r.bank_transaction_id == tx.id],
                "source_event_id": str(event.id),
            },
        )


async def _on_transaction_reviewed(session: AsyncSession, event: DomainEvent) -> None:
    if event.entity_id is None:
        return
    tx = await session.get(BankTransaction, event.entity_id, with_for_update=True)
    if tx is None:
        return
    payload: dict[str, Any] = event.payload or {}
    if payload.get("decision") == "ignore":
        reason = str(payload.get("reason") or "").strip()
        if not reason:
            # The review endpoint always carries a reason; an event without one (another
            # emitter) is skipped: the log never invents a reason, the round stays pending.
            log.warning("bank_transaction.reviewed without reason skipped", extra={"tx": tx.id})
            return
        pending = await proposals.pending_for(session, tx.id)
        if pending is not None and tx.status is TransactionStatus.IGNORED:
            await proposals.record_ignore(
                session, tx, user_id=event.actor_user_id, reason=reason, proposal_id=pending.id
            )
        return
    if payload.get("decision") == "keep":
        await proposals.ensure_pending(session, tx)


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None
