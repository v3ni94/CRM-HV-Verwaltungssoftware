"""PATCH /api/v1/auth/me/preferences (operator 27.09.2026, migration 0182): only the caller's
own ``ui_preferences`` are ever written, keys are validated, ``GET /auth/me`` echoes them back
so the main navigation renders its stored state without a flash."""

import asyncio
import base64
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from mhvp.core import crypto
from mhvp.core.auth import tokens
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.main import create_app
from mhvp.platform import services
from tests.conftest import make_settings
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration
PASSWORD = "correct horse battery staple"
_PEM = tokens.generate_private_key_pem()


def _settings(database: Database, redis_url: str) -> Settings:
    return make_settings(
        database_url=SecretStr(database.app_url),
        redis_url=SecretStr(redis_url),
        master_key=SecretStr(base64.b64encode(b"k" * 32).decode()),
        jwt_private_key=SecretStr(_PEM),
        jwt_issuer="http://testserver",
    )


@pytest.fixture
def client_and_users(
    database: Database, redis_url: str
) -> Iterator[tuple[TestClient, dict[str, str]]]:
    settings = _settings(database, redis_url)

    async def build() -> dict[str, str]:
        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        run = uuid.uuid4().hex[:8]
        try:
            emails = {}
            for name in ("alice", "bob"):
                email = f"{name}-{run}@example.org"
                await services.create_user(
                    factory,
                    email=email,
                    display_name=name,
                    password=PASSWORD,
                    is_platform_admin=False,
                )
                emails[name] = email
            return emails
        finally:
            await engine.dispose()

    emails = asyncio.run(build())
    with TestClient(create_app(settings)) as test_client:
        yield test_client, emails


def _login(client: TestClient, email: str) -> dict[str, str]:
    step = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert step.status_code == 200, step.text
    body = step.json()
    assert body["status"] == "ok"
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_preferences_are_merged_and_returned_by_me(
    client_and_users: tuple[TestClient, dict[str, str]],
) -> None:
    client, emails = client_and_users
    headers = _login(client, emails["alice"])

    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["ui_preferences"] == {}

    patched = client.patch(
        "/api/v1/auth/me/preferences",
        json={"nav_expanded_groups": ["Makler", "System"]},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["ui_preferences"] == {"nav_expanded_groups": ["Makler", "System"]}

    me_again = client.get("/api/v1/auth/me", headers=headers).json()
    assert me_again["ui_preferences"] == {"nav_expanded_groups": ["Makler", "System"]}

    # A second, smaller patch replaces the key (it is not appended to).
    collapsed = client.patch(
        "/api/v1/auth/me/preferences", json={"nav_expanded_groups": []}, headers=headers
    )
    assert collapsed.status_code == 200, collapsed.text
    assert collapsed.json()["ui_preferences"] == {"nav_expanded_groups": []}


def test_unknown_preference_key_is_rejected(
    client_and_users: tuple[TestClient, dict[str, str]],
) -> None:
    client, emails = client_and_users
    headers = _login(client, emails["alice"])
    response = client.patch(
        "/api/v1/auth/me/preferences", json={"favorite_color": "gold"}, headers=headers
    )
    assert response.status_code == 422, response.text


def test_a_user_can_never_change_another_users_preferences(
    client_and_users: tuple[TestClient, dict[str, str]],
) -> None:
    client, emails = client_and_users
    alice_headers = _login(client, emails["alice"])
    bob_headers = _login(client, emails["bob"])

    client.patch(
        "/api/v1/auth/me/preferences",
        json={"nav_expanded_groups": ["Makler"]},
        headers=alice_headers,
    )
    bob_me = client.get("/api/v1/auth/me", headers=bob_headers).json()
    assert bob_me["ui_preferences"] == {}

    # There is no endpoint that names another user's id; PATCH always targets the bearer's own
    # principal, so tenant separation is not applicable here (platform level table).
    unauthenticated = client.patch(
        "/api/v1/auth/me/preferences", json={"nav_expanded_groups": ["Makler"]}
    )
    assert unauthenticated.status_code in (401, 403)
