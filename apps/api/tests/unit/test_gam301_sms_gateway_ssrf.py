"""GAM-301: SSRF over the freely configurable SMS gateway URL.

Attack path: a user stores ``http://169.254.169.254/...`` or a loopback/private service as
gateway URL and triggers a test SMS or an escalation. Defence: ``pin_target`` before every send
(only https, public addresses, pinned IP, no redirects), ``check_target`` when saving, and the
change is bound to ``tenant_settings:update``."""

import asyncio
import socket
import uuid
from typing import Any

import httpx
import pytest

from mhvp.core.webhooks import UnsafeWebhookTargetError, check_target, pin_target
from mhvp.sla import channels, routers
from mhvp.sla.models import SmsGateway

TENANT = uuid.UUID("01900000-0000-7000-8000-000000000001")


def _gateway(url: str) -> SmsGateway:
    return SmsGateway(
        tenant_id=TENANT,
        enabled=True,
        url=url,
        method="POST",
        auth_header_name="X-Api-Key",
        auth_header_value="geheim-123",
        body_template='{"to": "{to}", "text": "{text}"}',
        sender=None,
    )


def _never(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(f"no request expected, got {request.url}")


def _real_pin(url: str) -> Any:
    return pin_target(url, allow_private=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/latest/meta-data/",
        "https://127.0.0.1:6379/",
        "https://[::1]/admin",
        "https://10.0.0.5/api",
        "https://192.168.1.10/",
        "https://localhost:8080/api/http/routers",
        "ftp://gateway.example/",
    ],
)
def test_send_refuses_private_loopback_and_metadata_targets(url: str) -> None:
    error = asyncio.run(
        channels.send_sms(
            _gateway(url), "+49170", "x", http_transport=httpx.MockTransport(_never), pin=_real_pin
        )
    )
    assert error == "SMS-Gateway-Ziel nicht zulässig (nur öffentliche https-Adressen)."


def test_send_rejects_dns_name_resolving_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: int, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    error = asyncio.run(
        channels.send_sms(
            _gateway("https://rebind.example/sms"),
            "+49170",
            "x",
            http_transport=httpx.MockTransport(_never),
            pin=_real_pin,
        )
    )
    assert error is not None
    assert "nicht zulässig" in error


def test_send_is_pinned_and_does_not_follow_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(host: str, port: int, **_: Any) -> list[Any]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            302, headers={"Location": "http://169.254.169.254/"}, text="internal secret"
        )

    error = asyncio.run(
        channels.send_sms(
            _gateway("https://gateway.example/api"),
            "+49170",
            "x",
            http_transport=httpx.MockTransport(handler),
            pin=_real_pin,
        )
    )
    assert len(seen) == 1  # redirect to the metadata service is not followed
    assert seen[0].url.host == "93.184.216.34"  # connected to the checked address
    assert seen[0].headers["Host"] == "gateway.example"
    assert error is not None
    assert "internal secret" not in error


def test_save_check_rejects_internal_targets() -> None:
    for url in ("http://169.254.169.254/", "https://127.0.0.1/", "http://gateway.example/"):
        with pytest.raises(UnsafeWebhookTargetError):
            check_target(url, allow_private=False)


def test_put_requires_tenant_settings_permission() -> None:
    route = next(
        r
        for r in routers.router.routes
        if getattr(r, "path", "") == "/sla/sms-gateway" and "PUT" in getattr(r, "methods", set())
    )
    deps = [d.call for d in route.dependant.dependencies]  # type: ignore[attr-defined]
    assert routers.APPROVE in deps
    assert routers.MANAGE not in deps
