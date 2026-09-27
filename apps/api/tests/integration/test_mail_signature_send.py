"""E-Mail-Signatur im Versandpfad (Review 1.36.0): der gespeicherte Text ist die einzige Quelle.
Die Signatur steht ab dem Anlegen des Entwurfs (Antworten, Vorschlag übernehmen, Ticketantwort)
oder spätestens ab dem Einreichen im Text, die freigebende Person sieht genau den versendeten
Text, der Versand hängt nichts an (auch nicht an vor 1.36.0 eingereichte Entwürfe). Die
E-Mail-Zeile ist die Adresse des sendenden Postfachs, nie die Anmeldeadresse; die interne
Bereitschaftsnummer (M35) erscheint nie. Antworten öffnet nur den eigenen offenen Entwurf im
Postfach der beantworteten Kopie. Eine geänderte Durchwahl wird gespeichert; eine gespeicherte
Vorlage mit unbekannten Platzhaltern blockiert weder Vorschau noch Entwurf."""

import asyncio
import email
import json
from collections.abc import Iterator
from email import policy
from email.message import EmailMessage
from typing import Any

import boto3
import httpx
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.communication import gmail
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail import _upload
from tests.integration.test_m20_mail_approval import FakeGmail, _eml

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
S = "/api/v1/mail/signature"
T = "/api/v1/tickets"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"sga-{RUN}", name=f"SigA {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"sgb-{RUN}", name=f"SigB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "sigadmin": [(a, "tenant_admin")],
            "sigfrei": [(a, "tenant_admin")],
            "sigstd": [(a, "standard")],
            "sigstd2": [(a, "standard")],
            "sigboth": [(a, "standard"), (b, "standard")],
        }
        for name, memberships in specs.items():
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            for tenant, role in memberships:
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
    return response.json() if response.content else None


def _gmail_box(client: TestClient, h: dict[str, str], address: str) -> dict[str, Any]:
    box: dict[str, Any] = _ok(
        client.post(
            f"{M}/mailboxes", json={"address": address, "kind": "gmail", "secret": "rt"}, headers=h
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=h))
    return box


def _imap_box(client: TestClient, h: dict[str, str], address: str) -> dict[str, Any]:
    box: dict[str, Any] = _ok(
        client.post(f"{M}/mailboxes", json={"address": address, "kind": "imap"}, headers=h), 201
    )
    return box


def _ingest(client: TestClient, h: dict[str, str], raw: bytes, box_id: str) -> dict[str, Any]:
    doc = _upload(client, h, "mail.eml", raw)
    msg: dict[str, Any] = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box_id}, headers=h),
        201,
    )
    return msg


def _inbound(
    client: TestClient, h: dict[str, str], tag: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    box = _gmail_box(client, h, f"box-{tag}@example.com")
    raw = _eml(f"mieter-{tag}@example.com", f"Frage {tag}", f"<{tag}@x>")
    return _ingest(client, h, raw, box["id"]), box


def _membership_id(client: TestClient, admin: dict[str, str], name: str) -> str:
    members = _ok(client.get("/api/v1/tenant/members", headers=admin))
    return str(next(m for m in members if m["display_name"] == name)["membership_id"])


def _profile_with_on_call_number(client: TestClient, admin: dict[str, str]) -> None:
    _ok(
        client.put(
            f"{S}/profile",
            json={"position": "Objektbetreuung", "phone": "02173 100"},
            headers=admin,
        )
    )
    # Interne Bereitschaftsnummer (SMS-Eskalation, M35): gehört nie in eine Signatur.
    mid = _membership_id(client, admin, "sigadmin")
    _ok(
        client.put(
            f"/api/v1/tenant/members/{mid}/mobile-phone",
            json={"mobile_phone": "+49 170 5550000"},
            headers=admin,
        ),
        204,
    )


def _sent_text(fake: FakeGmail) -> str:
    parsed = email.message_from_bytes(fake.sent[-1], policy=policy.default)
    assert parsed.get_content_type() in ("text/plain", "multipart/mixed")
    part = parsed.get_body(("plain",))
    assert part is not None
    assert parsed.get_body(("html",)) is None  # 1.36.0: Versand nur als Klartext
    return str(part.get_content())


def _approve(client: TestClient, frei: dict[str, str], message_id: str) -> dict[str, Any]:
    _ok(client.post(f"{M}/mail-approval/reauth", json={"password": PASSWORD}, headers=frei))
    sent: dict[str, Any] = _ok(client.post(f"{M}/messages/{message_id}/approve", headers=frei))
    assert sent["status"] == "sent"
    return sent


def test_signature_is_stored_in_the_body_and_sent_verbatim(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    admin = bearer(login(client, world, "sigadmin"))
    frei = bearer(login(client, world, "sigfrei"))
    _profile_with_on_call_number(client, admin)
    msg, box = _inbound(client, admin, f"store-{RUN}")

    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin), 201)
    body = draft["body"]
    assert "Mit freundlichen Grüßen\n\n-- \nsigadmin\nObjektbetreuung\n" in body
    assert "Telefon 02173 100" in body
    # E-Mail-Zeile: Adresse des sendenden Postfachs, nie die Anmeldeadresse.
    assert f"E-Mail {box['address']}" in body
    assert world.email("sigadmin") not in body
    # Keine Bereitschaftsnummer, keine Platzhalter der Vorlage neben der Signatur.
    assert "Mobil" not in body
    assert "5550000" not in body
    assert "[Name]" not in body
    assert "[Firma]" not in body

    # Die freigebende Person sieht genau den Text, der versendet wird.
    submitted = _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=admin))
    assert submitted["body"] == body
    sent = _approve(client, frei, draft["id"])
    assert sent["body"] == body
    assert _sent_text(fake).rstrip("\n") == body.rstrip("\n")


def test_submit_signs_missing_body_once_and_legacy_pending_is_sent_verbatim(
    client: TestClient, world: World, fake: FakeGmail, database: Database
) -> None:
    admin = bearer(login(client, world, "sigadmin"))
    frei = bearer(login(client, world, "sigfrei"))
    _profile_with_on_call_number(client, admin)

    # Entwurf ohne Signatur (Playbook, Vorschlag, Job): Einreichen fügt sie in den Text ein.
    msg, _ = _inbound(client, admin, f"plain-{RUN}")
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin), 201)
    _ok(
        client.patch(f"{M}/messages/{draft['id']}/draft", json={"body": "Nur Text."}, headers=admin)
    )
    submitted = _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=admin))
    assert submitted["body"].startswith("Nur Text.\n\n-- \nsigadmin\nObjektbetreuung\n")
    assert submitted["body"].count("Telefon 02173 100") == 1
    sent = _approve(client, frei, draft["id"])
    assert _sent_text(fake).rstrip("\n") == sent["body"].rstrip("\n")

    # Trennzeile gelöscht: keine zweite Signatur beim Einreichen.
    msg, _ = _inbound(client, admin, f"marker-{RUN}")
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin), 201)
    edited = draft["body"].replace("\n-- \n", "\n")
    _ok(client.patch(f"{M}/messages/{draft['id']}/draft", json={"body": edited}, headers=admin))
    submitted = _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=admin))
    assert submitted["body"] == edited
    assert submitted["body"].count("Telefon 02173 100") == 1

    # Vor 1.36.0 eingereicht (Text ohne Signatur): wird unverändert versendet.
    msg, _ = _inbound(client, admin, f"legacy-{RUN}")
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin), 201)
    _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=admin))
    engine = sa.create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(
            sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(world.tenant_a)},
        )
        conn.execute(
            sa.text("UPDATE message SET body = :body WHERE id = :id AND status = 'pending'"),
            {"body": "Alter Entwurf ohne Signatur.", "id": draft["id"]},
        )
    engine.dispose()
    sent = _approve(client, frei, draft["id"])
    assert sent["body"] == "Alter Entwurf ohne Signatur."
    assert _sent_text(fake).rstrip("\n") == "Alter Entwurf ohne Signatur."


def test_submit_does_not_sign_an_edited_signature_block_again(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "sigadmin"))
    _profile_with_on_call_number(client, admin)
    try:
        # Signaturblock bearbeitet (Durchwahl für diese Mail entfernt): keine zweite Signatur.
        msg, _ = _inbound(client, admin, f"sigedit-{RUN}")
        draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin), 201)
        assert "\nTelefon 02173 100\n" in draft["body"]
        edited = draft["body"].replace("Telefon 02173 100\n", "")
        _ok(client.patch(f"{M}/messages/{draft['id']}/draft", json={"body": edited}, headers=admin))
        submitted = _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=admin))
        assert submitted["body"] == edited
        assert submitted["body"].count("\n-- \n") == 1

        # Position zwischen Anlegen und Einreichen geändert: die gespeicherte Signatur bleibt.
        msg, _ = _inbound(client, admin, f"sigmoved-{RUN}")
        draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin), 201)
        _ok(
            client.put(
                f"{S}/profile",
                json={"position": "Buchhaltung", "phone": "02173 100"},
                headers=admin,
            )
        )
        submitted = _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=admin))
        assert submitted["body"] == draft["body"]
        assert "Buchhaltung" not in submitted["body"]

        # Weder Signaturtext noch Trennzeile: Einreichen fügt die aktuelle Signatur an.
        msg, _ = _inbound(client, admin, f"sigbare-{RUN}")
        draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin), 201)
        bare = draft["body"].replace("\n-- \n", "\n").replace("Telefon 02173 100\n", "")
        _ok(client.patch(f"{M}/messages/{draft['id']}/draft", json={"body": bare}, headers=admin))
        submitted = _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=admin))
        assert submitted["body"].startswith(bare.rstrip() + "\n\n-- \nsigadmin\nBuchhaltung\n")
        assert submitted["body"].count("\n-- \n") == 1
    finally:
        _profile_with_on_call_number(client, admin)


def test_ticket_reply_stores_the_signed_body_that_is_sent(
    client: TestClient, world: World, fake: FakeGmail
) -> None:
    admin = bearer(login(client, world, "sigadmin"))
    _profile_with_on_call_number(client, admin)
    msg, box = _inbound(client, admin, f"ticket-{RUN}")
    ticket_id = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), 201)[
        "ticket_id"
    ]
    reply = _ok(
        client.post(
            f"{T}/{ticket_id}/reply",
            json={"subject": "AW: Frage", "body": "Wir kümmern uns.", "confirm": True},
            headers=admin,
        ),
        201,
    )
    assert reply["direct_send"]["attempted"] is True
    assert reply["status"] == "sent"
    assert reply["body"].startswith("Wir kümmern uns.\n\n-- \nsigadmin\nObjektbetreuung\n")
    assert f"E-Mail {box['address']}" in reply["body"]
    assert "5550000" not in reply["body"]
    assert _sent_text(fake).rstrip("\n") == reply["body"].rstrip("\n")


def test_reply_draft_reuses_only_the_callers_draft_in_the_answered_mailbox(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "sigadmin"))
    std = bearer(login(client, world, "sigstd"))
    std2 = bearer(login(client, world, "sigstd2"))
    info = _imap_box(client, admin, f"info-sg{RUN}@example.com")
    brink = _imap_box(client, admin, f"brink-sg{RUN}@example.com")
    assert info["is_collective"] is True
    assert brink["is_collective"] is False
    _ok(client.patch(f"{M}/mailboxes/{info['id']}", json={"is_default": True}, headers=admin))
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = (
        f"Mieter <dupsig{RUN}@example.com>",
        "info@example.com, brink@example.com",
        f"Doppelt signiert {RUN}",
    )
    msg["Message-ID"] = f"<dupsig-{RUN}@x>"
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content("Gleicher Text")
    collective = _ingest(client, admin, bytes(msg), info["id"])
    personal = _ingest(client, admin, bytes(msg), brink["id"])
    assert personal["id"] != collective["id"]

    # Entwurf im persönlichen Postfach (brink@), das sigstd nicht nutzen darf.
    brink_draft = _ok(
        client.post(
            f"{M}/messages/{personal['id']}/reply-draft",
            json={"body": "Entwurf Brink."},
            headers=admin,
        ),
        201,
    )
    assert brink_draft["mailbox_id"] == brink["id"]

    # Antworten auf die Kopie im Sammelpostfach: eigener neuer Entwurf, nie der fremde.
    own = _ok(client.post(f"{M}/messages/{collective['id']}/reply-draft", headers=std), 201)
    assert own["id"] != brink_draft["id"]
    assert own["mailbox_id"] == info["id"]
    assert "Entwurf Brink." not in own["body"]
    # Vorschlag übernehmen ersetzt nur den eigenen Entwurf.
    again = _ok(
        client.post(
            f"{M}/messages/{collective['id']}/reply-draft",
            json={"body": "Vorschlag."},
            headers=std,
        ),
        201,
    )
    assert again["id"] == own["id"]
    assert again["body"].startswith("Vorschlag.\n\n-- \nsigstd\n")
    untouched = _ok(client.get(f"{M}/messages/{brink_draft['id']}", headers=admin))
    assert untouched["body"].startswith("Entwurf Brink.")
    assert untouched["updated_by"] != str(world.users["sigstd"])
    _ok(client.patch(f"{M}/messages/{own['id']}/draft", json={"body": "Eigener."}, headers=std))

    # Kollege im selben Postfach: eigener Entwurf, der von sigstd bleibt unberührt.
    other = _ok(client.post(f"{M}/messages/{collective['id']}/reply-draft", headers=std2), 201)
    assert other["id"] not in (own["id"], brink_draft["id"])
    assert _ok(client.get(f"{M}/messages/{own['id']}", headers=std))["body"] == "Eigener."
    assert (
        _ok(client.post(f"{M}/messages/{collective['id']}/reply-draft", headers=std), 201)["id"]
        == own["id"]
    )
    assert (
        _ok(client.post(f"{M}/messages/{personal['id']}/reply-draft", headers=admin), 201)["id"]
        == brink_draft["id"]
    )


def test_profile_keeps_a_changed_extension(client: TestClient, world: World) -> None:
    std = bearer(login(client, world, "sigstd"))
    admin = bearer(login(client, world, "sigadmin"))
    _ok(
        client.put(
            f"{S}/profile", json={"position": "Assistenz", "phone": "02173 111"}, headers=std
        )
    )
    changed = _ok(
        client.put(
            f"{S}/profile", json={"position": "Assistenz", "phone": "02173 222"}, headers=std
        )
    )
    assert changed["phone"] == "02173 222"
    assert _ok(client.get(f"{S}/profile", headers=std))["phone"] == "02173 222"
    preview = _ok(client.get(f"{S}/preview", headers=std))["text"]
    assert "Telefon 02173 222" in preview
    assert "02173 111" not in preview
    # Das Ereignisprotokoll enthält keine Durchwahl.
    events = _ok(
        client.get(
            "/api/v1/tenant/events",
            params={"type": "membership.position_changed"},
            headers=admin,
        )
    )
    assert "02173" not in json.dumps(events)


def test_preview_email_is_the_personal_mailbox_of_the_tenant(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "sigadmin"))
    both_a = bearer(login(client, world, "sigboth", world.tenant_a))
    both_b = bearer(login(client, world, "sigboth", world.tenant_b))
    login_address = world.email("sigboth")
    mid = _membership_id(client, admin, "sigboth")
    _ok(
        client.put(
            f"/api/v1/tenant/members/{mid}/mobile-phone",
            json={"mobile_phone": "+49 171 4440000"},
            headers=admin,
        ),
        204,
    )

    def preview(h: dict[str, str]) -> str:
        return str(_ok(client.get(f"{S}/preview", headers=h))["text"])

    # Ohne persönliches Postfach: keine E-Mail-Zeile, nie die Anmeldeadresse, nie Mobil.
    for h in (both_a, both_b):
        text = preview(h)
        assert "E-Mail" not in text
        assert login_address not in text
        assert "4440000" not in text
    personal = _imap_box(client, admin, f"sigboth-{RUN}@example.com")
    collective = _imap_box(client, admin, f"post-sg{RUN}@example.com")
    for box in (personal, collective):
        _ok(
            client.put(
                f"{M}/mailboxes/{box['id']}/users",
                json={"user_ids": [str(world.users["sigboth"])]},
                headers=admin,
            )
        )
    assert f"E-Mail {personal['address']}" in preview(both_a)
    # Mandant B hat kein Postfach für ihn: keine Adresse aus Mandant A.
    assert "E-Mail" not in preview(both_b)
    # Zweites persönliches Postfach: nicht eindeutig, die E-Mail-Zeile entfällt.
    second = _imap_box(client, admin, f"sigboth2-{RUN}@example.com")
    _ok(
        client.put(
            f"{M}/mailboxes/{second['id']}/users",
            json={"user_ids": [str(world.users["sigboth"])]},
            headers=admin,
        )
    )
    assert "E-Mail" not in preview(both_a)


def test_stored_template_with_unknown_placeholders_never_blocks(
    client: TestClient, world: World, database: Database
) -> None:
    admin = bearer(login(client, world, "sigadmin"))
    msg, _ = _inbound(client, admin, f"tpl-{RUN}")
    # Vorlage aus der Zeit vor der Prüfung beim Speichern (direkt gespeichert).
    template = {"text": "{name}\n{company.name}\n{name[0]}\n{name:>999999999}", "html": "{x.y}"}
    engine = sa.create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
                {"tenant": str(world.tenant_a)},
            )
            conn.execute(
                sa.text(
                    "UPDATE tenant_settings SET signature_template = CAST(:t AS jsonb) "
                    "WHERE tenant_id = :tenant"
                ),
                {"t": json.dumps(template), "tenant": str(world.tenant_a)},
            )
        preview = _ok(client.get(f"{S}/preview", headers=admin))
        assert preview["text"] == "-- \nsigadmin"
        draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", headers=admin), 201)
        assert draft["body"].endswith("\n\n-- \nsigadmin\n")
        # Speichern derselben Vorlage wird mit den unbekannten Namen abgelehnt.
        refused = client.patch(
            "/api/v1/tenant/settings", json={"signature_template": template}, headers=admin
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["unknown_placeholders"] == [
            "company.name",
            "name:>999999999",
            "name[0]",
            "x.y",
        ]
    finally:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE tenant_settings SET signature_template = '{}'::jsonb "
                    "WHERE tenant_id = :tenant"
                ),
                {"tenant": str(world.tenant_a)},
            )
        engine.dispose()
