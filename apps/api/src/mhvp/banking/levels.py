"""Case classes and automation levels of the learning bookkeeper (ADR 0014 addendum, plan M12
3.4 and S4, rule M12-05).

Case classes (``CASE_CLASSES``) route every bank transaction to one deterministic path:

* ``debtor_full``: one incoming payment settles exactly one open receivable in full
  (``posting_proposal`` kind ``full``, unambiguous).
* ``debtor_collective``: one incoming payment settles exactly one combination of open
  receivables (kind ``collective``); capped at L1 (7.4 no. 4: collective payments stay a
  decision of a person, one click at most).
* ``creditor_invoice``: outgoing payment of a posted invoice linked to the transaction
  (source ``invoice``); the account assignment comes from the invoice.
* ``recurring_expense``: outgoing payment against a ledger account by an active rule of
  action kind ``posting`` (L2b, only with ``auto_posting_outgoing_enabled`` and the B05
  evidence chain check in the verifier).
* ``transfer_pair``: recognised transfer between two own bank accounts (D04).
* ``excluded``: returns, deposits, partial and over payments, unclear cases and everything
  else; the only level is L0 (7.4 no. 4 and 5, M10-03, W07).

Levels (``LEVELS``): L0 proposal only, L1 one click and bulk confirmation of verified
proposals (every posting stays a manual posting of a person), L2 rule automation with daily
review, L3 automation with sampling (debtor_full and transfer_pair only). Levels are set per
tenant and class in ``tenant_settings.bookkeeping_automation``; raising a level needs a
request by one person and the release by another (``BookkeepingLevelRequest``), lowering is
immediate and is also done by the platform itself (``downgrade``). Thresholds
(``ELIGIBILITY``) are product protection standards without empirical basis (assumptions
A-085, docs/ASSUMPTIONS.md), never a legal requirement, and never lower per tenant. Nothing
here posts, and no level opens a gate: the runner checks G1 or a non leading ledger itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import event_types as ev
from mhvp.banking import posting_proposal as pp
from mhvp.banking.models import (
    AutoPostingReview,
    BookkeepingLevelRequest,
    LevelRequestStatus,
    PostingDecision,
    PostingDecisionStatus,
    ReviewStatus,
)
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

CLASS_DEBTOR_FULL = "debtor_full"
CLASS_DEBTOR_COLLECTIVE = "debtor_collective"
CLASS_CREDITOR_INVOICE = "creditor_invoice"
CLASS_RECURRING_EXPENSE = "recurring_expense"
CLASS_TRANSFER_PAIR = "transfer_pair"
CLASS_EXCLUDED = "excluded"
CASE_CLASSES: tuple[str, ...] = (
    CLASS_DEBTOR_FULL,
    CLASS_DEBTOR_COLLECTIVE,
    CLASS_CREDITOR_INVOICE,
    CLASS_RECURRING_EXPENSE,
    CLASS_TRANSFER_PAIR,
    CLASS_EXCLUDED,
)
CLASS_LABELS: dict[str, str] = {
    CLASS_DEBTOR_FULL: "Zahlungseingang, Vollausgleich",
    CLASS_DEBTOR_COLLECTIVE: "Zahlungseingang, Sammelzahlung",
    CLASS_CREDITOR_INVOICE: "Rechnungszahlung mit verknüpfter Rechnung",
    CLASS_RECURRING_EXPENSE: "Wiederkehrender Aufwand gegen Sachkonto",
    CLASS_TRANSFER_PAIR: "Umbuchung zwischen eigenen Konten",
    CLASS_EXCLUDED: "Ausgeschlossen (Rückläufer, Kaution, Teil- und Überzahlung, unklar)",
}

L0, L1, L2, L3 = "L0", "L1", "L2", "L3"
LEVELS: tuple[str, ...] = (L0, L1, L2, L3)
# Highest level a class may ever reach (plan 3.4).
CLASS_CAPS: dict[str, str] = {
    CLASS_DEBTOR_FULL: L3,
    CLASS_DEBTOR_COLLECTIVE: L1,
    CLASS_CREDITOR_INVOICE: L2,
    CLASS_RECURRING_EXPENSE: L2,
    CLASS_TRANSFER_PAIR: L3,
    CLASS_EXCLUDED: L0,
}
# Classes whose L3 review is a deterministic sample instead of every posting (plan 3.4).
SAMPLED_CLASSES: frozenset[str] = frozenset({CLASS_DEBTOR_FULL, CLASS_TRANSFER_PAIR})

# Eligibility thresholds per target level (product protection, assumption A-085): minimum
# number of decisions of persons in the window, minimum precision of the shown proposals,
# minimum days at the previous level, and for L3 the automatic figures.
ELIGIBILITY: dict[str, dict[str, Any]] = {
    L1: {"n_decided": 20, "precision_manual": Decimal("0.95"), "window_days": 90},
    L2: {
        "n_decided": 50,
        "precision_manual": Decimal("0.98"),
        "window_days": 90,
        "days_at_previous": 30,
    },
    L3: {
        "n_decided": 50,
        "precision_manual": Decimal("0.98"),
        "window_days": 90,
        "days_at_previous": 60,
        "n_auto": 100,
        "error_rate_auto": Decimal("0.005"),
    },
}
# Automatic downgrade (plan 3.3): error rate of automatic postings over 30 days above this
# lowers the class by one level (L3: the stricter figure); three corrections of L1 decisions
# in 30 days lower L1 to L0.
DOWNGRADE_ERROR_RATE = {L2: Decimal("0.02"), L3: Decimal("0.01")}
DOWNGRADE_WINDOW_DAYS = 30
DOWNGRADE_CORRECTIONS_L1 = 3


def level_index(level: str) -> int:
    if level not in LEVELS:
        raise ValueError(f"unknown level {level!r}")
    return LEVELS.index(level)


def cap_of(case_kind: str) -> str:
    return CLASS_CAPS.get(case_kind, L0)


# Pure classification ----------------------------------------------------------------------


def classify(tx: dict[str, Any], proposals: list[dict[str, Any]]) -> str:
    """Case class of a transaction from its features and the stage 1 proposals (plain dicts,
    unit tested with fixed expectations). The order matters: a return or deposit excludes
    everything else; a transfer pair beats the open item match; only an unambiguous single
    settlement is ``debtor_full``."""
    kinds = {p.get("kind") for p in proposals}
    if pp.KIND_RETURN in kinds or pp.KIND_DEPOSIT in kinds:
        return CLASS_EXCLUDED
    if tx.get("transfer_pair") or pp.KIND_TRANSFER in kinds:
        return CLASS_TRANSFER_PAIR
    amount = Decimal(str(tx.get("amount") or "0"))
    match = [p for p in proposals if p.get("source") == pp.SOURCE_MATCH]
    if amount > 0:
        full = [p for p in match if p.get("kind") == pp.KIND_FULL and p.get("unambiguous")]
        if full:
            return CLASS_DEBTOR_FULL
        if any(p.get("kind") == pp.KIND_COLLECTIVE for p in match):
            return CLASS_DEBTOR_COLLECTIVE
        return CLASS_EXCLUDED
    if any(p.get("source") == pp.SOURCE_INVOICE for p in proposals) or any(
        p.get("kind") == pp.KIND_INVOICE and p.get("unambiguous") for p in match
    ):
        return CLASS_CREDITOR_INVOICE
    posting_rule = any(
        p.get("source") == pp.SOURCE_RULE and p.get("kind") == "posting" for p in proposals
    )
    if posting_rule or any(p.get("source") == pp.SOURCE_HISTORY for p in proposals):
        return CLASS_RECURRING_EXPENSE
    return CLASS_EXCLUDED


def effective_levels(configured: dict[str, Any] | None) -> dict[str, str]:
    """Level per class from the tenant setting, capped and defaulting to L0."""
    out: dict[str, str] = {}
    for kind in CASE_CLASSES:
        raw = str((configured or {}).get(kind) or L0)
        level = raw if raw in LEVELS else L0
        if level_index(level) > level_index(cap_of(kind)):
            level = cap_of(kind)
        out[kind] = level
    return out


@dataclass
class ClassMetrics:
    """Figures of one class (and legal entity) in a window, from ``posting_decision`` only."""

    case_kind: str
    legal_entity_id: uuid.UUID | None
    window_from: date
    window_to: date
    n_decided: int = 0  # decisions of persons (accepted_unchanged, modified, rejected)
    n_accepted_unchanged: int = 0
    n_modified: int = 0
    n_rejected: int = 0
    n_bulk: int = 0
    n_auto: int = 0
    n_auto_reversed: int = 0
    n_open: int = 0
    n_total: int = 0
    days_at_level: int | None = None

    @property
    def precision_manual(self) -> Decimal | None:
        """Share of decisions of persons that took the shown proposal unchanged."""
        return _ratio(self.n_accepted_unchanged, self.n_decided)

    @property
    def error_rate_auto(self) -> Decimal | None:
        return _ratio(self.n_auto_reversed, self.n_auto)

    @property
    def coverage(self) -> Decimal | None:
        """Share of closed rounds that were posted without change (auto or unchanged)."""
        return _ratio(self.n_auto + self.n_accepted_unchanged, self.n_total)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_kind": self.case_kind,
            "legal_entity_id": self.legal_entity_id,
            "window_from": self.window_from,
            "window_to": self.window_to,
            "n_decided": self.n_decided,
            "n_accepted_unchanged": self.n_accepted_unchanged,
            "n_modified": self.n_modified,
            "n_rejected": self.n_rejected,
            "n_bulk": self.n_bulk,
            "n_auto": self.n_auto,
            "n_auto_reversed": self.n_auto_reversed,
            "n_open": self.n_open,
            "n_total": self.n_total,
            "precision_manual": self.precision_manual,
            "error_rate_auto": self.error_rate_auto,
            "coverage": self.coverage,
            "days_at_level": self.days_at_level,
        }


def _ratio(part: int, whole: int) -> Decimal | None:
    if whole == 0:
        return None
    return (Decimal(part) / Decimal(whole)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def missing_for(target: str, metrics: ClassMetrics, *, current: str) -> list[str]:
    """Reasons a class is not eligible for ``target`` (empty list: eligible). Pure."""
    reasons: list[str] = []
    if target not in LEVELS or target == L0:
        return ["Zielstufe ungültig"]
    if level_index(target) > level_index(cap_of(metrics.case_kind)):
        return [f"Klasse {metrics.case_kind} ist auf {cap_of(metrics.case_kind)} gedeckelt"]
    if level_index(target) != level_index(current) + 1:
        reasons.append(f"Nur eine Stufe je Antrag (aktuell {current}, beantragt {target})")
    need = ELIGIBILITY[target]
    if metrics.n_decided < need["n_decided"]:
        reasons.append(
            f"n_decided {metrics.n_decided} unter {need['n_decided']} "
            f"in {need['window_days']} Tagen"
        )
    precision = metrics.precision_manual
    if precision is None or precision < need["precision_manual"]:
        reasons.append(
            f"precision_manual {precision if precision is not None else 'ohne Basis'} "
            f"unter {need['precision_manual']}"
        )
    if "days_at_previous" in need and (
        metrics.days_at_level is None or metrics.days_at_level < need["days_at_previous"]
    ):
        reasons.append(
            f"Stufe {current} seit {metrics.days_at_level or 0} Tagen, "
            f"nötig {need['days_at_previous']}"
        )
    if "n_auto" in need and metrics.n_auto < need["n_auto"]:
        reasons.append(f"n_auto {metrics.n_auto} unter {need['n_auto']}")
    if "error_rate_auto" in need:
        rate = metrics.error_rate_auto
        if rate is None or rate > need["error_rate_auto"]:
            reasons.append(
                f"error_rate_auto {rate if rate is not None else 'ohne Basis'} "
                f"über {need['error_rate_auto']}"
            )
    return reasons


# Database side ----------------------------------------------------------------------------


async def _settings(session: AsyncSession) -> Any:
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings).with_for_update())
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


async def current_levels(session: AsyncSession) -> dict[str, str]:
    from mhvp.platform.models import TenantSettings

    configured = await session.scalar(select(TenantSettings.bookkeeping_automation))
    return effective_levels(configured if isinstance(configured, dict) else {})


async def level_since(session: AsyncSession, tenant_id: uuid.UUID, case_kind: str) -> date | None:
    """Day of the last approved raise of the class (from the request table)."""
    decided = await session.scalar(
        select(func.max(BookkeepingLevelRequest.decided_at)).where(
            BookkeepingLevelRequest.tenant_id == tenant_id,
            BookkeepingLevelRequest.case_kind == case_kind,
            BookkeepingLevelRequest.status == LevelRequestStatus.APPROVED.value,
        )
    )
    return decided.date() if isinstance(decided, datetime) else None


async def class_metrics(
    session: AsyncSession,
    *,
    window_from: date,
    window_to: date,
    legal_entity_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> list[ClassMetrics]:
    """Metrics per class (and per legal entity when ``legal_entity_id`` is None, plus one
    tenant wide row per class with ``legal_entity_id`` None) from ``posting_decision``.
    Decisions of persons are the rows closed by a person in the window; automatic postings
    are ``auto_posted`` rows; their reversals are ``reversed`` rows whose original was
    automatic. Rows of ``excluded`` count in ``n_total`` only."""
    start = datetime.combine(window_from, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(window_to + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    query = select(PostingDecision).where(
        PostingDecision.created_at >= start, PostingDecision.created_at < end
    )
    if legal_entity_id is not None:
        query = query.where(PostingDecision.legal_entity_id == legal_entity_id)
    rows = list(await session.scalars(query))
    originals = {r.id: r for r in rows}
    buckets: dict[tuple[str, uuid.UUID | None], ClassMetrics] = {}

    def bucket(kind: str, entity: uuid.UUID | None) -> ClassMetrics:
        key = (kind, entity)
        if key not in buckets:
            buckets[key] = ClassMetrics(kind, entity, window_from, window_to)
        return buckets[key]

    for r in rows:
        kind = case_class_of(r)
        targets = [bucket(kind, r.legal_entity_id)]
        if legal_entity_id is None:
            targets.append(bucket(kind, None))
        for m in targets:
            m.n_total += 1
            if r.status == PostingDecisionStatus.PENDING.value:
                m.n_open += 1
            elif r.status in (
                PostingDecisionStatus.ACCEPTED_UNCHANGED.value,
                PostingDecisionStatus.MODIFIED.value,
                PostingDecisionStatus.REJECTED.value,
            ):
                m.n_decided += 1
                if r.bulk:
                    m.n_bulk += 1
                if r.status == PostingDecisionStatus.ACCEPTED_UNCHANGED.value:
                    m.n_accepted_unchanged += 1
                elif r.status == PostingDecisionStatus.MODIFIED.value:
                    m.n_modified += 1
                else:
                    m.n_rejected += 1
            elif r.status == PostingDecisionStatus.AUTO_POSTED.value:
                m.n_auto += 1
            elif r.status == PostingDecisionStatus.REVERSED.value:
                original = originals.get(r.supersedes_id) if r.supersedes_id else None
                if original is not None and original.status == (
                    PostingDecisionStatus.AUTO_POSTED.value
                ):
                    m.n_auto_reversed += 1
    out = sorted(buckets.values(), key=lambda m: (m.case_kind, str(m.legal_entity_id or "")))
    if tenant_id is not None:
        levels = await current_levels(session)
        for m in out:
            since = await level_since(session, tenant_id, m.case_kind)
            if levels[m.case_kind] == L0:
                m.days_at_level = None
            else:
                m.days_at_level = (window_to - since).days if since else 0
    return out


def case_class_of(row: PostingDecision) -> str:
    """Case class of a stored decision: the runner and S4 store it in ``level``-adjacent
    ``case_kind`` as the stage 1 kind; the class is derived here so older rows classify too."""
    if row.case_kind in CASE_CLASSES:
        return row.case_kind
    return classify(
        {
            "amount": row.features.get("amount")
            or ("1" if row.features.get("direction") == "credit" else "-1"),
            "transfer_pair": row.features.get("transfer_pair"),
        },
        row.proposals,
    )


async def metrics_for_class(
    session: AsyncSession, tenant_id: uuid.UUID, case_kind: str, *, today: date, window_days: int
) -> ClassMetrics:
    rows = await class_metrics(
        session,
        window_from=today - timedelta(days=window_days),
        window_to=today,
        tenant_id=tenant_id,
    )
    for m in rows:
        if m.case_kind == case_kind and m.legal_entity_id is None:
            return m
    m = ClassMetrics(case_kind, None, today - timedelta(days=window_days), today)
    levels = await current_levels(session)
    since = await level_since(session, tenant_id, case_kind)
    m.days_at_level = None if levels[case_kind] == L0 else ((today - since).days if since else 0)
    return m


async def overdue_reviews(session: AsyncSession, *, today: date) -> dict[str, int]:
    """Open review items past their due date per class (an overdue item blocks the class)."""
    rows = await session.execute(
        select(AutoPostingReview.case_kind, func.count())
        .where(
            AutoPostingReview.status == ReviewStatus.OPEN.value, AutoPostingReview.due_on < today
        )
        .group_by(AutoPostingReview.case_kind)
    )
    return {str(kind): int(count) for kind, count in rows.all()}


@dataclass
class LevelActor:
    user_id: uuid.UUID | None
    tenant_id: uuid.UUID
    is_platform_admin: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


async def request_level(
    session: AsyncSession,
    actor: LevelActor,
    *,
    case_kind: str,
    level_to: str,
    reason: str,
    today: date,
) -> BookkeepingLevelRequest:
    """Request one step up for a class; refused (409 ``MHVP-BANK-0022``) with the reasons
    when the eligibility report is not met. The report is stored as evidence."""
    if case_kind not in CASE_CLASSES:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Fallklasse.")
    if level_to not in LEVELS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Stufe.")
    levels = await current_levels(session)
    current = levels[case_kind]
    if level_index(level_to) <= level_index(current):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Eine Absenkung braucht keinen Antrag (PUT levels)."
        )
    open_request = await session.scalar(
        select(BookkeepingLevelRequest).where(
            BookkeepingLevelRequest.case_kind == case_kind,
            BookkeepingLevelRequest.status == LevelRequestStatus.REQUESTED.value,
        )
    )
    if open_request is not None:
        raise ProblemError(
            ErrorCodes.CONFLICT, detail="Für die Klasse liegt bereits ein offener Antrag vor."
        )
    window = ELIGIBILITY.get(level_to, ELIGIBILITY[L1])["window_days"]
    metrics = await metrics_for_class(
        session, actor.tenant_id, case_kind, today=today, window_days=window
    )
    missing = missing_for(level_to, metrics, current=current)
    if missing:
        raise ProblemError(
            ErrorCodes.BANK_LEVEL_NOT_ELIGIBLE,
            detail="Eignung nicht erfüllt: " + "; ".join(missing),
        )
    if actor.user_id is None:
        raise ProblemError(ErrorCodes.FORBIDDEN, detail="Antrag nur durch eine angemeldete Person.")
    row = BookkeepingLevelRequest(
        tenant_id=actor.tenant_id,
        created_by=actor.user_id,
        case_kind=case_kind,
        level_from=current,
        level_to=level_to,
        reason=reason,
        evidence={
            "eligibility": _json(metrics.as_dict()),
            "thresholds": _json(ELIGIBILITY[level_to]),
        },
        requested_by=actor.user_id,
    )
    session.add(row)
    await session.flush()
    await emit(
        session,
        tenant_id=actor.tenant_id,
        type=ev.BOOKKEEPING_LEVEL_REQUESTED,
        entity_type="bookkeeping_level_request",
        entity_id=row.id,
        actor_user_id=actor.user_id,
        payload={"case_kind": case_kind, "level_from": current, "level_to": level_to},
    )
    return row


async def decide_level(
    session: AsyncSession,
    actor: LevelActor,
    *,
    request_id: uuid.UUID,
    approve: bool,
    comment: str | None,
) -> BookkeepingLevelRequest:
    """Second person decides (never the requester, never a platform admin)."""
    row = await session.get(BookkeepingLevelRequest, request_id, with_for_update=True)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    if row.status != LevelRequestStatus.REQUESTED.value:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Der Antrag ist bereits entschieden.")
    if actor.user_id is None or actor.user_id == row.requested_by or actor.is_platform_admin:
        raise ProblemError(
            ErrorCodes.GATE_FOUR_EYES, detail="Die Freigabe muss eine andere Person erteilen."
        )
    row.status = LevelRequestStatus.APPROVED.value if approve else LevelRequestStatus.REJECTED.value
    row.decided_by, row.decided_at, row.decision_comment = actor.user_id, datetime.now(UTC), comment
    row.updated_by = actor.user_id
    if approve:
        await _set_level(
            session,
            actor,
            case_kind=row.case_kind,
            level=row.level_to,
            reason=f"Antrag {row.id} freigegeben",
            request_id=row.id,
        )
    await session.flush()
    return row


async def _set_level(
    session: AsyncSession,
    actor: LevelActor,
    *,
    case_kind: str,
    level: str,
    reason: str,
    request_id: uuid.UUID | None = None,
    automatic: bool = False,
) -> str:
    settings = await _settings(session)
    configured = dict(settings.bookkeeping_automation or {})
    before = effective_levels(configured)[case_kind]
    configured[case_kind] = level
    settings.bookkeeping_automation = configured
    await session.flush()
    await emit(
        session,
        tenant_id=actor.tenant_id,
        type=ev.BOOKKEEPING_LEVEL_CHANGED,
        entity_type="tenant_settings",
        entity_id=settings.id,
        actor_user_id=actor.user_id,
        payload={
            "case_kind": case_kind,
            "level_from": before,
            "level_to": level,
            "reason": reason,
            "request_id": str(request_id) if request_id else None,
            "automatic": automatic,
        },
        changes={f"bookkeeping_automation.{case_kind}": {"old": before, "new": level}},
    )
    return before


async def lower_level(
    session: AsyncSession, actor: LevelActor, *, case_kind: str, level: str, reason: str
) -> str:
    """Lowering by a person: immediate, no second person (the safe direction)."""
    if case_kind not in CASE_CLASSES or level not in LEVELS:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Klasse oder Stufe.")
    current = (await current_levels(session))[case_kind]
    if level_index(level) >= level_index(current):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Eine Anhebung läuft über einen Antrag mit Freigabe."
        )
    return await _set_level(session, actor, case_kind=case_kind, level=level, reason=reason)


async def downgrade(
    session: AsyncSession, tenant_id: uuid.UUID, *, case_kind: str, reason: str
) -> str | None:
    """Automatic downgrade by one level (never up). Returns the new level or None."""
    current = (await current_levels(session))[case_kind]
    if current == L0:
        return None
    target = LEVELS[level_index(current) - 1]
    await _set_level(
        session,
        LevelActor(None, tenant_id),
        case_kind=case_kind,
        level=target,
        reason=reason,
        automatic=True,
    )
    return target


async def refresh_downgrades(
    session: AsyncSession, tenant_id: uuid.UUID, *, today: date
) -> dict[str, str]:
    """Nightly job (``mhvp.banking.levels_refresh``): only downgrades, from the figures of the
    last 30 days. Returns the classes lowered with their new level."""
    lowered: dict[str, str] = {}
    levels = await current_levels(session)
    rows = await class_metrics(
        session,
        window_from=today - timedelta(days=DOWNGRADE_WINDOW_DAYS),
        window_to=today,
        tenant_id=tenant_id,
    )
    for m in rows:
        if m.legal_entity_id is not None:
            continue
        level = levels[m.case_kind]
        limit = DOWNGRADE_ERROR_RATE.get(level)
        rate = m.error_rate_auto
        if limit is not None and rate is not None and rate > limit:
            new = await downgrade(
                session, tenant_id, case_kind=m.case_kind, reason=f"Fehlerquote {rate} über {limit}"
            )
            if new:
                lowered[m.case_kind] = new
            continue
        if level == L1 and m.n_modified + m.n_rejected >= DOWNGRADE_CORRECTIONS_L1:
            new = await downgrade(
                session,
                tenant_id,
                case_kind=m.case_kind,
                reason=(
                    f"{m.n_modified + m.n_rejected} Korrekturen in {DOWNGRADE_WINDOW_DAYS} Tagen"
                ),
            )
            if new:
                lowered[m.case_kind] = new
    return lowered


def _json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json(v) for v in value]
    if isinstance(value, Decimal | uuid.UUID | date):
        return str(value)
    return value


def request_out(row: BookkeepingLevelRequest) -> dict[str, Any]:
    return {
        "id": row.id,
        "case_kind": row.case_kind,
        "level_from": row.level_from,
        "level_to": row.level_to,
        "reason": row.reason,
        "evidence": row.evidence,
        "status": row.status,
        "requested_by": row.requested_by,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "decision_comment": row.decision_comment,
        "created_at": row.created_at,
    }
