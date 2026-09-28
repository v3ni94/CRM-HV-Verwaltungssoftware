"""HTTP client for the claims adjuster HV API v1 (contract draft
``docs/integrations/schadenstool-hv-api-v1-vertrag.md``, base path ``/api/integrations/hv/v1``).

Endpoints called (and only these):

- ``GET  /tickets`` (``cursor``, ``limit``, ``updatedSince``): connection test, pull, takeover
- ``GET  /tickets/{id}``: fetch after a webhook event
- ``POST /tickets``: create a damage ticket
- ``PATCH /tickets/{id}``: status only
- ``GET/POST /tickets/{id}/comments``
- ``GET/POST /tickets/{id}/attachments`` (POST multipart)
- ``GET  <downloadUrl>`` of an attachment (must be on the configured host)

Every write carries ``Idempotency-Key`` (mandatory per contract section 9). The optional HMAC
(``X-Timestamp``, ``X-Signature``) is added when the tenant stored an HMAC secret. The token is
never logged; errors carry the HTTP status and a German reason only.

``TRANSPORT`` lets tests plug an in-process fake server (``httpx.MockTransport``).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from mhvp.integrations.schadenstool.signature import signed_headers

log = logging.getLogger(__name__)

API_PATH = "/api/integrations/hv/v1"
TIMEOUT_SECONDS = 20.0
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
TRANSPORT: httpx.AsyncBaseTransport | None = None


class ErrorKind:
    AUTH = "auth"  # 401/403: "Token ungültig"
    RATE_LIMITED = "rate_limited"  # 429, honour Retry-After
    UNAVAILABLE = "unavailable"  # timeout, network, 5xx: retry
    REJECTED = "rejected"  # other 4xx: permanent, no retry


class SchadenstoolError(Exception):
    def __init__(
        self,
        kind: str,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.kind in (ErrorKind.RATE_LIMITED, ErrorKind.UNAVAILABLE)


@dataclass(frozen=True)
class Credentials:
    base_url: str
    token: str
    hmac_secret: str | None = None


def items_of(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [i for i in body if isinstance(i, dict)]
    if isinstance(body, dict) and isinstance(body.get("items"), list):
        return [i for i in body["items"] if isinstance(i, dict)]
    return []


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value and value.strip().isdigit():
        return min(int(value.strip()), 86_400)
    return None


class SchadenstoolClient:
    def __init__(self, credentials: Credentials) -> None:
        self._c = credentials
        self._root = credentials.base_url.rstrip("/")

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._root + API_PATH,
            timeout=TIMEOUT_SECONDS,
            transport=TRANSPORT,
            headers={"Authorization": f"Bearer {self._c.token}", "Accept": "application/json"},
            follow_redirects=False,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        idempotency_key: str | None = None,
        json_body: Any = None,
        files: Any = None,
        data: Any = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers: dict[str, str] = {}
        content: bytes | None = None
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if json_body is not None:
            content = json.dumps(json_body, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        try:
            async with self._http() as http:
                request = http.build_request(
                    method, path, content=content, files=files, data=data, params=params
                )
                if self._c.hmac_secret:
                    body = request.read()
                    request.headers.update(
                        signed_headers(self._c.hmac_secret, body, int(time.time()))
                    )
                request.headers.update(headers)
                response = await http.send(request)
        except httpx.TimeoutException as exc:
            raise SchadenstoolError(
                ErrorKind.UNAVAILABLE, "Der Schadenbearbeiter hat nicht rechtzeitig geantwortet."
            ) from exc
        except httpx.HTTPError as exc:
            raise SchadenstoolError(
                ErrorKind.UNAVAILABLE, "Der Schadenbearbeiter ist nicht erreichbar."
            ) from exc
        log.info(
            "schadenstool request",
            extra={"method": method, "path": path, "status": response.status_code},
        )
        status = response.status_code
        if status in (401, 403):
            raise SchadenstoolError(ErrorKind.AUTH, "Token ungültig.", status_code=status)
        if status == 429:
            raise SchadenstoolError(
                ErrorKind.RATE_LIMITED,
                "Anfragelimit des Schadenbearbeiters erreicht.",
                status_code=status,
                retry_after=_retry_after(response),
            )
        if status >= 500:
            raise SchadenstoolError(
                ErrorKind.UNAVAILABLE,
                f"Der Schadenbearbeiter antwortete mit Status {status}.",
                status_code=status,
            )
        if status >= 400:
            code = ""
            try:
                code = str(response.json().get("code") or "")
            except (ValueError, AttributeError):
                code = ""
            suffix = f" ({code})" if code else ""
            raise SchadenstoolError(
                ErrorKind.REJECTED,
                f"Der Schadenbearbeiter lehnte die Anfrage mit Status {status} ab{suffix}.",
                status_code=status,
            )
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {}

    async def list_tickets(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        updated_since: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if updated_since:
            params["updatedSince"] = updated_since
        body = self._json(await self._request("GET", "/tickets", params=params))
        next_cursor = body.get("nextCursor") if isinstance(body, dict) else None
        return {"items": items_of(body), "nextCursor": next_cursor}

    async def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        body = self._json(await self._request("GET", f"/tickets/{ticket_id}"))
        return body if isinstance(body, dict) else {}

    async def create_ticket(self, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        response = await self._request(
            "POST", "/tickets", idempotency_key=idempotency_key, json_body=payload
        )
        body = self._json(response)
        return body if isinstance(body, dict) else {}

    async def patch_status(self, ticket_id: str, status: str, idempotency_key: str) -> None:
        await self._request(
            "PATCH",
            f"/tickets/{ticket_id}",
            idempotency_key=idempotency_key,
            json_body={"status": status},
        )

    async def list_comments(self, ticket_id: str) -> list[dict[str, Any]]:
        return items_of(self._json(await self._request("GET", f"/tickets/{ticket_id}/comments")))

    async def add_comment(
        self, ticket_id: str, payload: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/tickets/{ticket_id}/comments",
            idempotency_key=idempotency_key,
            json_body=payload,
        )
        body = self._json(response)
        return body if isinstance(body, dict) else {}

    async def list_attachments(self, ticket_id: str) -> list[dict[str, Any]]:
        return items_of(self._json(await self._request("GET", f"/tickets/{ticket_id}/attachments")))

    async def add_attachment(
        self,
        ticket_id: str,
        *,
        filename: str,
        content: bytes,
        mime_type: str,
        external_attachment_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        response = await self._request(
            "POST",
            f"/tickets/{ticket_id}/attachments",
            idempotency_key=idempotency_key,
            files={"file": (filename, content, mime_type)},
            data={"externalAttachmentId": external_attachment_id},
        )
        body = self._json(response)
        return body if isinstance(body, dict) else {}

    async def download(self, url: str) -> tuple[bytes, str | None]:
        """Download an attachment. Relative URLs resolve against the base URL; absolute URLs
        must stay on the configured host (no token to third hosts)."""
        target = urljoin(self._root + "/", url)
        if urlsplit(target).netloc != urlsplit(self._root).netloc:
            raise SchadenstoolError(
                ErrorKind.REJECTED, "Download-Adresse liegt nicht beim Schadenbearbeiter."
            )
        response = await self._request("GET", target)
        if len(response.content) > MAX_DOWNLOAD_BYTES:
            raise SchadenstoolError(ErrorKind.REJECTED, "Anhang ist zu groß.")
        return response.content, response.headers.get("Content-Type")
