"""KI-Plausibilität (A35): ``POST``/``GET`` ``/statements/{id}/ai-check`` (M17) and
``/hoa/statements/{id}/ai-check`` (M24). The run goes through the AI gateway (release, DPA
evidence, budget); the result is an ``AiProposal`` of entity type ``statement_check`` with
findings and severities only. Nothing here changes a statement, a snapshot or a status."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from mhvp.ai import jobs
from mhvp.ai.models import AiProposal, AiTaskRun
from mhvp.billing import ai_check
from mhvp.billing.models import Statement
from mhvp.core.auth.principal import TenantPrincipal, require_permission, sessions, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore

router = APIRouter(tags=["Abrechnung"])
READ = require_permission("accounting:read")
CREATE = require_permission("accounting:create")


def _run_out(run: AiTaskRun) -> dict[str, Any]:
    ref = run.input_ref
    return {
        "id": run.id,
        "status": run.status.value,
        "error": run.error,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "snapshot_hash": ref.get("context", {}).get("snapshot_hash"),
        "created_at": run.created_at,
    }


def _proposal_out(proposal: AiProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "task_run_id": proposal.task_run_id,
        "entity_type": proposal.entity_type,
        "decision": proposal.decision.value,
        "created_at": proposal.created_at,
        "proposed": proposal.proposed,
    }


async def _state(session: Any, statement_id: uuid.UUID) -> dict[str, Any]:
    runs = await ai_check.runs_for(session, statement_id)
    proposals = await ai_check.proposals_for(session, statement_id)
    return {
        "statement_id": statement_id,
        "latest_run": _run_out(runs[0]) if runs else None,
        "latest": _proposal_out(proposals[0]) if proposals else None,
        "proposals": [_proposal_out(p) for p in proposals],
    }


async def _dispatch(request: Request, principal: TenantPrincipal, run_id: uuid.UUID) -> None:
    """Same execution path as the assistant and the receipt inbox: inline in tests, Celery
    ``io`` queue otherwise (``mhvp.ai.jobs.run_and_propose`` stores the proposal)."""
    settings = request.app.state.settings
    if settings.ai_inline:
        await jobs.run_and_propose(
            sessions(request), principal.tenant_id, run_id, BlobStore(settings), principal.user_id
        )
        return
    from mhvp.worker import get_celery

    get_celery().send_task(
        "mhvp.ai.run",
        args=[
            str(principal.tenant_id),
            str(run_id),
            str(principal.user_id) if principal.user_id else None,
        ],
        queue="io",
    )


async def _start(
    request: Request,
    principal: TenantPrincipal,
    statement_id: uuid.UUID,
    kind: ai_check.StatementKind,
    payload: dict[str, Any],
    snapshot_hash: str,
    session: Any,
) -> uuid.UUID:
    run = ai_check.queue_run(
        session,
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        statement_id=statement_id,
        kind=kind,
        snapshot_hash=snapshot_hash,
        payload=payload,
    )
    await session.flush()
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="statement.ai_check_requested",
        entity_type="statement" if kind == "operating_costs" else "hoa_statement",
        entity_id=statement_id,
        actor_user_id=principal.user_id,
        payload={"run_id": str(run.id), "snapshot_hash": snapshot_hash},
    )
    return run.id


# Operating cost statements (M17) -----------------------------------------------------------


@router.post(
    "/statements/{statement_id}/ai-check",
    status_code=202,
    summary="KI-Plausibilität des Abrechnungsentwurfs anstoßen (nur Hinweise)",
)
async def start_statement_check(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        st = await session.get(Statement, statement_id)
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        payload, snap = await ai_check.operating_costs_payload(session, st)
        run_id = await _start(
            request, principal, statement_id, "operating_costs", payload, snap.hash, session
        )
    await _dispatch(request, principal, run_id)
    async with tenant_tx(request, principal) as session:
        return await _state(session, statement_id)


@router.get("/statements/{statement_id}/ai-check", summary="KI-Plausibilität: Läufe und Hinweise")
async def get_statement_check(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        if await session.get(Statement, statement_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await _state(session, statement_id)


# HOA annual statements (M24) --------------------------------------------------------------


@router.post(
    "/hoa/statements/{statement_id}/ai-check",
    status_code=202,
    summary="KI-Plausibilität der Hausgeldabrechnung anstoßen (nur Hinweise)",
)
async def start_hoa_statement_check(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    from mhvp.hoa.models import HoaStatement

    async with tenant_tx(request, principal) as session:
        st = await session.scalar(select(HoaStatement).where(HoaStatement.id == statement_id))
        if st is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        payload, snapshot_hash = await ai_check.hoa_payload(session, st)
        run_id = await _start(
            request, principal, statement_id, "hoa", payload, snapshot_hash, session
        )
    await _dispatch(request, principal, run_id)
    async with tenant_tx(request, principal) as session:
        return await _state(session, statement_id)


@router.get(
    "/hoa/statements/{statement_id}/ai-check",
    summary="KI-Plausibilität der Hausgeldabrechnung: Läufe und Hinweise",
)
async def get_hoa_statement_check(
    statement_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ)
) -> dict[str, Any]:
    from mhvp.hoa.models import HoaStatement

    async with tenant_tx(request, principal) as session:
        if await session.get(HoaStatement, statement_id) is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return await _state(session, statement_id)
