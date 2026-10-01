"""SECURITY-2026-10-01 (R13): portal chat reply honours the property assignment (Befund 3),
the portal bundle index neutralises spreadsheet formulas (Befund 4), a password change ends
all refresh tokens (Befund 5). Other tenant 404, missing permission 403, bad body 422."""

import asyncio
import csv
import io
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
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok, _portal_user
from tests.integration.test_q10_portal_w3 import _released_doc, _tenant_setup
from tests.integration.test_q13_property_scope_etag import _assign, _estate

pytestmark = pytest.mark.integration
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"r13a-{RUN}", name=f"R13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"r13b-{RUN}", name=f"R13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("r13admin", a, "tenant_admin"),
            ("r13adminb", b, "tenant_admin"),
            ("r13clerk", a, "standard"),
            ("r13reader", a, "read_only"),
            ("r13pw", a, "read_only"),
        ):
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


def test_chat_reply_respects_property_assignment(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r13admin"))
    _ok(client.patch(f"{PA}/features", json={"chat_enabled": True}, headers=h))
    own = _estate(client, h, "731")
    foreign = _estate(client, h, "732")
    _assign(client, h, world.users["r13clerk"], [own["property"]])
    c = bearer(login(client, world, "r13clerk"))
    body = {"body": "Antwort der Verwaltung"}

    assert (
        client.post(f"{PA}/tickets/{own['ticket']}/messages", json=body, headers=c).status_code
        == 201
    )
    # outside the assignment: 404 (not 201), nothing written
    assert (
        client.post(f"{PA}/tickets/{foreign['ticket']}/messages", json=body, headers=c).status_code
        == 404
    )
    # other tenant 404, read only 403, empty body 422
    hb = bearer(login(client, world, "r13adminb"))
    _ok(client.patch(f"{PA}/features", json={"chat_enabled": True}, headers=hb))
    assert (
        client.post(f"{PA}/tickets/{own['ticket']}/messages", json=body, headers=hb).status_code
        == 404
    )
    r = bearer(login(client, world, "r13reader"))
    assert (
        client.post(f"{PA}/tickets/{own['ticket']}/messages", json=body, headers=r).status_code
        == 403
    )
    assert (
        client.post(
            f"{PA}/tickets/{own['ticket']}/messages", json={"body": ""}, headers=h
        ).status_code
        == 422
    )


def test_bundle_index_neutralises_formulas(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "r13admin"))
    contract, meta = _tenant_setup(client, h, world, "913")
    evil = '=HYPERLINK("http://example.invalid","x")'
    doc = _released_doc(client, h, evil, contract, ["tenant"])
    portal = _portal_user(client, h, world, "r13res", _contact_of(client, h, meta["party"]))
    res = client.post(
        "/api/v1/portal/documents/bundle", json={"document_ids": [doc]}, headers=portal
    )
    assert res.status_code == 200, res.text
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        index = archive.read("INDEX.csv").decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(index), delimiter=";"))
    assert rows[1][1] == "'" + evil
    assert not any(cell.startswith("=") for row in rows for cell in row)


def test_password_change_revokes_refresh_tokens(client: TestClient, world: World) -> None:
    issued = login(client, world, "r13pw")
    other = login(client, world, "r13pw")  # second device
    headers = bearer(issued)
    new_password = "R13-neues-Kennwort-2026"
    done = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": new_password},
        headers=headers,
    )
    assert done.status_code == 204, done.text
    for tokens in (issued, other):
        refreshed = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refreshed.status_code == 401, refreshed.text
    relogin = client.post(
        "/api/v1/auth/login", json={"email": world.email("r13pw"), "password": new_password}
    )
    assert relogin.status_code == 200
