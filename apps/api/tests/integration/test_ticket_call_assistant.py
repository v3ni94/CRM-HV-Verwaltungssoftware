"""Hallo-Heidi-Anrufe über die API (mhvp.tickets.call_assistant, propose_call und
``accept-and-reply``): ein Protokoll erzeugt Ticket, Zuordnung und Vorschlag mit
Antwortentwurf; "Freigeben und antworten" legt den Entwurf an den Anrufer an. Ohne
E-Mail-Adresse des Kontakts oder ohne Kontakt gibt es 422 und keinen leeren Entwurf, der
Vorschlag bleibt offen und kann ohne Antwort freigegeben werden; ein fremder Mandant sieht
nichts (Review 1.25.0). Die Fixtures und Hilfen kommen aus ``test_m19_ticket_proposals``."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import providers
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m19_ticket_proposals import (
    HEIDI,
    FakeProvider,
    T,
    _ingest,
    _ok,
    _owner,
    _weg,
)

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"tc-{RUN}", name=f"Anruf {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"td-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("tcadmin", "tenant_admin", a),
            ("tcreader", "read_only", a),
            ("tdadmin", "tenant_admin", b),
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
    return asyncio.run(
        _world(_settings(database, redis_url).model_copy(update={"ai_inline": True}))
    )


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    settings = _settings(database, redis_url).model_copy(update={"ai_inline": True})
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    provider = FakeProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


def _protocol(last: str, street: str, phone: str) -> str:
    return (
        "Neue Gesprächsnotiz von Hallo Heidi\n\n"
        f"Anrufer: Frau Petra {last}\n"
        f"Rückrufnummer: {phone}\n"
        f"Objekt: {street} 12, 40210 Düsseldorf\n"
        "Einheit: Whg. 3, 2. OG links\n"
        "Anliegen: Die Heizung in der Wohnung bleibt seit gestern kalt.\n"
    )


def _drafts(c: TestClient, h: dict[str, str], ticket_id: str) -> list[dict[str, Any]]:
    rows = _ok(c.get("/api/v1/mail/messages", params={"ticket_id": ticket_id}, headers=h))
    data = rows["data"] if isinstance(rows, dict) else rows
    return [m for m in data if m["direction"] == "out"]


def test_propose_call_and_accept_and_reply_happy_path(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "tcadmin"))
    street = f"Happy{RUN}straße"
    prop, unit = _weg(client, h, street, 11)
    email = f"petra.happy.{RUN}@example.org"
    last = f"Happy{RUN}"
    contact = _owner(client, h, unit, "Petra", last, email)

    msg = _ingest(
        client,
        h,
        HEIDI,
        "Hallo Heidi: neuer Anruf",
        f"<heidi-happy-{RUN}@x>",
        _protocol(last, f"Happy{RUN}str.", "0171 / 234 56 78"),
    )
    ticket_id = msg["ticket_id"]
    ticket = _ok(client.get(f"{T}/{ticket_id}", headers=h))
    assert ticket["contact_id"] == contact["id"]
    assert ticket["property_id"] == prop["id"]
    assert ticket["unit_id"] == unit
    summary = next(e for e in ticket["events"] if e["kind"] == "call_summary")
    assert summary["data"]["contact_id"] == contact["id"]
    assert summary["data"]["call"]["caller_phone"] == "+491712345678"

    rows = _ok(client.get(f"{T}/{ticket_id}/proposals", headers=h))
    assert len(rows) == 1
    proposal = rows[0]
    assert proposal["decision"] == "pending"
    assert proposal["proposed"]["kind"] == "call"
    assert proposal["proposed"]["contact_id"] == contact["id"]
    assert proposal["proposed"]["changes"][0]["new"] == "+491712345678"
    assert proposal["proposed"]["bank_change_mentioned"] is False
    assert proposal["proposed"]["reply_draft"]["body"].startswith(f"Hallo Frau {last},")

    done = _ok(
        client.post(f"{T}/{ticket_id}/proposals/{proposal['id']}/accept-and-reply", headers=h),
        201,
    )
    assert done["decision"] == "accepted"
    assert done["final"]["applied"] == ["phones"]
    assert done["reply_message_status"] == "draft"
    draft = _ok(client.get(f"/api/v1/mail/messages/{done['reply_message_id']}", headers=h))
    assert draft["to_addresses"] == [email]
    assert draft["status"] == "draft"
    assert draft["sent_at"] is None
    assert draft["ticket_id"] == ticket_id
    after = _ok(client.get(f"/api/v1/contacts/{contact['id']}", headers=h))
    assert {p["number"] for p in after["phones"]} >= {"+491712345678", "+492111234567"}
    detail = _ok(client.get(f"{T}/{ticket_id}", headers=h))
    assert {e["kind"] for e in detail["events"]} >= {
        "call_summary",
        "proposal_created",
        "proposal_accepted",
        "proposal_reply_draft",
    }


def test_accept_and_reply_without_contact_email_refuses_and_keeps_proposal(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    """Kontakt ohne E-Mail-Adresse: 422 mit deutschem Hinweis, kein Entwurf ohne Empfänger,
    Vorschlag bleibt offen, Nummer nicht übernommen; ``accept`` übernimmt danach die Nummer."""
    h = bearer(login(client, world, "tcadmin"))
    street = f"Ohnemail{RUN}straße"
    _prop, unit = _weg(client, h, street, 23)
    last = f"Ohnemail{RUN}"
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "salutation": "Frau", "first_name": "Petra", "last_name": last},
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party["id"],
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    msg = _ingest(
        client,
        h,
        HEIDI,
        "Hallo Heidi: neuer Anruf",
        f"<heidi-noemail-{RUN}@x>",
        _protocol(last, f"Ohnemail{RUN}str.", "0172 / 345 67 89"),
    )
    ticket_id = msg["ticket_id"]
    assert _ok(client.get(f"{T}/{ticket_id}", headers=h))["contact_id"] == contact["id"]
    proposal = _ok(client.get(f"{T}/{ticket_id}/proposals", headers=h))[0]
    assert proposal["proposed"]["contact_id"] == contact["id"]

    refused = client.post(f"{T}/{ticket_id}/proposals/{proposal['id']}/accept-and-reply", headers=h)
    assert refused.status_code == 422, refused.text
    problem = refused.json()
    assert problem["code"] == "MHVP-CORE-0004"
    assert "keine E-Mail-Adresse" in problem["detail"]
    assert _drafts(client, h, ticket_id) == []
    still = _ok(client.get(f"{T}/{ticket_id}/proposals", headers=h))[0]
    assert still["decision"] == "pending"
    assert still["reply_message_id"] is None
    before = _ok(client.get(f"/api/v1/contacts/{contact['id']}", headers=h))
    assert "+491723456789" not in {p["number"] for p in before["phones"]}
    assert before["version"] == contact["version"]

    # Stammdatenübernahme ohne Antwort bleibt möglich.
    accepted = _ok(client.post(f"{T}/{ticket_id}/proposals/{proposal['id']}/accept", headers=h))
    assert accepted["decision"] == "accepted"
    after = _ok(client.get(f"/api/v1/contacts/{contact['id']}", headers=h))
    assert "+491723456789" in {p["number"] for p in after["phones"]}
    # Auch der nachträgliche Antwortentwurf legt keinen leeren Entwurf an.
    later = client.post(f"{T}/{ticket_id}/proposals/{proposal['id']}/reply-draft", headers=h)
    assert later.status_code == 422, later.text
    assert _drafts(client, h, ticket_id) == []


def test_accept_and_reply_without_contact_refuses(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    """Unbekannter Anrufer ohne Objekt: Vorschlag ohne Kontakt, 422 und kein Entwurf."""
    h = bearer(login(client, world, "tcadmin"))
    msg = _ingest(
        client,
        h,
        HEIDI,
        "Hallo Heidi: neuer Anruf",
        f"<heidi-nocontact-{RUN}@x>",
        f"Anrufer: Herr Unbekannt{RUN} Niemand\nRückrufnummer: 0173 / 456 78 90\n"
        "Anliegen: Bitte um Rückruf.\n",
    )
    ticket_id = msg["ticket_id"]
    assert _ok(client.get(f"{T}/{ticket_id}", headers=h))["contact_id"] is None
    rows = _ok(client.get(f"{T}/{ticket_id}/proposals", headers=h))
    assert len(rows) == 1
    proposal = rows[0]
    assert proposal["proposed"]["contact_id"] is None
    refused = client.post(f"{T}/{ticket_id}/proposals/{proposal['id']}/accept-and-reply", headers=h)
    assert refused.status_code == 422, refused.text
    assert "kein Kontakt zugeordnet" in refused.json()["detail"]
    assert _drafts(client, h, ticket_id) == []
    assert _ok(client.get(f"{T}/{ticket_id}/proposals", headers=h))[0]["decision"] == "pending"


def test_accept_and_reply_tenant_separation_and_permission(
    client: TestClient, world: World, fake: FakeProvider
) -> None:
    h = bearer(login(client, world, "tcadmin"))
    other = bearer(login(client, world, "tdadmin"))
    reader = bearer(login(client, world, "tcreader"))
    street = f"Fremd{RUN}straße"
    _prop, unit = _weg(client, h, street, 37)
    last = f"Fremd{RUN}"
    _owner(client, h, unit, "Petra", last, f"petra.fremd.{RUN}@example.org")
    msg = _ingest(
        client,
        h,
        HEIDI,
        "Hallo Heidi: neuer Anruf",
        f"<heidi-tenant-{RUN}@x>",
        _protocol(last, f"Fremd{RUN}str.", "0174 / 567 89 01"),
    )
    ticket_id = msg["ticket_id"]
    proposal = _ok(client.get(f"{T}/{ticket_id}/proposals", headers=h))[0]
    url = f"{T}/{ticket_id}/proposals/{proposal['id']}/accept-and-reply"
    assert client.get(f"{T}/{ticket_id}", headers=other).status_code == 404
    assert client.get(f"{T}/{ticket_id}/proposals", headers=other).status_code == 404
    assert client.post(url, headers=other).status_code == 404
    assert client.post(url, headers=reader).status_code == 403
    assert _ok(client.get(f"{T}/{ticket_id}/proposals", headers=h))[0]["decision"] == "pending"
    assert _drafts(client, h, ticket_id) == []
    assert _ok(client.post(url, headers=h), 201)["reply_message_status"] == "draft"
