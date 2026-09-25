"""Automatische Ticket-Zuweisung aus Mails, Themen/Kompetenzen, Rechnungs-Weiterleitung und
SLA-Vorschlagswerte (operator 25.09.2026, docs/integrations/mail-optimierung.md). Synthetische
Namen und Adressen, kein Bezug zu echten Personen."""

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

pytestmark = pytest.mark.integration
M = "/api/v1/mail"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"az-{RUN}", name=f"Zuweisung {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("azadmin", "azina", "azsven"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _eml(sender: str, to: str, subject: str, body: str, msg_id: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = sender, to, subject, msg_id
    msg["Date"] = "Fri, 25 Sep 2026 09:00:00 +0200"
    msg.set_content(body)
    return bytes(msg)


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes) -> str:
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "message/rfc822")}, headers=h),
            201,
        )["id"]
    )


def _member_ids(client: TestClient, h: dict[str, str]) -> dict[str, str]:
    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    return {m["email"].split("@")[0].split("+")[-1]: m["membership_id"] for m in members}


def test_competence_catalogue_and_member_competences(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "azadmin"))
    catalogue = _ok(client.get("/api/v1/tenant/competence-catalogue", headers=h))
    codes = {c["code"] for c in catalogue}
    assert "buchhaltung" in codes
    assert "sonstiges" in codes

    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    ina = next(m for m in members if "azina" in m["email"])
    assert ina["competences"] == []

    client.put(
        f"/api/v1/tenant/members/{ina['membership_id']}/competences",
        json={"competence_codes": ["buchhaltung", "mahnwesen"]},
        headers=h,
    )
    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    ina = next(m for m in members if "azina" in m["email"])
    assert sorted(ina["competences"]) == ["buchhaltung", "mahnwesen"]

    bad = client.put(
        f"/api/v1/tenant/members/{ina['membership_id']}/competences",
        json={"competence_codes": ["nicht_im_katalog"]},
        headers=h,
    )
    assert bad.status_code == 422


def test_mailbox_address_assignment_a(client: TestClient, world: World) -> None:
    """Regel (a): das Postfach ist genau einem Mitglied zugeordnet -> primärer Zuweiser
    mit Grund "Anschrift"."""
    h = bearer(login(client, world, "azadmin"))
    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    sven = next(m for m in members if "azsven" in m["email"])

    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"sven-{RUN}@example.com", "secret": "geheim"},
            headers=h,
        ),
        201,
    )
    client.put(
        f"{M}/mailboxes/{box['id']}/users",
        json={"user_ids": [sven["user_id"]]},
        headers=h,
    )

    raw = _eml(
        f"Anfragender <anfrage-a{RUN}@example.com>",
        f"sven-{RUN}@example.com",
        "Allgemeine Frage",
        "Ein Text ohne besonderen Themenbezug und ohne Namen in der Signatur.",
        f"<a1-{RUN}@example.test>",
    )
    doc = _upload(client, h, "a1.eml", raw)
    msg = _ok(
        client.post(
            f"{M}/ingest",
            json={"document_id": doc, "mailbox_id": box["id"], "auto_ticket": True},
            headers=h,
        ),
        201,
    )
    ticket_id = msg["ticket_id"]
    assert ticket_id is not None
    ticket = _ok(client.get(f"/api/v1/tickets/{ticket_id}", headers=h))
    assert ticket["assignee_user_id"] == sven["user_id"]
    assignees = _ok(client.get(f"/api/v1/tickets/{ticket_id}/assignees", headers=h))
    assert any(a["user_id"] == sven["user_id"] and a["reason"] == "Anschrift" for a in assignees)


def test_signature_and_competence_assignment_b_c(client: TestClient, world: World) -> None:
    """Regel (b): Namensabgleich in der Signatur; Regel (c): jedes Mitglied mit passender
    Kompetenz wird zusätzlich zugewiesen."""
    h = bearer(login(client, world, "azadmin"))
    members = _ok(client.get("/api/v1/tenant/members", headers=h))
    ina = next(m for m in members if "azina" in m["email"])
    client.put(
        f"/api/v1/tenant/members/{ina['membership_id']}/competences",
        json={"competence_codes": ["buchhaltung"]},
        headers=h,
    )

    default_box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"info-bc-{RUN}@example.com", "secret": "geheim"},
            headers=h,
        ),
        201,
    )
    default_box = _ok(
        client.patch(f"{M}/mailboxes/{default_box['id']}", json={"is_default": True}, headers=h)
    )
    raw = _eml(
        f"Mieter <mieter-bc{RUN}@example.com>",
        f"info-bc-{RUN}@example.com",
        "Frage zur Rechnung",
        (
            "Hallo,\n\nbitte die Rechnung und Buchung prüfen.\n\n"
            "Viele Grüße\nIna Brink\nHausverwaltung"
        ),
        f"<bc1-{RUN}@example.test>",
    )
    doc = _upload(client, h, "bc1.eml", raw)
    msg = _ok(
        client.post(
            f"{M}/ingest",
            json={"document_id": doc, "mailbox_id": default_box["id"], "auto_ticket": True},
            headers=h,
        ),
        201,
    )
    ticket_id = msg["ticket_id"]
    assert ticket_id is not None
    ticket = _ok(client.get(f"/api/v1/tickets/{ticket_id}", headers=h))
    assert ticket["topic"] == "buchhaltung"
    assignees = _ok(client.get(f"/api/v1/tickets/{ticket_id}/assignees", headers=h))
    reasons_by_user = {a["user_id"]: a["reason"] for a in assignees}
    assert reasons_by_user.get(ina["user_id"]) in ("Signatur", "Kompetenz Buchhaltung")
    assert "Kompetenz Buchhaltung" in reasons_by_user.values()


def test_ticket_links_visible_via_list_filters(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "azadmin"))
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Lea", "last_name": f"Link{RUN}"},
            headers=h,
        ),
        201,
    )
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Linktest", "contact_id": contact["id"]},
            headers=h,
        ),
        201,
    )
    assert ticket["contact_id"] == contact["id"]
    by_contact = _ok(client.get("/api/v1/tickets", params={"contact_id": contact["id"]}, headers=h))
    assert any(t["id"] == ticket["id"] for t in by_contact)


def test_sla_presets_create_rules_and_business_hours(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "azadmin"))
    rules = _ok(client.post("/api/v1/sla/rules/presets", headers=h), 201)
    by_priority = {r["priority"]: r for r in rules}
    assert by_priority["immediate"]["response_minutes"] == 120
    assert by_priority["immediate"]["resolution_minutes"] == 480
    assert by_priority["normal"]["response_minutes"] == 24 * 60
    calendar = _ok(client.get("/api/v1/sla/calendar", headers=h))
    assert calendar["closes_at"] == "17:00"
    # Ein zweiter Aufruf ändert nichts an bereits vorhandenen Regeln.
    again = _ok(client.post("/api/v1/sla/rules/presets", headers=h), 201)
    assert {r["id"] for r in again} == {r["id"] for r in rules}


def test_invoice_forwarding_settings_and_classification(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "azadmin"))
    put = _ok(
        client.put(
            f"{M}/invoice-forwarding",
            json={
                "enabled": True,
                "forward_address": "buchhaltung@inbox.example.com",
                "sender_allowlist": [f"telekom-{RUN}@example.com"],
            },
            headers=h,
        )
    )
    assert put["forward_address"] == "buchhaltung@inbox.example.com"

    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"invoices-{RUN}@example.com", "secret": "geheim"},
            headers=h,
        ),
        201,
    )
    # Absender nicht auf der Positivliste -> nur Vorschlag, kein automatischer Versand.
    raw = _eml(
        f"Unbekannt <unbekannt-{RUN}@example.com>",
        f"invoices-{RUN}@example.com",
        "Ihre Rechnung Nr. 99",
        "Bitte begleichen Sie den Betrag.",
        f"<inv1-{RUN}@example.test>",
    )
    doc = _upload(client, h, "inv1.eml", raw)
    msg = _ok(
        client.post(
            f"{M}/ingest",
            json={"document_id": doc, "mailbox_id": box["id"], "auto_ticket": True},
            headers=h,
        ),
        201,
    )
    assert msg["classification"]["invoice_forward"]["decision"] == "suggest"


def test_mailbox_archive_setting_default_on_and_patchable(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "azadmin"))
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"archive-{RUN}@example.com", "secret": "geheim"},
            headers=h,
        ),
        201,
    )
    assert box["archive_on_ticket_done"] is True
    patched = _ok(
        client.patch(
            f"{M}/mailboxes/{box['id']}", json={"archive_on_ticket_done": False}, headers=h
        )
    )
    assert patched["archive_on_ticket_done"] is False
