"""M35 Stufe 5 / M35-01: `GET /objektakte/reconciliation` against a recorded objektakte
(`httpx.MockTransport`), and the local model proposal endpoint behind the tenant flag with an
injected predictor. Permissions (`objektakte:read` / `objektakte:update`), never an applied
category, tenant separation."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
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
from mhvp.objektakte.local_model import ScoredLabel
from mhvp.objektakte.models import DocumentReviewCase, ReviewCaseStatus
from mhvp.platform import services
from mhvp.platform.models import TenantSettings
from mhvp.properties.models import ManagementType, Property
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
RECON = "/api/v1/objektakte/reconciliation"
LOCAL = "/api/v1/objektakte/local-model"
API_URL = "https://uebernahme.example.test/api/crm/v1/"
TOKEN = "recon-token-" + RUN
SLUG = f"recon-{RUN}"
SHA_SAME = "a" * 64
SHA_CRM = "b" * 64
SHA_REMOTE = "c" * 64


def _configured(database: Database, redis_url: str, **overrides: object) -> Any:
    values: dict[str, object] = {
        "objektakte_api_url": API_URL,
        "objektakte_api_token": SecretStr(TOKEN),
        "objektakte_tenant": SLUG,
    }
    values.update(overrides)
    return base_settings(database, redis_url, **values)


def _remote_doc(doc_id: int, sha: str | None) -> dict[str, Any]:
    return {"id": doc_id, "title": f"Doc {doc_id}", "sha256": sha, "drive_file_id": f"d{doc_id}"}


class FakeObjektakte:
    def __init__(self) -> None:
        self.docs: dict[str, list[dict[str, Any]]] = {
            "291": [_remote_doc(1, SHA_SAME), _remote_doc(2, SHA_REMOTE), _remote_doc(4, None)],
            "77": [_remote_doc(5, SHA_SAME)],
        }
        self.calls: list[str] = []
        self.fail: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        path = request.url.path.removeprefix("/api/crm/v1/")
        self.calls.append(path)
        if self.fail is not None:
            return httpx.Response(self.fail, json={"detail": "kaputt"})
        if path == "objects/":
            rows = [{"number": n, "name": f"Objekt {n}"} for n in self.docs]
            return httpx.Response(
                200, json={"count": len(rows), "page": 1, "page_size": 100, "results": rows}
            )
        for number, docs in self.docs.items():
            if path == f"objects/{number}/documents/":
                return httpx.Response(
                    200, json={"count": len(docs), "page": 1, "page_size": 100, "results": docs}
                )
        return httpx.Response(404, json={"detail": "Nicht gefunden."})


async def _doc(session: Any, tenant_id: uuid.UUID, source_id: str, sha: str, **kw: Any) -> Document:
    values: dict[str, Any] = {
        "tenant_id": tenant_id,
        "title": f"Doc {source_id}",
        "filename": f"doc-{source_id}.pdf",
        "mime_type": "application/pdf",
        "size": 10,
        "sha256": sha,
        "storage": StorageKind.GOOGLE_DRIVE,
        "storage_ref": f"drive-{source_id}",
        "text_status": TextStatus.EXTRACTED,
        "source": DocumentSource.IMPORT,
        "visibility": ["tenant"],
        "source_system": "objektakte",
        "source_id": source_id,
    }
    values.update(kw)
    doc = Document(**values)
    session.add(doc)
    await session.flush()
    return doc


async def _world(settings: Any) -> tuple[World, dict[str, uuid.UUID]]:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    ids: dict[str, uuid.UUID] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG, name=f"Recon {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"reconb-{RUN}", name=f"Recon B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("reconadmin", a, "tenant_admin"),
            ("reconreader", a, "read_only"),
            ("reconcaretaker", a, "caretaker"),
            ("reconother", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        async with tenant_transaction(factory, a) as session:
            prop = Property(
                tenant_id=a, number="291", name="Haus", management_type=ManagementType.HOA
            )
            session.add(prop)
            await session.flush()
            ids["property"] = prop.id
            cat = DocumentCategory(tenant_id=a, code="02", name="Stammakte")
            session.add(cat)
            await session.flush()
            ids["category"] = cat.id
            for source_id, sha, extra in (
                ("1", SHA_SAME, {}),
                ("2", SHA_CRM, {}),
                ("3", "d" * 64, {"source_meta": {"sha256_placeholder": True}}),
            ):
                doc = await _doc(session, a, source_id, sha, **extra)
                session.add(
                    DocumentLink(
                        tenant_id=a,
                        document_id=doc.id,
                        entity_type="property",
                        entity_id=prop.id,
                        role=LinkRole.ORIGINAL,
                    )
                )
                ids[f"doc{source_id}"] = doc.id
            unlinked = await _doc(
                session, a, "8", "e" * 64, ocr_text="Teilungserklärung des Hauses"
            )
            ids["unlinked"] = unlinked.id
            case = DocumentReviewCase(
                tenant_id=a,
                document_id=unlinked.id,
                stage="rules",
                candidates={},
                priority=50,
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
    return asyncio.run(_world(_configured(database, redis_url)))


@pytest.fixture
def fake() -> FakeObjektakte:
    return FakeObjektakte()


class FakePredictor:
    version = "test-2026"

    def predict(self, text: str) -> list[ScoredLabel]:
        assert "__mgmt_" not in text or text.startswith("__mgmt_")
        return [ScoredLabel("02", 0.91), ScoredLabel("05", 0.06), ScoredLabel("01", 0.03)]


@pytest.fixture
def make_client(
    database: Database, redis_url: str, fake: FakeObjektakte
) -> Iterator[Callable[..., TestClient]]:
    opened: list[TestClient] = []

    def _make(**overrides: object) -> TestClient:
        app = create_app(_configured(database, redis_url, **overrides))
        app.state.objektakte_transport = httpx.MockTransport(fake.handler)
        app.state.objektakte_local_predictor = FakePredictor()
        client = TestClient(app)
        client.__enter__()
        opened.append(client)
        return client

    yield _make
    for client in opened:
        client.__exit__(None, None, None)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_reconciliation_report_per_object(
    make_client: Callable[..., TestClient],
    world_and_ids: tuple[World, dict[str, uuid.UUID]],
    fake: FakeObjektakte,
) -> None:
    world, _ = world_and_ids
    client = make_client()
    h = bearer(login(client, world, "reconreader"))
    report = _ok(client.get(RECON, headers=h))
    assert report["ok"] is False
    objects = {o["object_number"]: o for o in report["objects"]}
    obj = objects["291"]
    assert obj["objektakte_count"] == 3
    assert obj["crm_count"] == 3
    assert obj["missing_in_crm"] == ["4"]
    assert obj["missing_in_objektakte"] == ["3"]
    assert obj["hash_mismatches"] == [{"source_id": "2", "crm": SHA_CRM, "objektakte": SHA_REMOTE}]
    assert obj["placeholders"] == 1
    assert objects["077"]["missing_in_crm"] == ["5"]  # objektakte "77" normalised to "077"
    assert objects["ohne_objekt"]["missing_in_objektakte"] == ["8"]
    assert report["totals"]["objects_with_differences"] == 3
    assert "objects/" in fake.calls
    assert "objects/291/documents/" in fake.calls

    single = _ok(client.get(RECON, params={"number": "291"}, headers=h))
    assert single["scope"] == {"number": "291"}
    assert [o["object_number"] for o in single["objects"]] == ["291"]

    fake.fail = 503
    assert client.get(RECON, headers=h).status_code == 502

    caretaker = bearer(login(client, world, "reconcaretaker"))
    assert client.get(RECON, headers=caretaker).status_code == 403
    assert client.get(RECON).status_code == 401


def test_reconciliation_other_tenant_and_switched_off(
    make_client: Callable[..., TestClient], world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, _ = world_and_ids
    client = make_client()
    other = client.get(RECON, headers=bearer(login(client, world, "reconother")))
    assert other.status_code == 502
    assert other.json()["code"] == "MHVP-OAK-0001"
    off = make_client(objektakte_api_url=None, objektakte_api_token=None)
    refused = off.get(RECON, headers=bearer(login(off, world, "reconadmin")))
    assert refused.status_code == 502
    assert refused.json()["code"] == "MHVP-OAK-0001"


async def _set_flag(settings: Any, tenant_id: uuid.UUID, value: dict[str, Any]) -> None:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            row = await session.scalar(
                select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
            )
            assert row is not None
            row.objektakte_classification = {**(row.objektakte_classification or {}), **value}
    finally:
        await engine.dispose()


async def _read(settings: Any, tenant_id: uuid.UUID, ids: dict[str, uuid.UUID]) -> tuple[Any, Any]:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            doc = await session.get(Document, ids["unlinked"])
            case = await session.get(DocumentReviewCase, ids["case"])
            assert doc is not None
            assert case is not None
            return (doc.category_id, dict(doc.source_meta or {})), dict(case.candidates or {})
    finally:
        await engine.dispose()


def test_local_model_flag_off_by_default_then_proposal_only(
    database: Database,
    redis_url: str,
    make_client: Callable[..., TestClient],
    world_and_ids: tuple[World, dict[str, uuid.UUID]],
) -> None:
    world, ids = world_and_ids
    settings = _configured(database, redis_url)
    client = make_client()
    admin = bearer(login(client, world, "reconadmin"))
    reader = bearer(login(client, world, "reconreader"))

    status = _ok(client.get(LOCAL, headers=reader))
    assert status["enabled"] is False
    assert status["version"] is None
    assert status["artifact"]["models_dir"] == settings.objektakte_models_dir

    off = client.post(f"{LOCAL}/cases/{ids['case']}/propose", headers=admin)
    assert off.status_code == 409  # flag off: nothing is predicted

    asyncio.run(
        _set_flag(settings, world.tenant_a, {"local_model": {"enabled": True, "version": "v1"}})
    )
    assert client.post(f"{LOCAL}/cases/{ids['case']}/propose", headers=reader).status_code == 403

    body = _ok(client.post(f"{LOCAL}/cases/{ids['case']}/propose", headers=admin))
    proposal = body["proposal"]
    assert proposal["stage"] == "local_model"
    assert proposal["status"] == "proposal"
    assert proposal["document_class"] == "02"
    assert proposal["category"] == str(ids["category"])  # label mapped by category code
    assert proposal["confidence"] == 0.91
    assert proposal["model_version"] == "test-2026"
    assert proposal["candidates"][1] == {"label": "05", "category_id": None, "confidence": 0.06}

    (category_id, meta), candidates = asyncio.run(_read(settings, world.tenant_a, ids))
    assert category_id is None  # never applied automatically (rule 0.1.6)
    assert meta["classification"]["stage"] == "local_model"
    assert candidates["local_model"]["document_class"] == "02"

    # tenant separation: tenant B (flag off) is refused before any lookup; with its flag on the
    # case of tenant A is invisible to it (RLS, 404). Neither path writes anything.
    other = bearer(login(client, world, "reconother"))
    assert client.post(f"{LOCAL}/cases/{ids['case']}/propose", headers=other).status_code == 409
    asyncio.run(
        _set_flag(settings, world.tenant_b, {"local_model": {"enabled": True, "version": "v1"}})
    )
    assert client.post(f"{LOCAL}/cases/{ids['case']}/propose", headers=other).status_code == 404
    asyncio.run(_set_flag(settings, world.tenant_a, {"local_model": {"enabled": False}}))
