"""GAG-35: endpoint test of GET /oidc/userinfo (section 3.4, OIDC provider).

Covers token handling (missing, malformed and foreign-signature bearer are refused), the
claims of an authenticated user (``sub`` is the user id, ``email`` and ``name`` come from the
platform user, ``tenant_id`` is the tenant of the session), the tenant claim after a tenant
switch of a user with two memberships, and that an access token issued by the OIDC token
endpoint itself (public client, PKCE) reads the same claims as a CRM session token.
No claims beyond sub, email, name and tenant_id are returned (data minimisation, rule 0.1.13).
"""

import base64
import hashlib
import io
import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mhvp.core.auth import oidc_clients
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
RUN = uuid.uuid4().hex[:8]
URL = "/api/v1/oidc/userinfo"
CALLBACK = "https://tool.example.org/callback"


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = base_settings(database, redis_url, web_crm_url="https://crm.example.org")
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def cleanup(migrator_engine: Engine) -> Iterator[None]:
    yield
    with migrator_engine.begin() as conn:
        conn.execute(
            text("DELETE FROM oidc_authorization_code WHERE client_id LIKE :p"),
            {"p": f"ah21-{RUN}%"},
        )
        conn.execute(text("DELETE FROM oidc_client WHERE client_id LIKE :p"), {"p": f"ah21-{RUN}%"})


def test_userinfo_requires_a_valid_bearer(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    # a token signed with another key is refused like a missing one
    parts = ["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiJ4In0", "c2lnbmF0dXJl"]
    forged = {"Authorization": f"Bearer {'.'.join(parts)}"}
    assert client.get(URL, headers=forged).status_code == 401


def test_userinfo_returns_only_the_documented_claims(client: TestClient, world: World) -> None:
    issued = login(client, world, "admin")
    response = client.get(URL, headers=bearer(issued))
    assert response.status_code == 200, response.text
    claims = response.json()
    assert set(claims) == {"sub", "email", "name", "tenant_id"}
    assert claims["sub"] == str(world.users["admin"])
    assert claims["email"] == world.email("admin")
    assert claims["name"] == "admin"
    assert claims["tenant_id"] == str(world.tenant_a)
    # a read only member sees the same shape, the endpoint is not permission scoped
    reader = client.get(URL, headers=bearer(login(client, world, "reader")))
    assert reader.status_code == 200, reader.text
    assert reader.json()["sub"] == str(world.users["reader"])


def test_userinfo_tenant_claim_follows_the_session_tenant(client: TestClient, world: World) -> None:
    in_a = login(client, world, "both", tenant_id=world.tenant_a)
    assert client.get(URL, headers=bearer(in_a)).json()["tenant_id"] == str(world.tenant_a)
    in_b = login(client, world, "both", tenant_id=world.tenant_b)
    assert client.get(URL, headers=bearer(in_b)).json()["tenant_id"] == str(world.tenant_b)
    # a platform administrator without membership has no tenant claim
    padmin = login(client, world, "padmin")
    claims = client.get(URL, headers=bearer(padmin)).json()
    assert claims["sub"] == str(world.users["padmin"])
    assert claims["tenant_id"] is None


def test_userinfo_accepts_tokens_issued_by_the_oidc_token_endpoint(
    client: TestClient, world: World, database: Database, redis_url: str, cleanup: None
) -> None:
    client_id = f"ah21-{RUN}"
    out = io.StringIO()
    import asyncio

    code = asyncio.run(
        oidc_clients.run(
            [
                "create",
                "--client-id",
                client_id,
                "--name",
                "Werkzeug",
                "--redirect-uri",
                CALLBACK,
                "--public",
            ],
            settings=base_settings(database, redis_url),
            out=out,
        )
    )
    assert code == 0, out.getvalue()
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    headers = bearer(login(client, world, "admin"))
    redirect = client.get(
        "/api/v1/oidc/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CALLBACK,
            "scope": "openid email profile",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert redirect.status_code == 302, redirect.text
    grant = redirect.headers["location"].split("code=")[1].split("&")[0]
    issued = client.post(
        "/api/v1/oidc/token",
        data={
            "grant_type": "authorization_code",
            "code": grant,
            "redirect_uri": CALLBACK,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    assert issued.status_code == 200, issued.text
    claims: dict[str, Any] = client.get(URL, headers=bearer(issued.json())).json()
    assert claims["sub"] == str(world.users["admin"])
    assert claims["email"] == world.email("admin")
    assert claims["tenant_id"] == str(world.tenant_a)
