"""M35 Stufe 4, part Listengenerierung (docs/plans/M35-objektakte-uebernahme.md section 4):
Anforderungsliste (missing mandatory documents, per property and across properties) and
Dokumentenübersicht je Kategorie, each as JSON and CSV; Stufe 4 rest: Eigentümerliste and
Mieterliste from current contracts (contact fields only, no bank data) and filing a generated
list as a document of the property. Covers the happy path, authorization (a role without
`objektakte:read` gets 403) and tenant separation (a property of another tenant is not found
under RLS, the overview never lists it)."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

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
from tests.integration.test_m5_contracts import _unit

pytestmark = pytest.mark.integration
BASE = "/api/v1/objektakte"
BUCKET = "mhvp-lists"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
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


def _contact(client: TestClient, h: dict[str, str], last_name: str, **extra: Any) -> str:
    body: dict[str, Any] = {"kind": "person", "first_name": "Test", "last_name": last_name}
    body.update(extra)
    return str(_ok(client.post("/api/v1/contacts", json=body, headers=h), 201)["id"])


def _party_of(client: TestClient, h: dict[str, str], *contact_ids: str) -> str:
    members = [{"contact_id": c} for c in contact_ids]
    return str(_ok(client.post("/api/v1/parties", json={"members": members}, headers=h), 201)["id"])


def test_person_lists_and_store_as_document(
    client: TestClient, world_and_ids: tuple[World, dict[str, uuid.UUID]]
) -> None:
    """Eigentümerliste and Mieterliste: expected rows by hand. Unit 01: owner Eigner (address,
    e-mail, phone, ownership from 01.01.2020), tenant Bewohner (tenancy from 01.03.2024).
    Unit 02: owner party of two members (Eigner and Miteigner), no tenant. A tenancy that
    ended 29.02.2024 is not current on today's date and stays out. No IBAN anywhere in the
    output although the owner has a bank account."""
    world, ids = world_and_ids
    h = bearer(login(client, world, "listadmin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": "803",
                "name": "Haus Personen",
                "management_type": "hoa_with_sev",
                "street": "Listenweg",
                "house_number": "3",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    unit1 = _unit(client, h, prop["id"], "01")
    unit2 = _unit(client, h, prop["id"], "02")
    owner = _contact(
        client,
        h,
        f"Eigner{RUN}",
        addresses=[
            {
                "label": "postal",
                "street": "Hauptstraße",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            }
        ],
        phones=[{"label": "mobile", "number": "0171 1234567"}],
        emails=[{"email": f"eigner.{RUN}@example.org"}],
        bank_accounts=[{"iban": "DE02 1203 0000 0000 2020 51", "valid_from": "2020-01-01"}],
    )
    co_owner = _contact(client, h, f"Miteigner{RUN}")
    tenant = _contact(
        client, h, f"Bewohner{RUN}", emails=[{"email": f"bewohner.{RUN}@example.org"}]
    )
    former = _contact(client, h, f"Vormieter{RUN}")
    owner_party = _party_of(client, h, owner)
    pair_party = _party_of(client, h, owner, co_owner)
    ownership = {
        "kind": "ownership",
        "start_date": "2020-01-01",
        "title_transfer_date": "2020-01-01",
        "acquisition_kind": "first_acquisition",
    }
    _ok(
        client.post(
            "/api/v1/contracts",
            json={**ownership, "unit_id": unit1, "party_id": owner_party, "sev_enabled": True},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/contracts",
            json={**ownership, "unit_id": unit2, "party_id": pair_party},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit1,
                "party_id": _party_of(client, h, former),
                "start_date": "2022-01-01",
                "end_date": "2024-02-29",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit1,
                "party_id": _party_of(client, h, tenant),
                "start_date": "2024-03-01",
            },
            headers=h,
        ),
        201,
    )

    owners = _ok(client.get(f"{BASE}/properties/{prop['id']}/lists/owners", headers=h))
    assert owners["kind"] == "owners"
    assert owners["total"] == 3
    assert [(r["unit_number"], r["name"]) for r in owners["rows"]] == [
        ("01", f"Eigner{RUN}, Test"),
        ("02", f"Eigner{RUN}, Test"),
        ("02", f"Miteigner{RUN}, Test"),
    ]
    first = owners["rows"][0]
    assert first["street"] == "Hauptstraße 1"
    assert first["postal_code"] == "40789"
    assert first["city"] == "Monheim am Rhein"
    assert first["email"] == f"eigner.{RUN}@example.org"
    assert first["phone"] == "+491711234567"
    assert first["contract_start"] == "2020-01-01"
    assert first["contract_end"] is None
    assert owners["rows"][2]["email"] == ""
    assert "iban" not in str(owners).lower()
    assert "DE02" not in str(owners)

    tenants = _ok(client.get(f"{BASE}/properties/{prop['id']}/lists/tenants", headers=h))
    assert [(r["unit_number"], r["name"]) for r in tenants["rows"]] == [
        ("01", f"Bewohner{RUN}, Test")
    ]
    assert tenants["rows"][0]["contract_start"] == "2024-03-01"

    csv_resp = client.get(f"{BASE}/properties/{prop['id']}/lists/tenants/export", headers=h)
    assert csv_resp.status_code == 200, csv_resp.text
    assert 'filename="mieterliste-803.csv"' in csv_resp.headers["content-disposition"]
    lines = csv_resp.text.lstrip("\ufeff").splitlines()
    assert lines[0] == (
        "Objektnummer;Objekt;Einheit;Bezeichnung;Name;Straße;PLZ;Ort;E-Mail;Telefon;"
        "Vertragsnummer;Vertragsbeginn;Vertragsende"
    )
    assert len(lines) == 2
    assert lines[1].startswith(f"803;Haus Personen;01;WE 01;Bewohner{RUN}, Test;;;;bewohner.{RUN}@")
    assert lines[1].endswith(";01.03.2024;")
    owners_csv = client.get(f"{BASE}/properties/{prop['id']}/lists/owners/export", headers=h)
    assert 'filename="eigentuemerliste-803.csv"' in owners_csv.headers["content-disposition"]
    assert "DE02" not in owners_csv.text

    # store as document: new document of category "Liste", linked to the property, CSV content
    stored = _ok(client.post(f"{BASE}/properties/{prop['id']}/lists/owners/store", headers=h), 201)
    assert stored["mime_type"] == "text/csv"
    assert stored["source"] == "generated"
    assert stored["title"].startswith("Eigentümerliste 803 Haus Personen ")
    assert stored["filename"].startswith("eigentuemerliste-803-")
    assert stored["filename"].endswith(".csv")
    assert [(x["entity_type"], x["entity_id"], x["role"]) for x in stored["links"]] == [
        ("property", prop["id"], "generated")
    ]
    categories = _ok(client.get("/api/v1/document-categories", headers=h))
    liste = next(c for c in categories if c["code"] == "list")
    assert liste["name"] == "Liste"
    assert stored["category_id"] == liste["id"]
    content = client.get(f"/api/v1/documents/{stored['id']}/content", headers=h)
    assert content.status_code == 200
    body = content.content.decode("utf-8-sig")
    assert body.splitlines()[0].startswith("Objektnummer;Objekt;Einheit;")
    assert f"Eigner{RUN}, Test" in body
    assert "DE02" not in body
    # the stored list shows up in the Dokumentenübersicht of the property
    overview = _ok(client.get(f"{BASE}/properties/{prop['id']}/lists/documents", headers=h))
    assert [g["code"] for g in overview["groups"]] == ["list"]
    assert overview["groups"][0]["documents"][0]["document_id"] == stored["id"]
    # a second call stores a second snapshot, nothing is overwritten
    again = _ok(
        client.post(f"{BASE}/properties/{prop['id']}/lists/missing-documents/store", headers=h),
        201,
    )
    assert again["id"] != stored["id"]
    assert again["title"].startswith("Anforderungsliste 803 ")
    assert (
        client.post(f"{BASE}/properties/{prop['id']}/lists/unknown/store", headers=h).status_code
        == 422
    )

    # authorization and tenant separation
    caretaker = bearer(login(client, world, "listcaretaker"))
    for path in (
        f"{BASE}/properties/{prop['id']}/lists/owners",
        f"{BASE}/properties/{prop['id']}/lists/tenants/export",
    ):
        assert client.get(path, headers=caretaker).status_code == 403, path
    assert (
        client.post(
            f"{BASE}/properties/{prop['id']}/lists/owners/store", headers=caretaker
        ).status_code
        == 403
    )
    other = bearer(login(client, world, "listother", tenant_id=world.tenant_b))
    assert (
        client.get(f"{BASE}/properties/{prop['id']}/lists/owners", headers=other).status_code == 404
    )
    assert (
        client.post(f"{BASE}/properties/{prop['id']}/lists/owners/store", headers=other).status_code
        == 404
    )
    own = _ok(client.get(f"{BASE}/properties/{ids['other_property']}/lists/tenants", headers=other))
    assert own["total"] == 0
