"""finAPI Access adapter (M31, read-only stage; docs/BANKING-FINAPI.md).

Small, replaceable aggregator interface plus the finAPI implementation. Endpoints follow the
official documentation checked on 25.09.2026 (WebForm 2.0 import/update, tasks, users, OAuth);
the base URLs are project configuration, not claimed provider defaults. Bank PINs and TANs are
never handled here: authentication happens exclusively inside the provider's web form. Every
provider identity is created with automatic batch updates disabled (isAutoUpdateEnabled=false);
data is fetched only after an explicit user action.
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from mhvp.core.config import Settings


class AggregatorError(Exception):
    """Provider call failed; the sanitized message is safe for run protocols."""


class AggregatorNotConfiguredError(Exception):
    """Missing project configuration: the UI shows 'Bankanbindung noch nicht eingerichtet'."""


@dataclass(frozen=True)
class ProviderAccount:
    id: str
    iban: str | None
    holder_name: str | None
    label: str | None
    account_type: str | None
    currency: str
    balance: str | None
    available: str | None
    balance_date: str | None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderTransaction:
    id: str
    booking_date: str
    value_date: str | None
    amount: str
    currency: str
    counterpart_name: str | None
    counterpart_iban: str | None
    counterpart_bic: str | None
    purpose: str | None
    end_to_end_id: str | None
    mandate_reference: str | None
    creditor_id: str | None
    is_pending: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WebForm:
    id: str
    url: str
    status: str
    bank_connection_id: str | None


@dataclass(frozen=True)
class ProviderTask:
    id: str
    status: str
    bank_connection_id: str | None
    errors: list[str]


class BankingAggregator(Protocol):
    """The replaceable seam: exactly one productive provider in this stage (finAPI)."""

    async def ensure_user(self) -> dict[str, str]: ...
    async def create_import_webform(self, callback_url: str | None) -> WebForm: ...
    async def create_update_webform(
        self, bank_connection_id: str, callback_url: str | None
    ) -> WebForm: ...
    async def get_webform(self, webform_id: str) -> WebForm: ...
    async def start_update(self, bank_connection_id: str) -> ProviderTask: ...
    async def get_task(self, task_id: str) -> ProviderTask: ...
    async def list_accounts(self, bank_connection_id: str) -> list[ProviderAccount]: ...
    async def list_transactions(
        self, account_id: str, min_booking_date: str | None
    ) -> list[ProviderTransaction]: ...
    async def delete_bank_connection(self, bank_connection_id: str) -> None: ...
    async def aclose(self) -> None: ...


def configured(settings: Settings) -> bool:
    return bool(
        settings.banking_finapi_base_url
        and settings.banking_finapi_client_id
        and settings.banking_finapi_client_secret
    )


def user_credentials(raw: str | None) -> dict[str, str] | None:
    """Encrypted per-connection provider identity: {'user_id': ..., 'password': ...}."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if isinstance(data, dict) and data.get("user_id") and data.get("password"):
        return {"user_id": str(data["user_id"]), "password": str(data["password"])}
    return None


class FinApiClient:
    """Thin async client. One instance per request/job; the user identity is per connection,
    never a global identity for every SaaS customer."""

    def __init__(
        self,
        settings: Settings,
        credentials: dict[str, str] | None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not configured(settings):
            raise AggregatorNotConfiguredError("finAPI ist nicht konfiguriert.")
        assert settings.banking_finapi_base_url is not None  # noqa: S101 - configured() above
        self._base = settings.banking_finapi_base_url.rstrip("/")
        assert settings.banking_finapi_client_id is not None  # noqa: S101
        assert settings.banking_finapi_client_secret is not None  # noqa: S101
        self._client_id = settings.banking_finapi_client_id.get_secret_value()
        self._client_secret = settings.banking_finapi_client_secret.get_secret_value()
        self._credentials = credentials
        self._http = httpx.AsyncClient(timeout=45.0, transport=transport)
        self._user_token: str | None = None
        self._client_token: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- OAuth -------------------------------------------------------------------------

    async def _token(self, *, user: bool) -> str:
        if user and self._user_token:
            return self._user_token
        if not user and self._client_token:
            return self._client_token
        data: dict[str, str] = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        if user:
            if not self._credentials:
                raise AggregatorError("Keine Banking-Identität für diese Verbindung hinterlegt.")
            data |= {
                "grant_type": "password",
                "username": self._credentials["user_id"],
                "password": self._credentials["password"],
            }
        else:
            data["grant_type"] = "client_credentials"
        response = await self._http.post(f"{self._base}/oauth/token", data=data)
        if response.status_code != 200:
            raise AggregatorError(f"Token-Abruf fehlgeschlagen (HTTP {response.status_code}).")
        token = str(response.json()["access_token"])
        if user:
            self._user_token = token
        else:
            self._client_token = token
        return token

    async def _call(
        self,
        method: str,
        path: str,
        *,
        user: bool = True,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._token(user=user)
        response = await self._http.request(
            method,
            f"{self._base}{path}",
            json=json_body,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 401:
            # Session expired: renew once; an expired API session never deletes local links.
            if user:
                self._user_token = None
            else:
                self._client_token = None
            token = await self._token(user=user)
            response = await self._http.request(
                method,
                f"{self._base}{path}",
                json=json_body,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            raise AggregatorError(
                f"finAPI {method} {path}: HTTP {response.status_code} {_safe_error(response)}"
            )
        if response.status_code == 204 or not response.content:
            return {}
        return dict(response.json())

    # -- Identity ----------------------------------------------------------------------

    async def ensure_user(self) -> dict[str, str]:
        """Creates the per-connection provider identity with automatic updates disabled."""
        if self._credentials:
            return self._credentials
        user_id = f"mhvp-{uuid.uuid4().hex[:20]}"
        password = uuid.uuid4().hex
        await self._call(
            "POST",
            "/api/v1/users",
            user=False,
            json_body={
                "id": user_id,
                "password": password,
                # Kein automatischer Batch-Abruf: Daten fliessen nur nach Nutzerklick.
                "isAutoUpdateEnabled": False,
            },
        )
        self._credentials = {"user_id": user_id, "password": password}
        return self._credentials

    # -- WebForm 2.0 -------------------------------------------------------------------

    async def create_import_webform(self, callback_url: str | None) -> WebForm:
        body: dict[str, Any] = {"accountTypes": ["CHECKING", "SAVINGS"]}
        if callback_url:
            body["callbacks"] = {"finalised": callback_url}
        data = await self._call("POST", "/api/webForms/bankConnectionImport", json_body=body)
        return _webform(data)

    async def create_update_webform(
        self, bank_connection_id: str, callback_url: str | None
    ) -> WebForm:
        body: dict[str, Any] = {"bankConnectionId": int(bank_connection_id)}
        if callback_url:
            body["callbacks"] = {"finalised": callback_url}
        data = await self._call("POST", "/api/webForms/bankConnectionUpdate", json_body=body)
        return _webform(data)

    async def get_webform(self, webform_id: str) -> WebForm:
        data = await self._call("GET", f"/api/webForms/{webform_id}")
        return _webform(data)

    # -- Update-Tasks ------------------------------------------------------------------

    async def start_update(self, bank_connection_id: str) -> ProviderTask:
        data = await self._call(
            "POST",
            "/api/tasks/backgroundUpdate",
            json_body={"bankConnectionIds": [int(bank_connection_id)]},
        )
        return _task(data)

    async def get_task(self, task_id: str) -> ProviderTask:
        data = await self._call("GET", f"/api/tasks/{task_id}")
        return _task(data)

    # -- Data --------------------------------------------------------------------------

    async def list_accounts(self, bank_connection_id: str) -> list[ProviderAccount]:
        data = await self._call(
            "GET", "/api/v1/accounts", params={"bankConnectionIds": bank_connection_id}
        )
        return [_account(a) for a in data.get("accounts", [])]

    async def list_transactions(
        self, account_id: str, min_booking_date: str | None
    ) -> list[ProviderTransaction]:
        """All pages of one account; documented pagination via page/perPage."""
        rows: list[ProviderTransaction] = []
        page = 1
        while True:
            params: dict[str, Any] = {
                "accountIds": account_id,
                "view": "userView",
                "order": "id,asc",
                "page": page,
                "perPage": 500,
            }
            if min_booking_date:
                params["minBankBookingDate"] = min_booking_date
            data = await self._call("GET", "/api/v1/transactions", params=params)
            rows.extend(_transaction(t) for t in data.get("transactions", []))
            paging = data.get("paging", {})
            if page >= int(paging.get("pageCount", 1)):
                return rows
            page += 1

    async def delete_bank_connection(self, bank_connection_id: str) -> None:
        await self._call("DELETE", f"/api/v1/bankConnections/{bank_connection_id}")


def _safe_error(response: httpx.Response) -> str:
    """Error text without credentials or personal data: first provider error code/message."""
    try:
        errors = response.json().get("errors", [])
        if errors:
            first = errors[0]
            return str(first.get("code") or first.get("message") or "")[:200]
    except ValueError:
        pass
    return ""


def _webform(data: dict[str, Any]) -> WebForm:
    payload = data.get("payload") or {}
    return WebForm(
        id=str(data.get("id", "")),
        url=str(data.get("url", "")),
        status=str(data.get("status", "")),
        bank_connection_id=(
            str(payload.get("bankConnectionId"))
            if payload.get("bankConnectionId") is not None
            else None
        ),
    )


def _task(data: dict[str, Any]) -> ProviderTask:
    return ProviderTask(
        id=str(data.get("id", "")),
        status=str(data.get("status", "")),
        bank_connection_id=(
            str(data.get("bankConnectionId")) if data.get("bankConnectionId") is not None else None
        ),
        errors=[str(e) for e in data.get("errors", [])],
    )


def _account(data: dict[str, Any]) -> ProviderAccount:
    balance = data.get("balance")
    available = data.get("availableFunds")
    return ProviderAccount(
        id=str(data["id"]),
        iban=data.get("iban"),
        holder_name=data.get("accountHolderName"),
        label=data.get("accountName"),
        account_type=str(data.get("accountType") or "") or None,
        currency=str(data.get("currency") or "EUR"),
        balance=str(balance) if balance is not None else None,
        available=str(available) if available is not None else None,
        balance_date=data.get("lastSuccessfulUpdate"),
        raw={k: v for k, v in data.items() if k not in ("iban", "accountHolderName")},
    )


def _transaction(data: dict[str, Any]) -> ProviderTransaction:
    counterpart = data.get("counterpart") or {}
    return ProviderTransaction(
        id=str(data["id"]),
        booking_date=str(data.get("bankBookingDate") or data.get("bookingDate") or ""),
        value_date=data.get("valueDate"),
        amount=str(data["amount"]),
        currency=str(data.get("currency") or "EUR"),
        counterpart_name=counterpart.get("name") or data.get("counterpartName"),
        counterpart_iban=counterpart.get("iban") or data.get("counterpartIban"),
        counterpart_bic=counterpart.get("bic") or data.get("counterpartBic"),
        purpose=data.get("purpose"),
        end_to_end_id=data.get("endToEndReference") or data.get("endToEndId"),
        mandate_reference=data.get("mandateReference"),
        creditor_id=data.get("creditorId"),
        is_pending=not bool(data.get("isBooked", True)),
        raw={"id": data.get("id"), "isBooked": data.get("isBooked", True)},
    )
