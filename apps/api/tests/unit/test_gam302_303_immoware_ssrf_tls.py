"""GAM-302/303: SSRF and credential leak over the Immoware DAV connection, TLS switch-off.

Attack paths: an administrator of the connection stores an internal address (metadata service,
loopback, private network) or an own server that redirects to an internal target; discovery
returns absolute URLs to internal hosts; a tenant user switches TLS verification off."""

import asyncio
import ipaddress
import socket
from pathlib import Path
from typing import Any

import httpx
import pytest

from mhvp.core.problems import ProblemError
from mhvp.core.webhooks import UnsafeWebhookTargetError, check_target, pin_target
from mhvp.immoware import client as imw_client
from mhvp.immoware import routers
from mhvp.immoware.client import ReadOnlyDavClient, build_httpx_client

PUBLIC = "93.184.216.34"


def _real_pin(url: str) -> Any:
    return pin_target(url, allow_private=False)


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(host: str, port: int, **_: Any) -> list[Any]:
        try:
            address = str(ipaddress.ip_address(host))
        except ValueError:
            address = "127.0.0.1" if host == "internal.example" else PUBLIC
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def _never(request: httpx.Request) -> httpx.Response:  # pragma: no cover
    raise AssertionError(f"no request expected, got {request.url}")


def _run(client: ReadOnlyDavClient, url: str) -> httpx.Response:
    return asyncio.run(client.request("PROPFIND", url))


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "https://169.254.169.254/latest/meta-data/",
        "https://127.0.0.1/remote.php/dav/",
        "https://[::1]/dav/",
        "https://10.1.2.3/dav/",
        "https://internal.example/dav/",  # DNS name resolving to loopback
    ],
)
def test_requests_to_internal_targets_are_refused(public_dns: None, url: str) -> None:
    client = ReadOnlyDavClient(
        httpx.AsyncClient(transport=httpx.MockTransport(_never)), pin=_real_pin
    )
    with pytest.raises(ProblemError):
        _run(client, url)


def test_request_is_pinned_and_keeps_host(public_dns: None) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(207, content=b"<x/>")

    client = ReadOnlyDavClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), pin=_real_pin
    )
    assert _run(client, "https://iris.awi-rems.de/dav/").status_code == 207
    assert seen[0].url.host == PUBLIC
    assert seen[0].headers["Host"] == "iris.awi-rems.de"


def test_redirect_to_internal_host_is_not_followed(public_dns: None) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/"})

    auth_client = httpx.AsyncClient(
        auth=httpx.BasicAuth("u", "secret"), transport=httpx.MockTransport(handler)
    )
    client = ReadOnlyDavClient(auth_client, pin=_real_pin)
    with pytest.raises(ProblemError):
        _run(client, "https://attacker.example/dav/")
    assert len(seen) == 1  # credentials never reach the redirect target


def test_redirect_on_same_host_is_followed_and_pinned(public_dns: None) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/.well-known/carddav":
            return httpx.Response(301, headers={"Location": "/dav/"})
        return httpx.Response(207, content=b"<x/>")

    client = ReadOnlyDavClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), pin=_real_pin
    )
    assert _run(client, "https://iris.awi-rems.de/.well-known/carddav").status_code == 207
    assert [r.url.path for r in seen] == ["/.well-known/carddav", "/dav/"]
    assert all(r.url.host == PUBLIC for r in seen)


def test_discovered_absolute_url_to_internal_target_is_refused(public_dns: None) -> None:
    """Discovery hrefs pass through the same client; an absolute internal href is refused."""
    client = ReadOnlyDavClient(
        httpx.AsyncClient(transport=httpx.MockTransport(_never)), pin=_real_pin
    )
    with pytest.raises(ProblemError):
        _run(client, "https://internal.example/addressbooks/users/u/")


def test_client_does_not_follow_redirects_itself() -> None:
    assert (
        build_httpx_client(username=None, password=None, verify_tls=True).follow_redirects is False
    )


def test_save_check_rejects_internal_and_plain_http() -> None:
    for url in ("http://169.254.169.254/", "https://127.0.0.1/", "http://iris.awi-rems.de/"):
        with pytest.raises(UnsafeWebhookTargetError):
            check_target(url, allow_private=False)


def test_production_client_is_pinned() -> None:
    from mhvp.immoware import service
    from mhvp.immoware.models import ImmowareConnection

    conn = ImmowareConnection(base_url="https://iris.awi-rems.de", username="u", verify_tls=True)
    dav = service.dav_client(conn)
    assert dav._pin is service.dav_pin
    asyncio.run(dav.aclose())


def test_tls_switch_off_guard_present() -> None:
    """GAM-303 is covered end to end in the integration test; here only the module wiring."""
    assert imw_client.build_httpx_client(username=None, password=None, verify_tls=True)
    assert "immoware.tls_verification_changed" in Path(routers.__file__).read_text(encoding="utf-8")
