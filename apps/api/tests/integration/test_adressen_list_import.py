"""Addresses over the API (/imports/immoware24/lists/adressen-ableiten and /adressen): after
objektdaten the preview writes nothing, apply fills only empty fields and records an import run,
a second apply fills nothing, differences are conflicts and never overwrite, read only users get
403. Rows are invented."""

import asyncio
import io
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BASE = "/api/v1/imports/immoware24/lists"
OBJEKTDATEN = (
    "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
    "aktueller Eigentümer;vereinbarter Zahlbetrag;aktueller Mieter;vereinbarter Zahlbetrag\n"
    "82;Shalomweg 3;WEG-Verwaltung;;1;WE 1;EG;;;;\n"
    "83;WEG Am Panke Park 67-85;WEG-Verwaltung;;1;WE 1;EG;;;;\n"
    "84;Garagenhof Nord;Mietverwaltung;;1;Garage 1;;;;;\n"
)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"la-{RUN}", name=f"Adressen {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("laadmin", "tenant_admin"), ("lareader", "read_only")]:
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
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(base_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def _property(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    body = _ok(c.get("/api/v1/properties", params={"q": number, "page_size": 100}, headers=h))
    pid = next(p["id"] for p in body["items"] if p["number"] == number)
    return cast(dict[str, Any], _ok(c.get(f"/api/v1/properties/{pid}", headers=h)))


def _xlsx(rows: list[list[Any]]) -> bytes:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_adressen_derive_and_list(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "laadmin"))
    _ok(
        client.post(
            f"{BASE}/objektdaten",
            params={"mode": "apply"},
            files={"file": ("o.csv", OBJEKTDATEN.encode(), "text/csv")},
            headers=h,
        )
    )
    derive = f"{BASE}/adressen-ableiten"
    dry = _ok(client.post(derive, params={"mode": "preview"}, headers=h))
    assert dry["apply"] is False
    assert dry["counts"]["filled"] == 2
    assert [u["name"] for u in dry["unrecognised"]] == ["Garagenhof Nord"]
    assert _property(client, h, "082")["street"] is None

    applied = _ok(client.post(derive, params={"mode": "apply"}, headers=h))
    assert applied["import_run_id"]
    p82 = _property(client, h, "082")
    assert (p82["street"], p82["house_number"]) == ("Shalomweg", "3")
    p83 = _property(client, h, "083")
    assert (p83["street"], p83["house_number"]) == ("Am Panke Park", "67-85")
    run = _ok(client.get(f"/api/v1/imports/{applied['import_run_id']}", headers=h))
    assert run["source"] == "immoware24:adressen-ableiten"
    again = _ok(client.post(derive, params={"mode": "apply"}, headers=h))
    assert again["counts"]["filled"] == 0

    csv_text = (
        "Objektnummer;Straße;PLZ;Ort\n82;Shalomweg 3;10115;Berlin\n"
        "83;Andere Straße 1;13187;Berlin\n84;Garagenhof 5;13189;Berlin\n999;X 1;1;Y\n"
    )
    upload = {"file": ("adressen.csv", csv_text.encode(), "text/csv")}
    dry = _ok(client.post(f"{BASE}/adressen", params={"mode": "preview"}, files=upload, headers=h))
    assert dry["counts"]["filled"] == 3
    assert {(c["number"], c["field"]) for c in dry["conflicts"]} == {
        ("083", "Straße"),
        ("083", "Hausnummer"),
    }
    assert [u["number"] for u in dry["unknown"]] == ["999"]
    assert _property(client, h, "082")["city"] is None

    applied = _ok(
        client.post(f"{BASE}/adressen", params={"mode": "apply"}, files=upload, headers=h)
    )
    assert applied["import_run_id"]
    p82 = _property(client, h, "082")
    assert (p82["postal_code"], p82["city"]) == ("10115", "Berlin")
    p83 = _property(client, h, "083")
    assert (p83["street"], p83["postal_code"]) == ("Am Panke Park", "13187")
    p84 = _property(client, h, "084")
    assert (p84["street"], p84["house_number"]) == ("Garagenhof", "5")

    xlsx = _xlsx(
        [["Objekt-Nr.", "Str.", "Nr.", "PLZ", "Stadt"], [82, "Shalomweg", "3", "10115", "Berlin"]]
    )
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    again = _ok(
        client.post(
            f"{BASE}/adressen",
            params={"mode": "apply"},
            files={"file": ("a.xlsx", xlsx, mime)},
            headers=h,
        )
    )
    assert again["counts"]["filled"] == 0
    assert again["counts"]["conflicts"] == 0

    bad = {"file": ("x.csv", b"Name;Ort\nA;B\n", "text/csv")}
    assert client.post(f"{BASE}/adressen", files=bad, headers=h).status_code == 422
    reader = bearer(login(client, world, "lareader"))
    assert client.post(derive, headers=reader).status_code == 403
    assert client.post(f"{BASE}/adressen", files=upload, headers=reader).status_code == 403
