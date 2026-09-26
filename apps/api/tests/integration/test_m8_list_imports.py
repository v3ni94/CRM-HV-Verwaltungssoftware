"""Immoware24 list imports over the API (/imports/immoware24/lists): test run without effect,
apply as import run with undo items, read only users get 403, tenant separation. Column
headers follow the Immoware24 exports as described in docs/handbuch/import-objektdaten.md and
import-kontakte.md; the rows are invented for the test."""

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

pytestmark = pytest.mark.integration
BASE = "/api/v1/imports/immoware24/lists"

OBJEKTDATEN = (
    "Objekt-Nummer;Objekt;Verwaltungsart;Gebäude;VE-Nummer;VE-Beschreibung;VE-Lage;"
    "aktueller Eigentümer;vereinbarter Zahlbetrag;aktueller Mieter;vereinbarter Zahlbetrag\n"
    "81;Musterstraße 2;WEG-Verwaltung;Haus A;1;WE 1;EG links;Muster, Max;250,00;;\n"
    "81;Musterstraße 2;WEG-Verwaltung;Haus A;2;TG 1;;Muster, Max;30,00;;\n"
    "10012;Z ABGEGEBEN Testweg 1;Mietverwaltung;;1;WE 1;;;;Mieter, Erika;600,00\n"
)
EIGENTUEMER = (
    "id;Name;Briefanrede;Benutzername;Adresse;Stadt;PLZ;Staat;Land;Landesvorwahl;Vorwahl;"
    "Telefonnummer;E-Mail\n"
    "4711;Muster, Max;Sehr geehrter Herr Muster;;Musterstraße 2;Musterstadt;12345;;Deutschland;"
    "0049;30;123456;max@example.org\n"
)
MIETER = "id;Name;Briefanrede\n4711;Muster, Max;Sehr geehrter Herr Muster\n4712;Erika Mieter;\n"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(database, redis_url)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"la-{RUN}", name=f"Listen A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"lb-{RUN}", name=f"Listen B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("liadmin", a, "tenant_admin"),
            ("lireader", a, "read_only"),
            ("libadmin", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _csv(name: str, text: str) -> tuple[str, bytes, str]:
    return (name, text.encode("utf-8"), "text/csv")


def _objektdaten(c: TestClient, h: dict[str, str], mode: str, **data: Any) -> Any:
    return c.post(
        f"{BASE}/objektdaten",
        params={"mode": mode},
        files={"file": _csv("objektdaten.csv", OBJEKTDATEN)},
        data=data,
        headers=h,
    )


def _kontakte(c: TestClient, h: dict[str, str], mode: str) -> Any:
    return c.post(
        f"{BASE}/kontakte",
        params={"mode": mode},
        files=[
            ("files", _csv("eigentuemer.csv", EIGENTUEMER)),
            ("files", _csv("mieter.csv", MIETER)),
        ],
        data={"roles": ["eigentuemer", "mieter"]},
        headers=h,
    )


def _by_objekt(report: Any) -> dict[str, Any]:
    return {e["objekt"]: e for e in report["objekte"]}


def _post_objektdaten(c: TestClient, h: dict[str, str], mode: str, data: bytes, **form: Any) -> Any:
    return c.post(
        f"{BASE}/objektdaten",
        params={"mode": mode},
        files={"file": ("objektdaten.csv", data, "text/csv")},
        data=form,
        headers=h,
    )


def test_objektdaten_preview_then_apply(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "liadmin"))
    overview = "/api/v1/imports/immoware24/overview"
    before = _ok(client.get(overview, headers=h))

    preview = _ok(_objektdaten(client, h, "preview", number_map="", skip_handed_over="false"))
    assert preview["mode"] == "preview"
    assert preview["apply"] is False
    assert "import_run_id" not in preview
    entries = _by_objekt(preview)
    assert entries["81"]["status"] == "created"
    assert entries["81"]["nummer"] == "081"
    assert entries["81"]["einheiten"] == {"created": 2}
    assert "führenden Nullen" in entries["81"]["hinweise"][0]
    assert entries["10012"]["status"] == "übersprungen"
    assert "nicht dreistellig" in entries["10012"]["probleme"][0]
    assert preview["counts"] == {"property_created": 1, "property_skipped": 1, "unit_created": 2}
    # Nothing was stored by the test run.
    assert _ok(client.get(overview, headers=h)) == before

    skipped = _ok(
        _objektdaten(client, h, "preview", number_map="10012=012", skip_handed_over="true")
    )
    assert _by_objekt(skipped)["10012"]["probleme"] == [
        "abgegebenes Objekt (Option --skip-handed-over)"
    ]

    applied = _ok(_objektdaten(client, h, "apply", number_map="10012=012"))
    assert applied["mode"] == "apply"
    assert applied["apply"] is True
    assert applied["counts"] == {"property_created": 2, "unit_created": 3}
    after = _ok(client.get(overview, headers=h))
    assert after["properties"] == before["properties"] + 2
    assert after["units"] == before["units"] + 3

    run = _ok(client.get(f"/api/v1/imports/{applied['import_run_id']}", headers=h))
    assert run["source"] == "immoware24:objektdaten"
    assert run["status"] == "applied"
    assert run["summary"] == applied["counts"]
    # Two properties, two buildings ("Haus A" and the default building of 012) and three
    # units are recorded for undo.
    assert (
        sorted(i["entity_type"] for i in run["items"])
        == ["building"] * 2 + ["property"] * 2 + ["unit"] * 3
    )

    # Second run: everything unchanged, nothing created.
    again = _ok(_objektdaten(client, h, "apply", number_map="10012=012"))
    assert again["counts"] == {"property_unchanged": 2, "unit_unchanged": 3}

    # Undo removes the created rows (existing import run mechanism).
    undone = _ok(client.post(f"/api/v1/imports/{applied['import_run_id']}/undo", headers=h))
    assert undone["status"] == "undone"
    assert _ok(client.get(overview, headers=h)) == before


def test_objektdaten_rejects_bad_input(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "liadmin"))
    bad_map = _objektdaten(client, h, "preview", number_map="10012")
    assert bad_map.status_code == 422, bad_map.text
    missing = client.post(
        f"{BASE}/objektdaten",
        files={"file": _csv("x.csv", "Spalte A;Spalte B\n1;2\n")},
        headers=h,
    )
    assert missing.status_code == 422, missing.text
    assert "Spalten fehlen" in missing.json()["detail"]
    assert (
        client.post(f"{BASE}/objektdaten", params={"mode": "delete"}, headers=h).status_code == 422
    )


def test_kontakte_preview_then_apply(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "liadmin"))
    overview = "/api/v1/imports/immoware24/overview"
    before = _ok(client.get(overview, headers=h))

    preview = _ok(_kontakte(client, h, "preview"))
    assert preview["apply"] is False
    assert preview["counts"] == {"created": 2, "role_added": 1}
    rows = {(r["datei"], r["id"]): r for r in preview["kontakte"]}
    assert rows[("eigentuemer.csv", "4711")]["status"] == "created"
    assert rows[("mieter.csv", "4711")]["status"] == "role_added"
    assert rows[("mieter.csv", "4712")]["hinweise"] == ["Reihenfolge Vorname Nachname angenommen"]
    assert _ok(client.get(overview, headers=h)) == before

    applied = _ok(_kontakte(client, h, "apply"))
    assert applied["counts"] == {"created": 2, "role_added": 1}
    assert _ok(client.get(overview, headers=h))["contacts"] == before["contacts"] + 2
    run = _ok(client.get(f"/api/v1/imports/{applied['import_run_id']}", headers=h))
    assert run["source"] == "immoware24:kontakte"
    assert sorted(i["entity_type"] for i in run["items"]) == [
        "contact",
        "contact",
        "party",
        "party",
    ]

    contact_ids = [i["entity_id"] for i in run["items"] if i["entity_type"] == "contact"]
    by_external = {
        c["external_ids"].get("immoware24"): c
        for c in (_ok(client.get(f"/api/v1/contacts/{cid}", headers=h)) for cid in contact_ids)
    }
    assert sorted(by_external["4711"]["roles"]) == ["eigentuemer", "mieter"]
    assert by_external["4712"]["first_name"] == "Erika"

    again = _ok(_kontakte(client, h, "apply"))
    assert again["counts"] == {"unchanged": 3}

    bad_role = client.post(
        f"{BASE}/kontakte",
        files=[("files", _csv("x.csv", EIGENTUEMER))],
        data={"roles": ["hausmeister"]},
        headers=h,
    )
    assert bad_role.status_code == 422, bad_role.text


def test_read_only_forbidden(client: TestClient, world: World) -> None:
    reader = bearer(login(client, world, "lireader"))
    assert _objektdaten(client, reader, "preview").status_code == 403
    assert _objektdaten(client, reader, "apply").status_code == 403
    assert _kontakte(client, reader, "preview").status_code == 403
    assert _kontakte(client, reader, "apply").status_code == 403


def test_tenant_separation(client: TestClient, world: World) -> None:
    """Rows applied in tenant A are invisible in tenant B: a test run there creates them again,
    and the import run of A cannot be read from B."""
    a = bearer(login(client, world, "liadmin"))
    b = bearer(login(client, world, "libadmin"))
    applied = _ok(_objektdaten(client, a, "apply", number_map="10012=012"))
    assert (
        applied["counts"]["property_created"] + applied["counts"].get("property_unchanged", 0) == 2
    )
    preview_b = _ok(_objektdaten(client, b, "preview", number_map="10012=012"))
    assert preview_b["counts"] == {"property_created": 2, "unit_created": 3}
    assert _ok(client.get("/api/v1/imports/immoware24/overview", headers=b))["properties"] == 0
    assert client.get(f"/api/v1/imports/{applied['import_run_id']}", headers=b).status_code == 404
    contacts_a = _ok(_kontakte(client, a, "apply"))
    assert contacts_a["counts"]
    assert _ok(_kontakte(client, b, "preview"))["counts"] == {"created": 2, "role_added": 1}


def test_export_variants_give_the_same_preview(client: TestClient, world: World) -> None:
    """Windows-1252, BOM, comma or tab delimiter, repeated header and empty lines: the test run
    reports the same counts and objects as the plain UTF-8 export, plus file notes."""
    h = bearer(login(client, world, "libadmin"))
    reference = _ok(_post_objektdaten(client, h, "preview", OBJEKTDATEN.encode("utf-8")))
    assert reference["datei_hinweise"] == []
    header, *rows = OBJEKTDATEN.strip("\n").split("\n")
    variants = {
        "cp1252": OBJEKTDATEN.encode("cp1252"),
        "bom": b"\xef\xbb\xbf" + OBJEKTDATEN.encode("utf-8"),
        "comma": "\n".join(
            ",".join(f'"{c}"' for c in line.split(";")) for line in [header, *rows]
        ).encode("utf-8"),
        "tab": OBJEKTDATEN.replace(";", "\t").encode("utf-8"),
        "repeated_header": "\n".join([header, rows[0], "", header, *rows[1:], ""]).encode("utf-8"),
    }
    for name, data in variants.items():
        report = _ok(_post_objektdaten(client, h, "preview", data))
        assert report["counts"] == reference["counts"], name
        assert _by_objekt(report).keys() == _by_objekt(reference).keys(), name
        assert _by_objekt(report)["81"]["einheiten"] == {"created": 2}, name
    assert any(
        "Windows-1252" in n
        for n in _ok(_post_objektdaten(client, h, "preview", variants["cp1252"]))["datei_hinweise"]
    )
    assert any(
        "Komma" in n
        for n in _ok(_post_objektdaten(client, h, "preview", variants["comma"]))["datei_hinweise"]
    )
    notes = _ok(_post_objektdaten(client, h, "preview", variants["repeated_header"]))[
        "datei_hinweise"
    ]
    assert any("wiederholte Kopfzeile" in n for n in notes)
    assert any("leere Zeile" in n for n in notes)

    missing = _post_objektdaten(client, h, "preview", b"Objekt-Nummer;Objekt;VE-Nummer\n1;x;1\n")
    assert missing.status_code == 422, missing.text
    assert "Spalte fehlt: Verwaltungsart" in missing.json()["detail"]
    assert "Gefundene Spalten: Objekt-Nummer, Objekt, VE-Nummer" in missing.json()["detail"]


def test_kontakte_duplicates_iban_and_idempotent_apply(client: TestClient, world: World) -> None:
    """A repeated id within one file is reported and created once; an IBAN column is only a
    masked proposal and never becomes a bank account; test run and apply count the same, and
    a second apply changes nothing."""
    h = bearer(login(client, world, "libadmin"))
    overview = "/api/v1/imports/immoware24/overview"
    before = _ok(client.get(overview, headers=h))
    text = (
        "id;Name;Briefanrede;Adresse;PLZ;Stadt;Telefon;Email;IBAN\n"
        "9001;Duplikat, Dora;Sehr geehrte Frau Duplikat;Musterstraße 1a;12345;Musterstadt;"
        "0221 / 12 34 56 7;Dora <dora@example.org>;DE02 1203 0000 0000 2020 51\n"
        "9002;Beispiel GmbH & Co. KG;;Am Markt 3-5;12345;Musterstadt;;;\n"
        "9001;Duplikat, Dora;Sehr geehrte Frau Duplikat;Musterstraße 1a;12345;Musterstadt;;;\n"
    ).encode("cp1252")

    def post(mode: str) -> Any:
        return client.post(
            f"{BASE}/kontakte",
            params={"mode": mode},
            files=[("files", ("mieter.csv", text, "text/csv"))],
            data={"roles": ["mieter"]},
            headers=h,
        )

    preview = _ok(post("preview"))
    assert preview["counts"] == {"created": 2, "duplicate": 1}
    assert any("Windows-1252" in n for n in preview["datei_hinweise"])
    rows = {(r["zeile"], r["id"]): r for r in preview["kontakte"]}
    assert rows[(4, "9001")]["status"] == "duplicate"
    assert rows[(4, "9001")]["hinweise"] == ["id 9001 bereits in Zeile 2, nicht erneut angelegt"]
    assert any(
        "DE02 **** **** 2051" in n and "nicht übernommen" in n
        for n in rows[(2, "9001")]["hinweise"]
    )
    assert _ok(client.get(overview, headers=h)) == before

    applied = _ok(post("apply"))
    assert applied["counts"] == preview["counts"]
    assert _ok(client.get(overview, headers=h))["contacts"] == before["contacts"] + 2
    run = _ok(client.get(f"/api/v1/imports/{applied['import_run_id']}", headers=h))
    contact_ids = [i["entity_id"] for i in run["items"] if i["entity_type"] == "contact"]
    contacts = {
        c["external_ids"]["immoware24"]: c
        for c in (_ok(client.get(f"/api/v1/contacts/{cid}", headers=h)) for cid in contact_ids)
    }
    dora = contacts["9001"]
    assert dora["bank_accounts"] == []
    assert "120300000000202051" not in str(dora)
    assert "DE02 **** **** 2051" in (dora["notes"] or "")
    assert (dora["first_name"], dora["last_name"], dora["salutation"]) == (
        "Dora",
        "Duplikat",
        "Frau",
    )
    assert dora["addresses"][0]["street"] == "Musterstraße"
    assert dora["addresses"][0]["house_number"] == "1a"
    assert dora["phones"][0]["number"] == "+492211234567"
    assert dora["emails"][0]["email"] == "dora@example.org"
    firma = contacts["9002"]
    assert firma["kind"] == "company"
    assert firma["legal_form"] == "GmbH & Co. KG"
    assert firma["addresses"][0]["house_number"] == "3-5"

    again = _ok(post("apply"))
    assert again["counts"] == {"unchanged": 2, "duplicate": 1}
    assert _ok(client.get(overview, headers=h))["contacts"] == before["contacts"] + 2
