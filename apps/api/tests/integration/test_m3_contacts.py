"""M3 acceptance: CRUD via API, duplicate proposals, full text search, export per contact."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"c-{RUN}", name=f"Kontakte A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"d-{RUN}", name=f"Kontakte B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("clerk", a, "clerk_no_delete"),
            ("boss", a, "tenant_admin"),
            ("other", b, "tenant_admin"),
            ("viewer", a, "read_only"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(f"m3{name}"), display_name=name, password=PASSWORD
            )
            world.users[f"m3{name}"] = uid
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


PERSON = {
    "kind": "person",
    "salutation": "Frau",
    "first_name": "Erika",
    "last_name": f"Musterfrau{RUN}",
    "addresses": [
        {
            "label": "postal",
            "street": "Hauptstraße",
            "house_number": "1",
            "postal_code": "40789",
            "city": "Monheim am Rhein",
        }
    ],
    "phones": [{"label": "mobile", "number": "0171 1234567"}],
    "emails": [{"email": f"Erika.{RUN}@Example.org"}],
    "bank_accounts": [
        {
            "iban": "DE02 1203 0000 0000 2020 51",
            "valid_from": "2026-01-01",
            "holder": "Erika Musterfrau",
        }
    ],
    "types": ["owner"],
    "tags": ["Beirat", "WEG 342"],
}


def test_contact_crud_roundtrip(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "m3clerk"))
    created = client.post("/api/v1/contacts", json=PERSON, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["display_name"] == f"Musterfrau{RUN}, Erika"
    assert body["phones"][0]["number"] == "+491711234567"
    assert body["emails"][0]["email"] == f"erika.{RUN}@example.org"
    assert body["emails"][0]["is_primary"] is True
    assert body["bank_accounts"][0]["iban_masked"] == "DE02 **** **** 2051"
    assert "2020" not in created.text  # full IBAN never returned
    contact_id, etag = body["id"], created.headers["etag"]

    changed = dict(PERSON, first_name="Erika Maria", tags=["Beirat"])
    stale = client.put(
        f"/api/v1/contacts/{contact_id}", json=changed, headers=headers | {"If-Match": '"99"'}
    )
    assert stale.status_code == 412
    updated = client.put(
        f"/api/v1/contacts/{contact_id}", json=changed, headers=headers | {"If-Match": etag}
    )
    assert updated.status_code == 200
    assert updated.json()["tags"] == ["Beirat"]
    assert updated.json()["version"] == 2

    audit = client.get(
        f"/api/v1/tenant/audit-log?entity_id={contact_id}",
        headers=bearer(login(client, world, "m3boss")),
    ).json()
    assert audit[0]["changes"]["first_name"] == {"old": "Erika", "new": "Erika Maria"}

    # clerk_no_delete cannot delete; tenant admin can (soft delete)
    assert client.delete(f"/api/v1/contacts/{contact_id}", headers=headers).status_code == 403
    boss = bearer(login(client, world, "m3boss"))
    assert client.delete(f"/api/v1/contacts/{contact_id}", headers=boss).status_code == 204
    assert (
        client.get(f"/api/v1/contacts/{contact_id}", headers=boss).json()["deleted_at"] is not None
    )
    assert (
        client.put(f"/api/v1/contacts/{contact_id}", json=changed, headers=boss).status_code == 404
    )


@pytest.mark.parametrize(
    ("patch", "field"),
    [
        (
            {"bank_accounts": [{"iban": "DE02120300000000202052", "valid_from": "2026-01-01"}]},
            "iban",
        ),
        ({"phones": [{"number": "12"}]}, "number"),
        ({"emails": [{"email": "not-an-email"}]}, "email"),
        ({"first_name": None, "last_name": None}, ""),
    ],
)
def test_validation(client: TestClient, world: World, patch: dict[str, Any], field: str) -> None:
    headers = bearer(login(client, world, "m3clerk"))
    response = client.post("/api/v1/contacts", json=PERSON | patch, headers=headers)
    assert response.status_code == 422
    if field:
        assert any(e["field"] == field for e in response.json()["errors"])


def test_company_contact_and_duplicate_proposals(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "m3clerk"))
    company = {
        "kind": "company",
        "company_name": f"Sanitär Schmidt {RUN} GmbH",
        "emails": [{"email": f"info-{RUN}@schmidt.example.org"}],
    }
    first = client.post("/api/v1/contacts", json=company, headers=headers)
    assert first.status_code == 201
    by_email = client.get(
        "/api/v1/contacts/duplicates",
        params={"email": f"INFO-{RUN}@schmidt.example.org"},
        headers=headers,
    ).json()
    assert by_email[0]["contact"]["id"] == first.json()["id"]
    assert "gleiche E-Mail-Adresse" in by_email[0]["reasons"]
    by_name = client.get(
        "/api/v1/contacts/duplicates",
        params={"company_name": f"Sanitaer Schmidt {RUN}"},
        headers=headers,
    ).json()
    assert any(c["contact"]["id"] == first.json()["id"] for c in by_name)
    person = client.post(
        "/api/v1/contacts", json=PERSON | {"last_name": f"Iban{RUN}"}, headers=headers
    ).json()
    by_iban = client.get(
        "/api/v1/contacts/duplicates", params={"iban": "de02120300000000202051"}, headers=headers
    ).json()
    assert any(
        c["contact"]["id"] == person["id"] and "gleiche IBAN" in c["reasons"] for c in by_iban
    )


def test_full_text_and_global_search(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "m3clerk"))
    created = client.post(
        "/api/v1/contacts", json=PERSON | {"last_name": f"Suchbar{RUN}"}, headers=headers
    ).json()
    page = client.get("/api/v1/contacts", params={"q": f"suchbar{RUN[:4]}"}, headers=headers).json()
    assert any(item["id"] == created["id"] for item in page["items"])
    by_phone = client.get("/api/v1/contacts", params={"q": "1711234567"}, headers=headers).json()
    assert by_phone["total"] >= 1
    by_iban_end = client.get("/api/v1/contacts", params={"q": "2051"}, headers=headers).json()
    assert by_iban_end["total"] >= 1
    hits = client.get("/api/v1/search", params={"q": f"Suchbar{RUN}"}, headers=headers).json()
    assert hits[0]["id"] == created["id"]
    assert hits[0]["entity_type"] == "contact"
    tagged = client.get("/api/v1/contacts", params={"tag": "WEG 342"}, headers=headers).json()
    assert tagged["total"] >= 1


def test_contacts_isolated_between_tenants(client: TestClient, world: World) -> None:
    created = client.post(
        "/api/v1/contacts",
        json=PERSON | {"last_name": f"Geheim{RUN}"},
        headers=bearer(login(client, world, "m3clerk")),
    ).json()
    other = bearer(login(client, world, "m3other"))
    assert client.get(f"/api/v1/contacts/{created['id']}", headers=other).status_code == 404
    assert (
        client.get("/api/v1/contacts", params={"q": f"Geheim{RUN}"}, headers=other).json()["total"]
        == 0
    )
    assert client.get("/api/v1/search", params={"q": f"Geheim{RUN}"}, headers=other).json() == []
    assert client.get(f"/api/v1/contacts/{created['id']}/export", headers=other).status_code == 404


def test_read_only_cannot_write_or_export(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "m3viewer"))
    assert client.get("/api/v1/contacts", headers=headers).status_code == 200
    assert client.post("/api/v1/contacts", json=PERSON, headers=headers).status_code == 403
    assert client.get(f"/api/v1/contacts/{uuid.uuid4()}/export", headers=headers).status_code == 403


def test_parties_notes_consents_relations_and_export(client: TestClient, world: World) -> None:
    headers = bearer(login(client, world, "m3boss"))
    anna = client.post(
        "/api/v1/contacts",
        json={"kind": "person", "first_name": "Anna", "last_name": f"Paar{RUN}"},
        headers=headers,
    ).json()
    ben = client.post(
        "/api/v1/contacts",
        json={"kind": "person", "first_name": "Ben", "last_name": f"Paar{RUN}"},
        headers=headers,
    ).json()
    party = client.post(
        "/api/v1/parties",
        json={
            "members": [
                {"contact_id": anna["id"], "role": "primary", "share_percent": "50"},
                {"contact_id": ben["id"], "role": "co_party", "share_percent": "50"},
            ]
        },
        headers=headers,
    )
    assert party.status_code == 201
    assert party.json()["name"] == f"Anna und Ben Paar{RUN}"
    too_much = client.post(
        "/api/v1/parties",
        json={
            "members": [
                {"contact_id": anna["id"], "share_percent": "80"},
                {"contact_id": ben["id"], "share_percent": "30"},
            ]
        },
        headers=headers,
    )
    assert too_much.status_code == 422
    assert (
        client.post(
            f"/api/v1/contacts/{anna['id']}/notes",
            json={"body": "Rückruf erbeten", "pinned": True},
            headers=headers,
        ).status_code
        == 201
    )
    consent = client.post(
        f"/api/v1/contacts/{anna['id']}/consents",
        json={
            "kind": "email_delivery",
            "granted_at": "2026-09-01T10:00:00Z",
            "source": "Formular Portal",
        },
        headers=headers,
    )
    assert consent.status_code == 201
    assert (
        client.post(f"/api/v1/consents/{consent.json()['id']}/revoke", headers=headers).json()[
            "revoked_at"
        ]
        is not None
    )
    rel = client.post(
        f"/api/v1/contacts/{anna['id']}/relations",
        json={"related_contact_id": ben["id"], "kind": "spouse"},
        headers=headers,
    )
    assert rel.status_code == 201
    self_rel = client.post(
        f"/api/v1/contacts/{anna['id']}/relations",
        json={"related_contact_id": anna["id"], "kind": "spouse"},
        headers=headers,
    )
    assert self_rel.status_code == 422
    export = client.get(f"/api/v1/contacts/{anna['id']}/export", headers=headers)
    assert export.status_code == 200
    data = export.json()
    assert data["review_required"] is True
    assert data["contact"]["id"] == anna["id"]
    assert data["notes"][0]["body"] == "Rückruf erbeten"
    assert data["consents"][0]["revoked_at"] is not None
    assert data["parties"][0]["own_role"] == "primary"
    # Relations only reference the other contact; no data of that person is disclosed.
    assert data["relations"] == [{"kind": "spouse", "related_contact_id": ben["id"]}]
    assert "Ben" not in str(data["contact"])
    assert any(e["type"] == "contact.created" for e in data["processing_log"])


def test_iban_encrypted_at_rest(client: TestClient, world: World, migrator_engine: Engine) -> None:
    created = client.post(
        "/api/v1/contacts",
        json=PERSON | {"last_name": f"Krypto{RUN}"},
        headers=bearer(login(client, world, "m3clerk")),
    ).json()
    with migrator_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        raw = conn.execute(
            text("SELECT iban, iban_suffix FROM contact_bank_account WHERE contact_id = :c"),
            {"c": created["id"]},
        ).one()
    assert b"DE02120300000000202051" not in bytes(raw.iban)
    assert raw.iban_suffix == "2051"
