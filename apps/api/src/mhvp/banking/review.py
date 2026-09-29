"""Review queue of automatic postings and the one click correction (ADR 0014 addendum, plan
M12 S6, rule M12-05, B03).

* Every automatic posting of level L2 gets a review item due on the next working day; at L3
  only the deterministic sample (``runner.sampled``) gets one with seven days. An overdue
  item blocks its class in the runner until a person with ``accounting:review`` closed it.
* Outcomes: ``ok`` (posting confirmed), ``corrected`` (reversed with reason code and posted
  again through :func:`correct`), ``cancelled`` (reversed only; set by the event consumer when
  the posting was reversed elsewhere).
* ``correct`` is the "Korrigieren" of the operator: exactly B03, a reversal with reason code
  and free text plus one new posting in the same transaction, never an edit of the posted
  entry. It works for automatic and manual postings alike.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting import services as acc
from mhvp.accounting.models import (
    EntrySource,
    EntryStatus,
    JournalEntry,
    LedgerAccount,
    ReversalReason,
)
from mhvp.banking import decisions, matching, proposals
from mhvp.banking import event_types as ev
from mhvp.banking.models import (
    AutoPostingReview,
    BankTransaction,
    PostingDecision,
    ReviewKind,
    ReviewStatus,
    TransactionStatus,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

SAMPLE_DUE_DAYS = 7


def next_working_day(day: date) -> date:
    """Next Monday to Friday after ``day`` (no holiday calendar, assumption A-087)."""
    out = day + timedelta(days=1)
    while out.weekday() >= 5:
        out += timedelta(days=1)
    return out


def due_for(kind: str, today: date) -> date:
    if kind == ReviewKind.SAMPLE.value:
        return today + timedelta(days=SAMPLE_DUE_DAYS)
    return next_working_day(today)


async def open_items(session: AsyncSession, *, today: date) -> list[dict[str, Any]]:
    rows = list(
        await session.scalars(
            select(AutoPostingReview)
            .where(AutoPostingReview.status == ReviewStatus.OPEN.value)
            .order_by(AutoPostingReview.due_on, AutoPostingReview.created_at)
        )
    )
    return [await item_out(session, r, today=today) for r in rows]


async def item_out(session: AsyncSession, row: AutoPostingReview, *, today: date) -> dict[str, Any]:
    tx = await session.get(BankTransaction, row.bank_transaction_id)
    decision = await session.get(PostingDecision, row.posting_decision_id)
    entry = await session.get(JournalEntry, row.journal_entry_id) if row.journal_entry_id else None
    return {
        "id": row.id,
        "posting_decision_id": row.posting_decision_id,
        "bank_transaction_id": row.bank_transaction_id,
        "legal_entity_id": row.legal_entity_id,
        "journal_entry_id": row.journal_entry_id,
        "journal_number": (
            f"{entry.fiscal_year}-{entry.number}" if entry and entry.number else None
        ),
        "ledger_id": entry.ledger_id if entry else None,
        "rule_id": row.rule_id,
        "case_kind": row.case_kind,
        "kind": row.kind,
        "due_on": row.due_on,
        "overdue": row.status == ReviewStatus.OPEN.value and row.due_on < today,
        "status": row.status,
        "note": row.note,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
        "booking_date": tx.booking_date if tx else None,
        "amount": tx.amount if tx else None,
        "counterpart_name": tx.counterpart_name if tx else None,
        "purpose": tx.purpose if tx else None,
        "final": decision.final if decision else None,
        "verifier_fingerprint": decision.verifier_fingerprint if decision else None,
        "reversed": bool(entry and entry.reversed_by_id),
    }


async def decide(
    session: AsyncSession,
    *,
    item_id: uuid.UUID,
    outcome: str,
    note: str | None,
    user_id: uuid.UUID | None,
    tenant_id: uuid.UUID,
) -> AutoPostingReview:
    """A person closes an item. ``ok`` confirms the posting as it is; ``corrected`` and
    ``cancelled`` are only accepted when the posting was actually reversed (B03), otherwise
    the person uses ``correct`` first."""
    row = await session.get(AutoPostingReview, item_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.status != ReviewStatus.OPEN.value:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Die Nachkontrolle ist bereits abgeschlossen."
        )
    if outcome not in (
        ReviewStatus.OK.value,
        ReviewStatus.CORRECTED.value,
        ReviewStatus.CANCELLED.value,
    ):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekanntes Ergebnis.")
    entry = await session.get(JournalEntry, row.journal_entry_id) if row.journal_entry_id else None
    reversed_ = bool(entry and entry.reversed_by_id)
    if outcome == ReviewStatus.OK.value and reversed_:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Die Buchung wurde storniert; Ergebnis ok ist nicht möglich.",
        )
    if outcome != ReviewStatus.OK.value and not reversed_:
        raise ProblemError(
            ErrorCodes.CONFLICT,
            detail="Korrigiert oder aufgehoben setzt einen Storno voraus (Korrigieren nutzen).",
        )
    _close(row, outcome, note, user_id)
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.AUTO_POSTING_REVIEWED,
        entity_type="auto_posting_review",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={
            "outcome": outcome,
            "case_kind": row.case_kind,
            "rule_id": str(row.rule_id) if row.rule_id else None,
        },
    )
    return row


def _close(
    row: AutoPostingReview, outcome: str, note: str | None, user_id: uuid.UUID | None
) -> None:
    row.status = outcome
    row.note = note
    row.reviewed_by = user_id
    row.reviewed_at = datetime.now(UTC)
    row.updated_by = user_id


async def close_for_entry(
    session: AsyncSession,
    *,
    entry_id: uuid.UUID,
    outcome: str,
    note: str | None,
    user_id: uuid.UUID | None,
) -> list[AutoPostingReview]:
    """Closes every open item of a reversed posting (consumer: cancelled; correct: corrected)."""
    rows = list(
        await session.scalars(
            select(AutoPostingReview)
            .where(
                AutoPostingReview.journal_entry_id == entry_id,
                AutoPostingReview.status == ReviewStatus.OPEN.value,
            )
            .with_for_update()
        )
    )
    for row in rows:
        _close(row, outcome, note, user_id)
    await session.flush()
    return rows


@dataclass
class CorrectionIn:
    reason: str
    reason_code: ReversalReason
    settlements: list[tuple[uuid.UUID, Decimal]]
    counter_account_id: uuid.UUID | None
    text: str | None = None
    discount: Decimal = Decimal("0.00")


async def correct(
    session: AsyncSession,
    *,
    tx_id: uuid.UUID,
    body: CorrectionIn,
    user_id: uuid.UUID | None,
    tenant_id: uuid.UUID,
    today: date,
) -> tuple[JournalEntry, JournalEntry]:
    """Storno plus Neubuchung in one transaction (B03): the posting in force of the
    transaction is reversed with reason code and free text, the event
    ``journal_entry.reversed`` is emitted (the consumer writes the counter example row and
    handles rule downgrades), then the transaction is posted again as a manual posting of the
    person with a fresh decision round. Returns (reversal, new entry)."""
    tx = await matching.lock_for_booking(session, tx_id)
    entry = await matching._effective_entry(session, tx.journal_entry_id)
    if entry is None or entry.status is not EntryStatus.POSTED:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Der Umsatz trägt keine gebuchte, nicht stornierte Buchung."
        )
    ledger, _bank = await matching.ledger_for(session, tx)
    booking_date = acc.default_reversal_date(ledger, today)
    reversal = await acc.reverse(
        session,
        ledger,
        entry,
        user_id=user_id,
        reason=body.reason,
        booking_date=booking_date,
        reason_code=body.reason_code,
    )
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.JOURNAL_ENTRY_REVERSED,
        entity_type="journal_entry",
        entity_id=entry.id,
        actor_user_id=user_id,
        payload={
            "reversal_id": str(reversal.id),
            "reason": body.reason,
            "reason_code": body.reason_code.value,
            "bank_transaction_id": str(tx.id),
            "correction": True,
        },
    )
    await close_for_entry(
        session,
        entry_id=entry.id,
        outcome=ReviewStatus.CORRECTED.value,
        note=f"{body.reason_code.value}: {body.reason}"[:2000],
        user_id=user_id,
    )
    tx.status = TransactionStatus.NEW
    tx.matched_rule_id = None
    await session.flush()
    new = await matching.book_payment(
        session,
        tx,
        settlements=body.settlements,
        counter_account_id=body.counter_account_id,
        user_id=user_id,
        source=EntrySource.BANK_IMPORT,
        text=body.text,
        discount=body.discount,
    )
    counter_number = None
    if body.counter_account_id is not None:
        counter = await session.get(LedgerAccount, body.counter_account_id)
        counter_number = counter.number if counter is not None else None
    decision = await proposals.record_booking(
        session,
        tx,
        journal_entry_id=new.id,
        user_id=user_id,
        proposal_id=None,
        chosen=None,
        final=decisions.normalise_final(
            settlements=[{"open_item_id": i, "amount": a} for i, a in body.settlements],
            counter_account_number=counter_number,
            discount=body.discount,
            text=body.text,
        ),
    )
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.BANK_TRANSACTION_CORRECTED,
        entity_type="bank_transaction",
        entity_id=tx.id,
        actor_user_id=user_id,
        payload={
            "reversed_entry_id": str(entry.id),
            "reversal_id": str(reversal.id),
            "journal_entry_id": str(new.id),
            "reason_code": body.reason_code.value,
            "decision_id": str(decision.id) if decision else None,
        },
    )
    return reversal, new
