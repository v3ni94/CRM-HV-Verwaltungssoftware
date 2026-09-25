"""M30: operator registration of OIDC relying parties and the confidential client flow."""

import base64
import hashlib
import io
import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mhvp.core.auth import oidc_clients
from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    RUN,
    World,
    bearer,
    login,
)
from tests.integration.test_m2_platform import _settings as base_settings

CALLBACK = "https://status.example.org/oauth2/callback"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _run(database: Database, redis_url: str, *argv: str) -> tuple[int, str]:
    import asyncio

    out = io.StringIO()
    settings = base_settings(database, redis_url, web_crm_url="https://crm.example.org")
    code = asyncio.run(oidc_clients.run(list(argv), settings=settings, out=out))
    return code, out.getvalue()


def _secret(output: str) -> str:
    line = next(line for line in output.splitlines() if line.startswith("client_secret: "))
    return line.removeprefix("client_secret: ")


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
            {"p": f"m30-{RUN}%"},
        )
        conn.execute(text("DELETE FROM oidc_client WHERE client_id LIKE :p"), {"p": f"m30-{RUN}%"})


def _authorize(client: TestClient, headers: dict[str, str], client_id: str, verifier: str) -> Any:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CALLBACK,
        "scope": "openid email profile",
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        "state": "s-1",
    }
    return client.get(
        "/api/v1/oidc/authorize", params=params, headers=headers, follow_redirects=False
    )


def test_cli_registers_confidential_client_for_the_code_flow(
    client: TestClient,
    world: World,
    database: Database,
    redis_url: str,
    cleanup: None,
) -> None:
    client_id = f"m30-{RUN}-status"
    code, output = _run(
        database,
        redis_url,
        "create",
        "--client-id",
        client_id,
        "--name",
        "Statusseite",
        "--redirect-uri",
        CALLBACK,
    )
    assert code == 0, output
    secret = _secret(output)
    assert len(secret) >= 32

    code, listing = _run(database, redis_url, "list")
    assert code == 0
    row = next(line for line in listing.splitlines() if line.startswith(client_id))
    assert row.split("\t")[1:4] == ["active", "confidential", "Statusseite"]

    # duplicate registration is refused and does not touch the existing client
    code, _ = _run(
        database,
        redis_url,
        "create",
        "--client-id",
        client_id,
        "--name",
        "x",
        "--redirect-uri",
        CALLBACK,
    )
    assert code == 1

    # discovery sends browsers to the CRM bridge
    discovery = client.get("/.well-known/openid-configuration").json()
    assert discovery["authorization_endpoint"] == "https://crm.example.org/oidc/authorize"

    headers = bearer(login(client, world, "admin"))
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    redirect = _authorize(client, headers, client_id, verifier)
    assert redirect.status_code == 302, redirect.text
    location = redirect.headers["location"]
    assert location.startswith(f"{CALLBACK}?")
    grant = location.split("code=")[1].split("&")[0]
    form = {
        "grant_type": "authorization_code",
        "code": grant,
        "redirect_uri": CALLBACK,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    # a confidential client must present its secret
    assert client.post("/api/v1/oidc/token", data=form).status_code == 400
    assert (
        client.post("/api/v1/oidc/token", data=form | {"client_secret": "wrong"}).status_code == 400
    )
    issued = client.post("/api/v1/oidc/token", data=form | {"client_secret": secret})
    assert issued.status_code == 200, issued.text
    assert issued.json()["id_token"]

    # rotation invalidates the old secret at once (client authentication precedes code use)
    code, rotated = _run(database, redis_url, "rotate-secret", "--client-id", client_id)
    assert code == 0
    new_secret = _secret(rotated)
    assert new_secret != secret
    verifier = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b"=").decode()
    location = _authorize(client, headers, client_id, verifier).headers["location"]
    form["code"] = location.split("code=")[1].split("&")[0]
    form["code_verifier"] = verifier
    assert (
        client.post("/api/v1/oidc/token", data=form | {"client_secret": secret}).status_code == 400
    )
    assert (
        client.post("/api/v1/oidc/token", data=form | {"client_secret": new_secret}).status_code
        == 200
    )

    # deactivation stops new authorizations at once
    code, _ = _run(database, redis_url, "deactivate", "--client-id", client_id)
    assert code == 0
    assert _authorize(client, headers, client_id, verifier).status_code == 400
    code, _ = _run(database, redis_url, "activate", "--client-id", client_id)
    assert code == 0
    assert _authorize(client, headers, client_id, verifier).status_code == 302


def test_cli_public_client_has_no_secret(database: Database, redis_url: str, cleanup: None) -> None:
    client_id = f"m30-{RUN}-public"
    code, output = _run(
        database,
        redis_url,
        "create",
        "--client-id",
        client_id,
        "--name",
        "Browser-App",
        "--redirect-uri",
        "https://app.example.org/cb",
        "--public",
    )
    assert code == 0, output
    assert "client_secret: (public client, PKCE only)" in output
    code, _ = _run(database, redis_url, "rotate-secret", "--client-id", client_id)
    assert code == 1
    code, _ = _run(
        database,
        redis_url,
        "create",
        "--client-id",
        f"{client_id}-bad",
        "--name",
        "x",
        "--redirect-uri",
        "http://app.example.org/cb",
    )
    assert code == 1
