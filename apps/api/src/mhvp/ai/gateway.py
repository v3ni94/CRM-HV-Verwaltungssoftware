"""AI gateway (9.1, 9.3, 9.4): checks, prompt, provider call, validation, cost, logging.

Order of checks before any data leaves the platform: a released provider configuration with DPA
evidence and confirmed training opt-out (rule 0.1.13), a model and prices for the tier, and the
monthly budget. Results are validated against the task schema; one retry with the error message.
"""

import hashlib
import io
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.ai import providers, tasks
from mhvp.ai.models import AiExample, AiProvider, AiProviderConfig, AiTask, AiTaskRun, RunStatus
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import emit
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document, TextStatus

MAX_INPUT_CHARS = 400_000
MAX_TABLE_ROWS = 2_000
FEW_SHOT = 8
WARN_SHARE = Decimal("0.8")
MTOK = Decimal(1_000_000)


class GatewayBlockedError(Exception):
    """The run must not start; the reason is shown to the user."""


@dataclass
class TaskInput:
    text: str
    document_ids: list[uuid.UUID]
    context: dict[str, Any]


# Input preparation (deterministic, no AI) ------------------------------------------------


def _table_text(rows: list[list[Any]]) -> str:
    lines = []
    for number, row in enumerate(rows[:MAX_TABLE_ROWS], start=1):
        cells = ["" if c is None else str(c).strip() for c in row]
        if any(cells):
            lines.append(f"Zeile {number}: " + " | ".join(cells))
    return "\n".join(lines)


def spreadsheet_text(data: bytes) -> str:
    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for sheet in book.worksheets:
        rows = [list(r) for r in sheet.iter_rows(values_only=True)]
        parts.append(f"Tabellenblatt {sheet.title}\n{_table_text(rows)}")
    return "\n\n".join(parts)


def csv_text(data: bytes) -> str:
    import csv

    text = data.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t") if text else csv.excel
    return _table_text([list(r) for r in csv.reader(io.StringIO(text), dialect)])


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def document_text(session: AsyncSession, blobs: BlobStore, document_id: uuid.UUID) -> str:
    document = await session.get(Document, document_id)
    if document is None:
        raise GatewayBlockedError("Dokument nicht gefunden.")
    if document.mime_type == XLSX:
        body = spreadsheet_text(blobs.get(document.storage_ref))
    elif document.mime_type == "text/csv":
        body = csv_text(blobs.get(document.storage_ref))
    elif document.text_status is TextStatus.EXTRACTED and document.ocr_text:
        body = document.ocr_text
    else:
        raise GatewayBlockedError(
            f"Für {document.filename} liegt noch kein Text vor (Texterkennung ausstehend)."
        )
    return f'<datei name="{document.filename}" id="{document.id}">\n{body}\n</datei>'


async def retrieve(session: AsyncSession, question: str, limit: int = 6) -> list[Document]:
    """Full text retrieval over documents the tenant holds (RLS). Embeddings follow (M7-03)."""
    words = set(re.findall(r"[\wÄÖÜäöüß]{3,}", question))
    if not words:
        return []
    # Any word may match (OR); ranking puts documents with more matches first.
    ts = func.to_tsquery("german", " | ".join(sorted(words)))
    rows = (
        await session.scalars(
            select(Document)
            .where(Document.search_vector.op("@@")(ts), Document.ocr_text.is_not(None))
            .order_by(func.ts_rank(Document.search_vector, ts).desc())
            .limit(limit)
        )
    ).all()
    return list(rows)


async def build_input(session: AsyncSession, blobs: BlobStore, run: AiTaskRun) -> TaskInput:
    ref = run.input_ref
    document_ids = [uuid.UUID(d) for d in ref.get("document_ids", [])]
    parts = [f"Anweisung des Nutzers: {ref.get('instruction', '')}"]
    if run.task is AiTask.ANSWER_QUESTION:
        found = await retrieve(session, str(ref.get("instruction", "")))
        document_ids = [*document_ids, *[d.id for d in found if d.id not in document_ids]]
    for document_id in document_ids:
        parts.append(await document_text(session, blobs, document_id))
    text = "\n\n".join(parts)
    if len(text) > MAX_INPUT_CHARS:
        raise GatewayBlockedError(
            f"Die Unterlagen sind zu umfangreich ({len(text)} Zeichen, höchstens "
            f"{MAX_INPUT_CHARS}). Bitte in kleinere Teile aufteilen."
        )
    return TaskInput(text=text, document_ids=document_ids, context=dict(ref.get("context", {})))


# Checks and cost --------------------------------------------------------------------------


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def spent_this_month(
    session: AsyncSession, now: datetime, provider: AiProvider | None = None
) -> Decimal:
    query = select(func.coalesce(func.sum(AiTaskRun.cost_eur), 0)).where(
        AiTaskRun.created_at >= month_start(now)
    )
    if provider is not None:
        query = query.where(AiTaskRun.provider == provider)
    value = await session.scalar(query)
    return Decimal(value or 0)


ONLY = {"anthropic_only": AiProvider.ANTHROPIC, "openai_only": AiProvider.OPENAI}
FIRST = {"anthropic_first": AiProvider.ANTHROPIC, "openai_first": AiProvider.OPENAI}


async def routing_strategy(session: AsyncSession) -> str:
    from mhvp.platform.models import TenantSettings

    value = await session.scalar(select(TenantSettings.ai_routing))
    return value or "anthropic_first"


async def _provider_order(session: AsyncSession, strategy: str) -> list[AiProvider]:
    """Preferred provider first; "alternate" starts with the provider not used last."""
    if strategy in ONLY:
        return [ONLY[strategy]]
    first = FIRST.get(strategy)
    if strategy == "alternate":
        last = await session.scalar(
            select(AiTaskRun.provider)
            .where(AiTaskRun.provider.is_not(None))
            .order_by(AiTaskRun.created_at.desc())
            .limit(1)
        )
        first = AiProvider.OPENAI if last is AiProvider.ANTHROPIC else AiProvider.ANTHROPIC
    others = [p for p in AiProvider if p is not first]
    return [first, *others] if first else others


@dataclass
class Route:
    config: AiProviderConfig
    model: str
    price_in: Decimal
    price_out: Decimal


async def routes(session: AsyncSession, task: AiTask) -> tuple[list[Route], list[str]]:
    """Usable providers in strategy order plus the reasons for the unusable ones."""
    strategy = await routing_strategy(session)
    order = await _provider_order(session, strategy)
    configs = {
        c.provider: c
        for c in (
            await session.scalars(
                select(AiProviderConfig).where(AiProviderConfig.enabled.is_(True))
            )
        ).all()
    }
    if not configs:
        raise GatewayBlockedError("Kein freigegebener KI-Anbieter eingerichtet.")
    usable: list[Route] = []
    reasons: list[str] = []
    for provider in order:
        config = configs.get(provider)
        if config is None:
            if strategy in ONLY:
                reasons.append(f"{provider.value}: nicht eingerichtet oder nicht aktiv")
            continue
        if config.released_at is None:
            reasons.append(f"{config.provider.value}: Freigabe (Vier-Augen) fehlt")
            continue
        if not (
            config.data_processing_agreement_signed
            and config.dpa_document_id
            and config.training_opt_out_confirmed
        ):
            reasons.append(f"{config.provider.value}: AVV-Nachweis oder Opt-out fehlt")
            continue
        if not config.api_key:
            reasons.append(f"{config.provider.value}: API-Schlüssel fehlt")
            continue
        tier = config.task_tiers.get(task.value) or tasks.DEFAULT_TIERS.get(task, "large")
        entry = (config.models or {}).get(tier) or {}
        try:
            price_in = Decimal(str(entry["input_eur_per_mtok"]))
            price_out = Decimal(str(entry["output_eur_per_mtok"]))
            model = str(entry["model"])
        except (KeyError, ArithmeticError):
            reasons.append(f"{config.provider.value}: Modell oder Preise für Stufe {tier} fehlen")
            continue
        usable.append(Route(config, model, price_in, price_out))
    return usable, reasons


async def route(session: AsyncSession, task: AiTask) -> Route:
    usable, reasons = await routes(session, task)
    if not usable:
        raise GatewayBlockedError("; ".join(reasons))
    return usable[0]


def cost(route_: Route, tokens_in: int, tokens_out: int) -> Decimal:
    # Cache reads are priced like normal input here: an upper bound for the budget check.
    return (Decimal(tokens_in) * route_.price_in + Decimal(tokens_out) * route_.price_out) / MTOK


def input_hash(task: AiTask, version: str, text: str, context: dict[str, Any]) -> str:
    payload = json.dumps({"t": task.value, "v": version, "x": text, "c": context}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def examples(session: AsyncSession, task: AiTask) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(AiExample)
            .where(AiExample.task == task)
            .order_by(AiExample.created_at.desc())
            .limit(FEW_SHOT)
        )
    ).all()
    return [{"merkmale": r.features, "bestaetigt": r.result} for r in rows]


def confidence_of(task: AiTask, data: dict[str, Any]) -> Decimal | None:
    items: list[Any] = []
    if task is AiTask.EXTRACT_CONTACTS:
        items = data.get("contacts", [])
    elif task is AiTask.EXTRACT_PROPERTY:
        items = [*data.get("units", []), *data.get("parties", [])]
    values = [min(max(float(i.get("confidence", 0)), 0.0), 1.0) for i in items]
    if not values:
        return None
    return Decimal(str(round(sum(values) / len(values), 8)))


# Execution --------------------------------------------------------------------------------


def _messages(item: TaskInput, shots: list[dict[str, Any]]) -> list[dict[str, str]]:
    context = json.dumps(item.context, ensure_ascii=False, sort_keys=True)
    parts = []
    if shots:
        parts.append(
            "Bestätigte Beispiele dieses Mandanten (nur als Orientierung für Format und "
            f"Zuordnung):\n{json.dumps(shots, ensure_ascii=False)}"
        )
    parts.append(f"Kontext: {context}")
    parts.append(f"<daten>\n{item.text}\n</daten>")
    return [{"role": "user", "content": "\n\n".join(parts)}]


async def execute(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    blobs: BlobStore,
    actor_user_id: uuid.UUID | None,
) -> AiTaskRun:
    """Run a queued task. Three short transactions; the provider call happens outside them."""
    now = datetime.now(UTC)
    async with tenant_transaction(factory, tenant_id) as session:
        run = await session.get(AiTaskRun, run_id)
        if run is None or run.status is not RunStatus.QUEUED:
            raise GatewayBlockedError("Lauf nicht gefunden oder bereits bearbeitet.")
        task = run.task
        prompt = tasks.prompt(task, run.prompt_version)
        try:
            item = await build_input(session, blobs, run)
            usable, reasons = await routes(session, task)
            # Budget per provider; exhausted providers are skipped (fallback, M7-02) unless
            # the strategy names a single provider, then the run is blocked.
            plan: list[tuple[Route, Decimal, Decimal]] = []
            for candidate in usable:
                budget = candidate.config.monthly_budget_eur
                spent = await spent_this_month(session, now, candidate.config.provider)
                if budget <= 0 or spent >= budget:
                    reasons.append(
                        f"{candidate.config.provider.value}: Monatsbudget erreicht "
                        f"({spent:.2f} von {budget:.2f} EUR); harte Sperre"
                    )
                    continue
                plan.append((candidate, spent, budget))
            if not plan:
                raise GatewayBlockedError("; ".join(reasons))
            skipped = list(reasons)
        except GatewayBlockedError as exc:
            run.status, run.error = RunStatus.BLOCKED, str(exc)
            await emit(
                session,
                tenant_id=tenant_id,
                type="ai.run_blocked",
                entity_type="ai_task_run",
                entity_id=run.id,
                actor_user_id=actor_user_id,
                payload={"reason": str(exc)},
            )
            return run
        previous = await session.scalar(
            select(AiTaskRun)
            .where(
                AiTaskRun.input_hash == run.input_hash,
                AiTaskRun.status == RunStatus.SUCCEEDED,
                AiTaskRun.id != run.id,
            )
            .order_by(AiTaskRun.created_at.desc())
            .limit(1)
        )
        if previous is not None:  # deduplication by input hash (9.3)
            run.status, run.output, run.confidence = (
                RunStatus.SUCCEEDED,
                previous.output,
                previous.confidence,
            )
            run.provider, run.model = previous.provider, previous.model
            run.input_ref = {**run.input_ref, "deduplicated_from": str(previous.id)}
            return run
        shots = await examples(session, task)
        keys = {c.config.provider: c.config.api_key or "" for c, _, _ in plan}
        chosen, spent, budget = plan[0]
        run.status, run.provider, run.model = (
            RunStatus.RUNNING,
            chosen.config.provider,
            chosen.model,
        )
    started = time.monotonic()
    schema = tasks.json_schema(task)
    base_messages = _messages(item, shots)
    tokens_in = tokens_out = 0
    output: dict[str, Any] | None = None
    error: str | None = None
    for step in plan:
        chosen, spent, budget = step
        provider = chosen.config.provider
        client = providers.client_for(provider, keys[provider])
        messages = base_messages
        provider_failed = False
        for attempt in range(2):
            try:
                completion = await client.complete(
                    model=chosen.model,
                    system=prompt.system,
                    messages=messages,
                    schema=schema,
                    max_tokens=16000,
                )
            except providers.ProviderError as exc:
                error = f"Anbieterfehler: {exc}"
                provider_failed = True
                break
            tokens_in += completion.tokens_in
            tokens_out += completion.tokens_out
            try:
                output = tasks.SCHEMAS[task].model_validate(completion.data).model_dump(mode="json")
                error = None
                break
            except ValidationError as exc:
                error = f"Schemafehler: {exc.errors()[0]['msg']} bei {exc.errors()[0]['loc']}"
                if attempt == 0:
                    messages = [
                        *messages,
                        {"role": "assistant", "content": completion.raw_text or "{}"},
                        {
                            "role": "user",
                            "content": f"Die Antwort verletzt das Schema: {error}. "
                            "Bitte vollständig und schemakonform neu antworten.",
                        },
                    ]
        if not provider_failed:
            break
        # Provider error: try the next provider of the strategy (fallback), if any.
        skipped.append(f"{provider.value}: {error}")
    async with tenant_transaction(factory, tenant_id) as session:
        run = await session.get(AiTaskRun, run_id)
        assert run is not None  # noqa: S101 - locked above
        run.provider, run.model = chosen.config.provider, chosen.model
        if skipped:
            run.input_ref = {**run.input_ref, "fallback": skipped}
        run.tokens_in, run.tokens_out = tokens_in, tokens_out
        run.cost_eur = cost(chosen, tokens_in, tokens_out)
        run.duration_ms = int((time.monotonic() - started) * 1000)
        if output is not None:
            run.status, run.output = RunStatus.SUCCEEDED, output
            run.confidence = confidence_of(task, output)
        else:
            run.status, run.error = RunStatus.FAILED, error
        threshold = budget * WARN_SHARE
        if spent < threshold <= spent + run.cost_eur:
            await emit(
                session,
                tenant_id=tenant_id,
                type="ai.budget_warning",
                entity_type="ai_task_run",
                entity_id=run.id,
                actor_user_id=actor_user_id,
                payload={"threshold": "80%"},
            )
        await emit(
            session,
            tenant_id=tenant_id,
            type=f"ai.run_{run.status.value}",
            entity_type="ai_task_run",
            entity_id=run.id,
            actor_user_id=actor_user_id,
            payload={"task": task.value, "cost_eur": str(run.cost_eur)},
        )
    return run
