"""AE37 (Q08-01, M8): header detection, column proposal, stored assignments per tenant and
report type, validation report and status of the required exports.

Headers are invented for the test and make no statement about real Immoware24 exports (13.1).
Expected values by hand (rule 0.1.8): the CSV has a title line and an empty line above the
header, so the header is row 3 and rows 4 and 5 are data; "Objekt-Nr." becomes the label
"Objektnummer" (95), "Bezeichnung", "Verwaltungsart" and "Ort" equal their labels (95). With
the value map WEG -> hoa and Miete -> rental both rows are valid; without it both fail.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-ae37"
BASE = "/api/v1/imports/immoware24"
CSV = (
    b"Bestandsliste Stand 30.09.2026;;;\n"
    b";;;\n"
    b"Objekt-Nr.;Bezeichnung;Verwaltungsart;Ort\n"
    b"001;Haus A;WEG;Bernau\n"
    b"002;Haus B;Miete;Berlin\n"
)
VALUE_MAPS = {"management_type": {"WEG": "hoa", "Miete": "rental"}}


def _settings(database: Database, redis_url: str) -> Settings:
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
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae37-{RUN}", name=f"AE37 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae37b-{RUN}", name=f"AE37b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae37admin", a, "tenant_admin"),
            ("ae37reader", a, "read_only"),
            ("ae37other", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _document(c: TestClient, h: dict[str, str]) -> Any:
    files = {"file": (f"bestand-{RUN}.csv", CSV, "text/csv")}
    return _ok(c.post("/api/v1/documents", files=files, headers=h), 201)


def _stage(c: TestClient, h: dict[str, str]) -> tuple[Any, Any]:
    doc = _document(c, h)
    detected = _ok(
        c.post(
            f"{BASE}/header-detection",
            json={"document_id": doc["id"], "report_type": "properties"},
            headers=h,
        )
    )
    source = _ok(
        c.post(
            f"{BASE}/files",
            json={
                "document_id": doc["id"],
                "report_type": "properties",
                "header_row": detected["header_row"],
            },
            headers=h,
        ),
        201,
    )
    return detected, source


def test_detection_proposal_check_and_stored_assignments(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae37admin"))
    detected, source = _stage(client, h)
    assert detected["header_row"] == 3
    assert detected["headers"] == ["Objekt-Nr.", "Bezeichnung", "Verwaltungsart", "Ort"]
    assert detected["candidates"][0]["score"] == 100
    assert source["row_count"] == 2

    proposal = _ok(client.get(f"{BASE}/files/{source['id']}/column-proposal", headers=h))
    assert proposal["columns"] == {
        "number": "Objekt-Nr.",
        "name": "Bezeichnung",
        "management_type": "Verwaltungsart",
        "city": "Ort",
    }
    assert proposal["missing_required"] == []
    assert {f["status"] for f in proposal["fields"] if f["header"]} == {"sure"}

    check = _ok(
        client.post(
            f"{BASE}/files/{source['id']}/check",
            json={"columns": proposal["columns"], "value_maps": VALUE_MAPS},
            headers=h,
        )
    )
    assert (check["rows"], check["valid"], check["invalid"], check["ready"]) == (2, 2, 0, True)
    assert [r["status"] for r in check["required"]] == ["ok", "ok", "ok"]
    assert check["sample_rows"][0]["values"]["management_type"] == "hoa"
    unmapped = _ok(
        client.post(
            f"{BASE}/files/{source['id']}/check", json={"columns": proposal["columns"]}, headers=h
        )
    )
    assert (unmapped["valid"], unmapped["invalid"]) == (0, 2)
    assert unmapped["error_rows"][0]["row_number"] == 4

    # The check changed nothing: the staged rows are still pending.
    rows = _ok(client.get(f"{BASE}/files/{source['id']}/rows", headers=h))
    assert {r["status"] for r in rows} == {"pending"}

    body = {
        "report_type": "properties",
        "assignments": [
            {"header": "Objekt-Nr.", "target_field": "number"},
            {"header": "Ort", "target_field": None},
        ],
    }
    saved = _ok(client.put(f"{BASE}/column-assignments", json=body, headers=h))
    assert [(a["header"], a["target_field"], a["use_count"]) for a in saved] == [
        ("Objekt-Nr.", "number", 1),
        ("Ort", None, 1),
    ]
    again = _ok(client.put(f"{BASE}/column-assignments", json=body, headers=h))
    assert [a["use_count"] for a in again] == [2, 2]

    proposal = _ok(client.get(f"{BASE}/files/{source['id']}/column-proposal", headers=h))
    number = next(f for f in proposal["fields"] if f["name"] == "number")
    assert (number["status"], number["score"]) == ("stored", 100)
    assert proposal["ignored_headers"] == ["Ort"]
    assert "city" not in proposal["columns"]

    requirements = {
        r["report_type"]: r for r in _ok(client.get(f"{BASE}/export-requirements", headers=h))
    }
    props = requirements["properties"]
    assert (props["status"], props["files"], props["required_covered"]) == (
        "mapping_open",
        1,
        ["number"],
    )
    assert props["source"] == "Reports: Objektliste"
    assert requirements["units"]["status"] == "file_missing"

    full = {
        "report_type": "properties",
        "assignments": [
            {"header": "Bezeichnung", "target_field": "name"},
            {"header": "Verwaltungsart", "target_field": "management_type"},
        ],
    }
    _ok(client.put(f"{BASE}/column-assignments", json=full, headers=h))
    requirements = {
        r["report_type"]: r for r in _ok(client.get(f"{BASE}/export-requirements", headers=h))
    }
    assert requirements["properties"]["status"] == "mapping_stored"

    listed = _ok(
        client.get(f"{BASE}/column-assignments", params={"report_type": "properties"}, headers=h)
    )
    ort = next(a for a in listed if a["header"] == "Ort")
    assert client.delete(f"{BASE}/column-assignments/{ort['id']}", headers=h).status_code == 204
    listed = _ok(client.get(f"{BASE}/column-assignments", headers=h))
    assert "Ort" not in {a["header"] for a in listed}


def test_check_with_template(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae37admin"))
    _, source = _stage(client, h)
    mapping = _ok(
        client.post(
            f"{BASE}/mappings",
            json={
                "report_type": "properties",
                "name": f"AE37 {RUN}",
                "columns": {"number": "Objekt-Nr.", "management_type": "Verwaltungsart"},
                "value_maps": VALUE_MAPS,
            },
            headers=h,
        ),
        201,
    )
    check = _ok(
        client.post(
            f"{BASE}/files/{source['id']}/check", json={"mapping_id": mapping["id"]}, headers=h
        )
    )
    status = {r["name"]: r["status"] for r in check["required"]}
    assert status == {"number": "ok", "name": "missing", "management_type": "ok"}
    assert check["ready"] is False


def test_permissions_tenant_separation_and_validation(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "ae37admin"))
    reader = bearer(login(client, world, "ae37reader"))
    other = bearer(login(client, world, "ae37other"))
    detected, source = _stage(client, admin)
    saved = _ok(
        client.put(
            f"{BASE}/column-assignments",
            json={
                "report_type": "units",
                "assignments": [{"header": "VE", "target_field": "number"}],
            },
            headers=admin,
        )
    )
    assignment = next(a for a in saved if a["header"] == "VE")

    # Read permission: proposal, check and list yes; detection and saving no.
    _ok(client.get(f"{BASE}/files/{source['id']}/column-proposal", headers=reader))
    _ok(client.get(f"{BASE}/column-assignments", headers=reader))
    _ok(client.get(f"{BASE}/export-requirements", headers=reader))
    put = client.put(
        f"{BASE}/column-assignments",
        json={"report_type": "units", "assignments": [{"header": "X", "target_field": "number"}]},
        headers=reader,
    )
    assert put.status_code == 403
    assert (
        client.delete(f"{BASE}/column-assignments/{assignment['id']}", headers=reader).status_code
        == 403
    )
    doc = _document(client, admin)
    detect = client.post(
        f"{BASE}/header-detection",
        json={"document_id": doc["id"], "report_type": "properties"},
        headers=reader,
    )
    assert detect.status_code == 403

    # Other tenant: nothing visible, nothing deletable.
    assert (
        client.get(f"{BASE}/files/{source['id']}/column-proposal", headers=other).status_code == 404
    )
    assert (
        client.post(
            f"{BASE}/files/{source['id']}/check", json={"columns": {}}, headers=other
        ).status_code
        == 404
    )
    assert (
        client.delete(f"{BASE}/column-assignments/{assignment['id']}", headers=other).status_code
        == 404
    )
    assert _ok(client.get(f"{BASE}/column-assignments", headers=other)) == []
    foreign = client.post(
        f"{BASE}/header-detection",
        json={"document_id": doc["id"], "report_type": "properties"},
        headers=other,
    )
    assert foreign.status_code == 404

    # Validation.
    def put_status(body: dict[str, Any]) -> int:
        return client.put(f"{BASE}/column-assignments", json=body, headers=admin).status_code

    assert (
        put_status({"report_type": "units", "assignments": [{"header": "A", "target_field": "x"}]})
        == 422
    )
    assert put_status({"report_type": "journal", "assignments": [{"header": "A"}]}) == 422
    assert (
        put_status(
            {
                "report_type": "units",
                "assignments": [{"header": "Ort", "target_field": None}, {"header": " ort "}],
            }
        )
        == 422
    )
    assert put_status({"report_type": "units", "assignments": [{"header": "---"}]}) == 422
    assert put_status({"report_type": "units", "assignments": []}) == 422
    check = f"{BASE}/files/{source['id']}/check"
    assert client.post(check, json={}, headers=admin).status_code == 422
    assert (
        client.post(
            check,
            json={"columns": {"no_field": "Ort"}, "mapping_id": assignment["id"]},
            headers=admin,
        ).status_code
        == 422
    )
    assert (
        client.post(check, json={"columns": {"no_field": "Ort"}}, headers=admin).status_code == 422
    )
    assert (
        client.post(check, json={"columns": {}, "sample_size": 99}, headers=admin).status_code
        == 422
    )
    assert (
        client.get(f"{BASE}/column-assignments", params={"x": "1"}, headers=admin).status_code
        == 422
    )
    assert detected["header_row"] == 3
