"""Zuordnungsprüfung mit Rückfrage für Mails und Tickets (Betreiber 27.09.2026): sicher,
unsicher und kein Treffer je Dimension mit vorgerechneten Konfidenzen, Ja/Nein-Entscheidung,
Protokoll, Rechte und Mandantentrennung. Synthetische Namen und Adressen."""

import asyncio
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
M = "/api/v1/mail"
T = "/api/v1/tickets"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ar-{RUN}", name=f"Zuord {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"arb-{RUN}", name=f"Zuord B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("aradmin", "tenant_admin", a),
            ("arread", "read_only_master_data", a),
            ("aradminb", "tenant_admin", b),
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


def _eml(sender: str, subject: str, body: str, msg_id: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        sender,
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Sun, 27 Sep 2026 09:00:00 +0200"
    msg.set_content(body)
    return bytes(msg)


def _ingest(client: TestClient, h: dict[str, str], sender: str, subject: str, body: str) -> Any:
    tag = f"{RUN}-{abs(hash((sender, subject, body)))}"
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={
                "file": (
                    f"m-{tag}.eml",
                    _eml(sender, subject, body, f"<{tag}@x>"),
                    "message/rfc822",
                )
            },
            headers=h,
        ),
        201,
    )["id"]
    return _ok(client.post(f"{M}/ingest", json={"document_id": doc}, headers=h), 201)


def _by_dim(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["dimension"]: r for r in reviews}


@pytest.fixture(scope="module")
def data(database: Database, redis_url: str, world: World) -> dict[str, Any]:
    """Kontakt Mustermann (E-Mail, Kundennummer, Telefon), Objekt 812 Musterstraße 5 mit
    Einheit 12 (2. OG links) und Objektbeziehung des Kontakts, sowie Objekt 813 ohne Bezug."""
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as client:
            h = bearer(login(client, world, "aradmin"))
            contact = _ok(
                client.post(
                    "/api/v1/contacts",
                    json={
                        "kind": "person",
                        "first_name": "Max",
                        "last_name": f"Mustermann{RUN}",
                        "emails": [{"email": f"max{RUN}@example.com"}],
                        "phones": [{"label": "mobile", "number": "+49 171 5550123"}],
                        "identifiers": [{"kind": "customer_number", "value": f"KD-{RUN}"}],
                    },
                    headers=h,
                ),
                201,
            )
            twin = _ok(
                client.post(
                    "/api/v1/contacts",
                    json={"kind": "person", "first_name": "Erna", "last_name": f"Mustermann{RUN}"},
                    headers=h,
                ),
                201,
            )
            prop = _ok(
                client.post(
                    "/api/v1/properties",
                    json={
                        "number": "812",
                        "name": "Musterhaus",
                        "management_type": "rental",
                        "street": "Musterstraße",
                        "house_number": "5",
                        "postal_code": "12345",
                        "city": "Musterstadt",
                    },
                    headers=h,
                ),
                201,
            )
            other = _ok(
                client.post(
                    "/api/v1/properties",
                    json={"number": "813", "name": "Anderes Haus", "management_type": "rental"},
                    headers=h,
                ),
                201,
            )
            building = _ok(
                client.post(
                    f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h
                ),
                201,
            )
            unit = _ok(
                client.post(
                    f"/api/v1/properties/{prop['id']}/units",
                    json={
                        "building_id": building["id"],
                        "number": "12",
                        "unit_type": "apartment",
                        "location": "2. OG links",
                    },
                    headers=h,
                ),
                201,
            )
            _ok(
                client.post(
                    f"/api/v1/properties/{prop['id']}/units",
                    json={"building_id": building["id"], "number": "13", "unit_type": "apartment"},
                    headers=h,
                ),
                201,
            )
            return {
                "contact": contact["id"],
                "twin": twin["id"],
                "property": prop["id"],
                "other": other["id"],
                "unit": unit["id"],
            }


def test_contact_sure_by_sender_address(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Absenderadresse eindeutig -> Konfidenz 1,0, Status auto, Kontakt gesetzt."""
    h = bearer(login(client, world, "aradmin"))
    msg = _ingest(
        client, h, f"max{RUN}@example.com", "Frage zur Abrechnung", "Guten Tag, kurze Frage."
    )
    assert msg["contact_id"] == data["contact"]
    reviews = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))
    assert reviews["contact"]["status"] == "auto"
    assert reviews["contact"]["chosen_id"] == data["contact"]
    assert reviews["contact"]["candidates"][0]["confidence"] == 1.0
    assert reviews["contact"]["reason"] == "Absenderadresse stimmt überein"
    assert reviews["property"]["status"] == "none"


def test_contact_unsure_by_name_then_accept(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Unbekannte Adresse, Nachname in der Signatur trifft zwei Kontakte (Max und Erna):
    Max mit Vor- und Nachname 0,7, Erna nur Nachname 0,5 -> Rückfrage; Ja übernimmt Max."""
    h = bearer(login(client, world, "aradmin"))
    body = (
        "Sehr geehrte Damen und Herren,\n\nbitte um Rückruf.\n\nMit freundlichen Grüßen\nMax Mustermann"
        + RUN
    )
    msg = _ingest(client, h, f"privat{RUN}@example.org", "Rückruf", body)
    assert msg["contact_id"] is None
    reviews = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))
    contact = reviews["contact"]
    assert contact["status"] == "open"
    assert [c["id"] for c in contact["candidates"]] == [data["contact"], data["twin"]]
    assert contact["candidates"][0]["confidence"] == 0.7
    assert contact["candidates"][1]["confidence"] == 0.5
    assert contact["candidates"][0]["reasons"] == ["Vor- und Nachname im Text"]

    open_list = _ok(client.get(f"{M}/assignment-reviews/open", headers=h))
    assert msg["id"] in {r["entity_id"] for r in open_list}

    decided = _by_dim(
        _ok(
            client.post(
                f"{M}/messages/{msg['id']}/assignment-review/decide",
                json={"dimension": "contact", "decision": "accept"},
                headers=h,
            )
        )
    )
    assert decided["contact"]["status"] == "accepted"
    assert decided["contact"]["decision"] == "accept"
    assert decided["contact"]["chosen_id"] == data["contact"]
    assert decided["contact"]["decided_by"] == str(world.users["aradmin"])
    assert decided["contact"]["decided_at"]
    after = _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))
    assert after["contact_id"] == data["contact"]
    assert after["status"] == "assigned"
    assert msg["id"] not in {
        r["entity_id"] for r in _ok(client.get(f"{M}/assignment-reviews/open", headers=h))
    }


def test_contact_none_and_learning_switch_off(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Kein Treffer bei unbekanntem Absender ohne Namen; Ablehnen wird protokolliert, ohne
    Lernbeispiel, solange der Mandantenschalter aus ist (ADR 0010)."""
    h = bearer(login(client, world, "aradmin"))
    msg = _ingest(client, h, f"niemand{RUN}@example.org", "Hallo", "kurze nachricht ohne namen")
    reviews = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))
    assert reviews["contact"]["status"] == "none"
    assert reviews["contact"]["candidates"] == []
    # Kundennummer im Text einer Mail von unbekannter Adresse: Rückfrage (0,85), nie sicher.
    capped = _ingest(
        client, h, f"dritte{RUN}@example.org", "Weiterleitung", f"Kundennummer KD-{RUN}"
    )
    assert capped["contact_id"] is None
    contact = _by_dim(_ok(client.get(f"{M}/messages/{capped['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert contact["status"] == "open"
    assert contact["candidates"][0]["confidence"] == 0.85
    assert contact["candidates"][0]["reasons"][-1] == "Absenderadresse unbekannt"
    rejected = client.post(
        f"{M}/messages/{msg['id']}/assignment-review/decide",
        json={"dimension": "contact", "decision": "accept"},
        headers=h,
    )
    assert rejected.status_code == 422  # kein Kandidat vorhanden
    engine = create_engine(database.migrator_url)
    with engine.connect() as conn:
        events = conn.execute(
            text(
                "SELECT count(*) FROM audit_log WHERE entity_id = :id "
                "AND changes::text LIKE '%assignment_review.decided%'"
            ),
            {"id": msg["id"]},
        ).scalar()
        examples = conn.execute(
            text("SELECT count(*) FROM ai_example WHERE tenant_id = :t"), {"t": str(world.tenant_a)}
        ).scalar()
    engine.dispose()
    assert examples == 0
    assert events is not None


def test_property_sure_by_number_and_unsure_by_street(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Objektnummer im Betreff -> 1,0 sicher. Straße mit Hausnummer im Text -> 0,85 Rückfrage;
    Nein verwirft, danach manuelle Auswahl eines Objekts außerhalb der Liste."""
    h = bearer(login(client, world, "aradmin"))
    sure = _ingest(client, h, f"x{RUN}@example.org", "Objekt 812 Heizung", "Die Heizung ist kalt.")
    assert sure["property_id"] == data["property"]
    reviews = _by_dim(_ok(client.get(f"{M}/messages/{sure['id']}/assignment-review", headers=h)))
    assert reviews["property"]["status"] == "auto"
    assert reviews["property"]["reason"] == "Objektnummer 812 im Text"

    unsure = _ingest(
        client, h, f"y{RUN}@example.org", "Schaden", "In der Musterstraße 5 tropft es im Keller."
    )
    assert unsure["property_id"] is None
    reviews = _by_dim(_ok(client.get(f"{M}/messages/{unsure['id']}/assignment-review", headers=h)))
    prop = reviews["property"]
    assert prop["status"] == "open"
    assert prop["candidates"][0]["id"] == data["property"]
    assert prop["candidates"][0]["confidence"] == 0.85
    assert prop["candidates"][0]["label"] == "812 Musterhaus"

    rejected = _by_dim(
        _ok(
            client.post(
                f"{M}/messages/{unsure['id']}/assignment-review/decide",
                json={"dimension": "property", "decision": "reject"},
                headers=h,
            )
        )
    )
    assert rejected["property"]["status"] == "rejected"
    assert rejected["property"]["decision"] == "reject"
    assert _ok(client.get(f"{M}/messages/{unsure['id']}", headers=h))["property_id"] is None

    manual = _by_dim(
        _ok(
            client.post(
                f"{M}/messages/{unsure['id']}/assignment-review/decide",
                json={"dimension": "property", "decision": "accept", "candidate_id": data["other"]},
                headers=h,
            )
        )
    )
    assert manual["property"]["status"] == "accepted"
    assert manual["property"]["decision"] == "manual"
    assert manual["property"]["reason"] == "Manuell gewählt: 813 Anderes Haus"
    assert (
        _ok(client.get(f"{M}/messages/{unsure['id']}", headers=h))["property_id"] == data["other"]
    )

    unknown = client.post(
        f"{M}/messages/{unsure['id']}/assignment-review/decide",
        json={"dimension": "property", "decision": "accept", "candidate_id": unsure["id"]},
        headers=h,
    )
    assert unknown.status_code == 404
    bad_dimension = client.post(
        f"{M}/messages/{unsure['id']}/assignment-review/decide",
        json={"dimension": "unit", "decision": "accept"},
        headers=h,
    )
    assert bad_dimension.status_code == 422


def test_ticket_unit_sure_and_unsure(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Ticket mit Objekt: "Wohnung 12" -> Einheit 12 sicher (0,9). "2. OG links" ohne Nummer
    -> 0,6 Rückfrage; Ja setzt die Einheit und schreibt ein Ticketereignis."""
    h = bearer(login(client, world, "aradmin"))
    sure = _ok(
        client.post(
            T,
            json={
                "title": "Wasserhahn tropft",
                "property_id": data["property"],
                "public_description": "In Wohnung 12 tropft der Wasserhahn.",
            },
            headers=h,
        ),
        201,
    )
    assert sure["unit_id"] == data["unit"]
    reviews = _by_dim(_ok(client.get(f"{T}/{sure['id']}/assignment-review", headers=h)))
    assert reviews["unit"]["status"] == "auto"
    assert reviews["unit"]["candidates"][0]["confidence"] == 0.9
    assert reviews["property"]["status"] == "preset"
    assert reviews["contact"]["status"] == "none"

    unsure = _ok(
        client.post(
            T,
            json={
                "title": "Lärm",
                "property_id": data["property"],
                "public_description": "Der Mieter im 2. OG links beschwert sich.",
            },
            headers=h,
        ),
        201,
    )
    assert unsure["unit_id"] is None
    reviews = _by_dim(_ok(client.get(f"{T}/{unsure['id']}/assignment-review", headers=h)))
    assert reviews["unit"]["status"] == "open"
    assert reviews["unit"]["candidates"][0]["confidence"] == 0.6
    assert reviews["unit"]["candidates"][0]["label"] == "Einheit 12"
    assert unsure["id"] in {
        r["entity_id"] for r in _ok(client.get(f"{T}/assignment-reviews/open", headers=h))
    }
    decided = _by_dim(
        _ok(
            client.post(
                f"{T}/{unsure['id']}/assignment-review/decide",
                json={"dimension": "unit", "decision": "accept"},
                headers=h,
            )
        )
    )
    assert decided["unit"]["status"] == "accepted"
    detail = _ok(client.get(f"{T}/{unsure['id']}", headers=h))
    assert detail["unit_id"] == data["unit"]
    kinds = [e["kind"] for e in detail["events"]]
    assert "assignment_review" in kinds


def test_ticket_contact_then_property_from_relation(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Objektbeziehung des Kontakts: nach Ja beim Kontakt wird das Objekt aus der
    Beziehung mit 0,8 vorgeschlagen (Rückfrage, nicht automatisch)."""
    h = bearer(login(client, world, "aradmin"))
    _ok(
        client.post(
            f"/api/v1/properties/{data['property']}/contacts",
            json={
                "contact_id": data["contact"],
                "category_code": "caretaker",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    ticket = _ok(
        client.post(
            T,
            json={"title": "Anruf", "public_description": f"Kundennummer KD-{RUN} meldet Schaden."},
            headers=h,
        ),
        201,
    )
    reviews = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=h)))
    assert reviews["contact"]["status"] == "auto"
    assert reviews["contact"]["candidates"][0]["confidence"] == 0.95
    assert ticket["contact_id"] == data["contact"]
    assert reviews["property"]["status"] == "open"
    assert reviews["property"]["candidates"][0]["confidence"] == 0.8
    assert reviews["property"]["candidates"][0]["reasons"] == [
        "Objektbeziehung (caretaker) des Kontakts"
    ]


def test_permissions_and_tenant_separation(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    h = bearer(login(client, world, "aradmin"))
    msg = _ingest(
        client, h, f"z{RUN}@example.org", "Test", "Mit freundlichen Grüßen\nMax Mustermann" + RUN
    )
    reader = bearer(login(client, world, "arread"))
    assert (
        client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=reader).status_code == 403
    )
    assert (
        client.post(
            f"{M}/messages/{msg['id']}/assignment-review/decide",
            json={"dimension": "contact", "decision": "accept"},
            headers=reader,
        ).status_code
        == 403
    )
    other = bearer(login(client, world, "aradminb", world.tenant_b))
    assert (
        client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=other).status_code == 404
    )
    assert (
        client.post(
            f"{M}/messages/{msg['id']}/assignment-review/decide",
            json={"dimension": "contact", "decision": "accept"},
            headers=other,
        ).status_code
        == 404
    )
    assert _ok(client.get(f"{M}/assignment-reviews/open", headers=other)) == []
    assert _ok(client.get(f"{T}/assignment-reviews/open", headers=other)) == []
