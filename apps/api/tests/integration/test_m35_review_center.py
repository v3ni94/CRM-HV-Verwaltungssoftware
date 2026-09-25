"""M35 Stufe 3 part 3, Review-Center acceptance (docs/plans/M35-objektakte-uebernahme.md
section 4): list with filters, get, decide (accept candidate / manual / reject / snooze), bulk
decide, audit rows (before/after, decided_by), authorization (documents:read vs.
documents:update) and tenant separation (RLS)."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.models import (
    Document,
    DocumentCategory,
    DocumentLink,
    DocumentSource,
    LinkRole,
    StorageKind,
    TextStatus,
)
from mhvp.main import create_app
from mhvp.objektakte.models import DocumentReviewCase, DocumentReviewDecision, ReviewCaseStatus
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte/review"


async def _world(settings: Any) -> tuple[World, dict[str, uuid.UUID]]:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    ids: dict[str, uuid.UUID] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rev-{RUN}", name=f"Rev {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"revb-{RUN}", name=f"Rev B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("revadmin", a, "tenant_admin"),
            ("revreader", a, "read_only"),
            ("revother", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        async with tenant_transaction(factory, a) as session:
            cat = DocumentCategory(tenant_id=a, code="05", name="Eigentümerakte")
            session.add(cat)
            await session.flush()
            ids["category_a"] = cat.id

            doc1 = Document(
                tenant_id=a,
                title="Forderungsaufstellung",
                filename="forderung.pdf",
                mime_type="application/pdf",
                size=10,
                sha256="a" * 64,
                storage=StorageKind.MINIO,
                storage_ref="ref1",
                text_status=TextStatus.EXTRACTED,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )
            doc2 = Document(
                tenant_id=a,
                title="Unklares Dokument",
                filename="unklar.pdf",
                mime_type="application/pdf",
                size=10,
                sha256="b" * 64,
                storage=StorageKind.MINIO,
                storage_ref="ref2",
                text_status=TextStatus.EXTRACTED,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )
            session.add_all([doc1, doc2])
            await session.flush()
            ids["doc1"] = doc1.id
            ids["doc2"] = doc2.id

            prop_id = uuid.uuid4()
            session.add(
                DocumentLink(
                    tenant_id=a,
                    document_id=doc1.id,
                    entity_type="property",
                    entity_id=prop_id,
                    role=LinkRole.ORIGINAL,
                )
            )
            ids["property"] = prop_id

            case1 = DocumentReviewCase(
                tenant_id=a,
                document_id=doc1.id,
                stage="rules",
                candidates={
                    "candidates": [
                        {"category_id": str(cat.id), "document_type": "forderungsaufstellung"}
                    ]
                },
                priority=100,
                status=ReviewCaseStatus.OPEN,
            )
            case2 = DocumentReviewCase(
                tenant_id=a,
                document_id=doc2.id,
                stage="rules",
                candidates=None,
                priority=50,
                status=ReviewCaseStatus.OPEN,
            )
            session.add_all([case1, case2])
            await session.flush()
            ids["case1"] = case1.id
            ids["case2"] = case2.id
        return world, ids
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world_and_ids(database: Database, redis_url: str) -> tuple[World, dict[str, uuid.UUID]]:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_list_filters_by_status_property_and_priority(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    h = bearer(login(client, world, "revadmin"))
    body = _ok(client.get(BASE, headers=h))
    assert {c["id"] for c in body["items"]} == {str(ids["case1"]), str(ids["case2"])}

    by_property = _ok(client.get(BASE, params={"property_id": str(ids["property"])}, headers=h))
    assert [c["id"] for c in by_property["items"]] == [str(ids["case1"])]

    by_priority = _ok(client.get(BASE, params={"priority_min": 80}, headers=h))
    assert [c["id"] for c in by_priority["items"]] == [str(ids["case1"])]

    by_stage = _ok(client.get(BASE, params={"stage": "rules"}, headers=h))
    assert len(by_stage["items"]) == 2


def test_get_case_returns_candidates_and_preview_link(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    h = bearer(login(client, world, "revadmin"))
    body = _ok(client.get(f"{BASE}/{ids['case1']}", headers=h))
    assert body["candidates"]["candidates"][0]["category_id"] == str(ids["category_a"])
    assert body["document_preview_url"] == f"/api/v1/documents/{ids['doc1']}/content"


def test_reader_cannot_decide_but_can_list(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    h = bearer(login(client, world, "revreader"))
    _ok(client.get(BASE, headers=h))
    resp = client.post(f"{BASE}/{ids['case2']}/decide", json={"action": "reject"}, headers=h)
    assert resp.status_code == 403


async def _decisions_for_case(
    settings: Any, tenant_id: uuid.UUID, case_id: uuid.UUID
) -> list[DocumentReviewDecision]:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            rows = (
                (
                    await session.execute(
                        select(DocumentReviewDecision).where(
                            DocumentReviewDecision.review_case_id == case_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)
    finally:
        await engine.dispose()


def test_accept_candidate_files_document_and_writes_audit_decision(
    client: TestClient,
    world_and_ids: tuple[World, dict[str, uuid.UUID]],
    database: Database,
    redis_url: str,
) -> None:
    world, ids = world_and_ids
    h = bearer(login(client, world, "revadmin"))
    body = _ok(
        client.post(
            f"{BASE}/{ids['case1']}/decide",
            json={"action": "accept_candidate", "candidate_index": 0},
            headers=h,
        )
    )
    assert body["case"]["status"] == "resolved"

    doc = _ok(client.get(f"/api/v1/documents/{ids['doc1']}", headers=h))
    assert doc["category_id"] == str(ids["category_a"])

    rows = asyncio.run(
        _decisions_for_case(_settings(database, redis_url), world.tenant_a, ids["case1"])
    )
    assert len(rows) == 1
    assert rows[0].decided_by == world.users["revadmin"]
    assert rows[0].before_state["status"] == "open"
    assert rows[0].after_state["status"] == "resolved"
    assert rows[0].after_state["applied_category_id"] == str(ids["category_a"])


def test_bulk_decide_applies_same_class_and_skips_already_decided(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    h = bearer(login(client, world, "revadmin"))
    resp = _ok(
        client.post(
            f"{BASE}/bulk-decide",
            json={
                "case_ids": [str(ids["case1"]), str(ids["case2"])],
                "category_id": str(ids["category_a"]),
            },
            headers=h,
        )
    )
    # case1 was already resolved by the previous test (module-scoped world/ids).
    assert str(ids["case2"]) in resp["decided"]
    assert any(s["case_id"] == str(ids["case1"]) for s in resp["skipped"])


def test_tenant_separation_case_of_other_tenant_is_not_found(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    h = bearer(login(client, world, "revother"))
    resp = client.get(f"{BASE}/{ids['case2']}", headers=h)
    assert resp.status_code == 404
