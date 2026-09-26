"""Read-only Paperless-ngx search for the ticket and property document panels (M31).

No REST API of our own exists for Paperless beyond what it offers; we only read documents that
the mirror job (documents/tasks.py) already uploaded. Custom-field IDs for object number and
company are configured per tenant on ``DmsConnection.options`` (keys ``object_field_id`` and
``company_field_id``); a common default is 7 respectively 5 but nothing here hardcodes it.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx

TIMEOUT_SECONDS = 10.0
FileKind = Literal["download", "preview", "thumb"]


class PaperlessSearchError(Exception):
    """Paperless could not be reached or answered with an error; message has no secrets."""


class PaperlessNotConfiguredError(Exception):
    """No usable Paperless connection (base_url/token) for this tenant."""


@dataclass(frozen=True, slots=True)
class PaperlessDocument:
    id: int
    title: str
    created: str | None
    added: str | None
    correspondent: str | None
    document_type: str | None
    tags: list[str]
    page_count: int | None
    original_file_name: str | None
    # OCR text as Paperless holds it (A42 intake pipeline reuses it instead of a second OCR);
    # None when the listing was requested without it.
    content: str | None = None


@dataclass(frozen=True, slots=True)
class PaperlessPage:
    items: list[PaperlessDocument]
    total: int


@dataclass(frozen=True, slots=True)
class PaperlessFile:
    content: bytes
    content_type: str
    filename: str | None


class PaperlessSearch:
    """Thin, read-only client for ``/api/documents/`` search and file retrieval."""

    def __init__(
        self,
        base_url: str,
        token: str,
        client: httpx.AsyncClient | None = None,
        object_field_id: int | None = None,
        company_field_id: int | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        self._owns_client = client is None
        self.object_field_id = object_field_id
        self.company_field_id = company_field_id

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "PaperlessSearch":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def _object_query(self, number: str) -> str:
        assert self.object_field_id is not None  # noqa: S101 - guarded by caller
        # Feldwerte in Paperless: "523" oder "602, Bedburg, Am Fließ 6" (Objektnummer, Ort,
        # Straße). Deshalb exakt ODER mit "<Nummer>, " beginnend, kein reines istartswith auf die
        # Nummer, da das auch "5230" träfe.
        condition = [
            "OR",
            [
                [self.object_field_id, "exact", number],
                [self.object_field_id, "istartswith", f"{number}, "],
            ],
        ]
        return json.dumps(condition)

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.get(
                f"{self._base}{path}", params=params, headers=self._headers
            )
        except httpx.TimeoutException as exc:
            raise PaperlessSearchError("Paperless hat nicht rechtzeitig geantwortet.") from exc
        except httpx.HTTPError as exc:
            raise PaperlessSearchError("Paperless ist nicht erreichbar.") from exc
        if response.status_code == 401 or response.status_code == 403:
            raise PaperlessSearchError("Zugangsdaten für Paperless sind ungültig.")
        if response.status_code >= 400:
            raise PaperlessSearchError(f"Paperless antwortete mit Fehler {response.status_code}.")
        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise PaperlessSearchError("Paperless lieferte eine unlesbare Antwort.") from exc
        return payload

    @staticmethod
    def _map(raw: dict[str, Any]) -> PaperlessDocument:
        def name(value: Any) -> str | None:
            if isinstance(value, dict):
                return value.get("name")
            return None

        return PaperlessDocument(
            id=int(raw["id"]),
            title=str(raw.get("title") or ""),
            created=raw.get("created"),
            added=raw.get("added"),
            correspondent=name(raw.get("correspondent")),
            document_type=name(raw.get("document_type")),
            tags=[str(t) for t in (raw.get("tags") or []) if not isinstance(t, dict)]
            or [name(t) or "" for t in (raw.get("tags") or []) if isinstance(t, dict)],
            page_count=raw.get("page_count"),
            original_file_name=raw.get("original_file_name"),
            content=raw.get("content") if isinstance(raw.get("content"), str) else None,
        )

    def _page(self, payload: dict[str, Any]) -> PaperlessPage:
        results = payload.get("results", [])
        total = int(payload.get("count", len(results)))
        return PaperlessPage(items=[self._map(r) for r in results], total=total)

    async def list_by_object_number(
        self, number: str, page: int = 1, page_size: int = 25
    ) -> PaperlessPage:
        if not self.object_field_id:
            # Ohne gepflegte Feld-ID keine Annahme über den Filteraufbau, lieber leer als falsch
            # zugeordnet.
            return PaperlessPage(items=[], total=0)
        params = {
            "custom_field_query": self._object_query(number),
            "page": page,
            "page_size": page_size,
            "ordering": "-created",
        }
        return self._page(await self._get("/api/documents/", params))

    async def list_by_ticket(
        self, ticket_number: int | str, page: int = 1, page_size: int = 25
    ) -> PaperlessPage:
        """Volltextsuche nach der Ticketnummer, da kein eigenes Custom Field dafür existiert."""
        params = {
            "query": str(ticket_number),
            "page": page,
            "page_size": page_size,
            "ordering": "-created",
        }
        return self._page(await self._get("/api/documents/", params))

    async def list_added_since(
        self, added_after: str | None, page: int = 1, page_size: int = 50
    ) -> PaperlessPage:
        """Documents added to Paperless after ``added_after`` (ISO 8601, exclusive), oldest
        first, with their OCR ``content``; the inbox job (A42) keeps the last ``added`` value
        of a tenant as its watermark. Without a watermark the whole archive is paged."""
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "ordering": "added",
            "fields": "id,title,created,added,correspondent,document_type,tags,page_count,"
            "original_file_name,content",
        }
        if added_after:
            params["added__gt"] = added_after
        return self._page(await self._get("/api/documents/", params))

    async def fetch_file(self, document_id: int, kind: FileKind) -> PaperlessFile:
        endpoint = {"download": "download", "preview": "preview", "thumb": "thumb"}[kind]
        url = f"{self._base}/api/documents/{document_id}/{endpoint}/"
        try:
            response = await self._client.get(url, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise PaperlessSearchError("Paperless hat nicht rechtzeitig geantwortet.") from exc
        except httpx.HTTPError as exc:
            raise PaperlessSearchError("Paperless ist nicht erreichbar.") from exc
        if response.status_code == 404:
            raise PaperlessSearchError("Dokument wurde in Paperless nicht gefunden.")
        if response.status_code >= 400:
            raise PaperlessSearchError(f"Paperless antwortete mit Fehler {response.status_code}.")
        content_type = response.headers.get("content-type", "application/octet-stream")
        filename = None
        disposition = response.headers.get("content-disposition")
        if disposition and "filename=" in disposition:
            filename = disposition.split("filename=", 1)[1].strip('"; ')
        return PaperlessFile(content=response.content, content_type=content_type, filename=filename)
