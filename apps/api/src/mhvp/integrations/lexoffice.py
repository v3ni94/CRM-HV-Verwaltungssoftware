"""lexoffice public REST API client (M13-lexoffice).

Binding source: `docs/integrations/lexoffice.md` (retrieved 27.09.2026 from
https://developers.lexoffice.io/docs/, which redirects to https://developers.lexware.io/docs/).
Only the endpoints listed there as verified are called:

- ``GET /v1/profile``            connectivity/API key test
- ``POST /v1/contacts``          create a contact
- ``POST /v1/vouchers``          create a voucher (purchase or sales side, payload passthrough)
- ``GET /v1/voucherlist``        list/filter vouchers (voucherType, voucherStatus, paging,
                                 date filters)
- ``GET /v1/vouchers/{id}``      read one voucher
- ``POST /v1/files``             upload a file, returns a file id
- ``POST /v1/invoices``          create a sales invoice (payload passthrough)

The exact JSON body schema for a purchase invoice voucher and for a contact is not fully
documented on the pages this client could read (see docs/integrations/lexoffice.md, "offene
Punkte"); this client therefore never builds that body itself. Callers pass the finished
payload (reviewed by an operator/tax advisor before productive use, rule 0.1.3); this module
only adds authentication, transport, retry free error mapping and request logging. It never
guesses a field name.

No PIN, TAN or bank credential ever passes through this client. The API key is the tenant's
lexoffice application key, stored encrypted (``LexofficeTenantConfig.api_key``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from mhvp.core.problems import ErrorCodes, ProblemError

DEFAULT_BASE_URL = "https://api.lexware.io"
DOCUMENTED_API = "lexoffice public REST API (developers.lexware.io, retrieved 27.09.2026)"
TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class LexofficeCredentials:
    api_key: str
    base_url: str = DEFAULT_BASE_URL


class LexofficeClient:
    """Thin wrapper; every method maps to exactly one documented endpoint (see module doc)."""

    def __init__(self, credentials: LexofficeCredentials) -> None:
        self._credentials = credentials

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._credentials.base_url.rstrip("/"),
            timeout=TIMEOUT_SECONDS,
            headers={
                "Authorization": f"Bearer {self._credentials.api_key}",
                "Accept": "application/json",
            },
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            with self._client() as client:
                response = client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProblemError(
                ErrorCodes.LEXOFFICE_UNAVAILABLE,
                detail="lexoffice hat nicht rechtzeitig geantwortet.",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProblemError(
                ErrorCodes.LEXOFFICE_UNAVAILABLE, detail="lexoffice ist nicht erreichbar."
            ) from exc
        if response.status_code in (401, 403):
            raise ProblemError(ErrorCodes.LEXOFFICE_AUTH)
        if response.status_code == 429:
            raise ProblemError(ErrorCodes.LEXOFFICE_RATE_LIMITED)
        if response.status_code >= 400:
            raise ProblemError(
                ErrorCodes.LEXOFFICE_UNAVAILABLE,
                detail=f"lexoffice antwortete mit Status {response.status_code}.",
                developer_message=response.text[:500],
            )
        return response

    def test_connection(self) -> dict[str, Any]:
        """``GET /v1/profile``: valid credentials answer with the organization profile."""
        return dict(self._request("GET", "/v1/profile").json())

    def create_contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``POST /v1/contacts``. ``payload`` is passed through unchanged (see module doc)."""
        return dict(self._request("POST", "/v1/contacts", json=payload).json())

    def create_voucher(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``POST /v1/vouchers``. ``payload`` is passed through unchanged (see module doc)."""
        return dict(self._request("POST", "/v1/vouchers", json=payload).json())

    def create_invoice(self, payload: dict[str, Any], *, finalize: bool = False) -> dict[str, Any]:
        """``POST /v1/invoices[?finalize=true]``. ``payload`` is passed through unchanged."""
        params = {"finalize": "true"} if finalize else None
        return dict(self._request("POST", "/v1/invoices", json=payload, params=params).json())

    def upload_file(self, filename: str, content: bytes, content_type: str) -> str:
        """``POST /v1/files``, returns the ``id`` of the uploaded file."""
        files = {"file": (filename, content, content_type)}
        data = {"type": "voucher"}
        body = self._request("POST", "/v1/files", files=files, data=data).json()
        return str(body["id"])

    def list_voucherlist(
        self,
        voucher_type: str,
        voucher_status: str = "any",
        *,
        page: int = 0,
        size: int = 25,
        updated_date_from: str | None = None,
        created_date_from: str | None = None,
        voucher_number: str | None = None,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        """``GET /v1/voucherlist``. ``voucherType`` and ``voucherStatus`` are mandatory per the
        vendor documentation (verified 28.09.2026); date filters are ``yyyy-MM-dd`` and named
        ``updatedDateFrom``/``createdDateFrom`` (``updatedAtFrom`` does not exist)."""
        params: dict[str, Any] = {
            "voucherType": voucher_type,
            "voucherStatus": voucher_status,
            "page": page,
            "size": size,
        }
        if updated_date_from:
            params["updatedDateFrom"] = updated_date_from
        if created_date_from:
            params["createdDateFrom"] = created_date_from
        if voucher_number:
            params["voucherNumber"] = voucher_number
        if contact_id:
            params["contactId"] = contact_id
        return dict(self._request("GET", "/v1/voucherlist", params=params).json())

    def get_voucher(self, voucher_id: str) -> dict[str, Any]:
        """``GET /v1/vouchers/{id}``."""
        return dict(self._request("GET", f"/v1/vouchers/{voucher_id}").json())
