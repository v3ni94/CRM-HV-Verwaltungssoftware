"""KI-Plausibilität eines Mieterhöhungsfalls (M26-01, 6.3 ``rent_increase_case.ai_check_id``).

The AI never touches the case: the input is assembled deterministically from the stored case
(amounts, dates, basis, the deterministic check ``case.check``, whether sources are recorded),
without names, addresses or ids (rule 0.1.13), and the answer is stored as an ``AiProposal`` of
entity type ``rent_increase_check``. The job links it as ``case.ai_check_id``. The proposal
carries hints with a severity only: it is never a release, never a legal review and it cannot
be applied (``POST /ai/proposals/{id}/apply`` refuses it). The source register (annex C) holds
no rent law norm, so the prompt checks internal consistency only.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.ai import gateway, tasks
from mhvp.ai.models import AiProposal, AiTask, AiTaskRun, RunStatus
from mhvp.core.problems import ErrorCodes, ProblemError

ENTITY_TYPE = "rent_increase_check"
CONTEXT_TYPE = "rent_increase_check"
SEVERITIES: tuple[str, ...] = ("low", "medium", "high")
OVERALL_BY_SEVERITY = {"high": "kritisch", "medium": "pruefen", "low": "pruefen"}
INSTRUCTION = (
    "Prüfe den folgenden Mieterhöhungsfall auf innere Stimmigkeit. Die Daten sind JSON ohne "
    "Personen und Anschriften. Antworte ausschließlich mit Hinweisen und Schweregrad, nie mit "
    "Beträgen, Normen, Fristen oder einer Entscheidung."
)
NOTICE = (
    "Hinweise der KI ohne Wirkung auf den Mieterhöhungsfall; keine Freigabe und keine "
    "Rechtsprüfung. Prüfung und Entscheidung durch eine Person (Regel 0.1.6)."
)
# Keys of the deterministic check that may carry free text with names; they are dropped.
_CHECK_DROP = {"contact", "contact_name", "tenant", "tenant_name", "address", "document_id"}


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _area(value: Any) -> str | None:
    """Area with two decimals: ``NUMERIC(20,8)`` renders eight fraction digits, which the
    identifier mask would read as a phone number and so block the run."""
    if value is None:
        return None
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except InvalidOperation:
        return str(value)


def _clean(value: Any) -> Any:
    """Deterministic check without id or name fields (recursive)."""
    if isinstance(value, dict):
        return {
            k: _clean(v)
            for k, v in value.items()
            if k not in _CHECK_DROP and not str(k).endswith("_id")
        }
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def build_payload(case: Any) -> dict[str, Any]:
    """Prompt input of one case (``letting.models.RentIncreaseCase``); no AI, no lookup."""
    flats = []
    for flat in case.comparison_flats or []:
        if isinstance(flat, dict):
            flats.append(
                {
                    k: _area(v) if k == "living_area_sqm" else _s(v)
                    for k, v in flat.items()
                    if k in ("rent_per_sqm", "living_area_sqm", "rent", "year_built", "features")
                }
            )
    return {
        "basis": case.basis,
        "justification": case.justification,
        "current_rent": _s(case.current_rent),
        "target_rent": _s(case.target_rent),
        "reference_rent": _s(case.reference_rent),
        "cap_limit_percent": _s(case.cap_limit_percent),
        "comparison_rent_per_sqm": _s(case.comparison_rent_per_sqm),
        "living_area_sqm": _area(case.living_area_sqm),
        "earliest_effective_date": _s(case.earliest_effective_date),
        "effective_date": _s(case.effective_date),
        "received_on": _s(case.received_on),
        "status": case.status,
        "has_source_note": bool((case.source_note or "").strip()),
        "has_source_document": case.source_document_id is not None,
        "has_expert_document": case.expert_document_id is not None,
        "rent_index": (
            {"name": case.rent_index_name, "date": _s(case.rent_index_date)}
            if case.rent_index_name
            else None
        ),
        "comparison_flats": {"count": len(flats), "items": flats},
        "basis_data": _clean(case.basis_data or {}),
        "deterministic_check": _clean(case.check or {}),
    }


def prompt_text(payload: dict[str, Any]) -> str:
    return f"{INSTRUCTION}\n\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def assert_masked(payload: dict[str, Any]) -> None:
    """Defensive check before the run is queued: no UUID, IBAN, e-mail or phone number."""
    from mhvp.billing.ai_check import _UUID
    from mhvp.objektakte.masking import mask_identifiers

    text = json.dumps(payload, ensure_ascii=False)
    if _UUID.search(text) or mask_identifiers(text) != text:
        raise ProblemError(
            ErrorCodes.VALIDATION,
            detail="Eingabe für die KI-Prüfung enthält Kennungen; Lauf nicht gestartet.",
        )


def queue_run(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None, case: Any
) -> AiTaskRun:
    """Queues the gateway run (release, DPA evidence, budget checks happen in the gateway)."""
    payload = build_payload(case)
    assert_masked(payload)
    prompt = tasks.prompt(AiTask.RENT_INCREASE_CHECK)
    text = prompt_text(payload)
    context = {"context_type": CONTEXT_TYPE, "context_id": str(case.id)}
    run = AiTaskRun(
        tenant_id=tenant_id,
        created_by=user_id,
        task=AiTask.RENT_INCREASE_CHECK,
        conversation_id=None,
        prompt_version=prompt.version,
        input_hash=gateway.input_hash(AiTask.RENT_INCREASE_CHECK, prompt.version, text, context),
        input_ref={"instruction": text, "document_ids": [], "context": context},
        status=RunStatus.QUEUED,
    )
    session.add(run)
    return run


def normalize_result(output: dict[str, Any]) -> dict[str, Any]:
    """Findings deduplicated, ordered by severity; the overall assessment is derived from the
    highest severity instead of the model's own word."""
    seen: set[tuple[str, str, str]] = set()
    findings: list[dict[str, Any]] = []
    for item in output.get("findings", []):
        severity = str(item.get("severity", "low"))
        if severity not in SEVERITIES:
            severity = "low"
        key = (str(item.get("field", "")), str(item.get("description", "")).strip(), severity)
        if key in seen:
            continue
        seen.add(key)
        findings.append({"field": key[0], "description": key[1], "severity": severity})
    findings.sort(key=lambda f: (-SEVERITIES.index(f["severity"]), f["field"]))
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    top = next((s for s in reversed(SEVERITIES) if counts[s]), None)
    return {
        "findings": findings,
        "counts": counts,
        "max_severity": top,
        "overall": OVERALL_BY_SEVERITY[top] if top else "unauffaellig",
        "model_overall": output.get("overall"),
        "summary": str(output.get("summary") or ""),
    }


def proposal_payload(run: AiTaskRun) -> dict[str, Any]:
    context = run.input_ref.get("context", {})
    return {
        "case_id": context.get("context_id"),
        "prompt_version": run.prompt_version,
        "model": run.model,
        **normalize_result(run.output or {}),
        "notice": NOTICE,
    }


async def store_result(
    session: AsyncSession, run: AiTaskRun, provider_used: str | None
) -> AiProposal:
    """Proposal of a succeeded run, linked as ``ai_check_id`` of the case (the only field of
    the case written, a reference, never a value of the case)."""
    from mhvp.letting.models import RentIncreaseCase

    context = run.input_ref.get("context", {})
    proposal = AiProposal(
        tenant_id=run.tenant_id,
        task_run_id=run.id,
        entity_type=ENTITY_TYPE,
        context_id=uuid.UUID(str(context["context_id"])) if context.get("context_id") else None,
        proposed={**proposal_payload(run), "provider_used": provider_used},
    )
    session.add(proposal)
    await session.flush()
    if proposal.context_id is not None:
        case = await session.get(RentIncreaseCase, proposal.context_id)
        if case is not None:
            case.ai_check_id = proposal.id
    return proposal


async def latest_run(session: AsyncSession, case_id: uuid.UUID) -> AiTaskRun | None:
    row: AiTaskRun | None = await session.scalar(
        select(AiTaskRun)
        .where(
            AiTaskRun.task == AiTask.RENT_INCREASE_CHECK,
            AiTaskRun.input_ref["context"]["context_id"].astext == str(case_id),
        )
        .order_by(AiTaskRun.created_at.desc())
        .limit(1)
    )
    return row


async def auto_queue(
    session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID | None, case: Any
) -> uuid.UUID | None:
    """Automatic proposal after a case was created or changed (Q14-02, package R09).

    Returns the id of the queued run, or ``None`` when nothing was queued: switch off, case
    not in the status draft, no released provider (the gateway repeats this check before any
    call), the input unchanged since the last run, or the input not maskable. Never raises
    for these reasons, so creating or changing the case is never blocked by the AI."""
    from mhvp.ai import automation

    if case.status != "draft" or not await automation.is_enabled(session, "rent_increase_check"):
        return None
    try:
        usable, _reasons = await gateway.routes(session, AiTask.RENT_INCREASE_CHECK)
    except gateway.GatewayBlockedError:
        return None
    if not usable:
        return None
    try:
        payload = build_payload(case)
        assert_masked(payload)
    except (ProblemError, TypeError, ValueError):
        return None
    prompt = tasks.prompt(AiTask.RENT_INCREASE_CHECK)
    context = {"context_type": CONTEXT_TYPE, "context_id": str(case.id)}
    digest = gateway.input_hash(
        AiTask.RENT_INCREASE_CHECK, prompt.version, prompt_text(payload), context
    )
    previous = await latest_run(session, case.id)
    if previous is not None and previous.input_hash == digest:
        return None
    run = queue_run(session, tenant_id=tenant_id, user_id=user_id, case=case)
    await session.flush()
    return run.id
