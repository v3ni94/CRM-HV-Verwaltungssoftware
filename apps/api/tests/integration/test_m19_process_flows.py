"""Regel M19-11 Prozessflows: Katalog einspielen (idempotent), Vorlage mit Flowfeldern
bearbeiten (Validierung, doppelte Vorgangsart), Flow auf ein Ticket anwenden (idempotent,
Checkliste einmalig, Fristen nur als Vorschlag), Vorgangsart aus einer Mail übernehmen
(Ticket entsteht mit Kontakt und Objekt), Berechtigungen (403) und Mandantentrennung."""

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
T = "/api/v1/tickets"
M = "/api/v1/mail"


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _eml(sender: str, subject: str, msg_id: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Tue, 29 Sep 2026 09:00:00 +0200"
    msg.set_content(body)
    return bytes(msg)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pfl-{RUN}", name=f"Flows {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pfl2-{RUN}", name=f"Flows2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("pfadmin", "tenant_admin", a),
            ("pfcare", "caretaker", a),
            ("pfreader", "read_only", a),
            ("pfotherb", "tenant_admin", b),
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


def test_seed_catalogue_idempotent_and_permissions(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "pfadmin"))
    care = bearer(login(client, world, "pfcare"))

    catalogue = _ok(client.get(f"{T}/process-catalogue", headers=care))
    assert [p["code"] for p in catalogue["processes"]][:2] == ["kuendigung", "vermietung"]
    assert len(catalogue["processes"]) == 12
    assert "contract" in catalogue["link_kinds"]

    assert client.post(f"{T}/process-catalogue/seed", headers=care).status_code == 403
    first = _ok(client.post(f"{T}/process-catalogue/seed", headers=admin))
    assert first["created"] == 12
    assert first["kept"] == 0
    second = _ok(client.post(f"{T}/process-catalogue/seed", headers=admin))
    assert second == {"created": 0, "updated": 0, "kept": 12}

    templates = _ok(client.get(f"{T}/templates", headers=admin))
    by_code = {t["process_code"]: t for t in templates if t.get("process_code")}
    assert set(by_code) == {p["code"] for p in catalogue["processes"]}
    kuendigung = by_code["kuendigung"]
    assert kuendigung["process_label"] == "Kündigung"
    assert kuendigung["responsible_role"] == "standard"
    assert kuendigung["deadline_type_codes"] == ["contract_termination", "contract_end", "move_out"]
    assert kuendigung["required_links"] == ["contact", "unit", "property", "contract"]
    assert len(kuendigung["checklist"]) == 7

    # Vorlage bleibt bearbeitbar; unbekannter Fristtyp und doppelte Vorgangsart werden abgewiesen.
    patched = _ok(
        client.patch(
            f"{T}/templates/{kuendigung['id']}",
            json={"document_kinds": ["Kündigungsschreiben"], "deadline_type_codes": ["move_out"]},
            headers=admin,
        )
    )
    assert patched["document_kinds"] == ["Kündigungsschreiben"]
    assert (
        client.patch(
            f"{T}/templates/{kuendigung['id']}",
            json={"deadline_type_codes": ["kuendigungsfrist_14_tage"]},
            headers=admin,
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{T}/templates/{by_code['kaution']['id']}",
            json={"process_code": "kuendigung"},
            headers=admin,
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{T}/templates",
            json={"category": f"x-{RUN}", "title": "X", "process_code": "kaution"},
            headers=admin,
        ).status_code
        == 409
    )
    # Ein erneutes Einspielen überschreibt die Bearbeitung nicht.
    _ok(client.post(f"{T}/process-catalogue/seed", headers=admin))
    reloaded = _ok(client.get(f"{T}/templates/{kuendigung['id']}", headers=admin))
    assert reloaded["deadline_type_codes"] == ["move_out"]

    # Mandant B sieht nichts davon und kann ohne Einspielen keinen Flow anwenden.
    other = bearer(login(client, world, "pfotherb"))
    assert _ok(client.get(f"{T}/templates", headers=other)) == []
    ticket_b = _ok(client.post(T, json={"title": "B"}, headers=other), 201)
    assert (
        client.post(
            f"{T}/{ticket_b['id']}/apply-process", json={"process_code": "kaution"}, headers=other
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{T}/{ticket_b['id']}/apply-process", json={"process_code": "kaution"}, headers=admin
        ).status_code
        == 404
    )


def test_apply_flow_to_ticket_idempotent(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "pfadmin"))
    reader = bearer(login(client, world, "pfreader"))
    _ok(client.post(f"{T}/process-catalogue/seed", headers=admin))
    ticket = _ok(client.post(T, json={"title": f"Kaution {RUN}"}, headers=admin), 201)
    assert ticket["process_code"] is None

    assert (
        client.post(
            f"{T}/{ticket['id']}/apply-process", json={"process_code": "kaution"}, headers=reader
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{T}/{ticket['id']}/apply-process", json={"process_code": "unbekannt"}, headers=admin
        ).status_code
        == 422
    )
    applied = _ok(
        client.post(
            f"{T}/{ticket['id']}/apply-process", json={"process_code": "kaution"}, headers=admin
        )
    )
    assert applied["applied"] is True
    assert applied["process_code"] == "kaution"
    assert applied["process_label"] == "Kaution"
    assert applied["category"] == "kaution"
    assert len(applied["checklist"]) == 6
    flow = applied["flow"]
    assert flow["responsible_role"] == "accountant_no_banking"
    assert flow["links"] == {"contract": False, "contact": False, "unit": False}
    assert flow["deadline_proposals"] == []
    assert flow["document_kinds"] == ["Kautionsnachweis", "Kautionsabrechnung"]
    assert applied["status"] == "new"

    # Checklistenpunkt abhaken, dann erneut anwenden: nichts verdoppelt, Haken bleibt.
    key = applied["checklist"][0]["key"]
    _ok(client.patch(f"{T}/{ticket['id']}/checklist/{key}", json={"done": True}, headers=admin))
    again = _ok(
        client.post(
            f"{T}/{ticket['id']}/apply-process", json={"process_code": "kaution"}, headers=admin
        )
    )
    assert again["applied"] is False
    assert len(again["checklist"]) == 6
    assert again["checklist"][0]["done"] is True
    detail = _ok(client.get(f"{T}/{ticket['id']}", headers=admin))
    assert [e for e in detail["events"] if e["kind"] == "flow_applied"].__len__() == 1

    # Filter nach Vorgangsart in der Liste.
    listed = _ok(client.get(f"{T}?process_code=kaution", headers=admin))
    assert ticket["id"] in {t["id"] for t in listed}
    assert ticket["id"] not in {
        t["id"] for t in _ok(client.get(f"{T}?process_code=gericht", headers=admin))
    }

    # Mandant B erreicht das Ticket nicht.
    other = bearer(login(client, world, "pfotherb"))
    assert (
        client.post(
            f"{T}/{ticket['id']}/apply-process", json={"process_code": "kaution"}, headers=other
        ).status_code
        == 404
    )


def test_apply_process_from_mail_creates_ticket_with_links(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "pfadmin"))
    reader = bearer(login(client, world, "pfreader"))
    _ok(client.post(f"{T}/process-catalogue/seed", headers=admin))
    box = _ok(
        client.post(
            f"{M}/mailboxes",
            json={"address": f"info-pf{RUN}@example.com", "kind": "gmail", "secret": "pf"},
            headers=admin,
        ),
        201,
    )
    _ok(client.patch(f"{M}/mailboxes/{box['id']}", json={"enabled": True}, headers=admin))
    sender = f"erika-pf{RUN}@example.com"
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Erika",
                "last_name": "Muster",
                "emails": [{"email": sender}],
            },
            headers=admin,
        ),
        201,
    )
    raw = _eml(
        sender,
        f"Kündigung Wohnung {RUN}",
        f"<pf1-{RUN}@x>",
        "Hiermit kündige ich mein Mietverhältnis zum 31.03.2027.",
    )
    eml = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("k.eml", raw, "message/rfc822")},
            headers=admin,
        ),
        201,
    )["id"]
    message = _ok(
        client.post(
            f"{M}/ingest",
            json={"document_id": eml, "mailbox_id": box["id"], "auto_ticket": False},
            headers=admin,
        ),
        201,
    )
    process = message["classification"]["process"]
    assert process["process_code"] == "kuendigung"
    assert process["confidence"] >= 0.75
    assert message["ticket_id"] is None

    assert (
        client.post(
            f"{M}/messages/{message['id']}/apply-process", json={}, headers=reader
        ).status_code
        == 403
    )
    result = _ok(client.post(f"{M}/messages/{message['id']}/apply-process", json={}, headers=admin))
    assert result["process_code"] == "kuendigung"
    assert result["applied"] is True
    ticket = _ok(client.get(f"{T}/{result['ticket_id']}", headers=admin))
    assert ticket["contact_id"] == contact["id"]
    assert ticket["process_label"] == "Kündigung"
    assert ticket["flow"]["links"]["contact"] is True
    assert ticket["flow"]["links"]["contract"] is False
    # Fristtypen der Mandantenvorlage (in diesem Modul gegebenenfalls schon bearbeitet).
    template = _ok(client.get(f"{T}/templates/{ticket['template_id']}", headers=admin))
    assert template["process_code"] == "kuendigung"
    assert [d["type"] for d in ticket["flow"]["deadline_proposals"]] == template[
        "deadline_type_codes"
    ]
    assert ticket["flow"]["deadline_proposals"]
    assert all(d["due_on"] is None for d in ticket["flow"]["deadline_proposals"])
    assert ticket["status"] == "new"

    repeat = _ok(client.post(f"{M}/messages/{message['id']}/apply-process", json={}, headers=admin))
    assert repeat["ticket_id"] == result["ticket_id"]
    assert repeat["applied"] is False
    assert (
        client.post(
            f"{M}/messages/{message['id']}/apply-process",
            json={"process_code": "unbekannt"},
            headers=admin,
        ).status_code
        == 422
    )
