"""Batch processing for runs that are not time critical (9.3, M7-07, GAB-09).

A caller marks a queued run as deferred (``defer``); it is not dispatched to the worker but
picked up by the nightly job ``mhvp.ai.batch_nightly`` (``submit_deferred``). Two modes:

* Provider batch (``MODE_PROVIDER``): when the tenant switched ``batch_enabled`` on for a
  provider configuration whose client offers ``submit_batch``/``poll_batch`` (Anthropic
  Message Batches API), each run goes through the regular gateway path (release, DPA
  evidence, budget, masking, deduplication) with a capture active
  (``providers.batch_capture``). The provider call is not made; its request is recorded and
  the run returns to ``queued`` with state ``submitted``. All recorded requests of the tenant
  go out in one batch. The beat task ``mhvp.ai.batch_poll`` polls the batch; once it ended,
  each run is executed through the gateway again and the identical requests are answered from
  the batch results (replay). A request without a result (a further tool or chunk round)
  starts the next cycle; after ``MAX_CYCLES`` the run is executed synchronously. Calls to a
  provider without batch support run synchronously as before.
* Collective run (``MODE_NIGHTLY``, default): the deferred runs are executed one after another
  through the regular gateway path.

The batch price factor is entered per provider configuration (``batch_price_factor``,
default 1, no invented discount); it is applied to the run's cost only when every provider
answer of the run came from the batch. ADR 0025.

Only tasks listed in ``BATCH_TASKS`` may be deferred (classification and history analysis, no
chat, no user facing extraction).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.ai import providers
from mhvp.ai.models import AiProvider, AiProviderConfig, AiTask, AiTaskRun, RunStatus
from mhvp.core.logging import get_logger

log = get_logger("mhvp.ai.batch")
BATCH_KEY = "batch"
BATCH_TASKS: frozenset[AiTask] = frozenset(
    {AiTask.CLASSIFY_DOCUMENT, AiTask.CLASSIFY_EMAIL, AiTask.SUMMARIZE, AiTask.PROPOSE_POSTING}
)
MAX_RUNS_PER_TENANT = 200
MODE_NIGHTLY = "nightly"
MODE_PROVIDER = "provider"
MODE = MODE_NIGHTLY  # mode written by ``defer``; the provider mode is chosen per tenant
MAX_CYCLES = 3
COST_QUANT = Decimal("0.00000001")


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


class BatchPending(BaseException):
    """Raised by the capture instead of a provider call; derives from ``BaseException`` so the
    gateway's error handling does not turn it into a failed run."""


def request_key(
    provider: AiProvider,
    model: str,
    system: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    max_tokens: int,
) -> str:
    """Stable id of one provider request (64 hex chars, valid as batch ``custom_id``)."""
    raw = json.dumps(
        [provider.value, model, system, messages, schema, max_tokens],
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class Capture:
    """Active while a deferred run passes the gateway (``providers.batch_capture``)."""

    batch_providers: frozenset[AiProvider]
    results: dict[str, providers.Completion | providers.ProviderError] = field(default_factory=dict)
    pending: dict[str, providers.BatchRequest] = field(default_factory=dict)
    pending_provider: dict[str, AiProvider] = field(default_factory=dict)
    sync_calls: int = 0
    replayed: int = 0

    def wrap(self, provider: AiProvider, client: Any) -> Any:
        return _CapturingClient(self, provider, client)

    def reset_run(self) -> None:
        self.pending, self.pending_provider = {}, {}
        self.sync_calls = self.replayed = 0


class _CapturingClient:
    def __init__(self, capture: Capture, provider: AiProvider, inner: Any) -> None:
        self._capture, self._provider, self._inner = capture, provider, inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        max_tokens: int,
    ) -> providers.Completion:
        cap = self._capture
        if self._provider not in cap.batch_providers or not providers.supports_batch(self._inner):
            cap.sync_calls += 1
            result: providers.Completion = await self._inner.complete(
                model=model, system=system, messages=messages, schema=schema, max_tokens=max_tokens
            )
            return result
        key = request_key(self._provider, model, system, messages, schema, max_tokens)
        if key in cap.results:
            answer = cap.results[key]
            if isinstance(answer, providers.ProviderError):
                raise answer
            cap.replayed += 1
            return answer
        cap.pending[key] = providers.BatchRequest(
            custom_id=key,
            model=model,
            system=system,
            messages=messages,
            schema=schema,
            max_tokens=max_tokens,
        )
        cap.pending_provider[key] = self._provider
        raise BatchPending(key)


def _is_pending(exc: BaseException) -> bool:
    if isinstance(exc, BatchPending):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_pending(e) for e in exc.exceptions)
    return False


async def batch_configs(session: AsyncSession) -> dict[AiProvider, AiProviderConfig]:
    """Released provider configurations with the batch switch on (tenant scoped)."""
    rows = (
        await session.scalars(
            select(AiProviderConfig).where(
                AiProviderConfig.enabled.is_(True),
                AiProviderConfig.batch_enabled.is_(True),
                AiProviderConfig.released_at.is_not(None),
            )
        )
    ).all()
    return {r.provider: r for r in rows if r.api_key}


async def _run_once(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    blobs: Any,
    capture: Capture | None,
) -> AiTaskRun | None:
    """One pass through ``run_and_propose``; ``None`` when the run waits for the batch."""
    from mhvp.ai import jobs

    if capture is None:
        return await jobs.run_and_propose(factory, tenant_id, run_id, blobs, None)
    capture.reset_run()
    token = providers.batch_capture.set(capture)
    try:
        return await jobs.run_and_propose(factory, tenant_id, run_id, blobs, None)
    except BaseException as exc:
        if _is_pending(exc):
            return None
        raise
    finally:
        providers.batch_capture.reset(token)


async def _mark(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    state: dict[str, Any],
) -> None:
    """Writes the batch state; a run left ``running`` by the capture returns to ``queued``."""
    from mhvp.core.db.tenancy import tenant_transaction

    async with tenant_transaction(factory, tenant_id) as session:
        row = await session.get(AiTaskRun, run_id)
        if row is None:
            return
        if row.status is RunStatus.RUNNING:
            row.status = RunStatus.QUEUED
        row.input_ref = {**(row.input_ref or {}), BATCH_KEY: state}


async def _finish(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run: AiTaskRun | None,
    capture: Capture,
    config: AiProviderConfig,
    previous: dict[str, Any],
) -> bool:
    """Batch bookkeeping after the replay; the price factor only for a pure batch run."""
    from mhvp.core.db.tenancy import tenant_transaction

    if run is None:
        return False
    pure = capture.replayed > 0 and capture.sync_calls == 0
    factor = Decimal(config.batch_price_factor)
    async with tenant_transaction(factory, tenant_id) as session:
        row = await session.get(AiTaskRun, run.id)
        if row is None:
            return False
        state = {**previous, "state": "done", "price_factor": str(factor), "pure_batch": pure}
        if pure and row.status is RunStatus.SUCCEEDED and factor != 1:
            state["list_cost_eur"] = str(row.cost_eur)
            row.cost_eur = (Decimal(row.cost_eur) * factor).quantize(COST_QUANT)
        row.input_ref = {**(row.input_ref or {}), BATCH_KEY: state}
        return row.status is RunStatus.SUCCEEDED


async def _submit(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    config: AiProviderConfig,
    waiting: dict[uuid.UUID, tuple[list[str], int]],
    requests: dict[str, providers.BatchRequest],
) -> str | None:
    """Sends the collected requests as one provider batch and marks the waiting runs."""
    client = providers.client_for(config.provider, config.api_key or "", config.endpoint_region)
    try:
        batch_id: str = await client.submit_batch(list(requests.values()))  # type: ignore[attr-defined]
    except providers.ProviderError as exc:
        log.warning("ai_batch_submit_failed", tenant_id=str(tenant_id), reason=str(exc))
        for run_id in waiting:
            await _mark(factory, tenant_id, run_id, {"mode": MODE, "state": "deferred"})
        return None
    finally:
        await providers.close_client(client)
    now = datetime.now(UTC).isoformat()
    for run_id, (keys, cycle) in waiting.items():
        await _mark(
            factory,
            tenant_id,
            run_id,
            {
                "mode": MODE_PROVIDER,
                "state": "submitted",
                "provider": config.provider.value,
                "batch_id": batch_id,
                "keys": keys,
                "cycle": cycle,
                "submitted_at": now,
            },
        )
    return batch_id


async def submit_deferred(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    blobs: Any,
) -> dict[str, int]:
    """Nightly entry. Provider batch when the tenant enabled it (see module docstring),
    otherwise the collective run: the deferred runs one after another through
    ``run_and_propose``. A failing run is marked by the regular path; the others still run."""
    from mhvp.core.db.tenancy import tenant_transaction

    async with tenant_transaction(factory, tenant_id) as session:
        ids = await deferred_run_ids(session)
        configs = await batch_configs(session)
    report = {"runs": 0, "succeeded": 0, "other": 0, "submitted": 0}
    capture = Capture(frozenset(configs)) if configs else None
    waiting: dict[AiProvider, dict[uuid.UUID, tuple[list[str], int]]] = {}
    requests: dict[AiProvider, dict[str, providers.BatchRequest]] = {}
    for run_id in ids:
        run = await _run_once(factory, tenant_id, run_id, blobs, capture)
        report["runs"] += 1
        if run is None and capture is not None:
            provider = next(iter(capture.pending_provider.values()))
            waiting.setdefault(provider, {})[run_id] = (list(capture.pending), 1)
            requests.setdefault(provider, {}).update(capture.pending)
            report["submitted"] += 1
            continue
        if run is not None and run.status is RunStatus.SUCCEEDED:
            report["succeeded"] += 1
        else:
            report["other"] += 1
    for provider, runs in waiting.items():
        await _submit(factory, tenant_id, configs[provider], runs, requests[provider])
    return report


async def poll_submitted(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    blobs: Any,
) -> dict[str, int]:
    """Beat entry (``mhvp.ai.batch_poll``): polls the open batches of one tenant; for an ended
    batch the waiting runs are replayed through the gateway (see module docstring)."""
    from mhvp.core.db.tenancy import tenant_transaction

    async with tenant_transaction(factory, tenant_id) as session:
        rows = (
            await session.scalars(
                select(AiTaskRun)
                .where(
                    AiTaskRun.status == RunStatus.QUEUED,
                    AiTaskRun.input_ref[BATCH_KEY]["state"].astext == "submitted",
                )
                .order_by(AiTaskRun.created_at)
                .limit(MAX_RUNS_PER_TENANT)
            )
        ).all()
        open_runs = [(r.id, dict(r.input_ref[BATCH_KEY])) for r in rows]
        configs = await batch_configs(session)
    report = {"batches": 0, "open": 0, "runs": 0, "succeeded": 0, "resubmitted": 0, "sync": 0}
    by_batch: dict[str, list[tuple[uuid.UUID, dict[str, Any]]]] = {}
    for run_id, state in open_runs:
        by_batch.setdefault(str(state.get("batch_id")), []).append((run_id, state))
    for batch_id, members in by_batch.items():
        provider = AiProvider(members[0][1]["provider"])
        config = configs.get(provider)
        if config is None:
            # Switch turned off or release withdrawn: the runs go back to the nightly queue.
            for run_id, _state in members:
                await _mark(factory, tenant_id, run_id, {"mode": MODE, "state": "deferred"})
            continue
        client = providers.client_for(provider, config.api_key or "", config.endpoint_region)
        try:
            poll: providers.BatchPoll = await client.poll_batch(batch_id)  # type: ignore[attr-defined]
        except providers.ProviderError as exc:
            log.warning("ai_batch_poll_failed", tenant_id=str(tenant_id), reason=str(exc))
            continue
        finally:
            await providers.close_client(client)
        report["batches"] += 1
        if not poll.ended:
            report["open"] += 1
            continue
        capture = Capture(frozenset({provider}), results=dict(poll.results))
        waiting: dict[uuid.UUID, tuple[list[str], int]] = {}
        requests: dict[str, providers.BatchRequest] = {}
        for run_id, state in members:
            cycle = int(state.get("cycle") or 1)
            report["runs"] += 1
            run = await _run_once(factory, tenant_id, run_id, blobs, capture)
            if run is None and cycle < MAX_CYCLES:
                waiting[run_id] = (list(capture.pending), cycle + 1)
                requests.update(capture.pending)
                report["resubmitted"] += 1
                continue
            if run is None:
                await _mark(factory, tenant_id, run_id, {**state, "state": "sync"})
                run = await _run_once(factory, tenant_id, run_id, blobs, None)
                report["sync"] += 1
                if run is not None and run.status is RunStatus.SUCCEEDED:
                    report["succeeded"] += 1
                continue
            if await _finish(factory, tenant_id, run, capture, config, state):
                report["succeeded"] += 1
        if waiting:
            await _submit(factory, tenant_id, config, waiting, requests)
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
