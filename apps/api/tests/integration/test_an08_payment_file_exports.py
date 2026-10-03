"""AN08 (AM01 rest, GAJ-301): payment files in exports stay behind release gate G2.

Expected values by hand: one plain document (content exported in every case) and one
document in the ``payment_file`` category. With G2 closed the full tenant export carries the
payment file's metadata row in data/documents.jsonl, no original under documents/ and one
``withheld`` entry; with G2 open the original is exported. The Objektakte export of a
property with both documents linked contains one file and logs one withheld document while
G2 is closed, and two files when G2 is open.
"""

import asyncio
import io
import json
import uuid
import zipfile
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m27_market_readiness import BUCKET, _settings

pytestmark = pytest.mark.integration
PREFIX = f"9-an08-{RUN}"


class _Resolver:
    def __init__(self, open_: bool) -> None:
        self.open_ = open_

    async def is_open(self, tenant_id: uuid.UUID, gate: Any) -> bool:
        return self.open_


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"{PREFIX}a", name=f"AN08A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"{PREFIX}b", name=f"AN08B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory,
            email=world.email("an08admin"),
            display_name="an08admin",
            password=PASSWORD,
            is_platform_admin=False,
        )
        world.users["an08admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


async def _mark_and_link(
    settings: Any, tenant_id: uuid.UUID, pay_id: str, plain_id: str, prop_id: uuid.UUID
) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents import payment_files
    from mhvp.documents.models import Document, DocumentLink, LinkRole

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            doc = await session.get(Document, uuid.UUID(pay_id))
            assert doc is not None
            doc.category_id = await payment_files.category_id(session, tenant_id)
            for d in (pay_id, plain_id):
                session.add(
                    DocumentLink(
                        tenant_id=tenant_id,
                        document_id=uuid.UUID(d),
                        entity_type="property",
                        entity_id=prop_id,
                        role=LinkRole.ORIGINAL,
                    )
                )
    finally:
        await engine.dispose()


async def _full_export(settings: Any, tenant_id: uuid.UUID, target: Any) -> dict[str, Any]:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform.export_job import build_full_export

    engine = create_app_engine(settings)
    try:
        return await build_full_export(
            create_session_factory(engine),
            tenant_id,
            "an08",
            target,
            boto3.client("s3", region_name="us-east-1"),
            BUCKET,
        )
    finally:
        await engine.dispose()


async def _objektakte_files(
    settings: Any, tenant_id: uuid.UUID, prop_id: uuid.UUID
) -> tuple[list[str], Any]:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.documents.blobs import BlobStore
    from mhvp.objektakte.export import ExportResult, _documents

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            result = ExportResult(data=b"")
            prop = SimpleNamespace(id=prop_id, tenant_id=tenant_id)
            files = await _documents(session, BlobStore(settings), prop, result)  # type: ignore[arg-type]
            return [p for p, _ in files], result
    finally:
        await engine.dispose()


def test_payment_file_content_withheld_while_g2_closed(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from mhvp.core import release_gates

    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "an08admin"))
    ids = []
    for name, body in (("zahlung.xml", b"<Document>pain</Document>"), ("akte.txt", b"Akte")):
        up = client.post("/api/v1/documents", files={"file": (name, body, "text/plain")}, headers=h)
        assert up.status_code == 201, up.text
        ids.append(up.json()["id"])
    pay_id, plain_id = ids
    prop_id = uuid.uuid4()
    asyncio.run(_mark_and_link(settings, world.tenant_a, pay_id, plain_id, prop_id))

    # G2 closed (default resolver): metadata only, content withheld.
    monkeypatch.setattr(release_gates, "job_release_gate_resolver", _Resolver(False))
    target = tmp_path / "closed.zip"
    manifest = asyncio.run(_full_export(settings, world.tenant_a, target))
    archive = zipfile.ZipFile(target)
    names = archive.namelist()
    assert not any(n.startswith(f"documents/{pay_id}_") for n in names)
    assert any(n.startswith(f"documents/{plain_id}_") for n in names)
    withheld = manifest["documents"]["withheld"]
    assert [w["document_id"] for w in withheld] == [pay_id]
    assert withheld[0]["reason"] == "payment_file_g2_closed"
    rows = [json.loads(x) for x in archive.read("data/documents.jsonl").splitlines()]
    assert pay_id in {r["id"] for r in rows}
    paths, result = asyncio.run(_objektakte_files(settings, world.tenant_a, prop_id))
    assert len(paths) == 1
    assert paths[0].endswith("akte.txt")
    assert result.counts["documents_withheld"] == 1
    assert any("zahlung.xml" in line for line in result.log)

    # G2 open: content exported.
    monkeypatch.setattr(release_gates, "job_release_gate_resolver", _Resolver(True))
    target = tmp_path / "open.zip"
    manifest = asyncio.run(_full_export(settings, world.tenant_a, target))
    names = zipfile.ZipFile(io.BytesIO(target.read_bytes())).namelist()
    assert any(n.startswith(f"documents/{pay_id}_") for n in names)
    assert manifest["documents"]["withheld"] == []
    paths, result = asyncio.run(_objektakte_files(settings, world.tenant_a, prop_id))
    assert len(paths) == 2
    assert "documents_withheld" not in result.counts


def test_resolver_error_counts_as_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    from mhvp.core import release_gates
    from mhvp.documents import payment_files

    class _Broken:
        async def is_open(self, tenant_id: uuid.UUID, gate: Any) -> bool:
            raise RuntimeError("down")

    monkeypatch.setattr(release_gates, "job_release_gate_resolver", _Broken())
    assert asyncio.run(payment_files.content_released(uuid.uuid4())) is False
    assert asyncio.run(payment_files.content_released(uuid.uuid4(), _Resolver(True))) is True
