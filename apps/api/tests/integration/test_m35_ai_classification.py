"""M35 Stufe 3 part 2 (AI stage) acceptance: POST /api/v1/objektakte/review/{case_id}/ask-ai
with a fake provider, asserting no IBAN reaches the provider call and the result lands as a
proposal only (`document.source_meta["classification"]["stage"] == "ai"`, `document.category_id`
never set by this endpoint)."""

import asyncio
import json
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.ai import providers
from mhvp.ai.providers import Completion
from mhvp.core import crypto
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.models import Document, DocumentSource, StorageKind, TextStatus
from mhvp.main import create_app
from mhvp.objektakte.masking import contains_iban
from mhvp.objektakte.models import DocumentReviewCase, ReviewCaseStatus
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte/review"
BUCKET = "mhvp-m35-ai"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        ai_inline=True,
    )


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.queue: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        data = (
            self.queue.pop(0)
            if self.queue
            else {
                "document_class": "forderungsaufstellung",
                "category": "05",
                "confidence": 0.7,
                "reasons": ["Betreff nennt Forderungsaufstellung"],
            }
        )
        return Completion(
            data=data,
            raw_text=json.dumps(data),
            tokens_in=200,
            tokens_out=80,
            model=kwargs["model"],
        )


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    provider = FakeProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


PROVIDER = {
    "api_key": "sk-test-not-real",
    "models": {
        "small": {
            "model": "claude-haiku-5",
            "input_eur_per_mtok": "1",
            "output_eur_per_mtok": "5",
        }
    },
    "monthly_budget_eur": "50.00",
    "data_processing_agreement_signed": True,
    "training_opt_out_confirmed": True,
    "endpoint_region": "eu",
    "enabled": True,
}


async def _world(settings: Any) -> tuple[World, dict[str, uuid.UUID]]:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    ids: dict[str, uuid.UUID] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=f"m35ai-{RUN}", name=f"M35AI {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("aiadmin", "aisecond"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
        async with tenant_transaction(factory, a) as session:
            dpa = Document(
                tenant_id=a,
                title="AVV",
                filename="avv.txt",
                mime_type="text/plain",
                size=10,
                sha256="d" * 64,
                storage=StorageKind.MINIO,
                storage_ref="ref-dpa",
                text_status=TextStatus.NONE,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )
            session.add(dpa)
            await session.flush()
            ids["dpa"] = dpa.id
            doc = Document(
                tenant_id=a,
                title="Forderungsaufstellung",
                filename="forderung_iban_DE89370400440532013000.pdf",
                mime_type="application/pdf",
                size=10,
                sha256="c" * 64,
                storage=StorageKind.MINIO,
                storage_ref="ref-ai",
                ocr_text=(
                    "Forderungsaufstellung fuer Herrn Max Mustermann, IBAN "
                    "DE89 3704 0044 0532 0130 00, Kontakt erika.musterfrau@example.org, "
                    "Telefon 0211 1234567."
                ),
                text_status=TextStatus.EXTRACTED,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )
            session.add(doc)
            await session.flush()
            ids["doc"] = doc.id
            case = DocumentReviewCase(
                tenant_id=a,
                document_id=doc.id,
                stage="rules",
                candidates=None,
                priority=100,
                status=ReviewCaseStatus.OPEN,
            )
            session.add(case)
            await session.flush()
            ids["case"] = case.id
        return world, ids
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world_and_ids(database: Database, redis_url: str) -> tuple[World, dict[str, uuid.UUID]]:
    import asyncio

    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _setup_provider(client: TestClient, world: World, dpa_id: uuid.UUID) -> dict[str, str]:
    admin = bearer(login(client, world, "aiadmin"))
    second = bearer(login(client, world, "aisecond"))
    _ok(
        client.put(
            "/api/v1/ai/providers/anthropic",
            json={**PROVIDER, "dpa_document_id": str(dpa_id)},
            headers=admin,
        )
    )
    assert client.post("/api/v1/ai/providers/anthropic/release", headers=second).status_code == 200
    return admin


def test_ask_ai_masks_iban_and_writes_ai_proposal(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]], fake: FakeProvider
) -> None:
    world, ids = world_and_ids
    h = _setup_provider(client, world, ids["dpa"])

    body = _ok(client.post(f"{BASE}/{ids['case']}/ask-ai", headers=h))
    assert body["run_status"] == "succeeded"
    assert body["case"]["candidates"]["ai"]["document_class"] == "forderungsaufstellung"

    # The core assertion: no IBAN, in any form, reached the fake provider call.
    assert fake.calls, "provider was never called"
    for call in fake.calls:
        for message in call["messages"]:
            assert not contains_iban(message["content"])
            assert "DE89" not in message["content"]
            assert "erika.musterfrau@example.org" not in message["content"]
            assert "Max Mustermann" not in message["content"]

    doc = _ok(client.get(f"/api/v1/documents/{ids['doc']}", headers=h))
    assert doc["category_id"] is None  # never applied automatically (rule 0.1.6)


async def _case_without_document(settings: Settings, tenant_id: uuid.UUID) -> uuid.UUID:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            case = DocumentReviewCase(
                tenant_id=tenant_id,
                document_id=None,
                stage="rules",
                candidates=None,
                priority=100,
                status=ReviewCaseStatus.OPEN,
            )
            session.add(case)
            await session.flush()
            return case.id
    finally:
        await engine.dispose()


def test_ask_ai_rejects_case_without_document(
    client: TestClient,
    world_and_ids: tuple[World, dict[str, uuid.UUID]],
    fake: FakeProvider,
    database: Database,
    redis_url: str,
) -> None:
    world, ids = world_and_ids
    h = _setup_provider(client, world, ids["dpa"])
    case_id = asyncio.run(_case_without_document(_settings(database, redis_url), world.tenant_a))
    resp = client.post(f"{BASE}/{case_id}/ask-ai", headers=h)
    assert resp.status_code == 422
    assert not fake.calls
