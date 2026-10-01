# ruff: noqa: F811
"""B26/M21-04: public portal branding by portal host (colours, legal links, logo), neutral when
empty; B20: the tenant policy ``required`` forces the e-mail code for the magic link."""

import asyncio
import base64
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from redis.asyncio import Redis

from mhvp.core.auth import tokens
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.portal import magic_link
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m6_documents import BUCKET, _settings, _upload
from tests.integration.test_m21_magic_link import (  # noqa: F401
    _activated_account,
    _factory,
    _insert_link,
    app_settings,
)

pytestmark = pytest.mark.integration
# 1x1 transparent PNG.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"br-{RUN}", name=f"Marke {RUN}", domains=[f"portal-br-{RUN}.test"]
        )
        b, _ = await services.provision_tenant(
            factory, slug=f"bq-{RUN}", name=f"Leer {RUN}", domains=[f"portal-bq-{RUN}.test"]
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("bradmin"), display_name="bradmin", password=PASSWORD
        )
        world.users["bradmin"] = uid
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
def s3() -> Iterator[None]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield


@pytest.fixture
def client(database: Database, redis_url: str, s3: None) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def test_portal_branding_by_host_and_logo(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "bradmin"))
    host_a = {"x-portal-host": f"portal-br-{RUN}.test"}
    host_b = {"x-portal-host": f"portal-bq-{RUN}.test"}
    # Empty branding: neutral values, no logo, nothing invented.
    empty = client.get("/api/v1/tenant/branding", headers=host_a)
    assert empty.status_code == 200
    assert empty.json()["branding"]["imprint_url"] is None
    assert empty.json()["has_logo_light"] is False
    assert client.get("/api/v1/tenant/branding/logo/light", headers=host_a).status_code == 404
    assert (
        client.get("/api/v1/tenant/branding", headers={"x-portal-host": "unknown.test"}).status_code
        == 404
    )

    uploaded = _upload(client, h, "logo.png", PNG, "image/png")
    assert uploaded.status_code == 201, uploaded.text
    patch = client.patch(
        "/api/v1/tenant/settings",
        json={
            "branding": {
                "primary_color": "#112233",
                "accent_color": "#AA5500",
                "portal_name": "Mein Portal",
                "imprint_url": "https://example.test/impressum",
                "privacy_url": "https://example.test/datenschutz",
                "logo_light_document_id": uploaded.json()["id"],
            }
        },
        headers=h,
    )
    assert patch.status_code == 200, patch.text
    # Only https links are accepted.
    bad = client.patch(
        "/api/v1/tenant/settings",
        json={"branding": {"imprint_url": "javascript:alert(1)"}},
        headers=h,
    )
    assert bad.status_code == 422

    branded = client.get("/api/v1/tenant/branding", headers=host_a).json()
    assert branded["branding"]["primary_color"] == "#112233"
    assert branded["branding"]["imprint_url"] == "https://example.test/impressum"
    assert branded["has_logo_light"] is True
    assert branded["has_logo_dark"] is False
    logo = client.get("/api/v1/tenant/branding/logo/light", headers=host_a)
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert logo.content.startswith(b"\x89PNG")
    assert client.get("/api/v1/tenant/branding/logo/dark", headers=host_a).status_code == 404
    # Tenant separation: the other portal host never sees this logo or these colours.
    other = client.get("/api/v1/tenant/branding", headers=host_b).json()
    assert other["branding"]["primary_color"] is None
    assert client.get("/api/v1/tenant/branding/logo/light", headers=host_b).status_code == 404


def test_tenant_policy_forces_email_code(
    client: TestClient, world: World, app_settings: Any
) -> None:
    mworld, tenant_id = world, world.tenant_a
    h = bearer(login(client, mworld, "bradmin"))
    _account_id, _email = _activated_account(client, h, mworld, f"Policy 2FA {RUN}")
    account_id = uuid.UUID(_account_id)

    async def consume() -> str:
        factory, engine = _factory(app_settings)
        redis = Redis.from_url(app_settings.redis_url.get_secret_value())
        try:
            secret = tokens.new_opaque_secret()
            await _insert_link(
                factory,
                tenant_id=tenant_id,
                account_id=account_id,
                secret=secret,
                expires_at=datetime.now(UTC) + timedelta(minutes=15),
            )
            result = await magic_link.consume_link(
                factory,
                app_settings,
                redis,
                token=f"{tenant_id.hex}.{secret}",
                user_agent=None,
                portal_url=None,
            )
            return result.status
        finally:
            await redis.aclose()
            await engine.dispose()

    # Default (account_choice): the account has no own second factor, session right away.
    assert asyncio.run(consume()) == "ok"
    set_policy = client.patch(
        "/api/v1/tenant/settings", json={"portal_second_factor": "required"}, headers=h
    )
    assert set_policy.status_code == 200, set_policy.text
    try:
        assert asyncio.run(consume()) == "code_required"
    finally:
        client.patch(
            "/api/v1/tenant/settings", json={"portal_second_factor": "account_choice"}, headers=h
        )
    assert asyncio.run(consume()) == "ok"
