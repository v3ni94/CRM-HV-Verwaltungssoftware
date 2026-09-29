"""Learned bank rules from repeated identical decisions of persons (ADR 0014 addendum, plan
M12 3.3 and S5, rule M12-06).

After every decision of a person (booking, rejection) and after every reversal the caller
runs :func:`observe` inside a savepoint (it never breaks the booking). The pattern key is
per legal entity (B01): direction, counterparty (IBAN fingerprint or creditor id) and the
account pattern persons booked against. The trailing streak of consistent decisions comes
from ``mhvp.automation.learning`` (pure functions ``trailing_streak``, ``qualifies``,
``next_status``): a contradiction (another account, a rejection of that account, a reversal)
ends the run and withdraws an open proposal; after a rejection by a person the pattern is
proposed again only at twice the evidence. Bulk confirmations count with half weight.

Thresholds: ``tenant_settings.bank_rule_proposal_threshold`` (default 5) and, for a recurring
pattern (same counterparty, identical amount in every case), the lower
``bank_rule_recurring_threshold`` (default 3); both are assumptions (A-086), never
lower than ``MIN_THRESHOLD``. A proposal books nothing and activates nothing: ``accept``
creates a ``BankRule`` in state ``proposed`` (narrowing allowed, widening refused) that walks
the existing four eyes path; ``supersede`` on activation disables older learned rules of the
same key. Immoware24 journal, imports, drafts and model answers are never a source (7.4 no. 6).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import AccountCategory, JournalEntry, JournalLine, LedgerAccount
from mhvp.automation.learning import Decision, Streak, next_status, trailing_streak
from mhvp.automation.models import PROPOSAL_PROPOSED
from mhvp.banking import event_types as ev
from mhvp.banking.models import (
    BankRule,
    BankRuleProposal,
    BankTransaction,
    PostingDecision,
    PostingDecisionStatus,
    RuleProposalStatus,
    RuleState,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

MIN_THRESHOLD = 2
MAX_THRESHOLD = 50
DEFAULT_THRESHOLD = 5
DEFAULT_RECURRING_THRESHOLD = 3
BULK_WEIGHT = Decimal("0.5")
EVIDENCE_LIMIT = 200
MAX_TOKENS = 5
_TOKEN = re.compile(r"[a-zäöüß]{4,}")
# Words that appear in most purposes and carry no pattern (assumption A-086).
STOP_TOKENS = frozenset(
    {
        "zahlung",
        "ueberweisung",
        "überweisung",
        "rechnung",
        "betrag",
        "danke",
        "vielen",
        "dank",
        "lastschrift",
        "sepa",
        "gutschrift",
        "ref",
        "verwendungszweck",
        "mandat",
        "mandatsref",
    }
)

HUMAN_CLOSED = (
    PostingDecisionStatus.ACCEPTED_UNCHANGED.value,
    PostingDecisionStatus.MODIFIED.value,
    PostingDecisionStatus.REJECTED.value,
    PostingDecisionStatus.REVERSED.value,
)


# Pure helpers (unit tested) ---------------------------------------------------------------


def pattern_key(
    legal_entity_id: Any, direction: str, counterparty: str | None, accounts: str
) -> str | None:
    if not counterparty:
        return None
    return f"{legal_entity_id}|{direction}|{counterparty}|{accounts}"[:200]


def purpose_tokens(purposes: list[str | None], exclude: list[str | None]) -> list[str]:
    """Tokens (letters only, at least four characters, no stop words) contained in every
    purpose, minus tokens of the counterparty names; sorted, at most ``MAX_TOKENS``."""
    sets: list[set[str]] = []
    for purpose in purposes:
        sets.append(set(_TOKEN.findall((purpose or "").lower())) - STOP_TOKENS)
    if not sets:
        return []
    common = set.intersection(*sets)
    names = set()
    for name in exclude:
        names |= set(_TOKEN.findall((name or "").lower()))
    return sorted(common - names)[:MAX_TOKENS]


def weighted_count(streak: Streak | None, bulk_ids: set[str]) -> Decimal:
    if streak is None:
        return Decimal("0")
    return sum(
        (BULK_WEIGHT if d in bulk_ids else Decimal("1") for d in streak.decision_ids),
        Decimal("0"),
    )


def is_recurring(amounts: list[Decimal]) -> bool:
    return len(amounts) >= 2 and len({abs(a) for a in amounts}) == 1


def threshold_for(recurring: bool, *, threshold: int, recurring_threshold: int) -> int:
    value = recurring_threshold if recurring else threshold
    return max(MIN_THRESHOLD, min(MAX_THRESHOLD, int(value)))


def narrows(
    proposal: BankRuleProposal,
    *,
    amount_min: Decimal | None,
    amount_max: Decimal | None,
    tokens: list[str] | None,
) -> list[str]:
    """Reasons an acceptance would widen the proposal (empty: allowed)."""
    out: list[str] = []
    if amount_min is not None and amount_min < proposal.amount_min:
        out.append("Betragsuntergrenze unter der beobachteten Spanne")
    if amount_max is not None and amount_max > proposal.amount_max:
        out.append("Betragsobergrenze über der beobachteten Spanne")
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        out.append("Betragsspanne ungültig")
    if tokens is not None and not set(proposal.purpose_tokens or []) <= set(tokens):
        out.append("Zwecktoken des Vorschlags dürfen nicht entfernt werden")
    return out


# Database side ----------------------------------------------------------------------------


async def thresholds(session: AsyncSession) -> tuple[int, int]:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings))
    if row is None:
        return DEFAULT_THRESHOLD, DEFAULT_RECURRING_THRESHOLD
    return int(row.bank_rule_proposal_threshold), int(row.bank_rule_recurring_threshold)


def _counterparty(tx: BankTransaction) -> tuple[str | None, str | None, str | None]:
    """(key, fingerprint, creditor_id): the fingerprint wins, the creditor id is the fallback."""
    if tx.counterpart_iban_fingerprint:
        return f"fp:{tx.counterpart_iban_fingerprint}", tx.counterpart_iban_fingerprint, None
    if tx.creditor_id:
        return f"cid:{tx.creditor_id}", None, tx.creditor_id
    return None, None, None


async def _pattern_of(
    session: AsyncSession, entry_id: uuid.UUID | None, bank_account_id: uuid.UUID
) -> str | None:
    if entry_id is None:
        return None
    rows = await session.scalars(
        select(LedgerAccount.number)
        .join(JournalLine, JournalLine.account_id == LedgerAccount.id)
        .where(JournalLine.journal_entry_id == entry_id, LedgerAccount.id != bank_account_id)
        .distinct()
    )
    numbers = sorted(set(rows.all()))
    return "+".join(numbers) if numbers else None


async def _decisions_for_key(
    session: AsyncSession, tx: BankTransaction, bank_account_id: uuid.UUID
) -> tuple[list[Decision], set[str], dict[str, tuple[Decimal, str | None, str | None]]]:
    """Decisions of persons for the same counterparty, legal entity and direction, oldest
    first, as ``automation.learning.Decision`` (value = account pattern; a rejection names
    the rejected pattern; a reversal is a Nein for the reversed pattern). Also the ids of bulk
    decisions and per decision the amount, purpose and counterpart name."""
    keys = []
    if tx.counterpart_iban_fingerprint:
        keys.append(BankTransaction.counterpart_iban_fingerprint == tx.counterpart_iban_fingerprint)
    elif tx.creditor_id:
        keys.append(BankTransaction.creditor_id == tx.creditor_id)
    if not keys:
        return [], set(), {}
    direction = BankTransaction.amount > 0 if tx.amount > 0 else BankTransaction.amount < 0
    rows = (
        await session.execute(
            select(PostingDecision, BankTransaction)
            .join(BankTransaction, BankTransaction.id == PostingDecision.bank_transaction_id)
            .where(
                PostingDecision.legal_entity_id == tx.legal_entity_id,
                PostingDecision.status.in_(HUMAN_CLOSED),
                or_(*keys),
                direction,
            )
            .order_by(PostingDecision.decided_at.desc(), PostingDecision.id.desc())
            .limit(EVIDENCE_LIMIT)
        )
    ).all()
    out: list[Decision] = []
    bulk: set[str] = set()
    info: dict[str, tuple[Decimal, str | None, str | None]] = {}
    for decision, other in rows:
        at = decision.decided_at or decision.created_at
        if decision.status == PostingDecisionStatus.REVERSED.value:
            original = (
                await session.get(PostingDecision, decision.supersedes_id)
                if decision.supersedes_id
                else None
            )
            pattern = await _pattern_of(
                session, original.journal_entry_id if original else None, bank_account_id
            )
            if pattern:
                out.append(Decision(str(decision.id), at, str(other.id), rejected=pattern))
            continue
        if decision.status == PostingDecisionStatus.REJECTED.value:
            index = decision.chosen_index
            reference = (
                decision.proposals[index]
                if index is not None and index < len(decision.proposals)
                else None
            )
            rejected = (reference or {}).get("account_number")
            if rejected:
                out.append(Decision(str(decision.id), at, str(other.id), rejected=str(rejected)))
            continue
        if decision.decided_by is None:
            continue  # automatic postings are never a source (7.4 no. 6)
        entry = (
            await session.get(JournalEntry, decision.journal_entry_id)
            if decision.journal_entry_id
            else None
        )
        if entry is None or entry.reversed_by_id is not None:
            continue
        pattern = await _pattern_of(session, entry.id, bank_account_id)
        if not pattern:
            continue
        out.append(Decision(str(decision.id), at, str(other.id), value=pattern))
        if decision.bulk:
            bulk.add(str(decision.id))
        info[str(decision.id)] = (other.amount, other.purpose, other.counterpart_name)
    out.reverse()
    return out, bulk, info


async def _open_proposal(session: AsyncSession, key: str) -> BankRuleProposal | None:
    row = await session.scalar(
        select(BankRuleProposal)
        .where(
            BankRuleProposal.pattern_key == key,
            BankRuleProposal.status == RuleProposalStatus.PROPOSED.value,
        )
        .with_for_update()
    )
    return row if isinstance(row, BankRuleProposal) else None


async def _last_proposal(session: AsyncSession, key: str) -> BankRuleProposal | None:
    row = await session.scalar(
        select(BankRuleProposal)
        .where(BankRuleProposal.pattern_key == key)
        .order_by(BankRuleProposal.created_at.desc())
        .limit(1)
    )
    return row if isinstance(row, BankRuleProposal) else None


async def _existing_rule(
    session: AsyncSession,
    tx: BankTransaction,
    fingerprint: str | None,
    creditor_id: str | None,
    account_id: uuid.UUID | None,
) -> BankRule | None:
    rows = await session.scalars(
        select(BankRule).where(
            BankRule.legal_entity_id == tx.legal_entity_id,
            BankRule.approval_state.in_([RuleState.PROPOSED, RuleState.APPROVED, RuleState.ACTIVE]),
        )
    )
    for rule in rows.all():
        match = rule.match or {}
        same_key = (fingerprint and match.get("counterpart_iban_fingerprint") == fingerprint) or (
            creditor_id and match.get("creditor_id") == creditor_id
        )
        same_account = str(rule.action.get("account_id") or "") == str(account_id or "")
        if same_key and same_account:
            return rule
    return None


async def observe(session: AsyncSession, tx: BankTransaction) -> BankRuleProposal | None:
    """Re-evaluate the pattern of the transaction's counterparty after a decision. Returns
    the open proposal when one exists (now) for the key. Only with the tenant switch."""
    from mhvp.banking.matching import ledger_for
    from mhvp.banking.proposals import learning_enabled

    if not await learning_enabled(session):
        return None
    counterparty, fingerprint, creditor_id = _counterparty(tx)
    if counterparty is None:
        return None
    ledger, bank = await ledger_for(session, tx)
    decisions, bulk_ids, info = await _decisions_for_key(session, tx, bank.id)
    streak = trailing_streak(decisions)
    direction = "credit" if tx.amount > 0 else "debit"
    threshold, recurring_threshold = await thresholds(session)
    if streak is None:
        # Contradiction or nothing yet: withdraw an open proposal of every pattern of the key.
        for pattern in {d.value for d in decisions if d.value} | {
            d.rejected for d in decisions if d.rejected
        }:
            key = pattern_key(tx.legal_entity_id, direction, counterparty, pattern)
            if key:
                await _withdraw(session, tx.tenant_id, key, "Widerspruch in der Entscheidungsfolge")
        return None
    key = pattern_key(tx.legal_entity_id, direction, counterparty, streak.value)
    if key is None:
        return None
    # Other patterns of the same key lost their run: withdraw their open proposals.
    for pattern in {d.value for d in decisions if d.value and d.value != streak.value}:
        other_key = pattern_key(tx.legal_entity_id, direction, counterparty, pattern)
        if other_key:
            await _withdraw(session, tx.tenant_id, other_key, "Anderes Konto gewählt")
    amounts = [info[d][0] for d in streak.decision_ids if d in info]
    recurring = is_recurring(amounts)
    needed = threshold_for(recurring, threshold=threshold, recurring_threshold=recurring_threshold)
    count = weighted_count(streak, bulk_ids)
    last = await _last_proposal(session, key)
    current_status = last.status if last is not None else None
    if count < needed:
        if current_status == RuleProposalStatus.PROPOSED.value:
            await _withdraw(session, tx.tenant_id, key, "Nachweis unter der Schwelle")
        return None
    rejected_count = int(last.rejected_evidence_count or 0) if last is not None else None
    status = next_status(current_status, rejected_count, int(count))
    if status != PROPOSAL_PROPOSED or current_status in (
        RuleProposalStatus.ACCEPTED.value,
        RuleProposalStatus.SUPERSEDED.value,
    ):
        return (
            last if last is not None and last.status == RuleProposalStatus.PROPOSED.value else None
        )
    if current_status == RuleProposalStatus.PROPOSED.value and last is not None:
        last.evidence = _evidence(streak, info)
        last.evidence_count = count
        last.amount_min = min(abs(a) for a in amounts) if amounts else last.amount_min
        last.amount_max = max(abs(a) for a in amounts) if amounts else last.amount_max
        await session.flush()
        return last
    numbers = streak.value.split("+")
    account = None
    if len(numbers) == 1:
        account = await session.scalar(
            select(LedgerAccount).where(
                LedgerAccount.ledger_id == ledger.id, LedgerAccount.number == numbers[0]
            )
        )
    if account is None:
        return None  # split patterns are not learned (one account per rule)
    if await _existing_rule(session, tx, fingerprint, creditor_id, account.id) is not None:
        return None  # dedupe against existing rules
    if direction == "credit":
        action_kind = "debtor_payment" if account.category is AccountCategory.DEBTOR else "posting"
    else:
        action_kind = (
            "creditor_payment" if account.category is AccountCategory.CREDITOR else "posting"
        )
    row = BankRuleProposal(
        tenant_id=tx.tenant_id,
        legal_entity_id=tx.legal_entity_id,
        pattern_key=key,
        direction=direction,
        case_kind=_case_kind(direction, action_kind),
        counterpart_iban_fingerprint=fingerprint,
        creditor_id=creditor_id,
        account_number=account.number,
        account_id=account.id,
        action_kind=action_kind,
        amount_min=min(abs(a) for a in amounts) if amounts else abs(tx.amount),
        amount_max=max(abs(a) for a in amounts) if amounts else abs(tx.amount),
        purpose_tokens=purpose_tokens(
            [info[d][1] for d in streak.decision_ids if d in info],
            [info[d][2] for d in streak.decision_ids if d in info],
        ),
        recurring=recurring,
        threshold=needed,
        evidence=_evidence(streak, info),
        evidence_count=count,
    )
    session.add(row)
    await session.flush()
    await emit(
        session,
        tenant_id=tx.tenant_id,
        type=ev.BANK_RULE_PROPOSAL_CREATED,
        entity_type="bank_rule_proposal",
        entity_id=row.id,
        actor_user_id=None,
        payload={
            "pattern_key": key,
            "evidence_count": str(count),
            "threshold": needed,
            "recurring": recurring,
        },
    )
    return row


def _case_kind(direction: str, action_kind: str) -> str:
    if direction == "credit":
        return "debtor_full" if action_kind == "debtor_payment" else "excluded"
    return "creditor_invoice" if action_kind == "creditor_payment" else "recurring_expense"


def _evidence(
    streak: Streak, info: dict[str, tuple[Decimal, str | None, str | None]]
) -> dict[str, Any]:
    return {
        "decision_ids": list(streak.decision_ids),
        "transaction_ids": sorted(set(streak.addresses)),
        "first_at": streak.first_at.isoformat(),
        "last_at": streak.last_at.isoformat(),
        "amounts": [str(info[d][0]) for d in streak.decision_ids if d in info],
    }


async def _withdraw(session: AsyncSession, tenant_id: uuid.UUID, key: str, reason: str) -> None:
    row = await _open_proposal(session, key)
    if row is None:
        return
    row.status = RuleProposalStatus.WITHDRAWN.value
    row.reason = reason
    row.decided_at = datetime.now(UTC)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.BANK_RULE_PROPOSAL_WITHDRAWN,
        entity_type="bank_rule_proposal",
        entity_id=row.id,
        actor_user_id=None,
        payload={"pattern_key": key, "reason": reason},
    )


async def _locked(session: AsyncSession, proposal_id: uuid.UUID) -> BankRuleProposal:
    row = await session.get(BankRuleProposal, proposal_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.status != RuleProposalStatus.PROPOSED.value:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Vorschlag ist nicht mehr offen.")
    return row


async def accept(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    name: str | None,
    amount_min: Decimal | None,
    amount_max: Decimal | None,
    tokens: list[str] | None,
) -> BankRule:
    """Creates the BankRule (state proposed) from the proposal; narrowing only."""
    row = await _locked(session, proposal_id)
    widened = narrows(row, amount_min=amount_min, amount_max=amount_max, tokens=tokens)
    if widened:
        raise ProblemError(ErrorCodes.BANK_RULE_PROPOSAL_WIDENED, detail="; ".join(widened))
    match: dict[str, Any] = {
        "amount_min": str(amount_min if amount_min is not None else row.amount_min),
        "amount_max": str(amount_max if amount_max is not None else row.amount_max),
    }
    if row.counterpart_iban_fingerprint:
        match["counterpart_iban_fingerprint"] = row.counterpart_iban_fingerprint
    if row.creditor_id:
        match["creditor_id"] = row.creditor_id
    keywords = tokens if tokens is not None else list(row.purpose_tokens or [])
    if keywords:
        match["purpose_keywords"] = sorted(set(keywords))
    rule = BankRule(
        tenant_id=tenant_id,
        created_by=user_id,
        name=(name or f"Gelernt: {row.account_number} ({row.direction})")[:200],
        legal_entity_id=row.legal_entity_id,
        match=match,
        action={
            "kind": row.action_kind,
            "account_id": str(row.account_id) if row.account_id else None,
        },
        learned_from_proposal_id=row.id,
    )
    session.add(rule)
    await session.flush()
    row.status = RuleProposalStatus.ACCEPTED.value
    row.rule_id = rule.id
    row.decided_by, row.decided_at, row.updated_by = user_id, datetime.now(UTC), user_id
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.BANK_RULE_PROPOSAL_ACCEPTED,
        entity_type="bank_rule_proposal",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={"rule_id": str(rule.id), "match": match},
    )
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.BANK_RULE_PROPOSED,
        entity_type="bank_rule",
        entity_id=rule.id,
        actor_user_id=user_id,
        payload={
            "approval_state": rule.approval_state.value,
            "legal_entity_id": str(rule.legal_entity_id),
            "origin": "learned",
            "proposal_id": str(row.id),
        },
    )
    return rule


async def reject(
    session: AsyncSession,
    *,
    proposal_id: uuid.UUID,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    reason: str,
) -> BankRuleProposal:
    row = await _locked(session, proposal_id)
    row.status = RuleProposalStatus.REJECTED.value
    row.reason = reason
    row.rejected_evidence_count = row.evidence_count
    row.decided_by, row.decided_at, row.updated_by = user_id, datetime.now(UTC), user_id
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.BANK_RULE_PROPOSAL_REJECTED,
        entity_type="bank_rule_proposal",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={"reason": reason, "evidence_count": str(row.evidence_count)},
    )
    return row


async def supersede(
    session: AsyncSession, rule: BankRule, *, user_id: uuid.UUID | None
) -> list[BankRule]:
    """Activation of a learned rule disables older learned rules of the same key (legal
    entity, counterparty key, account); hand written rules stay untouched."""
    if rule.learned_from_proposal_id is None:
        return []
    match = rule.match or {}
    rows = await session.scalars(
        select(BankRule).where(
            BankRule.legal_entity_id == rule.legal_entity_id,
            BankRule.id != rule.id,
            BankRule.learned_from_proposal_id.is_not(None),
            BankRule.approval_state.in_([RuleState.APPROVED, RuleState.ACTIVE]),
        )
    )
    out: list[BankRule] = []
    for old in rows.all():
        old_match = old.match or {}
        same_key = (
            match.get("counterpart_iban_fingerprint")
            and old_match.get("counterpart_iban_fingerprint")
            == match.get("counterpart_iban_fingerprint")
        ) or (match.get("creditor_id") and old_match.get("creditor_id") == match.get("creditor_id"))
        if not same_key or old.action.get("account_id") != rule.action.get("account_id"):
            continue
        before = old.approval_state.value
        old.approval_state = RuleState.DISABLED
        old.superseded_by_id = rule.id
        await session.flush()
        await emit(
            session,
            tenant_id=rule.tenant_id,
            type=ev.BANK_RULE_SUPERSEDED,
            entity_type="bank_rule",
            entity_id=old.id,
            actor_user_id=user_id,
            payload={
                "before": before,
                "superseded_by": str(rule.id),
                "legal_entity_id": str(rule.legal_entity_id),
            },
        )
        out.append(old)
    return out


async def on_automation_error(
    session: AsyncSession,
    rule_id: uuid.UUID | None,
    *,
    tenant_id: uuid.UUID,
    reason_code: str | None,
    user_id: uuid.UUID | None,
) -> str | None:
    """Reversal of an automatic posting: every reversal counts as a contradiction of the rule;
    reason code ``automation_error`` lowers an active rule to approved at once and disables it
    at the second within 90 days (plan 3.3). Returns the new state or None."""
    if rule_id is None:
        return None
    rule = await session.get(BankRule, rule_id, with_for_update=True)
    if rule is None:
        return None
    rule.contradiction_count += 1
    if reason_code != "automation_error":
        await session.flush()
        return None
    before = rule.approval_state.value
    if rule.approval_state is RuleState.ACTIVE:
        rule.approval_state = RuleState.APPROVED
    elif rule.approval_state is RuleState.APPROVED:
        rule.approval_state = RuleState.DISABLED
    else:
        await session.flush()
        return None
    rule.max_amount = None
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type=ev.BANK_RULE_DOWNGRADED,
        entity_type="bank_rule",
        entity_id=rule.id,
        actor_user_id=user_id,
        payload={
            "before": before,
            "after": rule.approval_state.value,
            "reason_code": reason_code,
            "contradictions": rule.contradiction_count,
        },
    )
    return rule.approval_state.value


def proposal_out(row: BankRuleProposal) -> dict[str, Any]:
    return {
        "id": row.id,
        "legal_entity_id": row.legal_entity_id,
        "pattern_key": row.pattern_key,
        "status": row.status,
        "direction": row.direction,
        "case_kind": row.case_kind,
        "has_iban_key": row.counterpart_iban_fingerprint is not None,
        "creditor_id": row.creditor_id,
        "account_number": row.account_number,
        "account_id": row.account_id,
        "action_kind": row.action_kind,
        "amount_min": row.amount_min,
        "amount_max": row.amount_max,
        "purpose_tokens": row.purpose_tokens,
        "recurring": row.recurring,
        "threshold": row.threshold,
        "evidence": row.evidence,
        "evidence_count": row.evidence_count,
        "reason": row.reason,
        "rule_id": row.rule_id,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "created_at": row.created_at,
    }


# Retention of the learning store (operator decision M12-06 of 28.09.2026: 24 months). The
# guard trigger of ``posting_decision`` forbids every delete (B03, ADR 0014), so the run
# anonymises instead of deleting: payer fingerprint and proposal evidence are nulled, the
# decision outcome (status, final, diff, reason, entry, decided by and at) stays for the
# audit. The difference to the literal condition is documented in OPEN_QUESTIONS M12-09.
LEARNING_RETENTION_MONTHS = 24
_PROPOSAL_EVIDENCE_KEYS = ("reasoning", "evidence", "label", "text")


def anonymise_features(features: dict[str, Any]) -> dict[str, Any]:
    out = dict(features)
    if "counterpart_iban_fingerprint" in out:
        out["counterpart_iban_fingerprint"] = None
    return out


def anonymise_proposals(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keeps source, kind, confidence, splits and account of every shown proposal; drops the
    free text with identifiers (reasoning, evidence, labels)."""
    out: list[dict[str, Any]] = []
    for p in proposals:
        out.append({k: v for k, v in p.items() if k not in _PROPOSAL_EVIDENCE_KEYS})
    return out


async def anonymise_expired(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    now: datetime | None = None,
    months: int = LEARNING_RETENTION_MONTHS,
) -> dict[str, int]:
    """Anonymises closed decisions and closed rule proposals of one tenant older than the
    retention period. Evidence of rules that are still proposed, approved or active is kept
    (the proposal rows of those rules are skipped). Pending rows are never touched."""
    from mhvp.ai.examples import retention_cutoff

    cutoff = retention_cutoff(now or datetime.now(UTC), months)
    counts = {"decisions": 0, "proposals": 0}
    decisions = list(
        await session.scalars(
            select(PostingDecision)
            .where(
                PostingDecision.tenant_id == tenant_id,
                PostingDecision.status != PostingDecisionStatus.PENDING.value,
                PostingDecision.anonymised_at.is_(None),
                PostingDecision.created_at < cutoff,
            )
            .order_by(PostingDecision.created_at)
            .with_for_update()
        )
    )
    stamp = datetime.now(UTC)
    for row in decisions:
        row.features = anonymise_features(row.features or {})
        row.proposals = anonymise_proposals(row.proposals or [])
        row.anonymised_at = stamp
        counts["decisions"] += 1
    proposals = list(
        await session.scalars(
            select(BankRuleProposal)
            .where(
                BankRuleProposal.tenant_id == tenant_id,
                BankRuleProposal.status != RuleProposalStatus.PROPOSED.value,
                BankRuleProposal.anonymised_at.is_(None),
                BankRuleProposal.created_at < cutoff,
            )
            .order_by(BankRuleProposal.created_at)
            .with_for_update()
        )
    )
    for proposal in proposals:
        if proposal.rule_id is not None:
            rule = await session.get(BankRule, proposal.rule_id)
            if rule is not None and rule.approval_state is not RuleState.DISABLED:
                continue  # evidence of a living rule stays for its lifetime
        proposal.counterpart_iban_fingerprint = None
        proposal.purpose_tokens = []
        proposal.evidence = {}
        proposal.anonymised_at = stamp
        counts["proposals"] += 1
    await session.flush()
    return counts
