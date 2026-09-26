"""finAPI client (M11-01, operator decision 26.09.2026): OAuth2 client credentials plus user
token per connection, technical user creation with auto update off, date bounded transaction
listing with idempotent mapping to NUMERIC amounts, and HTTP error mapping to registered
problem codes. Fake transport only (`httpx.MockTransport`), never a live connection."""

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from mhvp.banking import finapi as finapi_client
from mhvp.banking.connectors import BankAccountInfo
from mhvp.core.problems import ErrorCodes, ProblemError


class FakeFinApi:
    """Records every request so tests can assert which grant and which parameters were used."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.token_grants: list[str] = []
        self.status_override: int | None = None
        self.headers_override: dict[str, str] = {}
        self.page_count = 1

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/oauth/token":
            form = dict(httpx.QueryParams(request.content.decode()))
            self.token_grants.append(form["grant_type"])
            if form["grant_type"] == "password":
                if form.get("username") != "u-1" or form.get("password") != "pw-1":
                    return httpx.Response(401, json={"errors": [{"message": "bad user"}]})
                return httpx.Response(200, json={"access_token": "user-token", "expires_in": 3599})
            return httpx.Response(200, json={"access_token": "client-token", "expires_in": 3599})
        if self.status_override is not None:
            return httpx.Response(
                self.status_override, json={"errors": []}, headers=self.headers_override
            )
        if path == "/users":
            return httpx.Response(
                201, json={"id": "u-1", "password": "pw-1", "isAutoUpdateEnabled": False}
            )
        if path == "/transactions":
            page = int(request.url.params.get("page", "1"))
            return httpx.Response(
                200,
                json={
                    "transactions": [
                        {
                            "id": f"tx-{page}",
                            "bankBookingDate": "2026-02-01",
                            "valueDate": "2026-02-02",
                            "amount": "700.10",
                            "currency": "EUR",
                            "counterpartName": "Zahler A",
                            "counterpartIban": "DE02120300000000202051",
                            "purpose": "Hausgeld Februar",
                        },
                        {
                            "id": f"old-{page}",
                            "bankBookingDate": "2025-12-31",
                            "amount": "-12.34",
                            "currency": "EUR",
                        },
                    ],
                    "paging": {"page": page, "perPage": 500, "pageCount": self.page_count},
                },
            )
        return httpx.Response(404, json={"detail": "unhandled path in fake finAPI"})


def _client(
    monkeypatch: pytest.MonkeyPatch, fake: FakeFinApi, **creds: Any
) -> finapi_client.FinApiClient:
    transport = httpx.MockTransport(fake.handler)

    def fake_http(self: finapi_client.FinApiClient) -> httpx.Client:
        return httpx.Client(base_url=self._credentials.base_url, transport=transport, timeout=5.0)

    monkeypatch.setattr(finapi_client.FinApiClient, "_client", fake_http)
    return finapi_client.FinApiClient(
        finapi_client.FinApiCredentials(
            client_id="cid", client_secret="csecret", base_url="https://sandbox.finapi.io", **creds
        )
    )


def test_client_token_cached_and_used_without_user(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeFinApi()
    client = _client(monkeypatch, fake)
    client.list_transactions(account_ids=["1"])
    client.list_transactions(account_ids=["1"])
    assert fake.token_grants == ["client_credentials"]  # cached after the first call
    auth = [r.headers["Authorization"] for r in fake.requests if r.url.path == "/transactions"]
    assert auth == ["Bearer client-token", "Bearer client-token"]


def test_create_user_uses_client_token_and_disables_auto_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeFinApi()
    client = _client(monkeypatch, fake)
    user = client.create_user()
    assert user == finapi_client.FinApiUser(user_id="u-1", password="pw-1")
    request = next(r for r in fake.requests if r.url.path == "/users")
    assert request.headers["Authorization"] == "Bearer client-token"
    assert b'"isAutoUpdateEnabled":false' in request.content.replace(b" ", b"")


def test_user_token_password_grant_for_data_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeFinApi()
    client = _client(monkeypatch, fake, user_id="u-1", user_password="pw-1")
    assert client.has_user
    client.list_transactions(account_ids=["1"])
    client.list_transactions(account_ids=["1"])
    assert fake.token_grants == ["password"]
    request = next(r for r in fake.requests if r.url.path == "/transactions")
    assert request.headers["Authorization"] == "Bearer user-token"
    token_request = next(r for r in fake.requests if r.url.path == "/oauth/token")
    form = dict(httpx.QueryParams(token_request.content.decode()))
    assert form["username"] == "u-1"
    assert form["password"] == "pw-1"


def test_wrong_user_credentials_map_to_auth_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeFinApi()
    client = _client(monkeypatch, fake, user_id="u-1", user_password="wrong")
    with pytest.raises(ProblemError) as exc:
        client.list_transactions(account_ids=["1"])
    assert exc.value.error is ErrorCodes.FINAPI_AUTH


def test_list_transactions_sends_date_bounds_and_reads_page_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeFinApi()
    fake.page_count = 2
    client = _client(monkeypatch, fake)
    items, has_more = client.list_transactions(
        account_ids=["1"],
        min_booking_date=date(2026, 1, 15),
        max_booking_date=date(2026, 2, 28),
    )
    request = next(r for r in fake.requests if r.url.path == "/transactions")
    assert request.url.params["minBankBookingDate"] == "2026-01-15"
    assert request.url.params["maxBankBookingDate"] == "2026-02-28"
    assert request.url.params["accountIds"] == "1"
    assert has_more is True
    assert len(items) == 2
    _, has_more_last = client.list_transactions(account_ids=["1"], page=2)
    assert has_more_last is False


def test_connector_maps_amounts_to_decimal_and_filters_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeFinApi()
    connector = finapi_client.FinApiConnector(_client(monkeypatch, fake))
    account = BankAccountInfo(iban="DE02120300000000202051", external_account_id="1")
    txs = connector.fetch_transactions(account, since=date(2026, 1, 1), until=date(2026, 2, 28))
    assert [t.bank_reference for t in txs] == ["finapi:tx-1"]  # old-1 is outside the range
    tx = txs[0]
    assert isinstance(tx.amount, Decimal)
    assert tx.amount == Decimal("700.10")
    assert tx.booking_date == date(2026, 2, 1)
    assert tx.value_date == date(2026, 2, 2)
    assert tx.counterpart_iban == "DE02120300000000202051"
    assert tx.raw == {"finapi_transaction_id": "tx-1"}


@pytest.mark.parametrize(
    ("status", "headers", "code", "retry_after"),
    [
        (401, {}, ErrorCodes.FINAPI_AUTH, None),
        (403, {}, ErrorCodes.FINAPI_AUTH, None),
        (429, {"Retry-After": "7"}, ErrorCodes.FINAPI_RATE_LIMITED, "7"),
        (500, {}, ErrorCodes.FINAPI_UNAVAILABLE, None),
        (422, {}, ErrorCodes.FINAPI_UNAVAILABLE, None),
    ],
)
def test_http_errors_map_to_problem_codes(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    headers: dict[str, str],
    code: Any,
    retry_after: str | None,
) -> None:
    fake = FakeFinApi()
    fake.status_override = status
    fake.headers_override = headers
    client = _client(monkeypatch, fake)
    with pytest.raises(ProblemError) as exc:
        client.list_accounts()
    assert exc.value.error is code
    if retry_after is not None:
        assert exc.value.extensions == {"retry_after": retry_after}


def test_transport_error_maps_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    transport = httpx.MockTransport(broken)

    def fake_http(self: finapi_client.FinApiClient) -> httpx.Client:
        return httpx.Client(base_url=self._credentials.base_url, transport=transport)

    monkeypatch.setattr(finapi_client.FinApiClient, "_client", fake_http)
    client = finapi_client.FinApiClient(
        finapi_client.FinApiCredentials(
            client_id="cid", client_secret="csecret", base_url="https://sandbox.finapi.io"
        )
    )
    with pytest.raises(ProblemError) as exc:
        client.list_accounts()
    assert exc.value.error is ErrorCodes.FINAPI_UNAVAILABLE


def test_default_base_url_by_data_center() -> None:
    kwargs = {"sandbox_url": "https://sandbox.finapi.io/", "live_url": "https://live.finapi.io"}
    assert finapi_client.default_base_url(True, **kwargs) == "https://sandbox.finapi.io"
    assert finapi_client.default_base_url(False, **kwargs) == "https://live.finapi.io"
