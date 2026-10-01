"""Batch processing for runs that are not time critical (9.3, M7-07).

The providers' batch APIs (Anthropic Message Batches, OpenAI Batch) are not wired in the
provider clients of this platform (``providers.py`` has no batch call, nothing is claimed that
the adapter cannot prove). Until they are, the same interface runs as a nightly collective
run: a caller marks a queued run as deferred (``defer``); it is not dispatched to the worker
but picked up by the nightly job ``mhvp.ai.batch_nightly`` and executed through the regular
gateway path (release, DPA evidence, budget, deduplication, cascade). Swapping the collective
run for a provider batch later changes ``submit_deferred`` only; callers keep ``defer``.

Only tasks listed in ``BATCH_TASKS`` may be deferred (classification and history analysis, no
chat, no user facing extraction).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.ai.models import AiTask, AiTaskRun, RunStatus
from mhvp.core.logging import get_logger

log = get_logger("mhvp.ai.batch")
BATCH_KEY = "batch"
BATCH_TASKS: frozenset[AiTask] = frozenset(
    {AiTask.CLASSIFY_DOCUMENT, AiTask.CLASSIFY_EMAIL, AiTask.SUMMARIZE, AiTask.PROPOSE_POSTING}
)
MAX_RUNS_PER_TENANT = 200
MODE = "nightly"  # "provider" once a provider batch call is wired and verified


def defer(run: AiTaskRun) -> bool:
    """Marks a queued run for the nightly collective run; False when the task may not wait."""
    if run.task not in BATCH_TASKS or run.status is not RunStatus.QUEUED:
        return False
    run.input_ref = {**(run.input_ref or {}), BATCH_KEY: {"mode": MODE, "state": "deferred"}}
    return True


def is_deferred(run: AiTaskRun) -> bool:
    return bool((run.input_ref or {}).get(BATCH_KEY)) and run.status is RunStatus.QUEUED


async def deferred_run_ids(
    session: AsyncSession, limit: int = MAX_RUNS_PER_TENANT
) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(AiTaskRun.id)
                .where(
                    AiTaskRun.status == RunStatus.QUEUED,
                    AiTaskRun.input_ref[BATCH_KEY]["state"].astext == "deferred",
                )
                .order_by(AiTaskRun.created_at)
                .limit(limit)
            )
        ).all()
    )


async def submit_deferred(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    blobs: Any,
) -> dict[str, int]:
    """Executes the deferred runs of one tenant one after another through ``run_and_propose``.
    A failing run is marked by the regular path; the others still run."""
    from mhvp.ai import jobs
    from mhvp.core.db.tenancy import tenant_transaction

    async with tenant_transaction(factory, tenant_id) as session:
        ids = await deferred_run_ids(session)
    report = {"runs": 0, "succeeded": 0, "other": 0}
    for run_id in ids:
        run = await jobs.run_and_propose(factory, tenant_id, run_id, blobs, None)
        report["runs"] += 1
        if run is not None and run.status is RunStatus.SUCCEEDED:
            report["succeeded"] += 1
        else:
            report["other"] += 1
    return report


async def run_callers(
    factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, settings: Any
) -> dict[str, Any]:
    """Callers of the collective run (M7-07): the nightly classification of inbound mails
    without a suggestion, behind the tenant switch ``batch_mail_classification``. Each caller
    reports counts or ``skipped``; a failing caller never stops the others."""
    from mhvp.communication import batch_classify

    report: dict[str, Any] = {}
    try:
        report["mail_classification"] = await batch_classify.run_for_tenant(
            factory, settings, tenant_id
        )
    except Exception:
        log.exception("ai batch caller failed", caller="mail_classification")
        report["mail_classification"] = {"error": True}
    return report
