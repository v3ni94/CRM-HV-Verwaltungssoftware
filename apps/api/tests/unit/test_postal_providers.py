"""M23-01: provider neutral postal interface. LetterXpress adapter against a mocked HTTP
transport (request shape as documented on the public API page), status mapping, manual
provider, registry."""

import base64
import json
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from mhvp.communication import postal_providers as pp


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_letterxpress_submit_builds_documented_letter_object() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"], seen["url"] = request.method, str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": 200,
                "message": "OK",
                "data": {
                    "id": 6035143,
                    "status": "queue",
                    "registered": "r1",
                    "items": [
                        {"address": "Jim Knopf", "pages": 2, "amount": 1.51, "status": "queue"}
                    ],
                },
            },
        )

    provider = pp.LetterXpressProvider("user", "key", "test", client=_client(handler))
    result = await provider.submit(
        b"%PDF-1.4",
        "Jim Knopf\nBahnhofstr. 1\n21337 Lüneburg",
        pp.PostalOptions(
            registered="r1",
            color=True,
            duplex=False,
            dispatch_date=date(2026, 10, 1),
            notice="dispatch:x",
        ),
        "Mahnung.pdf",
    )
    assert seen["method"] == "POST"
    assert seen["url"] == "https://api.letterxpress.de/v3/printjobs"
    body = seen["body"]
    assert body["auth"] == {"username": "user", "apikey": "key", "mode": "test"}
    letter = body["letter"]
    encoded = base64.b64encode(b"%PDF-1.4").decode()
    assert letter["base64_file"] == encoded
    assert letter["base64_file_checksum"] == pp.lxp_checksum(encoded)
    assert letter["specification"] == {"color": "4", "mode": "simplex", "shipping": "national"}
    assert letter["registered"] == "r1"
    assert letter["dispatch_date"] == "2026-10-01"
    assert letter["filename_original"] == "Mahnung.pdf"
    assert "address" not in letter  # the address is read from the PDF by the provider
    assert result.job_id == "6035143"
    assert result.status == "submitted"
    assert result.pages == 2
    assert result.price == Decimal("1.51")
    assert provider.external is False  # test mode: nothing leaves the provider's cart
    await provider.aclose()


@pytest.mark.anyio
async def test_letterxpress_status_and_cancel() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "DELETE":
            return httpx.Response(
                200, json={"status": 200, "message": "Print job deleted successfully"}
            )
        return httpx.Response(
            200,
            json={
                "status": 200,
                "data": {
                    "id": 6035138,
                    "status": "done",
                    "items": [
                        {
                            "pages": 1,
                            "amount": 0.67,
                            "status": "sent",
                            "tracking_code": "RC123456789DE",
                            "tracking_status": "Zugestellt: Sendung am 27.07.22 zugestellt.",
                        }
                    ],
                },
            },
        )

    provider = pp.LetterXpressProvider("user", "key", "live", client=_client(handler))
    status = await provider.status("6035138")
    assert status is not None
    assert status.status == "delivered"
    assert status.tracking_code == "RC123456789DE"
    assert await provider.cancel("6035138") is True
    assert calls == [("GET", "/v3/printjobs/6035138"), ("DELETE", "/v3/printjobs/6035138")]
    assert provider.external is True
    await provider.aclose()


@pytest.mark.anyio
async def test_letterxpress_errors_never_include_credentials() -> None:
    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthorized."})

    provider = pp.LetterXpressProvider("user", "top-secret", client=_client(unauthorized))
    with pytest.raises(pp.PostalProviderError) as exc:
        await provider.balance()
    assert "top-secret" not in str(exc.value)

    def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    provider = pp.LetterXpressProvider("user", "top-secret", client=_client(offline))
    with pytest.raises(pp.PostalProviderUnavailableError):
        await provider.status("1")
    with pytest.raises(pp.PostalProviderError):
        pp.LetterXpressProvider("u", "k", "production")


def test_status_mapping_of_documented_states() -> None:
    assert (
        pp.lxp_map_status({"status": "queue", "items": [{"status": "queue"}]}).status == "submitted"
    )
    assert pp.lxp_map_status({"status": "hold"}).status == "submitted"
    assert pp.lxp_map_status({"status": "draft"}).status == "submitted"
    assert pp.lxp_map_status({"status": "canceled"}).status == "cancelled"
    done = pp.lxp_map_status(
        {"status": "done", "items": [{"status": "sent", "tracking_status": "--"}]}
    )
    assert done.status == "sent"
    assert done.tracking_status is None
    unknown = pp.lxp_map_status({"status": "weird"})
    assert unknown.status == "submitted"
    assert "zu prüfen" in (unknown.detail or "")


@pytest.mark.anyio
async def test_manual_provider_and_registry() -> None:
    manual = pp.build_provider("manual", {})
    result = await manual.submit(b"x", "A", pp.PostalOptions(), "a.pdf")
    assert result.job_id.startswith("manual-")
    assert result.status == "submitted"
    assert await manual.status(result.job_id) is None
    assert await manual.cancel(result.job_id) is True

    class Fake(pp.ManualPostalProvider):
        name = "fake"

    pp.register_provider("fake", lambda cfg: Fake())
    try:
        assert "fake" in pp.provider_names()
        assert isinstance(pp.build_provider("fake", {}), Fake)
    finally:
        pp.unregister_provider("fake")
    with pytest.raises(pp.PostalProviderError):
        pp.build_provider("letterxpress", {"username": "u"})
    with pytest.raises(pp.PostalProviderError):
        pp.build_provider("nope", {})
