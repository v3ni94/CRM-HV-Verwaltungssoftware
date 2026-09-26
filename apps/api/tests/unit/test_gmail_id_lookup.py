"""Unit-Test: GmailClient.find_by_header_id (Nachtrag fehlender Gmail-Kennungen, 26.09.2026)."""

import httpx
import pytest

from mhvp.communication.gmail import GmailClient, GmailError


def _client(handler: httpx.MockTransport) -> GmailClient:
    return GmailClient("client-id", "client-secret", "refresh-token", transport=handler)


def _handler(status: int, payload: dict) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "token-1"})
        assert request.url.params["q"] == "rfc822msgid:<abc@example.org>"
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handle)


@pytest.mark.asyncio
async def test_find_by_header_id_returns_gmail_id() -> None:
    client = _client(_handler(200, {"messages": [{"id": "18f1", "threadId": "t"}]}))
    assert await client.find_by_header_id("<abc@example.org>") == "18f1"


@pytest.mark.asyncio
async def test_find_by_header_id_none_when_missing() -> None:
    client = _client(_handler(200, {"resultSizeEstimate": 0}))
    assert await client.find_by_header_id("<abc@example.org>") is None


@pytest.mark.asyncio
async def test_find_by_header_id_raises_on_http_error() -> None:
    client = _client(_handler(500, {}))
    with pytest.raises(GmailError):
        await client.find_by_header_id("<abc@example.org>")
