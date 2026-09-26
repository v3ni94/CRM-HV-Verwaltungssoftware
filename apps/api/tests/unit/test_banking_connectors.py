"""Stage 1, M11-finapi rebuild: `BankConnector` protocol seam, `FinApiConnector` on top of the
existing `FinApiClient`, and `FileConnector`/`UnconfiguredConnector` staying within it. Fake
finAPI transport only (`httpx.MockTransport`), never a live connection."""

from datetime import date
from typing import Any

import httpx
import pytest

from mhvp.banking import finapi as finapi_client
from mhvp.banking.connectors import (
    BankAccountInfo,
    BankConnector,
    BankSearchResult,
    ConnectorNotConfiguredError,
    ConnectorNotSupportedError,
    FileConnector,
    UnconfiguredConnector,
)
from mhvp.core.problems import ProblemError

WEB_FORM_ID = "wf-1"
BANK_CONNECTION_ID = "9001"
ACCOUNT_ID = "1001"
IBAN = "DE02120300000000202051"


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/oauth/token":
        return httpx.Response(200, json={"access_token": "t-1", "expires_in": 3599})
    if path == "/api/webForms/bankConnectionImport":
        return httpx.Response(
            200,
            json={
                "id": WEB_FORM_ID,
                "url": "https://webform.finapi.io/wf-1",
                "status": "AWAITING_AUTHORIZATION",
                "payload": {},
            },
        )
    if path == f"/api/webForms/{WEB_FORM_ID}":
        return httpx.Response(
            200,
            json={
                "id": WEB_FORM_ID,
                "url": "https://webform.finapi.io/wf-1",
                "status": "FINISHED",
                "payload": {"bankConnectionId": BANK_CONNECTION_ID},
            },
        )
    if path == f"/bankConnections/{BANK_CONNECTION_ID}":
        return httpx.Response(200, json={"id": BANK_CONNECTION_ID, "status": "READY"})
    if path == "/accounts":
        return httpx.Response(
            200,
            json={
                "accounts": [
                    {
                        "id": ACCOUNT_ID,
                        "iban": IBAN,
                        "accountHolderName": "GdWE Testweg",
                        "accountType": "checking",
                        "accountName": "Hausgeldkonto",
                        "balance": "1234.56",
                        "currency": "EUR",
                    }
                ]
            },
        )
    if path == "/transactions":
        account_ids = (request.url.params.get("accountIds") or "").split(",")
        if ACCOUNT_ID in account_ids:
            return httpx.Response(
                200,
                json={
                    "transactions": [
                        {
                            "id": "tx-1",
                            "bankBookingDate": "2026-02-01",
                            "amount": "700.00",
                            "currency": "EUR",
                            "counterpartName": "Zahler A",
                            "purpose": "Hausgeld Februar",
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"transactions": []})
    return httpx.Response(404, json={"detail": "unhandled path in fake finAPI"})


@pytest.fixture
def connector(monkeypatch: pytest.MonkeyPatch) -> finapi_client.FinApiConnector:
    transport = httpx.MockTransport(_handler)

    def fake_client(self: finapi_client.FinApiClient) -> httpx.Client:
        return httpx.Client(base_url=self._credentials.base_url, transport=transport, timeout=5.0)

    monkeypatch.setattr(finapi_client.FinApiClient, "_client", fake_client)
    client = finapi_client.FinApiClient(
        finapi_client.FinApiCredentials(
            client_id="cid", client_secret="csecret", base_url="https://sandbox.finapi.io"
        )
    )
    return finapi_client.FinApiConnector(client)


def test_finapi_connector_satisfies_protocol(connector: finapi_client.FinApiConnector) -> None:
    assert isinstance(connector, BankConnector)


def test_search_bank_raises_not_verified(connector: finapi_client.FinApiConnector) -> None:
    """No verified bank-search endpoint (docs/integrations/finapi.md): never invented."""
    with pytest.raises(finapi_client.FinApiNotVerifiedError):
        connector.search_bank("Sparkasse")


def test_start_and_complete_connection(connector: finapi_client.FinApiConnector) -> None:
    handle = connector.start_connection(BankSearchResult(name="Sparkasse", external_ref="n/a"))
    assert handle.external_ref == WEB_FORM_ID
    assert handle.url.startswith("https://webform.finapi.io/")
    assert handle.status == "AWAITING_AUTHORIZATION"

    result = connector.complete_connection(handle.external_ref)
    assert result.status == "READY"
    assert result.connection_ref == BANK_CONNECTION_ID
    assert result.error_message is None


def test_complete_connection_still_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    def pending_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "t-1", "expires_in": 3599})
        if request.url.path == f"/api/webForms/{WEB_FORM_ID}":
            return httpx.Response(
                200,
                json={
                    "id": WEB_FORM_ID,
                    "url": "https://webform.finapi.io/wf-1",
                    "status": "AWAITING_AUTHORIZATION",
                    "payload": {},
                },
            )
        return httpx.Response(404, json={"detail": "unhandled"})

    transport = httpx.MockTransport(pending_handler)

    def fake_client(self: finapi_client.FinApiClient) -> httpx.Client:
        return httpx.Client(base_url=self._credentials.base_url, transport=transport, timeout=5.0)

    monkeypatch.setattr(finapi_client.FinApiClient, "_client", fake_client)
    client = finapi_client.FinApiClient(
        finapi_client.FinApiCredentials(
            client_id="cid", client_secret="csecret", base_url="https://sandbox.finapi.io"
        )
    )
    connector = finapi_client.FinApiConnector(client)
    result = connector.complete_connection(WEB_FORM_ID)
    assert result.status == "AWAITING_AUTHORIZATION"
    assert result.connection_ref is None


def test_list_accounts_maps_fields(connector: finapi_client.FinApiConnector) -> None:
    accounts = connector.list_accounts(connection_ref=BANK_CONNECTION_ID)
    assert len(accounts) == 1
    account = accounts[0]
    assert account.iban == IBAN
    assert account.external_account_id == ACCOUNT_ID
    assert account.balance_booked == "1234.56"


def test_fetch_transactions_paginates_and_maps_bank_reference(
    connector: finapi_client.FinApiConnector,
) -> None:
    account = BankAccountInfo(iban=IBAN, external_account_id=ACCOUNT_ID)
    txs = connector.fetch_transactions(account, since=date(2026, 1, 1), until=date(2026, 3, 1))
    assert len(txs) == 1
    assert txs[0].bank_reference == "finapi:tx-1"
    assert str(txs[0].amount) == "700.00"


def test_fetch_transactions_requires_external_account_id(
    connector: finapi_client.FinApiConnector,
) -> None:
    account = BankAccountInfo(iban=IBAN)
    with pytest.raises(ProblemError):
        connector.fetch_transactions(account, since=date(2026, 1, 1), until=date(2026, 3, 1))


def test_refresh_consent_opens_new_web_form(connector: finapi_client.FinApiConnector) -> None:
    handle = connector.refresh_consent(BANK_CONNECTION_ID)
    assert handle.external_ref == WEB_FORM_ID
    assert handle.status == "AWAITING_AUTHORIZATION"


# --- FileConnector / UnconfiguredConnector stay on the same seam ------------------------


def test_file_connector_satisfies_protocol() -> None:
    assert isinstance(FileConnector(), BankConnector)


def test_file_connector_has_no_online_banking() -> None:
    file_connector = FileConnector()
    with pytest.raises(ConnectorNotSupportedError):
        file_connector.search_bank("Sparkasse")
    with pytest.raises(ConnectorNotSupportedError):
        file_connector.list_accounts()
    with pytest.raises(ConnectorNotSupportedError):
        file_connector.fetch_transactions(
            BankAccountInfo(iban=IBAN), since=date(2026, 1, 1), until=date(2026, 2, 1)
        )


def test_unconfigured_connector_satisfies_protocol_and_refuses() -> None:
    connector: Any = UnconfiguredConnector("fints")
    assert isinstance(connector, BankConnector)
    with pytest.raises(ConnectorNotConfiguredError):
        connector.search_bank("Sparkasse")
    with pytest.raises(ConnectorNotConfiguredError):
        connector.list_accounts()
