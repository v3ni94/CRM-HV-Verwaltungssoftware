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


async def pull_contacts(
    client: ReadOnlyDavClient,
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    carddav_url: str,
) -> CardDavPullResult:
    result = CardDavPullResult()
    remote = await _list_hrefs(client, carddav_url)
    result.seen = len(remote)
    existing_rows = list(
        await session.scalars(
            select(ImmowareDavContact).where(ImmowareDavContact.tenant_id == tenant_id)
        )
    )
    by_href = {row.external_id: row for row in existing_rows if row.deleted_at is None}
    to_fetch = [
        href
        for href, etag in remote.items()
        if by_href.get(href) is None or by_href[href].checksum != etag
    ]
    cards = await _multiget(client, carddav_url, to_fetch)
    now = datetime.now(UTC)
    for href, vcard_raw in cards.items():
        parsed = parse_vcard(vcard_raw)
        etag = remote.get(href)
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
            result.added += 1
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
            result.changed += 1
    removed_hrefs = set(by_href) - set(remote)
    for href in removed_hrefs:
        by_href[href].deleted_at = now
        result.removed += 1
    return result
