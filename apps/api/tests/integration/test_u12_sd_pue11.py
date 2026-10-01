"""U12 (SD-04): acceptance case PUE11, tenant inspection of the receipts behind the statement
(section 556 Abs. 4 BGB, electronic provision, D31) against the existing functions.

Expected values by hand (synthetic): the original receipt names a third party and an IBAN. The
tenant sees nothing of it before the release. The redacted copy (reason, scope, two steps) is
internal until a second person releases it for the tenant (four eyes). Afterwards the tenant
list holds exactly one document (the copy, with the redaction note), the original answers 404 in
list, detail, download and bundle, and stays unchanged and linked with role generated. A
neighbour tenant sees nothing. The bundle holds two files (copy and INDEX.csv)."""

import asyncio
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
from mhvp.portal import access
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user
from tests.integration.test_q10_portal_w3 import _tenant_setup

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
ORIGINAL = b"Beleg Handwerker Meyer, Zahler Erika Beispiel, IBAN DE00 0000 0000 0000 0000 00"
REDACTED = b"Beleg Handwerker Meyer, Zahler XXXX, IBAN XXXX"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"u12a-{RUN}", name=f"U12 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"u12b-{RUN}", name=f"U12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("u12admin", a), ("u12second", a), ("u12other", b)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
                actor_user_id=None,
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


def test_sd04_pue11_tenant_receipt_inspection_redaction_flow(
    client: TestClient, world: World
) -> None:
    ha = bearer(login(client, world, "u12admin"))
    second = bearer(login(client, world, "u12second"))
    contract, meta = _tenant_setup(client, ha, world, "941")
    tenant = _portal_user(client, ha, world, "u12mieter", _contact_of(client, ha, meta["party"]))

    original = _ok(
        client.post(
            "/api/v1/documents",
            data={
                "title": "Handwerkerrechnung",
                "links": json.dumps([{"entity_type": "contract", "entity_id": contract}]),
            },
            files={"file": ("beleg.txt", ORIGINAL, "text/plain")},
            headers=ha,
        ),
        201,
    )
    oid = original["id"]
    # Receipts with data of third parties are internal by decision of the administrator.
    _ok(client.patch(f"/api/v1/documents/{oid}", json={"visibility": ["internal"]}, headers=ha))
    # Before any release the tenant sees nothing (no blanket opening of private files).
    assert _ok(client.get(f"{P}/documents", headers=tenant)) == []

    url = f"/api/v1/documents/{oid}/redactions"
    form = {
        "reason": "Angaben Dritter nicht erforderlich",
        "scope": "Name Zahler und IBAN",
        "steps": json.dumps(["Name geschwärzt", "IBAN geschwärzt"]),
    }
    red = _ok(
        client.post(
            url, files={"file": ("beleg.txt", REDACTED, "text/plain")}, data=form, headers=ha
        ),
        201,
    )
    copy_id = red["copy_document_id"]
    assert red["released_at"] is None
    assert red["reason"] == form["reason"]
    assert red["steps"] == ["Name geschwärzt", "IBAN geschwärzt"]
    assert _ok(client.get(f"{P}/documents", headers=tenant)) == []  # internal until released

    release = f"{url}/{red['id']}/release"
    assert client.post(release, json={"visibility": ["tenant"]}, headers=ha).status_code == 403
    _ok(client.post(release, json={"visibility": ["tenant"]}, headers=second))

    listed = _ok(client.get(f"{P}/documents", headers=tenant))
    assert [d["id"] for d in listed] == [copy_id]
    assert listed[0]["redaction_note"] == access.REDACTION_NOTE
    detail = _ok(client.get(f"{P}/documents/{copy_id}", headers=tenant))
    assert detail["redaction_note"] == access.REDACTION_NOTE
    body = client.get(f"{P}/documents/{copy_id}/download", headers=tenant)
    assert body.status_code == 200
    assert body.content == REDACTED
    assert b"IBAN DE00" not in body.content

    # The original stays out of every path of the tenant.
    assert client.get(f"{P}/documents/{oid}", headers=tenant).status_code == 404
    assert client.get(f"{P}/documents/{oid}/download", headers=tenant).status_code == 404
    assert (
        client.post(
            f"{P}/documents/bundle", json={"document_ids": [copy_id, oid]}, headers=tenant
        ).status_code
        == 404
    )
    bundle = client.post(f"{P}/documents/bundle", json={"document_ids": [copy_id]}, headers=tenant)
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert len(archive.namelist()) == 2
        assert "INDEX.csv" in archive.namelist()
        assert all(ORIGINAL not in archive.read(n) for n in archive.namelist())

    # Original unchanged, linked to the copy with role generated; deletion before the copy is refused.
    kept = _ok(client.get(f"/api/v1/documents/{oid}", headers=ha))
    assert kept["sha256"] == original["sha256"]
    copy = _ok(client.get(f"/api/v1/documents/{copy_id}", headers=ha))
    assert any(
        x["entity_type"] == "document" and x["entity_id"] == oid and x["role"] == "generated"
        for x in copy["links"]
    )
    assert client.delete(f"/api/v1/documents/{oid}", headers=ha).status_code == 409

    # Tenant isolation: another tenant neither sees nor redacts the original.
    other = bearer(login(client, world, "u12other"))
    assert client.get(f"/api/v1/documents/{oid}", headers=other).status_code == 404
    assert client.get(url, headers=other).status_code == 404
    # Validation: a redaction without steps or reason is refused.
    bad = client.post(
        url,
        files={"file": ("b.txt", b"Beleg XXX", "text/plain")},
        data={**form, "steps": "[]"},
        headers=ha,
    )
    assert bad.status_code == 422
