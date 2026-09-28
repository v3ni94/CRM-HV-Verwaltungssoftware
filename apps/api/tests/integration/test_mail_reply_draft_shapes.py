"""Hotfix reply draft 500 (Betreibermeldung 27.09.2026): "Antworten" and "Vorschlag
übernehmen" answered "Interner Fehler" (MHVP-CORE-0001).

Root cause: the signature read the whole ``app_user`` row in the tenant session. For a user
with the optional second factor, ``totp_secret`` is sealed in the platform scope and could not
be decrypted in the tenant scope (``CryptoError``), so every path that signs a draft failed
for that user: reply draft (with and without a proposed text), submit, ticket reply and the
signature preview. The test users of the existing suites never had TOTP switched on.

Beyond that, the reply draft endpoint and the ticket reply context must not raise for any
realistic mail data shape: sender without display name or in capitals, missing sender,
encoded words, To/Cc lists empty or with NULL entries, Reply-To present or absent,
collective mailbox copies and duplicates, messages linked to a ticket, removed mailboxes,
users without signature data, empty tenant settings, missing thread ids, long subjects,
reply prefixes, html only bodies, proposed bodies with null fields, an open draft of another
user and a draft whose original was deleted."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    PASSWORD,
    RUN,
    World,
    bearer,
    enable_totp,
    login,
)
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m20_mail import _upload

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
T = "/api/v1/tickets"
SENDER = f"mieter-rds-{RUN}@example.com"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rds-{RUN}", name=f"RDS {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in (
            ("rdsadmin", "tenant_admin"),
            ("rdsstd", "standard"),
            ("rdstotp", "standard"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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
    return response.json() if response.content else None


def _sql(database: Database, world: World, statement: str, **params: Any) -> None:
    engine = sa.create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(
            sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
            {"tenant": str(world.tenant_a)},
        )
        conn.execute(sa.text(statement), params)
    engine.dispose()


def _raw(
    headers: dict[str, str | None], body: str = "Bitte um Rückmeldung.", html: bool = False
) -> bytes:
    """Raw RFC 5322 bytes as a Gmail export delivers them (headers verbatim, 8 bit body)."""
    lines = [f"{k}: {v}" for k, v in headers.items() if v is not None]
    lines.append("Date: Sun, 27 Sep 2026 09:00:00 +0200")
    lines.append("MIME-Version: 1.0")
    lines.append(f'Content-Type: text/{"html" if html else "plain"}; charset="utf-8"')
    lines.append("Content-Transfer-Encoding: 8bit")
    return ("\r\n".join(lines) + "\r\n\r\n" + body + "\r\n").encode()


def _ingest(client: TestClient, h: dict[str, str], raw: bytes, box_id: str) -> dict[str, Any]:
    doc = _upload(client, h, "mail.eml", raw)
    msg: dict[str, Any] = _ok(
        client.post(f"{M}/ingest", json={"document_id": doc, "mailbox_id": box_id}, headers=h),
        201,
    )
    return msg


def _box(
    client: TestClient, h: dict[str, str], address: str, collective: bool = False
) -> dict[str, Any]:
    box: dict[str, Any] = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": address, "kind": "imap", "is_collective": collective},
            headers=h,
        ),
        201,
    )
    return box


def _totp(client: TestClient, world: World, name: str) -> dict[str, str]:
    """Session of a user with the optional second factor switched on, like the operator in
    production: ``app_user.totp_secret`` is then set, sealed in the platform scope."""
    if name not in world.secrets:
        enable_totp(client, world, name)
    return bearer(login(client, world, name))


class _Failures(list[str]):
    def check(self, response: Any, what: str) -> None:
        if response.status_code >= 500:
            self.append(f"{what}: {response.status_code} {response.text[:200]}")


def _reply_everywhere(
    client: TestClient, h: dict[str, str], msg_id: str, what: str, failures: _Failures
) -> None:
    """Antworten (no body and ``{}``), Vorschlag übernehmen (text, null, empty) and, when the
    mail belongs to a ticket, the ticket reply context with and without the message."""
    for payload in (None, {}, {"body": None}, {"body": ""}, {"body": f"Vorschlag {what}"}):
        kwargs: dict[str, Any] = {"headers": h}
        if payload is not None:
            kwargs["json"] = payload
        failures.check(
            client.post(f"{M}/messages/{msg_id}/reply-draft", **kwargs), f"{what} {payload}"
        )
    detail = client.get(f"{M}/messages/{msg_id}", headers=h)
    failures.check(detail, f"{what} detail")
    ticket_id = detail.json().get("ticket_id") if detail.status_code == 200 else None
    if ticket_id:
        failures.check(
            client.get(
                f"{T}/{ticket_id}/reply-context",
                params={"reply_to_message_id": msg_id},
                headers=h,
            ),
            f"{what} ticket reply-context",
        )
        failures.check(client.get(f"{T}/{ticket_id}/reply-context", headers=h), f"{what} ctx")


def test_second_factor_user_gets_a_signed_reply_draft(
    client: TestClient, world: World, database: Database
) -> None:
    """Regression of the production 500: every signing path works for a TOTP user."""
    admin = _totp(client, world, "rdsadmin")
    user = _totp(client, world, "rdstotp")
    box = _box(client, admin, f"totp-{RUN}@example.com")
    _sql(database, world, "UPDATE mailbox SET is_default = true WHERE id = :id", id=box["id"])
    raw = _raw(
        {
            "From": f"Max Mieter <{SENDER}>",
            "To": f"totp-{RUN}@example.com",
            "Subject": "Heizung",
            "Message-ID": f"<totp-{RUN}@x>",
        }
    )
    msg = _ingest(client, admin, raw, box["id"])

    # Antworten: new draft, signed with the display name and the sending mailbox.
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", json={}, headers=user), 201)
    assert draft["to_addresses"] == [SENDER]
    assert "\n-- \nrdstotp\n" in draft["body"]
    assert f"E-Mail totp-{RUN}@example.com" in draft["body"]
    # Vorschlag übernehmen: same draft, proposed text replaces the body and is signed.
    taken = _ok(
        client.post(
            f"{M}/messages/{msg['id']}/reply-draft",
            json={"body": "Der Techniker kommt am Montag."},
            headers=user,
        ),
        201,
    )
    assert taken["id"] == draft["id"]
    assert taken["body"].startswith("Der Techniker kommt am Montag.\n\n-- \nrdstotp\n")
    # Vorschlag übernehmen as the first click creates the draft with the proposed text.
    first = _ok(
        client.post(
            f"{M}/messages/{msg['id']}/reply-draft",
            json={"body": "Direkt übernommen."},
            headers=admin,
        ),
        201,
    )
    assert first["body"].startswith("Direkt übernommen.\n\n-- \nrdsadmin\n")
    submitted = _ok(client.post(f"{M}/messages/{draft['id']}/submit", headers=user))
    assert submitted["status"] == "pending"
    assert submitted["body"].count("\n-- \n") == 1

    preview = _ok(client.get(f"{M}/signature/preview", headers=user))
    assert preview["text"].startswith("-- \nrdstotp")

    # Ticket reply of the same user (signs the stored body when it is created).
    ticket = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), 201)
    context = _ok(client.get(f"{T}/{ticket['ticket_id']}/reply-context", headers=user))
    assert context["to_addresses"] == [SENDER]
    reply = _ok(
        client.post(
            f"{T}/{ticket['ticket_id']}/reply",
            json={
                "subject": "AW: Heizung",
                "body": "Wir kümmern uns.",
                "reply_to_message_id": msg["id"],
                "confirm": True,
            },
            headers=user,
        ),
        201,
    )
    assert reply["status"] == "pending"
    assert "\n-- \nrdstotp\n" in reply["body"]


HEADER_VARIANTS: dict[str, dict[str, str | None]] = {
    "plain": {"From": f"Max Mieter <{SENDER}>", "To": "info@example.com", "Subject": "Frage"},
    "no_display_name": {"From": SENDER, "To": "info@example.com", "Subject": "Frage"},
    "upper_sender": {"From": f"MAX <{SENDER.upper()}>", "To": "INFO@EXAMPLE.COM", "Subject": "x"},
    "no_from": {"From": None, "To": "info@example.com", "Subject": "Ohne Absender"},
    "empty_from": {"From": "", "To": "info@example.com", "Subject": "Leerer Absender"},
    "encoded_words": {
        "From": f"=?utf-8?q?M=C3=BCller=2C_J=C3=BCrgen?= <{SENDER}>",
        "To": "=?utf-8?q?Hausverwaltung?= <info@example.com>",
        "Subject": "=?utf-8?q?W=C3=A4rmez=C3=A4hler?=",
    },
    "reply_to": {
        "From": f"Portal <noreply-{RUN}@example.com>",
        "Reply-To": f"Echte Person <{SENDER}>",
        "To": "info@example.com",
        "Cc": f"kollege-{RUN}@example.com, info@example.com",
        "Subject": "Mit Reply-To",
    },
    "group_syntax": {
        "From": SENDER,
        "Reply-To": "undisclosed-recipients:;",
        "To": "undisclosed-recipients:;",
        "Subject": "Gruppe",
    },
    "no_to": {"From": SENDER, "To": None, "Subject": "Ohne Empfänger"},
    "no_subject": {"From": SENDER, "To": "info@example.com", "Subject": None},
    "re_prefix": {"From": SENDER, "To": "info@example.com", "Subject": "Re: AW: Heizung"},
    "long_subject": {"From": SENDER, "To": "info@example.com", "Subject": "Heizung " * 140},
    "no_message_id": {"From": SENDER, "To": "info@example.com", "Subject": "Ohne ID"},
}


def test_reply_draft_never_500_for_parsed_mail_shapes(client: TestClient, world: World) -> None:
    failures = _Failures()
    admin = _totp(client, world, "rdsadmin")
    std = bearer(login(client, world, "rdsstd"))
    box = _box(client, admin, f"info-{RUN}@example.com")
    for tag, variant in HEADER_VARIANTS.items():
        for html in (False, True):
            headers = dict(variant)
            if tag != "no_message_id":
                headers["Message-ID"] = f"<{tag}-{html}-{RUN}@x>"
            body = "<p>Nur <b>HTML</b></p>" if html else "Bitte um Rückmeldung."
            msg = _ingest(client, admin, _raw(headers, body, html=html), box["id"])
            what = f"{tag} html={html}"
            _reply_everywhere(client, admin, msg["id"], what, failures)
            _reply_everywhere(client, std, msg["id"], f"{what} std", failures)
            failures.check(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), what)
            _reply_everywhere(client, admin, msg["id"], f"{what} ticket", failures)
    assert not failures, failures


STORED_VARIANTS: dict[str, str] = {
    "null_array_entries": "UPDATE message SET "
    "to_addresses = ARRAY[NULL, '', 'A@B.DE']::varchar[], "
    "cc_addresses = ARRAY[NULL]::varchar[] WHERE id = :id",
    "null_from": "UPDATE message SET from_address = NULL, reply_to = NULL WHERE id = :id",
    "empty_from": "UPDATE message SET from_address = '', reply_to = '' WHERE id = :id",
    "reply_to_upper": "UPDATE message SET reply_to = 'ANTWORT@EXAMPLE.COM' WHERE id = :id",
    "no_thread": "UPDATE message SET thread_id = NULL, header_message_id = NULL, "
    "references_header = NULL WHERE id = :id",
    "body_none": "UPDATE message SET body = NULL, body_html = '<p>x</p>' WHERE id = :id",
    "subject_998": "UPDATE message SET subject = repeat('Ü', 998) WHERE id = :id",
    "references_huge": "UPDATE message SET references_header = repeat('<a@b> ', 5000) "
    "WHERE id = :id",
    "empty_json": "UPDATE message SET classification = '{}'::jsonb, suggestion = '{}'::jsonb "
    "WHERE id = :id",
}


def test_reply_draft_never_500_for_stored_data_shapes(
    client: TestClient, world: World, database: Database
) -> None:
    failures = _Failures()
    admin = _totp(client, world, "rdsadmin")
    std = bearer(login(client, world, "rdsstd"))
    box = _box(client, admin, f"team-{RUN}@example.com", collective=True)
    for tag, statement in STORED_VARIANTS.items():
        headers: dict[str, str | None] = {
            "From": f"Max <{SENDER}>",
            "To": f"team-{RUN}@example.com",
            "Subject": f"Speicher {tag}",
            "Message-ID": f"<st-{tag}-{RUN}@x>",
        }
        msg = _ingest(client, admin, _raw(headers), box["id"])
        _sql(database, world, statement, id=msg["id"])
        _reply_everywhere(client, admin, msg["id"], tag, failures)
        _reply_everywhere(client, std, msg["id"], f"{tag} std", failures)
        failures.check(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), tag)
        _reply_everywhere(client, admin, msg["id"], f"{tag} ticket", failures)
    assert not failures, failures

    # NULL entries: To is the sender, Cc keeps only the real address.
    headers = {
        "From": SENDER,
        "To": f"team-{RUN}@example.com",
        "Subject": "Null",
        "Message-ID": f"<st-null-check-{RUN}@x>",
    }
    msg = _ingest(client, admin, _raw(headers), box["id"])
    _sql(database, world, STORED_VARIANTS["null_array_entries"], id=msg["id"])
    draft = _ok(client.post(f"{M}/messages/{msg['id']}/reply-draft", json={}, headers=admin), 201)
    assert draft["to_addresses"] == [SENDER]
    assert draft["cc_addresses"] == ["A@B.DE"]


def _contact(client: TestClient, h: dict[str, str], email: str, **fields: Any) -> str:
    body = {"emails": [{"email": email, "is_primary": True}], **fields}
    return str(_ok(client.post("/api/v1/contacts", json=body, headers=h), 201)["id"])


def test_reply_draft_never_500_for_case_context(
    client: TestClient, world: World, database: Database
) -> None:
    failures = _Failures()
    admin = _totp(client, world, "rdsadmin")
    std = bearer(login(client, world, "rdsstd"))
    box = _box(client, admin, f"ctx-{RUN}@example.com")
    team = _box(client, admin, f"ctx-team-{RUN}@example.com", collective=True)
    contacts = {
        "herr": {"kind": "person", "salutation": "Herr", "first_name": "Max", "last_name": "M"},
        "frau": {"kind": "person", "salutation": "Frau", "last_name": "Muster"},
        "divers": {"kind": "person", "salutation": "Divers", "last_name": "Muster"},
        "no_salutation": {"kind": "person", "first_name": "Max"},
        "company": {"kind": "company", "company_name": f"Firma {RUN}"},
    }
    for tag, fields in contacts.items():
        sender = f"{tag}-{RUN}@example.com"
        _contact(client, admin, sender, **fields)
        headers: dict[str, str | None] = {
            "From": f"{tag} <{sender.upper()}>",
            "To": f"ctx-{RUN}@example.com",
            "Cc": f"ctx-team-{RUN}@example.com",
            "Subject": f"Kontakt {tag}",
            "Message-ID": f"<ctx-{tag}-{RUN}@x>",
        }
        # The same mail in the personal and the collective mailbox (duplicate copy).
        msg = _ingest(client, admin, _raw(headers), box["id"])
        copy = _ingest(client, admin, _raw(headers), team["id"])
        for row in (msg, copy):
            _reply_everywhere(client, admin, row["id"], f"contact {tag}", failures)
        failures.check(client.post(f"{M}/messages/{msg['id']}/ticket", headers=admin), tag)
        for row in (msg, copy):
            _reply_everywhere(client, admin, row["id"], f"contact {tag} ticket", failures)
            _reply_everywhere(client, std, row["id"], f"contact {tag} ticket std", failures)

    headers = {
        "From": SENDER,
        "To": f"ctx-{RUN}@example.com",
        "Subject": "Kontext",
        "Message-ID": f"<ctx-misc-{RUN}@x>",
    }
    msg = _ingest(client, admin, _raw(headers), box["id"])
    # An open draft of another user comes first.
    _reply_everywhere(client, std, msg["id"], "other user's draft first", failures)
    _reply_everywhere(client, admin, msg["id"], "own after other user's draft", failures)
    # No position or extension, empty company data, branding and template.
    _sql(
        database,
        world,
        "UPDATE membership SET position = NULL, phone = NULL WHERE user_id = :u",
        u=str(world.users["rdsadmin"]),
    )
    _sql(
        database,
        world,
        "UPDATE tenant_settings SET company = '{}'::jsonb, branding = '{}'::jsonb, "
        "signature_template = '{}'::jsonb WHERE tenant_id = :t",
        t=str(world.tenant_a),
    )
    _reply_everywhere(client, admin, msg["id"], "empty settings", failures)
    # Disconnected and removed mailbox, then a message without mailbox.
    _sql(
        database,
        world,
        "UPDATE mailbox SET enabled = false, secret = NULL, deleted_at = now() WHERE id = :id",
        id=box["id"],
    )
    _reply_everywhere(client, admin, msg["id"], "removed mailbox", failures)
    _reply_everywhere(client, std, msg["id"], "removed mailbox std", failures)
    _sql(database, world, "UPDATE message SET mailbox_id = NULL WHERE id = :id", id=msg["id"])
    _reply_everywhere(client, admin, msg["id"], "no mailbox", failures)
    assert not failures, failures

    # A draft whose original was deleted stays editable; answering a draft is a 409.
    headers["Message-ID"] = f"<ctx-deleted-{RUN}@x>"
    orphan = _ingest(client, admin, _raw(headers), team["id"])
    draft = _ok(client.post(f"{M}/messages/{orphan['id']}/reply-draft", headers=admin), 201)
    _sql(database, world, "DELETE FROM message WHERE id = :id", id=orphan["id"])
    assert client.post(f"{M}/messages/{orphan['id']}/reply-draft", headers=admin).status_code == 404
    _ok(client.patch(f"{M}/messages/{draft['id']}/draft", json={"body": "x"}, headers=admin))
    assert client.post(f"{M}/messages/{draft['id']}/reply-draft", headers=admin).status_code == 409
