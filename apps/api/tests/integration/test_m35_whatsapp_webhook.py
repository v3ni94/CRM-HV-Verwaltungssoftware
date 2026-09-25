"""M35: Meta Cloud API webhook (/api/v1/whatsapp/webhook) - GET verification and signed POST
status updates."""

import base64
import hashlib
import hmac
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from mhvp.core.auth import tokens
from mhvp.main import create_app
from tests.conftest import make_settings
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration

_PEM = tokens.generate_private_key_pem()


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = make_settings(
        database_url=SecretStr(database.app_url),
        redis_url=SecretStr(redis_url),
        master_key=SecretStr(base64.b64encode(b"k" * 32).decode()),
        jwt_private_key=SecretStr(_PEM),
        jwt_issuer="http://testserver",
        webhook_allow_private_targets=True,
        whatsapp_verify_token=SecretStr("verify-me-m35"),
        whatsapp_app_secret=SecretStr("app-secret-m35"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_webhook_verify_accepts_matching_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-me-m35",
            "hub.challenge": "1234",
        },
    )
    assert response.status_code == 200
    assert response.text == "1234"


def test_webhook_verify_rejects_wrong_token(client: TestClient) -> None:
    response = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "1234",
        },
    )
    assert response.status_code == 403


def test_webhook_status_update_requires_valid_signature(client: TestClient) -> None:
    body = json.dumps(
        {
            "entry": [
                {
                    "changes": [
                        {"value": {"statuses": [{"id": "wamid.unknown", "status": "delivered"}]}}
                    ]
                }
            ]
        }
    ).encode()

    unsigned = client.post(
        "/api/v1/whatsapp/webhook", content=body, headers={"Content-Type": "application/json"}
    )
    assert unsigned.status_code == 200
    assert unsigned.json() == {"status": "ignored"}

    sig = "sha256=" + hmac.new(b"app-secret-m35", body, hashlib.sha256).hexdigest()
    signed = client.post(
        "/api/v1/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )
    assert signed.status_code == 200
    assert signed.json() == {"status": "ok"}

    tampered_sig = "sha256=" + "0" * 64
    tampered = client.post(
        "/api/v1/whatsapp/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": tampered_sig},
    )
    assert tampered.status_code == 200
    assert tampered.json() == {"status": "ignored"}
