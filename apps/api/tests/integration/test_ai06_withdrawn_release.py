"""AI06 (GAH-203, GAH-204): after a later withdrawal of the release, the DPA document, the DPA
flag or the training opt-out no provider call happens, neither through the gateway, nor the
embedding route, nor the batch path (submit and poll). Fake provider counts every call, no
network.

Expected values by hand: before the withdrawal one synchronous call succeeds (1 call). After
each withdrawal a chat run is not ``succeeded`` and the call counter stays at 1; the batch
submit captures nothing (0 batches); a submitted batch is not polled (0 polls) and its run goes
back to ``deferred`` with reason ``release_withdrawn`` and the aborted batch id; the batch is
cancelled at the provider exactly once (GAI-610, 1 cancel call)."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import providers
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_ag04_ai_provider_batch import (
    FakeBatchProvider,
    _call,
    _defer_copy,
    _run,
)
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m7_ai import BUCKET, PROVIDER, _chat, _settings, _upload

pytestmark = pytest.mark.integration
P = "/api/v1/ai/providers/anthropic"


class CountingProvider(FakeBatchProvider):
    def __init__(self) -> None:
        super().__init__()
        self.polls = 0
        self.cancelled: list[str] = []

    async def cancel_batch(self, batch_id: str) -> None:
        self.cancelled.append(batch_id)

    async def poll_batch(self, batch_id: str) -> providers.BatchPoll:
        self.polls += 1
        return await super().poll_batch(batch_id)


@pytest.fixture
def fake() -> Iterator[CountingProvider]:
    provider = CountingProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ai6a-{RUN}", name=f"AI06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ai6b-{RUN}", name=f"AI06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name in ("ai6admin", "ai6second"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


async def _config(settings: Any, tenant_id: uuid.UUID, **changes: Any) -> dict[str, Any]:
    """Sets fields of the anthropic configuration directly (later withdrawal) and returns the
    stored snapshot of the changed fields before the change."""
    from sqlalchemy import select

    from mhvp.ai.models import AiProvider, AiProviderConfig
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            row = await session.scalar(
                select(AiProviderConfig).where(AiProviderConfig.provider == AiProvider.ANTHROPIC)
            )
            assert row is not None
            before = {k: getattr(row, k) for k in changes}
            for key, value in changes.items():
                setattr(row, key, value)
            return before
    finally:
        await engine.dispose()


async def _embedding_reason(settings: Any, tenant_id: uuid.UUID) -> str | None:
    from mhvp.ai import embeddings
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            route, reason = await embeddings.embedding_route(session)
            assert route is None
            return reason
    finally:
        await engine.dispose()


WITHDRAWALS: list[dict[str, Any]] = [
    {"released_at": None, "released_by": None},
    {"dpa_document_id": None},
    {"data_processing_agreement_signed": False},
    {"training_opt_out_confirmed": False},
]


def test_withdrawn_release_dpa_or_opt_out_stops_every_provider_call(
    client: TestClient,
    world: World,
    fake: CountingProvider,
    database: Database,
    redis_url: str,
) -> None:
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "ai6admin"))
    second = bearer(login(client, world, "ai6second"))
    dpa = _upload(client, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    body = {**PROVIDER, "dpa_document_id": dpa, "batch_enabled": True}
    response = client.put(P, json=body, headers=admin)
    assert response.status_code == 200, response.text
    assert client.post(f"{P}/release", headers=second).status_code == 200
    done = _chat(client, admin, "summarize", f"Fasse zusammen {RUN}", [])
    assert done["status"] == "succeeded"
    assert len(fake.calls) == 1

    for change in WITHDRAWALS:
        before = asyncio.run(_config(settings, world.tenant_a, **change))
        # Gateway: no route, no call.
        blocked = _chat(client, admin, "summarize", f"Nochmal {RUN} {change}", [])
        assert blocked["status"] != "succeeded", change
        assert len(fake.calls) == 1, change
        # Batch submit: no usable batch configuration, nothing captured, no call.
        asyncio.run(_defer_copy(settings, world.tenant_a, done["id"]))
        report = asyncio.run(_call(settings, "submit_deferred", world.tenant_a))
        assert report["submitted"] == 0, change
        assert fake.batches == {}, change
        assert len(fake.calls) == 1, change
        asyncio.run(_config(settings, world.tenant_a, **before))

    # Embedding route under the same conditions (no OpenAI configuration here: no route).
    assert asyncio.run(_embedding_reason(settings, world.tenant_a)) is not None

    # Poll path: a batch submitted while released, the opt-out withdrawn before the poll.
    run_id = asyncio.run(_defer_copy(settings, world.tenant_a, done["id"]))
    report = asyncio.run(_call(settings, "submit_deferred", world.tenant_a))
    assert report["submitted"] >= 1
    assert len(fake.batches) == 1
    asyncio.run(_config(settings, world.tenant_a, training_opt_out_confirmed=False))
    fake.ended = True
    report = asyncio.run(_call(settings, "poll_submitted", world.tenant_a))
    assert report["batches"] == 0
    assert fake.polls == 0
    # GAI-610: the open batch is cancelled at the provider (id only, no content).
    assert fake.cancelled == ["msgbatch_0"]
    assert report["cancelled"] == 1
    assert len(fake.calls) == 1
    status, ref, _cost = asyncio.run(_run(settings, world.tenant_a, run_id))
    assert status == "queued"
    assert ref["batch"]["state"] == "deferred"
    assert ref["batch"]["reason"] == "release_withdrawn"
    assert ref["batch"]["aborted_batch_id"] == "msgbatch_0"
    assert ref["batch"]["provider_cancel"] == "cancelled"


async def _openai_reason(settings: Any, tenant_id: uuid.UUID, **fields: Any) -> str | None:
    from mhvp.ai.models import AiProvider, AiProviderConfig
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            from sqlalchemy import select

            row = await session.scalar(
                select(AiProviderConfig).where(AiProviderConfig.provider == AiProvider.OPENAI)
            )
            assert row is not None
            for key, value in fields.items():
                setattr(row, key, value)
        return await _embedding_reason(settings, tenant_id)
    finally:
        await engine.dispose()


def test_embedding_route_blocks_after_withdrawn_dpa_or_opt_out(
    client: TestClient, world: World, fake: CountingProvider, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "ai6admin"))
    second = bearer(login(client, world, "ai6second"))
    dpa = _upload(client, admin, "avv2.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    models = {
        **PROVIDER["models"],
        "embedding": {
            "model": "text-embedding-3-small",
            "input_eur_per_mtok": "0.02",
            "output_eur_per_mtok": "0",
        },
    }
    body = {**PROVIDER, "models": models, "dpa_document_id": dpa}
    response = client.put("/api/v1/ai/providers/openai", json=body, headers=admin)
    assert response.status_code == 200, response.text
    assert client.post("/api/v1/ai/providers/openai/release", headers=second).status_code == 200
    for change, text in (
        ({"training_opt_out_confirmed": False}, "AVV-Nachweis oder Opt-out fehlt"),
        ({"training_opt_out_confirmed": True, "dpa_document_id": None}, "AVV-Nachweis"),
        (
            {"dpa_document_id": uuid.UUID(dpa), "released_at": None, "released_by": None},
            "Freigabe Vier-Augen fehlt",
        ),
    ):
        reason = asyncio.run(_openai_reason(settings, world.tenant_a, **change))
        assert reason is not None, change
        assert text in reason, (change, reason)
    assert fake.calls == []
