"""M29 Stufe 4: objektakte client (fake answers via httpx.MockTransport, never a real call),
webhook signature and the pure helpers of the document linkage."""

import asyncio
import hashlib
import hmac
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from mhvp.objektakte.dms_service import _name_key, _norm_label, normalize_number, parse_document
from mhvp.objektakte.remote import (
    ObjektakteClient,
    ObjektakteNotFoundError,
    ObjektakteUnavailableError,
)
from mhvp.objektakte.webhook import sign, verify
from tests.conftest import make_settings

BASE = "https://oa.example.test/api/crm/v1"


def _client(handler: Any) -> ObjektakteClient:
    return ObjektakteClient(BASE, "tok", timeout=1.0, transport=httpx.MockTransport(handler))


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_pagination_reads_all_pages_with_bearer_token() -> None:
    rows = [{"number": str(n)} for n in range(1, 1203)]
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tok"
        assert request.url.path == "/api/crm/v1/objects/"
        page = int(request.url.params["page"])
        size = int(request.url.params["page_size"])
        seen.append((request.url.params["page"], request.url.params["page_size"]))
        chunk = rows[(page - 1) * size : page * size]
        return httpx.Response(
            200, json={"count": len(rows), "page": page, "page_size": size, "results": chunk}
        )

    async def go() -> list[dict[str, Any]]:
        async with _client(handler) as client:
            return await client.objects()

    result = _run(go())
    assert len(result) == 1202
    assert seen == [("1", "500"), ("2", "500"), ("3", "500")]


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(404, json={}), ObjektakteNotFoundError),
        (httpx.Response(401, json={}), ObjektakteUnavailableError),
        (httpx.Response(403, json={}), ObjektakteUnavailableError),
        (httpx.Response(500, text="boom tok"), ObjektakteUnavailableError),
        (httpx.Response(200, text="<html>"), ObjektakteUnavailableError),
    ],
)
def test_errors_are_mapped_without_token_or_body(
    response: httpx.Response, error: type[Exception]
) -> None:
    async def go() -> None:
        async with _client(lambda _r: response) as client:
            await client.object("523")

    with pytest.raises(error) as info:
        _run(go())
    assert "tok" not in str(info.value)
    assert "boom" not in str(info.value)


def test_timeout_and_connection_errors_are_unavailable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    for handler in (timeout, refused):

        async def go(h: Any = handler) -> None:
            async with _client(h) as client:
                await client.documents("523")

        with pytest.raises(ObjektakteUnavailableError):
            _run(go())


def test_documents_passes_filters_and_caps_page_size() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/crm/v1/objects/523/documents/"
        assert request.url.params["folder"] == "02_Stammakte"
        assert request.url.params["page_size"] == "500"
        assert "since" not in request.url.params
        return httpx.Response(200, json={"count": 0, "page": 1, "page_size": 500, "results": []})

    async def go() -> dict[str, Any]:
        async with _client(handler) as client:
            return await client.documents("523", page_size=9999, folder="02_Stammakte")

    assert _run(go())["results"] == []


def test_invalid_object_number_never_reaches_objektakte() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not be called")

    async def go() -> None:
        async with _client(handler) as client:
            await client.owners("../admin")

    with pytest.raises(ObjektakteNotFoundError):
        _run(go())


def test_from_settings_is_off_while_url_or_token_is_empty() -> None:
    assert make_settings().objektakte_api_configured is False
    assert make_settings(objektakte_api_url=BASE).objektakte_api_configured is False
    assert (
        make_settings(objektakte_api_url=BASE, objektakte_api_token=SecretStr(" "))
    ).objektakte_api_configured is False
    on = make_settings(objektakte_api_url=BASE, objektakte_api_token=SecretStr("t"))
    assert on.objektakte_api_configured is True
    with pytest.raises(ObjektakteUnavailableError):
        ObjektakteClient.from_settings(make_settings())


def test_settings_accept_the_contract_variable_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OBJEKTAKTE_API_URL", BASE)
    monkeypatch.setenv("OBJEKTAKTE_API_TOKEN", "t")
    monkeypatch.setenv("OBJEKTAKTE_WEBHOOK_SECRET", "s")
    monkeypatch.setenv("OBJEKTAKTE_TENANT", "hausverwaltung-mueller")
    settings = make_settings()
    assert settings.objektakte_api_configured is True
    assert settings.objektakte_webhook_secret is not None
    assert settings.objektakte_webhook_secret.get_secret_value() == "s"
    assert settings.objektakte_tenant == "hausverwaltung-mueller"


def test_signature_matches_the_contract() -> None:
    body = b'{"event":"document.filed","object_number":"523"}'
    expected = "sha256=" + hmac.new(b"geheim", body, hashlib.sha256).hexdigest()
    assert sign("geheim", body) == expected
    assert verify("geheim", expected, body)
    assert not verify("geheim", expected, body + b" ")
    assert not verify("geheim", expected.removeprefix("sha256="), body)
    assert not verify("", sign("", body), body)
    assert not verify("geheim", None, body)


def test_number_label_and_name_normalisation() -> None:
    assert normalize_number("523") == "523"
    assert normalize_number("82") == "082"
    assert normalize_number("0623") == "623"
    assert normalize_number("1000") is None
    assert normalize_number("0") is None
    assert normalize_number("A1") is None
    assert _norm_label("WE 01") == "we01"
    assert _norm_label("01") == _norm_label("1") == "1"
    assert _name_key("Müller, Anna") == _name_key("anna  müller")


def test_parse_document_validates_required_fields() -> None:
    raw = {"id": 7, "title": " Plan ", "sha256": "A" * 64, "drive_file_id": "d7", "size_bytes": 3}
    doc = parse_document(raw)
    assert (doc.id, doc.title, doc.sha256, doc.drive_file_id) == (7, "Plan", "a" * 64, "d7")
    for broken in (
        None,
        {**raw, "id": 0},
        {**raw, "id": True},
        {**raw, "sha256": "xyz"},
        {**raw, "size_bytes": -1},
        {**raw, "title": 5},
    ):
        with pytest.raises(ValueError, match=r"\w"):
            parse_document(broken)
