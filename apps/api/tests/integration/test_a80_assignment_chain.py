"""Sure chain of the Zuordnungsprüfung (Betreiber 27.09.2026, A-068 Nachtrag 1.37.0): once the
contact is sure, exactly one active tenancy contract or exactly one active ownership unit of
the contact assigns unit and property automatically, only into an empty field; several
contracts or an unsure contact stay a question or untouched. Synthetic names and addresses."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_a80_assignment_review import _eml
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _property, _unit
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
        a, _ = await services.provision_tenant(factory, slug=f"ach-{RUN}", name=f"Kette {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("achadmin"), display_name="achadmin", password=PASSWORD
        )
        world.users["achadmin"] = uid
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


def _by_dim(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {r["dimension"]: r for r in reviews}


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


def _ticket_from_mail(
    client: TestClient, h: dict[str, str], sender: str, subject: str, body: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Erzeugt ein Ticket aus einer Mail mit eindeutiger Absenderadresse (Kontakt sicher, auto)
    und liefert (Ticket, Mail)."""
    msg = _ingest(client, h, sender, subject, body)
    created = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=h), 201)
    ticket = _ok(client.get(f"{T}/{created['ticket_id']}", headers=h))
    return ticket, msg


def _contact_with_email(client: TestClient, h: dict[str, str], name: str, email: str) -> Any:
    return _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": name,
                "last_name": f"Test{RUN}",
                "emails": [{"email": email}],
            },
            headers=h,
        ),
        201,
    )


def _owner(client: TestClient, h: dict[str, str], property_id: str) -> None:
    """Vermieter des Objekts (Voraussetzung für einen Mietvertrag)."""
    landlord, _ = _party(client, h, "Vermieter")
    _ok(
        client.post(
            f"/api/v1/properties/{property_id}/owners",
            json={"party_id": landlord, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )


def _tenancy(client: TestClient, h: dict[str, str], unit_id: str, party_id: str) -> Any:
    return _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit_id,
                "party_id": party_id,
                "start_date": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )


def _ownership(client: TestClient, h: dict[str, str], unit_id: str, party_id: str) -> Any:
    return _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit_id,
                "party_id": party_id,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )


def _auto_events(database: Database, tenant_id: Any, ticket_id: str) -> list[dict[str, Any]]:
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
            )
            rows = conn.execute(
                text(
                    "SELECT payload FROM domain_event WHERE entity_id = :id "
                    "AND type = 'assignment_review.auto'"
                ),
                {"id": ticket_id},
            ).all()
            return [dict(r._mapping["payload"]) for r in rows]
    finally:
        engine.dispose()


def _n(n: int) -> str:
    """Eine gültige dreistellige Objektnummer, je Test verschieden, ohne Kollision zwischen
    parallelen Testläufen (RUN ist je Modulausführung eindeutig)."""
    return f"{(int(RUN, 16) + n) % 900:03d}"


def test_single_tenancy_contract_assigns_unit_and_property(
    client: TestClient, world: World, database: Database
) -> None:
    """Kontakt sicher (eindeutige Absenderadresse) mit genau einem aktiven Mietvertrag: Einheit
    und Objekt werden automatisch übernommen, Grund "eindeutiger Vertrag"."""
    h = bearer(login(client, world, "achadmin"))
    prop = _property(client, h, _n(1), "rental")
    unit = _unit(client, h, prop["id"], "01")
    _owner(client, h, prop["id"])
    email = f"anna-{RUN}@example.com"
    contact = _contact_with_email(client, h, "Anna", email)
    contract_party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    _tenancy(client, h, unit, contract_party["id"])

    ticket, _msg = _ticket_from_mail(client, h, email, "Frage", "Guten Tag, kurze Frage.")
    assert ticket["contact_id"] == contact["id"]
    assert ticket["property_id"] == prop["id"]
    assert ticket["unit_id"] == unit

    reviews = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=h)))
    assert reviews["property"]["status"] == "auto"
    assert reviews["property"]["reason"] == "eindeutiger Vertrag"
    assert reviews["unit"]["status"] == "auto"
    assert reviews["unit"]["reason"] == "eindeutiger Vertrag"

    events = _auto_events(database, world.tenant_a, ticket["id"])
    assert any(
        e["dimension"] == "property" and e["reason"] == "eindeutiger Vertrag" for e in events
    )
    assert any(e["dimension"] == "unit" and e["reason"] == "eindeutiger Vertrag" for e in events)


def test_single_ownership_unit_assigns_unit_and_property(client: TestClient, world: World) -> None:
    """Kontakt sicher mit genau einer aktiven Eigentümerschaft (Vertrag kind=ownership) einer
    Einheit: automatische Übernahme, Grund "eindeutiges Eigentum"."""
    h = bearer(login(client, world, "achadmin"))
    weg = _property(client, h, _n(2), "hoa_with_sev")
    unit = _unit(client, h, weg["id"], "01")
    email = f"bernd-{RUN}@example.com"
    contact = _contact_with_email(client, h, "Bernd", email)
    contract_party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    _ownership(client, h, unit, contract_party["id"])

    ticket, _msg = _ticket_from_mail(client, h, email, "Frage", "Guten Tag, kurze Frage.")
    assert ticket["property_id"] == weg["id"]
    assert ticket["unit_id"] == unit
    reviews = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=h)))
    assert reviews["property"]["reason"] == "eindeutiges Eigentum"
    assert reviews["unit"]["reason"] == "eindeutiges Eigentum"


def test_two_contracts_stay_a_question(client: TestClient, world: World) -> None:
    """Zwei aktive Mietverträge über verschiedene Einheiten: keine automatische Übernahme,
    beide Einheiten als Kandidaten der Rückfrage."""
    h = bearer(login(client, world, "achadmin"))
    prop = _property(client, h, _n(3), "rental")
    unit_a = _unit(client, h, prop["id"], "01")
    unit_b = _unit(client, h, prop["id"], "02")
    _owner(client, h, prop["id"])
    email = f"clara-{RUN}@example.com"
    contact = _contact_with_email(client, h, "Clara", email)
    contract_party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    _tenancy(client, h, unit_a, contract_party["id"])
    _tenancy(client, h, unit_b, contract_party["id"])

    ticket, _msg = _ticket_from_mail(client, h, email, "Frage", "Guten Tag, kurze Frage.")
    assert ticket["property_id"] is None
    assert ticket["unit_id"] is None
    reviews = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=h)))
    assert reviews["property"]["status"] == "open"
    assert {c["id"] for c in reviews["property"]["candidates"]} == {prop["id"]}
    assert {c["id"] for c in reviews["unit"]["candidates"]} == {unit_a, unit_b}


def test_unsure_contact_derives_no_unit_or_property(client: TestClient, world: World) -> None:
    """Unbekannte Absenderadresse, Nachname trifft zwei Kontakte (Rückfrage): keine Ableitung
    von Objekt oder Einheit, auch wenn ein Kontakt einen eindeutigen Vertrag hat."""
    h = bearer(login(client, world, "achadmin"))
    prop = _property(client, h, _n(4), "rental")
    unit = _unit(client, h, prop["id"], "01")
    _owner(client, h, prop["id"])
    surname = f"Zwilling{RUN}"
    dora = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Dora", "last_name": surname},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Doris", "last_name": surname},
            headers=h,
        ),
        201,
    )
    contract_party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": dora["id"]}]}, headers=h),
        201,
    )
    _tenancy(client, h, unit, contract_party["id"])

    body = (
        f"Sehr geehrte Damen und Herren,\n\nbitte um Rückruf.\n\nMit freundlichen Grüßen\n{surname}"
    )
    ticket = _ok(
        client.post(T, json={"title": "Frage", "public_description": body}, headers=h), 201
    )
    assert ticket["contact_id"] is None
    assert ticket["property_id"] is None
    assert ticket["unit_id"] is None
    reviews = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=h)))
    assert reviews["contact"]["status"] == "open"
    assert reviews["property"]["status"] == "none"
    assert reviews["unit"]["status"] == "none"


def test_already_set_field_stays_untouched(client: TestClient, world: World) -> None:
    """Objekt bereits (manuell) gesetzt: der eindeutige Vertrag des sicheren Kontakts
    überschreibt es nicht (Regel 1: nur bei leerem Feld)."""
    h = bearer(login(client, world, "achadmin"))
    prop = _property(client, h, _n(5), "rental")
    other = _property(client, h, _n(6), "rental")
    unit = _unit(client, h, prop["id"], "01")
    _owner(client, h, prop["id"])
    email = f"elke-{RUN}@example.com"
    contact = _contact_with_email(client, h, "Elke", email)
    contract_party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    _tenancy(client, h, unit, contract_party["id"])

    msg = _ingest(client, h, email, "Frage", "Guten Tag, kurze Frage.")
    assert msg["contact_id"] == contact["id"]
    # Objekt manuell setzen, bevor das Ticket aus der Mail entsteht (die Zuordnungsprüfung des
    # Tickets sieht dann ein bereits gefülltes Feld).
    _ok(client.patch(f"{M}/messages/{msg['id']}", json={"property_id": other["id"]}, headers=h))
    created = _ok(client.post(f"{M}/messages/{msg['id']}/ticket", headers=h), 201)
    ticket = _ok(client.get(f"{T}/{created['ticket_id']}", headers=h))
    assert ticket["contact_id"] == contact["id"]
    assert ticket["property_id"] == other["id"]
    assert ticket["unit_id"] is None
    reviews = _by_dim(_ok(client.get(f"{T}/{ticket['id']}/assignment-review", headers=h)))
    assert reviews["property"]["chosen_id"] == other["id"]


def test_ja_on_contact_reevaluates_the_chain(client: TestClient, world: World) -> None:
    """Ein Ja auf eine unsichere Kontakt-Rückfrage löst die Prüfung von Objekt und Einheit
    erneut aus; hat der bestätigte Kontakt genau einen aktiven Vertrag, wird dieser jetzt
    automatisch übernommen."""
    h = bearer(login(client, world, "achadmin"))
    prop = _property(client, h, _n(7), "rental")
    unit = _unit(client, h, prop["id"], "01")
    _owner(client, h, prop["id"])
    surname = f"Nachzuegler{RUN}"
    frieda = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Frieda", "last_name": surname},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Frida", "last_name": surname},
            headers=h,
        ),
        201,
    )
    contract_party = _ok(
        client.post("/api/v1/parties", json={"members": [{"contact_id": frieda["id"]}]}, headers=h),
        201,
    )
    _tenancy(client, h, unit, contract_party["id"])

    body = (
        "Sehr geehrte Damen und Herren,\n\nbitte um Rückruf.\n\n"
        f"Mit freundlichen Grüßen\nFrieda {surname}"
    )
    ticket = _ok(
        client.post(T, json={"title": "Frage", "public_description": body}, headers=h), 201
    )
    assert ticket["contact_id"] is None
    assert ticket["property_id"] is None

    decided = _by_dim(
        _ok(
            client.post(
                f"{T}/{ticket['id']}/assignment-review/decide",
                json={
                    "dimension": "contact",
                    "decision": "accept",
                    "candidate_id": frieda["id"],
                    "seen_value": None,
                },
                headers=h,
            )
        )
    )
    assert decided["contact"]["status"] == "accepted"
    assert decided["property"]["status"] == "auto"
    assert decided["property"]["reason"] == "eindeutiger Vertrag"
    assert decided["unit"]["status"] == "auto"
    after = _ok(client.get(f"{T}/{ticket['id']}", headers=h))
    assert after["property_id"] == prop["id"]
    assert after["unit_id"] == unit
