"""A43 `DocumentStore.delete` and A42 Drive inbox listing / Paperless `list_added_since` against
httpx MockTransport (no database)."""

import asyncio
from typing import Any

import httpx
import pytest

from mhvp.documents.dms import DmsError, GoogleDriveStore, PaperlessStore
from mhvp.documents.paperless_search import PaperlessSearch


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _paperless(handler: Any) -> tuple[PaperlessStore, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PaperlessStore("https://dms.example.org", "tok", client), client


def _drive(handler: Any) -> tuple[GoogleDriveStore, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return GoogleDriveStore("root", "cid", "secret", "refresh", client), client


def test_paperless_delete_by_id_and_already_gone() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        assert request.headers["authorization"] == "Token tok"
        if request.url.path == "/api/documents/42/":
            return httpx.Response(204)
        return httpx.Response(404)

    store, client = _paperless(handler)

    async def go() -> None:
        async with client:
            assert await store.delete("42") is True
            assert await store.delete("43") is False
            with pytest.raises(DmsError):
                await store.delete("task:abc")

    _run(go())
    assert calls == ["DELETE /api/documents/42/", "DELETE /api/documents/43/"]


def test_paperless_delete_error_is_reported() -> None:
    store, client = _paperless(lambda _r: httpx.Response(503))

    async def go() -> None:
        async with client:
            with pytest.raises(DmsError, match="delete: HTTP 503"):
                await store.delete("42")

    _run(go())


def test_drive_delete_and_inbox_listing_with_paging() -> None:
    pages = {
        None: {"nextPageToken": "p2", "files": [{"id": "a", "name": "A.pdf", "mimeType": "x"}]},
        "p2": {"files": [{"id": "b", "name": "B.pdf", "mimeType": "y", "modifiedTime": "t2"}]},
    }
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "drive-token"})
        assert request.headers["authorization"] == "Bearer drive-token"
        if request.method == "DELETE":
            return httpx.Response(204 if request.url.path.endswith("/f1") else 404)
        params = dict(request.url.params)
        seen.append(params)
        return httpx.Response(200, json=pages[params.get("pageToken")])

    store, client = _drive(handler)

    async def go() -> None:
        async with client:
            assert await store.delete("f1") is True
            assert await store.delete("f2") is False
            files = await store.list_folder("inbox", modified_after="2026-09-01T00:00:00Z")

        assert [f.ref for f in files] == ["a", "b"]
        assert files[1].modified_at == "t2"
        assert files[0].modified_at == ""
        assert "'inbox' in parents" in seen[0]["q"]
        assert "modifiedTime > '2026-09-01T00:00:00Z'" in seen[0]["q"]
        assert "mimeType != 'application/vnd.google-apps.folder'" in seen[0]["q"]
        assert seen[1]["pageToken"] == "p2"

    _run(go())


def test_paperless_list_added_since_passes_watermark_and_content() -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "count": 1,
                "results": [
                    {"id": 5, "title": "T", "added": "2026-09-02T00:00:00Z", "content": "Text"}
                ],
            },
        )

    async def go() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            search = PaperlessSearch("https://dms.example.org", "tok", client=client)
            page = await search.list_added_since("2026-09-01T00:00:00Z")
            assert page.items[0].content == "Text"
            assert page.items[0].added == "2026-09-02T00:00:00Z"
            page = await search.list_added_since(None)
            assert page.total == 1

    _run(go())
    assert seen[0]["added__gt"] == "2026-09-01T00:00:00Z"
    assert seen[0]["ordering"] == "added"
    assert "added__gt" not in seen[1]
