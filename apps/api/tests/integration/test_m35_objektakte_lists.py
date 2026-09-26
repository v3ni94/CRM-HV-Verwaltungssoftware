"""M35 Stufe 4, part Listengenerierung (docs/plans/M35-objektakte-uebernahme.md section 4):
Anforderungsliste (missing mandatory documents, per property and across properties) and
Dokumentenübersicht je Kategorie, each as JSON and CSV. Covers the happy path, authorization
(a role without `objektakte:read` gets 403) and tenant separation (a property of another
tenant is not found under RLS, the overview never lists it)."""

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
from mhvp.objektakte.models import ObjektakteRequiredDocument
from mhvp.platform import services
from mhvp.properties.models import ManagementType, Property
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(database, redis_url)


def _document(
    tenant_id: uuid.UUID, title: str, sha: str, category_id: uuid.UUID | None
) -> Document:
    return Document(
        tenant_id=tenant_id,
        title=title,
        filename=f"{title.lower().replace(' ', '-')}.pdf",
        mime_type="application/pdf",
        size=10,
        sha256=sha * 64,
        storage=StorageKind.MINIO,
        storage_ref=f"ref-{sha}",
        category_id=category_id,
        text_status=TextStatus.EXTRACTED,
        source=DocumentSource.UPLOAD,
        visibility=[],
    )


async def _world(settings: Any) -> tuple[World, dict[str, uuid.UUID]]:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    ids: dict[str, uuid.UUID] = {}
    try:
        a, _ = await services.provision_tenant(factory, slug=f"m35list-{RUN}", name=f"List {RUN}")
        b, _ = await services.provision_tenant(
            factory, slug=f"m35listb-{RUN}", name=f"List B {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("listadmin", a, "tenant_admin"),
            ("listcaretaker", a, "caretaker"),
            ("listother", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        async with tenant_transaction(factory, a) as session:
            cat_plan = DocumentCategory(
                tenant_id=a, code="wp", name="Wirtschaftsplan", sort_order=2
            )
            cat_prot = DocumentCategory(tenant_id=a, code="prot", name="Protokoll", sort_order=1)
            session.add_all([cat_plan, cat_prot])
            await session.flush()
            ids["cat_plan"] = cat_plan.id
            ids["cat_prot"] = cat_prot.id
            session.add_all(
                [
                    ObjektakteRequiredDocument(
                        tenant_id=a,
                        management_type=ManagementType.HOA,
                        document_category_id=cat_plan.id,
                        mandatory=True,
                    ),
                    ObjektakteRequiredDocument(
                        tenant_id=a,
                        management_type=ManagementType.HOA,
                        document_category_id=cat_prot.id,
                        mandatory=True,
                    ),
                ]
            )

            prop = Property(
                tenant_id=a, number="801", name="Haus Listenweg", management_type=ManagementType.HOA
            )
            complete_prop = Property(
                tenant_id=a,
                number="802",
                name="Haus Vollständig",
                management_type=ManagementType.HOA,
            )
            session.add_all([prop, complete_prop])
            await session.flush()
            ids["property"] = prop.id
            ids["complete_property"] = complete_prop.id

            doc_plan = _document(a, "Wirtschaftsplan 2027", "1", cat_plan.id)
            doc_none = _document(a, "Unklares Schreiben", "2", None)
            doc_c_plan = _document(a, "Wirtschaftsplan 802", "3", cat_plan.id)
            doc_c_prot = _document(a, "Protokoll 802", "4", cat_prot.id)
            session.add_all([doc_plan, doc_none, doc_c_plan, doc_c_prot])
            await session.flush()
            ids["doc_plan"] = doc_plan.id
            ids["doc_none"] = doc_none.id
            for document, target in (
                (doc_plan, prop),
                (doc_none, prop),
                (doc_c_plan, complete_prop),
                (doc_c_prot, complete_prop),
            ):
                session.add(
                    DocumentLink(
                        tenant_id=a,
                        document_id=document.id,
                        entity_type="property",
                        entity_id=target.id,
                        role=LinkRole.ORIGINAL,
                    )
                )
            # a second link (another role) to the same document must not duplicate the row
            session.add(
                DocumentLink(
                    tenant_id=a,
                    document_id=doc_plan.id,
                    entity_type="property",
                    entity_id=prop.id,
                    role=LinkRole.ATTACHMENT,
                )
            )
        async with tenant_transaction(factory, b) as session:
            other = Property(
                tenant_id=b, number="901", name="Fremdes Haus", management_type=ManagementType.HOA
            )
            session.add(other)
            await session.flush()
            ids["other_property"] = other.id
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


def test_missing_documents_list_and_csv(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    h = bearer(login(client, world, "listadmin"))

    single = _ok(
        client.get(f"{BASE}/properties/{ids['property']}/lists/missing-documents", headers=h)
    )
    assert single["property_number"] == "801"
    assert single["complete"] is False
    assert [m["code"] for m in single["missing"]] == ["prot"]
    assert single["satisfied_count"] == 1

    overview = _ok(client.get(f"{BASE}/lists/missing-documents", headers=h))
    by_number = {e["property_number"]: e for e in overview["items"]}
    assert by_number["801"]["complete"] is False
    assert by_number["802"]["complete"] is True
    assert "901" not in by_number

    incomplete_only = _ok(
        client.get(f"{BASE}/lists/missing-documents", params={"only_incomplete": "true"}, headers=h)
    )
    assert [e["property_number"] for e in incomplete_only["items"]] == ["801"]

    csv_resp = client.get(f"{BASE}/lists/missing-documents/export", headers=h)
    assert csv_resp.status_code == 200, csv_resp.text
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert 'filename="anforderungsliste.csv"' in csv_resp.headers["content-disposition"]
    lines = csv_resp.text.lstrip("﻿").splitlines()
    assert lines[0] == "Objektnummer;Objekt;Verwaltungsart;Kategorie;Fehlende Unterlage"
    assert "801;Haus Listenweg;hoa;prot;Protokoll" in lines
    assert not any(line.startswith("802;") for line in lines)

    single_csv = client.get(
        f"{BASE}/properties/{ids['property']}/lists/missing-documents/export", headers=h
    )
    assert single_csv.status_code == 200
    assert 'filename="anforderungsliste-801.csv"' in single_csv.headers["content-disposition"]


def test_documents_by_category_and_csv(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    h = bearer(login(client, world, "listadmin"))

    body = _ok(client.get(f"{BASE}/properties/{ids['property']}/lists/documents", headers=h))
    assert body["total"] == 2  # the doubly linked document counts once
    assert [g["code"] for g in body["groups"]] == ["wp", ""]
    assert body["groups"][0]["documents"][0]["document_id"] == str(ids["doc_plan"])
    assert body["groups"][1]["name"] == "Ohne Kategorie"
    assert body["groups"][1]["documents"][0]["duplicate"] is False

    csv_resp = client.get(f"{BASE}/properties/{ids['property']}/lists/documents/export", headers=h)
    assert csv_resp.status_code == 200, csv_resp.text
    assert 'filename="dokumentenuebersicht-801.csv"' in csv_resp.headers["content-disposition"]
    lines = csv_resp.text.lstrip("﻿").splitlines()
    assert lines[0].startswith("Objektnummer;Objekt;Kategorie;Kategoriename;Titel;Dateiname")
    assert len(lines) == 3
    assert lines[1].startswith("801;Haus Listenweg;wp;Wirtschaftsplan;Wirtschaftsplan 2027;")
    assert lines[2].startswith("801;Haus Listenweg;;Ohne Kategorie;Unklares Schreiben;")


def test_lists_require_objektakte_read(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    anonymous = client.get(f"{BASE}/lists/missing-documents")
    assert anonymous.status_code == 401
    h = bearer(login(client, world, "listcaretaker"))
    for path in (
        f"{BASE}/lists/missing-documents",
        f"{BASE}/lists/missing-documents/export",
        f"{BASE}/properties/{ids['property']}/lists/missing-documents",
        f"{BASE}/properties/{ids['property']}/lists/documents/export",
    ):
        resp = client.get(path, headers=h)
        assert resp.status_code == 403, (path, resp.text)


def test_lists_are_tenant_separated(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    world, ids = world_and_ids
    other = bearer(login(client, world, "listother", tenant_id=world.tenant_b))
    for path in (
        f"{BASE}/properties/{ids['property']}/lists/missing-documents",
        f"{BASE}/properties/{ids['property']}/lists/documents",
        f"{BASE}/properties/{ids['property']}/lists/documents/export",
    ):
        resp = client.get(path, headers=other)
        assert resp.status_code == 404, (path, resp.text)
    overview = _ok(client.get(f"{BASE}/lists/missing-documents", headers=other))
    assert [e["property_number"] for e in overview["items"]] == ["901"]
    own = _ok(
        client.get(f"{BASE}/properties/{ids['other_property']}/lists/documents", headers=other)
    )
    assert own["total"] == 0

    admin = bearer(login(client, world, "listadmin"))
    foreign = client.get(
        f"{BASE}/properties/{ids['other_property']}/lists/missing-documents", headers=admin
    )
    assert foreign.status_code == 404
