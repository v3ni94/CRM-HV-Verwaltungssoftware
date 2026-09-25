"""M33 Wissensbasis und Mail-Vorbereitung (Welle 3 item 14): Wissenseintrag anlegen, ändern,
löschen, Mandantentrennung und Berechtigungen; Mail-Vorbereitung löst Absender, Rolle und Einheit
auf und erstellt einen Antwortentwurf mit einem gefakten KI-Anbieter (keine Netzwerkzugriffe); die
Korrektur einer Vorbereitung legt einen gelernten Wissenseintrag an."""

import asyncio
import json
from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.ai import providers
from mhvp.ai.providers import Completion
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
M = "/api/v1"

PROVIDER = {
    "api_key": "sk-test-not-real",
    "models": {
        "small": {
            "model": "claude-haiku-4-5",
            "input_eur_per_mtok": "1",
            "output_eur_per_mtok": "5",
        },
        "large": {"model": "claude-opus-5", "input_eur_per_mtok": "5", "output_eur_per_mtok": "25"},
    },
    "monthly_budget_eur": "50.00",
    "data_processing_agreement_signed": True,
    "training_opt_out_confirmed": True,
    "endpoint_region": "eu",
    "enabled": True,
}


class FakeProvider:
    def __init__(self) -> None:
        self.queue: list[Any] = []
        self.calls: list[dict[str, Any]] = []

    async def complete(self, **kwargs: Any) -> Completion:
        self.calls.append(kwargs)
        data = self.queue.pop(0) if self.queue else {}
        return Completion(
            data=data, raw_text=json.dumps(data), tokens_in=100, tokens_out=50, model=kwargs["model"]
        )


@pytest.fixture
def fake() -> Iterator[FakeProvider]:
    provider = FakeProvider()
    providers.set_factory(lambda _p, _k: provider)
    yield provider
    providers.set_factory(providers.default_factory)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"kb-{RUN}", name=f"Wissen {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"kb2-{RUN}", name=f"Wissen2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for tenant_id, name, role in [
            (a, "kbadmin", "tenant_admin"),
            (a, "kbsecond", "tenant_admin"),
            (a, "kbreader", "read_only"),
            (b, "kbother", "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"Objekt {number}",
        "management_type": "rental",
        "street": "Rheinpromenade",
        "house_number": "13",
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }
    return _ok(c.post(f"{M}/properties", json=body, headers=h), 201)


def _unit(c: TestClient, h: dict[str, str], prop_id: str, number: str) -> str:
    building = _ok(
        c.post(f"{M}/properties/{prop_id}/buildings", json={"name": "Haus"}, headers=h), 201
    )
    unit = _ok(
        c.post(
            f"{M}/properties/{prop_id}/units",
            json={
                "building_id": building["id"],
                "number": number,
                "label": f"WE {number}",
                "unit_type": "apartment",
            },
            headers=h,
        ),
        201,
    )
    return str(unit["id"])


def _party_with_email(
    c: TestClient, h: dict[str, str], name: str, email: str
) -> tuple[str, str]:
    contact = _ok(
        c.post(
            f"{M}/contacts",
            json={
                "kind": "person",
                "first_name": name,
                "last_name": f"Test{RUN}",
                "emails": [{"label": "private", "email": email, "is_primary": True}],
            },
            headers=h,
        ),
        201,
    )
    party = _ok(
        c.post(f"{M}/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h), 201
    )
    return str(party["id"]), str(contact["id"])


def _eml(sender: str, subject: str, msg_id: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"], msg["Message-ID"] = (
        f"Mieter <{sender}>",
        "info@example.com",
        subject,
        msg_id,
    )
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0200"
    msg.set_content(body)
    return bytes(msg)


def _upload(c: TestClient, h: dict[str, str], name: str, data: bytes) -> str:
    return str(
        _ok(
            c.post("/api/v1/documents", files={"file": (name, data, "message/rfc822")}, headers=h),
            201,
        )["id"]
    )


def _setup_provider(c: TestClient, admin: dict[str, str], second: dict[str, str]) -> None:
    dpa = _upload(c, admin, "avv.eml", b"Auftragsverarbeitungsvertrag Muster")
    body = {**PROVIDER, "dpa_document_id": dpa}
    _ok(c.put(f"{M}/ai/providers/anthropic", json=body, headers=admin), 200)
    _ok(c.post(f"{M}/ai/providers/anthropic/release", headers=second), 200)


# Wissensbasis: CRUD, Mandantentrennung, Berechtigungen ---------------------------------------


def test_knowledge_crud_and_filters(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "kbadmin"))
    reader = bearer(login(client, world, "kbreader"))
    prop = _property(client, admin, "801")

    forbidden = client.post(
        f"{M}/ai/knowledge",
        json={"kind": "fact", "title": "x", "content": "y"},
        headers=reader,
    )
    assert forbidden.status_code == 403

    global_entry = _ok(
        client.post(
            f"{M}/ai/knowledge",
            json={"kind": "workflow", "title": "Ablage", "content": "Rechnungen nach Objekt."},
            headers=admin,
        ),
        201,
    )
    assert global_entry["source"] == "manual"
    property_entry = _ok(
        client.post(
            f"{M}/ai/knowledge",
            json={
                "property_id": prop["id"],
                "kind": "filing_rule",
                "title": "Teilungserklärung",
                "content": "Liegt im Drive-Ordner 02_Stammakte.",
            },
            headers=admin,
        ),
        201,
    )

    all_entries = _ok(client.get(f"{M}/ai/knowledge", headers=admin))
    assert {e["id"] for e in all_entries} >= {global_entry["id"], property_entry["id"]}

    by_property = _ok(
        client.get(f"{M}/ai/knowledge", params={"property_id": prop["id"]}, headers=admin)
    )
    assert [e["id"] for e in by_property] == [property_entry["id"]]

    by_kind = _ok(client.get(f"{M}/ai/knowledge", params={"kind": "workflow"}, headers=admin))
    assert global_entry["id"] in [e["id"] for e in by_kind]
    assert property_entry["id"] not in [e["id"] for e in by_kind]

    updated = _ok(
        client.put(
            f"{M}/ai/knowledge/{property_entry['id']}",
            json={
                "property_id": prop["id"],
                "kind": "filing_rule",
                "title": "Teilungserklärung",
                "content": "Liegt im Drive-Ordner 02_Stammakte, aktualisiert.",
            },
            headers=admin,
        )
    )
    assert updated["content"].endswith("aktualisiert.")

    assert client.delete(f"{M}/ai/knowledge/{property_entry['id']}", headers=reader).status_code == 403
    assert client.delete(f"{M}/ai/knowledge/{property_entry['id']}", headers=admin).status_code == 204
    assert client.get(f"{M}/ai/knowledge", headers=admin).status_code == 200
    remaining = _ok(client.get(f"{M}/ai/knowledge", headers=admin))
    assert property_entry["id"] not in [e["id"] for e in remaining]


def test_knowledge_tenant_separation(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "kbadmin"))
    other = bearer(login(client, world, "kbother"))
    entry = _ok(
        client.post(
            f"{M}/ai/knowledge",
            json={"kind": "fact", "title": "Nur Mandant A", "content": "Geheim"},
            headers=admin,
        ),
        201,
    )
    other_list = _ok(client.get(f"{M}/ai/knowledge", headers=other))
    assert entry["id"] not in [e["id"] for e in other_list]
    assert client.put(
        f"{M}/ai/knowledge/{entry['id']}",
        json={"kind": "fact", "title": "x", "content": "y"},
        headers=other,
    ).status_code == 404


# Mail-Vorbereitung ---------------------------------------------------------------------------


def test_mail_preparation_and_correction(client: TestClient, world: World, fake: FakeProvider) -> None:
    admin = bearer(login(client, world, "kbadmin"))
    second = bearer(login(client, world, "kbsecond"))
    _setup_provider(client, admin, second)

    prop = _property(client, admin, "802")
    unit = _unit(client, admin, prop["id"], "01")
    email = f"mieter-vorbereitung{RUN}@example.com"
    party_id, contact_id = _party_with_email(client, admin, "Vorbereitung", email)
    owner_id, _ = _party_with_email(client, admin, "Eigentuemer", f"owner{RUN}@example.com")
    _ok(
        client.post(
            f"{M}/properties/{prop['id']}/owners",
            json={"party_id": owner_id, "valid_from": "2020-01-01"},
            headers=admin,
        ),
        201,
    )
    contract = _ok(
        client.post(
            f"{M}/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party_id,
                "start_date": "2026-01-01",
            },
            headers=admin,
        ),
        201,
    )
    assert contract["property_id"] == prop["id"]

    _ok(
        client.post(
            f"{M}/ai/knowledge",
            json={
                "property_id": prop["id"],
                "kind": "workflow",
                "title": "Nebenkostenabrechnung",
                "content": "Frist ist jeweils der 31.12. des Folgejahres.",
            },
            headers=admin,
        ),
        201,
    )

    fake.queue.append(
        {
            "category": "Abrechnung",
            "urgency": "normal",
            "summary": "Mieter fragt nach der Nebenkostenabrechnung.",
            "property_number": prop["number"],
            "contact_name": "Vorbereitung",
            "reply_draft": "Sehr geehrte Frau Vorbereitung, die Abrechnung folgt fristgerecht.",
        }
    )
    raw = _eml(
        email,
        f"Frage zur Nebenkostenabrechnung Objekt {prop['number']} {RUN}",
        f"<prep-{RUN}@x>",
        "Wann bekomme ich meine Nebenkostenabrechnung?",
    )
    doc = _upload(client, admin, "m1.eml", raw)
    msg = _ok(
        client.post(f"{M}/mail/ingest", json={"document_id": doc, "auto_ticket": False}, headers=admin),
        201,
    )

    computed = _ok(
        client.post(f"{M}/mail/messages/{msg['id']}/preparation", headers=admin)
    )
    assert computed["contact_id"] == contact_id
    assert computed["unit_id"] == unit
    assert computed["property_id"] == prop["id"]
    assert computed["role"] == "tenant"
    assert computed["status"] == "ready"
    assert "Abrechnung" in (computed["draft"] or "")
    assert any(r for r in computed["reasons"] if "Vertrag" in r)

    fetched = _ok(client.get(f"{M}/mail/messages/{msg['id']}/preparation", headers=admin))
    assert fetched["draft"] == computed["draft"]

    correction = _ok(
        client.post(
            f"{M}/mail/messages/{msg['id']}/preparation/correct",
            json={
                "contact_id": contact_id,
                "unit_id": unit,
                "property_id": prop["id"],
                "note": "Rolle war falsch erkannt, richtig ist Mieter Erdgeschoss links.",
            },
            headers=admin,
        )
    )
    assert "knowledge_entry_id" in correction

    knowledge = _ok(client.get(f"{M}/ai/knowledge", params={"kind": "correction"}, headers=admin))
    entry = next(e for e in knowledge if e["id"] == correction["knowledge_entry_id"])
    assert entry["source"] == "learned"
    assert "Erdgeschoss" in entry["content"]

    after_correction = _ok(client.get(f"{M}/mail/messages/{msg['id']}/preparation", headers=admin))
    assert after_correction["correction"]["note"].startswith("Rolle war falsch")


def test_preparation_without_contact_match(client: TestClient, world: World, fake: FakeProvider) -> None:
    admin = bearer(login(client, world, "kbadmin"))
    raw = _eml(
        f"unbekannt{RUN}@example.com",
        f"Allgemeine Frage {RUN}",
        f"<prep2-{RUN}@x>",
        "Ich habe eine allgemeine Frage.",
    )
    doc = _upload(client, admin, "m2.eml", raw)
    msg = _ok(
        client.post(f"{M}/mail/ingest", json={"document_id": doc, "auto_ticket": False}, headers=admin),
        201,
    )
    computed = _ok(client.post(f"{M}/mail/messages/{msg['id']}/preparation", headers=admin))
    assert computed["contact_id"] is None
    assert computed["property_id"] is None
    assert any("Kontakt" in r for r in computed["reasons"])
