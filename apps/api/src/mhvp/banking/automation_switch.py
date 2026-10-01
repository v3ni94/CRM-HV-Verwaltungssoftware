"""Automation switch with four eyes and comparison report (AE03; M12-09, BK2-03, ADR 0014).

``comparison``: read only report automation against manual booking. Source is the decision
log ``posting_decision`` (snapshot of the stage 1 proposals and the person's decision). Per
closed round the outcome says what the automation would have done compared with what the
person booked: ``match`` (the top proposal was booked unchanged), ``other_proposal`` (a lower
ranked proposal was booked), ``modified`` (booked with a diff), ``no_proposal`` (booked without
any proposal), ``rejected`` (proposals rejected), ``auto_posted`` and ``reversed``. The report
writes nothing and posts nothing; it is evidence for the G1 opening, not a proof (7.4).

Switch requests: switching the tenant automation on needs gate G1 open, a request with reason
by one person and the approval by another person (never a platform admin). Only the approval
writes ``tenant_settings.auto_posting_enabled``; the runner keeps its own checks.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking.models import (
    AutoPostingSwitchRequest,
    PostingDecision,
    PostingDecisionStatus,
    SwitchRequestStatus,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

OUTCOMES = (
    "match",
    "other_proposal",
    "modified",
    "no_proposal",
    "rejected",
    "auto_posted",
    "reversed",
)
_SKIPPED = {
    PostingDecisionStatus.PENDING.value,
    PostingDecisionStatus.IGNORED.value,
    PostingDecisionStatus.EXPIRED.value,
}


def outcome_of(status: str, chosen_index: int | None, proposals: list[Any] | None) -> str | None:
    """Pure classification of one closed decision round (None: not part of the report)."""
    if status in _SKIPPED:
        return None
    if status == PostingDecisionStatus.AUTO_POSTED.value:
        return "auto_posted"
    if status == PostingDecisionStatus.REVERSED.value:
        return "reversed"
    if status == PostingDecisionStatus.REJECTED.value:
        return "rejected"
    if not proposals:
        return "no_proposal"
    if status == PostingDecisionStatus.MODIFIED.value:
        return "modified"
    if status == PostingDecisionStatus.ACCEPTED_UNCHANGED.value:
        return "match" if (chosen_index or 0) == 0 else "other_proposal"
    return None


async def comparison(
    session: AsyncSession, *, date_from: date | None, date_to: date | None, limit: int
) -> dict[str, Any]:
    stmt = select(PostingDecision).order_by(PostingDecision.decided_at.desc().nulls_last())
    if date_from is not None:
        stmt = stmt.where(PostingDecision.decided_at >= datetime.combine(date_from, time.min, UTC))
    if date_to is not None:
        stmt = stmt.where(PostingDecision.decided_at <= datetime.combine(date_to, time.max, UTC))
    totals: Counter[str] = Counter()
    by_class: dict[str, Counter[str]] = defaultdict(Counter)
    rows: list[dict[str, Any]] = []
    for row in (await session.scalars(stmt)).all():
        outcome = outcome_of(row.status, row.chosen_index, row.proposals)
        if outcome is None:
            continue
        totals[outcome] += 1
        by_class[row.case_kind][outcome] += 1
        if len(rows) < limit:
            rows.append(
                {
                    "decision_id": row.id,
                    "bank_transaction_id": row.bank_transaction_id,
                    "legal_entity_id": row.legal_entity_id,
                    "case_kind": row.case_kind,
                    "status": row.status,
                    "outcome": outcome,
                    "chosen_index": row.chosen_index,
                    "proposal_count": len(row.proposals or []),
                    "best_source": row.best_source,
                    "journal_entry_id": row.journal_entry_id,
                    "decided_at": row.decided_at,
                }
            )
    compared = sum(totals[k] for k in ("match", "other_proposal", "modified", "no_proposal"))
    return {
        "date_from": date_from,
        "date_to": date_to,
        "outcomes": list(OUTCOMES),
        "totals": {k: totals[k] for k in OUTCOMES},
        "by_case_kind": {k: {o: v[o] for o in OUTCOMES} for k, v in sorted(by_class.items())},
        "compared_bookings": compared,
        # Share as string with four decimals (no float for evidence figures).
        "match_rate": f"{totals['match'] / compared:.4f}" if compared else None,
        "rows": rows,
        "note": (
            "Vergleich der Vorschläge der Automatik mit den manuellen Buchungen aus dem "
            "Entscheidungsspeicher. Der Bericht bucht nichts und ist kein Sicherheitsnachweis."
        ),
    }


def switch_out(row: AutoPostingSwitchRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "reason": row.reason,
        "status": row.status,
        "requested_by": row.requested_by,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "decision_comment": row.decision_comment,
        "created_at": row.created_at,
    }


async def list_requests(session: AsyncSession) -> list[AutoPostingSwitchRequest]:
    rows = await session.scalars(
        select(AutoPostingSwitchRequest)
        .order_by(AutoPostingSwitchRequest.created_at.desc())
        .limit(50)
    )
    return list(rows.all())


async def request_switch_on(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    reason: str,
    gate_open: bool,
) -> AutoPostingSwitchRequest:
    from mhvp.platform.models import TenantSettings

    if user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, developer_message="Needs a person.")
    if not gate_open:
        raise ProblemError(
            ErrorCodes.RELEASE_GATE_CLOSED,
            detail="Die Automatik kann erst nach Freigabe G1 eingeschaltet werden.",
        )
    if await session.scalar(select(TenantSettings.auto_posting_enabled)):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Die Automatik ist bereits eingeschaltet.")
    pending = await session.scalar(
        select(AutoPostingSwitchRequest.id).where(
            AutoPostingSwitchRequest.status == SwitchRequestStatus.REQUESTED.value
        )
    )
    if pending is not None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Es liegt bereits ein offener Antrag vor.")
    row = AutoPostingSwitchRequest(
        tenant_id=tenant_id, reason=reason, requested_by=user_id, created_by=user_id
    )
    session.add(row)
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type="tenant.auto_posting_switch_requested",
        entity_type="auto_posting_switch_request",
        entity_id=row.id,
        actor_user_id=user_id,
        payload={"reason": reason},
    )
    return row


async def decide(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    is_platform_admin: bool,
    request_id: uuid.UUID,
    approve: bool,
    comment: str | None,
    gate_open: bool,
) -> AutoPostingSwitchRequest:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(
        select(AutoPostingSwitchRequest)
        .where(AutoPostingSwitchRequest.id == request_id)
        .with_for_update()
    )
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.status != SwitchRequestStatus.REQUESTED.value:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Antrag ist bereits entschieden.")
    if user_id is None or user_id == row.requested_by or is_platform_admin:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
        )
    if approve and not gate_open:
        raise ProblemError(
            ErrorCodes.RELEASE_GATE_CLOSED,
            detail="Die Automatik kann erst nach Freigabe G1 eingeschaltet werden.",
        )
    row.status = (SwitchRequestStatus.APPROVED if approve else SwitchRequestStatus.REJECTED).value
    row.decided_by, row.decided_at, row.decision_comment = user_id, datetime.now(UTC), comment
    row.updated_by = user_id
    if approve:
        settings = await session.scalar(select(TenantSettings).with_for_update())
        if settings is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        settings.auto_posting_enabled = True
        await emit(
            session,
            tenant_id=tenant_id,
            type="tenant.auto_posting_changed",
            entity_type="tenant_settings",
            entity_id=settings.id,
            actor_user_id=user_id,
            payload={"enabled": True, "reason": row.reason, "switch_request_id": str(row.id)},
        )
    await session.flush()
    return row
