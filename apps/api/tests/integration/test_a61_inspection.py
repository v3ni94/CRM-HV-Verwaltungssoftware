"""A61 inspection requests outside the portal (M25-04, section 14 phase boundary).

Expected values by hand: two released documents (visibility ``owner``) linked to the community
go into the package, a third document without owner release is rejected by name; the ZIP is
deterministic (same selection, same SHA-256 twice); the trail carries one row per status
change, note, package and retrieval; a read only role cannot record or release; a second
tenant sees nothing."""

import asyncio
import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
H = "/api/v1/hoa/inspection-requests"


async def _world(settings: Any, slug: str, admin: str, reader: str | None = None) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"{slug}-{RUN}", name=f"{slug} {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, roles in ((admin, ["tenant_admin"]), (reader, ["read_only"])):
            if name is None:
                continue
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=roles, actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url), "a61", "a61admin", "a61reader"))


@pytest.fixture(scope="module")
def other_world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url), "a61b", "a61other"))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _doc(
    c: TestClient, h: dict[str, str], name: str, data: bytes, entity: str, *, owner: bool
) -> str:
    links = json.dumps([{"entity_type": "legal_entity", "entity_id": entity, "role": "attachment"}])
    doc = _ok(
        c.post(
            "/api/v1/documents",
            files={"file": (name, data, "application/pdf")},
            data={"links": links},
            headers=h,
        ),
        201,
    )
    if owner:
        _ok(
            c.patch(
                f"/api/v1/documents/{doc['id']}",
                json={"visibility": ["tenant", "owner"]},
                headers=h,
            )
        )
    return str(doc["id"])


def test_inspection_request_flow_and_package(
    client: TestClient, world: World, other_world: World
) -> None:
    h = bearer(login(client, world, "a61admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "761", "name": "WEG Einsicht", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    _, applicant = _party(client, h, "Einsicht")
    contact_id = applicant["id"]

    # Record: scope needs a selection or a text; unknown scope kinds are rejected.
    base = {
        "legal_entity_id": hoa,
        "applicant_contact_id": contact_id,
        "requested_on": "2026-09-20",
    }
    assert client.post(H, json=base, headers=h).status_code == 422
    assert client.post(H, json={**base, "scope_kinds": ["fotos"]}, headers=h).status_code == 422
    req = _ok(
        client.post(
            H,
            json={
                **base,
                "scope_kinds": ["statement", "receipts"],
                "scope_text": "Heizkosten 2025",
            },
            headers=h,
        ),
        201,
    )
    rid = req["id"]
    assert req["status"] == "requested"
    assert req["property_id"] == prop["id"]
    assert [e["kind"] for e in req["events"]] == ["status"]

    # Read only role: sees the list, may not record, release or build a package.
    hr = bearer(login(client, world, "a61reader"))
    assert _ok(client.get(H, params={"legal_entity_id": hoa}, headers=hr))[0]["id"] == rid
    assert (
        client.post(H, json={**base, "scope_kinds": ["contracts"]}, headers=hr).status_code == 403
    )
    assert (
        client.post(f"{H}/{rid}/transition", json={"status": "released"}, headers=hr).status_code
        == 403
    )
    assert (
        client.post(f"{H}/{rid}/package", json={"document_ids": [rid]}, headers=hr).status_code
        == 403
    )

    # Tenant separation: the other tenant sees nothing and cannot read the request.
    ho = bearer(login(client, other_world, "a61other"))
    assert _ok(client.get(H, headers=ho)) == []
    assert client.get(f"{H}/{rid}", headers=ho).status_code == 404
    assert client.post(f"{H}/{rid}/notes", json={"text": "x"}, headers=ho).status_code == 404

    # Package before release is refused; a question is a note in the trail.
    _ok(client.post(f"{H}/{rid}/notes", json={"text": "Welches Jahr?"}, headers=h), 201)
    d1 = _doc(client, h, "abrechnung-2025.pdf", b"%PDF-1.4 a", hoa, owner=True)
    d2 = _doc(client, h, "beleg 07.pdf", b"%PDF-1.4 b", hoa, owner=True)
    d3 = _doc(client, h, "intern.pdf", b"%PDF-1.4 c", hoa, owner=False)
    assert (
        client.post(f"{H}/{rid}/package", json={"document_ids": [d1]}, headers=h).status_code == 409
    )
    assert (
        client.post(f"{H}/{rid}/transition", json={"status": "provided"}, headers=h).status_code
        == 409
    )
    rel = _ok(client.post(f"{H}/{rid}/transition", json={"status": "released"}, headers=h))
    assert rel["status"] == "released"
    assert rel["released_by_user_id"] == str(world.users["a61admin"])
    assert rel["released_at"] is not None

    # Only released documents of the community: the internal one is named and nothing is built.
    refused = client.post(f"{H}/{rid}/package", json={"document_ids": [d1, d3]}, headers=h)
    assert refused.status_code == 422, refused.text
    assert "intern.pdf" in refused.json()["detail"]
    assert "nicht für Eigentümer freigegeben" in refused.json()["detail"]
    assert _ok(client.get(f"{H}/{rid}", headers=h))["package_document_id"] is None

    candidates = _ok(client.get(f"{H}/{rid}/candidates", headers=h))
    assert [(c["filename"], c["released"]) for c in candidates] == [
        ("abrechnung-2025.pdf", True),
        ("beleg 07.pdf", True),
        ("intern.pdf", False),
    ]
    assert client.get(f"{H}/{rid}/candidates", headers=ho).status_code == 404

    pack = _ok(client.post(f"{H}/{rid}/package", json={"document_ids": [d2, d1]}, headers=h))
    assert [e["file"] for e in pack["entries"]] == ["abrechnung-2025.pdf", "beleg_07.pdf"]
    assert pack["entries"][0]["sha256"] == hashlib.sha256(b"%PDF-1.4 a").hexdigest()
    again = _ok(client.post(f"{H}/{rid}/package", json={"document_ids": [d1, d2]}, headers=h))
    assert again["sha256"] == pack["sha256"], "same selection must give the same ZIP"
    assert again["document_id"] != pack["document_id"]

    # The package is a document linked to the request and to the community.
    links = _ok(client.get(f"/api/v1/documents/{again['document_id']}", headers=h))["links"]
    assert {(x["entity_type"], x["entity_id"]) for x in links} >= {
        ("hoa_inspection_request", rid),
        ("legal_entity", hoa),
    }

    # Delivery: data medium needs the package (present); the download is logged and moves the
    # request to retrieved.
    prov = _ok(
        client.post(
            f"{H}/{rid}/transition",
            json={"status": "provided", "delivery_kind": "data_medium"},
            headers=h,
        )
    )
    assert prov["status"] == "provided"
    assert prov["delivery_kind"] == "data_medium"
    download = client.get(f"{H}/{rid}/package", headers=h)
    assert download.status_code == 200, download.text
    assert download.headers["content-type"].startswith("application/zip")
    assert hashlib.sha256(download.content).hexdigest() == again["sha256"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
        names = zf.namelist()
        assert names == [
            "dokumente/abrechnung-2025.pdf",
            "dokumente/beleg_07.pdf",
            "index.json",
            "index.csv",
        ]
        index = json.loads(zf.read("index.json"))
        assert [(e["file"], e["sha256"]) for e in index] == [
            ("abrechnung-2025.pdf", hashlib.sha256(b"%PDF-1.4 a").hexdigest()),
            ("beleg_07.pdf", hashlib.sha256(b"%PDF-1.4 b").hexdigest()),
        ]
        csv_text = zf.read("index.csv").decode("utf-8-sig")
        assert csv_text.startswith("Dateiname;Dokumentkategorie;Datum;SHA-256;Bytes\r\n")
        assert zf.read("dokumente/beleg_07.pdf") == b"%PDF-1.4 b"
    assert client.get(f"{H}/{rid}/package", headers=ho).status_code == 404

    detail = _ok(client.get(f"{H}/{rid}", headers=h))
    assert detail["status"] == "retrieved"
    kinds = [(e["kind"], e["to_status"]) for e in detail["events"]]
    assert kinds == [
        ("status", "requested"),
        ("note", None),
        ("status", "released"),
        ("package", None),
        ("package", None),
        ("status", "provided"),
        ("retrieval", "retrieved"),
    ]
    assert detail["events"][1]["note"] == "Welches Jahr?"

    # Closing is final; a rejection needs a reason (checked on a second request).
    closed = _ok(client.post(f"{H}/{rid}/transition", json={"status": "closed"}, headers=h))
    assert closed["status"] == "closed"
    assert (
        client.post(f"{H}/{rid}/transition", json={"status": "released"}, headers=h).status_code
        == 409
    )
    second = _ok(client.post(H, json={**base, "scope_kinds": ["resolutions"]}, headers=h), 201)
    assert (
        client.post(
            f"{H}/{second['id']}/transition", json={"status": "rejected"}, headers=h
        ).status_code
        == 422
    )
    rejected = _ok(
        client.post(
            f"{H}/{second['id']}/transition",
            json={"status": "rejected", "note": "Kein Eigentümer dieser Gemeinschaft."},
            headers=h,
        )
    )
    assert rejected["status"] == "rejected"
    assert rejected["events"][-1]["note"] == "Kein Eigentümer dieser Gemeinschaft."
    assert len(_ok(client.get(H, params={"property_id": prop["id"]}, headers=h))) == 2
