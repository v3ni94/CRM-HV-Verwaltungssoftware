"""Unit-Test: GmailClient.archive (M20-03 "Erledigt archiviert Mail", operator 25.09.2026)
gegen ein simuliertes Gmail-API-Transport, ohne Netzwerk oder Datenbank."""

import httpx
import pytest

from mhvp.communication.gmail import GmailClient, GmailError, GmailScopeMissingError


def _client(handler: httpx.MockTransport) -> GmailClient:
    return GmailClient("client-id", "client-secret", "refresh-token", transport=handler)


def _token_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"access_token": "token-1"})


async def test_archive_removes_inbox_label_on_success() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "token" in str(request.url):
            return _token_response(request)
        calls.append(request)
        assert request.url.path.endswith("/messages/msg-1/modify")
        return httpx.Response(200, json={"id": "msg-1", "labelIds": []})

    client = _client(httpx.MockTransport(handler))
    try:
        await client.archive("msg-1")
    finally:
        await client.aclose()
    assert len(calls) == 1


async def test_archive_missing_scope_raises_scope_missing_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "token" in str(request.url):
            return _token_response(request)
        return httpx.Response(403, json={"error": "insufficient scope"})

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(GmailScopeMissingError):
            await client.archive("msg-1")
    finally:
        await client.aclose()


async def test_archive_already_gone_is_a_no_op() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "token" in str(request.url):
            return _token_response(request)
        return httpx.Response(404)

    client = _client(httpx.MockTransport(handler))
    try:
        await client.archive("msg-missing")  # does not raise
    finally:
        await client.aclose()


async def test_archive_other_error_raises_gmail_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "token" in str(request.url):
            return _token_response(request)
        return httpx.Response(500)

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(GmailError):
            await client.archive("msg-1")
    finally:
        await client.aclose()
