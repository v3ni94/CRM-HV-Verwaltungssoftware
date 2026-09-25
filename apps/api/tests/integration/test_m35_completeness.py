"""M35 Stufe 3 part 4 (completeness check) acceptance: required-document settings CRUD,
GET .../properties/{id}/completeness (missing vs. satisfied per management type), and the
Nachforderungsschreiben draft text (marked Entwurf, never sent)."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

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
from mhvp.platform import services
from mhvp.properties.models import ManagementType, Property
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(database, redis_url)


async def _world(settings: Any) -> tuple[World, dict[str, uuid.UUID]]:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    ids: dict[str, uuid.UUID] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=f"m35comp-{RUN}", name=f"Comp {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("compadmin", "compreader"):
            role = "tenant_admin" if name == "compadmin" else "read_only"
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        async with tenant_transaction(factory, a) as session:
            cat_plan = DocumentCategory(tenant_id=a, code="wp", name="Wirtschaftsplan")
            cat_protokoll = DocumentCategory(tenant_id=a, code="prot", name="Protokoll")
            session.add_all([cat_plan, cat_protokoll])
            await session.flush()
            ids["cat_plan"] = cat_plan.id
            ids["cat_protokoll"] = cat_protokoll.id

            prop = Property(
                tenant_id=a,
                number="701",
                name="Haus Musterstraße",
                management_type=ManagementType.HOA,
            )
            session.add(prop)
            await session.flush()
            ids["property"] = prop.id

            doc = Document(
                tenant_id=a,
                title="Wirtschaftsplan 2027",
                filename="wp2027.pdf",
                mime_type="application/pdf",
                size=10,
                sha256="e" * 64,
                storage=StorageKind.MINIO,
                storage_ref="ref-wp",
                category_id=cat_plan.id,
                text_status=TextStatus.EXTRACTED,
                source=DocumentSource.UPLOAD,
                visibility=[],
            )
            session.add(doc)
            await session.flush()
            session.add(
                DocumentLink(
                    tenant_id=a,
                    document_id=doc.id,
                    entity_type="property",
                    entity_id=prop.id,
                    role=LinkRole.ORIGINAL,
                )
            )
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


def test_required_document_crud(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    admin = bearer(login(client, world, "compadmin"))
    reader = bearer(login(client, world, "compreader"))

    created = _ok(
        client.post(
            f"{BASE}/required-documents",
            json={
                "management_type": "hoa",
                "document_category_id": str(ids["cat_plan"]),
                "mandatory": True,
            },
            headers=admin,
        ),
        201,
    )
    assert created["mandatory"] is True

    forbidden = client.post(
        f"{BASE}/required-documents",
        json={
            "management_type": "hoa",
            "document_category_id": str(ids["cat_protokoll"]),
            "mandatory": True,
        },
        headers=reader,
    )
    assert forbidden.status_code == 403

    listed = _ok(
        client.get(f"{BASE}/required-documents", params={"management_type": "hoa"}, headers=admin)
    )
    assert any(r["id"] == created["id"] for r in listed)

    deleted = client.delete(f"{BASE}/required-documents/{created['id']}", headers=admin)
    assert deleted.status_code == 204
    after_delete = _ok(
        client.get(f"{BASE}/required-documents", params={"management_type": "hoa"}, headers=admin)
    )
    assert not any(r["id"] == created["id"] for r in after_delete)


def test_completeness_reports_missing_and_satisfied(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    admin = bearer(login(client, world, "compadmin"))
    _ok(
        client.post(
            f"{BASE}/required-documents",
            json={
                "management_type": "hoa",
                "document_category_id": str(ids["cat_plan"]),
                "mandatory": True,
            },
            headers=admin,
        ),
        201,
    )
    _ok(
        client.post(
            f"{BASE}/required-documents",
            json={
                "management_type": "hoa",
                "document_category_id": str(ids["cat_protokoll"]),
                "mandatory": True,
            },
            headers=admin,
        ),
        201,
    )

    result = _ok(client.get(f"{BASE}/properties/{ids['property']}/completeness", headers=admin))
    assert result["management_type"] == "hoa"
    satisfied_codes = {m["code"] for m in result["satisfied"]}
    missing_codes = {m["code"] for m in result["missing"]}
    assert "wp" in satisfied_codes
    assert "prot" in missing_codes


def test_nachforderungsschreiben_draft_lists_missing_and_is_marked_entwurf(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    admin = bearer(login(client, world, "compadmin"))
    body = _ok(
        client.post(
            f"{BASE}/properties/{ids['property']}/completeness/nachforderungsschreiben",
            headers=admin,
        )
    )
    assert body["draft"] is True
    assert "ENTWURF" in body["text"]
    assert "Protokoll" in body["text"]
    assert "Wirtschaftsplan" not in body["text"]  # already satisfied, not requested again
