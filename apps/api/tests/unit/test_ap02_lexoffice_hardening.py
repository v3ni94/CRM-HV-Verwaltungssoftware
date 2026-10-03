"""AP02: lexoffice hardening (GAL-202 key only to the vendor, GAL-203 no vendor data in
problem answers and Retry-After, GAL-201 timeout of a write is marked "maybe processed").
Each attack path is replayed against a fake transport; no network call."""

from __future__ import annotations

import httpx
import pytest

from mhvp.core.config import Environment
from mhvp.core.problems import ErrorCodes, ProblemError, problem_response
from mhvp.integrations import lexoffice

PII = "Erika Mustermann, DE89370400440532013000, erika@example.org"


def _client(monkeypatch: pytest.MonkeyPatch, handler: object) -> lexoffice.LexofficeClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]

    def fake_http(self: lexoffice.LexofficeClient) -> httpx.Client:
        return httpx.Client(base_url=self._credentials.base_url, transport=transport, timeout=5.0)

    monkeypatch.setattr(lexoffice.LexofficeClient, "_client", fake_http)
    return lexoffice.LexofficeClient(
        lexoffice.LexofficeCredentials(api_key="key-1", base_url="https://api.lexware.io")
    )


# --- GAL-202 ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example.org",
        "https://api.lexware.io.evil.example.org",
        "https://api.lexware.io:8443",
        "https://api.lexware.io/../steal",
        "http://api.lexware.io",
        "https://api.lexware.io@evil.example.org",
        "https://169.254.169.254",
        "https://127.0.0.1",
        "file:///etc/passwd",
        "",
    ],
)
def test_strict_allowlist_refuses_foreign_targets(url: str) -> None:
    with pytest.raises(ProblemError) as exc:
        lexoffice.validate_base_url(url, strict=True)
    assert exc.value.error is ErrorCodes.VALIDATION


@pytest.mark.parametrize("url", ["https://api.lexware.io", "https://api.lexoffice.io/"])
def test_strict_allowlist_accepts_vendor_hosts(url: str) -> None:
    assert lexoffice.validate_base_url(url, strict=True) == url.rstrip("/")


@pytest.mark.parametrize(
    "url", ["http://api.lexware.io", "https://user:pw@api.lexware.io", "ftp://x", "https://"]
)
def test_syntax_check_also_in_dev(url: str) -> None:
    with pytest.raises(ProblemError):
        lexoffice.validate_base_url(url, strict=False)


def test_strict_outside_dev_and_test() -> None:
    class S:
        env = Environment.PROD

    assert lexoffice.strict_hosts(S()) is True
    S.env = Environment.STAGING
    assert lexoffice.strict_hosts(S()) is True
    S.env = Environment.TEST
    assert lexoffice.strict_hosts(S()) is False


def test_client_never_sends_the_key_over_plain_http(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[httpx.Request] = []
    monkeypatch.setattr(
        lexoffice.LexofficeClient,
        "_client",
        lambda self: httpx.Client(
            transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200))
        ),
    )
    with pytest.raises(ProblemError):
        lexoffice.LexofficeClient(
            lexoffice.LexofficeCredentials(api_key="secret", base_url="http://attacker.test")
        )
    assert sent == []


# --- GAL-203 ---------------------------------------------------------------------------


def test_vendor_error_body_does_not_reach_the_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "status": 400,
                "error": "Bad Request",
                "message": PII,
                "IssueList": [{"source": "address.street", "type": "invalid", "i18nKey": PII}],
            },
        )

    client = _client(monkeypatch, handler)
    with pytest.raises(ProblemError) as exc:
        client.create_contact({"name": PII})
    message = exc.value.developer_message
    assert "Erika" not in message
    assert "DE89" not in message
    assert "example.org" not in message
    assert "address.street" in message
    body = problem_response(
        exc.value.error,
        instance="/x",
        detail=exc.value.detail,
        developer_message=message,
        extensions=exc.value.extensions,
    ).body.decode()
    assert "Erika" not in body
    assert "DE89" not in body


def test_non_json_error_body_is_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, lambda r: httpx.Response(500, text=f"<html>{PII}</html>"))
    with pytest.raises(ProblemError) as exc:
        client.test_connection()
    assert exc.value.developer_message == "lexoffice status 500"


def test_retry_after_is_passed_on(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(
        monkeypatch, lambda r: httpx.Response(429, headers={"Retry-After": "7"}, json={})
    )
    with pytest.raises(ProblemError) as exc:
        client.test_connection()
    assert exc.value.error is ErrorCodes.LEXOFFICE_RATE_LIMITED
    assert exc.value.extensions == {"retry_after": 7}
    response = problem_response(
        exc.value.error,
        instance="/x",
        extensions=exc.value.extensions,
        headers={"Retry-After": "7"},
    )
    assert response.headers["Retry-After"] == "7"


# --- GAL-201 ---------------------------------------------------------------------------


def test_write_timeout_is_marked_maybe_processed(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = _client(monkeypatch, handler)
    with pytest.raises(ProblemError) as exc:
        client.create_voucher({"voucherNumber": "R-1"})
    assert exc.value.extensions["maybe_processed"] is True
    with pytest.raises(ProblemError) as read_exc:
        client.get_voucher("v-1")
    assert read_exc.value.extensions["maybe_processed"] is False
