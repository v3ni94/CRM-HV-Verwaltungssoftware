"""Async client for the Lexware Office public REST API (rule INT-LEXO-01).

Binding source: ``docs/integrations/lexoffice.md`` (vendor documentation verified 28.09.2026).
Endpoints called, and only these: ``GET /v1/profile``, ``GET /v1/contacts`` (filters email,
name, number, customer, vendor, page, size), ``GET/POST/PUT /v1/contacts/{id}``,
``GET /v1/voucherlist``, ``GET /v1/invoices/{id}``, ``GET /v1/invoices/{id}/file``,
``POST /v1/invoices`` (never with ``finalize``).

Errors are mapped to typed exceptions with ``retryable``; both vendor error formats (legacy
``IssueList`` and regular ``details[]``) are parsed into :class:`Issue` and redacted: ``args``,
``additionalData`` and free text ``message`` are dropped. The API key is never logged.
``TRANSPORT`` lets tests plug an ``httpx.MockTransport``; the rate limiter runs before every
request (``ratelimit.acquire``).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from mhvp.core.webhooks import pin_target
from mhvp.integrations.lexoffice_ext import ratelimit

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.lexware.io"
TIMEOUT_SECONDS = 20.0
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MIN_FILTER_LENGTH = 3
TRANSPORT: httpx.AsyncBaseTransport | None = None

_FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)


@dataclass(frozen=True)
class Issue:
    field: str | None
    violation: str | None
    message_key: str | None = None


class LexofficeError(Exception):
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        issues: list[Issue] | None = None,
        trace_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.issues = issues or []
        self.trace_id = trace_id

    def redacted(self) -> str:
        """Error text built from status, field/violation and trace id only (section 4.6)."""
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"Status {self.status_code}")
        for issue in self.issues[:5]:
            parts.append(f"{issue.field or '?'}: {issue.violation or issue.message_key or '?'}")
        if self.trace_id:
            parts.append(f"traceId {self.trace_id}")
        return ", ".join(parts)[:500]


class LexofficeAuthError(LexofficeError):
    pass


class LexofficeRateLimitedError(LexofficeError):
    retryable = True

    def __init__(self, message: str, *, retry_after: int | None, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.retry_after = retry_after


class LexofficeConflictError(LexofficeError):
    pass


class LexofficeNotFoundError(LexofficeError):
    pass


class LexofficeRejectedError(LexofficeError):
    pass


class LexofficeUnavailableError(LexofficeError):
    retryable = True

    def __init__(self, message: str, *, maybe_processed: bool = False, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.maybe_processed = maybe_processed


class LexofficeOrganizationMismatchError(LexofficeError):
    pass


class LexofficeValidationError(LexofficeError):
    """Local validation before any call (filter too short, unsafe URL)."""


@dataclass(frozen=True)
class DownloadedFile:
    content: bytes
    content_type: str
    filename: str | None


@dataclass
class AsyncCredentials:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    organization_id: str | None = None
    rate_key: str = "default"
    redis: Any | None = None
    allow_private: bool = False
    request_log: list[dict[str, Any]] = field(default_factory=list)


def parse_issues(body: Any) -> tuple[list[Issue], str | None]:
    """Both documented error formats, redacted (no ``args``, ``additionalData``, ``message``)."""
    issues: list[Issue] = []
    trace_id: str | None = None
    if not isinstance(body, dict):
        return issues, trace_id
    trace = body.get("traceId")
    if isinstance(trace, str):
        trace_id = trace[:64]
    for item in body.get("IssueList") or []:
        if isinstance(item, dict):
            issues.append(
                Issue(
                    field=_short(item.get("source")),
                    violation=_short(item.get("type")),
                    message_key=_short(item.get("i18nKey")),
                )
            )
    for item in body.get("details") or []:
        if isinstance(item, dict):
            issues.append(
                Issue(field=_short(item.get("field")), violation=_short(item.get("violation")))
            )
    return issues, trace_id


def _short(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)[:80]


def _retry_after(response: httpx.Response) -> int | None:
    value = response.headers.get("Retry-After")
    if value and value.strip().isdigit():
        return min(int(value.strip()), 86_400)
    return None


def encode_filter(value: str) -> str:
    """``&``, ``<`` and ``>`` are HTML encoded before URL encoding, as documented."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def filename_from_disposition(header: str | None) -> str | None:
    if not header:
        return None
    match = _FILENAME_RE.search(header)
    if not match:
        return None
    name = match.group(1).strip().replace("/", "_").replace("\\", "_")
    return name[:200] or None


class LexofficeAsyncClient:
    def __init__(self, credentials: AsyncCredentials) -> None:
        self._c = credentials
        self._root = credentials.base_url.rstrip("/")

    def _http(self, accept: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._root,
            timeout=TIMEOUT_SECONDS,
            transport=TRANSPORT,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {self._c.api_key}", "Accept": accept},
        )

    def _check_organization(self, body: Any) -> None:
        if not isinstance(body, dict) or self._c.organization_id is None:
            return
        remote = body.get("organizationId")
        if isinstance(remote, str) and remote != self._c.organization_id:
            raise LexofficeOrganizationMismatchError(
                "API Schlüssel gehört zu einer anderen Lexware Organisation."
            )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        accept: str = "application/json",
    ) -> httpx.Response:
        await ratelimit.acquire(self._c.redis, self._c.rate_key)
        headers: dict[str, str] = {}
        content: bytes | None = None
        if json_body is not None:
            content = json.dumps(json_body, separators=(",", ":"), default=str).encode()
            headers["Content-Type"] = "application/json"
        try:
            async with self._http(accept) as http:
                response = await http.request(
                    method, path, params=params, content=content, headers=headers
                )
        except httpx.TimeoutException as exc:
            raise LexofficeUnavailableError(
                "Lexware Office hat nicht rechtzeitig geantwortet.", maybe_processed=True
            ) from exc
        except httpx.HTTPError as exc:
            raise LexofficeUnavailableError("Lexware Office ist nicht erreichbar.") from exc
        log.info(
            "lexoffice request",
            extra={"method": method, "path": path, "status": response.status_code},
        )
        return self._raise_for_status(response)

    def _raise_for_status(self, response: httpx.Response) -> httpx.Response:
        status = response.status_code
        if status in (401, 403):
            raise LexofficeAuthError("API Schlüssel abgelehnt.", status_code=status)
        if status == 429:
            raise LexofficeRateLimitedError(
                "Anfragelimit von Lexware Office erreicht.",
                status_code=status,
                retry_after=_retry_after(response),
            )
        if status in (301, 302, 303, 307, 308):
            raise LexofficeRejectedError("Weiterleitung abgelehnt.", status_code=status)
        if status >= 500:
            raise LexofficeUnavailableError(
                f"Lexware Office antwortete mit Status {status}.",
                status_code=status,
                maybe_processed=status == 504,
            )
        if status >= 400:
            issues, trace_id = parse_issues(self._json(response))
            if status == 404:
                raise LexofficeNotFoundError(
                    "Nicht gefunden.", status_code=status, trace_id=trace_id
                )
            if status == 409:
                raise LexofficeConflictError(
                    "Datensatz zwischenzeitlich geändert.", status_code=status, trace_id=trace_id
                )
            raise LexofficeRejectedError(
                "Anfrage abgelehnt.", status_code=status, issues=issues, trace_id=trace_id
            )
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {}

    async def _json_request(self, method: str, path: str, **kw: Any) -> dict[str, Any]:
        body = self._json(await self._request(method, path, **kw))
        self._check_organization(body)
        return body if isinstance(body, dict) else {}

    # Endpoints ------------------------------------------------------------------------

    async def get_profile(self) -> dict[str, Any]:
        return await self._json_request("GET", "/v1/profile")

    async def list_contacts(
        self,
        *,
        page: int = 0,
        size: int = 250,
        email: str | None = None,
        name: str | None = None,
        number: int | None = None,
        customer: bool | None = None,
        vendor: bool | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "size": min(size, 250)}
        for key, value in (("email", email), ("name", name)):
            if value is not None:
                if len(value.strip()) < MIN_FILTER_LENGTH:
                    raise LexofficeValidationError("Filter braucht mindestens drei Zeichen.")
                params[key] = encode_filter(value.strip())
        if number is not None:
            params["number"] = number
        if customer is not None:
            params["customer"] = "true" if customer else "false"
        if vendor is not None:
            params["vendor"] = "true" if vendor else "false"
        return await self._json_request("GET", "/v1/contacts", params=params)

    async def get_contact(self, contact_id: str) -> dict[str, Any]:
        return await self._json_request("GET", f"/v1/contacts/{contact_id}")

    async def create_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._json_request("POST", "/v1/contacts", json_body=payload)

    async def update_contact(self, contact_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._json_request("PUT", f"/v1/contacts/{contact_id}", json_body=payload)

    async def list_voucherlist(
        self,
        voucher_type: str,
        voucher_status: str,
        *,
        page: int = 0,
        size: int = 25,
        updated_date_from: str | None = None,
        created_date_from: str | None = None,
        voucher_number: str | None = None,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "voucherType": voucher_type,
            "voucherStatus": voucher_status,
            "page": page,
            "size": min(size, 250),
        }
        if updated_date_from:
            params["updatedDateFrom"] = updated_date_from
        if created_date_from:
            params["createdDateFrom"] = created_date_from
        if voucher_number:
            params["voucherNumber"] = voucher_number
        if contact_id:
            params["contactId"] = contact_id
        return await self._json_request("GET", "/v1/voucherlist", params=params)

    async def get_invoice(self, invoice_id: str) -> dict[str, Any]:
        return await self._json_request("GET", f"/v1/invoices/{invoice_id}")

    async def create_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``POST /v1/invoices`` without any query: drafts only in this module."""
        return await self._json_request("POST", "/v1/invoices", json_body=payload)

    async def download_invoice_file(
        self,
        invoice_id: str,
        accept: Literal["application/pdf", "*/*", "application/xml"] = "application/pdf",
    ) -> DownloadedFile:
        """``GET /v1/invoices/{id}/file``: host pinned (DNS resolved, SNI kept) unless a test
        transport is plugged in, no redirects, 25 MB ceiling."""
        path = f"/v1/invoices/{invoice_id}/file"
        if TRANSPORT is None:
            pinned = pin_target(self._root, allow_private=self._c.allow_private)
            await ratelimit.acquire(self._c.redis, self._c.rate_key)
            try:
                async with httpx.AsyncClient(
                    timeout=TIMEOUT_SECONDS,
                    follow_redirects=False,
                    headers={"Authorization": f"Bearer {self._c.api_key}", "Accept": accept},
                ) as http:
                    response = await http.get(
                        pinned.url.rstrip("/") + path,
                        headers=pinned.headers,
                        extensions=pinned.extensions,
                    )
            except httpx.TimeoutException as exc:
                raise LexofficeUnavailableError(
                    "Lexware Office hat nicht rechtzeitig geantwortet."
                ) from exc
            except httpx.HTTPError as exc:
                raise LexofficeUnavailableError("Lexware Office ist nicht erreichbar.") from exc
            response = self._raise_for_status(response)
        else:
            response = await self._request("GET", path, accept=accept)
        content = response.content
        if len(content) > MAX_DOWNLOAD_BYTES:
            raise LexofficeUnavailableError("Datei zu groß.", status_code=response.status_code)
        return DownloadedFile(
            content=content,
            content_type=response.headers.get("Content-Type", "application/octet-stream"),
            filename=filename_from_disposition(response.headers.get("Content-Disposition")),
        )
