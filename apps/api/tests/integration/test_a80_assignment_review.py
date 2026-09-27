"""Zuordnungsprüfung mit Rückfrage für Mails und Tickets (Betreiber 27.09.2026): sicher,
unsicher und kein Treffer je Dimension mit vorgerechneten Konfidenzen, Ja/Nein-Entscheidung,
Protokoll, Rechte und Mandantentrennung. Synthetische Namen und Adressen."""

import asyncio
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
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
            ("arro", "read_only", a),
            ("arstd", "standard", a),
            # Own staff member whose surname appears in salutations and quoted signatures.
            (f"Tina Verwalter{RUN}", "standard", a),
        ]:
            uid = await services.create_user(
                factory,
                email=world.email(name.split()[0].lower()),
                display_name=name,
                password=PASSWORD,
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


def _ingest(
    client: TestClient,
    h: dict[str, str],
    sender: str,
    subject: str,
    body: str,
    **extra: Any,
) -> Any:
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
    return _ok(client.post(f"{M}/ingest", json={"document_id": doc, **extra}, headers=h), 201)


def _by_dim(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["dimension"]: r for r in reviews}


def _sql(database: Database, world: World, statement: str, **params: Any) -> Any:
    """Direct database access as migrator within tenant A (RLS is forced for the owner too);
    simulates records from before 1.36.0."""
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
            )
            result = conn.execute(text(statement), params)
            return result.scalar() if result.returns_rows else None
    finally:
        engine.dispose()


def _open_ids(client: TestClient, h: dict[str, str], base: str = M) -> set[str]:
    rows = _ok(client.get(f"{base}/assignment-reviews/open", params={"limit": 200}, headers=h))
    return {r["entity_id"] for r in rows}


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
                json={
                    "dimension": "contact",
                    "decision": "accept",
                    "candidate_id": data["contact"],
                    "seen_value": None,
                },
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
        json={"dimension": "contact", "decision": "accept", "seen_value": None},
        headers=h,
    )
    assert rejected.status_code == 422  # Ja ohne bestätigten Kandidaten
    assert (
        rejected.json()["detail"] == "Bei Ja ist der bestätigte Kandidat (candidate_id) anzugeben."
    )
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
                json={"dimension": "property", "decision": "reject", "seen_value": None},
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
                json={
                    "dimension": "property",
                    "decision": "accept",
                    "candidate_id": data["other"],
                    "seen_value": None,
                },
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
        json={
            "dimension": "property",
            "decision": "accept",
            "candidate_id": unsure["id"],
            "seen_value": data["other"],
        },
        headers=h,
    )
    assert unknown.status_code == 404
    bad_dimension = client.post(
        f"{M}/messages/{unsure['id']}/assignment-review/decide",
        json={
            "dimension": "unit",
            "decision": "accept",
            "candidate_id": data["unit"],
            "seen_value": None,
        },
        headers=h,
    )
    assert bad_dimension.status_code == 422


def test_ticket_unit_keyword_and_location_are_questions(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Ticket mit Objekt: "Wohnung 12" allein ist nur ein Vorschlag (0,6 Rückfrage, Review
    1.36.0), nie automatisch. "2. OG links" ohne Nummer -> 0,6 Rückfrage; Ja setzt die
    Einheit und schreibt ein Ticketereignis."""
    h = bearer(login(client, world, "aradmin"))
    keyword = _ok(
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
    assert keyword["unit_id"] is None
    reviews = _by_dim(_ok(client.get(f"{T}/{keyword['id']}/assignment-review", headers=h)))
    assert reviews["unit"]["status"] == "open"
    assert reviews["unit"]["candidates"][0]["confidence"] == 0.6
    assert reviews["unit"]["candidates"][0]["reasons"] == ["Einheitennummer 12 im Text"]
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
                json={
                    "dimension": "unit",
                    "decision": "accept",
                    "candidate_id": data["unit"],
                    "seen_value": None,
                },
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
    """Kundennummer im Text eines Tickets ohne Absender: Rückfrage (0,85), nie automatisch
    (Review 1.36.0). Nach Ja beim Kontakt wird das Objekt aus der Objektbeziehung mit 0,8
    vorgeschlagen (Rückfrage, nicht automatisch)."""
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
    assert ticket["contact_id"] is None
    assert reviews["contact"]["status"] == "open"
    assert reviews["contact"]["candidates"][0]["id"] == data["contact"]
    assert reviews["contact"]["candidates"][0]["confidence"] == 0.85
    assert reviews["contact"]["candidates"][0]["reasons"] == [
        f"Kundennummer KD-{RUN} im Text",
        "Keine Absenderadresse",
    ]
    assert reviews["property"]["status"] == "none"
    reviews = _by_dim(
        _ok(
            client.post(
                f"{T}/{ticket['id']}/assignment-review/decide",
                json={
                    "dimension": "contact",
                    "decision": "accept",
                    "candidate_id": data["contact"],
                    "seen_value": None,
                },
                headers=h,
            )
        )
    )
    assert reviews["contact"]["status"] == "accepted"
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
    accept = {
        "dimension": "contact",
        "decision": "accept",
        "candidate_id": data["contact"],
        "seen_value": None,
    }
    assert (
        client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=reader).status_code == 403
    )
    assert (
        client.post(
            f"{M}/messages/{msg['id']}/assignment-review/decide",
            json=accept,
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
            json=accept,
            headers=other,
        ).status_code
        == 404
    )
    assert _ok(client.get(f"{M}/assignment-reviews/open", headers=other)) == []
    assert _ok(client.get(f"{T}/assignment-reviews/open", headers=other)) == []


def test_get_review_is_read_only_and_decide_stores_with_event(
    client: TestClient, world: World, data: dict[str, Any], database: Database, redis_url: str
) -> None:
    """Review 1.36.0 (Befunde 6, 18, 37, 43): Für einen Vorgang ohne Prüfzeilen (Altbestand vor
    1.36.0) rechnet der GET nur und speichert nichts, auch nicht für reine Leser; ein sicherer
    Treffer erscheint als Rückfrage. Zwei gleichzeitige erste Abrufe liefern beide 200. Erst
    die Entscheidung per POST speichert; die automatische Übernahme des Objekts (Objektnummer
    812 im Betreff, 1,0) schreibt das Ereignis assignment_review.auto."""
    h = bearer(login(client, world, "aradmin"))
    msg = _ingest(client, h, f"max{RUN}@example.com", "Objekt 812 Altbestand", "Bitte melden.")
    _sql(database, world, "DELETE FROM assignment_review WHERE entity_id = :id", id=msg["id"])
    _sql(
        database,
        world,
        "UPDATE message SET contact_id = NULL, property_id = NULL, status = 'new' WHERE id = :id",
        id=msg["id"],
    )
    reader = bearer(login(client, world, "arro"))
    url = f"{M}/messages/{msg['id']}/assignment-review"
    reviews = _by_dim(_ok(client.get(url, headers=reader)))
    assert reviews["contact"]["status"] == "open"
    assert reviews["contact"]["candidates"][0]["id"] == data["contact"]
    assert reviews["contact"]["candidates"][0]["confidence"] == 1.0
    assert reviews["property"]["status"] == "open"
    assert reviews["property"]["candidates"][0]["id"] == data["property"]

    settings = _settings(database, redis_url)

    def first_read(_: int) -> int:
        with TestClient(create_app(settings)) as own:
            return own.get(url, headers=reader).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(first_read, range(2))) == [200, 200]
    count = "SELECT count(*) FROM assignment_review WHERE entity_id = :id"
    assert _sql(database, world, count, id=msg["id"]) == 0
    untouched = _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))
    assert (untouched["contact_id"], untouched["property_id"], untouched["status"]) == (
        None,
        None,
        "new",
    )

    auto_events = (
        "SELECT count(*) FROM domain_event WHERE entity_id = :id "
        "AND type = 'assignment_review.auto'"
    )
    logged_before = _sql(database, world, auto_events, id=msg["id"])
    decided = _by_dim(
        _ok(
            client.post(
                f"{url}/decide",
                json={
                    "dimension": "contact",
                    "decision": "accept",
                    "candidate_id": data["contact"],
                    "seen_value": None,
                },
                headers=h,
            )
        )
    )
    assert decided["contact"]["status"] == "accepted"
    assert decided["property"]["status"] == "auto"
    assert decided["property"]["chosen_id"] == data["property"]
    assert _sql(database, world, count, id=msg["id"]) == 2
    after = _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))
    assert (after["contact_id"], after["property_id"]) == (data["contact"], data["property"])
    assert _sql(database, world, auto_events, id=msg["id"]) == logged_before + 1

    # Ticket from before 1.36.0: the GET for a reader writes nothing either.
    ticket = _ok(
        client.post(
            T,
            json={"title": "Altticket", "public_description": f"Kundennummer KD-{RUN}"},
            headers=h,
        ),
        201,
    )
    _sql(database, world, "DELETE FROM assignment_review WHERE entity_id = :id", id=ticket["id"])
    treviews = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=reader)))
    assert treviews["contact"]["status"] == "open"
    assert _sql(database, world, count, id=ticket["id"]) == 0


def test_open_list_respects_mailbox_visibility(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Review 1.36.0 (Befund 16): offene Rückfragen einer Mail aus einem nicht freigegebenen
    Postfach erscheinen nicht in der Sammelliste eines Mitglieds, erst nach der Freigabe."""
    h = bearer(login(client, world, "aradmin"))
    box = _ok(
        client.post(f"{M}/mailboxes", json={"address": f"privat-{RUN}@example.com"}, headers=h), 201
    )
    msg = _ingest(
        client,
        h,
        f"unbekannt{RUN}@example.org",
        "Rückruf privat",
        "Bitte um Rückruf.\n\nMit freundlichen Grüßen\nMax Mustermann" + RUN,
        mailbox_id=box["id"],
    )
    assert msg["contact_id"] is None
    assert msg["id"] in _open_ids(client, h)
    member = bearer(login(client, world, "arstd"))
    assert msg["id"] not in _open_ids(client, member)
    _ok(
        client.put(
            f"{M}/mailboxes/{box['id']}/users",
            json={"user_ids": [str(world.users["arstd"])]},
            headers=h,
        )
    )
    assert msg["id"] in _open_ids(client, member)


def test_ticket_at_intake_contact_sure_only_by_sender(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Review 1.36.0 (Befund 39): Das Ticket aus einer Mail einer fremden Adresse mit
    Kundennummer bekommt keinen Kontakt, nur eine Rückfrage (0,85). Bei bekanntem Absender
    bestätigt die Ticketprüfung den Kontakt über die Absenderadresse. Name und Telefon im Text
    eines Tickets ohne Absender: 0,7 + 0,7 begrenzt auf 0,85, Rückfrage."""
    h = bearer(login(client, world, "aradmin"))
    msg = _ingest(
        client,
        h,
        f"anwalt{RUN}@kanzlei.example",
        "Mandantensache",
        f"Namens unseres Mandanten, Kundennummer KD-{RUN}.",
        auto_ticket=True,
    )
    assert msg["contact_id"] is None
    assert msg["ticket_id"]
    assert _ok(client.get(f"{T}/{msg['ticket_id']}", headers=h))["contact_id"] is None
    contact = _by_dim(_ok(client.get(f"{T}/{msg['ticket_id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert contact["status"] == "open"
    assert contact["candidates"][0]["confidence"] == 0.85
    assert contact["candidates"][0]["reasons"][-1] == "Absenderadresse unbekannt"

    known = _ingest(
        client, h, f"max{RUN}@example.com", "Neue Frage", "Kurze Frage.", auto_ticket=True
    )
    kcontact = _by_dim(_ok(client.get(f"{T}/{known['ticket_id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert kcontact["status"] == "auto"
    assert kcontact["reason"] == "Absenderadresse stimmt überein"

    manual = _ok(
        client.post(
            T,
            json={"title": "Anruf", "public_description": f"Max Mustermann{RUN}\n+49 171 5550123"},
            headers=h,
        ),
        201,
    )
    assert manual["contact_id"] is None
    mcontact = _by_dim(_ok(client.get(f"{T}/{manual['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert mcontact["status"] == "open"
    assert mcontact["candidates"][0]["id"] == data["contact"]
    assert mcontact["candidates"][0]["confidence"] == 0.85


def test_shared_sender_address_is_no_sure_assignment(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Review 1.36.0 (Befund 40): Eine Absenderadresse, die zwei Kontakte tragen (je 0,6), ist
    nie eine sichere Zuordnung; ein beim Eingang vorbelegter Kontakt wird nicht als auto
    geführt."""
    h = bearer(login(client, world, "aradmin"))
    shared = f"familie{RUN}@example.com"
    for first in ("Paul", "Paula"):
        _ok(
            client.post(
                "/api/v1/contacts",
                json={
                    "kind": "person",
                    "first_name": first,
                    "last_name": f"Teiler{RUN}",
                    "emails": [{"email": shared}],
                },
                headers=h,
            ),
            201,
        )
    msg = _ingest(client, h, shared, "Frage", "kurze frage ohne namen")
    contact = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert [c["confidence"] for c in contact["candidates"]] == [0.6, 0.6]
    if msg["contact_id"] is None:
        assert contact["status"] == "open"
    else:
        assert contact["status"] == "preset"
        assert contact["reason"] == "Bereits zugeordnet"


def test_bare_nr_is_no_unit_keyword(client: TestClient, world: World, data: dict[str, Any]) -> None:
    """Review 1.36.0 (Befund 41): "Rechnung Nr. 12" oder "Musterstraße Nr. 5" ergeben keine
    Einheit. "Whg. Nr. 12" im 2. OG links: 0,6 + 0,6, ohne Vertrag begrenzt auf 0,85,
    Rückfrage statt automatischer Zuordnung."""
    h = bearer(login(client, world, "aradmin"))
    invoice = _ok(
        client.post(
            T,
            json={
                "title": "Rechnung Nr. 12",
                "property_id": data["property"],
                "public_description": "Rechnung Nr. 12 für die Musterstraße Nr. 5.",
            },
            headers=h,
        ),
        201,
    )
    assert invoice["unit_id"] is None
    unit = _by_dim(_ok(client.get(f"{T}/{invoice['id']}/assignment-review", headers=h)))["unit"]
    assert unit["status"] == "none"
    assert unit["candidates"] == []

    explicit = _ok(
        client.post(
            T,
            json={
                "title": "Tropfen",
                "property_id": data["property"],
                "public_description": "In der Whg. Nr. 12 im 2. OG links tropft es.",
            },
            headers=h,
        ),
        201,
    )
    assert explicit["unit_id"] is None
    unit = _by_dim(_ok(client.get(f"{T}/{explicit['id']}/assignment-review", headers=h)))["unit"]
    assert unit["status"] == "open"
    assert unit["candidates"][0]["id"] == data["unit"]
    assert unit["candidates"][0]["confidence"] == 0.85


def test_yes_never_overwrites_a_value_set_meanwhile(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0 (Befund 42): Wird der Kontakt auf anderem Weg gesetzt, zeigt die Prüfung
    ihn als superseded, die Sammelliste führt die Rückfrage nicht mehr, und jede Entscheidung
    aus der älteren Ansicht (Ja mit einem Kandidaten, Ja auf den Vorschlag, Nein) endet mit
    409, ohne etwas zu schreiben: der Wert bleibt, die gespeicherte Zeile ist unverändert."""
    h = bearer(login(client, world, "aradmin"))
    msg = _ingest(
        client,
        h,
        f"neu{RUN}@example.org",
        "Rückruf bitte",
        "Bitte um Rückruf.\n\nMit freundlichen Grüßen\nMax Mustermann" + RUN,
    )
    url = f"{M}/messages/{msg['id']}/assignment-review"
    assert _by_dim(_ok(client.get(url, headers=h)))["contact"]["status"] == "open"
    assert msg["id"] in _open_ids(client, h)
    _ok(client.patch(f"{M}/messages/{msg['id']}", json={"contact_id": data["twin"]}, headers=h))
    contact = _by_dim(_ok(client.get(url, headers=h)))["contact"]
    assert contact["status"] == "superseded"
    assert contact["chosen_id"] == data["twin"]
    assert contact["reason"] == "Inzwischen anders zugeordnet"
    assert msg["id"] not in _open_ids(client, h)
    conflict = client.post(
        f"{url}/decide",
        json={
            "dimension": "contact",
            "decision": "accept",
            "candidate_id": data["contact"],
            "seen_value": None,
        },
        headers=h,
    )
    assert conflict.status_code == 409, conflict.text
    assert _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))["contact_id"] == data["twin"]
    stored = (
        "SELECT status || ':' || coalesce(decision, '-') FROM assignment_review "
        "WHERE entity_id = :id AND dimension = 'contact'"
    )
    assert _sql(database, world, stored, id=msg["id"]) == "open:-"
    # The older view (empty field) and the view after reloading (superseded, Erna shown) both
    # end in 409: the question was computed against an empty field.
    for seen in (None, data["twin"]):
        for body in (
            {"dimension": "contact", "decision": "accept", "candidate_id": data["contact"]},
            {"dimension": "contact", "decision": "reject"},
            {"dimension": "contact", "decision": "accept", "candidate_id": data["twin"]},
        ):
            again = client.post(f"{url}/decide", json=body | {"seen_value": seen}, headers=h)
            assert again.status_code == 409, (seen, body, again.text)
    assert _sql(database, world, stored, id=msg["id"]) == "open:-"
    assert _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))["contact_id"] == data["twin"]
    assert _by_dim(_ok(client.get(url, headers=h)))["contact"]["status"] == "superseded"


def test_salutation_and_own_staff_are_no_sender_name(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Review 1.36.0 (Befund 44): Die Anrede nennt das eigene Mitglied "Tina Verwalter"; ein
    gleichnamiger Kontakt wird deshalb nicht vorgeschlagen. Außerhalb der Anredezeile zählt der
    Name weiter: ein Kontakt "Hans Verwalter" mit dem Nachnamen des Mitglieds wird aus der
    Signatur (0,7) und vom Anfang einer Anrufnotiz vorgeschlagen, Tina nur mit dem Nachnamen
    (0,5)."""
    h = bearer(login(client, world, "aradmin"))
    ids = {}
    for first in ("Tina", "Hans"):
        ids[first] = _ok(
            client.post(
                "/api/v1/contacts",
                json={"kind": "person", "first_name": first, "last_name": f"Verwalter{RUN}"},
                headers=h,
            ),
            201,
        )["id"]
    salutation = f"Sehr geehrte Frau Verwalter{RUN},\n\ndie Heizung ist kalt."
    msg = _ingest(client, h, f"fremd{RUN}@example.org", "Heizung", salutation)
    contact = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert (contact["status"], contact["candidates"]) == ("none", [])

    signed = f"{salutation}\n\nMit freundlichen Grüßen\nHans Verwalter{RUN}"
    msg = _ingest(client, h, f"mieter{RUN}@example.org", "Heizung kalt", signed)
    contact = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert contact["status"] == "open"
    assert [(c["id"], c["confidence"]) for c in contact["candidates"]] == [
        (ids["Hans"], 0.7),
        (ids["Tina"], 0.5),
    ]
    assert contact["candidates"][1]["reasons"] == ["Nachname im Text"]

    note = f"Hans Verwalter{RUN} ruft an\n" + "\n".join(f"Punkt {i}" for i in range(8))
    ticket = _ok(
        client.post(T, json={"title": "Anruf", "public_description": note}, headers=h), 201
    )
    contact = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert contact["status"] == "open"
    assert contact["candidates"][0]["id"] == ids["Hans"]
    assert contact["candidates"][0]["confidence"] == 0.7


def test_shared_sender_address_leaves_the_contact_empty_at_intake(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Review 1.36.0 (Befund 40, Eingang): Tragen zwei aktive Kontakte die Absenderadresse,
    wird beim Eingang kein Kontakt vorbelegt; die Prüfung fragt nach ("Handelt es sich um den
    Kontakt XY?"). Objekt und Einheit werden weder an der Mail noch am Ticket aus der
    Objektbeziehung eines beliebig gewählten Kontakts abgeleitet."""
    h = bearer(login(client, world, "aradmin"))
    shared = f"paar{RUN}@example.com"
    ids = []
    for first in ("Jan", "Jana"):
        contact = _ok(
            client.post(
                "/api/v1/contacts",
                json={
                    "kind": "person",
                    "first_name": first,
                    "last_name": f"Paarweise{RUN}",
                    "emails": [{"email": shared}],
                },
                headers=h,
            ),
            201,
        )
        ids.append(contact["id"])
        _ok(
            client.post(
                f"/api/v1/properties/{data['property']}/contacts",
                json={
                    "contact_id": contact["id"],
                    "category_code": "caretaker",
                    "valid_from": "2026-01-01",
                },
                headers=h,
            ),
            201,
        )
    msg = _ingest(client, h, shared, "Anliegen", "bitte um rueckruf", auto_ticket=True)
    assert msg["contact_id"] is None
    assert msg["property_id"] is None
    reviews = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))
    assert reviews["contact"]["status"] == "open"
    assert sorted(c["id"] for c in reviews["contact"]["candidates"]) == sorted(ids)
    assert [c["confidence"] for c in reviews["contact"]["candidates"]] == [0.6, 0.6]
    assert reviews["property"]["status"] == "none"
    assert reviews["property"]["candidates"] == []
    assert msg["id"] in _open_ids(client, h)
    ticket = _ok(client.get(f"{T}/{msg['ticket_id']}", headers=h))
    assert (ticket["contact_id"], ticket["property_id"], ticket["unit_id"]) == (None, None, None)
    treviews = _by_dim(_ok(client.get(f"{T}/{msg['ticket_id']}/assignment-review", headers=h)))
    assert treviews["contact"]["status"] == "open"
    assert treviews["property"]["status"] == "none"
    assert treviews["unit"]["status"] == "none"


def test_deleted_contact_is_never_prefilled_as_sender(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Review 1.36.0 (Befund 40, Eingang): Die Adresse eines weich gelöschten Kontakts belegt
    beim Eingang nichts vor. Trägt danach genau ein aktiver Kontakt die Adresse (Dublette aus
    dem Import bereinigt), ist er der sichere Treffer (1,0, auto)."""
    h = bearer(login(client, world, "aradmin"))
    address = f"dublette{RUN}@example.com"

    def contact(first: str) -> str:
        created = _ok(
            client.post(
                "/api/v1/contacts",
                json={
                    "kind": "person",
                    "first_name": first,
                    "last_name": f"Dublette{RUN}",
                    "emails": [{"email": address}],
                },
                headers=h,
            ),
            201,
        )
        return str(created["id"])

    deleted = contact("Alt")
    assert client.delete(f"/api/v1/contacts/{deleted}", headers=h).status_code == 204
    only_deleted = _ingest(client, h, address, "Frage", "erste frage zur abrechnung")
    assert only_deleted["contact_id"] is None
    assert only_deleted["status"] == "new"
    review = _by_dim(
        _ok(client.get(f"{M}/messages/{only_deleted['id']}/assignment-review", headers=h))
    )["contact"]
    assert (review["status"], review["candidates"]) == ("none", [])

    active = contact("Neu")
    msg = _ingest(client, h, address, "Frage", "zweite frage zur abrechnung")
    assert msg["contact_id"] == active
    review = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert review["status"] == "auto"
    assert review["chosen_id"] == active
    assert [c["confidence"] for c in review["candidates"]] == [1.0]
    assert review["reason"] == "Absenderadresse stimmt überein"


def test_yes_corrects_a_wrong_preset(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0: Eine Zeile merkt sich den Wert, gegen den sie gerechnet wurde. Ein Ja
    korrigiert eine falsche Vorgabe, solange das Feld noch diesen Wert hat: am Ticket mit dem
    Vorschlag (Objektnummer 812 statt vorgegebenem 813), an der Mail nach Nein mit einem manuell
    gesuchten Kontakt. Wird der Wert danach auf anderem Weg geändert, endet ein Ja mit 409, der
    Wert bleibt, die gespeicherte Entscheidung bleibt unverändert, und die Prüfung zeigt sie als
    superseded."""
    h = bearer(login(client, world, "aradmin"))
    ticket = _ok(
        client.post(
            T,
            json={
                "title": "Objekt 812 Heizung",
                "property_id": data["other"],
                "public_description": "Die Heizung ist kalt.",
            },
            headers=h,
        ),
        201,
    )
    turl = f"{T}/{ticket['id']}/assignment-review"
    prop = _by_dim(_ok(client.get(turl, headers=h)))["property"]
    assert (prop["status"], prop["chosen_id"]) == ("preset", data["other"])
    assert prop["candidates"][0]["id"] == data["property"]
    fixed = _by_dim(
        _ok(
            client.post(
                f"{turl}/decide",
                json={
                    "dimension": "property",
                    "decision": "accept",
                    "candidate_id": data["property"],
                    "seen_value": data["other"],
                },
                headers=h,
            )
        )
    )["property"]
    assert (fixed["status"], fixed["decision"]) == ("accepted", "accept")
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["property_id"] == data["property"]

    msg = _ingest(client, h, f"max{RUN}@example.com", "Vorgabe falsch", "Kurze Frage.")
    murl = f"{M}/messages/{msg['id']}/assignment-review"
    assert _by_dim(_ok(client.get(murl, headers=h)))["contact"]["status"] == "auto"
    rejected = _by_dim(
        _ok(
            client.post(
                f"{murl}/decide",
                json={"dimension": "contact", "decision": "reject", "seen_value": data["contact"]},
                headers=h,
            )
        )
    )["contact"]
    assert (rejected["status"], rejected["chosen_id"]) == ("rejected", data["contact"])
    manual = _by_dim(
        _ok(
            client.post(
                f"{murl}/decide",
                json={
                    "dimension": "contact",
                    "decision": "accept",
                    "candidate_id": data["twin"],
                    "seen_value": data["contact"],
                },
                headers=h,
            )
        )
    )["contact"]
    assert (manual["status"], manual["decision"]) == ("accepted", "manual")
    assert _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))["contact_id"] == data["twin"]

    _ok(client.patch(f"{M}/messages/{msg['id']}", json={"contact_id": data["contact"]}, headers=h))
    # Older view (Erna accepted) and the view after reloading (Max shown, the field holds the
    # row's basis again): a Ja is final, both end in 409.
    for seen in (data["twin"], data["contact"]):
        conflict = client.post(
            f"{murl}/decide",
            json={
                "dimension": "contact",
                "decision": "accept",
                "candidate_id": data["twin"],
                "seen_value": seen,
            },
            headers=h,
        )
        assert conflict.status_code == 409, (seen, conflict.text)
    assert _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))["contact_id"] == data["contact"]
    stored = "SELECT status FROM assignment_review WHERE entity_id = :id AND dimension = 'contact'"
    assert _sql(database, world, stored, id=msg["id"]) == "accepted"
    shown = _by_dim(_ok(client.get(murl, headers=h)))["contact"]
    assert (shown["status"], shown["chosen_id"]) == ("superseded", data["contact"])


def test_ticket_change_supersedes_an_open_question(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Review 1.36.0: Setzt eine Ticketänderung den Kontakt, macht die erneute Prüfung die
    offene Rückfrage zu superseded. Ein Ja aus der älteren Ansicht endet mit 409 und
    überschreibt die Änderung nicht."""
    h = bearer(login(client, world, "aradmin"))
    ticket = _ok(
        client.post(
            T, json={"title": "Rückruf", "public_description": f"Kundennummer KD-{RUN}"}, headers=h
        ),
        201,
    )
    url = f"{T}/{ticket['id']}/assignment-review"
    contact = _by_dim(_ok(client.get(url, headers=h)))["contact"]
    assert (contact["status"], contact["candidates"][0]["id"]) == ("open", data["contact"])
    _ok(client.patch(f"{T}/{ticket['id']}", json={"contact_id": data["twin"]}, headers=h))
    contact = _by_dim(_ok(client.get(url, headers=h)))["contact"]
    assert (contact["status"], contact["chosen_id"]) == ("superseded", data["twin"])
    stale = client.post(
        f"{url}/decide",
        json={
            "dimension": "contact",
            "decision": "accept",
            "candidate_id": data["contact"],
            "seen_value": None,
        },
        headers=h,
    )
    assert stale.status_code == 409, stale.text
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["contact_id"] == data["twin"]


def test_preview_rows_have_stable_ids_and_are_decided_like_the_crm(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0: Für einen Vorgang ohne gespeicherte Prüfung liefert der GET bei jedem
    Abruf dieselben Zeilen-IDs, ohne etwas zu speichern. Die CRM-Karte (AssignmentPrompt)
    entscheidet über Dimension und Kandidat, nie über die ID: Nein speichert die Prüfung, die
    Suche mit manueller Auswahl setzt den Kontakt."""
    h = bearer(login(client, world, "aradmin"))
    ticket = _ok(
        client.post(
            T,
            json={"title": "Altvorgang", "public_description": f"Kundennummer KD-{RUN}"},
            headers=h,
        ),
        201,
    )
    _sql(database, world, "DELETE FROM assignment_review WHERE entity_id = :id", id=ticket["id"])
    url = f"{T}/{ticket['id']}/assignment-review"
    first = _ok(client.get(url, headers=h))
    second = _ok(client.get(url, headers=h))
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert len({r["id"] for r in first}) == 3
    count = "SELECT count(*) FROM assignment_review WHERE entity_id = :id"
    assert _sql(database, world, count, id=ticket["id"]) == 0
    assert _by_dim(first)["contact"]["status"] == "open"

    rejected = _by_dim(
        _ok(
            client.post(
                f"{url}/decide",
                json={
                    "dimension": "contact",
                    "decision": "reject",
                    "candidate_id": None,
                    "seen_value": None,
                },
                headers=h,
            )
        )
    )["contact"]
    assert (rejected["status"], rejected["chosen_id"]) == ("rejected", None)
    assert rejected["id"] != _by_dim(first)["contact"]["id"]
    assert _sql(database, world, count, id=ticket["id"]) == 3
    manual = _by_dim(
        _ok(
            client.post(
                f"{url}/decide",
                json={
                    "dimension": "contact",
                    "decision": "accept",
                    "candidate_id": data["twin"],
                    "seen_value": None,
                },
                headers=h,
            )
        )
    )["contact"]
    assert (manual["status"], manual["decision"]) == ("accepted", "manual")
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["contact_id"] == data["twin"]


def test_prefilled_value_labelled_auto_has_an_event(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0: Ein beim Eingang vorbelegter und von den Regeln bestätigter Kontakt
    (eindeutige Absenderadresse) ist auto und hat genau ein Ereignis assignment_review.auto
    (prefilled), das Ticket aus der Mail zusätzlich einen Eintrag im Ticketverlauf; eine
    erneute Prüfung protokolliert nichts doppelt. Eine nur berechnete Vorschau ohne Ereignis
    zeigt denselben Wert als preset."""
    h = bearer(login(client, world, "aradmin"))
    msg = _ingest(client, h, f"max{RUN}@example.com", "Vorbelegt", "Kurze Frage.", auto_ticket=True)
    assert msg["contact_id"] == data["contact"]
    logged = (
        "SELECT count(*) FROM domain_event WHERE entity_id = :id "
        "AND type = 'assignment_review.auto' AND payload->>'dimension' = 'contact' "
        "AND payload->>'prefilled' = 'true'"
    )
    assert _sql(database, world, logged, id=msg["id"]) == 1
    assert _sql(database, world, logged, id=msg["ticket_id"]) == 1
    detail = _ok(client.get(f"{T}/{msg['ticket_id']}", headers=h))
    assert [
        e["data"]["dimension"]
        for e in detail["events"]
        if e["kind"] == "assignment_review" and e["data"].get("decision") == "auto"
    ] == ["contact"]
    tcontact = _by_dim(_ok(client.get(f"{T}/{msg['ticket_id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert tcontact["status"] == "auto"
    _ok(
        client.patch(
            f"{T}/{msg['ticket_id']}", json={"internal_description": "Rückruf erledigt"}, headers=h
        )
    )
    assert _sql(database, world, logged, id=msg["ticket_id"]) == 1

    _sql(database, world, "DELETE FROM assignment_review WHERE entity_id = :id", id=msg["id"])
    contact = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert (contact["status"], contact["chosen_id"]) == ("preset", data["contact"])
    assert contact["reason"] == "Bereits zugeordnet"


def _stored(database: Database, world: World, entity_id: str, dimension: str) -> str:
    """Stored row as "status|decision|chosen_id|basis_id|decided_by" ("-" for NULL)."""
    return str(
        _sql(
            database,
            world,
            "SELECT concat_ws('|', status, coalesce(decision, '-'), coalesce(chosen_id::text, '-'),"
            " coalesce(basis_id::text, '-'), coalesce(decided_by::text, '-')) "
            "FROM assignment_review WHERE entity_id = :id AND dimension = :dim",
            id=entity_id,
            dim=dimension,
        )
    )


def test_second_member_with_a_stale_view_gets_409_and_the_first_decision_stays(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0 (lost update): Zwei Mitglieder sehen dieselbe offene Rückfrage mit den
    Kandidaten Max und Erna Mustermann. A bestätigt Max. B entscheidet danach aus seiner älteren
    Ansicht (leeres Feld) und nach dem Neuladen (Max zugeordnet): Ja auf Erna und Nein enden mit
    409 (Fehlercode MHVP-COMM-0003), der Kontakt bleibt Max und die gespeicherte Entscheidung von
    A bleibt unverändert. Dasselbe Ja noch einmal (Wiederholung durch A, oder B mit Max) ändert
    nichts. Die Zeile führt den Wert, gegen den die Rückfrage gerechnet wurde (leer), getrennt
    von der Entscheidung (Max)."""
    a = bearer(login(client, world, "aradmin"))
    b = bearer(login(client, world, "arstd"))
    msg = _ingest(
        client,
        a,
        f"veraltet{RUN}@example.org",
        "Rückfrage Verlust",
        "Bitte um Rückruf.\n\nMit freundlichen Grüßen\nMax Mustermann" + RUN,
    )
    url = f"{M}/messages/{msg['id']}/assignment-review"
    for viewer in (a, b):
        contact = _by_dim(_ok(client.get(url, headers=viewer)))["contact"]
        assert contact["status"] == "open"
        assert {data["contact"], data["twin"]} <= {c["id"] for c in contact["candidates"]}
    accept_max = {
        "dimension": "contact",
        "decision": "accept",
        "candidate_id": data["contact"],
        "seen_value": None,
    }
    first = _by_dim(_ok(client.post(f"{url}/decide", json=accept_max, headers=a)))["contact"]
    assert (first["status"], first["chosen_id"]) == ("accepted", data["contact"])
    decided = f"accepted|accept|{data['contact']}|-|{world.users['aradmin']}"
    assert _stored(database, world, msg["id"], "contact") == decided

    for seen in (None, data["contact"]):
        for body in (
            {"dimension": "contact", "decision": "accept", "candidate_id": data["twin"]},
            {"dimension": "contact", "decision": "reject"},
        ):
            stale = client.post(f"{url}/decide", json=body | {"seen_value": seen}, headers=b)
            assert stale.status_code == 409, (seen, body, stale.text)
            problem = stale.json()
            assert (problem["code"], problem["title"]) == (
                "MHVP-COMM-0003",
                "Zuordnung inzwischen geändert",
            )
            assert problem["detail"] == (
                "Die Zuordnung wurde inzwischen anders gesetzt. Die Rückfrage ist überholt, "
                "bitte neu laden."
            )
            current = _ok(client.get(f"{M}/messages/{msg['id']}", headers=a))["contact_id"]
            assert current == data["contact"]
            assert _stored(database, world, msg["id"], "contact") == decided

    decided_events = (
        "SELECT count(*) FROM domain_event WHERE entity_id = :id "
        "AND type = 'assignment_review.decided'"
    )
    events = _sql(database, world, decided_events, id=msg["id"])
    for viewer in (a, b):
        again = _by_dim(_ok(client.post(f"{url}/decide", json=accept_max, headers=viewer)))[
            "contact"
        ]
        assert (again["status"], again["chosen_id"]) == ("accepted", data["contact"])
        assert _stored(database, world, msg["id"], "contact") == decided
    assert _sql(database, world, decided_events, id=msg["id"]) == events
    shown = _by_dim(_ok(client.get(url, headers=b)))["contact"]
    assert (shown["status"], shown["chosen_id"]) == ("accepted", data["contact"])


def test_preset_on_a_never_reviewed_record_can_be_corrected_or_rejected(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0: Vorgänge ohne gespeicherte Prüfung (bei der Einführung jede vorhandene
    Mail und jedes Ticket) rechnen gegen den aktuellen Feldwert. Ein Ja korrigiert eine falsche
    Vorgabe ohne 409 (Ticket: Objekt 813 vorgegeben, 812 im Betreff). Ein Nein auf eine Vorgabe
    speichert rejected mit dieser Vorgabe als Grundlage und bleibt rejected, nicht superseded;
    danach korrigiert die manuelle Auswahl den Kontakt."""
    h = bearer(login(client, world, "aradmin"))
    ticket = _ok(
        client.post(
            T,
            json={"title": "Objekt 812 Altbestand", "property_id": data["other"]},
            headers=h,
        ),
        201,
    )
    _sql(database, world, "DELETE FROM assignment_review WHERE entity_id = :id", id=ticket["id"])
    turl = f"{T}/{ticket['id']}/assignment-review"
    prop = _by_dim(_ok(client.get(turl, headers=h)))["property"]
    assert (prop["status"], prop["chosen_id"]) == ("preset", data["other"])
    assert prop["candidates"][0]["id"] == data["property"]
    fixed = _by_dim(
        _ok(
            client.post(
                f"{turl}/decide",
                json={
                    "dimension": "property",
                    "decision": "accept",
                    "candidate_id": data["property"],
                    "seen_value": data["other"],
                },
                headers=h,
            )
        )
    )["property"]
    assert (fixed["status"], fixed["chosen_id"]) == ("accepted", data["property"])
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["property_id"] == data["property"]
    assert _stored(database, world, ticket["id"], "property") == (
        f"accepted|accept|{data['property']}|{data['other']}|{world.users['aradmin']}"
    )

    msg = _ingest(client, h, f"max{RUN}@example.com", "Altbestand Vorgabe", "Kurze Frage.")
    assert msg["contact_id"] == data["contact"]
    _sql(database, world, "DELETE FROM assignment_review WHERE entity_id = :id", id=msg["id"])
    murl = f"{M}/messages/{msg['id']}/assignment-review"
    assert _by_dim(_ok(client.get(murl, headers=h)))["contact"]["status"] == "preset"
    rejected = _by_dim(
        _ok(
            client.post(
                f"{murl}/decide",
                json={"dimension": "contact", "decision": "reject", "seen_value": data["contact"]},
                headers=h,
            )
        )
    )["contact"]
    assert (rejected["status"], rejected["chosen_id"]) == ("rejected", data["contact"])
    shown = _by_dim(_ok(client.get(murl, headers=h)))["contact"]
    assert (shown["status"], shown["chosen_id"]) == ("rejected", data["contact"])
    assert _stored(database, world, msg["id"], "contact") == (
        f"rejected|reject|{data['contact']}|{data['contact']}|{world.users['aradmin']}"
    )
    manual = _by_dim(
        _ok(
            client.post(
                f"{murl}/decide",
                json={
                    "dimension": "contact",
                    "decision": "accept",
                    "candidate_id": data["twin"],
                    "seen_value": data["contact"],
                },
                headers=h,
            )
        )
    )["contact"]
    assert (manual["status"], manual["decision"]) == ("accepted", "manual")
    assert _ok(client.get(f"{M}/messages/{msg['id']}", headers=h))["contact_id"] == data["twin"]


def test_rows_without_a_question_follow_the_current_value(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0: Nur eine offene Rückfrage wird überholt (superseded), wenn das Feld
    inzwischen anders gesetzt ist. Zeilen ohne Rückfrage (none, auto, preset) folgen dem
    aktuellen Wert: nach einer Ticketänderung gespeichert als preset, an der Mail ohne erneute
    Prüfung in der Anzeige als preset."""
    h = bearer(login(client, world, "aradmin"))
    ticket = _ok(client.post(T, json={"title": "Ohne Treffer"}, headers=h), 201)
    assert _stored(database, world, ticket["id"], "contact").startswith("none|")
    _ok(client.patch(f"{T}/{ticket['id']}", json={"contact_id": data["twin"]}, headers=h))
    assert _stored(database, world, ticket["id"], "contact").startswith(
        f"preset|-|{data['twin']}|{data['twin']}|"
    )
    contact = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert (contact["status"], contact["chosen_id"], contact["reason"]) == (
        "preset",
        data["twin"],
        "Bereits zugeordnet",
    )

    msg = _ingest(client, h, f"max{RUN}@example.com", "Folgt", "Kurze Frage.", auto_ticket=True)
    assert _stored(database, world, msg["ticket_id"], "contact").startswith("auto|")
    _ok(client.patch(f"{T}/{msg['ticket_id']}", json={"contact_id": data["twin"]}, headers=h))
    assert _stored(database, world, msg["ticket_id"], "contact").startswith(
        f"preset|-|{data['twin']}|{data['twin']}|"
    )

    plain = _ingest(client, h, f"leer{RUN}@example.org", "Heizung", "Die Heizung ist kalt.")
    murl = f"{M}/messages/{plain['id']}/assignment-review"
    assert _by_dim(_ok(client.get(murl, headers=h)))["contact"]["status"] == "none"
    _ok(client.patch(f"{M}/messages/{plain['id']}", json={"contact_id": data["twin"]}, headers=h))
    contact = _by_dim(_ok(client.get(murl, headers=h)))["contact"]
    assert (contact["status"], contact["chosen_id"]) == ("preset", data["twin"])


def test_quoted_own_signature_names_no_contact(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    """Review 1.36.0: Die Antwort eines unbekannten Absenders zitiert unsere Mail mit der
    Signatur des Mitglieds "Tina Verwalter". Der zitierte Teil liefert keine Namen; ein Kontakt
    mit dem Nachnamen des Mitglieds wird nicht vorgeschlagen, die Absenderin aus ihrer eigenen
    Signatur über dem Zitat schon (Vor- und Nachname 0,7)."""
    h = bearer(login(client, world, "aradmin"))
    ids = {}
    for first, last in (("Paula", f"Quelle{RUN}"), ("Olaf", f"Verwalter{RUN}")):
        ids[first] = _ok(
            client.post(
                "/api/v1/contacts",
                json={"kind": "person", "first_name": first, "last_name": last},
                headers=h,
            ),
            201,
        )["id"]
    body = (
        "Vielen Dank für die schnelle Hilfe.\n\nViele Grüße\n"
        f"Paula Quelle{RUN}\n\n"
        f"Am 26.09.2026 um 10:00 schrieb Tina Verwalter{RUN} <tina{RUN}@example.com>:\n"
        f"> Sehr geehrte Frau Quelle{RUN},\n> der Techniker kommt morgen.\n"
        f"> Mit freundlichen Grüßen\n> Tina Verwalter{RUN}\n> Hausverwaltung Muster"
    )
    msg = _ingest(client, h, f"quelle{RUN}@example.org", "AW: Heizung", body)
    contact = _by_dim(_ok(client.get(f"{M}/messages/{msg['id']}/assignment-review", headers=h)))[
        "contact"
    ]
    assert contact["status"] == "open"
    assert [(c["id"], c["confidence"]) for c in contact["candidates"]] == [(ids["Paula"], 0.7)]
    assert contact["candidates"][0]["reasons"] == ["Vor- und Nachname im Text"]


def test_decision_from_a_stale_preview_never_overwrites_a_manual_change(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0 (Einführung): Eine Mail ohne gespeicherte Prüfung zeigt die Rückfrage nur
    als Vorschau auf ein leeres Feld. A ordnet danach Erna von Hand zu (PATCH). B entscheidet
    aus der Vorschau (gesehener Wert leer): Ja auf Max und Nein enden mit 409 (MHVP-COMM-0003),
    Erna bleibt, keine Prüfzeile und kein Ereignis wird gespeichert. Nach dem Neuladen (Erna
    als Vorgabe gezeigt) korrigiert ein Ja auf Max die Vorgabe."""
    a = bearer(login(client, world, "aradmin"))
    b = bearer(login(client, world, "arstd"))
    msg = _ingest(
        client,
        a,
        f"vorschau{RUN}@example.org",
        "Rückruf Vorschau",
        "Bitte um Rückruf.\n\nMit freundlichen Grüßen\nMax Mustermann" + RUN,
    )
    _sql(database, world, "DELETE FROM assignment_review WHERE entity_id = :id", id=msg["id"])
    url = f"{M}/messages/{msg['id']}/assignment-review"
    preview = _by_dim(_ok(client.get(url, headers=b)))["contact"]
    assert (preview["status"], preview["chosen_id"]) == ("open", None)
    assert preview["candidates"][0]["id"] == data["contact"]
    _ok(client.patch(f"{M}/messages/{msg['id']}", json={"contact_id": data["twin"]}, headers=a))

    for body in (
        {"dimension": "contact", "decision": "accept", "candidate_id": data["contact"]},
        {"dimension": "contact", "decision": "reject"},
    ):
        stale = client.post(f"{url}/decide", json=body | {"seen_value": None}, headers=b)
        assert stale.status_code == 409, (body, stale.text)
        assert stale.json()["code"] == "MHVP-COMM-0003"
        after = _ok(client.get(f"{M}/messages/{msg['id']}", headers=a))["contact_id"]
        assert after == data["twin"]
    count = "SELECT count(*) FROM assignment_review WHERE entity_id = :id"
    assert _sql(database, world, count, id=msg["id"]) == 0
    decided_events = (
        "SELECT count(*) FROM domain_event WHERE entity_id = :id "
        "AND type = 'assignment_review.decided'"
    )
    assert _sql(database, world, decided_events, id=msg["id"]) == 0

    reloaded = _by_dim(_ok(client.get(url, headers=b)))["contact"]
    assert (reloaded["status"], reloaded["chosen_id"]) == ("preset", data["twin"])
    fixed = _by_dim(
        _ok(
            client.post(
                f"{url}/decide",
                json={
                    "dimension": "contact",
                    "decision": "accept",
                    "candidate_id": data["contact"],
                    "seen_value": data["twin"],
                },
                headers=b,
            )
        )
    )["contact"]
    assert (fixed["status"], fixed["chosen_id"]) == ("accepted", data["contact"])
    assert _sql(database, world, decided_events, id=msg["id"]) == 1


def test_ja_needs_the_candidate_seen_and_never_takes_the_first_proposal(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0 (Rückfrage mit einem Kandidaten): B sieht am Ticket die Rückfrage mit dem
    einzigen Kandidaten Paula. Eine Änderung der internen Beschreibung rechnet die Vorschläge
    neu, Max (Kundennummer, 0,85) steht nun vorn. Ein Ja ohne Kandidat endet mit 422, es gibt
    keinen Rückgriff auf den ersten Vorschlag. Steht Paula noch in der Liste, setzt das Ja
    Paula. Ist Paula nicht mehr in der Liste, endet das Ja mit 409 (MHVP-COMM-0003) und
    speichert nichts."""
    h = bearer(login(client, world, "aradmin"))
    b = bearer(login(client, world, "arstd"))
    paula = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Paula", "last_name": f"Probe{RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    note = f"Paula Probe{RUN} bittet um Rückruf"

    def question() -> tuple[str, str]:
        created = _ok(
            client.post(T, json={"title": "Rückruf", "internal_description": note}, headers=h),
            201,
        )
        url = f"{T}/{created['id']}/assignment-review"
        contact = _by_dim(_ok(client.get(url, headers=b)))["contact"]
        assert contact["status"] == "open"
        assert [(c["id"], c["confidence"]) for c in contact["candidates"]] == [(paula, 0.7)]
        return created["id"], url

    def ja(url: str, candidate_id: str | None = None) -> Any:
        body = {"dimension": "contact", "decision": "accept", "seen_value": None}
        if candidate_id is not None:
            body["candidate_id"] = candidate_id
        return client.post(f"{url}/decide", json=body, headers=b)

    ticket_id, url = question()
    patch = {"internal_description": f"{note}, Kundennummer KD-{RUN}"}
    _ok(client.patch(f"{T}/{ticket_id}", json=patch, headers=h))
    contact = _by_dim(_ok(client.get(url, headers=h)))["contact"]
    assert [c["id"] for c in contact["candidates"]] == [data["contact"], paula]
    first = ja(url)
    assert first.status_code == 422, first.text
    assert _ok(client.get(f"{T}/{ticket_id}", headers=h))["contact_id"] is None
    decided = _by_dim(_ok(ja(url, paula)))["contact"]
    assert (decided["status"], decided["decision"], decided["chosen_id"]) == (
        "accepted",
        "accept",
        paula,
    )
    assert _ok(client.get(f"{T}/{ticket_id}", headers=h))["contact_id"] == paula

    ticket_id, url = question()
    patch = {"internal_description": f"Kundennummer KD-{RUN}"}
    _ok(client.patch(f"{T}/{ticket_id}", json=patch, headers=h))
    contact = _by_dim(_ok(client.get(url, headers=h)))["contact"]
    assert [c["id"] for c in contact["candidates"]] == [data["contact"]]
    gone = ja(url, paula)
    assert gone.status_code == 409, gone.text
    assert (gone.json()["code"], gone.json()["detail"]) == (
        "MHVP-COMM-0003",
        "Der bestätigte Kandidat gehört nicht zu den aktuellen Vorschlägen. Die Rückfrage ist "
        "überholt, bitte neu laden.",
    )
    assert _ok(client.get(f"{T}/{ticket_id}", headers=h))["contact_id"] is None
    assert _stored(database, world, ticket_id, "contact") == "open|-|-|-|-"
    assert _by_dim(_ok(ja(url, data["contact"])))["contact"]["chosen_id"] == data["contact"]


def test_superseded_question_stays_superseded_on_a_later_check(
    client: TestClient, world: World, data: dict[str, Any], database: Database
) -> None:
    """Review 1.36.0: Eine überholte Rückfrage bleibt bei jeder weiteren Prüfung überholt und
    gegen das leere Feld gerechnet. Nach einer zweiten Ticketänderung (interne Beschreibung)
    ist sie weiter superseded; ein Ja aus der Ansicht nach dem Neuladen (Erna gezeigt) endet
    mit 409 und überschreibt Erna nicht."""
    h = bearer(login(client, world, "aradmin"))
    ticket = _ok(
        client.post(
            T, json={"title": "Rückruf", "public_description": f"Kundennummer KD-{RUN}"}, headers=h
        ),
        201,
    )
    url = f"{T}/{ticket['id']}/assignment-review"
    assert _by_dim(_ok(client.get(url, headers=h)))["contact"]["status"] == "open"
    _ok(client.patch(f"{T}/{ticket['id']}", json={"contact_id": data["twin"]}, headers=h))
    assert _stored(database, world, ticket["id"], "contact") == "superseded|-|-|-|-"
    _ok(
        client.patch(
            f"{T}/{ticket['id']}", json={"internal_description": "Rückruf erledigt"}, headers=h
        )
    )
    assert _stored(database, world, ticket["id"], "contact") == "superseded|-|-|-|-"
    shown = _by_dim(_ok(client.get(url, headers=h)))["contact"]
    assert (shown["status"], shown["chosen_id"]) == ("superseded", data["twin"])
    stale = client.post(
        f"{url}/decide",
        json={
            "dimension": "contact",
            "decision": "accept",
            "candidate_id": data["contact"],
            "seen_value": data["twin"],
        },
        headers=h,
    )
    assert stale.status_code == 409, stale.text
    assert _ok(client.get(f"{T}/{ticket['id']}", headers=h))["contact_id"] == data["twin"]
