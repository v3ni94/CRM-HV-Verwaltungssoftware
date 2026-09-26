"""Eigentümer festlegen (POST /properties/{id}/owner) against PostgreSQL: a rental property
without owner is listed by without_owner and leaves its tenancy unassigned; setting the owner
from a contact is idempotent, another owner is a conflict unless replaced, WEG objects refuse,
and a second assignment run then finds the landlord. Rows are invented."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.config import Settings
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m8_list_imports import EIGENTUEMER, MIETER

pytestmark = pytest.mark.integration
BASE = "/api/v1/imports/immoware24/lists"
OBJEKTDATEN = (
    "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
    "aktueller Eigentümer;vereinbarter Zahlbetrag;aktueller Mieter;vereinbarter Zahlbetrag\n"
    "83;Musterstraße 2;WEG-Verwaltung;Haus A;1;WE 1;EG links;Muster, Max;250,00;;\n"
    "84;Testweg 1;Mietverwaltung;;1;WE 1;;;;Erika Mieter;600,00\n"
)


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(database, redis_url)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"po-{RUN}", name=f"Eigentümer {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("poadmin", "tenant_admin"), ("poreader", "read_only")]:
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json()


def _csv(name: str, text: str) -> tuple[str, bytes, str]:
    return (name, text.encode("utf-8"), "text/csv")


def _zuordnung(c: TestClient, h: dict[str, str]) -> Any:
    return _ok(
        c.post(
            f"{BASE}/zuordnung",
            params={"mode": "apply"},
            files={"file": _csv("objektdaten.csv", OBJEKTDATEN)},
            data={"start_date": "2026-01-01"},
            headers=h,
        )
    )


def _prop(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    page = _ok(c.get("/api/v1/properties", params={"q": number}, headers=h))
    return next(p for p in page["items"] if p["number"] == number)


def _contact(c: TestClient, h: dict[str, str], q: str) -> str:
    page = _ok(c.get("/api/v1/contacts", params={"q": q}, headers=h))
    items = page["items"] if isinstance(page, dict) else page
    return str(items[0]["id"])


def test_set_owner_then_tenancy_is_assigned(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "poadmin"))
    _ok(
        client.post(
            f"{BASE}/objektdaten",
            params={"mode": "apply"},
            files={"file": _csv("objektdaten.csv", OBJEKTDATEN)},
            headers=h,
        )
    )
    _ok(
        client.post(
            f"{BASE}/kontakte",
            params={"mode": "apply"},
            files=[
                ("files", _csv("eigentuemer.csv", EIGENTUEMER)),
                ("files", _csv("mieter.csv", MIETER)),
            ],
            data={"roles": ["eigentuemer", "mieter"]},
            headers=h,
        )
    )
    first = _zuordnung(client, h)
    assert [(e["objekt"], e["rolle"]) for e in first["konflikte"]] == [("84", "Mieter")]
    assert first["mieter_zugeordnet"] == 0

    rental, weg = _prop(client, h, "084"), _prop(client, h, "083")
    assert rental["owner_missing"] is True
    assert weg["owner_missing"] is False
    missing = _ok(client.get("/api/v1/properties", params={"without_owner": True}, headers=h))
    assert [p["number"] for p in missing["items"]] == ["084"]

    max_id = _contact(client, h, "Muster")
    url = f"/api/v1/properties/{rental['id']}/owner"
    reader = bearer(login(client, world, "poreader"))
    assert client.post(url, json={"contact_id": max_id}, headers=reader).status_code == 403
    weg_set = client.post(
        f"/api/v1/properties/{weg['id']}/owner", json={"contact_id": max_id}, headers=h
    )
    assert weg_set.status_code == 422

    body = {"contact_id": max_id, "valid_from": "2026-01-01", "share_percent": "100"}
    created = _ok(client.post(url, json=body, headers=h), 201)
    assert created["status"] == "created"
    assert created["owner"]["contact_id"] == max_id
    assert created["owner"]["legal_entity_id"]
    again = _ok(client.post(url, json=body, headers=h))
    assert again["status"] == "unchanged"
    assert again["owner"]["id"] == created["owner"]["id"]
    owners = _ok(client.get(f"/api/v1/properties/{rental['id']}/owners", headers=h))
    assert [o["contact_id"] for o in owners] == [max_id]
    missing = _ok(client.get("/api/v1/properties", params={"without_owner": True}, headers=h))
    assert missing["items"] == []
    roles = _ok(client.get(f"/api/v1/contacts/{max_id}", headers=h))["roles"]
    assert "eigentuemer" in roles

    second = _zuordnung(client, h)
    assert second["konflikte"] == []
    assert second["mieter_zugeordnet"] == 1

    erika = _contact(client, h, "Erika")
    conflict = client.post(url, json={"contact_id": erika}, headers=h)
    assert conflict.status_code == 409, conflict.text
    early = client.post(
        url, json={"contact_id": erika, "valid_from": "2026-01-01", "replace": True}, headers=h
    )
    assert early.status_code == 422
    replaced = _ok(
        client.post(
            url, json={"contact_id": erika, "valid_from": "2026-07-01", "replace": True}, headers=h
        )
    )
    assert replaced["status"] == "replaced"
    assert replaced["ended"][0]["valid_to"] == "2026-06-30"
    assert replaced["owner"]["contact_id"] == erika
