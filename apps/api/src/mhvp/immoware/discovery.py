"""Standardbasierte Discovery der DAV-Endpunkte (M32 Folgeauftrag, Betreiberbericht 25.09.2026).

Implementiert RFC 6764 (CalDAV/CardDAV-Discovery via .well-known und current-user-principal /
*-home-set) sowie eine WebDAV-Wurzelsuche fuer Dokumente (RFC 4918). Nur lesende Methoden
(PROPFIND), read only ueber ``ReadOnlyDavClient``. Ergebnisse werden ausschliesslich als
Vorschlag zurueckgegeben; das Speichern auf der Connection entscheidet der Aufrufer (Regel:
manuell gesetzte Werte werden nie ueberschrieben).
"""

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from mhvp.immoware.client import ReadOnlyDavClient, sanitize_error
from mhvp.immoware.webdav import DAV_NS

_PRINCIPAL_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:current-user-principal/></D:prop>
</D:propfind>"""

_ADDRESSBOOK_HOME_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop><C:addressbook-home-set/></D:prop>
</D:propfind>"""

_CALENDAR_HOME_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:" xmlns:CAL="urn:ietf:params:xml:ns:caldav">
  <D:prop><CAL:calendar-home-set/></D:prop>
</D:propfind>"""

_RESOURCETYPE_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:resourcetype/><D:displayname/></D:prop>
</D:propfind>"""

_COMMON_DOCUMENT_ROOTS = ("/dav/", "/dav/files/", "/dav/documents/")


@dataclass
class DiscoveryStep:
    """Ein einzelner Discovery-Schritt fuer Protokoll und Diagnose-Endpunkt."""

    name: str
    url: str
    status: int | None
    ok: bool
    note: str
    collections: list[str] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    steps: list[DiscoveryStep] = field(default_factory=list)
    carddav_url: str | None = None
    caldav_url: str | None = None
    webdav_url: str | None = None


def _mask(url: str) -> str:
    return sanitize_error(url)


def _href_text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    href = el.find(f"{{{DAV_NS}}}href")
    return href.text if href is not None and href.text else None


def _first_response_prop(xml_bytes: bytes) -> ET.Element | None:
    root = ET.fromstring(xml_bytes)  # noqa: S314 - kontrollierte Serverantwort
    response = root.find(f"{{{DAV_NS}}}response")
    if response is None:
        return None
    propstat = response.find(f"{{{DAV_NS}}}propstat")
    if propstat is None:
        return None
    return propstat.find(f"{{{DAV_NS}}}prop")


def _resolve(base: str, href: str) -> str:
    if href.startswith("http"):
        return href
    from urllib.parse import urljoin

    return urljoin(base, href)


async def _propfind(
    client: ReadOnlyDavClient, url: str, body: str, depth: str = "0"
) -> tuple[int, bytes | None]:
    try:
        response = await client.request(
            "PROPFIND",
            url,
            content=body.encode("utf-8"),
            headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
        )
        return response.status_code, response.content
    except Exception:
        return 0, None


def _interpret(status: int) -> str:
    if status == 0:
        return "Nicht erreichbar (Netzwerkfehler oder Zeitueberschreitung)."
    if status == 401 or status == 403:
        return "401/403: Zugangsdaten oder DAV-Modul nicht freigeschaltet."
    if status == 404:
        return "404: Ressource nicht vorhanden."
    if status in (207, 200):
        return "gefunden."
    return f"unerwarteter Status {status}."


async def _well_known(
    client: ReadOnlyDavClient, base_url: str, path: str, steps: list[DiscoveryStep]
) -> str | None:
    url = base_url.rstrip("/") + path
    status, _ = await _propfind(client, url, _PRINCIPAL_BODY, depth="0")
    # .well-known redirects are handled by the underlying client's follow_redirects=True; we
    # only record whether the endpoint answered.
    ok = status in (200, 207, 301, 302, 308)
    steps.append(
        DiscoveryStep(
            name=f".well-known{path}",
            url=_mask(url),
            status=status or None,
            ok=ok,
            note=_interpret(status),
        )
    )
    return url if ok else None


async def _current_user_principal(
    client: ReadOnlyDavClient, url: str, steps: list[DiscoveryStep], *, step_name: str
) -> str | None:
    status, content = await _propfind(client, url, _PRINCIPAL_BODY, depth="0")
    ok = status in (200, 207) and content is not None
    principal_url: str | None = None
    if ok and content:
        try:
            prop = _first_response_prop(content)
            principal_href = None
            if prop is not None:
                cup = prop.find(f"{{{DAV_NS}}}current-user-principal")
                principal_href = _href_text(cup)
            if principal_href:
                principal_url = _resolve(url, principal_href)
        except ET.ParseError:
            ok = False
    steps.append(
        DiscoveryStep(
            name=step_name,
            url=_mask(url),
            status=status or None,
            ok=ok,
            note=_interpret(status)
            if not ok
            else f"gefunden, Principal: {_mask(principal_url or '')}",
        )
    )
    return principal_url


async def _home_set(
    client: ReadOnlyDavClient,
    principal_url: str,
    body: str,
    tag: str,
    ns: str,
    steps: list[DiscoveryStep],
    *,
    step_name: str,
) -> str | None:
    status, content = await _propfind(client, principal_url, body, depth="0")
    ok = status in (200, 207) and content is not None
    home_url: str | None = None
    if ok and content:
        try:
            prop = _first_response_prop(content)
            if prop is not None:
                home_set = prop.find(f"{{{ns}}}{tag}")
                if home_set is not None:
                    home_url = _href_text(home_set)
                    if home_url:
                        home_url = _resolve(principal_url, home_url)
        except ET.ParseError:
            ok = home_url is not None
    steps.append(
        DiscoveryStep(
            name=step_name,
            url=_mask(principal_url),
            status=status or None,
            ok=ok and home_url is not None,
            note=_interpret(status)
            if not (ok and home_url)
            else f"gefunden: {_mask(home_url or '')}",
        )
    )
    return home_url


async def _list_collections(
    client: ReadOnlyDavClient, home_url: str, steps: list[DiscoveryStep], *, step_name: str
) -> list[str]:
    status, content = await _propfind(client, home_url, _RESOURCETYPE_BODY, depth="1")
    collections: list[str] = []
    if status in (200, 207) and content:
        try:
            root = ET.fromstring(content)  # noqa: S314
            for response in root.findall(f"{{{DAV_NS}}}response"):
                href_el = response.find(f"{{{DAV_NS}}}href")
                if (
                    href_el is not None
                    and href_el.text
                    and href_el.text.rstrip("/") != home_url.rstrip("/")
                ):
                    collections.append(_resolve(home_url, href_el.text))
        except ET.ParseError:
            pass
    steps.append(
        DiscoveryStep(
            name=step_name,
            url=_mask(home_url),
            status=status or None,
            ok=status in (200, 207),
            note=f"gefunden, {len(collections)} Sammlung(en)."
            if status in (200, 207)
            else _interpret(status),
            collections=[_mask(c) for c in collections],
        )
    )
    return collections


async def discover_addressbooks(
    client: ReadOnlyDavClient, base_url: str, username: str | None
) -> tuple[str | None, list[DiscoveryStep]]:
    steps: list[DiscoveryStep] = []
    await _well_known(client, base_url, "/carddav", steps)
    principal_url = await _current_user_principal(
        client, base_url, steps, step_name="current-user-principal (base)"
    )
    if principal_url is None:
        dav_root = base_url.rstrip("/") + "/dav/"
        principal_url = await _current_user_principal(
            client, dav_root, steps, step_name="current-user-principal (/dav/)"
        )
    if principal_url is None:
        return None, steps
    home_url = await _home_set(
        client,
        principal_url,
        _ADDRESSBOOK_HOME_BODY,
        "addressbook-home-set",
        "urn:ietf:params:xml:ns:carddav",
        steps,
        step_name="addressbook-home-set",
    )
    if home_url is None:
        return None, steps
    collections = await _list_collections(
        client, home_url, steps, step_name="Adressbuecher auflisten"
    )
    return (collections[0] if collections else home_url), steps


async def discover_calendars_home(
    client: ReadOnlyDavClient, base_url: str, username: str | None
) -> tuple[str | None, list[str], list[DiscoveryStep]]:
    steps: list[DiscoveryStep] = []
    await _well_known(client, base_url, "/caldav", steps)
    principal_url = await _current_user_principal(
        client, base_url, steps, step_name="current-user-principal (base)"
    )
    if principal_url is None:
        dav_root = base_url.rstrip("/") + "/dav/"
        principal_url = await _current_user_principal(
            client, dav_root, steps, step_name="current-user-principal (/dav/)"
        )
    if principal_url is None:
        return None, [], steps
    home_url = await _home_set(
        client,
        principal_url,
        _CALENDAR_HOME_BODY,
        "calendar-home-set",
        "urn:ietf:params:xml:ns:caldav",
        steps,
        step_name="calendar-home-set",
    )
    if home_url is None:
        return None, [], steps
    collections = await _list_collections(client, home_url, steps, step_name="Kalender auflisten")
    return home_url, collections, steps


async def discover_document_root(
    client: ReadOnlyDavClient, base_url: str
) -> tuple[str | None, list[DiscoveryStep]]:
    """PROPFIND Depth 1 auf base_url und gaengigen Wurzeln; erste erreichbare mit Sammlungen
    gewinnt."""
    steps: list[DiscoveryStep] = []
    candidates = [base_url] + [base_url.rstrip("/") + p for p in _COMMON_DOCUMENT_ROOTS]
    for candidate in candidates:
        status, content = await _propfind(client, candidate, _RESOURCETYPE_BODY, depth="1")
        collections: list[str] = []
        if status in (200, 207) and content:
            try:
                root = ET.fromstring(content)  # noqa: S314
                for response in root.findall(f"{{{DAV_NS}}}response"):
                    href_el = response.find(f"{{{DAV_NS}}}href")
                    if href_el is not None and href_el.text:
                        collections.append(href_el.text)
            except ET.ParseError:
                pass
        steps.append(
            DiscoveryStep(
                name=f"WebDAV-Wurzel {_mask(candidate)}",
                url=_mask(candidate),
                status=status or None,
                ok=status in (200, 207),
                note=f"gefunden, {len(collections)} Eintraege."
                if status in (200, 207)
                else _interpret(status),
            )
        )
        if status in (200, 207) and collections:
            return candidate, steps
    return None, steps


async def run_full_discovery(
    client: ReadOnlyDavClient, base_url: str, username: str | None
) -> DiscoveryResult:
    """Fuehrt alle drei Discovery-Zweige aus und sammelt Schritte fuer den Diagnose-Endpunkt."""
    result = DiscoveryResult()
    carddav_url, carddav_steps = await discover_addressbooks(client, base_url, username)
    caldav_home, caldav_collections, caldav_steps = await discover_calendars_home(
        client, base_url, username
    )
    webdav_root, webdav_steps = await discover_document_root(client, base_url)
    result.carddav_url = carddav_url
    result.caldav_url = caldav_collections[0] if caldav_collections else caldav_home
    result.webdav_url = webdav_root
    result.steps = [*carddav_steps, *caldav_steps, *webdav_steps]
    return result
