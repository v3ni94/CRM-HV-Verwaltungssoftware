"""AA05 (GA04-07, 10, 11, 12): work order workflow reference, template context and
placeholders, provenance of generated documents, similarity ranking of learning examples."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import select

from mhvp.ai import embeddings
from mhvp.ai.models import (
    EMBEDDING_DIMENSIONS,
    AiEmbedding,
    AiExample,
    AiTask,
    EmbeddingSourceKind,
)
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents import letters
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m6_documents import BUCKET, COMPANY, _contact, _ok

pytestmark = pytest.mark.integration


def test_placeholders_of_lists_dotted_paths_and_skips_local_names() -> None:
    found = letters.placeholders_of(
        "Betreff {{ felder.thema }}",
        "{% set x = 1 %}{% for p in felder.posten %}{{ p }}{% endfor %}"
        "{{ empfaenger.anrede }} {{ datum }} {{ x }}",
    )
    assert found == ["datum", "empfaenger.anrede", "felder.posten", "felder.thema"]
    with pytest.raises(letters.PlaceholderError):
        letters.placeholders_of("{{ a")


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aa5-{RUN}", name=f"AA05 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aa5f-{RUN}", name=f"AA05F {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("aa5admin", a, "tenant_admin"),
            ("aa5care", a, "caretaker"),
            ("aa5other", b, "tenant_admin"),
        ]:
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


def test_template_context_and_generated_document(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "aa5admin"))
    _ok(
        client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h),
        200,
    )
    code = f"ctx_{RUN}"
    body = {
        "code": code,
        "name": "Kontextbrief",
        "subject": "Info {{ felder.thema }}",
        "body": "{{ empfaenger.anrede }},\n\n{{ felder.text }}",
        "context_types": ["property", "contact"],
    }
    # Validation, permission
    assert (
        client.post(
            "/api/v1/document-templates", json={**body, "context_types": ["bogus"]}, headers=h
        ).status_code
        == 422
    )
    care = bearer(login(client, world, "aa5care"))
    assert client.post("/api/v1/document-templates", json=body, headers=care).status_code == 403
    master = _ok(
        client.post(
            "/api/v1/document-templates",
            json={**body, "code": f"master_{RUN}", "context_types": []},
            headers=h,
        )
    )
    tpl = _ok(
        client.post(
            "/api/v1/document-templates",
            json={**body, "master_template_id": master["id"]},
            headers=h,
        )
    )
    assert tpl["context_types"] == ["contact", "property"]
    assert tpl["master_template_id"] == master["id"]
    assert tpl["placeholders_used"] == ["empfaenger.anrede", "felder.text", "felder.thema"]
    unknown_master = client.post(
        "/api/v1/document-templates",
        json={**body, "code": f"m2_{RUN}", "master_template_id": str(uuid.uuid4())},
        headers=h,
    )
    assert unknown_master.status_code == 404

    # Filter by context: restricted template shows for property, not for contract
    by_property = _ok(
        client.get("/api/v1/document-templates", params={"context_type": "property"}, headers=h),
        200,
    )
    by_contract = _ok(
        client.get("/api/v1/document-templates", params={"context_type": "contract"}, headers=h),
        200,
    )
    assert code in {t["code"] for t in by_property}
    assert code not in {t["code"] for t in by_contract}
    assert f"master_{RUN}" in {t["code"] for t in by_contract}  # unrestricted
    assert (
        client.get(
            "/api/v1/document-templates", params={"context_type": "x"}, headers=h
        ).status_code
        == 422
    )

    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "591",
                "name": "AA05",
                "management_type": "rental",
                "street": "Rheinpromenade",
                "house_number": "13",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    anna = _contact(client, h, "Gen", salutation="Frau")
    letter = {
        "template_id": tpl["id"],
        "contact_id": anna["id"],
        "letter_date": "2026-10-01",
        "fields": {"thema": "Termin", "text": "Der Termin ist am 02.10.2026."},
    }
    created = _ok(
        client.post("/api/v1/letters", json={**letter, "property_id": prop["id"]}, headers=h)
    )
    rows = _ok(
        client.get("/api/v1/generated-documents", params={"document_id": created["id"]}, headers=h),
        200,
    )
    assert len(rows) == 1
    row = rows[0]
    assert (row["template_code"], row["template_version"]) == (code, 1)
    assert (row["context_type"], row["context_id"]) == ("property", prop["id"])
    assert row["recipient_contact_id"] == anna["id"]
    assert row["dispatch_id"] is None

    # Without entity the recipient is the context
    plain = _ok(client.post("/api/v1/letters", json=letter, headers=h))
    plain_row = _ok(
        client.get("/api/v1/generated-documents", params={"document_id": plain["id"]}, headers=h),
        200,
    )[0]
    assert (plain_row["context_type"], plain_row["context_id"]) == ("contact", anna["id"])

    # Template restricted to property and contact refuses a contract context
    refused = client.post(
        "/api/v1/letters", json={**letter, "contract_id": str(uuid.uuid4())}, headers=h
    )
    assert refused.status_code == 422

    # Tenant separation: other tenant sees nothing
    other = bearer(login(client, world, "aa5other"))
    assert _ok(client.get("/api/v1/generated-documents", headers=other), 200) == []


def test_work_order_carries_approval_workflow_id(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "aa5admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "592",
                "name": "AA05 Auftrag",
                "management_type": "rental",
                "street": "Rheinpromenade",
                "house_number": "14",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        )
    )
    provider = _contact(client, h, "Handwerk")
    workflow = str(uuid.uuid4())
    order = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "property_id": prop["id"],
                "provider_contact_id": provider["id"],
                "description": "Dachrinne reinigen",
                "approval_workflow_id": workflow,
            },
            headers=h,
        )
    )
    assert order["approval_workflow_id"] == workflow
    bad = client.post(
        "/api/v1/work-orders",
        json={
            "property_id": prop["id"],
            "provider_contact_id": provider["id"],
            "description": "Dachrinne reinigen",
            "approval_workflow_id": "nope",
        },
        headers=h,
    )
    assert bad.status_code == 422


def _vec(*head: float) -> list[float]:
    values = list(head) + [0.0] * (EMBEDDING_DIMENSIONS - len(head))
    return values


def test_learning_examples_are_embedded_and_ranked(
    world: World, database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(database, redis_url)

    async def run() -> None:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                near = AiExample(
                    tenant_id=world.tenant_a,
                    task=AiTask.TICKET_RESOLUTION,
                    features={"text": "Heizung defekt"},
                    result={"antwort": "Monteur beauftragen"},
                )
                far = AiExample(
                    tenant_id=world.tenant_a,
                    task=AiTask.TICKET_RESOLUTION,
                    features={"text": "Schlüssel verloren"},
                    result={"antwort": "Schloss tauschen"},
                )
                session.add_all([near, far])
                await session.flush()
                # Pending before the index job ran; no embeddings: recency order stays.
                state = await embeddings.status(session)
                assert state["examples_total"] == 2
                assert state["examples_pending"] == 2
                assert (
                    await embeddings.rank_examples(
                        session,
                        AiTask.TICKET_RESOLUTION,
                        "Heizung kalt",
                        tenant_id=world.tenant_a,
                        actor=None,
                        limit=5,
                    )
                    is None
                )
                text = embeddings.masked_source_text(EmbeddingSourceKind.AI_EXAMPLE, near)
                assert "Heizung defekt" in text
                for shot, vector in ((near, _vec(1.0, 0.0)), (far, _vec(0.0, 1.0))):
                    session.add(
                        AiEmbedding(
                            tenant_id=world.tenant_a,
                            source_kind=EmbeddingSourceKind.AI_EXAMPLE,
                            source_id=shot.id,
                            chunk_index=0,
                            chunk_count=1,
                            content_hash="x",
                            model="test",
                            embedding=vector,
                        )
                    )
                await session.flush()

                async def fake_query(*_a: Any, **_k: Any) -> list[float]:
                    return _vec(0.9, 0.1)

                monkeypatch.setattr(embeddings, "embed_query", fake_query)
                ranked = await embeddings.rank_examples(
                    session,
                    AiTask.TICKET_RESOLUTION,
                    "Heizung kalt",
                    tenant_id=world.tenant_a,
                    actor=None,
                    limit=5,
                )
                assert ranked is not None
                assert ranked[0].id == near.id
                assert far.id not in {r.id for r in ranked}  # beyond the distance cut-off
                kinds = (await session.scalars(select(AiEmbedding.source_kind).distinct())).all()
                assert EmbeddingSourceKind.AI_EXAMPLE in kinds
        finally:
            await engine.dispose()

    asyncio.run(run())
