"""GA10-04: the DocumentStore protocol (get, search, list_changes) across Paperless, Drive and
MinIO adapter (httpx MockTransport and a stub blob store, no network, no database)."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest

from mhvp.documents.dms import (
    DmsError,
    DocumentStore,
    GoogleDriveStore,
    MinioStore,
    MirrorMeta,
    PaperlessStore,
)


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_paperless_get_search_and_changes() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path == "/api/documents/7/download/":
            return httpx.Response(200, content=b"PDF")
        if request.url.path == "/api/documents/8/download/":
            return httpx.Response(404)
        params = dict(request.url.params)
        if "modified__gt" in params:
            return httpx.Response(
                200, json={"results": [{"id": 9, "title": "N", "modified": "2026-10-01T10:00:00Z"}]}
            )
        return httpx.Response(200, json={"results": [{"id": 7, "title": "Rechnung"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    store: DocumentStore = PaperlessStore("https://dms.example.org", "tok", client)

    async def go() -> None:
        async with client:
            assert await store.get("7") == b"PDF"
            with pytest.raises(DmsError):
                await store.get("8")
            with pytest.raises(DmsError):
                await store.get("task:abc")
            hits = await store.search("602", ["Rechnung"])
            assert [h.ref for h in hits] == ["7"]
            none, cursor = await store.list_changes(None)
            assert none == []
            assert cursor
            changes, latest = await store.list_changes("2026-09-30T00:00:00Z")
            assert [c.file_id for c in changes] == ["9"]
            assert latest == "2026-10-01T10:00:00Z"

    _run(go())
    assert any("tags__name__iexact=objekt%3A602" in u for u in seen)


def test_drive_get_and_cursor_start() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "t"})
        if request.url.path.endswith("/startPageToken"):
            return httpx.Response(200, json={"startPageToken": "42"})
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=b"DRIVE")
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    store: DocumentStore = GoogleDriveStore("root", "cid", "secret", "refresh", client)

    async def go() -> None:
        async with client:
            assert await store.get("f1") == b"DRIVE"
            assert await store.list_changes(None) == ([], "42")

    _run(go())


class _Blobs:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    @staticmethod
    def key(tenant_id: uuid.UUID, document_id: uuid.UUID) -> str:
        return f"tenants/{tenant_id}/documents/{document_id}"

    def put(self, key: str, data: bytes, mime_type: str, sha256: str) -> None:
        self.data[key] = data

    def get(self, key: str) -> bytes:
        return self.data[key]

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


def test_minio_store_is_a_document_store() -> None:
    blobs = _Blobs()
    store: DocumentStore = MinioStore(blobs, uuid.uuid4())  # type: ignore[arg-type]
    meta = MirrorMeta(
        document_id=uuid.uuid4(),
        title="t",
        filename="t.pdf",
        mime_type="application/pdf",
        tenant_slug="x",
    )

    async def go() -> None:
        result = await store.put(b"abc", meta)
        assert result.final
        assert await store.resolve(result.ref) == result.ref
        assert await store.get(result.ref) == b"abc"
        assert await store.update_meta(result.ref, meta) is True
        assert await store.search("602", ["x"]) == []
        assert await store.list_changes("c") == ([], "c")
        assert await store.delete(result.ref) is True
        with pytest.raises(DmsError):
            await store.get(result.ref)

    _run(go())


def test_followup_detection_without_database() -> None:
    from types import SimpleNamespace

    from mhvp.documents.intake_followup import suggest

    async def kinds(
        title: str, mime: str, category: str | None, final: dict[str, Any]
    ) -> list[str]:
        doc: Any = SimpleNamespace(title=title, filename=title, mime_type=mime, id=uuid.uuid4())
        items = await suggest(None, doc, category_name=category, text="", final=final)  # type: ignore[arg-type]
        assert all(i["status"] == "proposed" for i in items)
        return [i["kind"] for i in items]

    assert _run(kinds("Rechnung 4711.pdf", "application/pdf", None, {})) == ["invoice"]
    assert _run(kinds("Wasserschaden Keller.jpg", "image/jpeg", None, {})) == ["ticket_new"]
    assert _run(kinds("Mietvertrag.pdf", "application/pdf", None, {"contract_id": "c1"})) == [
        "contract_file"
    ]
    assert _run(kinds("Protokoll Eigentümerversammlung.pdf", "application/pdf", None, {})) == [
        "meeting"
    ]
    assert _run(kinds("Foto.jpg", "image/jpeg", None, {})) == []
