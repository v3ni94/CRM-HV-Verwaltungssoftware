"""Paperless-Suche (M31): Objekt-/Ticketsuche und Datei-Proxy gegen einen MockTransport."""

from typing import Any

import httpx
import pytest

from mhvp.documents.paperless_search import PaperlessSearch, PaperlessSearchError


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_list_by_object_number_uses_custom_field_query() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = request.url
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [
                    {
                        "id": 42,
                        "title": "Nebenkostenabrechnung",
                        "created": "2026-01-01",
                        "added": "2026-01-02",
                        "correspondent": {"name": "Stadtwerke"},
                        "document_type": {"name": "Abrechnung"},
                        "tags": [{"name": "objekt:602"}],
                        "page_count": 3,
                        "original_file_name": "nk.pdf",
                    }
                ],
            },
        )

    search = PaperlessSearch(
        "https://paperless.example", "sek-ret", client=_client(handler), object_field_id=7
    )
    page = await search.list_by_object_number("602", page=1, page_size=25)
    await search.aclose()

    assert page.total == 1
    assert page.items[0].id == 42
    assert page.items[0].correspondent == "Stadtwerke"
    assert "custom_field_query" in str(seen["url"])
    assert seen["auth"] == "Token sek-ret"
    assert "sek-ret" not in str(seen["url"])


@pytest.mark.asyncio
async def test_list_by_object_number_without_field_id_is_empty() -> None:
    async def unreachable(_: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected without a configured field id")

    search = PaperlessSearch("https://paperless.example", "t", client=_client(unreachable))
    page = await search.list_by_object_number("602")
    await search.aclose()

    assert page.items == []
    assert page.total == 0


@pytest.mark.asyncio
async def test_list_by_ticket_uses_fulltext_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["query"] == "1234"
        return httpx.Response(200, json={"count": 0, "results": []})

    search = PaperlessSearch("https://paperless.example", "t", client=_client(handler))
    page = await search.list_by_ticket(1234)
    await search.aclose()

    assert page.total == 0


@pytest.mark.asyncio
async def test_fetch_file_streams_bytes_and_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/documents/42/preview/")
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})

    search = PaperlessSearch("https://paperless.example", "t", client=_client(handler))
    file = await search.fetch_file(42, "preview")
    await search.aclose()

    assert file.content == b"%PDF-1.4"
    assert file.content_type == "application/pdf"


@pytest.mark.asyncio
async def test_unreachable_paperless_raises_clean_error_without_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    search = PaperlessSearch("https://paperless.example", "geheimes-token", client=_client(handler))
    with pytest.raises(PaperlessSearchError) as exc:
        await search.list_by_ticket("1234")
    await search.aclose()

    assert "geheimes-token" not in str(exc.value)


@pytest.mark.asyncio
async def test_error_status_is_wrapped_without_leaking_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    search = PaperlessSearch("https://paperless.example", "geheimes-token", client=_client(handler))
    with pytest.raises(PaperlessSearchError) as exc:
        await search.fetch_file(1, "download")
    await search.aclose()

    assert "geheimes-token" not in str(exc.value)
