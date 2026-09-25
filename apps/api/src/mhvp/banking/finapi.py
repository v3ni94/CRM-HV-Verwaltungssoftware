"""FinApiBankingProvider: read only finAPI Access integration behind the banking
connector abstraction (`mhvp.banking.connectors.BankConnector`).

Binding source: `docs/integrations/finapi.md` (API version, retrieval date, verified
endpoints and fields). Every method here calls only an endpoint listed there as verified.
An endpoint marked "zu prüfen" (not verified against the official documentation) is not
called; the corresponding method raises :class:`FinApiNotVerifiedError` instead of guessing
a path or field name (master prompt section 3, rule 0.1.3).

No PIN or TAN ever passes through this client: bank login and account authorization happen
exclusively in the finAPI WebForm the browser is redirected to (section 6 of the banking
master prompt). This client only creates the WebForm, polls its status, and afterwards reads
accounts, balances and transactions of the finAPI bank connection it created.

Local development and the test suite use `httpx.MockTransport`; this module never claims a
live connection is available, and refuses to run against a `base_url` that is not configured
per tenant (`FinApiTenantConfig`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from mhvp.banking.camt import RawTransaction
from mhvp.banking.connectors import (
    BankAccountInfo,
    BankSearchResult,
    ConnectionResult,
    WebFormHandle,
)
from mhvp.core.problems import ErrorCodes, ProblemError

# API version this client was written against (docs/integrations/finapi.md, retrieved
# 25.09.2026). Never call a differently versioned host without re-checking that document
# (banking master prompt Q4).
API_VERSION_DOCUMENTED = "finAPI Access API (2024, client's activated version) / WebForm 2.0"


class FinApiNotVerifiedError(ProblemError):
    """Raised instead of guessing an endpoint or field that `docs/integrations/finapi.md`
    marks as "zu prüfen"."""

    def __init__(self, what: str) -> None:
        super().__init__(
            ErrorCodes.FINAPI_NOT_VERIFIED,
            detail=(
                f"{what} ist in docs/integrations/finapi.md als zu prüfen markiert und wird "
                "nicht ungeprüft aufgerufen."
            ),
        )


@dataclass(frozen=True)
class FinApiCredentials:
    client_id: str
    client_secret: str
    base_url: str
    mandator_id: str | None = None


@dataclass(frozen=True)
class FinApiWebForm:
    web_form_id: str
    url: str
    status: str
    finapi_bank_connection_id: str | None


@dataclass(frozen=True)
class FinApiAccount:
    account_id: str
    iban: str | None
    account_holder_name: str | None
    account_type: str | None
    account_name: str | None
    balance_booked: str | None
    balance_available: str | None
    balance_currency: str | None
    balance_as_of: str | None


@dataclass(frozen=True)
class FinApiTransaction:
    transaction_id: str
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
    is_removed: bool = False


class FinApiClient:
    """Thin HTTP client for the finAPI Access endpoints verified in
    `docs/integrations/finapi.md`. `transport` lets tests inject `httpx.MockTransport`."""

    def __init__(
        self, credentials: FinApiCredentials, *, transport: httpx.BaseTransport | None = None
    ):
        self._credentials = credentials
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._credentials.base_url, transport=self._transport, timeout=20.0
        )

    def _client_token(self) -> str:
        """POST /oauth/token, grant_type=client_credentials (verified, docs section 1)."""
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        with self._client() as client:
            response = client.post(
                "/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._credentials.client_id,
                    "client_secret": self._credentials.client_secret,
                },
            )
        _raise_for_status(response, "Token-Abruf")
        body = response.json()
        self._token = body["access_token"]
        self._token_expires_at = time.monotonic() + float(body.get("expires_in", 3599)) - 30
        return self._token

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._client_token()}"}
        if self._credentials.mandator_id:
            # finAPI application/mandator concept (docs/integrations/finapi.md, "zu prüfen"):
            # the exact header or path segment for multi-mandator setups is not verified yet,
            # so it is passed as a plain custom header only for later inspection, never relied
            # on to select a mandator.
            headers["X-MHVP-Mandator-Hint"] = self._credentials.mandator_id
        return headers

    def create_bank_connection_import_web_form(
        self, *, account_type_ids: list[int] | None = None
    ) -> FinApiWebForm:
        """POST /api/webForms/bankConnectionImport (verified, docs section 2)."""
        payload: dict[str, Any] = {}
        if account_type_ids:
            payload["accountTypeIds"] = account_type_ids
        with self._client() as client:
            response = client.post(
                "/api/webForms/bankConnectionImport", json=payload, headers=self._auth_headers()
            )
        _raise_for_status(response, "WebForm-Erstellung")
        body = response.json()
        return FinApiWebForm(
            web_form_id=str(body["id"]),
            url=body["url"],
            status=body["status"],
            finapi_bank_connection_id=(
                str(body.get("payload", {}).get("bankConnectionId"))
                if body.get("payload", {}).get("bankConnectionId") is not None
                else None
            ),
        )

    def get_web_form(self, web_form_id: str) -> FinApiWebForm:
        """GET /api/webForms/{id} (verified, docs section 2)."""
        with self._client() as client:
            response = client.get(f"/api/webForms/{web_form_id}", headers=self._auth_headers())
        _raise_for_status(response, "WebForm-Status")
        body = response.json()
        return FinApiWebForm(
            web_form_id=str(body["id"]),
            url=body.get("url", ""),
            status=body["status"],
            finapi_bank_connection_id=(
                str(body.get("payload", {}).get("bankConnectionId"))
                if body.get("payload", {}).get("bankConnectionId") is not None
                else None
            ),
        )

    def get_bank_connection(self, bank_connection_id: str) -> dict[str, Any]:
        """GET /bankConnections/{id} (verified, docs section 2)."""
        with self._client() as client:
            response = client.get(
                f"/bankConnections/{bank_connection_id}", headers=self._auth_headers()
            )
        _raise_for_status(response, "Bankverbindungsstatus")
        return dict(response.json())

    def list_accounts(self, *, bank_connection_id: str | None = None) -> list[FinApiAccount]:
        """GET /accounts (verified, docs section 2). Field names for balances and IBAN beyond
        `id` are marked "zu prüfen" in docs/integrations/finapi.md, so this method reads them
        defensively (missing fields become `None`) instead of asserting a schema."""
        params: dict[str, Any] = {}
        if bank_connection_id:
            params["bankConnectionId"] = bank_connection_id
        with self._client() as client:
            response = client.get("/accounts", params=params, headers=self._auth_headers())
        _raise_for_status(response, "Kontenabruf")
        body = response.json()
        accounts = body.get("accounts", body if isinstance(body, list) else [])
        return [_account_from_json(a) for a in accounts]

    def list_transactions(
        self, *, account_ids: list[str] | None = None, page: int = 1, per_page: int = 500
    ) -> tuple[list[FinApiTransaction], bool]:
        """GET /transactions (verified, docs section 2). Pagination field names and the
        distinction between booked and pending transactions are marked "zu prüfen"; this
        method reads a conservative `page`/`perPage` pair and treats a full page as "there may
        be more", never asserting a total count."""
        params: dict[str, Any] = {"page": page, "perPage": per_page}
        if account_ids:
            params["accountIds"] = ",".join(account_ids)
        with self._client() as client:
            response = client.get("/transactions", params=params, headers=self._auth_headers())
        _raise_for_status(response, "Umsatzabruf")
        body = response.json()
        raw = body.get("transactions", body if isinstance(body, list) else [])
        items = [_transaction_from_json(t) for t in raw]
        has_more = len(raw) >= per_page
        return items, has_more

    def trigger_update(self, bank_connection_id: str) -> str:
        """Not verified: docs/integrations/finapi.md lists the update endpoint under 'zu
        prüfen' (the navigation names "Update a Bank Connection" but the concrete method,
        path and body are not confirmed from the fetched pages). Raises instead of guessing."""
        raise FinApiNotVerifiedError("Der Update-Endpunkt für eine Bankverbindung")

    def disconnect(self, bank_connection_id: str) -> None:
        """Not verified: the delete/deactivate endpoint for a bank connection is marked "zu
        prüfen" in docs/integrations/finapi.md. Disconnect therefore only removes the local
        link (see routers.disconnect) and reports that the provider side is unconfirmed."""
        raise FinApiNotVerifiedError("Der Trenn-/Löschendpunkt für eine Bankverbindung")


def _account_from_json(a: dict[str, Any]) -> FinApiAccount:
    return FinApiAccount(
        account_id=str(a.get("id")),
        iban=a.get("iban"),
        account_holder_name=a.get("accountHolderName"),
        account_type=a.get("accountType") or a.get("accountTypeName"),
        account_name=a.get("accountName") or a.get("name"),
        balance_booked=_to_str(a.get("balance")),
        balance_available=_to_str(a.get("availableFunds") or a.get("availableBalance")),
        balance_currency=a.get("currency"),
        balance_as_of=a.get("balanceDate")
        or a.get("accountUpdateStatus", {}).get("lastUpdateTime"),
    )


def _transaction_from_json(t: dict[str, Any]) -> FinApiTransaction:
    return FinApiTransaction(
        transaction_id=str(t.get("id")),
        booking_date=str(t.get("bankBookingDate") or t.get("valueDate") or t.get("bookingDate")),
        value_date=t.get("valueDate"),
        amount=_to_str(t.get("amount")) or "0",
        currency=t.get("currency") or "EUR",
        counterpart_name=t.get("counterpartName"),
        counterpart_iban=t.get("counterpartIban"),
        counterpart_bic=t.get("counterpartBic"),
        purpose=t.get("purpose"),
        end_to_end_id=t.get("endToEndId"),
        mandate_reference=t.get("mandateReference"),
        creditor_id=t.get("creditorId"),
        is_removed=bool(t.get("isRemoved", False)),
    )


def _to_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _raise_for_status(response: httpx.Response, action: str) -> None:
    if response.status_code >= 400:
        raise ProblemError(
            ErrorCodes.FINAPI_UNAVAILABLE,
            detail=f"{action} bei finAPI fehlgeschlagen (HTTP {response.status_code}).",
            developer_message=response.text[:500],
        )


def _finapi_transaction_to_raw(t: FinApiTransaction) -> RawTransaction:
    """Shared mapping finAPI -> `RawTransaction` (6.9.7): the finAPI transaction id becomes the
    ``bank_reference`` prefixed with ``finapi:`` so dedup (`mhvp.banking.services`, D05) works
    the same way as for a file import. Nothing here is synthesized: a field the provider did
    not send stays `None`."""
    return RawTransaction(
        bank_reference=f"finapi:{t.transaction_id}",
        booking_date=datetime.fromisoformat(t.booking_date).date(),
        value_date=datetime.fromisoformat(t.value_date).date() if t.value_date else None,
        amount=Decimal(t.amount),
        currency=t.currency,
        counterpart_name=t.counterpart_name,
        counterpart_iban=t.counterpart_iban,
        counterpart_bic=t.counterpart_bic,
        purpose=t.purpose,
        end_to_end_id=t.end_to_end_id,
        mandate_reference=t.mandate_reference,
        creditor_id=t.creditor_id,
        transaction_code=None,
        raw={"finapi_transaction_id": t.transaction_id},
    )


class FinApiConnector:
    """`mhvp.banking.connectors.BankConnector` implementation on top of `FinApiClient`
    (Stage 1, M11-finapi rebuild). Read only PSD2/XS2A via the finAPI aggregator; no PIN or
    TAN ever passes through here (see module docstring and
    `docs/rules/M11-04-no-credentials-in-crm.md`)."""

    def __init__(self, client: FinApiClient) -> None:
        self._client = client

    def search_bank(self, query: str) -> list[BankSearchResult]:
        """Not verified: `docs/integrations/finapi.md` documents no separate bank search
        endpoint for the WebForm 2.0 model. Bank selection (by name, IBAN or BIC) happens
        inside the finAPI WebForm itself once `start_connection` opens it, not via a call from
        this backend, so this method raises instead of guessing an endpoint (rule 0.1.3)."""
        raise FinApiNotVerifiedError("Eine serverseitige Banksuche")

    def start_connection(self, bank: BankSearchResult) -> WebFormHandle:
        """`bank.external_ref` is only descriptive here (no verified bank-selection endpoint,
        see `search_bank`); the operator picks the bank inside the WebForm that opens."""
        web_form = self._client.create_bank_connection_import_web_form()
        return WebFormHandle(
            external_ref=web_form.web_form_id, url=web_form.url, status=web_form.status
        )

    def complete_connection(self, external_ref: str) -> ConnectionResult:
        """Re-checks the WebForm and, once finished, the bank connection with the tenant's own
        credentials (master prompt section 6): a browser return from the WebForm alone is
        never trusted as proof of success."""
        web_form = self._client.get_web_form(external_ref)
        if web_form.status != "FINISHED" or not web_form.finapi_bank_connection_id:
            return ConnectionResult(
                status=web_form.status, connection_ref=None, consent_valid_until=None
            )
        details = self._client.get_bank_connection(web_form.finapi_bank_connection_id)
        error = details.get("errorMessage")
        return ConnectionResult(
            status=str(details.get("status") or web_form.status),
            connection_ref=web_form.finapi_bank_connection_id,
            consent_valid_until=None,  # not verified: no consent-expiry field confirmed yet
            error_message=error,
        )

    def list_accounts(self, connection_ref: str | None = None) -> list[BankAccountInfo]:
        accounts = self._client.list_accounts(bank_connection_id=connection_ref)
        return [
            BankAccountInfo(
                iban=a.iban or "",
                currency=a.balance_currency or "EUR",
                external_account_id=a.account_id,
                account_holder_name=a.account_holder_name,
                account_type=a.account_type,
                account_name=a.account_name,
                balance_booked=a.balance_booked,
                balance_available=a.balance_available,
                balance_currency=a.balance_currency,
                balance_as_of=a.balance_as_of,
            )
            for a in accounts
        ]

    def fetch_transactions(
        self, account: BankAccountInfo, since: date, until: date
    ) -> list[RawTransaction]:
        """Fetches every page finAPI returns for this account and stores it as delivered; the
        `since`/`until` window is not filtered here because the verified `/transactions`
        endpoint documents no confirmed date parameter (see docs/integrations/finapi.md,
        "zu prüfen") -- filtering by date happens by the caller on the returned rows, nothing
        is synthesized to fill a gap the provider does not cover (rule 0.1.3)."""
        if account.external_account_id is None:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Konto ohne finAPI-Kontoreferenz.")
        page = 1
        out: list[RawTransaction] = []
        while True:
            items, has_more = self._client.list_transactions(
                account_ids=[account.external_account_id], page=page
            )
            out.extend(_finapi_transaction_to_raw(t) for t in items if not t.is_removed)
            if not has_more:
                break
            page += 1
        return out

    def refresh_consent(self, connection_ref: str) -> WebFormHandle:
        """Re-authorization is only reachable through a fresh WebForm (docs/integrations/
        finapi.md, "Update a Bank Connection" is not verified); `connection_ref` (the finAPI
        bank connection id) is accepted for interface symmetry but the new WebForm is not tied
        to it beyond what the operator does inside it."""
        web_form = self._client.create_bank_connection_import_web_form()
        return WebFormHandle(
            external_ref=web_form.web_form_id, url=web_form.url, status=web_form.status
        )
