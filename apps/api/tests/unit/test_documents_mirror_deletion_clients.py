"""DMS client steps of the mirror deletion (M6-03, operator decision 26.09.2026) against a
MockTransport, no network: Paperless ``add_tag`` (tag "gelöscht" created when missing,
assigned once, document kept) and Drive ``trash`` as fallback to the permanent ``delete``."""

import json
from collections.abc import Callable

import httpx
import pytest

from mhvp.documents.dms import DmsError, GoogleDriveStore, PaperlessStore

BASE = "https://dms.example.org"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class FakePaperless:
    def __init__(self, *, tags: dict[int, str], document_tags: list[int]) -> None:
        self.tags = tags
        self.document_tags = document_tags
        self.created: list[str] = []
        self.patched: list[list[int]] = []
        self.missing = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Token t"
        path = request.url.path
        if path == "/api/tags/":
            if request.method == "GET":
                name = request.url.params["name__iexact"]
                return httpx.Response(
                    200,
                    json={
                        "results": [{"id": i, "name": n} for i, n in self.tags.items() if n == name]
                    },
                )
            name = json.loads(request.content)["name"]
            new_id = max(self.tags, default=0) + 1
            self.tags[new_id] = name
            self.created.append(name)
            return httpx.Response(201, json={"id": new_id})
        if path == "/api/documents/77/":
            if self.missing:
                return httpx.Response(404)
            if request.method == "GET":
                return httpx.Response(200, json={"id": 77, "tags": self.document_tags})
            assert request.method == "PATCH"
            self.document_tags = json.loads(request.content)["tags"]
            self.patched.append(self.document_tags)
            return httpx.Response(200, json={"id": 77})
        return httpx.Response(500)


@pytest.mark.asyncio
async def test_paperless_add_tag_creates_and_assigns_once() -> None:
    fake = FakePaperless(tags={1: "mhvp:tenant:hvm"}, document_tags=[1])
    async with _client(fake) as http:
        store = PaperlessStore(BASE, "t", http)
        assert await store.add_tag("77", "gelöscht") is True
        assert fake.created == ["gelöscht"]
        assert fake.patched == [[1, 2]]
        # Existing tag: no second creation, no second PATCH.
        assert await store.add_tag("77", "gelöscht") is True
        assert fake.created == ["gelöscht"]
        assert fake.patched == [[1, 2]]


@pytest.mark.asyncio
async def test_paperless_add_tag_reuses_existing_tag_and_reports_missing_document() -> None:
    fake = FakePaperless(tags={1: "mhvp:tenant:hvm", 5: "gelöscht"}, document_tags=[1])
    async with _client(fake) as http:
        store = PaperlessStore(BASE, "t", http)
        assert await store.add_tag("77", "gelöscht") is True
        assert fake.created == []
        assert fake.patched == [[1, 5]]
        fake.missing = True
        assert await store.add_tag("77", "gelöscht") is False
        with pytest.raises(DmsError):
            await store.add_tag("task:abc", "gelöscht")


def _drive(http: httpx.AsyncClient) -> GoogleDriveStore:
    return GoogleDriveStore(
        root_folder_id="root", client_id="c", client_secret="s", refresh_token="r", client=http
    )


@pytest.mark.asyncio
async def test_drive_trash_is_a_patch_and_delete_error_is_raised() -> None:
    calls: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok"})
        assert request.headers["authorization"] == "Bearer tok"
        calls.append((request.method, request.url.path, request.content))
        if request.method == "DELETE":
            return httpx.Response(403)
        if request.method == "PATCH":
            return httpx.Response(200, json={"id": "f1", "trashed": True})
        return httpx.Response(500)

    async with _client(handler) as http:
        drive = _drive(http)
        with pytest.raises(DmsError, match="delete: HTTP 403"):
            await drive.delete("f1")
        assert await drive.trash("f1") is True
    assert calls[-1] == ("PATCH", "/drive/v3/files/f1", b'{"trashed":true}')


@pytest.mark.asyncio
async def test_drive_trash_reports_missing_file() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(404)

    async with _client(handler) as http:
        assert await _drive(http).trash("gone") is False
