"""KI-Plausibilität eines Abrechnungsentwurfs (A35, M17 and M24, 9.2 task ``check_statement``).

The AI never touches the statement: the input is assembled deterministically from the stored
snapshot (result per party, positions with key and amount, previous period where one exists,
posted account balances), masked before it leaves the platform (no names, no IBAN, parties as
unit numbers, rule 0.1.13), and the answer is stored as an ``AiProposal`` of entity type
``statement_check`` (rule 0.1.6). The result carries findings with a severity only, never
amounts, corrections or a decision; the snapshot hash stays what it was.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai import gateway, tasks
from mhvp.ai.models import AiProposal, AiTask, AiTaskRun, RunStatus
from mhvp.billing.models import Statement, StatementSnapshot
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.objektakte.masking import mask_identifiers

ENTITY_TYPE = "statement_check"
CONTEXT_TYPE = "statement_check"
StatementKind = Literal["operating_costs", "hoa"]
SEVERITIES: tuple[str, ...] = ("low", "medium", "high")
OVERALL_BY_SEVERITY = {"high": "kritisch", "medium": "pruefen", "low": "pruefen"}
NO_FINDINGS = "unauffaellig"
NAME_PLACEHOLDER = "[NAME]"
# A person or company named with a title in a free text (label, basis); names without a title
# are not recognised here (open point, see billing README).
_TITLED_NAME = re.compile(
    r"\b(?:Herrn?|Frau|Familie|Firma|Fa\.|Eheleute)\s+[A-ZÄÖÜ][\wäöüß-]+(?:\s+[A-ZÄÖÜ][\wäöüß-]+)?"
)
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
INSTRUCTION = (
    "Prüfe den folgenden Abrechnungsentwurf auf Plausibilität. Die Daten sind JSON; Parteien "
    "sind nur als Einheit-Kennung enthalten. Antworte ausschließlich mit Hinweisen und "
    "Schweregrad, nie mit Beträgen, Korrekturen oder einer Entscheidung."
)


# Masking -------------------------------------------------------------------------------------


def mask_free_text(text: str | None) -> str:
    """IBAN, e-mail and phone (``mask_identifiers``), titled person or company names and UUIDs
    are replaced; the remaining text (cost labels, contract clauses) stays readable."""
    if not text:
        return ""
    masked = mask_identifiers(text)
    masked = _TITLED_NAME.sub(NAME_PLACEHOLDER, masked)
    return _UUID.sub("[ID]", masked)


def _money(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def change_percent(current: Any, previous: Any) -> str | None:
    """Change of ``current`` against ``previous`` in percent, one decimal, ``None`` without a
    usable previous value (no previous period, or a previous value of zero)."""
    cur, prev = _money(current), _money(previous)
    if cur is None or prev is None or Decimal(prev) == 0:
        return None
    ratio = (Decimal(cur) - Decimal(prev)) / Decimal(prev) * Decimal(100)
    return str(ratio.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _sum(values: list[str | None]) -> str:
    return str(sum((Decimal(v) for v in values if v is not None), Decimal("0.00")))


# Input assembly (deterministic, no AI) --------------------------------------------------------


def _positions(
    positions: list[dict[str, Any]],
    previous: dict[str, str] | None,
    extra: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Positions of a snapshot in prompt form: ``ref`` P1..Pn, masked label and basis, key and
    account facts where the snapshot (operating costs) or ``extra`` (HOA cost items) holds
    them, previous amount and change where a previous statement carries the same label."""
    out: list[dict[str, Any]] = []
    for index, pos in enumerate(positions, start=1):
        label = str(pos.get("label", ""))
        facts = (extra or {}).get(label, {})
        key = pos.get("allocation_key") or facts.get("allocation_key")
        account = pos.get("account") or facts.get("account")
        amount = _money(pos.get("amount"))
        prev_amount = previous.get(label) if previous else None
        split = pos.get("split") or {}
        out.append(
            {
                "ref": f"P{index}",
                "label": mask_free_text(label),
                "amount": amount,
                "basis": mask_free_text(str(pos.get("basis") or "")),
                "allocation_key": (
                    {
                        "code": key.get("code"),
                        "name": mask_free_text(str(key.get("name") or "")),
                        "template_derived": bool(key.get("template_derived")),
                    }
                    if key
                    else None
                ),
                "account": (
                    {
                        "number": account.get("number"),
                        "allocation_category": account.get("allocation_category"),
                        "posted_in_period": _money(account.get("posted_in_period")),
                    }
                    if account
                    else None
                ),
                "previous_amount": prev_amount,
                "change_percent": change_percent(amount, prev_amount),
                "split_total": _sum([_money(v) for v in split.values()]) if split else None,
            }
        )
    return out


def _previous_positions(snapshot: dict[str, Any] | None) -> dict[str, str] | None:
    if not snapshot:
        return None
    return {
        str(p.get("label", "")): _money(p.get("amount")) or "0.00"
        for p in snapshot.get("positions", [])
    }


def build_operating_costs_input(
    snapshot: StatementSnapshot,
    previous: StatementSnapshot | None,
    period: tuple[str, str],
    previous_period: tuple[str, str] | None,
) -> dict[str, Any]:
    """Operating cost statement (M17): positions from ``snapshot.inputs`` (key and account
    facts recorded by ``services.check_item``), results from ``snapshot.results``. Contract
    ids and occupant keys are dropped; a party is the unit number only."""
    inputs, results = snapshot.inputs, snapshot.results
    prev_positions = _previous_positions(previous.inputs if previous else None)
    prev_units = (
        {r["unit_number"]: _money(r.get("costs")) for r in previous.results.get("results", [])}
        if previous
        else {}
    )
    positions = _positions(inputs.get("positions", []), prev_positions)
    units: list[dict[str, Any]] = []
    for row in results.get("results", []):
        unit = str(row.get("unit_number"))
        costs = _money(row.get("costs"))
        units.append(
            {
                "unit": unit,
                "days": _days(row.get("from"), row.get("to")),
                "costs": costs,
                "advances_due": _money(row.get("advances_due")),
                "advances_paid": _money(row.get("advances_paid")),
                "balance": _money(row.get("balance")),
                "previous_costs": prev_units.get(unit),
                "change_percent": change_percent(costs, prev_units.get(unit)),
            }
        )
    accounts = _accounts_of(positions)
    return {
        "statement_kind": "operating_costs",
        "period": {"from": period[0], "to": period[1]},
        "rule_version": snapshot.rule_version,
        "positions": positions,
        "units": units,
        "totals": {
            "total": _money(results.get("total")),
            "sum_of_positions": _sum([p["amount"] for p in positions]),
            "sum_of_unit_costs": _sum([u["costs"] for u in units]),
            "vacancy_owner_share": _money(results.get("vacancy_owner_share")),
        },
        "accounts": accounts,
        "previous_period": (
            {
                "from": previous_period[0],
                "to": previous_period[1],
                "total": _money(previous.results.get("total")),
            }
            if previous is not None and previous_period is not None
            else None
        ),
    }


def build_hoa_input(
    snapshot: dict[str, Any],
    previous: dict[str, Any] | None,
    year: int,
    item_facts: dict[str, dict[str, Any]],
    account_balances: list[dict[str, Any]],
) -> dict[str, Any]:
    """HOA annual statement (M24): positions and units from the stored snapshot, key and
    account facts per cost item from ``item_facts`` (label -> facts), posted balances of the
    referenced accounts from ``account_balances``. Owner names never enter."""
    positions = _positions(snapshot.get("positions", []), _previous_positions(previous), item_facts)
    prev_units = (
        {u["unit_number"]: _money(u.get("cost_share")) for u in previous.get("units", [])}
        if previous
        else {}
    )
    units: list[dict[str, Any]] = []
    for row in snapshot.get("units", []):
        unit = str(row.get("unit_number"))
        costs = _money(row.get("cost_share"))
        units.append(
            {
                "unit": unit,
                "costs": costs,
                "advances_due": _money(row.get("advances_resolved")),
                "advances_paid": _money(row.get("advances_paid")),
                "balance": _money(row.get("result")),
                "arrears": _money(row.get("arrears")),
                "previous_costs": prev_units.get(unit),
                "change_percent": change_percent(costs, prev_units.get(unit)),
            }
        )
    reserve = snapshot.get("reserve") or {}
    return {
        "statement_kind": "hoa",
        "period": {"year": year},
        "rule_version": None,
        "positions": positions,
        "units": units,
        "totals": {
            "total": _money(snapshot.get("total_costs")),
            "sum_of_positions": _sum([p["amount"] for p in positions]),
            "sum_of_unit_costs": _sum([u["costs"] for u in units]),
            "vacancy_owner_share": None,
        },
        "accounts": account_balances or _accounts_of(positions),
        "reserve": (
            {
                key: _money(reserve.get(key))
                for key in (
                    "opening",
                    "contributions_resolved",
                    "contributions_paid",
                    "withdrawals",
                    "interest",
                    "closing",
                    "bank_balance",
                    "bank_difference",
                )
            }
            if reserve
            else None
        ),
        "previous_period": (
            {"year": year - 1, "total": _money(previous.get("total_costs"))} if previous else None
        ),
    }


def _accounts_of(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for pos in positions:
        account = pos.get("account")
        if account and account.get("number"):
            seen.setdefault(
                str(account["number"]),
                {"number": account["number"], "posted_in_period": account["posted_in_period"]},
            )
    return [seen[k] for k in sorted(seen)]


def _days(start: Any, end: Any) -> int | None:
    from datetime import date

    try:
        return (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days + 1
    except (TypeError, ValueError):
        return None


def prompt_text(payload: dict[str, Any]) -> str:
    """The instruction handed to the gateway: fixed sentence plus the JSON input, sorted keys
    so the input hash (deduplication, 9.3) is stable for the same snapshot."""
    return f"{INSTRUCTION}\n\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def assert_masked(payload: dict[str, Any]) -> None:
    """Defensive check before the run is queued: no UUID, IBAN or e-mail in the prompt input."""
    text = json.dumps(payload, ensure_ascii=False)
    if _UUID.search(text) or mask_identifiers(text) != text:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Eingabe für die KI-Plausibilität enthält Kennungen; Lauf nicht gestartet.",
        )


# Result normalisation (deterministic, measured by the offline evaluation) ------------------


def normalize_result(
    output: dict[str, Any],
    known_positions: set[str] | None = None,
    known_units: set[str] | None = None,
) -> dict[str, Any]:
    """Post-processing of a validated ``CheckStatementResult``: findings deduplicated and
    ordered by severity (high first), references to unknown positions or units cleared (kept
    as a finding, the reference is dropped), the overall assessment derived from the highest
    severity instead of trusting the model's own word (rule 0.1.6: consistency is checked
    here, not assumed)."""
    seen: set[tuple[str, str, str]] = set()
    findings: list[dict[str, Any]] = []
    for item in output.get("findings", []):
        severity = str(item.get("severity", "low"))
        if severity not in SEVERITIES:
            severity = "low"
        position = item.get("position")
        unit = item.get("unit")
        if known_positions is not None and position is not None and position not in known_positions:
            position = None
        if known_units is not None and unit is not None and unit not in known_units:
            unit = None
        key = (str(item.get("field", "")), str(item.get("description", "")).strip(), severity)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "field": key[0],
                "description": key[1],
                "severity": severity,
                "position": position,
                "unit": unit,
            }
        )
    findings.sort(key=lambda f: (-SEVERITIES.index(f["severity"]), f["field"]))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    max_severity = next((s for s in reversed(SEVERITIES) if counts[s]), None)
    return {
        "findings": findings,
        "counts": counts,
        "max_severity": max_severity,
        "overall": OVERALL_BY_SEVERITY[max_severity] if max_severity else NO_FINDINGS,
        "model_overall": output.get("overall"),
        "summary": str(output.get("summary") or ""),
        "positions": sorted({f["position"] for f in findings if f["position"]}),
        "units": sorted({f["unit"] for f in findings if f["unit"]}),
    }


def proposal_payload(run: AiTaskRun) -> dict[str, Any]:
    """Content of the ``statement_check`` proposal built from a succeeded run; no field of it
    is ever written back to the statement."""
    context = run.input_ref.get("context", {})
    normalized = normalize_result(
        run.output or {},
        known_positions=set(context.get("positions", [])) or None,
        known_units=set(context.get("units", [])) or None,
    )
    return {
        "statement_id": context.get("context_id"),
        "statement_kind": context.get("statement_kind"),
        "snapshot_hash": context.get("snapshot_hash"),
        "prompt_version": run.prompt_version,
        "model": run.model,
        **normalized,
        "notice": (
            "Hinweise der KI ohne Wirkung auf die Abrechnung; Prüfung und Entscheidung durch "
            "eine Person (Regel 0.1.6)."
        ),
    }


# Database access ---------------------------------------------------------------------------


async def previous_operating_costs(
    session: AsyncSession, statement: Statement
) -> tuple[StatementSnapshot | None, tuple[str, str] | None]:
    """The latest calculated version of the statement whose period ends the day before this
    one starts (same ledger); ``None`` without one."""
    day_before = statement.period_from - timedelta(days=1)
    previous = await session.scalar(
        select(Statement)
        .where(
            Statement.ledger_id == statement.ledger_id,
            Statement.period_to == day_before,
            Statement.snapshot_id.is_not(None),
            Statement.id != statement.id,
        )
        .order_by(Statement.version.desc(), Statement.created_at.desc())
        .limit(1)
    )
    if previous is None or previous.snapshot_id is None:
        return None, None
    snap = await session.get(StatementSnapshot, previous.snapshot_id)
    if snap is None:
        return None, None
    return snap, (previous.period_from.isoformat(), previous.period_to.isoformat())


async def operating_costs_payload(
    session: AsyncSession, statement: Statement
) -> tuple[dict[str, Any], StatementSnapshot]:
    if statement.snapshot_id is None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kein Ergebnis-Snapshot; erst berechnen.")
    snap = await session.get(StatementSnapshot, statement.snapshot_id)
    if snap is None:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kein Ergebnis-Snapshot; erst berechnen.")
    previous, previous_period = await previous_operating_costs(session, statement)
    payload = build_operating_costs_input(
        snap,
        previous,
        (statement.period_from.isoformat(), statement.period_to.isoformat()),
        previous_period,
    )
    return payload, snap


async def hoa_payload(session: AsyncSession, statement: Any) -> tuple[dict[str, Any], str]:
    """HOA statement (``mhvp.hoa.models.HoaStatement``): snapshot plus key and account facts
    of its cost items and the posted balance of each referenced account in the year."""
    from datetime import date

    from mhvp.accounting.models import EntryStatus, JournalEntry, JournalLine, LedgerAccount
    from mhvp.hoa.models import HoaCostItem, HoaStatement
    from mhvp.properties.models import AllocationKey

    if not statement.snapshot or not statement.snapshot_hash:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kein Ergebnis-Snapshot; erst berechnen.")
    previous = await session.scalar(
        select(HoaStatement)
        .where(
            HoaStatement.ledger_id == statement.ledger_id,
            HoaStatement.year == statement.year - 1,
            HoaStatement.snapshot.is_not(None),
        )
        .order_by(HoaStatement.version.desc(), HoaStatement.created_at.desc())
        .limit(1)
    )
    items = (
        await session.scalars(select(HoaCostItem).where(HoaCostItem.statement_id == statement.id))
    ).all()
    start, end = date(statement.year, 1, 1), date(statement.year, 12, 31)
    facts: dict[str, dict[str, Any]] = {}
    balances: dict[str, dict[str, Any]] = {}
    for item in items:
        entry: dict[str, Any] = {}
        key = await session.get(AllocationKey, item.allocation_key_id)
        if key is not None:
            entry["allocation_key"] = {
                "code": key.code,
                "name": key.name,
                "template_derived": key.is_template_derived,
            }
        if item.account_id is not None:
            account = await session.get(LedgerAccount, item.account_id)
            if account is not None:
                debit, credit = (
                    await session.execute(
                        select(
                            func.coalesce(func.sum(JournalLine.debit), 0),
                            func.coalesce(func.sum(JournalLine.credit), 0),
                        )
                        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
                        .where(
                            JournalLine.account_id == account.id,
                            JournalEntry.status == EntryStatus.POSTED,
                            JournalEntry.booking_date.between(start, end),
                        )
                    )
                ).one()
                posted = str(Decimal(debit) - Decimal(credit))
                category = getattr(account, "allocation_category", None)
                entry["account"] = {
                    "number": account.number,
                    "allocation_category": getattr(category, "value", None),
                    "posted_in_period": posted,
                }
                balances[account.number] = {
                    "number": account.number,
                    "posted_in_period": _money(posted),
                }
        facts[item.label] = entry
    payload = build_hoa_input(
        statement.snapshot,
        previous.snapshot if previous is not None else None,
        statement.year,
        facts,
        [balances[k] for k in sorted(balances)],
    )
    return payload, str(statement.snapshot_hash)


def queue_run(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID | None,
    statement_id: uuid.UUID,
    kind: StatementKind,
    snapshot_hash: str,
    payload: dict[str, Any],
) -> AiTaskRun:
    """Queues the gateway run (release, budget and provider checks happen in the gateway).
    The caller dispatches it after commit, inline or on the ``io`` queue."""
    assert_masked(payload)
    prompt = tasks.prompt(AiTask.CHECK_STATEMENT)
    text = prompt_text(payload)
    context = {
        "context_type": CONTEXT_TYPE,
        "context_id": str(statement_id),
        "statement_kind": kind,
        "snapshot_hash": snapshot_hash,
        "positions": [p["ref"] for p in payload["positions"]],
        "units": [u["unit"] for u in payload["units"]],
    }
    run = AiTaskRun(
        tenant_id=tenant_id,
        created_by=user_id,
        task=AiTask.CHECK_STATEMENT,
        conversation_id=None,
        prompt_version=prompt.version,
        input_hash=gateway.input_hash(AiTask.CHECK_STATEMENT, prompt.version, text, context),
        input_ref={"instruction": text, "document_ids": [], "context": context},
        status=RunStatus.QUEUED,
    )
    session.add(run)
    return run


async def runs_for(session: AsyncSession, statement_id: uuid.UUID) -> list[AiTaskRun]:
    rows = await session.scalars(
        select(AiTaskRun)
        .where(
            AiTaskRun.task == AiTask.CHECK_STATEMENT,
            AiTaskRun.input_ref["context"]["context_id"].astext == str(statement_id),
        )
        .order_by(AiTaskRun.created_at.desc())
        .limit(20)
    )
    return list(rows.all())


async def proposals_for(session: AsyncSession, statement_id: uuid.UUID) -> list[AiProposal]:
    rows = await session.scalars(
        select(AiProposal)
        .where(AiProposal.entity_type == ENTITY_TYPE, AiProposal.context_id == statement_id)
        .order_by(AiProposal.created_at.desc())
        .limit(20)
    )
    return list(rows.all())
