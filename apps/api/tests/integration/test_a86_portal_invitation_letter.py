"""A86 (M21-01, M21-08): the printed invitation to the customer portal,
POST /portal-admin/accounts/{id}/invitation-letter (contacts:update).

The letter is a PDF on the tenant letterhead with a new invitation code (the POST rotates the
code, the code handed out before stops working), valid QR_INVITE_DAYS (90) days, and with a
public portal address the invitation link as text and as QR image. Without a portal address
the letter carries the code only and no QR block. Tenant separation by RLS: a foreign account
is not found."""

import asyncio
import io
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _ok

pytestmark = pytest.mark.integration
PA = "/api/v1/portal-admin"
P = "/api/v1/portal"
PORTAL_URL = "https://portal.example.test/"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pla-{RUN}", name=f"Brief A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"plb-{RUN}", name=f"Brief B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("a86ladmin", a, "tenant_admin"),
            ("a86lreader", a, "read_only"),
            ("a86lother", b, "tenant_admin"),
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


def _client(database: Database, redis_url: str, portal_url: str | None) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url).model_copy(update={"web_portal_url": portal_url})
        with TestClient(create_app(settings)) as test_client:
            yield test_client


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    yield from _client(database, redis_url, PORTAL_URL)


@pytest.fixture
def plain_client(database: Database, redis_url: str) -> Iterator[TestClient]:
    """Client without a public portal address: the letter has no link and no QR block."""
    yield from _client(database, redis_url, None)


def _account(client: TestClient, h: dict[str, str], world: World, name: str) -> dict[str, Any]:
    party, _ = _party(client, h, f"Brief{name}")
    contact = _contact_of(client, h, party)
    created = _ok(
        client.post(
            f"{PA}/accounts",
            json={"contact_id": contact, "email": world.email(name), "display_name": name},
            headers=h,
        ),
        201,
    )
    return {**created, "contact_id": contact}


def _page(response: Any) -> Any:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert "einladung-kundenportal.pdf" in response.headers["content-disposition"]
    return PdfReader(io.BytesIO(response.content)).pages[0]


def _has_image(page: Any) -> bool:
    resources = page["/Resources"]
    if "/XObject" not in resources:
        return False
    return any(x.get_object()["/Subtype"] == "/Image" for x in resources["/XObject"].values())


def _token(text: str, world: World) -> str:
    match = re.search(rf"{world.tenant_a.hex}\.[A-Za-z0-9_-]{{43}}", text)
    assert match is not None, text
    return match.group(0)


def test_a86_invitation_letter_rotates_code_and_carries_qr(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "a86ladmin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    account = _account(client, h, world, "a86lres")
    first_token = account["invitation_token"]

    page = _page(client.post(f"{PA}/accounts/{account['id']}/invitation-letter", headers=h))
    assert _has_image(page)
    text = page.extract_text().replace("\n", "").replace(" ", "")
    assert "ZugangzumKundenportal" in text
    assert "https://portal.example.test/einladung?code=" in text
    assert "Einladungslink" in text
    token = _token(text, world)
    assert token != first_token
    assert first_token not in text

    # 90 days validity of the printed code (QR_INVITE_DAYS), visible on the account.
    row = _ok(client.get(f"{PA}/accounts", params={"contact_id": account["contact_id"]}, headers=h))
    expires = datetime.fromisoformat(row[0]["invitation_expires_at"])
    assert timedelta(days=89) < expires - datetime.now(UTC) <= timedelta(days=90)
    assert row[0]["status"] == "invited"

    # The code handed out before the letter no longer works; the printed code does, once.
    old = client.post(f"{P}/invitations/accept", json={"token": first_token, "password": PASSWORD})
    assert old.status_code == 422
    _ok(client.post(f"{P}/invitations/accept", json={"token": token, "password": PASSWORD}))
    again = client.post(f"{P}/invitations/accept", json={"token": token, "password": PASSWORD})
    assert again.status_code == 422


def test_a86_invitation_letter_without_portal_url_has_no_qr(
    plain_client: TestClient, world: World
) -> None:
    client = plain_client
    h = bearer(login(client, world, "a86ladmin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    account = _account(client, h, world, "a86lplain")
    page = _page(client.post(f"{PA}/accounts/{account['id']}/invitation-letter", headers=h))
    assert not _has_image(page)
    text = page.extract_text().replace("\n", "").replace(" ", "")
    assert "einladung?code=" not in text
    assert "Einladungslink" not in text
    _token(text, world)


def test_a86_invitation_letter_permission_tenant_and_validation(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "a86ladmin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    account = _account(client, h, world, "a86lperm")
    url = f"{PA}/accounts/{account['id']}/invitation-letter"

    # Permission: read only role has no contacts:update, no login is 401.
    reader = bearer(login(client, world, "a86lreader"))
    assert client.post(url, headers=reader).status_code == 403
    assert client.post(url).status_code == 401
    # Tenant separation: the other tenant does not find the account.
    other = bearer(login(client, world, "a86lother"))
    assert client.post(url, headers=other).status_code == 404
    # Validation: unknown id 404, malformed id 422, GET is not offered (a prefetch must not
    # rotate the code).
    unknown = f"{PA}/accounts/01920000-0000-7000-8000-000000000001/invitation-letter"
    assert client.post(unknown, headers=h).status_code == 404
    assert client.post(f"{PA}/accounts/x/invitation-letter", headers=h).status_code == 422
    assert client.get(url, headers=h).status_code == 405
    # None of the refused calls rotated the code: the provisioned code still works.
    _ok(
        client.post(
            f"{P}/invitations/accept",
            json={"token": account["invitation_token"], "password": PASSWORD},
        )
    )
