"""M7-03 Einbettungen (Betreiberentscheidung 26.09.2026): Index-Lauf mit gefaktem Einbettungs-
Client (kein Netz), Statuszähler, Berechtigung des Neuaufbaus, Ähnlichkeitsranking mit
handgemachten Vektoren, Mandantentrennung (RLS), Schlüsselwort-Rückfall ohne Einbettungen und
harte Budgetsperre."""

import asyncio
import hashlib
import json
import math
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import select

from mhvp.ai import embeddings, gateway, providers
from mhvp.ai.models import (
    EMBEDDING_DIMENSIONS,
    AiEmbedding,
    AiKnowledgeEntry,
    AiTask,
    AiTaskRun,
    EmbeddingSourceKind,
)
from mhvp.ai.providers import Completion, Embeddings, ProviderError
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m7_ai import BUCKET, PROVIDER, _ok, _settings, _upload

pytestmark = pytest.mark.integration
M = "/api/v1"
DIMS = EMBEDDING_DIMENSIONS


def fake_vector(text: str) -> list[float]:
    """Deterministic bag of words vector: shared words give a small cosine distance."""
    vector = [0.0] * DIMS
    for word in {w.lower() for w in text.split() if len(w) > 2}:
        index = int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIMS
        vector[index] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeEmbeddingProvider:
    def __init__(self) -> None:
        self.embed_calls: list[dict[str, Any]] = []
        self.complete_calls: list[dict[str, Any]] = []
        self.fail_next: str | None = None
        self.tokens_in = 100

    async def embed(self, *, model: str, inputs: list[str]) -> Embeddings:
        self.embed_calls.append({"model": model, "inputs": list(inputs)})
        if self.fail_next is not None:
            reason, self.fail_next = self.fail_next, None
            raise ProviderError(reason)
        return Embeddings(
            vectors=[fake_vector(i) for i in inputs], tokens_in=self.tokens_in, model=model
        )

    async def complete(self, **kwargs: Any) -> Completion:
        self.complete_calls.append(kwargs)
        data = {"answer": "Antwort", "sources": []}
        return Completion(
            data=data, raw_text=json.dumps(data), tokens_in=10, tokens_out=5, model=kwargs["model"]
        )


@pytest.fixture
def fake() -> Iterator[FakeEmbeddingProvider]:
    provider = FakeEmbeddingProvider()
    providers.set_factory(lambda _p, _k, _r: provider)
    yield provider
    providers.set_factory(providers.default_factory)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"emb-{RUN}", name=f"Emb {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"emb2-{RUN}", name=f"Emb2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant_id, name, role in [
            (a, "embadmin", "tenant_admin"),
            (a, "embsecond", "tenant_admin"),
            (a, "embclerk", "standard"),
            (b, "embother", "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


def _inline(database: Database, redis_url: str) -> Any:
    return _settings(database, redis_url).model_copy(update={"ai_inline": True})


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_inline(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_inline(database, redis_url))) as test_client:
            yield test_client


OPENAI = {
    **PROVIDER,
    "models": {
        "small": {"model": "gpt-4.1-mini", "input_eur_per_mtok": "1", "output_eur_per_mtok": "4"},
        "large": {"model": "gpt-4.1", "input_eur_per_mtok": "5", "output_eur_per_mtok": "20"},
        "embedding": {
            "model": "text-embedding-3-small",
            "input_eur_per_mtok": "20",  # test price: visible in the usage view at 4 decimals
            "output_eur_per_mtok": "0",
        },
    },
}


def _setup_openai(c: TestClient, world: World, **overrides: Any) -> dict[str, str]:
    admin = bearer(login(c, world, "embadmin"))
    second = bearer(login(c, world, "embsecond"))
    dpa = _upload(c, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    body = {**OPENAI, "dpa_document_id": dpa, **overrides}
    _ok(c.put(f"{M}/ai/providers/openai", json=body, headers=admin), 200)
    _ok(c.post(f"{M}/ai/providers/openai/release", headers=second), 200)
    return admin


def _status(c: TestClient, h: dict[str, str]) -> dict[str, Any]:
    return _ok(c.get(f"{M}/ai/embeddings/status", headers=h), 200)  # type: ignore[no-any-return]


def _reindex(c: TestClient, h: dict[str, str], full: bool = False) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(f"{M}/ai/embeddings/reindex", json={"full": full}, headers=h), 202
    )


def _run(settings: Any, coro_factory: Any) -> Any:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    async def _go() -> Any:
        engine = create_app_engine(settings)
        try:
            return await coro_factory(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def test_reindex_needs_release_and_permission(
    client: TestClient, world: World, fake: FakeEmbeddingProvider
) -> None:
    admin = bearer(login(client, world, "embadmin"))
    clerk = bearer(login(client, world, "embclerk"))
    # No usable route yet: the status names it and the reindex refuses with 422.
    before = _status(client, admin)
    assert before["enabled"] is False
    assert "embedding" in (before["reason"] or "")
    refused = client.post(f"{M}/ai/embeddings/reindex", json={"full": False}, headers=admin)
    assert refused.status_code == 422, refused.text
    assert client.post(f"{M}/ai/embeddings/reindex", json={}, headers=clerk).status_code == 403
    # The standard role reads the settings (status) but never triggers the job.
    assert client.get(f"{M}/ai/embeddings/status", headers=clerk).status_code == 200
    assert fake.embed_calls == []


def test_index_job_counts_budget_and_masks(
    client: TestClient,
    world: World,
    fake: FakeEmbeddingProvider,
    database: Database,
    redis_url: str,
) -> None:
    admin = _setup_openai(client, world)
    doc_roof = _upload(
        client,
        admin,
        "dachbeschluss.txt",
        f"Dachbeschluss {RUN}: Die Sanierung des Daches wurde beschlossen. "
        "Rueckfragen an max@example.org oder IBAN DE89370400440532013000.".encode(),
        "text/plain",
    )
    doc_heating = _upload(
        client,
        admin,
        "heizung.txt",
        f"Heizungswartung {RUN}: Wartungsvertrag verlaengert.".encode(),
        "text/plain",
    )
    entry = _ok(
        client.post(
            f"{M}/ai/knowledge",
            json={"kind": "fact", "title": f"Muellabfuhr {RUN}", "content": "Dienstags."},
            headers=admin,
        ),
        201,
    )
    status = _status(client, admin)
    assert status["enabled"] is True
    assert status["model"] == "text-embedding-3-small"
    assert status["documents_pending"] >= 2
    assert status["knowledge_pending"] >= 1

    after = _reindex(client, admin)
    assert after["queued"] is False
    assert after["documents_pending"] == 0
    assert after["knowledge_pending"] == 0
    assert after["documents_embedded"] == after["documents_total"] >= 3  # incl. the DPA file
    assert after["knowledge_embedded"] == after["knowledge_total"] >= 1
    assert after["chunks"] >= 4
    assert after["last_run_status"] == "succeeded"
    assert after["last_run_report"]["stopped"] is None
    # Masked input: no e-mail or IBAN reaches the provider; the model is the configured one.
    sent = "\n".join(i for call in fake.embed_calls for i in call["inputs"])
    assert "max@example.org" not in sent
    assert "DE89370400440532013000" not in sent
    assert "[E-MAIL]" in sent
    assert "[IBAN]" in sent
    assert all(call["model"] == "text-embedding-3-small" for call in fake.embed_calls)
    # Budget accounting: runs of task "embed" with cost (100 tokens at 20 EUR/MTok per call).
    usage = _ok(client.get(f"{M}/ai/usage", headers=admin), 200)
    assert Decimal(usage["by_task"]["embed"]) > 0

    # A second run has nothing to do and makes no provider call.
    calls = len(fake.embed_calls)
    again = _reindex(client, admin)
    assert len(fake.embed_calls) == calls
    assert again["chunks"] == after["chunks"]

    # Semantic retrieval ranks the roof document first for a roof question and drops unrelated
    # documents (distance cut-off); a foreign tenant sees no vectors at all (RLS).
    settings = _inline(database, redis_url)

    async def _query(factory: Any) -> tuple[list[uuid.UUID], int, int]:
        async with tenant_transaction(factory, world.tenant_a) as session:
            found = await gateway.retrieve(
                session,
                "Dachbeschluss Sanierung des Daches beschlossen",
                tenant_id=world.tenant_a,
                actor=world.users["embadmin"],
            )
            ranked = await embeddings.rank_knowledge(
                session,
                f"Muellabfuhr {RUN} Dienstags",
                list(
                    await session.scalars(
                        select(AiKnowledgeEntry).where(
                            AiKnowledgeEntry.id == uuid.UUID(entry["id"])
                        )
                    )
                ),
                tenant_id=world.tenant_a,
                actor=None,
                limit=5,
            )
            assert ranked is not None
            assert [e.id for e in ranked] == [uuid.UUID(entry["id"])]
            own = len((await session.scalars(select(AiEmbedding.id))).all())
        async with tenant_transaction(factory, world.tenant_b) as session:
            foreign = len((await session.scalars(select(AiEmbedding.id))).all())
            assert (
                await embeddings.similar_sources(
                    session, EmbeddingSourceKind.DOCUMENT, fake_vector("Dachbeschluss"), limit=5
                )
                == []
            )
        return [d.id for d in found], own, foreign

    ids, own, foreign = _run(settings, _query)
    assert ids
    assert ids[0] == uuid.UUID(doc_roof)
    assert uuid.UUID(doc_heating) not in ids
    assert own >= 4
    assert foreign == 0
    other = bearer(login(client, world, "embother", tenant_id=world.tenant_b))
    assert _status(client, other)["chunks"] == 0

    # Full rebuild drops everything and embeds again.
    calls = len(fake.embed_calls)
    rebuilt = _reindex(client, admin, full=True)
    assert len(fake.embed_calls) > calls
    assert rebuilt["chunks"] == after["chunks"]


def test_similarity_ranking_with_hand_made_vectors(
    world: World, database: Database, redis_url: str
) -> None:
    settings = _inline(database, redis_url)

    def unit(index: int, second: int | None = None, weight: float = 0.0) -> list[float]:
        vector = [0.0] * DIMS
        vector[index] = 1.0
        if second is not None:
            vector[second] = weight
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector]

    near, mid, far = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def _go(factory: Any) -> list[tuple[uuid.UUID, float]]:
        async with tenant_transaction(factory, world.tenant_b) as session:
            for source_id, vector, chunk in [
                (near, unit(0, 1, 0.2), 0),
                (near, unit(5), 1),  # a worse chunk must not hurt the best chunk ranking
                (mid, unit(0, 1, 1.0), 0),
                (far, unit(2), 0),
            ]:
                session.add(
                    AiEmbedding(
                        tenant_id=world.tenant_b,
                        source_kind=EmbeddingSourceKind.KNOWLEDGE_ENTRY,
                        source_id=source_id,
                        chunk_index=chunk,
                        chunk_count=2 if source_id == near else 1,
                        content_hash="h",
                        model="hand",
                        embedding=vector,
                    )
                )
            await session.flush()
            hits = await embeddings.similar_sources(
                session, EmbeddingSourceKind.KNOWLEDGE_ENTRY, unit(0), limit=10
            )
            # Cleanup so other tests of the tenant start from zero.
            for row in (await session.scalars(select(AiEmbedding))).all():
                await session.delete(row)
            return hits

    hits = _run(settings, _go)
    assert [h[0] for h in hits] == [near, mid]  # far: distance 1.0 > cut-off
    assert hits[0][1] < hits[1][1] < embeddings.MAX_COSINE_DISTANCE
    assert hits[0][1] == pytest.approx(1 - 1 / math.sqrt(1.04), abs=1e-6)


def test_keyword_fallback_without_embeddings(
    client: TestClient,
    world: World,
    fake: FakeEmbeddingProvider,
    database: Database,
    redis_url: str,
) -> None:
    other = bearer(login(client, world, "embother", tenant_id=world.tenant_b))
    doc = _upload(
        client,
        other,
        "protokoll.txt",
        f"Versammlungsprotokoll Zaunbau {RUN}".encode(),
        "text/plain",
    )
    settings = _inline(database, redis_url)

    async def _go(factory: Any) -> list[uuid.UUID]:
        async with tenant_transaction(factory, world.tenant_b) as session:
            assert not await embeddings.has_embeddings(session, EmbeddingSourceKind.DOCUMENT)
            found = await gateway.retrieve(
                session, f"Zaunbau {RUN}", tenant_id=world.tenant_b, actor=None
            )
            return [d.id for d in found]

    assert uuid.UUID(doc) in _run(settings, _go)
    assert fake.embed_calls == []  # no route for tenant B: never a provider call


def test_budget_stop_and_provider_error(
    client: TestClient,
    world: World,
    fake: FakeEmbeddingProvider,
    database: Database,
    redis_url: str,
) -> None:
    # Price so high that a single call exceeds the budget: the first call runs (nothing spent
    # yet), everything after it is blocked with the hard stop.
    admin = _setup_openai(
        client,
        world,
        monthly_budget_eur="1.00",
        models={
            **OPENAI["models"],
            "embedding": {
                "model": "text-embedding-3-small",
                "input_eur_per_mtok": "1000000",
                "output_eur_per_mtok": "0",
            },
        },
    )
    _upload(client, admin, "budget1.txt", f"Budgettest eins {RUN}".encode(), "text/plain")
    first = _reindex(client, admin, full=True)
    assert first["last_run_status"] == "succeeded"
    _upload(client, admin, "budget2.txt", f"Budgettest zwei {RUN}".encode(), "text/plain")
    calls = len(fake.embed_calls)
    second = _reindex(client, admin)
    assert len(fake.embed_calls) == calls
    assert second["documents_pending"] == 1
    assert "Monatsbudget erreicht" in (second["last_run_report"]["stopped"] or "")
    usage = _ok(client.get(f"{M}/ai/usage", headers=admin), 200)
    assert usage["blocked"] is True
    # A question now falls back to the keyword search without a provider call.
    settings = _inline(database, redis_url)

    async def _go(factory: Any) -> int:
        query_runs = select(AiTaskRun.id).where(
            AiTaskRun.task == AiTask.EMBED, AiTaskRun.input_ref["query"].as_boolean()
        )
        async with tenant_transaction(factory, world.tenant_a) as session:
            before = len((await session.scalars(query_runs)).all())
            await gateway.retrieve(
                session, f"Budgettest zwei {RUN}", tenant_id=world.tenant_a, actor=None
            )
            # No query call was recorded: the budget check runs before the provider call.
            return len((await session.scalars(query_runs)).all()) - before

    assert _run(settings, _go) == 0
    assert len(fake.embed_calls) == calls

    # Provider error with budget available: the run row is kept as failed, the job stops.
    _setup_openai(client, world, monthly_budget_eur="1000.00")
    fake.fail_next = "HTTP 500: boom"
    stopped = _reindex(client, admin)
    assert stopped["last_run_status"] == "failed"
    assert "boom" in (stopped["last_run_error"] or "")
    assert stopped["documents_pending"] == 2  # budget2 plus the new DPA file of the re-setup
    fake.fail_next = None
    assert _reindex(client, admin)["documents_pending"] == 0
