"""Compact view and HTML newsletter display (operator 30.09.2026)."""

import asyncio
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail import _upload

pytestmark = pytest.mark.integration
M = "/api/v1/mail"

NEWSLETTER = """<html><head><style>p{color:red}</style></head><body>
<style>body { margin: 0; padding: 0; }</style><table><tr><td><table><tr><td>
<p>Herbstausgabe der Hausnachrichten.</p><p>Die Heizperiode beginnt am 01.10.2026.</p>
</td></tr></table></td></tr></table></body></html>"""


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"mcomp-{RUN}", name=f"CP {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"cpb-{RUN}", name=f"CPB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("cpadmin", "tenant_admin", a),
            ("cpread", "read_only_master_data", a),
            ("cpadminb", "tenant_admin", b),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ingest(client: TestClient, h: dict[str, str], raw: bytes, name: str) -> dict[str, Any]:
    doc = _upload(client, h, name, raw)
    return _ok(client.post(f"{M}/ingest", json={"document_id": doc}, headers=h), 201)


def test_newsletter_and_compact_view(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "cpadmin"))
    sender = f"kompakt{RUN}@example.com"
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "salutation": "Frau",
                "first_name": "Karla",
                "last_name": f"Kompakt{RUN}",
                "emails": [{"email": sender}],
            },
            headers=h,
        ),
        201,
    )
    news = EmailMessage()
    news["From"], news["To"], news["Subject"] = sender, "info@example.com", "Newsletter"
    news["Message-ID"] = f"<news-{RUN}@example.test>"
    news.set_content(NEWSLETTER, subtype="html")
    msg = _ingest(client, h, bytes(news), "news.eml")
    detail = _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))
    assert not detail["body"].startswith("body {")
    assert "margin" not in detail["body"]
    assert "Herbstausgabe" in detail["body"]
    assert "margin" not in (detail["body_html"] or "")

    compact = _ok(client.get(f"{M}/messages/{msg['id']}/compact", headers=h))
    assert compact["summary"]["source"] == "excerpt"
    assert compact["summary"]["text"].startswith("Herbstausgabe")
    assert compact["crm"]["contact"]["id"] == contact["id"]
    assert compact["crm"]["open_tickets"]["count"] >= 0
    assert compact["crm"]["open_items"] == {"count": 0, "overdue": 0, "remaining": "0.00"}
    assert compact["reply"]["source"] == "template"
    assert compact["reply"]["text"].startswith("Sehr geehrte Frau")
    assert compact["can_reply"] is True

    # Without a released provider the AI summary is skipped and nothing is stored.
    skipped = _ok(client.post(f"{M}/messages/{msg['id']}/compact/summary", headers=h))
    assert skipped["status"] in {"skipped", "failed"}
    again = _ok(client.get(f"{M}/messages/{msg['id']}/compact", headers=h))
    assert again["summary"]["source"] == "excerpt"

    # Read only role may read, not trigger the AI run; other tenant sees nothing.
    hr = bearer(login(client, world, "cpread"))
    reader = client.get(f"{M}/messages/{msg['id']}/compact", headers=hr)
    assert reader.status_code in {200, 403}
    assert client.post(f"{M}/messages/{msg['id']}/compact/summary", headers=hr).status_code == 403
    hb = bearer(login(client, world, "cpadminb"))
    assert client.get(f"{M}/messages/{msg['id']}/compact", headers=hb).status_code == 404
    assert client.get(f"{M}/messages/not-a-uuid/compact", headers=h).status_code == 422


class _FakeFetcher:
    """IMAP server double: UIDVALIDITY 77, messages by UID (no network)."""

    def __init__(self, messages: dict[int, bytes], validity: int = 77) -> None:
        self.messages = messages
        self.validity = validity
        self.calls: list[tuple[int | None, Any]] = []

    def fetch(self, mailbox: Any, *, after_uid: int | None, since: Any, limit: int) -> Any:
        from mhvp.communication.imap import FetchResult

        self.calls.append((after_uid, since))
        uids = sorted(u for u in self.messages if after_uid is None or u > after_uid)
        return FetchResult(
            uidvalidity=self.validity,
            uidnext=max(self.messages, default=0) + 1,
            messages=[(u, self.messages[u]) for u in uids[:limit]],
            more=len(uids) > limit,
        )


def _plain(sender: str, subject: str, msg_id: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        sender,
        "imap@example.com",
        subject,
        msg_id,
    )
    msg.set_content(body)
    msg.add_attachment(b"%PDF-1.4 x", maintype="application", subtype="pdf", filename="a.pdf")
    return bytes(msg)


def test_imap_fetch_pipeline(client: TestClient, world: World) -> None:
    from mhvp.communication import imap

    h = bearer(login(client, world, "cpadmin"))
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={
                "address": f"imap{RUN}@example.com",
                "kind": "imap",
                "imap_host": "imap.example.invalid",
                "username": "user",
                "secret": "geheim",
                "enabled": True,
            },
            headers=h,
        ),
        201,
    )
    one = _plain("a@example.org", "Heizung", f"<imap1-{RUN}@x>", "Die Heizung ist kalt.")
    two = _plain("b@example.org", "Wasser", f"<imap2-{RUN}@x>", "Wasser tropft.")
    fake = _FakeFetcher({10: one, 11: two})
    previous = imap.set_fetcher(fake)
    try:
        first = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
        assert first["created"] == 2
        assert first["failed"] == 0
        assert fake.calls[0][0] is None
        assert fake.calls[0][1] is not None  # initial window
        again = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
        assert again["fetched"] == 0
        assert fake.calls[1][0] == 11  # cursor
        # New UIDVALIDITY: cursor restarts, re-fetched mails are duplicates, no new rows.
        fake.validity = 78
        reset = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
        assert reset["uidvalidity_reset"] is True
        refetch = _ok(client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h))
        assert refetch["created"] == 0
        assert refetch["duplicates"] == 2
        rows = _ok(client.get(f"{M}/messages", params={"mailbox_id": box["id"]}, headers=h))
        subjects = sorted(r["subject"] for r in rows if r["mailbox_id"] == box["id"])
        assert subjects == ["Heizung", "Wasser"]
        assert all(
            len(r["attachment_document_ids"]) == 1 for r in rows if r["mailbox_id"] == box["id"]
        )

        # Login error: stored on the mailbox, secret never in the answer.
        class _Denied:
            def fetch(self, *a: Any, **k: Any) -> Any:
                raise imap.ImapError("IMAP-Anmeldung abgelehnt.")

        imap.set_fetcher(_Denied())
        denied = client.post(f"{M}/mailboxes/{box['id']}/sync", headers=h)
        assert denied.status_code == 409
        assert "geheim" not in denied.text
        boxes = _ok(client.get(f"{M}/mailboxes", headers=h))
        assert (
            next(b for b in boxes if b["id"] == box["id"])["last_error"]
            == "IMAP-Anmeldung abgelehnt."
        )
    finally:
        imap.set_fetcher(previous)
    hb = bearer(login(client, world, "cpadminb"))
    assert client.post(f"{M}/mailboxes/{box['id']}/sync", headers=hb).status_code == 404
    hr = bearer(login(client, world, "cpread"))
    assert client.post(f"{M}/mailboxes/{box['id']}/sync", headers=hr).status_code == 403
