"""Zuordnung over the API (/imports/immoware24/lists/zuordnung): after objektdaten and kontakte a
test run writes nothing, apply creates the ownership contract once and records an import run, a second
apply finds them, unknown names and tenancies without landlord are reported, read only users get 403. Rows are invented."""

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
    "81;Musterstraße 2;WEG-Verwaltung;Haus A;1;WE 1;EG links;Muster, Max;250,00;;\n"
    "81;Musterstraße 2;WEG-Verwaltung;Haus A;2;WE 2;OG;Niemand, Nora;30,00;;\n"
    "82;Testweg 1;Mietverwaltung;;1;WE 1;;;;Erika Mieter;600,00\n"
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
        a, _ = await services.provision_tenant(factory, slug=f"lz-{RUN}", name=f"Zuordnung {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("lzadmin", "tenant_admin"), ("lzreader", "read_only")]:
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


def _ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _csv(name: str, text: str) -> tuple[str, bytes, str]:
    return (name, text.encode("utf-8"), "text/csv")


def _zuordnung(c: TestClient, h: dict[str, str], mode: str, **data: Any) -> Any:
    return c.post(
        f"{BASE}/zuordnung",
        params={"mode": mode},
        files={"file": _csv("objektdaten.csv", OBJEKTDATEN)},
        data=data,
        headers=h,
    )


def test_zuordnung_preview_then_apply(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "lzadmin"))
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

    dry = _ok(_zuordnung(client, h, "preview", start_date="2026-01-01"))
    assert dry["mode"] == "preview"
    assert dry["apply"] is False
    assert dry["start_date"] == "2026-01-01"
    assert dry["start_date_assumed"] is False
    assert dry["einheiten_gesamt"] == 3
    assert dry["eigentuemer_zugeordnet"] == 1
    assert dry["mieter_zugeordnet"] == 0
    assert [e["name"] for e in dry["nicht_gefunden"]] == ["Niemand, Nora"]
    # Without a known landlord the tenancy is reported as conflict, never guessed.
    assert [(e["objekt"], e["rolle"]) for e in dry["konflikte"]] == [("82", "Mieter")]
    assert dry["counts"]["vertraege_angelegt"] == 1

    applied = _ok(_zuordnung(client, h, "apply"))
    assert applied["mode"] == "apply"
    assert applied["import_run_id"]
    assert applied["start_date_assumed"] is True
    assert applied["counts"]["vertraege_angelegt"] == 1
    run = _ok(client.get(f"/api/v1/imports/{applied['import_run_id']}", headers=h))
    assert run["source"] == "immoware24:zuordnung"

    again = _ok(_zuordnung(client, h, "apply"))
    assert again["counts"].get("vertraege_angelegt", 0) == 0
    assert again["counts"]["vertraege_vorhanden"] == 1

    reader = bearer(login(client, world, "lzreader"))
    assert _zuordnung(client, reader, "preview").status_code == 403
    assert _zuordnung(client, h, "preview", start_date="kein Datum").status_code == 422
