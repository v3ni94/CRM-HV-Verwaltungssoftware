"""DAV-Adapter fuer Immoware24 (M32): PROPFIND-XML, vCard, iCalendar, Methodensperre."""

import httpx
import pytest

from mhvp.immoware.client import ReadOnlyDavClient, WriteBlockedError, sanitize_error
from mhvp.immoware.ical import parse_ical
from mhvp.immoware.vcard import parse_vcard
from mhvp.immoware.webdav import guess_object_number, parse_propfind

PROPFIND_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>/posteingang/123 Musterstrasse/</D:href>
    <D:propstat>
      <D:prop>
        <D:displayname>123 Musterstrasse</D:displayname>
        <D:resourcetype><D:collection/></D:resourcetype>
        <D:getetag>"col-1"</D:getetag>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
  <D:response>
    <D:href>/posteingang/123 Musterstrasse/rechnung.pdf</D:href>
    <D:propstat>
      <D:prop>
        <D:displayname>rechnung.pdf</D:displayname>
        <D:getcontenttype>application/pdf</D:getcontenttype>
        <D:getcontentlength>2048</D:getcontentlength>
        <D:getetag>"file-7"</D:getetag>
        <D:getlastmodified>Wed, 01 Jan 2026 10:00:00 GMT</D:getlastmodified>
        <D:resourcetype/>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>"""

VCARD_RAW = (
    "BEGIN:VCARD\r\n"
    "VERSION:3.0\r\n"
    "UID:contact-1\r\n"
    "FN:Erika Musterfrau\r\n"
    "ORG:Musterfrau GmbH;\r\n"
    "EMAIL:erika@example.com\r\n"
    "TEL:+49 30 1234567\r\n"
    "ADR;TYPE=home:;;Musterstr. 1;Berlin;;10115;DE\r\n"
    "END:VCARD\r\n"
)

ICAL_RAW = (
    "BEGIN:VCALENDAR\r\n"
    "VERSION:2.0\r\n"
    "BEGIN:VEVENT\r\n"
    "UID:event-1\r\n"
    "SUMMARY:Eigentuemerversammlung\r\n"
    "DTSTART:20260301T090000Z\r\n"
    "DTEND:20260301T110000Z\r\n"
    "LOCATION:Gemeinschaftsraum\r\n"
    "DESCRIPTION:Jahresversammlung\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def test_parse_propfind_reads_collection_and_file() -> None:
    entries = parse_propfind(PROPFIND_XML)
    assert len(entries) == 2
    folder, file_ = entries
    assert folder.is_collection is True
    assert folder.display_name == "123 Musterstrasse"
    assert file_.is_collection is False
    assert file_.content_type == "application/pdf"
    assert file_.size == 2048
    assert file_.etag == '"file-7"'


def test_guess_object_number_from_href() -> None:
    assert guess_object_number("/posteingang/123 Musterstrasse/rechnung.pdf") == "123"
    assert guess_object_number("/posteingang/ohne-nummer/x.pdf") is None


def test_parse_vcard_extracts_fields() -> None:
    card = parse_vcard(VCARD_RAW)
    assert card.uid == "contact-1"
    assert card.fn == "Erika Musterfrau"
    assert card.org == "Musterfrau GmbH"
    assert card.emails == ["erika@example.com"]
    assert card.phones == ["+49 30 1234567"]
    assert card.addresses[0]["city"] == "Berlin"
    assert card.addresses[0]["postal_code"] == "10115"


def test_parse_ical_extracts_event() -> None:
    events = parse_ical(ICAL_RAW)
    assert len(events) == 1
    event = events[0]
    assert event.uid == "event-1"
    assert event.summary == "Eigentuemerversammlung"
    assert event.location == "Gemeinschaftsraum"
    assert event.dtstart is not None
    assert event.dtstart.hour == 9
    assert event.dtend is not None
    assert event.dtend.hour == 11


@pytest.mark.asyncio
async def test_write_methods_are_blocked_before_any_request() -> None:
    called = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        called["count"] += 1
        return httpx.Response(200)

    transport = httpx.MockTransport(_handler)
    client = ReadOnlyDavClient(
        httpx.AsyncClient(transport=transport, base_url="https://dav.example")
    )
    try:
        for method in ("PUT", "DELETE", "MOVE", "PROPPATCH", "POST"):
            with pytest.raises(WriteBlockedError):
                await client.request(method, "/x")
        assert called["count"] == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_allowed_methods_pass_through() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(207, content=b"<D:multistatus xmlns:D='DAV:'/>")

    transport = httpx.MockTransport(_handler)
    client = ReadOnlyDavClient(
        httpx.AsyncClient(transport=transport, base_url="https://dav.example")
    )
    try:
        response = await client.request("PROPFIND", "/x", headers={"Depth": "0"})
        assert response.status_code == 207
    finally:
        await client.aclose()


def test_sanitize_error_removes_basic_auth_header_and_credentials_in_url() -> None:
    message = (
        "Request failed for https://user:s3cr3t@dav.example/ with header "
        "Authorization: Basic dXNlcjpzM2NyM3Q="
    )
    cleaned = sanitize_error(message)
    assert "s3cr3t" not in cleaned
    assert "dXNlcjpzM2NyM3Q=" not in cleaned
    assert "***" in cleaned


HOME_PROPFIND_XML = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/dav/calendars/users/info@example.de/</d:href>
    <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop>
    <d:status>HTTP/1.1 200 OK</d:status></d:propstat>
  </d:response>
  <d:response>
    <d:href>/dav/calendars/users/info@example.de/default/</d:href>
    <d:propstat><d:prop><d:displayname>Termine</d:displayname>
    <d:resourcetype><d:collection/><cal:calendar/></d:resourcetype></d:prop>
    <d:status>HTTP/1.1 200 OK</d:status></d:propstat>
  </d:response>
  <d:response>
    <d:href>/dav/calendars/users/info@example.de/inbox/</d:href>
    <d:propstat><d:prop><d:resourcetype><d:collection/><cal:schedule-inbox/></d:resourcetype></d:prop>
    <d:status>HTTP/1.1 200 OK</d:status></d:propstat>
  </d:response>
</d:multistatus>"""


def test_parse_calendar_hrefs_keeps_only_calendar_collections() -> None:
    from mhvp.immoware.caldav import parse_calendar_hrefs

    assert parse_calendar_hrefs(HOME_PROPFIND_XML) == [
        "/dav/calendars/users/info@example.de/default/"
    ]


@pytest.mark.asyncio
async def test_discover_calendars_resolves_absolute_urls_and_skips_home() -> None:
    from mhvp.immoware.caldav import discover_calendars

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PROPFIND"
        assert request.headers["Depth"] == "1"
        return httpx.Response(207, content=HOME_PROPFIND_XML)

    client = ReadOnlyDavClient(httpx.AsyncClient(transport=httpx.MockTransport(_handler)))
    try:
        urls = await discover_calendars(
            client, "https://dav.example/dav/calendars/users/info@example.de/"
        )
    finally:
        await client.aclose()
    assert urls == ["https://dav.example/dav/calendars/users/info@example.de/default/"]


@pytest.mark.asyncio
async def test_discover_calendars_returns_empty_on_error() -> None:
    from mhvp.immoware.caldav import discover_calendars

    client = ReadOnlyDavClient(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    )
    try:
        assert await discover_calendars(client, "https://dav.example/dav/calendars/") == []
    finally:
        await client.aclose()


def test_derive_urls_use_username_when_known() -> None:
    from mhvp.immoware.client import derive_caldav_url, derive_carddav_url

    assert (
        derive_caldav_url("https://x.dav.example/dav", "info@example.de")
        == "https://x.dav.example/dav/calendars/users/info@example.de/"
    )
    assert (
        derive_carddav_url("https://x.dav.example/dav/")
        == "https://x.dav.example/dav/addressbooks/"
    )
