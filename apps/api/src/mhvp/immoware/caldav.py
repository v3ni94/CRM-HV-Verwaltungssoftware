"""CalDAV-Adapter (Regel 1/2 des Hubs): calendar-query REPORT fuer einen Zeitraum (Default minus
90 Tage bis plus 365 Tage), Upsert der Termine in ``immoware_dav_event`` je href.

Die konfigurierte ``caldav_url`` darf die Kalender-Heimat des Benutzers sein (z. B.
``.../dav/calendars/users/<login>/``): vor dem REPORT werden per PROPFIND Depth 1 die
Kalendersammlungen darunter ermittelt und einzeln abgefragt. Ein REPORT direkt auf die
Heimat beantworten SabreDAV-Server mit 404, daher die Erkennung.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.immoware.client import ReadOnlyDavClient, sanitize_error
from mhvp.immoware.ical import parse_ical
from mhvp.immoware.models import SOURCE_SYSTEM, ImmowareDavEvent
from mhvp.immoware.webdav import DAV_NS

CALDAV_NS = "urn:ietf:params:xml:ns:caldav"

DISCOVER_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:displayname/>
    <D:resourcetype/>
  </D:prop>
</D:propfind>"""

DEFAULT_PAST_DAYS = 90
DEFAULT_FUTURE_DAYS = 365

QUERY_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start}" end="{end}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""


@dataclass
class CalDavPullResult:
    seen: int = 0
    added: int = 0
    changed: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def parse_calendar_hrefs(xml_bytes: bytes) -> list[str]:
    """Liefert die hrefs aller Antworten, deren resourcetype eine CalDAV-Kalendersammlung ist."""
    root = ET.fromstring(xml_bytes)  # noqa: S314 - kontrollierte Serverantwort
    hrefs: list[str] = []
    for resp in root.findall(f"{{{DAV_NS}}}response"):
        href_el = resp.find(f"{{{DAV_NS}}}href")
        if href_el is None or not href_el.text:
            continue
        for propstat in resp.findall(f"{{{DAV_NS}}}propstat"):
            prop = propstat.find(f"{{{DAV_NS}}}prop")
            rt = prop.find(f"{{{DAV_NS}}}resourcetype") if prop is not None else None
            if rt is not None and rt.find(f"{{{CALDAV_NS}}}calendar") is not None:
                hrefs.append(href_el.text)
                break
    return hrefs


async def discover_calendars(client: ReadOnlyDavClient, caldav_url: str) -> list[str]:
    """PROPFIND Depth 1 auf ``caldav_url``; Ergebnis sind absolute URLs der Kalender darunter.
    Antwortet der Server mit einem Fehler oder ohne Kalender, ist die Liste leer und der
    Aufrufer fragt ``caldav_url`` selbst als Kalender ab."""
    response = await client.request(
        "PROPFIND",
        caldav_url,
        content=DISCOVER_BODY.encode("utf-8"),
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    if response.status_code >= 400:
        return []
    try:
        hrefs = parse_calendar_hrefs(response.content)
    except ET.ParseError:
        return []
    base = urlsplit(caldav_url)
    urls: list[str] = []
    for href in hrefs:
        absolute = urljoin(caldav_url, href)
        # Die Heimat selbst ist kein Kalender, auch wenn manche Server sie so kennzeichnen.
        if urlsplit(absolute).path.rstrip("/") == base.path.rstrip("/"):
            continue
        if absolute not in urls:
            urls.append(absolute)
    return urls


async def _calendar_query(
    client: ReadOnlyDavClient, url: str, body: str
) -> dict[str, tuple[str | None, str]]:
    response = await client.request(
        "REPORT",
        url,
        content=body.encode("utf-8"),
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    if response.status_code >= 400:
        raise RuntimeError(sanitize_error(f"REPORT {response.status_code} auf {url}"))
    root = ET.fromstring(response.content)  # noqa: S314 - kontrollierte Serverantwort
    remote: dict[str, tuple[str | None, str]] = {}
    for resp in root.findall(f"{{{DAV_NS}}}response"):
        href_el = resp.find(f"{{{DAV_NS}}}href")
        propstat = resp.find(f"{{{DAV_NS}}}propstat")
        prop = propstat.find(f"{{{DAV_NS}}}prop") if propstat is not None else None
        if href_el is None or href_el.text is None or prop is None:
            continue
        etag_el = prop.find(f"{{{DAV_NS}}}getetag")
        data_el = prop.find(f"{{{CALDAV_NS}}}calendar-data")
        if data_el is None or not data_el.text:
            continue
        remote[href_el.text] = (etag_el.text if etag_el is not None else None, data_el.text)
    return remote


RemoteEvents = dict[str, tuple[str | None, str]]


async def fetch_events(
    client: ReadOnlyDavClient,
    caldav_url: str,
    *,
    past_days: int = DEFAULT_PAST_DAYS,
    future_days: int = DEFAULT_FUTURE_DAYS,
) -> RemoteEvents:
    """Abrufphase ohne Datenbankzugriff: Kalender ermitteln und je Kalender den
    calendar-query REPORT fuer den Zeitraum stellen. Ergebnis href -> (etag, ical_raw)."""
    now = datetime.now(UTC)
    start, end = now - timedelta(days=past_days), now + timedelta(days=future_days)
    body = QUERY_BODY.format(start=_fmt(start), end=_fmt(end))
    calendars = await discover_calendars(client, caldav_url) or [caldav_url]
    remote: RemoteEvents = {}
    for url in calendars:
        remote.update(await _calendar_query(client, url, body))
    return remote


async def apply_events(
    session: AsyncSession, *, tenant_id: uuid.UUID, remote: RemoteEvents, now: datetime
) -> tuple[int, int]:
    """Anwendungsphase fuer einen Batch: Upsert je href in ``immoware_dav_event``. Eine frueher
    als entfallen markierte Zeile mit gleichem href wird wiederbelebt (Unique
    ``(tenant_id, external_id)``). Rueckgabe ``(added, changed)``."""
    if not remote:
        return 0, 0
    existing_rows = await session.scalars(
        select(ImmowareDavEvent).where(
            ImmowareDavEvent.tenant_id == tenant_id,
            ImmowareDavEvent.external_id.in_(list(remote)),
        )
    )
    by_href = {row.external_id: row for row in existing_rows}
    added = 0
    changed = 0
    for href, (etag, ical_raw) in remote.items():
        existing = by_href.get(href)
        if existing is not None and existing.checksum == etag and existing.deleted_at is None:
            existing.last_synced_at = now
            continue
        events = parse_ical(ical_raw)
        parsed = events[0] if events else None
        if existing is None:
            session.add(
                ImmowareDavEvent(
                    tenant_id=tenant_id,
                    source_system=SOURCE_SYSTEM,
                    external_id=href,
                    first_synced_at=now,
                    last_synced_at=now,
                    checksum=etag,
                    href=href,
                    etag=etag,
                    uid=parsed.uid if parsed else None,
                    summary=parsed.summary if parsed else None,
                    dtstart=parsed.dtstart if parsed else None,
                    dtend=parsed.dtend if parsed else None,
                    location=parsed.location if parsed else None,
                    description=parsed.description if parsed else None,
                    ical_raw=ical_raw,
                )
            )
            added += 1
        else:
            existing.deleted_at = None
            existing.last_synced_at = now
            existing.checksum = etag
            existing.sync_version += 1
            existing.etag = etag
            existing.uid = parsed.uid if parsed else None
            existing.summary = parsed.summary if parsed else None
            existing.dtstart = parsed.dtstart if parsed else None
            existing.dtend = parsed.dtend if parsed else None
            existing.location = parsed.location if parsed else None
            existing.description = parsed.description if parsed else None
            existing.ical_raw = ical_raw
            changed += 1
    await session.flush()
    return added, changed


async def mark_removed(
    session: AsyncSession, *, tenant_id: uuid.UUID, remote_hrefs: set[str], now: datetime
) -> int:
    """Markiert aktive Zeilen, die im Abrufzeitraum nicht mehr vorkommen, mit ``deleted_at``."""
    stale = await session.scalars(
        select(ImmowareDavEvent).where(
            ImmowareDavEvent.tenant_id == tenant_id,
            ImmowareDavEvent.deleted_at.is_(None),
            ImmowareDavEvent.external_id.not_in(remote_hrefs or {""}),
        )
    )
    removed = 0
    for row in stale:
        row.deleted_at = now
        removed += 1
    await session.flush()
    return removed


async def pull_events(
    client: ReadOnlyDavClient,
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    caldav_url: str,
    past_days: int = DEFAULT_PAST_DAYS,
    future_days: int = DEFAULT_FUTURE_DAYS,
) -> CalDavPullResult:
    """Abruf und Anwendung in einer Session (Einzelaufrufe, Tests). Der Lauf ueber
    ``service.run_sync`` nutzt die Einzelphasen mit kurzen Transaktionen je Batch."""
    result = CalDavPullResult()
    remote = await fetch_events(client, caldav_url, past_days=past_days, future_days=future_days)
    result.seen = len(remote)
    now = datetime.now(UTC)
    result.added, result.changed = await apply_events(
        session, tenant_id=tenant_id, remote=remote, now=now
    )
    result.removed = await mark_removed(
        session, tenant_id=tenant_id, remote_hrefs=set(remote), now=now
    )
    return result
