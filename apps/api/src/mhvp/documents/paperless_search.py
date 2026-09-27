"""Read-only Paperless-ngx search for the ticket and property document panels (M31).

No REST API of our own exists for Paperless beyond what it offers; we only read documents that
the mirror job (documents/tasks.py) already uploaded. Custom-field IDs for object number and
company are configured per tenant on ``DmsConnection.options`` (keys ``object_field_id`` and
``company_field_id``); a common default is 7 respectively 5 but nothing here hardcodes it.

Object search and company filter follow the Immoware Hub (dossier
``docs/integrations/immoware-hub.md`` sections 5 and 7.2): an object matches only when its
object field is exactly ``<number>`` or starts with ``<number>, `` (so ``523`` never hits
``5230``), and the company filter compares the option id of a configurable select field. The
mapping option id to company comes from ``DmsConnection.options["company_options"]``
(``parse_company_options``); nothing here knows real option ids.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import httpx

TIMEOUT_SECONDS = 10.0
FileKind = Literal["download", "preview", "thumb"]


class PaperlessSearchError(Exception):
    """Paperless could not be reached or answered with an error; message has no secrets."""


class PaperlessNotConfiguredError(Exception):
    """No usable Paperless connection (base_url/token) for this tenant."""


# Key in ``DmsConnection.options`` holding the option id to company mapping as text, one
# ``<Option-ID>=<Gesellschaft>`` per line (the options column only stores strings).
COMPANY_OPTIONS_KEY = "company_options"
_MAX_COMPANY_OPTIONS = 50
_MAX_OPTION_ID_LENGTH = 64
_MAX_COMPANY_LABEL_LENGTH = 100


def object_number_matches(value: object, number: str) -> bool:
    """Hub rule for the object field: exactly ``<number>`` or beginning with ``<number>, ``.

    ``523`` matches ``523`` and ``523, Musterstr``, but neither ``5230`` nor ``1523``. The same
    rule is sent to Paperless as ``custom_field_query`` and applied again to the results, so a
    Paperless that ignores or misreads the filter cannot attach foreign documents to an object.
    """
    if not isinstance(value, str) or not number:
        return False
    return value == number or value.startswith(f"{number}, ")


def parse_field_id(raw: object, label: str) -> int | None:
    """Custom-field id from the options column: empty means not configured, otherwise a
    positive integer (Paperless ids); anything else is rejected instead of guessed."""
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip()
    if not text.isdigit() or int(text) <= 0:
        raise ValueError(f"{label} muss eine positive ganze Zahl sein.")
    return int(text)


def parse_company_options(raw: object) -> dict[str, str]:
    """Parse ``<Option-ID>=<Gesellschaft>`` lines (``;`` also separates) into a mapping.

    Empty input means no company filter. Duplicate option ids, missing parts or overlong
    values raise ``ValueError`` with a German message for the settings form.
    """
    if raw is None:
        return {}
    text = str(raw)
    result: dict[str, str] = {}
    for part in text.replace(";", "\n").splitlines():
        entry = part.strip()
        if not entry:
            continue
        option_id, sep, label = entry.partition("=")
        option_id, label = option_id.strip(), label.strip()
        if not sep or not option_id or not label:
            raise ValueError(
                f'Gesellschaftsoption "{entry[:40]}" hat nicht die Form Options-ID=Gesellschaft.'
            )
        if len(option_id) > _MAX_OPTION_ID_LENGTH or len(label) > _MAX_COMPANY_LABEL_LENGTH:
            raise ValueError(f'Gesellschaftsoption "{entry[:40]}" ist zu lang.')
        if option_id in result:
            raise ValueError(f"Options-ID {option_id} ist mehrfach eingetragen.")
        result[option_id] = label
    if len(result) > _MAX_COMPANY_OPTIONS:
        raise ValueError(f"Höchstens {_MAX_COMPANY_OPTIONS} Gesellschaftsoptionen zulässig.")
    return result


def format_company_options(options: Mapping[str, str]) -> str:
    """Normalised text form of the mapping as it is stored in ``DmsConnection.options``."""
    return "\n".join(f"{option_id}={label}" for option_id, label in options.items())


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
    # Company label from the configured option mapping (7.2); None without mapping or value.
    company: str | None = None


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
        company_options: Mapping[str, str] | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        self._owns_client = client is None
        self.object_field_id = object_field_id
        self.company_field_id = company_field_id
        self.company_options: dict[str, str] = dict(company_options or {})

    @property
    def company_filter_available(self) -> bool:
        return bool(self.company_field_id and self.company_options)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "PaperlessSearch":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    def _object_condition(self, number: str) -> list[Any]:
        assert self.object_field_id is not None  # noqa: S101 - guarded by caller
        # Feldwerte in Paperless: "523" oder "602, Bedburg, Am Fließ 6" (Objektnummer, Ort,
        # Straße). Deshalb exakt ODER mit "<Nummer>, " beginnend, kein reines istartswith auf die
        # Nummer, da das auch "5230" träfe (object_number_matches prüft dasselbe lokal nach).
        return [
            "OR",
            [
                [self.object_field_id, "exact", number],
                [self.object_field_id, "istartswith", f"{number}, "],
            ],
        ]

    def _company_condition(self, option_id: str) -> list[Any]:
        assert self.company_field_id is not None  # noqa: S101 - guarded by caller
        # Auswahlfeld: Paperless vergleicht die Options-ID der gewählten Option.
        return [self.company_field_id, "exact", option_id]

    def _object_query(self, number: str) -> str:
        return json.dumps(self._object_condition(number))

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
    def _field_value(raw: dict[str, Any], field_id: int) -> tuple[bool, Any]:
        """(listed, value) of a custom field in a Paperless result; ``listed`` is False when
        the result carries no ``custom_fields`` at all (then nothing can be checked)."""
        fields = raw.get("custom_fields")
        if not isinstance(fields, list):
            return False, None
        for entry in fields:
            if isinstance(entry, dict) and entry.get("field") == field_id:
                return True, entry.get("value")
        return True, None

    def _company_label(self, raw: dict[str, Any]) -> str | None:
        if not self.company_field_id or not self.company_options:
            return None
        _, value = self._field_value(raw, self.company_field_id)
        if value is None:
            return None
        return self.company_options.get(str(value))

    def _map(self, raw: dict[str, Any]) -> PaperlessDocument:
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
            company=self._company_label(raw),
        )

    def _page(
        self,
        payload: dict[str, Any],
        object_number: str | None = None,
        company_option_id: str | None = None,
    ) -> PaperlessPage:
        results = payload.get("results", [])
        total = int(payload.get("count", len(results)))
        kept: list[dict[str, Any]] = []
        for raw in results:
            if object_number is not None and self.object_field_id:
                listed, value = self._field_value(raw, self.object_field_id)
                if listed and not object_number_matches(value, object_number):
                    continue
            if company_option_id is not None and self.company_field_id:
                listed, value = self._field_value(raw, self.company_field_id)
                if listed and (value is None or str(value) != company_option_id):
                    continue
            kept.append(raw)
        # Treffer, die Paperless trotz Filter lieferte, zählen nicht mit (nur auf dieser Seite
        # erkennbar; bei einem korrekt filternden Paperless ist die Differenz 0).
        total = max(total - (len(results) - len(kept)), len(kept))
        return PaperlessPage(items=[self._map(r) for r in kept], total=total)

    async def search(
        self,
        *,
        object_number: str | None = None,
        company_option_id: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> PaperlessPage:
        """Combined read-only search: object number (Hub rule), company option and full text.

        A requested filter whose field is not configured yields an empty page instead of an
        unfiltered one (lieber leer als falsch zugeordnet). Unknown company option ids too.
        """
        conditions: list[list[Any]] = []
        if object_number is not None:
            if not self.object_field_id:
                return PaperlessPage(items=[], total=0)
            conditions.append(self._object_condition(object_number))
        if company_option_id is not None:
            if not self.company_filter_available or company_option_id not in self.company_options:
                return PaperlessPage(items=[], total=0)
            conditions.append(self._company_condition(company_option_id))
        params: dict[str, Any] = {"page": page, "page_size": page_size, "ordering": "-created"}
        if conditions:
            condition = conditions[0] if len(conditions) == 1 else ["AND", conditions]
            params["custom_field_query"] = json.dumps(condition)
        if query:
            params["query"] = query
        payload = await self._get("/api/documents/", params)
        return self._page(payload, object_number=object_number, company_option_id=company_option_id)

    async def list_by_object_number(
        self,
        number: str,
        page: int = 1,
        page_size: int = 25,
        company_option_id: str | None = None,
    ) -> PaperlessPage:
        # Ohne gepflegte Feld-ID keine Annahme über den Filteraufbau, lieber leer als falsch
        # zugeordnet (search() prüft das).
        return await self.search(
            object_number=number,
            company_option_id=company_option_id,
            page=page,
            page_size=page_size,
        )

    async def list_by_ticket(
        self,
        ticket_number: int | str,
        page: int = 1,
        page_size: int = 25,
        company_option_id: str | None = None,
    ) -> PaperlessPage:
        """Volltextsuche nach der Ticketnummer, da kein eigenes Custom Field dafür existiert."""
        return await self.search(
            query=str(ticket_number),
            company_option_id=company_option_id,
            page=page,
            page_size=page_size,
        )

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
