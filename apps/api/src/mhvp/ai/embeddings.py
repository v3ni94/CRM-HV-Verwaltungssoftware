"""Embeddings and similarity search (9.1 RAG, M7-03, operator decision 26.09.2026).

* Provider: OpenAI ``text-embedding-3-small`` through the existing adapter (EU base URL when the
  configured region is ``eu``); the model name and price come from
  ``AiProviderConfig.models["embedding"]`` (operator entered, never invented here). Anthropic
  offers no embeddings; without a released OpenAI configuration nothing is embedded and the
  keyword search stays in place.
* Storage: ``ai_embedding`` (pgvector, RLS per tenant). Sources are extracted document texts and
  knowledge entries, split into chunks of ``CHUNK_CHARS``; the chunk text itself is not stored.
* Input masking: IBAN, e-mail and phone values are masked before the text leaves the platform
  (``mhvp.objektakte.masking.mask_identifiers``, the same rule as the contact change task).
* Budget: every provider call is an ``AiTaskRun`` of task ``embed`` with tokens and cost, so
  the monthly budget per provider applies exactly as for the other tasks (hard stop, 9.1).
* Search: cosine distance (``<=>``), best chunk per source, ``MAX_COSINE_DISTANCE`` cut-off.
  Callers fall back to the keyword search when the tenant has no embeddings, no usable route
  or the provider fails (``retrieve_documents`` returns ``None``).
"""

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.ai import gateway, providers
from mhvp.ai.models import (
    AiEmbedding,
    AiExample,
    AiKnowledgeEntry,
    AiProvider,
    AiProviderConfig,
    AiTask,
    AiTaskRun,
    EmbeddingSourceKind,
    RunStatus,
)
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.logging import get_logger
from mhvp.documents.models import Document, TextStatus
from mhvp.objektakte.masking import mask_identifiers

log = get_logger("mhvp.ai.embeddings")

PROMPT_VERSION = "embed-v1"  # recorded on every run (9.1: prompt_version is mandatory)
CHUNK_CHARS = 1500  # about 400 tokens per chunk
CHUNK_OVERLAP = 200
MAX_CHUNKS_PER_SOURCE = 200  # very long documents: the rest is not embedded (status shows it)
BATCH_CHUNKS = 64  # chunks per provider call
SOURCES_PER_BATCH = 20  # sources loaded per transaction
MAX_BATCHES_PER_JOB = 500
QUERY_CHARS = 2000
# Cosine distance beyond which a hit is not offered (assumption, docs/ASSUMPTIONS.md); the
# caller then falls back to the keyword search.
MAX_COSINE_DISTANCE = 0.8
NO_ROUTE = "Keine Einbettungen: OpenAI mit Stufe embedding ist nicht freigegeben"


@dataclass
class EmbeddingRoute:
    config: AiProviderConfig
    model: str
    price_in: Decimal


@dataclass
class IndexReport:
    """Result of one index job (also the ``status`` of the last run in the status endpoint)."""

    batches: int = 0
    sources: int = 0
    chunks: int = 0
    skipped_unchanged: int = 0
    cost_eur: Decimal = Decimal(0)
    stopped: str | None = None  # None: nothing left; else the reason (budget, provider, route)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "batches": self.batches,
            "sources": self.sources,
            "chunks": self.chunks,
            "skipped_unchanged": self.skipped_unchanged,
            "cost_eur": str(self.cost_eur.quantize(Decimal("0.0001"))),
            "stopped": self.stopped,
            "errors": self.errors,
        }


# Route and budget -------------------------------------------------------------------------


async def embedding_route(session: AsyncSession) -> tuple[EmbeddingRoute | None, str | None]:
    """The OpenAI configuration with an ``embedding`` tier, under the same release conditions
    as every other route (four eyes release, DPA evidence, opt-out, key; rule 0.1.13)."""
    config = await session.scalar(
        select(AiProviderConfig).where(
            AiProviderConfig.provider == AiProvider.OPENAI, AiProviderConfig.enabled.is_(True)
        )
    )
    if config is None:
        return None, f"{NO_ROUTE} (nicht eingerichtet oder nicht aktiv)"
    if config.released_at is None:
        return None, f"{NO_ROUTE} (Freigabe Vier-Augen fehlt)"
    if not (
        config.data_processing_agreement_signed
        and config.dpa_document_id
        and config.training_opt_out_confirmed
    ):
        return None, f"{NO_ROUTE} (AVV-Nachweis oder Opt-out fehlt)"
    if not config.api_key:
        return None, f"{NO_ROUTE} (API-Schlüssel fehlt)"
    entry = (config.models or {}).get("embedding") or {}
    try:
        model = str(entry["model"])
        price_in = Decimal(str(entry["input_eur_per_mtok"]))
    except (KeyError, ArithmeticError):
        return None, f"{NO_ROUTE} (Modell oder Preis der Stufe embedding fehlt)"
    return EmbeddingRoute(config, model, price_in), None


async def budget_block(session: AsyncSession, route: EmbeddingRoute, now: datetime) -> str | None:
    budget = route.config.monthly_budget_eur
    spent = await gateway.spent_this_month(session, now, AiProvider.OPENAI)
    if budget <= 0 or spent >= budget:
        return f"openai: Monatsbudget erreicht ({spent:.2f} von {budget:.2f} EUR); harte Sperre"
    return None


def cost(route: EmbeddingRoute, tokens_in: int) -> Decimal:
    return Decimal(tokens_in) * route.price_in / gateway.MTOK


async def _embed_with_retry(
    client: providers.EmbeddingClient, model: str, inputs: list[str]
) -> providers.Embeddings:
    for delay in (*gateway.RETRY_DELAYS_S, None):
        try:
            return await client.embed(model=model, inputs=inputs)
        except providers.ProviderError as exc:
            if not exc.retryable or delay is None:
                raise
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


def _client(route: EmbeddingRoute) -> providers.EmbeddingClient:
    client = providers.client_for(
        AiProvider.OPENAI, route.config.api_key or "", route.config.endpoint_region
    )
    if not providers.supports_embeddings(client):
        raise providers.ProviderError("provider offers no embeddings")
    return client  # type: ignore[return-value]


def _run_row(
    route: EmbeddingRoute,
    *,
    actor: uuid.UUID | None,
    tenant_id: uuid.UUID,
    input_hash: str,
    input_ref: dict[str, Any],
) -> AiTaskRun:
    return AiTaskRun(
        tenant_id=tenant_id,
        created_by=actor,
        task=AiTask.EMBED,
        provider=AiProvider.OPENAI,
        model=route.model,
        prompt_version=PROMPT_VERSION,
        input_hash=input_hash,
        input_ref=input_ref,
        status=RunStatus.RUNNING,
    )


async def _call(
    session: AsyncSession,
    route: EmbeddingRoute,
    inputs: list[str],
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    input_ref: dict[str, Any],
) -> tuple[list[list[float]], AiTaskRun]:
    """One provider call recorded as an ``AiTaskRun`` (budget accounting like every task).
    The run row stays with status ``failed`` and the error text when the provider fails."""
    digest = hashlib.sha256("\n".join(inputs).encode()).hexdigest()
    run = _run_row(route, actor=actor, tenant_id=tenant_id, input_hash=digest, input_ref=input_ref)
    session.add(run)
    await session.flush()
    started = datetime.now(UTC)
    client = _client(route)
    try:
        result = await _embed_with_retry(client, route.model, inputs)
    except providers.ProviderError as exc:
        run.status = RunStatus.FAILED
        run.error = str(exc)[:500]
        run.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        raise
    finally:
        await providers.close_client(client)
    run.status = RunStatus.SUCCEEDED
    run.model = result.model or route.model
    run.tokens_in = result.tokens_in
    run.tokens_out = 0
    run.cost_eur = cost(route, result.tokens_in)
    run.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    return result.vectors, run


# Chunking ---------------------------------------------------------------------------------


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Fixed size character windows with overlap, cut at a line or blank when one is near."""
    text = " ".join(text.split("\r"))
    text = text.strip()
    if not text:
        return []
    if size <= 0:
        raise ValueError("size must be positive")
    overlap = min(max(overlap, 0), size // 2)
    chunks: list[str] = []
    start = 0
    while start < len(text) and len(chunks) < MAX_CHUNKS_PER_SOURCE:
        end = min(start + size, len(text))
        if end < len(text):
            # Prefer a line end in the second half of the window, then a blank.
            cut = text.rfind("\n", start + size // 2, end)
            if cut <= start:
                cut = text.rfind(" ", start + size // 2, end)
            if cut > start:
                end = cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def masked_source_text(
    kind: EmbeddingSourceKind, row: Document | AiKnowledgeEntry | AiExample
) -> str:
    if isinstance(row, AiExample):
        # GA04-12: features and confirmed result as compact JSON, masked like every source.
        raw = json.dumps(
            {"task": row.task.value, "merkmale": row.features, "ergebnis": row.result},
            ensure_ascii=False,
            sort_keys=True,
        )
    elif isinstance(row, AiKnowledgeEntry):
        raw = f"{row.title}\n{row.content}"
    else:
        raw = f"{row.title}\n{row.ocr_text or ''}"
    return mask_identifiers(raw)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# Pending sources and status ---------------------------------------------------------------


def _embedded_at(kind: EmbeddingSourceKind, source_id: Any) -> Any:
    return (
        select(AiEmbedding.updated_at)
        .where(
            AiEmbedding.source_kind == kind,
            AiEmbedding.source_id == source_id,
            AiEmbedding.chunk_index == 0,
        )
        .scalar_subquery()
    )


def _documents_with_text() -> Any:
    return select(Document).where(
        Document.text_status == TextStatus.EXTRACTED,
        Document.ocr_text.is_not(None),
        func.length(func.btrim(Document.ocr_text)) > 0,
    )


def _pending_documents() -> Any:
    embedded = _embedded_at(EmbeddingSourceKind.DOCUMENT, Document.id)
    return _documents_with_text().where(or_(embedded.is_(None), embedded < Document.updated_at))


def _knowledge_live() -> Any:
    return select(AiKnowledgeEntry).where(AiKnowledgeEntry.deleted_at.is_(None))


def _pending_knowledge() -> Any:
    embedded = _embedded_at(EmbeddingSourceKind.KNOWLEDGE_ENTRY, AiKnowledgeEntry.id)
    return _knowledge_live().where(or_(embedded.is_(None), embedded < AiKnowledgeEntry.updated_at))


def _pending_examples() -> Any:
    embedded = _embedded_at(EmbeddingSourceKind.AI_EXAMPLE, AiExample.id)
    return select(AiExample).where(or_(embedded.is_(None), embedded < AiExample.updated_at))


async def _count(session: AsyncSession, query: Any) -> int:
    value = await session.scalar(select(func.count()).select_from(query.subquery()))
    return int(value or 0)


async def status(session: AsyncSession) -> dict[str, Any]:
    """Counters for the settings page: sources with text, embedded and pending per kind, chunk
    rows, the route state and the last index run."""
    route, reason = await embedding_route(session)
    docs_total = await _count(session, _documents_with_text())
    docs_pending = await _count(session, _pending_documents())
    kb_total = await _count(session, _knowledge_live())
    kb_pending = await _count(session, _pending_knowledge())
    ex_total = await _count(session, select(AiExample))
    ex_pending = await _count(session, _pending_examples())
    chunks = int(await session.scalar(select(func.count()).select_from(AiEmbedding)) or 0)
    last = await session.scalar(
        select(AiTaskRun)
        .where(AiTaskRun.task == AiTask.EMBED, AiTaskRun.input_ref["job_summary"].as_boolean())
        .order_by(AiTaskRun.created_at.desc())
        .limit(1)
    )
    return {
        "enabled": route is not None,
        "reason": reason,
        "model": route.model if route else None,
        "documents_total": docs_total,
        "documents_embedded": docs_total - docs_pending,
        "documents_pending": docs_pending,
        "knowledge_total": kb_total,
        "knowledge_embedded": kb_total - kb_pending,
        "knowledge_pending": kb_pending,
        "examples_total": ex_total,
        "examples_embedded": ex_total - ex_pending,
        "examples_pending": ex_pending,
        "chunks": chunks,
        "last_run_at": last.created_at if last else None,
        "last_run_status": last.status.value if last else None,
        "last_run_error": last.error if last else None,
        "last_run_report": (last.input_ref.get("report") if last else None),
    }


async def has_embeddings(session: AsyncSession, kind: EmbeddingSourceKind) -> bool:
    row = await session.scalar(
        select(AiEmbedding.id).where(AiEmbedding.source_kind == kind).limit(1)
    )
    return row is not None


async def delete_all(session: AsyncSession) -> int:
    result = await session.execute(delete(AiEmbedding))
    return int(getattr(result, "rowcount", 0) or 0)


async def remove_orphans(session: AsyncSession) -> int:
    """Rows whose document is gone or whose knowledge entry is deleted or gone."""
    live_docs = select(Document.id)
    live_kb = select(AiKnowledgeEntry.id).where(AiKnowledgeEntry.deleted_at.is_(None))
    result = await session.execute(
        delete(AiEmbedding).where(
            or_(
                (AiEmbedding.source_kind == EmbeddingSourceKind.DOCUMENT)
                & AiEmbedding.source_id.not_in(live_docs),
                (AiEmbedding.source_kind == EmbeddingSourceKind.KNOWLEDGE_ENTRY)
                & AiEmbedding.source_id.not_in(live_kb),
            )
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


# Index job --------------------------------------------------------------------------------


@dataclass
class _Pending:
    kind: EmbeddingSourceKind
    source_id: uuid.UUID
    text: str
    chunks: list[str]


async def _load_pending(session: AsyncSession, limit: int) -> list[_Pending]:
    items: list[_Pending] = []
    docs = (
        await session.scalars(_pending_documents().order_by(Document.updated_at).limit(limit))
    ).all()
    for document in docs:
        text = masked_source_text(EmbeddingSourceKind.DOCUMENT, document)
        items.append(_Pending(EmbeddingSourceKind.DOCUMENT, document.id, text, chunk_text(text)))
    remaining = limit - len(items)
    if remaining > 0:
        entries = (
            await session.scalars(
                _pending_knowledge().order_by(AiKnowledgeEntry.updated_at).limit(remaining)
            )
        ).all()
        for entry in entries:
            text = masked_source_text(EmbeddingSourceKind.KNOWLEDGE_ENTRY, entry)
            items.append(
                _Pending(EmbeddingSourceKind.KNOWLEDGE_ENTRY, entry.id, text, chunk_text(text))
            )
    remaining = limit - len(items)
    if remaining > 0:
        shots = (
            await session.scalars(
                _pending_examples().order_by(AiExample.updated_at).limit(remaining)
            )
        ).all()
        for shot in shots:
            text = masked_source_text(EmbeddingSourceKind.AI_EXAMPLE, shot)
            items.append(_Pending(EmbeddingSourceKind.AI_EXAMPLE, shot.id, text, chunk_text(text)))
    return items


async def _existing_hash(session: AsyncSession, item: _Pending) -> str | None:
    value: str | None = await session.scalar(
        select(AiEmbedding.content_hash).where(
            AiEmbedding.source_kind == item.kind,
            AiEmbedding.source_id == item.source_id,
            AiEmbedding.chunk_index == 0,
        )
    )
    return value


async def _touch(session: AsyncSession, item: _Pending, now: datetime) -> None:
    await session.execute(
        update(AiEmbedding)
        .where(AiEmbedding.source_kind == item.kind, AiEmbedding.source_id == item.source_id)
        .values(updated_at=now)
    )


async def _replace_rows(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    item: _Pending,
    vectors: list[list[float]],
    model: str,
    digest: str,
    now: datetime,
) -> None:
    await session.execute(
        delete(AiEmbedding).where(
            AiEmbedding.source_kind == item.kind, AiEmbedding.source_id == item.source_id
        )
    )
    for index, vector in enumerate(vectors):
        session.add(
            AiEmbedding(
                tenant_id=tenant_id,
                created_by=actor,
                source_kind=item.kind,
                source_id=item.source_id,
                chunk_index=index,
                chunk_count=len(vectors),
                content_hash=digest,
                model=model,
                embedding=vector,
                updated_at=now,
            )
        )


async def index_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    report: IndexReport,
    now: datetime | None = None,
) -> bool:
    """One transaction: up to ``SOURCES_PER_BATCH`` pending sources, at most ``BATCH_CHUNKS``
    chunks per provider call. Returns False when nothing is left or the job must stop
    (``report.stopped`` names the reason)."""
    now = now or datetime.now(UTC)
    route, reason = await embedding_route(session)
    if route is None:
        report.stopped = reason
        return False
    items = await _load_pending(session, SOURCES_PER_BATCH)
    if not items:
        return False
    # Unchanged text (metadata edit only): no provider call, just mark as current.
    todo: list[_Pending] = []
    for item in items:
        digest = content_hash(item.text)
        if not item.chunks:
            continue
        if await _existing_hash(session, item) == digest:
            await _touch(session, item, now)
            report.skipped_unchanged += 1
            continue
        todo.append(item)
    if not todo:
        report.batches += 1
        return True
    blocked = await budget_block(session, route, now)
    if blocked is not None:
        report.stopped = blocked
        return False
    # Fill the call up to BATCH_CHUNKS whole sources; a source larger than that goes alone.
    selected: list[_Pending] = []
    total = 0
    for item in todo:
        if selected and total + len(item.chunks) > BATCH_CHUNKS:
            break
        selected.append(item)
        total += len(item.chunks)
    inputs = [chunk for item in selected for chunk in item.chunks]
    try:
        vectors, run = await _call(
            session,
            route,
            inputs,
            tenant_id=tenant_id,
            actor=actor,
            input_ref={"sources": len(selected), "chunks": len(inputs), "index_job": True},
        )
    except providers.ProviderError as exc:
        report.stopped = f"openai: {exc}"
        report.errors.append(str(exc)[:200])
        return False
    offset = 0
    for item in selected:
        item_vectors = vectors[offset : offset + len(item.chunks)]
        offset += len(item.chunks)
        await _replace_rows(
            session,
            tenant_id,
            actor,
            item,
            item_vectors,
            run.model or route.model,
            content_hash(item.text),
            now,
        )
    report.batches += 1
    report.sources += len(selected)
    report.chunks += len(inputs)
    report.cost_eur += run.cost_eur
    return True


async def index_tenant(
    factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    *,
    max_batches: int = MAX_BATCHES_PER_JOB,
) -> IndexReport:
    """Runs batches until nothing is pending, the budget is reached, the provider fails or
    ``max_batches`` is hit. Each batch commits on its own so a stop keeps what was embedded."""
    report = IndexReport()
    async with tenant_transaction(factory, tenant_id) as session:
        await remove_orphans(session)
    while report.batches < max_batches:
        async with tenant_transaction(factory, tenant_id) as session:
            try:
                more = await index_batch(session, tenant_id, actor, report)
            except Exception as exc:  # the run row of the failed call is kept by the commit
                report.stopped = f"Fehler: {type(exc).__name__}"
                report.errors.append(str(exc)[:200])
                more = False
        if not more:
            break
    else:
        report.stopped = f"Höchstzahl von {max_batches} Durchläufen erreicht"
    async with tenant_transaction(factory, tenant_id) as session:
        # Summary row of the job (no tokens, no cost): the status endpoint shows it as the last
        # run; a stop (budget, route, provider) is recorded as failed with the reason.
        session.add(
            AiTaskRun(
                tenant_id=tenant_id,
                created_by=actor,
                task=AiTask.EMBED,
                provider=AiProvider.OPENAI,
                prompt_version=PROMPT_VERSION,
                input_hash=hashlib.sha256(str(report.as_dict()).encode()).hexdigest(),
                input_ref={"job_summary": True, "report": report.as_dict()},
                status=RunStatus.SUCCEEDED if report.stopped is None else RunStatus.FAILED,
                error=report.stopped,
            )
        )
    log.info(
        "ai.embeddings.indexed",
        tenant_id=str(tenant_id),
        batches=report.batches,
        sources=report.sources,
        chunks=report.chunks,
        stopped=report.stopped,
    )
    return report


# Search -----------------------------------------------------------------------------------


async def embed_query(
    session: AsyncSession, text: str, *, tenant_id: uuid.UUID, actor: uuid.UUID | None
) -> list[float] | None:
    """Vector of a question (masked, cut to ``QUERY_CHARS``); ``None`` when no route, budget
    reached or the provider fails. The call is recorded as a run like any other."""
    route, _reason = await embedding_route(session)
    if route is None:
        return None
    now = datetime.now(UTC)
    if await budget_block(session, route, now) is not None:
        return None
    masked = mask_identifiers(text)[:QUERY_CHARS].strip()
    if not masked:
        return None
    try:
        vectors, _run = await _call(
            session,
            route,
            [masked],
            tenant_id=tenant_id,
            actor=actor,
            input_ref={"query": True, "chunks": 1},
        )
    except providers.ProviderError as exc:
        log.warning("ai.embeddings.query_failed", error=str(exc)[:200])
        return None
    return vectors[0] if vectors else None


async def similar_sources(
    session: AsyncSession,
    kind: EmbeddingSourceKind,
    vector: list[float],
    *,
    limit: int,
    only_ids: list[uuid.UUID] | None = None,
    max_distance: float = MAX_COSINE_DISTANCE,
) -> list[tuple[uuid.UUID, float]]:
    """Sources ordered by the cosine distance of their best chunk (RLS limits the tenant;
    ``only_ids`` applies a permission filter before ranking, 9.1)."""
    distance = func.min(AiEmbedding.embedding.cosine_distance(vector)).label("distance")
    query = (
        select(AiEmbedding.source_id, distance)
        .where(AiEmbedding.source_kind == kind)
        .group_by(AiEmbedding.source_id)
        .having(distance <= max_distance)
        .order_by(distance.asc())
        .limit(limit)
    )
    if only_ids is not None:
        if not only_ids:
            return []
        query = query.where(AiEmbedding.source_id.in_(only_ids))
    rows = (await session.execute(query)).all()
    return [(uuid.UUID(str(source_id)), float(dist)) for source_id, dist in rows]


async def retrieve_documents(
    session: AsyncSession,
    question: str,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    limit: int,
    only_ids: list[uuid.UUID] | None = None,
) -> list[Document] | None:
    """Documents by similarity, or ``None`` for the keyword fallback (no embeddings for this
    tenant, no route, budget reached, provider error or nothing under the distance cut-off)."""
    if not await has_embeddings(session, EmbeddingSourceKind.DOCUMENT):
        return None
    vector = await embed_query(session, question, tenant_id=tenant_id, actor=actor)
    if vector is None:
        return None
    hits = await similar_sources(
        session, EmbeddingSourceKind.DOCUMENT, vector, limit=limit, only_ids=only_ids
    )
    if not hits:
        return None
    order = {source_id: rank for rank, (source_id, _d) in enumerate(hits)}
    rows = (
        await session.scalars(
            select(Document).where(Document.id.in_(list(order)), Document.ocr_text.is_not(None))
        )
    ).all()
    return sorted(rows, key=lambda d: order.get(d.id, len(order)))


async def rank_knowledge(
    session: AsyncSession,
    question: str,
    entries: list[AiKnowledgeEntry],
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    limit: int,
) -> list[AiKnowledgeEntry] | None:
    """Reorders the given (already permission scoped) knowledge entries by similarity to the
    question; ``None`` keeps the caller's order (keyword or recency fallback)."""
    if not entries or not await has_embeddings(session, EmbeddingSourceKind.KNOWLEDGE_ENTRY):
        return None
    vector = await embed_query(session, question, tenant_id=tenant_id, actor=actor)
    if vector is None:
        return None
    hits = await similar_sources(
        session,
        EmbeddingSourceKind.KNOWLEDGE_ENTRY,
        vector,
        limit=limit,
        only_ids=[e.id for e in entries],
    )
    if not hits:
        return None
    by_id = {e.id: e for e in entries}
    return [by_id[source_id] for source_id, _d in hits if source_id in by_id]


async def rank_examples(
    session: AsyncSession,
    task: AiTask,
    text: str,
    *,
    tenant_id: uuid.UUID,
    actor: uuid.UUID | None,
    limit: int,
) -> list[AiExample] | None:
    """GA04-12: the learning examples of ``task`` most similar to ``text`` (cosine distance of
    the masked example text, only embedded examples). ``None`` keeps the caller's recency
    order: no embeddings, no released route (AVV, rule 13), budget reached, provider error or
    nothing under the distance cut-off."""
    if not text.strip() or not await has_embeddings(session, EmbeddingSourceKind.AI_EXAMPLE):
        return None
    ids = list((await session.scalars(select(AiExample.id).where(AiExample.task == task))).all())
    if not ids:
        return None
    vector = await embed_query(session, text, tenant_id=tenant_id, actor=actor)
    if vector is None:
        return None
    hits = await similar_sources(
        session, EmbeddingSourceKind.AI_EXAMPLE, vector, limit=limit, only_ids=ids
    )
    if not hits:
        return None
    rows = {
        r.id: r
        for r in (
            await session.scalars(select(AiExample).where(AiExample.id.in_([i for i, _ in hits])))
        ).all()
    }
    return [rows[i] for i, _d in hits if i in rows]
