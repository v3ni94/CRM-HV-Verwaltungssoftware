"""CardDAV-Adapter (Regel 1/2 des Hubs): PROPFIND auf das Adressbuch (getetag), Upsert der
vCards in ``immoware_dav_contact`` je href. Aenderungserkennung ueber etag; ein vollstaendiger
Multiget-REPORT holt die geaenderten hrefs (Immoware24 bietet kein sync-token zuverlaessig,
daher Vollabgleich wie im Hub, vgl. CardDavConnector)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.immoware.client import ReadOnlyDavClient, sanitize_error
from mhvp.immoware.models import SOURCE_SYSTEM, ImmowareDavContact
from mhvp.immoware.vcard import parse_vcard
from mhvp.immoware.webdav import DAV_NS, parse_propfind

MULTIGET_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<C:addressbook-multiget xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">
  <D:prop>
    <D:getetag/>
    <C:address-data/>
  </D:prop>
{hrefs}
</C:addressbook-multiget>"""

PROPFIND_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:getetag/><D:resourcetype/></D:prop>
</D:propfind>"""


@dataclass
class CardDavPullResult:
    seen: int = 0
    added: int = 0
    changed: int = 0
    removed: int = 0
    errors: list[str] = field(default_factory=list)


async def _list_hrefs(client: ReadOnlyDavClient, carddav_url: str) -> dict[str, str | None]:
    response = await client.request(
        "PROPFIND",
        carddav_url,
        content=PROPFIND_BODY.encode("utf-8"),
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    if response.status_code >= 400:
        raise RuntimeError(sanitize_error(f"PROPFIND {response.status_code} auf {carddav_url}"))
    result: dict[str, str | None] = {}
    for entry in parse_propfind(response.content):
        if entry.is_collection or entry.href.rstrip("/") == carddav_url.rstrip("/"):
            continue
        result[entry.href] = entry.etag
    return result


def _address_data(response_el: ET.Element, ns_card: str) -> str | None:
    propstat = response_el.find(f"{{{DAV_NS}}}propstat")
    prop = propstat.find(f"{{{DAV_NS}}}prop") if propstat is not None else None
    if prop is None:
        return None
    found = prop.find(f"{{{ns_card}}}address-data")
    return found.text if found is not None else None


async def _multiget(
    client: ReadOnlyDavClient, carddav_url: str, hrefs: list[str]
) -> dict[str, str]:
    if not hrefs:
        return {}
    body = MULTIGET_BODY.format(hrefs="\n".join(f"<D:href>{h}</D:href>" for h in hrefs))
    response = await client.request(
        "REPORT",
        carddav_url,
        content=body.encode("utf-8"),
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    if response.status_code >= 400:
        raise RuntimeError(sanitize_error(f"REPORT {response.status_code} auf {carddav_url}"))
    root = ET.fromstring(response.content)  # noqa: S314 - kontrollierte Serverantwort
    ns_card = "urn:ietf:params:xml:ns:carddav"
    out: dict[str, str] = {}
    for resp in root.findall(f"{{{DAV_NS}}}response"):
        href_el = resp.find(f"{{{DAV_NS}}}href")
        data = _address_data(resp, ns_card)
        if href_el is not None and href_el.text and data:
            out[href_el.text] = data
    return out


async def fetch_hrefs(client: ReadOnlyDavClient, carddav_url: str) -> dict[str, str | None]:
    """Abrufphase 1 ohne Datenbankzugriff: alle hrefs des Adressbuchs mit etag."""
    return await _list_hrefs(client, carddav_url)


async def fetch_cards(
    client: ReadOnlyDavClient, carddav_url: str, hrefs: list[str]
) -> dict[str, str]:
    """Abrufphase 2 ohne Datenbankzugriff: Multiget-REPORT fuer die uebergebenen hrefs."""
    return await _multiget(client, carddav_url, hrefs)


async def load_checksums(session: AsyncSession, *, tenant_id: uuid.UUID) -> dict[str, str | None]:
    """Etag-Stand der aktiven Spiegelzeilen (href -> checksum) fuer die Aenderungserkennung."""
    rows = await session.execute(
        select(ImmowareDavContact.external_id, ImmowareDavContact.checksum).where(
            ImmowareDavContact.tenant_id == tenant_id,
            ImmowareDavContact.deleted_at.is_(None),
        )
    )
    return {str(href): checksum for href, checksum in rows.tuples()}


def hrefs_to_fetch(remote: dict[str, str | None], checksums: dict[str, str | None]) -> list[str]:
    """hrefs, die neu sind oder deren etag vom gespiegelten Stand abweicht."""
    return [
        href for href, etag in remote.items() if href not in checksums or checksums[href] != etag
    ]


async def apply_cards(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    cards: dict[str, str],
    etags: dict[str, str | None],
    now: datetime,
) -> tuple[int, int]:
    """Anwendungsphase fuer einen Batch: Upsert je href in ``immoware_dav_contact``. Eine frueher
    als entfallen markierte Zeile mit gleichem href wird wiederbelebt statt neu angelegt
    (Unique ``(tenant_id, external_id)``). Rueckgabe ``(added, changed)``."""
    if not cards:
        return 0, 0
    existing_rows = await session.scalars(
        select(ImmowareDavContact).where(
            ImmowareDavContact.tenant_id == tenant_id,
            ImmowareDavContact.external_id.in_(list(cards)),
        )
    )
    by_href = {row.external_id: row for row in existing_rows}
    added = 0
    changed = 0
    for href, vcard_raw in cards.items():
        parsed = parse_vcard(vcard_raw)
        etag = etags.get(href)
        existing = by_href.get(href)
        if existing is None:
            session.add(
                ImmowareDavContact(
                    tenant_id=tenant_id,
                    source_system=SOURCE_SYSTEM,
                    external_id=href,
                    first_synced_at=now,
                    last_synced_at=now,
                    checksum=etag,
                    href=href,
                    etag=etag,
                    uid=parsed.uid,
                    vcard_raw=vcard_raw,
                    fn=parsed.fn,
                    org=parsed.org,
                    emails=parsed.emails,
                    phones=parsed.phones,
                    addresses=parsed.addresses,
                )
            )
            added += 1
        else:
            existing.deleted_at = None
            existing.last_synced_at = now
            existing.checksum = etag
            existing.sync_version += 1
            existing.etag = etag
            existing.uid = parsed.uid
            existing.vcard_raw = vcard_raw
            existing.fn = parsed.fn
            existing.org = parsed.org
            existing.emails = parsed.emails
            existing.phones = parsed.phones
            existing.addresses = parsed.addresses
            changed += 1
    await session.flush()
    return added, changed


async def mark_removed(
    session: AsyncSession, *, tenant_id: uuid.UUID, remote_hrefs: set[str], now: datetime
) -> int:
    """Markiert aktive Zeilen, die im Adressbuch nicht mehr vorkommen, mit ``deleted_at``."""
    stale = await session.scalars(
        select(ImmowareDavContact).where(
            ImmowareDavContact.tenant_id == tenant_id,
            ImmowareDavContact.deleted_at.is_(None),
            ImmowareDavContact.external_id.not_in(remote_hrefs or {""}),
        )
    )
    removed = 0
    for row in stale:
        row.deleted_at = now
        removed += 1
    await session.flush()
    return removed


async def pull_contacts(
    client: ReadOnlyDavClient,
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    carddav_url: str,
) -> CardDavPullResult:
    """Abruf und Anwendung in einer Session (Einzelaufrufe, Tests). Der Lauf ueber
    ``service.run_sync`` nutzt die Einzelphasen mit kurzen Transaktionen je Batch."""
    result = CardDavPullResult()
    remote = await fetch_hrefs(client, carddav_url)
    result.seen = len(remote)
    checksums = await load_checksums(session, tenant_id=tenant_id)
    cards = await fetch_cards(client, carddav_url, hrefs_to_fetch(remote, checksums))
    now = datetime.now(UTC)
    result.added, result.changed = await apply_cards(
        session, tenant_id=tenant_id, cards=cards, etags=remote, now=now
    )
    result.removed = await mark_removed(
        session, tenant_id=tenant_id, remote_hrefs=set(remote), now=now
    )
    return result
