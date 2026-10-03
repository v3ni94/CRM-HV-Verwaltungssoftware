"""Weekly L3 digest with confirmation duty and B09 coupling (plan M12 S10, 7.4 no. 4, M12-02).

Level L3 replaces the daily review of every automatic posting by a deterministic sample
(``runner.sampled``). As compensating controls the plan requires (Produktschutz, not a legal
duty):

* a weekly digest per legal entity (automatic postings, sampled reviews, open reviews,
  findings) that a person confirms before the next week without daily review, and
* the monthly bank reconciliation B09 of the involved accounts as completeness check.

``build_week`` writes one ``auto_posting_digest`` row per legal entity with automatic postings
in the week (idempotent per tenant, legal entity and week start). ``confirm`` requires a
reconciliation without difference and no open sampled review. ``l3_blocked`` is read by the
runner: while a digest of an earlier week is unconfirmed, the sampled classes at L3 are
blocked (no automatic posting), the lower levels stay unaffected.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import event_types as ev
from mhvp.banking.models import (
    AutoPostingDigest,
    AutoPostingReview,
    BankTransaction,
    PostingDecision,
    PostingDecisionStatus,
    ReviewKind,
    ReviewStatus,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError


def week_start_of(day: date) -> date:
    """Monday of the ISO week of ``day``."""
    return day - timedelta(days=day.weekday())


def previous_month(day: date) -> tuple[date, date]:
    """First and last day of the calendar month before ``day``."""
    last = day.replace(day=1) - timedelta(days=1)
    return last.replace(day=1), last


def reconciliation_ok(rows: list[dict[str, Any]]) -> bool:
    """B09 as completeness check: every involved account has at least one statement closing
    in the previous month, and every such statement reconciles (opening plus movements equals
    closing) and, where a ledger account is linked, matches the ledger balance."""
    for row in rows:
        if not row.get("statements"):
            return False
        for st in row["statements"]:
            diff = st.get("statement_difference")
            if diff is None or Decimal(str(diff)) != 0:
                return False
            ledger_diff = st.get("ledger_difference")
            if ledger_diff is not None and Decimal(str(ledger_diff)) != 0:
                return False
    return True


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


async def _reconciliation(
    session: AsyncSession, account_ids: list[uuid.UUID], week_start: date
) -> list[dict[str, Any]]:
    from mhvp.banking.services import reconcile

    first, last = previous_month(week_start)
    out: list[dict[str, Any]] = []
    for account_id in account_ids:
        statements = [
            {k: _jsonable(v) for k, v in row.items()}
            for row in await reconcile(session, account_id, strict=False)
            if row["closing_date"] is not None and first <= row["closing_date"] <= last
        ]
        out.append(
            {
                "property_bank_account_id": str(account_id),
                "month": first.isoformat()[:7],
                "statements": statements,
            }
        )
    return out


async def build_week(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    week_start: date,
    actor_user_id: uuid.UUID | None = None,
) -> list[AutoPostingDigest]:
    """Digest rows of one week (Monday ``week_start``), one per legal entity with automatic
    postings. Existing unconfirmed rows are refreshed, confirmed rows stay as confirmed."""
    week_start = week_start_of(week_start)
    start = datetime.combine(week_start, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=7)
    rows = (
        await session.execute(
            select(
                PostingDecision.id,
                PostingDecision.legal_entity_id,
                BankTransaction.property_bank_account_id,
            )
            .join(BankTransaction, BankTransaction.id == PostingDecision.bank_transaction_id)
            .where(
                PostingDecision.status == PostingDecisionStatus.AUTO_POSTED.value,
                PostingDecision.decided_at >= start,
                PostingDecision.decided_at < end,
            )
        )
    ).all()
    per_entity: dict[uuid.UUID, dict[str, Any]] = {}
    for decision_id, legal_entity_id, account_id in rows:
        bucket = per_entity.setdefault(legal_entity_id, {"decisions": [], "accounts": set()})
        bucket["decisions"].append(decision_id)
        bucket["accounts"].add(account_id)
    out: list[AutoPostingDigest] = []
    for legal_entity_id, bucket in sorted(per_entity.items(), key=lambda kv: str(kv[0])):
        reviews = (
            await session.execute(
                select(AutoPostingReview.status, func.count())
                .where(
                    AutoPostingReview.posting_decision_id.in_(bucket["decisions"]),
                    AutoPostingReview.kind == ReviewKind.SAMPLE.value,
                )
                .group_by(AutoPostingReview.status)
            )
        ).all()
        by_status = {str(s): int(c) for s, c in reviews}
        recon = await _reconciliation(session, sorted(bucket["accounts"], key=str), week_start)
        digest = await session.scalar(
            select(AutoPostingDigest).where(
                AutoPostingDigest.legal_entity_id == legal_entity_id,
                AutoPostingDigest.week_start == week_start,
            )
        )
        created = digest is None
        if digest is None:
            digest = AutoPostingDigest(
                tenant_id=tenant_id, legal_entity_id=legal_entity_id, week_start=week_start
            )
            session.add(digest)
        if digest.confirmed_at is None:
            digest.auto_posted = len(bucket["decisions"])
            digest.sampled = sum(by_status.values())
            digest.reviews_open = by_status.get(ReviewStatus.OPEN.value, 0)
            digest.findings = by_status.get(ReviewStatus.CORRECTED.value, 0) + by_status.get(
                ReviewStatus.CANCELLED.value, 0
            )
            digest.reconciliation = recon
            digest.reconciliation_ok = reconciliation_ok(recon)
        await session.flush()
        if created:
            await emit(
                session,
                tenant_id=tenant_id,
                type=ev.AUTO_POSTING_DIGEST_CREATED,
                entity_type="auto_posting_digest",
                entity_id=digest.id,
                actor_user_id=actor_user_id,
                payload={
                    "legal_entity_id": str(legal_entity_id),
                    "week_start": week_start.isoformat(),
                    "auto_posted": digest.auto_posted,
                    "sampled": digest.sampled,
                    "findings": digest.findings,
                    "reconciliation_ok": digest.reconciliation_ok,
                },
            )
        out.append(digest)
    return out


async def confirm(
    session: AsyncSession, digest: AutoPostingDigest, *, user_id: uuid.UUID
) -> AutoPostingDigest:
    """Confirmation by a person. Refused (MHVP-BANK-0028) while a sampled review is open or
    the B09 reconciliation shows a difference or a missing statement."""
    if digest.confirmed_at is not None:
        return digest
    if digest.reviews_open > 0:
        raise ProblemError(
            ErrorCodes.BANK_DIGEST_NOT_CONFIRMABLE,
            detail="Offene Stichproben-Nachkontrollen müssen zuerst erledigt werden.",
        )
    if not digest.reconciliation_ok:
        raise ProblemError(
            ErrorCodes.BANK_DIGEST_NOT_CONFIRMABLE,
            detail=(
                "Die Bankkontoabstimmung (B09) des Vormonats zeigt eine Differenz oder "
                "ein Kontoauszug fehlt."
            ),
        )
    digest.confirmed_at = datetime.now(UTC)
    digest.confirmed_by = user_id
    digest.updated_by = user_id
    await session.flush()
    await emit(
        session,
        tenant_id=digest.tenant_id,
        type=ev.AUTO_POSTING_DIGEST_CONFIRMED,
        entity_type="auto_posting_digest",
        entity_id=digest.id,
        actor_user_id=user_id,
        payload={
            "legal_entity_id": str(digest.legal_entity_id),
            "week_start": digest.week_start.isoformat(),
        },
    )
    return digest


async def l3_blocked(session: AsyncSession, *, today: date) -> bool:
    """True while a digest of a week before the current one is unconfirmed."""
    pending = await session.scalar(
        select(func.count())
        .select_from(AutoPostingDigest)
        .where(
            AutoPostingDigest.confirmed_at.is_(None),
            AutoPostingDigest.week_start < week_start_of(today),
        )
    )
    return bool(pending)
