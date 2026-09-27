"""Messdienstleister stage 2: document intake into the document store, sync executor and
tenant boundaries (master prompt Messdienstleister section 13, cases 7, 8 and 10). Artificial
data only: the ``fake`` adapter scripts the provider, the object store is moto. No sandbox or
production system of ista or KALO is called (end to end checks with real access are not
executed, see docs/integrations/messdienstleister.md)."""

import asyncio
import base64
import io
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.blobs import BlobStore
from mhvp.documents.models import Document
from mhvp.main import create_app
from mhvp.metering.adapters import _ADAPTERS, FakeAdapter
from mhvp.metering.tasks import run_sync_job_once
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m40_metering import _assign, _connection, _ok

pytestmark = pytest.mark.integration

BUCKET = "mhvp-docs"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=200_000,
    )


@pytest.fixture
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


@pytest.fixture
def admin(client: TestClient, world: World) -> dict[str, str]:
    h = bearer(login(client, world, "admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"metering_module_enabled": True}, headers=h))
    return h


def _property(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    number = f"{(int(RUN[:6], 16) + int(number)) % 1000:03d}"  # NNN, unique per run
    """Property without building: the metering assignment needs only the property; unit
    assignments are covered by the stage 1 cases."""
    existing = _ok(client.get("/api/v1/properties", params={"search": number}, headers=h))
    rows = existing if isinstance(existing, list) else existing.get("items", [])
    for row in rows:
        if row.get("number") == number:
            return dict(row)
    return dict(
        _ok(
            client.post(
                "/api/v1/properties",
                json={
                    "number": number,
                    "name": f"Messhaus {number}",
                    "management_type": "rental",
                    "street": "Zählerweg",
                    "house_number": "2",
                    "postal_code": "40789",
                    "city": "Monheim am Rhein",
                },
                headers=h,
            ),
            201,
        )
    )


def _pdf(text: str) -> str:
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    canvas.drawString(72, 720, text)
    canvas.save()
    return base64.b64encode(buffer.getvalue()).decode()


def _document(external_id: str, version: str, content: str, **extra: Any) -> dict[str, Any]:
    return {
        "type": "document",
        "external_id": external_id,
        "version": version,
        "filename": f"{external_id}.pdf",
        "doctype": "HKA-G",
        "external_billing_unit": "0004750",
        "period_from": "2025-01-01",
        "period_to": "2025-12-31",
        "content_b64": content,
        **extra,
    }


def _meta(settings: Settings, tenant: uuid.UUID, document_id: str) -> dict[str, Any]:
    """Provenance of a stored document (``source_meta`` is not part of the public schema)."""

    async def read() -> dict[str, Any]:
        engine = create_async_engine(
            settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
        )
        try:
            async with tenant_transaction(create_session_factory(engine), tenant) as session:
                row = await session.get(Document, uuid.UUID(document_id))
                assert row is not None
                return {
                    "source_system": row.source_system,
                    "source_id": row.source_id,
                    "visibility": list(row.visibility),
                    **dict(row.source_meta or {}),
                }
        finally:
            await engine.dispose()

    return asyncio.run(read())


def _version(client: TestClient, h: dict[str, str], conn: dict[str, Any]) -> int:
    return int(_ok(client.get(f"/api/v1/metering/connections/{conn['id']}", headers=h))["version"])


def _run(settings: Settings, tenant: uuid.UUID, job: dict[str, Any]) -> str:
    return asyncio.run(run_sync_job_once(settings, tenant, uuid.UUID(job["id"])))


def _job(client: TestClient, h: dict[str, str], conn: dict[str, Any], prop: dict[str, Any]) -> Any:
    return _ok(
        client.post(
            "/api/v1/metering/sync-jobs",
            json={
                "connection_id": conn["id"],
                "data_kind": "documents",
                "property_ids": [prop["id"]],
            },
            headers=h,
        ),
        202,
    )


def test_case_7_document_redownload_versions_and_receipt_only_after_storage(
    client: TestClient,
    world: World,
    admin: dict[str, str],
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mhvp.metering.tasks.run_sync_job_task.delay", lambda *args: None)
    fake = _ADAPTERS["fake"]
    assert isinstance(fake, FakeAdapter)
    fake.acknowledged.clear()
    fake.downloads.clear()
    settings = _settings(database, redis_url)
    prop = _property(client, admin, "915")
    records = [
        _document(f"DOC-{RUN}-1", "h1", _pdf("Abrechnung 2025"), external_unit_number="0001"),
        _document(f"DOC-{RUN}-2", "h1", "bm9wZQ=="),  # not a PDF: rejected, never acknowledged
        _document(f"DOC-{RUN}-3", "h1", _pdf("fremd"), external_billing_unit="0009999"),
        _document(f"DOC-{RUN}-4", "h1", _pdf("ohne Referenz"), external_billing_unit=None),
    ]
    conn = _connection(
        client,
        admin,
        f"ista Dokumente {RUN}",
        config={"adapter": "fake", "fake_records": records},
        account_release={"documents": True},
    )
    _ok(client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=admin))
    assignment = _ok(
        _assign(client, admin, conn, prop, external_number="0004750", valid_from="2025-01-01"),
        201,
    )
    job = _job(client, admin, conn, prop)
    assert _run(settings, world.tenant_a, job) == "succeeded"
    done = _ok(client.get(f"/api/v1/metering/sync-jobs/{job['id']}", headers=admin))
    parts = {p["part"]: p for p in done["parts"]}
    assert parts["store"]["stored"] == 1, done
    assert "3 Datensätze" in parts["clearing"]["error"]
    clearing = _ok(
        client.get(
            "/api/v1/metering/clearing-items", params={"connection_id": conn["id"]}, headers=admin
        )
    )
    assert {c["external_identifier"] for c in clearing} == {
        f"DOC-{RUN}-2",
        f"DOC-{RUN}-3",
        f"DOC-{RUN}-4",
    }
    docs = _ok(
        client.get(
            "/api/v1/documents",
            params={"entity_type": "property", "entity_id": prop["id"]},
            headers=admin,
        )
    )["items"]
    assert len(docs) == 1
    first = _meta(settings, world.tenant_a, docs[0]["id"])
    assert first["source_system"] == "metering"
    assert first["external_id"] == f"DOC-{RUN}-1"
    assert first["property_assignment_id"] == assignment["id"]
    assert first["provider_code"] == "ista" and first["connection_id"] == conn["id"]  # noqa: PT018
    assert first["visibility"] == ["tenant"]
    assert (
        _ok(client.get(f"/api/v1/documents/{docs[0]['id']}", headers=admin))["source"] == "import"
    )
    # receipt only for the durably stored document, sent after the commit
    assert fake.acknowledged == [f"DOC-{RUN}-1"]
    assert first["acknowledge_pending"] is False and first["acknowledged_at"]  # noqa: PT018
    # re download: no duplicate, no second download of the same version
    downloads_before = len(fake.downloads)
    assert _run(settings, world.tenant_a, _job(client, admin, conn, prop)) == "succeeded"
    docs = _ok(
        client.get(
            "/api/v1/documents",
            params={"entity_type": "property", "entity_id": prop["id"]},
            headers=admin,
        )
    )["items"]
    assert len(docs) == 1
    assert fake.downloads.count(f"DOC-{RUN}-1") == 1
    assert len(fake.downloads) > downloads_before  # rejected documents are re-tried (clearing)
    # corrected billing under the same external id: new version, old document kept
    records[0] = _document(f"DOC-{RUN}-1", "h2", _pdf("Abrechnung 2025 korrigiert"))
    _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={
                "config": {"adapter": "fake", "fake_records": records},
                "version": _version(client, admin, conn),
            },
            headers=admin,
        )
    )
    _ok(client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=admin))
    assert _run(settings, world.tenant_a, _job(client, admin, conn, prop)) == "succeeded"
    docs = _ok(
        client.get(
            "/api/v1/documents",
            params={"entity_type": "property", "entity_id": prop["id"]},
            headers=admin,
        )
    )["items"]
    metas = [_meta(settings, world.tenant_a, d["id"]) for d in docs]
    assert {m["version"] for m in metas} == {"h1", "h2"}
    newer = next(m for m in metas if m["version"] == "h2")
    assert newer["supersedes"] == [docs[0]["id"]] or len(newer["supersedes"]) == 1
    # a failed storage process produces no receipt
    fake.acknowledged.clear()
    records[0] = _document(f"DOC-{RUN}-9", "h1", _pdf("Speicherfehler"))
    _ok(
        client.patch(
            f"/api/v1/metering/connections/{conn['id']}",
            json={
                "config": {"adapter": "fake", "fake_records": records},
                "version": _version(client, admin, conn),
            },
            headers=admin,
        )
    )
    _ok(client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=admin))
    job = _job(client, admin, conn, prop)

    def broken_put(self: BlobStore, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("object store down")

    monkeypatch.setattr(BlobStore, "put", broken_put)
    with pytest.raises(RuntimeError):
        _run(settings, world.tenant_a, job)
    assert fake.acknowledged == []
    assert (
        _ok(client.get(f"/api/v1/metering/sync-jobs/{job['id']}", headers=admin))["status"]
        == "queued"
    )
    assert f"DOC-{RUN}-9" not in {
        _meta(settings, world.tenant_a, d["id"])["external_id"]
        for d in _ok(
            client.get(
                "/api/v1/documents",
                params={"entity_type": "property", "entity_id": prop["id"]},
                headers=admin,
            )
        )["items"]
    }


def test_case_8_10_tenant_boundary_partial_fetch_and_lock(
    client: TestClient,
    world: World,
    admin: dict[str, str],
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mhvp.metering.tasks.run_sync_job_task.delay", lambda *args: None)
    settings = _settings(database, redis_url)
    prop = _property(client, admin, "916")
    records = [
        {
            "external_billing_unit": "0004760",
            "external_unit_number": None,
            "period_from": "2026-01-01",
            "period_to": "2026-01-31",
            "value": "7",
        }
    ]
    conn = _connection(
        client,
        admin,
        f"ista teilweise {RUN}",
        config={
            "adapter": "fake",
            "fake_records": records,
            "fake_errors": ["Abrechnungseinheit B: Anbieterfehler (HTTP 503)."],
        },
    )
    _ok(client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=admin))
    _ok(_assign(client, admin, conn, prop, external_number="0004760"), 201)
    job = _ok(
        client.post(
            "/api/v1/metering/sync-jobs",
            json={
                "connection_id": conn["id"],
                "data_kind": "consumption",
                "property_ids": [prop["id"]],
            },
            headers=admin,
        ),
        202,
    )
    # case 8: another tenant sees neither the job nor can it execute it
    other = bearer(login(client, world, "both", tenant_id=world.tenant_b))
    assert client.get(f"/api/v1/metering/sync-jobs/{job['id']}", headers=other).status_code == 404
    assert _run(settings, world.tenant_b, job) == "missing"
    # case 10: partial fetch is shown as partial with the error per part, last success kept
    assert _run(settings, world.tenant_a, job) == "partial"
    done = _ok(client.get(f"/api/v1/metering/sync-jobs/{job['id']}", headers=admin))
    parts = {p["part"]: p for p in done["parts"]}
    assert parts["fetch"]["status"] == "error" and "HTTP 503" in parts["fetch"]["error"]  # noqa: PT018
    assert parts["store"]["stored"] == 1
    assert "geheim" not in done["error_summary"]
    # lock: a finished job is never executed twice (idempotent re run)
    assert _run(settings, world.tenant_a, job) == "skipped"
    connection = _ok(client.get(f"/api/v1/metering/connections/{conn['id']}", headers=admin))
    assert connection["last_sync"]["consumption"]
    assert "secrets" not in connection and connection["secret_names"] == ["api_key"]  # noqa: PT018
