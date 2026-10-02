"""AG04 (GAB-09): provider batch for deferred runs. Fake provider with recorded batch
behaviour, no network.

Expected values by hand: batch switch off by default and price factor 1; a factor outside
(0, 1] is rejected (422), a reader may not change the configuration (403), the other tenant
does not see the configuration. With the switch on a deferred summarize run is captured, not
called: zero synchronous provider calls, one batch with one request, the run stays queued with
state submitted. A poll of an open batch changes nothing; after the end the run succeeds from
the batch answer (1000 input and 500 output tokens on the small tier at 1 and 5 EUR per
million tokens = 0,0035 EUR list price) and the factor 0,5 gives 0,00175 EUR."""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import providers
from mhvp.ai.providers import BatchPoll, BatchRequest, Completion
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m7_ai import BUCKET, PROVIDER, _chat, _settings, _upload

pytestmark = pytest.mark.integration
P = "/api/v1/ai/providers/anthropic"


class FakeBatchProvider:
    """Answers ``complete`` synchronously and batches from recorded results."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.batches: dict[str, list[BatchRequest]] = {}
        self.ended = False

    def _answer(self, model: str) -> Completion:
        data = {"summary": "Stapel", "open_points": []}
        return Completion(data=data, raw_text="", tokens_in=1000, tokens_out=500, model=model)

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        return self._answer(kwargs["model"])

    async def submit_batch(self, requests: list[BatchRequest]) -> str:
        batch_id = f"msgbatch_{len(self.batches)}"
        self.batches[batch_id] = list(requests)
        return batch_id

    async def poll_batch(self, batch_id: str) -> BatchPoll:
        if not self.ended:
            return BatchPoll(ended=False)
        return BatchPoll(
            ended=True,
            results={r.custom_id: self._answer(r.model) for r in self.batches[batch_id]},
        )


@pytest.fixture
def fake() -> Iterator[FakeBatchProvider]:
    provider = FakeBatchProvider()
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
        a, _ = await services.provision_tenant(factory, slug=f"ag4a-{RUN}", name=f"AG04 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag4b-{RUN}", name=f"AG04 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ag4admin", a, "tenant_admin"),
            ("ag4second", a, "tenant_admin"),
            ("ag4reader", a, "read_only"),
            ("ag4other", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


async def _defer_copy(settings: Any, tenant_id: uuid.UUID, run_id: str) -> uuid.UUID:
    """Queues a deferred copy of a finished run with a different instruction."""
    from mhvp.ai import batch
    from mhvp.ai.models import AiTaskRun, RunStatus
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            done = await session.get(AiTaskRun, uuid.UUID(run_id))
            assert done is not None
            ref = {
                k: v
                for k, v in done.input_ref.items()
                if k not in ("progress", "input_stats", "deduplicated_from")
            }
            copy = AiTaskRun(
                tenant_id=tenant_id,
                task=done.task,
                prompt_version=done.prompt_version,
                input_hash="0" * 64,
                input_ref={**ref, "instruction": f"Nachts {RUN}"},
                status=RunStatus.QUEUED,
            )
            assert batch.defer(copy)
            session.add(copy)
            await session.flush()
            return copy.id
    finally:
        await engine.dispose()


async def _call(settings: Any, fn: str, tenant_id: uuid.UUID) -> dict[str, Any]:
    from mhvp.ai import batch
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.documents.blobs import BlobStore

    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        result: dict[str, Any] = await getattr(batch, fn)(factory, tenant_id, BlobStore(settings))
        return result
    finally:
        await engine.dispose()


async def _run(settings: Any, tenant_id: uuid.UUID, run_id: uuid.UUID) -> Any:
    from mhvp.ai.models import AiTaskRun
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            row = await session.get(AiTaskRun, run_id)
            assert row is not None
            return row.status.value, dict(row.input_ref), Decimal(row.cost_eur)
    finally:
        await engine.dispose()


def test_provider_batch_switch_capture_poll_and_price_factor(
    client: TestClient,
    world: World,
    fake: FakeBatchProvider,
    database: Database,
    redis_url: str,
) -> None:
    settings = _settings(database, redis_url)
    admin = bearer(login(client, world, "ag4admin"))
    second = bearer(login(client, world, "ag4second"))
    dpa = _upload(client, admin, "avv.txt", b"Auftragsverarbeitungsvertrag Muster", "text/plain")
    body = {**PROVIDER, "dpa_document_id": dpa}
    stored = _ok(client.put(P, json=body, headers=admin))
    assert (stored["batch_enabled"], Decimal(stored["batch_price_factor"])) == (False, 1)
    for bad in ("0", "1.5"):
        response = client.put(P, json={**body, "batch_price_factor": bad}, headers=admin)
        assert response.status_code == 422, response.text
    reader = bearer(login(client, world, "ag4reader"))
    assert client.put(P, json=body, headers=reader).status_code == 403
    stored = _ok(
        client.put(
            P, json={**body, "batch_enabled": True, "batch_price_factor": "0.5"}, headers=admin
        )
    )
    assert stored["batch_enabled"] is True
    assert Decimal(stored["batch_price_factor"]) == Decimal("0.5")
    # A later change without the fields keeps them (None leaves the stored value).
    stored = _ok(client.put(P, json=body, headers=admin))
    assert stored["batch_enabled"] is True
    _ok(client.post(f"{P}/release", headers=second))
    other = bearer(login(client, world, "ag4other"))
    others = _ok(client.get("/api/v1/ai/providers", headers=other))
    assert all(not p.get("batch_enabled") for p in others)

    # A regular run first (synchronous), then a deferred copy goes through the batch.
    done = _chat(client, admin, "summarize", f"Fasse zusammen {RUN}", [])
    assert done["status"] == "succeeded"
    sync_calls = len(fake.calls)
    run_id = asyncio.run(_defer_copy(settings, world.tenant_a, done["id"]))
    report = asyncio.run(_call(settings, "submit_deferred", world.tenant_a))
    assert report["submitted"] == 1
    assert len(fake.calls) == sync_calls
    assert [len(r) for r in fake.batches.values()] == [1]
    status, ref, _cost = asyncio.run(_run(settings, world.tenant_a, run_id))
    assert status == "queued"
    assert ref["batch"]["state"] == "submitted"
    assert ref["batch"]["batch_id"] == "msgbatch_0"
    assert ref["batch"]["cycle"] == 1

    # The other tenant has nothing to poll; an open batch changes nothing.
    assert asyncio.run(_call(settings, "poll_submitted", world.tenant_b))["batches"] == 0
    assert asyncio.run(_call(settings, "poll_submitted", world.tenant_a))["open"] == 1
    assert asyncio.run(_run(settings, world.tenant_a, run_id))[0] == "queued"

    fake.ended = True
    report = asyncio.run(_call(settings, "poll_submitted", world.tenant_a))
    assert report["succeeded"] == 1
    assert report["resubmitted"] == 0
    assert len(fake.calls) == sync_calls  # answered from the batch, no synchronous call
    status, ref, cost = asyncio.run(_run(settings, world.tenant_a, run_id))
    assert status == "succeeded"
    assert ref["batch"]["state"] == "done"
    assert ref["batch"]["pure_batch"] is True
    assert Decimal(ref["batch"]["list_cost_eur"]) == Decimal("0.0035")
    assert cost == Decimal("0.00175")
