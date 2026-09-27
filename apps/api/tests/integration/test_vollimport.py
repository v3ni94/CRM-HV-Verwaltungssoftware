"""Full import with cut-off date over the API (M8-01, M8-02, V9, annex D D01/D02): pre-check,
dry run without effect, apply of the synthetic 67 objects / 869 units dataset with a
reconciliation of zero differences, idempotent re-import, update of deviating master data,
contract lists (Mietverträge, Eigentümerverträge) with per object counts and target sums,
opening balance proposals assigned to the contracts as draft, PDF draft, permissions and
tenant separation. Runtime of the full run is measured and printed (rule 0.1.8: expected
counts come from the generator)."""

from __future__ import annotations

import asyncio
import time
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
from tests.synthetic_immoware import OBJEKTDATEN_HEADER, Dataset, generate

pytestmark = pytest.mark.integration
BASE = "/api/v1/imports/immoware24/vollimport"
CUTOFF = "2026-12-31"


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(database, redis_url)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"vi-{RUN}", name=f"Vollimport {RUN}")
        b, _ = await services.provision_tenant(
            factory, slug=f"vi2-{RUN}", name=f"Vollimport2 {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("viadmin", a, "tenant_admin"),
            ("vireader", a, "read_only"),
            ("vibadmin", b, "tenant_admin"),
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


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return generate()


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _files(
    data: Dataset, objektdaten: str | None = None
) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("files", ("objektdaten.csv", (objektdaten or data.objektdaten).encode(), "text/csv")),
        ("files", ("eigentuemer.csv", data.eigentuemer.encode("cp1252"), "text/csv")),
        ("files", ("mieter.csv", data.mieter.encode(), "text/csv")),
        ("files", ("adressen.csv", data.adressen.encode(), "text/csv")),
        ("files", ("salden.csv", data.salden.encode(), "text/csv")),
        ("files", ("bank.csv", data.bankumsaetze.encode(), "text/csv")),
        ("files", ("eigentuemervertraege.csv", data.eigentuemervertraege.encode(), "text/csv")),
        ("files", ("mietvertraege.csv", data.mietvertraege.encode(), "text/csv")),
    ]


KINDS = [
    "objektdaten",
    "eigentuemer",
    "mieter",
    "adressen",
    "salden",
    "bankumsaetze",
    "eigentuemervertraege",
    "mietvertraege",
]


def _run(
    c: TestClient,
    h: dict[str, str],
    data: Dataset,
    mode: str,
    objektdaten: str | None = None,
    **form: Any,
) -> Any:
    return c.post(
        BASE,
        params={"mode": mode},
        files=_files(data, objektdaten),
        data={"cutoff_date": CUTOFF, "kinds": KINDS, **form},
        headers=h,
    )


def _entity(report: Any, name: str) -> Any:
    return next(e for e in report["abgleich"] if e["entitaet"] == name)


def test_export_kinds_and_precheck(client: TestClient, world: World, dataset: Dataset) -> None:
    h = bearer(login(client, world, "viadmin"))
    kinds = _ok(client.get(f"{BASE}/exporttypen", headers=h))
    assert {k["kind"] for k in kinds} >= {
        "objektdaten",
        "eigentuemer",
        "mieter",
        "sonstige",
        "adressen",
        "bankumsaetze",
        "mietvertraege",
        "eigentuemervertraege",
    }
    check = _ok(
        client.post(f"{BASE}/vorpruefung", files=_files(dataset), data={"kinds": KINDS}, headers=h)
    )
    assert check["ok"] is True
    by_kind = {c["art"]: c for c in check["vorpruefung"]}
    assert by_kind["objektdaten"]["zeilen"] == 869
    assert by_kind["eigentuemer"]["zeichensatz"] == "Windows-1252"
    assert len(by_kind["objektdaten"]["sha256"]) == 64
    # A broken header aborts the run before anything is written (422 with the pre-check).
    bad = client.post(
        BASE,
        params={"mode": "apply"},
        files=[("files", ("o.csv", b"Objekt;VE-Nummer\n1;2\n", "text/csv"))],
        data={"cutoff_date": CUTOFF, "kinds": ["objektdaten"]},
        headers=h,
    )
    assert bad.status_code == 422, bad.text
    assert _ok(client.get(BASE, headers=h)) == []


def test_full_import_67_objects_869_units_zero_differences(
    client: TestClient, world: World, dataset: Dataset
) -> None:
    h = bearer(login(client, world, "viadmin"))
    overview = "/api/v1/imports/immoware24/overview"
    before = _ok(client.get(overview, headers=h))

    preview = _ok(_run(client, h, dataset, "preview"))
    assert preview["apply"] is False
    assert preview["id"] is None
    assert preview["abgebrochen"] is False
    assert preview["vorschau"]["objekte"] == {"created": 67}
    assert preview["vorschau"]["einheiten"] == {"created": 869}
    assert preview["vorschau"]["kontakte"]["created"] == len(dataset.owner_ids) + len(
        dataset.tenant_ids
    )
    assert preview["vorschau"]["mietvertraege"] == {"created": dataset.tenancy_rows}
    assert preview["vorschau"]["eigentuemervertraege"] == {"created": dataset.ownership_rows}
    # The reconciliation inside the preview sees the rows of the savepoint: zero differences.
    assert preview["differenzen"] == 0
    assert _ok(client.get(overview, headers=h)) == before
    assert _ok(client.get(BASE, headers=h)) == []

    started = time.perf_counter()
    applied = _ok(_run(client, h, dataset, "apply"))
    elapsed = time.perf_counter() - started
    print(  # noqa: T201 - runtime measurement for docs/plans/M8.md
        f"\nVollimport 67 Objekte / 869 Einheiten: {elapsed:.1f} s (Server {applied['dauer_ms']} ms)"
    )
    assert applied["apply"] is True
    assert applied["id"]
    assert applied["stichtag"] == CUTOFF
    assert applied["counts"]["objektdaten"] == {"property_created": 67, "unit_created": 869}
    objekte, einheiten = _entity(applied, "objekte"), _entity(applied, "einheiten")
    assert (objekte["soll"], objekte["ist"], objekte["uebereinstimmend"]) == (67, 67, 67)
    assert (einheiten["soll"], einheiten["ist"], einheiten["uebereinstimmend"]) == (869, 869, 869)
    eig = _entity(applied, "kontakte_eigentuemer")
    assert eig["soll"] == len(dataset.owner_ids) == eig["uebereinstimmend"]
    mie = _entity(applied, "kontakte_mieter")
    assert mie["soll"] == len(dataset.tenant_ids) == mie["uebereinstimmend"]
    adr = _entity(applied, "adressen")
    assert adr["soll"] == 67 == adr["uebereinstimmend"]
    assert applied["differenzen"] == 0
    assert _entity(applied, "bankumsaetze")["soll"] == 67
    # Contract lists: every row created once, target and actual per object agree, the rent
    # and Hausgeld sums per object equal the reference sums of the generator.
    assert applied["counts"]["vertraege"] == {
        "eigentuemervertraege": {"created": dataset.ownership_rows},
        "mietvertraege": {"created": dataset.tenancy_rows},
    }
    miet = _entity(applied, "mietvertraege")
    assert (miet["soll"], miet["ist"], miet["uebereinstimmend"]) == (dataset.tenancy_rows,) * 3
    eig_v = _entity(applied, "eigentuemervertraege")
    assert (eig_v["soll"], eig_v["ist"], eig_v["uebereinstimmend"]) == (dataset.ownership_rows,) * 3
    assert {o["objekt"]: o["soll_summe"] for o in miet["je_objekt"]} == {
        k: f"{v:.2f}" for k, v in dataset.rent_sums.items()
    }
    assert all(o["ist_summe"] == o["soll_summe"] for o in miet["je_objekt"])
    assert all(not o["abweichung"] for o in miet["je_objekt"] + eig_v["je_objekt"])
    assert {
        o["objekt"]: o["ist_summe"] for o in eig_v["je_objekt"] if o["objekt"] in dataset.fee_sums
    } == {k: f"{v:.2f}" for k, v in dataset.fee_sums.items()}
    assert sum(o["soll_anzahl"] for o in eig_v["je_objekt"]) == dataset.ownership_rows
    # Opening balances: every entry is assigned to exactly one contract (draft, G1 closed).
    salden = applied["eroeffnungssalden"]
    assert salden["status"] == "entwurf"
    assert salden["anzahl"] == {"zugeordnet": dataset.balance_rows}
    assert all(e["contract_id"] and e["vertrag"] for e in salden["eintraege"])
    after = _ok(client.get(overview, headers=h))
    assert after["properties"] == before["properties"] + 67
    assert after["units"] == before["units"] + 869
    assert after["contracts"] == before["contracts"] + dataset.tenancy_rows + (
        dataset.ownership_rows - dataset.landlord_rows
    )
    assert elapsed < 600
    # Imported contracts wait for the management approval; nothing is posted.
    pending = _ok(client.get("/api/v1/contracts/pending-approval", headers=h))
    assert len(pending) >= dataset.tenancy_rows

    run = _ok(client.get(f"/api/v1/imports/{applied['import_run_id']}", headers=h))
    assert run["source"] == "immoware24:vollimport"
    stored = _ok(client.get(f"{BASE}/{applied['id']}", headers=h))
    assert stored["status"] == "applied"
    assert stored["differences"] == 0
    assert stored["cutoff_date"] == CUTOFF
    assert [f["art"] for f in stored["files"]] == KINDS
    assert stored["report"]["differenzen"] == 0
    pdf = client.get(f"{BASE}/{applied['id']}/pdf", headers=h)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"].startswith("application/pdf")

    # Idempotent re-import: nothing is created twice, still zero differences.
    started = time.perf_counter()
    again = _ok(_run(client, h, dataset, "apply"))
    print(  # noqa: T201 - runtime measurement for docs/plans/M8.md
        f"\nRe-Import inkl. Verträge: {time.perf_counter() - started:.1f} s "
        f"(Server {again['dauer_ms']} ms)"
    )
    assert again["counts"]["objektdaten"] == {"property_unchanged": 67, "unit_unchanged": 869}
    assert again["differenzen"] == 0
    assert again["counts"]["kontakte"].get("created") is None
    assert again["counts"]["vertraege"] == {
        "eigentuemervertraege": {"unchanged": dataset.ownership_rows},
        "mietvertraege": {"unchanged": dataset.tenancy_rows},
    }
    assert _ok(client.get(overview, headers=h)) == after
    # A changed rent in the file: the reconciliation lists the row and the object sum, a
    # re-import reports the row as unchanged (contract amounts are never overwritten).
    first_rent = dataset.mietvertraege.splitlines()[1]
    changed_rent = dataset.mietvertraege.replace(
        first_rent, first_rent[: first_rent.rfind(";")] + ";1,00", 1
    )
    check_rent = _ok(
        client.post(
            BASE,
            params={"mode": "abgleich"},
            files=[("files", ("mietvertraege.csv", changed_rent.encode(), "text/csv"))],
            data={"cutoff_date": CUTOFF, "kinds": ["mietvertraege"]},
            headers=h,
        )
    )
    miet_check = _entity(check_rent, "mietvertraege")
    assert check_rent["differenzen"] == 1
    assert miet_check["abweichend"][0]["felder"][0]["feld"] == "rent"
    assert miet_check["abweichend"][0]["felder"][0]["soll"] == "1.00"
    assert sum(1 for o in miet_check["je_objekt"] if o["abweichung"]) == 1
    # A tenancy on a unit of a pure WEG object is rejected, never created (M5-03).
    weg_row = "MV-X;100;01;" + dataset.tenant_ids[0] + ";01.01.2025;;100,00"
    rejected = _ok(
        client.post(
            BASE,
            params={"mode": "preview"},
            files=[
                (
                    "files",
                    (
                        "mietvertraege.csv",
                        (dataset.mietvertraege.splitlines()[0] + "\n" + weg_row + "\n").encode(),
                        "text/csv",
                    ),
                )
            ],
            data={"cutoff_date": CUTOFF, "kinds": ["mietvertraege"]},
            headers=h,
        )
    )
    assert rejected["vorschau"]["mietvertraege"] == {"invalid": 1}
    assert "WEG" in rejected["importe"]["vertraege"]["probleme"]["mietvertraege"][0]["grund"]

    # A renamed object and a relabelled unit: the reconciliation lists them, a re-import
    # with update_existing follows the file, afterwards zero differences again.
    assert dataset.objektdaten.count("100;Gladbacher Straße 3;") > 0
    assert dataset.objektdaten.startswith(OBJEKTDATEN_HEADER + "\n100;")
    changed = dataset.objektdaten.replace(
        "100;Gladbacher Straße 3;", "100;Gladbacher Straße 3a;"
    ).replace(";01;Stellplatz 1;EG;", ";01;Stellplatz 1 neu;EG;", 1)
    check = _ok(_run(client, h, dataset, "abgleich", objektdaten=changed))
    assert check["apply"] is False
    assert check["id"]
    assert _entity(check, "objekte")["abweichend"][0]["felder"][0]["feld"] == "name"
    assert _entity(check, "einheiten")["abweichend"][0]["felder"] == [
        {"feld": "label", "soll": "Stellplatz 1 neu", "ist": "Stellplatz 1"}
    ]
    assert check["differenzen"] == 2
    conflict = _ok(_run(client, h, dataset, "apply", objektdaten=changed))
    assert conflict["counts"]["objektdaten"]["property_conflict"] == 1
    assert conflict["differenzen"] == 2
    updated = _ok(_run(client, h, dataset, "apply", objektdaten=changed, update_existing="true"))
    assert sorted(u["feld"] for u in updated["aktualisiert"]) == ["label", "name"]
    assert updated["differenzen"] == 0
    assert _ok(client.get(overview, headers=h)) == after
    runs = _ok(client.get(BASE, headers=h))
    assert [r["status"] for r in runs] == [
        "applied",
        "applied",
        "reconciled",
        "reconciled",
        "applied",
        "applied",
    ]


def test_permissions_and_tenant_separation(
    client: TestClient, world: World, dataset: Dataset
) -> None:
    reader = bearer(login(client, world, "vireader"))
    assert _run(client, reader, dataset, "preview").status_code == 403
    assert (
        client.post(
            f"{BASE}/vorpruefung", files=_files(dataset), data={"kinds": KINDS}, headers=reader
        ).status_code
        == 403
    )
    admin = bearer(login(client, world, "viadmin"))
    runs = _ok(client.get(BASE, headers=admin))
    assert runs
    other = bearer(login(client, world, "vibadmin"))
    assert _ok(client.get(BASE, headers=other)) == []
    assert client.get(f"{BASE}/{runs[0]['id']}", headers=other).status_code == 404
    assert client.get(f"{BASE}/{runs[0]['id']}/pdf", headers=other).status_code == 404
