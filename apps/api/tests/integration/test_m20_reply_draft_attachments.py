"""Antworten mit Anhängen (operator 27.09.2026): ein offener Entwurf je Eingangsmail (Vorbereiten
und Antworten öffnen denselben), An/Cc bearbeitbar, Anhänge aus dem DMS verknüpfen (Verweis),
Upload vom lokalen Rechner (Typprüfung), Entfernen, Versand über Gmail mit allen Anhängen,
Rechte (nur Lesen darf nicht ändern) und Mandantentrennung (fremdes Dokument nicht anhängbar)."""

import asyncio
import email
from collections.abc import Iterator
from email import policy
from typing import Any

import boto3
import httpx
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.communication import gmail
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail_approval import FakeGmail, _eml

pytestmark = pytest.mark.integration
M = "/api/v1/mail"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ra-{RUN}", name=f"ReplyA {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"rb-{RUN}", name=f"ReplyB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("raadmin", "tenant_admin", a),
            ("rafreigeber", "tenant_admin", a),
            ("raread", "read_only_master_data", a),
            ("rbadmin", "tenant_admin", b),
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
def fake() -> FakeGmail:
    return FakeGmail()


@pytest.fixture
def client(
    database: Database, redis_url: str, fake: FakeGmail, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    settings = _settings(database, redis_url).model_copy(
        update={"google_client_id": "cid", "google_client_secret": SecretStr("csecret")}
    )
    original = gmail.GmailClient

    def patched(client_id: str, client_secret: str, refresh_token: str, **_: Any) -> Any:
        return original(
            client_id, client_secret, refresh_token, transport=httpx.MockTransport(fake.handler)
        )

    monkeypatch.setattr(gmail, "GmailClient", patched)
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _upload_document(
    c: TestClient, h: dict[str, str], name: str, data: bytes, mime: str, title: str | None = None
) -> str:
    form = {"title": title} if title else {}
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, mime)}, data=form, headers=h),
            201,
        )["id"]
    )


def _inbound(client: TestClient, h: dict[str, str], tag: str) -> tuple[dict[str, Any], str]:
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"box-{tag}@example.com", "kind": "gmail", "secret": "rt"},
            headers=h,
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h))
    doc = _upload_document(
        client,
        h,
        f"{tag}.eml",
        _eml(f"mieter-{tag}@example.com", f"Frage {tag}", f"<{tag}@x>"),
        "message/rfc822",
    )
    msg = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box["id"]}, headers=h),
        201,
    )
    return dict(msg), str(box["id"])


def test_reply_draft_is_reused_and_editable(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "raadmin"))
    msg, _ = _inbound(client, h, f"reuse-{RUN}")
    first = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    # "Vorbereiten" übernimmt den Vorschlag in denselben Entwurf, "Antworten" öffnet ihn.
    second = _ok(
        client.post(
            f"{M}/messages/{msg['id']}/reply-draft",
            json={"body": "Vorgeschlagener Text."},
            headers=h,
        ),
        201,
    )
    assert second["id"] == first["id"]
    assert second["body"] == "Vorgeschlagener Text."
    third = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    assert third["id"] == first["id"]
    assert third["body"] == "Vorgeschlagener Text."
    drafts = _ok(
        client.get(f"{M}/messages", params={"direction": "out", "status": "draft"}, headers=h)
    )
    assert sum(1 for d in drafts if d["thread_id"] == first["thread_id"]) == 1
    edited = _ok(
        client.patch(
            f"{M}/messages/{first['id']}/draft",
            json={
                "to_addresses": ["a@example.com"],
                "cc_addresses": ["kopie@example.com"],
                "subject": "Neu",
                "body": "Manuell bearbeitet.",
            },
            headers=h,
        )
    )
    assert edited["cc_addresses"] == ["kopie@example.com"]
    assert edited["body"] == "Manuell bearbeitet."
    # Antworten auf einen Ausgang ist kein Antworten.
    assert client.post(f"{M}/messages/{first['id']}/reply-draft", headers=h).status_code == 409
    # Ohne Empfänger ist die Einreichung verständlich abgelehnt.
    _ok(client.patch(f"{M}/messages/{first['id']}/draft", json={"to_addresses": []}, headers=h))
    refused = client.post(f"{M}/messages/{first['id']}/submit", headers=h)
    assert refused.status_code == 422
    assert "Empfänger" in refused.json()["detail"]


def test_attachments_dms_upload_remove_and_send(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    h = bearer(login(client, world, "raadmin"))
    freigeber = bearer(login(client, world, "rafreigeber"))
    msg, _ = _inbound(client, h, f"att-{RUN}")
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    assert _ok(client.get(f"{M}/messages/{draft['id']}/attachments", headers=h)) == []

    # Aus dem DMS: Suche nach Titel, Verknüpfung als Verweis.
    dms_id = _upload_document(
        client, h, "hausordnung.pdf", b"%PDF-1.4 hausordnung", "application/pdf", "Hausordnung"
    )
    hits = _ok(
        client.get(
            f"{M}/messages/{draft['id']}/attachment-candidates",
            params={"q": "hausordnung"},
            headers=h,
        )
    )
    assert dms_id in {x["document_id"] for x in hits}
    listed = _ok(
        client.post(
            f"{M}/messages/{draft['id']}/attachments", json={"document_id": dms_id}, headers=h
        ),
        201,
    )
    assert [x["document_id"] for x in listed] == [dms_id]
    # Doppeltes Verknüpfen bleibt ein Anhang.
    listed = _ok(
        client.post(
            f"{M}/messages/{draft['id']}/attachments", json={"document_id": dms_id}, headers=h
        ),
        201,
    )
    assert len(listed) == 1

    # Upload vom lokalen Rechner: Typprüfung wie beim Dokumentenupload.
    bad = client.post(
        f"{M}/messages/{draft['id']}/attachments/upload",
        files={"file": ("setup.exe", b"MZ\x00\x00", "application/x-msdownload")},
        headers=h,
    )
    assert bad.status_code == 422, bad.text
    listed = _ok(
        client.post(
            f"{M}/messages/{draft['id']}/attachments/upload",
            files={"file": ("nachweis.pdf", b"%PDF-1.4 nachweis", "application/pdf")},
            headers=h,
        ),
        201,
    )
    assert [x["filename"] for x in listed] == ["hausordnung.pdf", "nachweis.pdf"]
    uploaded_id = listed[1]["document_id"]
    assert _ok(client.get(f"/api/v1/documents/{uploaded_id}", headers=h))["source"] == "upload"

    # Entfernen: der Verweis verschwindet, das Dokument bleibt.
    listed = _ok(client.delete(f"{M}/messages/{draft['id']}/attachments/{dms_id}", headers=h))
    assert [x["document_id"] for x in listed] == [uploaded_id]
    assert client.get(f"/api/v1/documents/{dms_id}", headers=h).status_code == 200
    assert (
        client.delete(f"{M}/messages/{draft['id']}/attachments/{dms_id}", headers=h).status_code
        == 404
    )

    # Versand: Freigabe durch eine zweite Person, der Anhang geht mit.
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=h))
    # Am eingereichten Entwurf sind Anhänge nicht mehr änderbar.
    assert (
        client.delete(
            f"{M}/messages/{draft['id']}/attachments/{uploaded_id}", headers=h
        ).status_code
        == 409
    )
    _ok(client.post(f"{M}/mail-approval/reauth", json={"password": PASSWORD}, headers=freigeber))
    sent = _ok(client.post(f"{M}/messages/{draft['id']}/approve", headers=freigeber))
    assert sent["status"] == "sent"
    assert len(fake.sent) == 1
    parsed = email.message_from_bytes(fake.sent[0], policy=policy.default)
    names = [part.get_filename() for part in parsed.iter_attachments()]
    assert names == ["nachweis.pdf"]


def test_attachment_permissions_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "raadmin"))
    reader = bearer(login(client, world, "raread"))
    other = bearer(login(client, world, "rbadmin"))
    msg, _ = _inbound(client, h, f"sep-{RUN}")
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=h), 201)
    own_doc = _upload_document(client, h, "eigen.pdf", b"%PDF-1.4 eigen", "application/pdf")
    foreign_doc = _upload_document(
        client, other, "fremd.pdf", b"%PDF-1.4 fremd", "application/pdf", "Fremd"
    )

    # Nur Lesen: keine Änderung an Anhängen.
    assert (
        client.post(
            f"{M}/messages/{draft['id']}/attachments", json={"document_id": own_doc}, headers=reader
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{M}/messages/{draft['id']}/attachments/upload",
            files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")},
            headers=reader,
        ).status_code
        == 403
    )

    # Mandantentrennung: fremdes Dokument ist weder auffindbar noch anhängbar, fremder
    # Entwurf nicht sichtbar.
    hits = _ok(
        client.get(
            f"{M}/messages/{draft['id']}/attachment-candidates", params={"q": "fremd"}, headers=h
        )
    )
    assert foreign_doc not in {x["document_id"] for x in hits}
    assert (
        client.post(
            f"{M}/messages/{draft['id']}/attachments", json={"document_id": foreign_doc}, headers=h
        ).status_code
        == 404
    )
    assert client.get(f"{M}/messages/{draft['id']}/attachments", headers=other).status_code == 404
    assert (
        client.post(
            f"{M}/messages/{draft['id']}/attachments", json={"document_id": own_doc}, headers=other
        ).status_code
        == 404
    )
