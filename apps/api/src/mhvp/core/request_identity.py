"""Cheap request identity for pure ASGI middlewares (idempotency, rate limiting).

Middlewares run before the dependency system, so the principal is derived from the
``Authorization`` bearer token or the ``X-API-Key`` header without touching the database.
The token signature is verified (same code path as ``mhvp.core.auth.principal``); an API key
is only parsed, its secret is checked later by the authentication dependency. A forged key
therefore gains nothing but its own counter or idempotency namespace and is still rejected
by the endpoint.
"""

import ipaddress
from dataclasses import dataclass

from starlette.types import Scope

from mhvp.core.auth.principal import API_KEY_HEADER, parse_api_key
from mhvp.core.auth.tokens import TokenError, decode_access_token
from mhvp.core.config import Settings


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    """``tenant`` is the tenant id (hex) or ``None`` for platform level tokens;
    ``actor`` is ``user:<hex>`` or ``apikey:<prefix>``."""

    tenant: str | None
    actor: str

    @property
    def scope_key(self) -> str:
        return f"{self.tenant or 'platform'}:{self.actor}"


def header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return None


def identify(scope: Scope, settings: Settings) -> RequestIdentity | None:
    """Return the identity behind the request or ``None`` for unauthenticated requests."""
    authorization = header(scope, b"authorization")
    if authorization and authorization[:7].lower() == "bearer ":
        try:
            claims = decode_access_token(settings, authorization[7:].strip())
        except TokenError:
            return None
        tenant = claims.tenant_id.hex if claims.tenant_id else None
        return RequestIdentity(tenant=tenant, actor=f"user:{claims.user_id.hex}")
    api_key = header(scope, API_KEY_HEADER.encode())
    if api_key:
        parsed = parse_api_key(api_key.strip())
        if parsed is None:
            return None
        tenant_id, prefix, _secret = parsed
        return RequestIdentity(tenant=tenant_id.hex, actor=f"apikey:{prefix}")
    return None


_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def _in_networks(address: str, networks: list[_Network]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def _parse_networks(
    entries: list[str] | tuple[str, ...],
) -> list[_Network]:
    networks: list[_Network] = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry.strip(), strict=False))
        except ValueError:
            continue
    return networks


def client_ip(
    scope: Scope,
    *,
    trust_forwarded_for: bool,
    trusted_proxies: list[str] | tuple[str, ...] = (),
) -> str:
    """Client address for limits and logs.

    GAI-311 trust boundary: with ``trusted_proxies`` (CIDR list, empty by default) the
    ``X-Forwarded-For`` header is honoured only when the direct peer is one of these proxies
    (Traefik, the CRM and portal BFF containers); the address is then the rightmost entry that
    is not itself a trusted proxy, so a client cannot spoof it by prepending values. The older
    ``trust_forwarded_for`` switch trusts the first entry from any peer and stays unchanged.
    """
    networks = _parse_networks(trusted_proxies)
    if networks:
        client = scope.get("client")
        peer = str(client[0]) if client else ""
        if peer and _in_networks(peer, networks):
            forwarded = header(scope, b"x-forwarded-for")
            if forwarded:
                hops = [h.strip() for h in forwarded.split(",") if h.strip()]
                for hop in reversed(hops):
                    if not _in_networks(hop, networks):
                        return hop[:64]
        return peer or "unknown"
    if trust_forwarded_for:
        forwarded = header(scope, b"x-forwarded-for")
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
    client = scope.get("client")
    if client:
        return str(client[0])
    return "unknown"


def settings_client_ip(scope: Scope, settings: Settings) -> str:
    """``client_ip`` with the configured trust settings (GAI-311)."""
    return client_ip(
        scope,
        trust_forwarded_for=settings.rate_limit_trust_forwarded_for,
        trusted_proxies=settings.rate_limit_trusted_proxies,
    )
