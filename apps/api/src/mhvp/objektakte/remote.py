"""Client for the objektakte read API (M29 Stufe 4, contract in docs/integrations/objektakte.md).

objektakte (the separate object takeover system) offers five GET endpoints under
``<OBJEKTAKTE_API_URL>`` (``.../api/crm/v1/``) with a bearer token that carries scopes:

1. ``objects/`` (objects:read), 2. ``objects/{number}/`` (objects:read), 3.
``objects/{number}/documents/`` (documents:read), 4. ``objects/{number}/owners/`` and 5.
``objects/{number}/tenants/`` (persons:read). Lists are paginated
(``{"count", "page", "page_size", "results"}``, ``page_size`` at most 500).

The token never reaches the browser: only the API calls objektakte, server side. Every failure
(timeout, connection error, 401/403 because of a wrong token or scope, 5xx, malformed JSON)
becomes :class:`ObjektakteUnavailableError`, which the CRM endpoints answer with 502; a 404 of
an object becomes :class:`ObjektakteNotFoundError`. Messages never contain the token or the
response body.

Upload (26.09.2026, docs/integrations/objektakte.md): endpoint 6
``POST objects/{number}/documents/`` (documents:write) hands a CRM document to the objektakte
pipeline, endpoint 7 ``documents/{id}/`` (documents:read) returns its state. A 503 (switch off
in objektakte) becomes :class:`ObjektakteDeferredError`, a definite rejection (400, 404, 409,
413) :class:`ObjektakteRejectedError` with the German reason objektakte gives.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from mhvp.core.config import Settings

MAX_PAGE_SIZE = 500
UPLOAD_TIMEOUT_SECONDS = 120.0  # a file of up to 50 MB over the office line; reads keep 10 s
# Upper bound of pages read for one "all" listing (500 x 40 = 20,000 rows); objektakte holds
# 67 objects and a few thousand documents per object at most, so hitting it means a paging bug.
MAX_PAGES = 40


class ObjektakteError(Exception):
    """Base class; the message is safe to log and to show (no token, no body)."""


class ObjektakteUnavailableError(ObjektakteError):
    pass


class ObjektakteDeferredError(ObjektakteError):
    """objektakte accepts uploads later (switch sync.crm_uploads_enabled off, HTTP 503)."""


class ObjektakteRejectedError(ObjektakteError):
    """objektakte rejected an upload for good (400, 404, 409, 413); retrying does not help."""


class ObjektakteNotFoundError(ObjektakteError):
    pass


class ObjektakteClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/") + "/"
        self._client = httpx.AsyncClient(
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            follow_redirects=False,
        )

    @classmethod
    def from_settings(
        cls, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
    ) -> ObjektakteClient:
        if not settings.objektakte_api_configured:
            raise ObjektakteUnavailableError("objektakte ist nicht angebunden.")
        assert settings.objektakte_api_url is not None  # noqa: S101 - checked above
        assert settings.objektakte_api_token is not None  # noqa: S101 - checked above
        return cls(
            settings.objektakte_api_url,
            settings.objektakte_api_token.get_secret_value(),
            timeout=settings.objektakte_api_timeout_seconds,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ObjektakteClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self._base + path.lstrip("/")
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            response = await self._client.get(url, params=clean)
        except httpx.TimeoutException:
            raise ObjektakteUnavailableError(
                "objektakte antwortet nicht (Zeitüberschreitung)."
            ) from None
        except httpx.HTTPError:
            raise ObjektakteUnavailableError("objektakte ist nicht erreichbar.") from None
        if response.status_code == 404:
            raise ObjektakteNotFoundError("Objekt in objektakte nicht gefunden.")
        if response.status_code in (401, 403):
            raise ObjektakteUnavailableError(
                f"objektakte verweigert den Zugriff (HTTP {response.status_code}); "
                "Token oder Berechtigung prüfen."
            )
        if response.status_code >= 400:
            raise ObjektakteUnavailableError(f"objektakte meldet HTTP {response.status_code}.")
        try:
            return response.json()
        except ValueError:
            raise ObjektakteUnavailableError("objektakte liefert keine gültige Antwort.") from None

    async def _page(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        data = await self._get(path, params)
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ObjektakteUnavailableError("objektakte liefert keine gültige Liste.")
        return data

    async def _all(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            data = await self._page(
                path, {**(params or {}), "page": page, "page_size": MAX_PAGE_SIZE}
            )
            results = [r for r in data["results"] if isinstance(r, dict)]
            rows.extend(results)
            count = data.get("count")
            if not results or (isinstance(count, int) and len(rows) >= count):
                return rows
        raise ObjektakteUnavailableError("objektakte liefert mehr Seiten als erwartet.")

    @staticmethod
    def _number(number: str) -> str:
        value = str(number).strip()
        if not value or not value.isalnum():
            raise ObjektakteNotFoundError("Objektnummer ungültig.")
        return value

    async def objects(self) -> list[dict[str, Any]]:
        """Endpoint 1, all pages."""
        return await self._all("objects/")

    async def object(self, number: str) -> dict[str, Any]:
        """Endpoint 2."""
        data = await self._get(f"objects/{self._number(number)}/")
        if not isinstance(data, dict):
            raise ObjektakteUnavailableError("objektakte liefert keine gültige Antwort.")
        return data

    async def documents(
        self,
        number: str,
        *,
        page: int = 1,
        page_size: int = 100,
        folder: str | None = None,
        since: str | None = None,
    ) -> dict[str, Any]:
        """Endpoint 3, one page."""
        return await self._page(
            f"objects/{self._number(number)}/documents/",
            {
                "page": page,
                "page_size": min(max(page_size, 1), MAX_PAGE_SIZE),
                "folder": folder,
                "since": since,
            },
        )

    async def all_documents(self, number: str) -> list[dict[str, Any]]:
        """Endpoint 3, all pages."""
        return await self._all(f"objects/{self._number(number)}/documents/")

    async def owners(self, number: str) -> list[dict[str, Any]]:
        """Endpoint 4, all pages."""
        return await self._all(f"objects/{self._number(number)}/owners/")

    async def tenants(self, number: str) -> list[dict[str, Any]]:
        """Endpoint 5, all pages."""
        return await self._all(f"objects/{self._number(number)}/tenants/")

    async def upload_document(
        self,
        number: str,
        *,
        crm_document_id: str,
        filename: str,
        data: bytes,
        mime_type: str,
        hints: dict[str, Any],
    ) -> dict[str, Any]:
        """Upload endpoint 6 (POST on the document list, scope documents:write)."""
        url = self._base + f"objects/{self._number(number)}/documents/"
        try:
            response = await self._client.post(
                url,
                data={
                    "crm_document_id": crm_document_id,
                    "hints": json.dumps(hints, ensure_ascii=False),
                },
                files={"file": (filename, data, mime_type)},
                timeout=UPLOAD_TIMEOUT_SECONDS,
            )
        except httpx.TimeoutException:
            raise ObjektakteUnavailableError(
                "objektakte antwortet nicht (Zeitüberschreitung)."
            ) from None
        except httpx.HTTPError:
            raise ObjektakteUnavailableError("objektakte ist nicht erreichbar.") from None
        if response.status_code == 503:
            raise ObjektakteDeferredError("objektakte nimmt Uploads derzeit nicht an (HTTP 503).")
        if response.status_code in (400, 404, 409, 413):
            raise ObjektakteRejectedError(
                f"objektakte lehnt den Upload ab (HTTP {response.status_code}): "
                f"{_error_text(response)}"
            )
        if response.status_code in (401, 403):
            raise ObjektakteUnavailableError(
                f"objektakte verweigert den Upload (HTTP {response.status_code}); "
                "Token oder Scope documents:write prüfen."
            )
        if response.status_code >= 400:
            raise ObjektakteUnavailableError(f"objektakte meldet HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError:
            raise ObjektakteUnavailableError("objektakte liefert keine gültige Antwort.") from None
        if not isinstance(body, dict):
            raise ObjektakteUnavailableError("objektakte liefert keine gültige Antwort.")
        return body

    async def document_status(self, document_id: int) -> dict[str, Any]:
        """Status endpoint 7."""
        data = await self._get(f"documents/{int(document_id)}/")
        if not isinstance(data, dict):
            raise ObjektakteUnavailableError("objektakte liefert keine gültige Antwort.")
        return data


def _error_text(response: httpx.Response) -> str:
    """The German ``error`` text objektakte returns, cut to 200 characters; never the body."""
    try:
        data = response.json()
    except ValueError:
        return "ohne Begründung"
    text = data.get("error") if isinstance(data, dict) else None
    return str(text)[:200] if text else "ohne Begründung"
