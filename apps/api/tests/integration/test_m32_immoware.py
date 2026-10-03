"""M32: Immoware24-Lesezugriff per DAV, gegen einen gefakten WebDAV/CardDAV/CalDAV-Server
(httpx.MockTransport statt eines echten Immoware24). Erwartete Werte von Hand:

* Der Fake-WebDAV-Baum unter ``/webdav/`` liefert (Depth 1) genau zwei Dateien
  (``rechnung.pdf``, ``mahnung.pdf``) und keine Unterordner -> ``pull_tree`` meldet
  seen=2, added=2, changed=0, removed=0; ``GET /documents`` liefert danach 2 Zeilen.
* Das Fake-Adressbuch liefert eine vCard (FN "Erika Musterfrau") -> ``pull_contacts`` meldet
  seen=1, added=1; ``GET /contacts`` liefert eine Zeile mit ``fn == "Erika Musterfrau"``.
* Der Fake-Kalender liefert einen Termin (SUMMARY "Eigentümerversammlung",
  DTSTART 20260615T090000Z) -> ``pull_events`` meldet seen=1, added=1.
* Kein Endpunkt unter ``/api/v1/immoware`` nimmt PUT/POST/PATCH/DELETE auf ``/documents``,
  ``/contacts`` oder ``/events`` entgegen (nur ``/connection``, ``/sync/{kind}`` und die beiden
  Kontakt-Aktionen ``match``/``create-contact`` schreiben, alles andere ist GET); zusätzlich
  lehnt ``ReadOnlyDavClient`` jede Methode außer PROPFIND/REPORT/GET ab, bevor eine Anfrage das
  Netz verlässt (Regel 2 des Hubs).
"""

import asyncio
import socket
import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.webhooks import PinnedTarget, check_target
from mhvp.immoware import service as immoware_service
from mhvp.immoware import tasks as immoware_tasks
from mhvp.immoware.client import ReadOnlyDavClient, WriteBlockedError
from mhvp.immoware.models import ImmowareSyncRun, SyncKind, SyncStatus
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
IM = "/api/v1/immoware"

BASE_URL = "https://dav.example.internal/"
CARDDAV_URL = "https://dav.example.internal/addressbooks/default/"
CALDAV_URL = "https://dav.example.internal/calendars/default/"

VCARD = (
    "BEGIN:VCARD\r\nVERSION:3.0\r\nUID:contact-1\r\nFN:Erika Musterfrau\r\n"
    "ORG:Musterfrau GmbH\r\nEMAIL:erika@example.org\r\nTEL:+49 30 1234567\r\nEND:VCARD\r\n"
)
ICAL = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:event-1\r\n"
    "SUMMARY:Eigentümerversammlung\r\nDTSTART:20260615T090000Z\r\nDTEND:20260615T110000Z\r\n"
    "LOCATION:Gemeinschaftsraum\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
)


def _multistatus(entries: list[str]) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?><D:multistatus xmlns:D="DAV:">'
        + "".join(entries)
        + "</D:multistatus>"
    ).encode()


class FakeDav:
    """Minimaler WebDAV/CardDAV/CalDAV-Server fuer den Immoware24-Spiegel (M32)."""

    def __init__(self) -> None:
        self.username = "hvm"
        self.password = "secret-dav-pw"
        self.methods_seen: list[str] = []
        self.write_attempted = False
        self._locked_paths: set[str] = set()
        # Optionaler asynchroner Haken, der vor jeder Antwort laeuft (Tests zur Transaktions-
        # und Sperrlogik: Beobachtung aus einer zweiten Verbindung, Blockieren des Abrufs).
        self.hook: Callable[[httpx.Request], Awaitable[None]] | None = None

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self.hook is not None:
            await self.hook(request)
        return self.handler(request)

    def lock_subfolder(self, path: str) -> None:
        """Ab jetzt liefert PROPFIND auf ``path`` 403 und die Wurzel listet ``path`` zusaetzlich
        als Sammlung (Betreiberbericht 25.09.2026, Auftragspunkt 4: gesperrte Unterordner duerfen
        den Lauf nicht abbrechen)."""
        self._locked_paths.add(path)

    def _auth_ok(self, request: httpx.Request) -> bool:
        auth = request.headers.get("Authorization", "")
        return bool(auth.startswith("Basic "))  # httpx.BasicAuth already encoded correctly on send

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.methods_seen.append(request.method)
        if request.method not in ("PROPFIND", "REPORT", "GET"):
            self.write_attempted = True
            return httpx.Response(405)
        if not self._auth_ok(request):
            return httpx.Response(401)
        path = request.url.path
        if request.method == "PROPFIND" and path in self._locked_paths:
            return httpx.Response(403)
        if request.method == "PROPFIND" and path == "/":
            depth = request.headers.get("Depth")
            if depth == "0":  # connection check
                return httpx.Response(207, content=_multistatus([]))
            locked_entries = [
                (
                    f"<D:response><D:href>{locked}</D:href><D:propstat>"
                    f"<D:prop><D:displayname>{locked.strip('/')}</D:displayname>"
                    "<D:resourcetype><D:collection/></D:resourcetype>"
                    "</D:prop></D:propstat></D:response>"
                )
                for locked in sorted(self._locked_paths)
            ]
            return httpx.Response(
                207,
                content=_multistatus(
                    [
                        (
                            "<D:response><D:href>/rechnung.pdf</D:href><D:propstat>"
                            "<D:prop><D:displayname>rechnung.pdf</D:displayname>"
                            "<D:getcontenttype>application/pdf</D:getcontenttype>"
                            "<D:getcontentlength>1234</D:getcontentlength>"
                            '<D:getetag>"etag-rechnung"</D:getetag>'
                            "<D:resourcetype/></D:prop></D:propstat></D:response>"
                        ),
                        (
                            "<D:response><D:href>/mahnung.pdf</D:href><D:propstat>"
                            "<D:prop><D:displayname>mahnung.pdf</D:displayname>"
                            "<D:getcontenttype>application/pdf</D:getcontenttype>"
                            "<D:getcontentlength>567</D:getcontentlength>"
                            '<D:getetag>"etag-mahnung"</D:getetag>'
                            "<D:resourcetype/></D:prop></D:propstat></D:response>"
                        ),
                        *locked_entries,
                    ]
                ),
            )
        if request.method == "GET" and path == "/rechnung.pdf":
            return httpx.Response(200, content=b"%PDF-1.4 fake rechnung")
        if request.method == "GET" and path == "/mahnung.pdf":
            return httpx.Response(200, content=b"%PDF-1.4 fake mahnung")
        if request.method == "PROPFIND" and path == "/addressbooks/default/":
            return httpx.Response(
                207,
                content=_multistatus(
                    [
                        (
                            "<D:response><D:href>/addressbooks/default/contact-1.vcf</D:href>"
                            "<D:propstat><D:prop>"
                            '<D:getetag>"etag-contact-1"</D:getetag>'
                            "<D:resourcetype/></D:prop></D:propstat></D:response>"
                        )
                    ]
                ),
            )
        if request.method == "REPORT" and path == "/addressbooks/default/":
            return httpx.Response(
                207,
                content=(
                    '<?xml version="1.0" encoding="utf-8"?>'
                    '<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav">'
                    "<D:response><D:href>/addressbooks/default/contact-1.vcf</D:href>"
                    "<D:propstat><D:prop>"
                    '<D:getetag>"etag-contact-1"</D:getetag>'
                    f"<C:address-data>{VCARD}</C:address-data>"
                    "</D:prop></D:propstat></D:response></D:multistatus>"
                ).encode(),
            )
        if request.method == "REPORT" and path == "/calendars/default/":
            return httpx.Response(
                207,
                content=(
                    '<?xml version="1.0" encoding="utf-8"?>'
                    '<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">'
                    "<D:response><D:href>/calendars/default/event-1.ics</D:href>"
                    "<D:propstat><D:prop>"
                    '<D:getetag>"etag-event-1"</D:getetag>'
                    f"<C:calendar-data>{ICAL}</C:calendar-data>"
                    "</D:prop></D:propstat></D:response></D:multistatus>"
                ).encode(),
            )
        return httpx.Response(404)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"m32a-{RUN}", name=f"M32 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"m32b-{RUN}", name=f"M32 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant_id, name, role in [
            (a, "m32admin", "tenant_admin"),
            (a, "m32standard", "standard"),  # ohne immoware:*
            (b, "m32badmin", "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    import asyncio

    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def fake() -> FakeDav:
    return FakeDav()


@pytest.fixture
def client(
    database: Database, redis_url: str, fake: FakeDav, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """Patches ``build_httpx_client`` so ``ReadOnlyDavClient`` talks to ``fake`` via
    ``httpx.MockTransport``, exactly as the real client would over the network (Basic Auth,
    only PROPFIND/REPORT/GET)."""

    def patched(
        *, username: str | None, password: str | None, verify_tls: bool, timeout: float = 30.0
    ) -> httpx.AsyncClient:
        auth = httpx.BasicAuth(username, password or "") if username else None
        return httpx.AsyncClient(
            auth=auth, transport=httpx.MockTransport(fake.handle), timeout=timeout
        )

    monkeypatch.setattr(immoware_service, "build_httpx_client", patched)
    # GAM-302: the test host resolves to a public documentation address so the save check
    # passes; the per-request pin is checked, but the fake keeps the host name in the URL.
    real_getaddrinfo = socket.getaddrinfo

    def fake_dns(host: str, port: Any, *args: Any, **kwargs: Any) -> Any:
        if host == "dav.example.internal":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", fake_dns)

    def checked_pin(url: str) -> PinnedTarget:
        check_target(url, allow_private=False)
        return PinnedTarget(url=url)

    monkeypatch.setattr(immoware_service, "dav_pin", checked_pin)
    settings = _settings(database, redis_url)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _connect(client: TestClient, h: dict[str, str], fake: FakeDav) -> None:
    _ok(
        client.put(
            f"{IM}/connection",
            json={
                "base_url": BASE_URL,
                "carddav_url": CARDDAV_URL,
                "caldav_url": CALDAV_URL,
                "username": fake.username,
                "password": fake.password,
                "enabled": True,
                "verify_tls": True,
                "poll_minutes": 30,
            },
            headers=h,
        )
    )


def test_sync_and_list_documents_happy_path(
    client: TestClient, world: World, fake: FakeDav
) -> None:
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    assert _ok(client.get(f"{IM}/connection", headers=h))["has_password"] is True

    run = _ok(client.post(f"{IM}/sync/webdav", headers=h))
    assert "run_id" in run
    runs = {r["kind"]: r for r in _ok(client.get(f"{IM}/sync/runs", headers=h))}
    assert (runs["webdav"]["status"], runs["webdav"]["seen"], runs["webdav"]["added"]) == (
        "ok",
        2,
        2,
    )

    page = _ok(client.get(f"{IM}/documents", headers=h))
    assert page["meta"]["total"] == 2
    names = sorted(d["display_name"] for d in page["data"])
    assert names == ["mahnung.pdf", "rechnung.pdf"]

    # Detail: text search narrows to one row.
    narrowed = _ok(client.get(f"{IM}/documents", params={"q": "rechnung"}, headers=h))
    assert narrowed["meta"]["total"] == 1
    doc = narrowed["data"][0]
    assert doc["content_type"] == "application/pdf"
    assert doc["size"] == 1234

    # Download proxy streams the file via GET, the DAV password never appears in the response.
    download = client.get(f"{IM}/documents/{doc['id']}/file", headers=h)
    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 fake rechnung"
    assert fake.password not in download.text

    # A second, unchanged sync run adds nothing (idempotent full sync).
    run2 = _ok(client.post(f"{IM}/sync/webdav", headers=h))
    run2_row = next(
        r for r in _ok(client.get(f"{IM}/sync/runs", headers=h)) if r["id"] == run2["run_id"]
    )
    assert (run2_row["seen"], run2_row["added"], run2_row["changed"]) == (2, 0, 0)


def test_sync_contacts_and_events_happy_path(
    client: TestClient, world: World, fake: FakeDav
) -> None:
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)

    _ok(client.post(f"{IM}/sync/carddav", headers=h))
    contacts = _ok(client.get(f"{IM}/contacts", headers=h))
    assert contacts["meta"]["total"] == 1
    contact = contacts["data"][0]
    assert (contact["fn"], contact["org"], contact["emails"]) == (
        "Erika Musterfrau",
        "Musterfrau GmbH",
        ["erika@example.org"],
    )
    assert contact["matched_contact_id"] is None

    _ok(client.post(f"{IM}/sync/caldav", headers=h))
    events = _ok(client.get(f"{IM}/events", headers=h))
    assert events["meta"]["total"] == 1
    event = events["data"][0]
    assert event["summary"] == "Eigentümerversammlung"
    assert event["dtstart"] == "2026-06-15T09:00:00Z"

    # Detail: matching links the DAV contact to a CRM contact by external id, never by name/mail.
    crm_contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Erika", "last_name": "Musterfrau"},
            headers=h,
        ),
        201,
    )
    matched = _ok(
        client.post(
            f"{IM}/contacts/{contact['id']}/match",
            json={"contact_id": crm_contact["id"]},
            headers=h,
        )
    )
    assert matched["matched_contact_id"] == crm_contact["id"]


def test_authorization_role_without_immoware_permission_gets_403(
    client: TestClient, world: World, fake: FakeDav
) -> None:
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)

    # "standard" has none of the immoware:* permissions (permissions.py: _TICKETS/_MASTER_RWD/
    # _ACC_RW/_SLA_MANAGE do not include "immoware").
    standard = bearer(login(client, world, "m32standard"))
    assert client.get(f"{IM}/connection", headers=standard).status_code == 403
    assert client.get(f"{IM}/documents", headers=standard).status_code == 403
    assert client.get(f"{IM}/contacts", headers=standard).status_code == 403
    assert client.get(f"{IM}/events", headers=standard).status_code == 403
    assert client.post(f"{IM}/sync/webdav", headers=standard).status_code == 403


def test_tenant_separation_other_tenant_sees_nothing(
    client: TestClient, world: World, fake: FakeDav
) -> None:
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    _ok(client.post(f"{IM}/sync/webdav", headers=h))
    doc_id = _ok(client.get(f"{IM}/documents", headers=h))["data"][0]["id"]

    hb = bearer(login(client, world, "m32badmin"))
    # Tenant B has no connection of its own configured -> empty document list, not tenant A's.
    page_b = _ok(client.get(f"{IM}/documents", headers=hb))
    assert page_b == {"data": [], "meta": {"page": 1, "per_page": 50, "total": 0}}
    # Tenant A's document id is not reachable through tenant B's session (RLS).
    assert client.get(f"{IM}/documents/{doc_id}/file", headers=hb).status_code == 404


def test_validation_bad_input_is_422(client: TestClient, world: World, fake: FakeDav) -> None:
    h = bearer(login(client, world, "m32admin"))
    # Unknown sync kind is rejected by the path enum before any DAV request is made.
    assert client.post(f"{IM}/sync/ftp", headers=h).status_code == 422
    # page_size above the allowed maximum (200) is rejected.
    assert client.get(f"{IM}/documents", params={"page_size": 500}, headers=h).status_code == 422
    # An unknown field on the connection body is rejected (extra="forbid").
    assert (
        client.put(
            f"{IM}/connection", json={"base_url": "https://x", "foo": "bar"}, headers=h
        ).status_code
        == 422
    )
    # A non-UUID contact id on /match is rejected.
    assert (
        client.post(
            f"{IM}/contacts/not-a-uuid/match", json={"contact_id": str(uuid.uuid4())}, headers=h
        ).status_code
        == 422
    )


def test_read_only_guarantee(client: TestClient, world: World, fake: FakeDav) -> None:
    """No write endpoint exists for the mirrored data, and the underlying DAV client refuses any
    write method before a request ever leaves the process."""
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    _ok(client.post(f"{IM}/sync/webdav", headers=h))
    doc_id = _ok(client.get(f"{IM}/documents", headers=h))["data"][0]["id"]

    # No PUT/PATCH/DELETE exists on the mirrored resources; FastAPI answers 405 (method exists on
    # no route for this path) rather than silently accepting a write.
    assert client.put(f"{IM}/documents/{doc_id}", json={}, headers=h).status_code in (404, 405)
    assert client.delete(f"{IM}/documents/{doc_id}", headers=h).status_code in (404, 405)
    assert client.patch(f"{IM}/documents/{doc_id}/file", json={}, headers=h).status_code in (
        404,
        405,
    )
    assert client.delete(f"{IM}/contacts/{uuid.uuid4()}", headers=h).status_code in (404, 405)
    assert client.put(f"{IM}/events/{uuid.uuid4()}", json={}, headers=h).status_code in (404, 405)

    # No write method was ever attempted against the fake DAV server through normal use.
    assert fake.write_attempted is False
    assert set(fake.methods_seen) <= {"PROPFIND", "REPORT", "GET"}

    # The read-only client itself blocks a write method before sending anything, for any caller
    # that might try to bypass the router (unit-level guarantee, Regel 2 des Hubs).
    import asyncio

    async def _attempt_put() -> None:
        wrapped = ReadOnlyDavClient(httpx.AsyncClient(transport=httpx.MockTransport(fake.handler)))
        try:
            with pytest.raises(WriteBlockedError):
                await wrapped.request("PUT", BASE_URL + "new-file.txt", content=b"x")
        finally:
            await wrapped.aclose()

    asyncio.run(_attempt_put())
    assert fake.write_attempted is False  # blocked before it reached the fake server


def test_diagnose_connection_reports_steps(client: TestClient, world: World, fake: FakeDav) -> None:
    """The fake server only answers the fixed paths it knows; it does not implement RFC 6764
    (no current-user-principal href, no home-sets), so the standards based discovery finds
    neither an addressbook nor a calendar home and never overwrites the manually configured URLs
    (Betreiberbericht 25.09.2026). Every step is protocol-only and never leaks the DAV password."""
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)

    diagnosis = _ok(client.post(f"{IM}/connection/diagnose", headers=h))
    assert diagnosis["carddav_url"] is None
    assert diagnosis["caldav_url"] is None
    assert len(diagnosis["steps"]) > 0
    for step in diagnosis["steps"]:
        assert fake.password not in step["url"]
        assert fake.password not in step["note"]

    persisted = _ok(client.get(f"{IM}/connection", headers=h))
    assert persisted["last_diagnosis_at"] is not None
    assert persisted["last_diagnosis"]["carddav_url"] is None
    # Manually configured URLs (via _connect) are never overwritten by discovery.
    assert persisted["carddav_url"] == CARDDAV_URL
    assert persisted["carddav_url_discovered"] is False


def test_take_over_contacts_bulk(client: TestClient, world: World, fake: FakeDav) -> None:
    """The module scoped ``world``/tenant is shared with earlier tests in this file, so an
    earlier ``/match`` on the same DAV contact may already have linked it; the bulk endpoint must
    stay correct either way (unmatched count before == created+linked, 0 afterwards)."""
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    _ok(client.post(f"{IM}/sync/carddav", headers=h))
    unmatched_before = _ok(client.get(f"{IM}/contacts", params={"unmatched": True}, headers=h))
    contact_id = unmatched_before["data"][0]["id"] if unmatched_before["data"] else None
    expected_total = unmatched_before["meta"]["total"]

    result = _ok(client.post(f"{IM}/contacts/take-over", json={}, headers=h))
    assert result["total"] == expected_total
    assert result["created"] + result["linked"] == expected_total
    assert result["skipped"] == 0

    still_unmatched = _ok(client.get(f"{IM}/contacts", params={"unmatched": True}, headers=h))
    assert still_unmatched["meta"]["total"] == 0

    # Idempotent: a second call finds no more unlinked rows.
    result2 = _ok(
        client.post(
            f"{IM}/contacts/take-over",
            json={"contact_ids": [contact_id]} if contact_id else {},
            headers=h,
        )
    )
    assert result2 == {"created": 0, "linked": 0, "skipped": 0, "total": 0}


def test_take_over_document_single_and_folder(
    client: TestClient, world: World, fake: FakeDav
) -> None:
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    _ok(client.post(f"{IM}/sync/webdav", headers=h))
    docs = _ok(client.get(f"{IM}/documents", headers=h))["data"]
    doc_id = next(d["id"] for d in docs if d["display_name"] == "rechnung.pdf")

    result = _ok(
        client.post(f"{IM}/documents/{doc_id}/take-over", headers=h),
        201,
    )
    assert result["created"] is True
    crm_document_id = result["document_id"]

    # Idempotent by href+etag: a second take-over of the same, unchanged row does not create a
    # second CRM document.
    result2 = _ok(client.post(f"{IM}/documents/{doc_id}/take-over", headers=h), 201)
    assert result2 == {"document_id": crm_document_id, "created": False}

    # Bulk-Uebernahme des gesamten (flachen) Baums: die bereits uebernommene Datei zaehlt als
    # "linked" (idempotent), nur die noch offene ("mahnung.pdf") wird neu angelegt.
    folder_result = _ok(
        client.post(f"{IM}/documents/take-over-folder", json={"folder_prefix": "/"}, headers=h)
    )
    assert folder_result["failed"] == 0
    assert folder_result["total"] == 2
    assert folder_result["created"] + folder_result["linked"] == 2


def test_webdav_sync_continues_past_locked_subfolder(
    client: TestClient, world: World, fake: FakeDav
) -> None:
    """A subfolder answering 401/403 must not abort the whole WebDAV run; it is recorded in
    ``folder_errors`` on the sync run instead (Betreiberbericht 25.09.2026, Auftragspunkt 4)."""
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    fake.lock_subfolder("/locked/")

    run = _ok(client.post(f"{IM}/sync/webdav", headers=h))
    runs = {r["id"]: r for r in _ok(client.get(f"{IM}/sync/runs", headers=h))}
    row = runs[run["run_id"]]
    assert row["status"] == "ok"
    assert row["seen"] >= 2  # the two known top level files were still picked up
    assert len(row["folder_errors"]) == 1
    assert row["folder_errors"][0]["status"] == 403
    for entry in row["folder_errors"]:
        assert fake.password not in entry["url"]


def _is_tree_propfind(request: httpx.Request) -> bool:
    return (
        request.method == "PROPFIND"
        and request.url.path == "/"
        and request.headers.get("Depth") == "1"
    )


def _running_count_sql() -> Any:
    return (
        select(func.count())
        .select_from(ImmowareSyncRun)
        .where(
            ImmowareSyncRun.kind == SyncKind.WEBDAV, ImmowareSyncRun.status == SyncStatus.RUNNING
        )
    )


def test_sync_holds_no_open_transaction_during_dav_fetch(
    client: TestClient, world: World, fake: FakeDav, database: Database
) -> None:
    """Produktionsbefund 27.09.2026: der DAV-Abruf lief innerhalb der Transaktion, die die
    Laufzeile angelegt hatte (``idle in transaction`` ueber Minuten). Jetzt ist die Laufzeile
    mit Status ``running`` waehrend des Abrufs aus einer zweiten Verbindung sichtbar, was nur nach
    Commit moeglich ist, und keine Session der App-Rolle steht ``idle in transaction``."""
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    observed: list[tuple[int, int]] = []

    async def probe(request: httpx.Request) -> None:
        if not _is_tree_propfind(request) or observed:
            return
        engine = create_async_engine(database.app_url, poolclass=NullPool)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                running = int(await session.scalar(_running_count_sql()) or 0)
                idle_in_tx = int(
                    await session.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE usename = current_user AND datname = current_database() "
                            "AND state = 'idle in transaction'"
                        )
                    )
                    or 0
                )
            observed.append((running, idle_in_tx))
        finally:
            await engine.dispose()

    fake.hook = probe
    run = _ok(client.post(f"{IM}/sync/webdav", headers=h))
    assert observed == [(1, 0)], observed
    row = next(r for r in _ok(client.get(f"{IM}/sync/runs", headers=h)) if r["id"] == run["run_id"])
    assert (row["status"], row["seen"]) == ("ok", 2)  # added haengt von Vorlaeufen im Modul ab


def test_parallel_start_is_refused_while_first_run_fetches(
    client: TestClient, world: World, fake: FakeDav, database: Database, redis_url: str
) -> None:
    """Zwei gleichzeitige Starts derselben Art: der zweite trifft auf die committete
    ``running``-Zeile und wird mit ``IMW_SYNC_RUNNING`` abgewiesen, der erste laeuft normal zu Ende.
    Ein Fehler im Abruf setzt den Lauf in eigener Transaktion auf ``failed``."""
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    settings = _settings(database, redis_url)

    async def scenario() -> None:
        engine = create_async_engine(settings.database_url.get_secret_value(), poolclass=NullPool)
        try:
            factory = create_session_factory(engine)
            started = asyncio.Event()
            release = asyncio.Event()

            async def block_first_fetch(request: httpx.Request) -> None:
                if _is_tree_propfind(request):
                    started.set()
                    await release.wait()

            fake.hook = block_first_fetch
            first = asyncio.create_task(
                immoware_service.run_sync(factory, world.tenant_a, SyncKind.WEBDAV)
            )
            await started.wait()
            with pytest.raises(ProblemError) as excinfo:
                await immoware_service.run_sync(factory, world.tenant_a, SyncKind.WEBDAV)
            assert excinfo.value.error is ErrorCodes.IMW_SYNC_RUNNING
            release.set()
            run = await first
            assert run.status is SyncStatus.OK
            assert run.seen == 2

            # Fehlerfall: ein Verbindungsabbruch im CardDAV-Abruf (WebDAV toleriert Fehler je
            # Ordner) setzt die Laufzeile in eigener Transaktion auf ``failed``; keine Zeile
            # bleibt auf ``running`` stehen.
            async def explode(request: httpx.Request) -> None:
                if request.url.path == "/addressbooks/default/":
                    raise httpx.ConnectError("verbindung abgebrochen")

            fake.hook = explode
            failed = await immoware_service.run_sync(factory, world.tenant_a, SyncKind.CARDDAV)
            assert failed.status is SyncStatus.FAILED
            # ``ReadOnlyDavClient`` bildet Transportfehler auf IMW_UNAVAILABLE ab; der
            # gespeicherte Text ist die bereinigte Meldung ohne Zugangsdaten.
            assert failed.error is not None
            assert "Immoware24" in failed.error
            assert fake.password not in failed.error
            async with tenant_transaction(factory, world.tenant_a) as session:
                still_running = await session.scalar(
                    select(func.count())
                    .select_from(ImmowareSyncRun)
                    .where(ImmowareSyncRun.status == SyncStatus.RUNNING)
                )
                assert int(still_running or 0) == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_router_409_and_task_skip_while_running_and_stale_run_is_closed(
    client: TestClient,
    world: World,
    fake: FakeDav,
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bei vorhandener ``running``-Zeile antwortet der Router 409 mit Problemcode MHVP-IMW-0005
    und der Celery-Task ueberspringt den Tenant. Eine ``running``-Zeile aelter als
    ``STALE_RUNNING_AFTER`` gilt als verwaist: der naechste Start schliesst sie als ``failed`` ab
    und laeuft selbst durch."""
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    settings = _settings(database, redis_url)
    stale_id = uuid.uuid4()

    async def insert_running(started_at: datetime) -> None:
        engine = create_async_engine(database.app_url, poolclass=NullPool)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                session.add(
                    ImmowareSyncRun(
                        id=stale_id,
                        tenant_id=world.tenant_a,
                        kind=SyncKind.WEBDAV,
                        started_at=started_at,
                        status=SyncStatus.RUNNING,
                    )
                )
        finally:
            await engine.dispose()

    # 45 Minuten alt: aelter als poll_minutes (30), juenger als STALE_RUNNING_AFTER -> laeuft noch.
    asyncio.run(insert_running(datetime.now(UTC) - timedelta(minutes=45)))
    response = client.post(f"{IM}/sync/webdav", headers=h)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "MHVP-IMW-0005"
    assert body["run_id"] == str(stale_id)

    # The task walks every active tenant of the database. Connections of other modules or of
    # earlier runs against the same database become due after poll_minutes and would count as
    # "ran"; they are held by "another worker" (Redis lock) so the totals describe this tenant.
    try_lock = immoware_tasks._try_lock
    own_key = f"immoware:sync:{SyncKind.WEBDAV.value}:{world.tenant_a}"
    monkeypatch.setattr(
        immoware_tasks,
        "_try_lock",
        lambda redis_client, key: key == own_key and try_lock(redis_client, key),
    )
    totals = asyncio.run(immoware_tasks._sync_all(settings, SyncKind.WEBDAV))
    assert (totals["ran"], totals["failed"]) == (0, 0)
    assert totals["skipped"] >= 1
    runs = _ok(client.get(f"{IM}/sync/runs", headers=h))
    assert [r["id"] for r in runs if r["status"] == "running"] == [str(stale_id)]

    # Verwaist: Startzeit vor 3 Stunden -> neuer Lauf schliesst die alte Zeile ab.
    async def age_running() -> None:
        engine = create_async_engine(database.app_url, poolclass=NullPool)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                row = await session.get(ImmowareSyncRun, stale_id)
                assert row is not None
                row.started_at = datetime.now(UTC) - timedelta(hours=3)
        finally:
            await engine.dispose()

    asyncio.run(age_running())
    new_run = _ok(client.post(f"{IM}/sync/webdav", headers=h))
    by_id = {r["id"]: r for r in _ok(client.get(f"{IM}/sync/runs", headers=h))}
    assert by_id[new_run["run_id"]]["status"] == "ok"
    assert by_id[str(stale_id)]["status"] == "failed"
    assert "abgebrochen" in (by_id[str(stale_id)]["error"] or "")


@pytest.mark.parametrize(
    "field",
    ["base_url", "carddav_url", "caldav_url"],
)
@pytest.mark.parametrize(
    "url",
    ["http://169.254.169.254/latest/", "https://127.0.0.1:5432/", "https://10.0.0.7/dav/"],
)
def test_gam302_internal_dav_targets_are_refused_on_save(
    client: TestClient, world: World, fake: FakeDav, field: str, url: str
) -> None:
    """GAM-302: metadata service, loopback and private networks are refused for every URL."""
    h = bearer(login(client, world, "m32admin"))
    body = {"base_url": BASE_URL, "username": "hub", "enabled": False, field: url}
    response = client.put(f"{IM}/connection", json=body, headers=h)
    assert response.status_code == 422, response.text


def test_gam303_tls_switch_off_needs_platform_admin(
    client: TestClient, world: World, fake: FakeDav
) -> None:
    """GAM-303: a tenant administrator cannot switch TLS verification off."""
    h = bearer(login(client, world, "m32admin"))
    _connect(client, h, fake)
    body = {
        "base_url": BASE_URL,
        "carddav_url": CARDDAV_URL,
        "caldav_url": CALDAV_URL,
        "username": "hub",
        "enabled": True,
        "verify_tls": False,
    }
    denied = client.put(f"{IM}/connection", json=body, headers=h)
    assert denied.status_code == 403, denied.text
    assert _ok(client.get(f"{IM}/connection", headers=h))["verify_tls"] is True
