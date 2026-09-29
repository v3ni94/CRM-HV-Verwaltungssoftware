"""Automatic posting runner of levels L2 and L3 (ADR 0014 addendum, plan M12 S6, rule M12-05).

Runs after every import and sync (``tasks.compute_proposals_once`` calls it once the
snapshots exist) and on ``POST /banking/auto-post``. Per tenant, serialised by an advisory
transaction lock; per transaction in a savepoint with the row lock of ``matching``.

Preconditions, all checked here and never replaced by confidence (0.1.6, 7.4 no. 4):

* tenant switches ``auto_posting_enabled`` and ``learning_bookkeeper_enabled`` (the decision
  log is the protocol of every automatic posting);
* the case class of the transaction is at level L2 or L3 and not blocked by an overdue
  review item;
* G1 is open for the tenant, or the ledger is not the leading system (operator decision
  M12-07 of 28.09.2026: comparison postings by the automation before G1 are allowed);
* an active rule of the legal entity matches and the verifier of the class passes with the
  recomputed case (``verifiers``), the fingerprint is stored on the ``auto_posted`` decision;
* case limits per rule and day, per run and per tenant and day stop the run with an event.

Every automatic posting: ``book_payment`` (created_by None, source bank import), decision
``auto_posted`` with fingerprint and review due date, review item (daily at L2, sampled at
L3 for debtor_full and transfer_pair), event ``bank_transaction.auto_posted``, counters in
the sync run. A missing evidence chain (B05) of a recurring expense yields a clarification
event instead of a posting. Nothing here opens a gate or pays.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import EntrySource, LeadingSystem, Ledger, LedgerAccount
from mhvp.banking import (
    decisions,
    levels,
    matching,
    proposals,
    review,
    verifiers,
)
from mhvp.banking import (
    event_types as ev,
)
from mhvp.banking import posting_proposal as pp
from mhvp.banking.models import (
    AutoPostingReview,
    BankRule,
    BankSyncRun,
    BankTransaction,
    PostingDecision,
    PostingDecisionStatus,
    ReviewKind,
    RuleState,
    TransactionStatus,
)
from mhvp.core.events import emit
from mhvp.core.problems import ProblemError
from mhvp.workspace.services import local_today

log = logging.getLogger(__name__)

# Case limits (product protection, assumption A-087): per rule and day, per run, per tenant
# and day. Reaching one stops the run with ``bank_auto_post.run_stopped``.
RULE_DAY_LIMIT = 50
RUN_LIMIT = 200
TENANT_DAY_LIMIT = 500
# L3 sample: share in percent of the transaction id hash space (plan 3.4, M12-08 open).
SAMPLE_PERCENT = 10

COUNTER_KEYS = (
    "auto_checked",
    "auto_posted",
    "auto_refused",
    "auto_skipped",
    "auto_period_locked",
    "auto_clarification",
    "auto_blocked",
    "auto_gate_closed",
    "auto_limit_stopped",
)


def sampled(tx_id: uuid.UUID) -> bool:
    """Deterministic sample by the hash of the transaction id (stable, reproducible)."""
    digest = hashlib.sha256(str(tx_id).encode()).hexdigest()
    return int(digest[:8], 16) % 100 < SAMPLE_PERCENT


@dataclass
class RunContext:
    tenant_id: uuid.UUID
    today: date
    levels: dict[str, str]
    blocked: dict[str, int]
    gate_open: bool
    outgoing_enabled: bool
    learning: bool
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(COUNTER_KEYS, 0))
    posted_today: int = 0
    posted_this_run: int = 0
    rule_hits_today: dict[uuid.UUID, int] = field(default_factory=dict)
    stopped: str | None = None


async def _settings(session: AsyncSession) -> Any:
    from mhvp.platform.models import TenantSettings

    return await session.scalar(select(TenantSettings))


async def _try_lock(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    got = await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
        {"key": f"bank_auto_post:{tenant_id}"},
    )
    return bool(got)


async def _posted_today(session: AsyncSession, today: date) -> tuple[int, dict[uuid.UUID, int]]:
    start = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    rows = await session.execute(
        select(BankTransaction.matched_rule_id, func.count())
        .join(PostingDecision, PostingDecision.bank_transaction_id == BankTransaction.id)
        .where(
            PostingDecision.status == PostingDecisionStatus.AUTO_POSTED.value,
            PostingDecision.decided_at >= start,
        )
        .group_by(BankTransaction.matched_rule_id)
    )
    per_rule: dict[uuid.UUID, int] = {}
    total = 0
    for rule_id, count in rows.all():
        total += int(count)
        if rule_id is not None:
            per_rule[rule_id] = int(count)
    return total, per_rule


async def context_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, *, gate_open: bool, today: date | None = None
) -> RunContext | None:
    """The run context, or None when the runner is off for the tenant."""
    settings = await _settings(session)
    if settings is None or not settings.auto_posting_enabled:
        return None
    if not settings.learning_bookkeeper_enabled:
        return None
    today = today or local_today()
    current = levels.effective_levels(settings.bookkeeping_automation)
    if all(levels.level_index(v) < levels.level_index(levels.L2) for v in current.values()):
        return None
    posted_today, per_rule = await _posted_today(session, today)
    return RunContext(
        tenant_id=tenant_id,
        today=today,
        levels=current,
        blocked=await levels.overdue_reviews(session, today=today),
        gate_open=gate_open,
        outgoing_enabled=bool(settings.auto_posting_outgoing_enabled),
        learning=True,
        posted_today=posted_today,
        rule_hits_today=per_rule,
    )


async def _account_flags(
    session: AsyncSession, ledger: Ledger
) -> dict[str, verifiers.AccountFlags]:
    rows = list(
        await session.scalars(select(LedgerAccount).where(LedgerAccount.ledger_id == ledger.id))
    )
    return {
        a.number: verifiers.AccountFlags(
            number=a.number,
            category=a.category.value,
            vat_option=a.vat_option.value,
            deductible_vat_rule=a.deductible_vat_rule.value,
            section_35a_eligible=a.section_35a_eligible,
            review_status=a.review_status,
            active=a.active,
            name=a.name,
        )
        for a in rows
    }


async def _active_rules(session: AsyncSession, tx: BankTransaction) -> list[BankRule]:
    rows = await session.scalars(
        select(BankRule)
        .where(
            BankRule.approval_state == RuleState.ACTIVE,
            BankRule.legal_entity_id == tx.legal_entity_id,
        )
        .order_by(BankRule.priority, BankRule.created_at)
    )
    return [r for r in rows.all() if matching.rule_matches(r, tx)]


def _rule_dict(rule: BankRule, collected_rules: list[dict[str, Any]]) -> dict[str, Any]:
    found = next((r for r in collected_rules if str(r.get("id")) == str(rule.id)), None)
    if found is not None:
        return found
    return {
        "id": str(rule.id),
        "name": rule.name,
        "match": rule.match,
        "action": {"kind": rule.action.get("kind"), "account_number": None},
        "approval_state": rule.approval_state.value,
        "max_amount": rule.max_amount,
        "contract_end": None,
    }


async def auto_post_transaction(
    session: AsyncSession, tx: BankTransaction, ctx: RunContext
) -> tuple[str, Any]:
    """One transaction (the caller holds the row lock and a savepoint). Returns the counter
    key and the journal entry when posted."""
    if tx.status is not TransactionStatus.NEW:
        return "auto_skipped", None
    collected, snapshot = await proposals.snapshot(session, tx)
    case_kind = levels.classify(collected.tx, snapshot)
    level = ctx.levels.get(case_kind, levels.L0)
    if levels.level_index(level) < levels.level_index(levels.L2):
        return "auto_skipped", None
    if ctx.blocked.get(case_kind):
        return "auto_blocked", None
    ledger, _bank = await matching.ledger_for(session, tx)
    if ledger.leading_system is not LeadingSystem.IMMOWARE24 and not ctx.gate_open:
        # Leading ledger and G1 closed: nothing productive (18.0, ADR 0003).
        return "auto_gate_closed", None
    rules = await _active_rules(session, tx)
    if not rules:
        return "auto_skipped", None
    accounts = await _account_flags(session, ledger)
    verification: verifiers.Verification | None = None
    rule_row: BankRule | None = None
    for candidate in rules:
        if ctx.rule_hits_today.get(candidate.id, 0) >= RULE_DAY_LIMIT:
            ctx.stopped = f"Fallgrenze je Regel und Tag ({RULE_DAY_LIMIT}) erreicht"
            return "auto_limit_stopped", None
        vctx = verifiers.Context(
            rule=_rule_dict(candidate, collected.rules),
            accounts=accounts,
            engine_version=pp.ENGINE_VERSION,
            rule_version=collected.rule_version,
            features_hash=collected.hash(),
            locked_until=ledger.locked_until,
            outgoing_enabled=ctx.outgoing_enabled,
        )
        verification = verifiers.verify(
            case_kind,
            collected.tx,
            snapshot,
            open_items=collected.open_items,
            payables=collected.payables,
            ctx=vctx,
        )
        rule_row = candidate
        if verification.ok or verification.skipped or verification.clarification:
            break
    assert verification is not None  # noqa: S101 - rules are not empty
    assert rule_row is not None  # noqa: S101
    if verification.skipped:
        return "auto_period_locked", None
    if verification.clarification:
        await emit(
            session,
            tenant_id=ctx.tenant_id,
            type=ev.BANK_TRANSACTION_CLARIFICATION,
            entity_type="bank_transaction",
            entity_id=tx.id,
            actor_user_id=None,
            payload={
                "case_kind": case_kind,
                "rule_id": str(rule_row.id),
                "reasons": verification.reasons,
            },
        )
        return "auto_clarification", None
    if not verification.ok:
        return "auto_refused", None
    if ctx.posted_this_run >= RUN_LIMIT:
        ctx.stopped = f"Fallgrenze je Lauf ({RUN_LIMIT}) erreicht"
        return "auto_limit_stopped", None
    if ctx.posted_today >= TENANT_DAY_LIMIT:
        ctx.stopped = f"Fallgrenze je Tag ({TENANT_DAY_LIMIT}) erreicht"
        return "auto_limit_stopped", None
    counter_id = None
    if verification.counter_account_number is not None:
        counter = await session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.ledger_id == ledger.id,
                LedgerAccount.number == verification.counter_account_number,
            )
        )
        if counter is None:
            return "auto_refused", None
        counter_id = counter.id
    settlements = [
        (uuid.UUID(s["open_item_id"]), Decimal(s["amount"])) for s in verification.settlements
    ]
    entry = await matching.book_payment(
        session,
        tx,
        settlements=settlements,
        counter_account_id=counter_id,
        user_id=None,
        source=EntrySource.BANK_IMPORT,
    )
    tx.matched_rule_id = rule_row.id
    rule_row.hit_count += 1
    rule_row.last_hit_at = datetime.now(UTC)
    kind = ReviewKind.DAILY.value
    due: date | None = review.due_for(kind, ctx.today)
    if level == levels.L3 and case_kind in levels.SAMPLED_CLASSES:
        if sampled(tx.id):
            kind = ReviewKind.SAMPLE.value
            due = review.due_for(kind, ctx.today)
        else:
            due = None
    decision = await _record_auto(
        session,
        tx,
        collected,
        snapshot,
        case_kind=case_kind,
        level=level,
        entry_id=entry.id,
        verification=verification,
        counter_number=verification.counter_account_number,
        due=due,
    )
    if due is not None:
        session.add(
            AutoPostingReview(
                tenant_id=tx.tenant_id,
                posting_decision_id=decision.id,
                bank_transaction_id=tx.id,
                legal_entity_id=tx.legal_entity_id,
                journal_entry_id=entry.id,
                rule_id=rule_row.id,
                case_kind=case_kind,
                kind=kind,
                due_on=due,
            )
        )
    await session.flush()
    await emit(
        session,
        tenant_id=ctx.tenant_id,
        type=ev.BANK_TRANSACTION_AUTO_POSTED,
        entity_type="bank_transaction",
        entity_id=tx.id,
        actor_user_id=None,
        payload={
            "journal_entry_id": str(entry.id),
            "decision_id": str(decision.id),
            "case_kind": case_kind,
            "level": level,
            "rule_id": str(rule_row.id),
            "verifier_fingerprint": verification.fingerprint,
            "review_due_on": due.isoformat() if due else None,
            "review_kind": kind if due else None,
        },
    )
    ctx.posted_this_run += 1
    ctx.posted_today += 1
    ctx.rule_hits_today[rule_row.id] = ctx.rule_hits_today.get(rule_row.id, 0) + 1
    return "auto_posted", entry


async def _record_auto(
    session: AsyncSession,
    tx: BankTransaction,
    collected: Any,
    snapshot: list[dict[str, Any]],
    *,
    case_kind: str,
    level: str,
    entry_id: uuid.UUID,
    verification: verifiers.Verification,
    counter_number: str | None,
    due: date | None,
) -> PostingDecision:
    final = decisions.normalise_final(
        settlements=[
            {"open_item_id": s["open_item_id"], "amount": s["amount"]}
            for s in verification.settlements
        ],
        counter_account_number=counter_number,
        discount="0.00",
        text=None,
    )
    pending = await proposals.pending_for(session, tx.id)
    if pending is not None and pending.features_hash == collected.hash():
        row = pending
        row.status = PostingDecisionStatus.AUTO_POSTED.value
    else:
        if pending is not None:
            proposals._close(
                pending,
                status=PostingDecisionStatus.EXPIRED.value,
                user_id=None,
                reason="Merkmale geändert, Automatiklauf",
            )
            await session.flush()
        row = proposals._new_row(
            tx,
            collected,
            snapshot,
            round_no=await proposals._next_round(session, tx.id),
            status=PostingDecisionStatus.AUTO_POSTED.value,
            supersedes_id=pending.id if pending is not None else None,
        )
        session.add(row)
    row.level = level
    row.decided_by = None
    row.decided_at = datetime.now(UTC)
    row.reason = f"{case_kind}: " + "; ".join(verification.reasons)
    row.final = final
    row.diff = {}
    row.journal_entry_id = entry_id
    row.verifier_fingerprint = verification.fingerprint
    row.review_due_on = due
    await session.flush()
    return row


async def run_for_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    gate_open: bool,
    run_id: uuid.UUID | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """The runner over every open transaction of the tenant in chronological order."""
    ctx = await context_for_tenant(session, tenant_id, gate_open=gate_open, today=today)
    if ctx is None:
        return {"enabled": False, "posted": 0}
    if not await _try_lock(session, tenant_id):
        return {"enabled": True, "posted": 0, "locked": True}
    ids = list(
        await session.scalars(
            select(BankTransaction.id)
            .where(BankTransaction.status == TransactionStatus.NEW)
            .order_by(BankTransaction.booking_date, BankTransaction.created_at)
        )
    )
    for tx_id in ids:
        if ctx.stopped:
            break
        ctx.counts["auto_checked"] += 1
        nested = await session.begin_nested()
        try:
            tx = await matching.lock_for_booking(session, tx_id)
            key, _entry = await auto_post_transaction(session, tx, ctx)
            await nested.commit()
            ctx.counts[key] += 1
        except (ProblemError, IntegrityError) as exc:
            await nested.rollback()
            ctx.counts["auto_refused"] += 1
            log.info("auto post refused", extra={"tx": str(tx_id), "error": str(exc)})
    if ctx.stopped:
        await emit(
            session,
            tenant_id=tenant_id,
            type=ev.AUTO_POST_RUN_STOPPED,
            entity_type="bank_sync_run",
            entity_id=run_id,
            actor_user_id=None,
            payload={"reason": ctx.stopped, **ctx.counts},
        )
    if run_id is not None:
        run = await session.get(BankSyncRun, run_id, with_for_update=True)
        if run is not None:
            run.counts = {**(run.counts or {}), **ctx.counts}
    await session.flush()
    return {
        "enabled": True,
        "posted": ctx.counts["auto_posted"],
        "checked": ctx.counts["auto_checked"],
        **ctx.counts,
    }
