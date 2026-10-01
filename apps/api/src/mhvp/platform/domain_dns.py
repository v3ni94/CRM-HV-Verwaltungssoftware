"""DNS check of customer domains against the platform host (GA01-10).

``dnspython`` is used for the CNAME chain when installed (it is not a declared dependency);
otherwise only the address comparison via ``socket.getaddrinfo`` is possible.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass, field

MAX_CNAME_DEPTH = 8


@dataclass(frozen=True)
class DnsResult:
    cnames: list[str] = field(default_factory=list)
    addresses: set[str] = field(default_factory=set)
    error: str | None = None


def resolve_host(host: str) -> DnsResult:
    """Resolve CNAME chain and addresses of ``host``; never raises."""
    cnames: list[str] = []
    try:
        import dns.exception
        import dns.resolver

        resolver = dns.resolver.Resolver()
        resolver.lifetime = 4.0
        current = host
        for _ in range(MAX_CNAME_DEPTH):
            try:
                answer = resolver.resolve(current, "CNAME")
            except (
                dns.resolver.NoAnswer,
                dns.resolver.NXDOMAIN,
                dns.resolver.NoNameservers,
                dns.exception.Timeout,
            ):
                break
            current = str(answer[0].target).rstrip(".").lower()
            cnames.append(current)
    except ImportError:
        pass
    except Exception as exc:  # resolver misconfiguration must not break the endpoint
        return DnsResult(cnames, set(), f"DNS-Abfrage fehlgeschlagen ({type(exc).__name__}).")
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        return DnsResult(cnames, set(), None)
    return DnsResult(cnames, {str(i[4][0]) for i in infos}, None)


def evaluate(host: str, platform_hosts: list[str]) -> tuple[str, str]:
    """Return (status, finding) for ``host`` against the platform hosts."""
    result = resolve_host(host)
    if result.error:
        return "failed", result.error
    for target in platform_hosts:
        if target in result.cnames:
            return "verified", f"CNAME zeigt auf {target}."
    if not result.cnames and not result.addresses:
        return "failed", "Kein CNAME oder A-Eintrag gefunden."
    platform_addresses: set[str] = set()
    for target in platform_hosts:
        platform_addresses |= resolve_host(target).addresses
    common = result.addresses & platform_addresses
    if common:
        return "verified", f"A-Eintrag stimmt mit dem Plattformhost überein ({sorted(common)[0]})."
    seen = ", ".join(result.cnames) if result.cnames else ", ".join(sorted(result.addresses))
    return "failed", f"Weder CNAME noch A-Eintrag zeigen auf den Plattformhost (gefunden: {seen})."
