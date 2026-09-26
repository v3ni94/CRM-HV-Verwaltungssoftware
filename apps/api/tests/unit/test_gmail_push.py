"""Unit tests of the Gmail push building blocks (operator 26.09.2026): Pub/Sub envelope
parsing, optional OIDC verification against a local key set, watch renewal timing with time
travel, and the new GmailClient calls (watch, label total, paginated inbox) against a fake
transport. No network."""

import base64
import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from mhvp.communication import gmail
from mhvp.communication.gmail_push import parse_envelope, verify_oidc
from mhvp.communication.models import Mailbox


def _envelope(payload: Any, *, raw_data: str | None = None) -> bytes:
    data = raw_data if raw_data is not None else base64.b64encode(json.dumps(payload).encode())
    if isinstance(data, bytes):
        data = data.decode()
    return json.dumps(
        {"message": {"data": data, "messageId": "1", "publishTime": "2026-09-26T10:00:00Z"}}
    ).encode()


def test_parse_envelope_accepts_gmail_payload() -> None:
    raw = _envelope({"emailAddress": "Info@Example.com", "historyId": 12345})
    assert parse_envelope(raw) == ("info@example.com", "12345")
    # historyId may arrive as a string; unpadded base64 (URL safe style) is tolerated.
    data = base64.b64encode(b'{"emailAddress":"a@b.de","historyId":"77"}').decode().rstrip("=")
    assert parse_envelope(_envelope(None, raw_data=data)) == ("a@b.de", "77")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b"[]",
        b'{"message": "x"}',
        b'{"message": {}}',
        _envelope(None, raw_data="%%%"),
        _envelope(None, raw_data=base64.b64encode(b"[1,2]").decode()),
        _envelope({"historyId": 1}),
        _envelope({"emailAddress": "nomail", "historyId": 1}),
        _envelope({"emailAddress": "a@b.de"}),
        _envelope({"emailAddress": "a@b.de", "historyId": True}),
        _envelope({"emailAddress": "a@b.de", "historyId": "abc"}),
    ],
)
def test_parse_envelope_rejects_malformed(raw: bytes) -> None:
    with pytest.raises(ValueError, match=r"Pub/Sub|Gmail|emailAddress|historyId"):
        parse_envelope(raw)


def _rsa_jwks() -> tuple[Any, Any]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update(kid="k1", use="sig", alg="RS256")
    return private, (jwt.PyJWKSet.from_dict({"keys": [jwk]}), public_pem)


def test_verify_oidc_accepts_google_token_for_audience() -> None:
    private, (jwks, _) = _rsa_jwks()
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://crm.example.org/api/v1/integrations/gmail/push",
        "exp": now + 300,
        "iat": now,
        "email": "push@project.iam.gserviceaccount.com",
    }
    token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "k1"})
    out = verify_oidc(token, claims["aud"], jwks)  # type: ignore[arg-type]
    assert out["email"] == "push@project.iam.gserviceaccount.com"
    with pytest.raises(ValueError, match="OIDC"):
        verify_oidc(token, "https://other.example.org/", jwks)
    other = jwt.encode({**claims, "iss": "https://evil.example"}, private, "RS256", {"kid": "k1"})
    with pytest.raises(ValueError, match="Aussteller"):
        verify_oidc(other, claims["aud"], jwks)  # type: ignore[arg-type]
    expired = jwt.encode({**claims, "exp": now - 10}, private, "RS256", {"kid": "k1"})
    with pytest.raises(ValueError, match="OIDC"):
        verify_oidc(expired, claims["aud"], jwks)  # type: ignore[arg-type]
    no_kid = jwt.encode(claims, private, algorithm="RS256")
    with pytest.raises(ValueError, match="OIDC"):
        verify_oidc(no_kid, claims["aud"], jwks)  # type: ignore[arg-type]


def _mailbox(expiration: datetime | None) -> Mailbox:
    box = Mailbox(tenant_id=uuid.uuid4(), address="x@example.com", kind="gmail", enabled=True)
    box.gmail_watch_expiration = expiration
    return box


def test_watch_due_with_time_travel() -> None:
    now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    assert gmail.watch_due(_mailbox(None), now) is True
    seven_days = _mailbox(now + timedelta(days=7))
    assert gmail.watch_due(seven_days, now) is False
    assert gmail.watch_due(seven_days, now + timedelta(days=5, hours=23)) is False
    assert gmail.watch_due(seven_days, now + timedelta(days=6)) is True  # margin of one day
    assert gmail.watch_due(seven_days, now + timedelta(days=8)) is True  # already expired


def _client(handler: Any) -> gmail.GmailClient:
    return gmail.GmailClient("cid", "secret", "refresh", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_client_watch_label_total_and_pages() -> None:
    calls: list[dict[str, Any]] = []
    expiration_ms = int(datetime(2026, 10, 3, 12, 0, tzinfo=UTC).timestamp() * 1000)

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t"})
        assert request.headers["Authorization"] == "Bearer t"
        if path.endswith("/watch"):
            calls.append(json.loads(request.content))
            return httpx.Response(200, json={"historyId": "999", "expiration": expiration_ms})
        if path.endswith("/labels/INBOX"):
            return httpx.Response(200, json={"id": "INBOX", "messagesTotal": 123})
        if path.endswith("/messages"):
            calls.append(dict(request.url.params))
            if request.url.params.get("pageToken") == "p2":
                return httpx.Response(200, json={"messages": [{"id": "c"}]})
            return httpx.Response(
                200, json={"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "p2"}
            )
        return httpx.Response(404)

    client = _client(handle)
    try:
        history, expiration = await client.watch("projects/p/topics/t")
        assert (history, expiration) == ("999", datetime(2026, 10, 3, 12, 0, tzinfo=UTC))
        assert calls[0] == {
            "topicName": "projects/p/topics/t",
            "labelIds": ["INBOX"],
            "labelFilterBehavior": "INCLUDE",
        }
        assert await client.label_total() == 123
        assert await client.list_inbox_page(None, 2) == (["a", "b"], "p2")
        assert await client.list_inbox_page("p2", 2) == (["c"], None)
        assert calls[1] == {"labelIds": "INBOX", "maxResults": "2"}
        assert calls[2]["pageToken"] == "p2"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_register_watch_stores_expiration_and_keeps_cursor() -> None:
    from pydantic import SecretStr

    from mhvp.core.config import Settings

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path.endswith("/watch"):
            expiration = int((datetime.now(UTC) + timedelta(days=7)).timestamp() * 1000)
            return httpx.Response(200, json={"historyId": "555", "expiration": expiration})
        return httpx.Response(500)

    settings = Settings(
        database_url=SecretStr("postgresql+psycopg://x"),
        redis_url=SecretStr("redis://x"),
        celery_broker_url=SecretStr("redis://x"),
        gmail_pubsub_topic="projects/p/topics/t",
        gmail_push_token=SecretStr("s"),
    )
    box = _mailbox(None)
    box.gmail_history_id = "100"
    client = _client(handle)
    try:
        assert await gmail.ensure_watch(settings, box, client) is True
        assert box.gmail_watch_history_id == "555"
        assert box.gmail_history_id == "100"
        assert box.gmail_watch_expiration is not None
        assert await gmail.ensure_watch(settings, box, client) is False  # not due
        # Without a topic nothing is called.
        off = settings.model_copy(update={"gmail_pubsub_topic": None})
        assert await gmail.ensure_watch(off, _mailbox(None), client) is False
    finally:
        await client.aclose()
