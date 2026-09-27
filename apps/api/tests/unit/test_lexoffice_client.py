"""lexoffice client (M13-lexoffice): only documented endpoints are called (module doc of
`mhvp.integrations.lexoffice`), payloads are passed through unchanged (never built by this
client), and HTTP errors map to the registered problem codes. Fake transport only
(`httpx.MockTransport`), never a live connection."""

from typing import Any

import httpx
import pytest

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.integrations import lexoffice


class FakeLexoffice:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status_override: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("Authorization") != "Bearer key-1":
            return httpx.Response(401, json={"message": "unauthorized"})
        if self.status_override is not None:
            return httpx.Response(self.status_override, json={"message": "error"})
        path = request.url.path
        if path == "/v1/profile":
            return httpx.Response(200, json={"organizationId": "org-1", "companyName": "Test"})
        if path == "/v1/contacts" and request.method == "POST":
            return httpx.Response(201, json={"id": "contact-1"})
        if path == "/v1/vouchers" and request.method == "POST":
            return httpx.Response(201, json={"id": "voucher-1"})
        if path == "/v1/voucherlist":
            page = int(request.url.params.get("page", "0"))
            return httpx.Response(
                200,
                json={
                    "content": [{"id": f"v-{page}", "voucherNumber": f"R-{page}"}],
                    "paging": {"page": page, "totalPages": 1},
                },
            )
        if path.startswith("/v1/vouchers/"):
            return httpx.Response(200, json={"id": path.rsplit("/", 1)[-1]})
        return httpx.Response(404, json={"message": "unhandled path in fake lexoffice"})


def _client(monkeypatch: pytest.MonkeyPatch, fake: FakeLexoffice) -> lexoffice.LexofficeClient:
    transport = httpx.MockTransport(fake.handler)

    def fake_http(self: lexoffice.LexofficeClient) -> httpx.Client:
        return httpx.Client(
            base_url=self._credentials.base_url,
            transport=transport,
            timeout=5.0,
            headers={"Authorization": f"Bearer {self._credentials.api_key}"},
        )

    monkeypatch.setattr(lexoffice.LexofficeClient, "_client", fake_http)
    return lexoffice.LexofficeClient(
        lexoffice.LexofficeCredentials(api_key="key-1", base_url="https://api.lexware.io")
    )


def test_test_connection_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLexoffice()
    client = _client(monkeypatch, fake)
    profile = client.test_connection()
    assert profile["organizationId"] == "org-1"
    assert fake.requests[0].url.path == "/v1/profile"


def test_bad_key_maps_to_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLexoffice()
    transport = httpx.MockTransport(fake.handler)

    def fake_http(self: lexoffice.LexofficeClient) -> httpx.Client:
        return httpx.Client(base_url=self._credentials.base_url, transport=transport, timeout=5.0)

    monkeypatch.setattr(lexoffice.LexofficeClient, "_client", fake_http)
    client = lexoffice.LexofficeClient(
        lexoffice.LexofficeCredentials(api_key="wrong", base_url="https://api.lexware.io")
    )
    with pytest.raises(ProblemError) as exc:
        client.test_connection()
    assert exc.value.error is ErrorCodes.LEXOFFICE_AUTH


def test_rate_limited_maps_to_rate_limited_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLexoffice()
    fake.status_override = 429
    client = _client(monkeypatch, fake)
    with pytest.raises(ProblemError) as exc:
        client.test_connection()
    assert exc.value.error is ErrorCodes.LEXOFFICE_RATE_LIMITED


def test_create_voucher_passes_payload_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLexoffice()
    client = _client(monkeypatch, fake)
    payload: dict[str, Any] = {"type": "purchaseinvoice", "voucherNumber": "R-1"}
    result = client.create_voucher(payload)
    assert result["id"] == "voucher-1"
    sent = fake.requests[-1]
    assert sent.method == "POST"
    assert sent.url.path == "/v1/vouchers"


def test_create_contact_passes_payload_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLexoffice()
    client = _client(monkeypatch, fake)
    result = client.create_contact({"roles": {"customer": {}}})
    assert result["id"] == "contact-1"


def test_list_voucherlist_passes_paging_and_updated_at_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeLexoffice()
    client = _client(monkeypatch, fake)
    result = client.list_voucherlist(page=0, updated_at_from="2026-01-01T00:00:00Z")
    assert result["content"][0]["id"] == "v-0"
    sent = fake.requests[-1]
    assert sent.url.params["updatedAtFrom"] == "2026-01-01T00:00:00Z"


def test_get_voucher(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeLexoffice()
    client = _client(monkeypatch, fake)
    result = client.get_voucher("v-42")
    assert result["id"] == "v-42"
