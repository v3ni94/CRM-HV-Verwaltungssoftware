"""WebDAV-Adapter (Regel 1/2 des Hubs): PROPFIND rekursiv gegen den Immoware24-Dokumentenbaum,
Upsert in ``immoware_dav_document`` je href, entfallene Eintraege werden mit ``deleted_at``
markiert. Datei-Download per GET als Stream fuer den Proxy-Endpunkt.
"""

import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.immoware.client import ReadOnlyDavClient, sanitize_error
from mhvp.immoware.models import SOURCE_SYSTEM, ImmowareDavDocument

DAV_NS = "DAV:"
_OBJECT_NUMBER_RE = re.compile(r"(?:^|/)(\d{3})(?:\s|$|/)")

PROPFIND_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:displayname/>
    <D:getcontenttype/>
    <D:getcontentlength/>
    <D:getetag/>
    <D:getlastmodified/>
    <D:resourcetype/>
  </D:prop>
</D:propfind>"""


@dataclass
class DavEntry:
    href: str
    display_name: str | None = None
    content_type: str | None = None
    size: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    is_collection: bool = False


@dataclass
class WebdavPullResult:
    seen: int = 0
    added: int = 0
    changed: int = 0
    removed: int = 0
    entries: list[DavEntry] = field(default_factory=list)
    folder_errors: list[dict[str, object]] = field(default_factory=list)


def _tag(el: ET.Element) -> str:
    return el.tag.split("}", 1)[-1] if "}" in el.tag else el.tag


def _text(prop: ET.Element | None, name: str) -> str | None:
    if prop is None:
        return None
    found = prop.find(f"{{{DAV_NS}}}{name}")
    return found.text if found is not None and found.text else None


def parse_propfind(xml_bytes: bytes) -> list[DavEntry]:
    """Parst eine PROPFIND-Multistatus-Antwort (DAV:-Namespace) in ``DavEntry``-Zeilen."""
    root = ET.fromstring(xml_bytes)  # noqa: S314 - kontrollierte Serverantwort, kein DTD-Risiko
    entries: list[DavEntry] = []
    for response in root.findall(f"{{{DAV_NS}}}response"):
        href_el = response.find(f"{{{DAV_NS}}}href")
        if href_el is None or not href_el.text:
            continue
        href = href_el.text
        propstat = response.find(f"{{{DAV_NS}}}propstat")
        prop = propstat.find(f"{{{DAV_NS}}}prop") if propstat is not None else None
        is_collection = False
        if prop is not None:
            resourcetype = prop.find(f"{{{DAV_NS}}}resourcetype")
            if resourcetype is not None and any(
                _tag(child) == "collection" for child in resourcetype
            ):
                is_collection = True
        size_text = _text(prop, "getcontentlength")
        entries.append(
            DavEntry(
                href=href,
                display_name=_text(prop, "displayname"),
                content_type=_text(prop, "getcontenttype"),
                size=int(size_text) if size_text and size_text.isdigit() else None,
                etag=_text(prop, "getetag"),
                last_modified=_text(prop, "getlastmodified"),
                is_collection=is_collection,
            )
        )
    return entries


def guess_object_number(href: str) -> str | None:
    match = _OBJECT_NUMBER_RE.search(href)
    return match.group(1) if match else None


async def propfind(client: ReadOnlyDavClient, url: str, *, depth: int | str = 1) -> list[DavEntry]:
    response = await client.request(
        "PROPFIND",
        url,
        content=PROPFIND_BODY.encode("utf-8"),
        headers={"Depth": str(depth), "Content-Type": "application/xml; charset=utf-8"},
    )
    if response.status_code >= 400:
        raise RuntimeError(sanitize_error(f"PROPFIND {response.status_code} auf {url}"))
    return parse_propfind(response.content)


async def _propfind_folder(
    client: ReadOnlyDavClient, url: str
) -> tuple[list[DavEntry], dict[str, object] | None]:
    """Wie ``propfind``, aber ein Fehlerstatus (insbesondere 401/403) fuehrt nicht zum
    RuntimeError, sondern kommt als Fehlerdatensatz zurueck, damit ``pull_tree`` den Lauf pro
    Ordner fortsetzen kann (Betreiberbericht 25.09.2026: manche Unterordner sind gesperrt, ohne
    dass der gesamte Sync abbrechen soll)."""
    try:
        response = await client.request(
            "PROPFIND",
            url,
            content=PROPFIND_BODY.encode("utf-8"),
            headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
        )
    except Exception as exc:
        return [], {"url": sanitize_error(url), "status": None, "note": sanitize_error(str(exc))}
    if response.status_code >= 400:
        note = (
            "Zugriff verweigert (401/403)."
            if response.status_code in (401, 403)
            else f"HTTP {response.status_code}."
        )
        return [], {"url": sanitize_error(url), "status": response.status_code, "note": note}
    try:
        return parse_propfind(response.content), None
    except ET.ParseError as exc:
        return [], {"url": sanitize_error(url), "status": response.status_code, "note": str(exc)}


async def pull_tree(
    client: ReadOnlyDavClient,
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    base_url: str,
    max_depth: int = 4,
) -> WebdavPullResult:
    """PROPFIND Depth 1 rekursiv bis ``max_depth``. Immoware24 unterstuetzt kein Depth: infinity
    zuverlaessig, daher wird Ordner fuer Ordner abgestiegen (Hub-Vorbild: DavPullRunner). Ein
    401/403 auf einem einzelnen Unterordner bricht den Lauf nicht ab, sondern wird in
    ``result.folder_errors`` protokolliert (Betreiberbericht 25.09.2026)."""
    result = WebdavPullResult()
    seen_ids: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]
    visited: set[str] = set()
    while queue:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        entries, folder_error = await _propfind_folder(client, url)
        if folder_error is not None:
            result.folder_errors.append(folder_error)
            continue
        for entry in entries:
            result.entries.append(entry)
            result.seen += 1
            seen_ids.add(entry.href)
            if entry.is_collection and depth + 1 < max_depth:
                next_url = url.rstrip("/") + "/" + entry.href.rstrip("/").rsplit("/", 1)[-1] + "/"
                if entry.href.startswith("http"):
                    next_url = entry.href
                queue.append((next_url, depth + 1))
    now = datetime.now(UTC)
    for entry in result.entries:
        existing = await session.scalar(
            select(ImmowareDavDocument).where(
                ImmowareDavDocument.tenant_id == tenant_id,
                ImmowareDavDocument.external_id == entry.href,
            )
        )
        if existing is None:
            session.add(
                ImmowareDavDocument(
                    tenant_id=tenant_id,
                    source_system=SOURCE_SYSTEM,
                    external_id=entry.href,
                    first_synced_at=now,
                    last_synced_at=now,
                    checksum=entry.etag,
                    href=entry.href,
                    display_name=entry.display_name,
                    content_type=entry.content_type,
                    size=entry.size,
                    etag=entry.etag,
                    last_modified=entry.last_modified,
                    is_collection=entry.is_collection,
                    object_number_guess=guess_object_number(entry.href),
                )
            )
            result.added += 1
        else:
            existing.deleted_at = None
            existing.last_synced_at = now
            if existing.checksum != entry.etag:
                existing.checksum = entry.etag
                existing.sync_version += 1
                result.changed += 1
            existing.display_name = entry.display_name
            existing.content_type = entry.content_type
            existing.size = entry.size
            existing.etag = entry.etag
            existing.last_modified = entry.last_modified
            existing.is_collection = entry.is_collection
    stale = await session.scalars(
        select(ImmowareDavDocument).where(
            ImmowareDavDocument.tenant_id == tenant_id,
            ImmowareDavDocument.deleted_at.is_(None),
            ImmowareDavDocument.external_id.not_in(seen_ids or {""}),
        )
    )
    for row in stale:
        row.deleted_at = now
        result.removed += 1
    return result


async def download(client: ReadOnlyDavClient, url: str) -> AsyncIterator[bytes]:
    """GET als Stream fuer den Download-Proxy. Der Aufrufer schliesst den Response-Kontext."""
    async with client._client.stream("GET", url) as response:
        if response.status_code >= 400:
            raise RuntimeError(sanitize_error(f"GET {response.status_code} auf {url}"))
        async for chunk in response.aiter_bytes():
            yield chunk
