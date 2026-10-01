"""Package T10 (M8-01, wave 5) with synthetic exports: deposits, allocation keys with unit
values, meters, energy certificates, service providers and portal user status. Expected figures
are fixed in the comments (rule 0.1.8). Column headers are invented for the test and make no
statement about real Immoware24 exports (M8-01 stays open for them)."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BASE, BUCKET, XLSX, _settings, _stage, _xlsx
from tests.integration.test_m10_ledger import _prop
from tests.integration.test_q08_import_history import _map, _ok

pytestmark = pytest.mark.integration
NEW_TYPES = ("deposit", "allocation_key", "meter", "energy_certificate", "service_provider")


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"t10-{RUN}", name=f"T10 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"t10b-{RUN}", name=f"T10b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "t10admin": (a, "tenant_admin"),
            "t10reader": (a, "read_only"),
            "t10other": (b, "tenant_admin"),
        }
        for name, (tenant, role) in specs.items():
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _external(c: TestClient, h: dict[str, str], contact_id: str, external: str) -> None:
    _ok(
        c.patch(
            f"/api/v1/contacts/{contact_id}",
            json={"external_ids": {"immoware24": external}},
            headers=h,
        )
    )


def _import(
    c: TestClient,
    h: dict[str, str],
    report: str,
    rows: list[list[Any]],
    columns: dict[str, str],
    *,
    name: str = "export.xlsx",
    **maps: Any,
) -> dict[str, Any]:
    source = _stage(c, h, report, name, _xlsx(rows), XLSX)
    mapping = _map(c, h, report, columns, **maps)
    _ok(
        c.post(
            f"{BASE}/files/{source['id']}/validate", json={"mapping_id": mapping["id"]}, headers=h
        )
    )
    dry = _ok(c.post(f"{BASE}/files/{source['id']}/test-run", headers=h))
    applied = _ok(c.post(f"{BASE}/files/{source['id']}/apply", headers=h), 201)
    assert dry["counts"] == applied["report"]["apply"]["counts"]
    out: dict[str, Any] = applied["report"]["apply"]
    out["run_id"] = applied["report"].get("import_run_id") or applied.get("import_run_id")
    return out


def _cols(**names: str) -> dict[str, str]:
    return dict(names)


def test_w5_fields_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "t10admin"))
    reader = bearer(login(client, world, "t10reader"))
    fields = _ok(client.get(f"{BASE}/fields", headers=h))
    required = {
        rt: {f["name"] for f in fields[rt] if f["required"]} for rt in (*NEW_TYPES, "portal_user")
    }
    assert required["deposit"] == {
        "property_number",
        "unit_number",
        "contact_external_id",
        "kind",
        "amount_due",
        "valid_from",
    }
    assert required["allocation_key"] == {"property_number", "code"}
    assert required["meter"] == {"property_number", "meter_type_code", "number", "valid_from"}
    assert required["energy_certificate"] == {"property_number", "valid_until", "issued_on"}
    assert required["portal_user"] == {"contact_external_id", "portal_status"}
    # Leserecht: apply and mapping are forbidden (403), unknown file 404.
    assert client.post(f"{BASE}/files/{uuid.uuid4()}/apply", headers=reader).status_code == 403
    other = bearer(login(client, world, "t10other"))
    assert client.post(f"{BASE}/files/{uuid.uuid4()}/apply", headers=other).status_code == 404


def test_w5_reports(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "t10admin"))
    other = bearer(login(client, world, "t10other"))
    prop = _prop(client, h, "891", "rental")
    unit = _unit(client, h, prop["id"], "01")
    tenant_party, tenant_contact = _party(client, h, "Mieter")
    _external(client, h, tenant_contact["id"], "K891")
    _, provider_contact = _party(client, h, "Hausdienst", "company")
    _external(client, h, provider_contact["id"], "K891D")
    owner, _ = _party(client, h, "Eigentuemer", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": tenant_party,
                "start_date": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )

    # Kautionen: K1 Barkaution 1.500,00 ab 01.01.2026 (created), same again (unchanged),
    # another amount for the same start (conflict), unknown unit 99 (invalid).
    d_cols = _cols(
        property_number="Objekt",
        unit_number="Einheit",
        contact_external_id="Mieter",
        kind="Art",
        amount_due="Betrag",
        valid_from="Ab",
    )
    head = ["Objekt", "Einheit", "Mieter", "Art", "Betrag", "Ab"]
    rows = [
        head,
        ["891", "01", "K891", "B", "1.500,00", "01.01.2026"],
        ["891", "99", "K891", "B", "100,00", "01.01.2026"],
    ]
    dep = _import(client, h, "deposit", rows, d_cols, kind={"B": "cash"})
    assert dep["counts"] == {"created": 1, "invalid": 1}
    assert dep["sums"]["created_amount"] == "1500.00"
    again = _import(client, h, "deposit", rows[:2], d_cols, name="again.xlsx", kind={"B": "cash"})
    assert again["counts"] == {"unchanged": 1}
    changed = [head, ["891", "01", "K891", "B", "1.200,00", "01.01.2026"]]
    conflict = _import(client, h, "deposit", changed, d_cols, name="c.xlsx", kind={"B": "cash"})
    assert conflict["counts"] == {"conflict": 1}
    contract_id = _ok(client.get("/api/v1/contracts", headers=h))
    contract_id = next(c["id"] for c in contract_id if c["unit_id"] == unit)
    deposits = _ok(client.get(f"/api/v1/contracts/{contract_id}/deposits", headers=h))
    assert [d["amount_due"] for d in deposits] == ["1500.00"]  # never overwritten

    # Umlageschluessel: new key ZK (m2 style) with value 62,5 for unit 01 from 01.01.2026,
    # repeated (unchanged), other value same period (conflict), value without date (invalid).
    k_cols = _cols(
        property_number="Objekt",
        code="Kürzel",
        name="Name",
        unit_of_measure="ME",
        kind="Art",
        unit_number="Einheit",
        value="Wert",
        valid_from="Ab",
    )
    k_head = ["Objekt", "Kürzel", "Name", "ME", "Art", "Einheit", "Wert", "Ab"]
    k_rows = [k_head, ["891", "ZK", "Zusatzschlüssel", "m2", "S", "01", "62,5", "01.01.2026"]]
    key_run = _import(client, h, "allocation_key", k_rows, k_cols, kind={"S": "static"})
    assert key_run["counts"] == {"created": 1}
    key_again = _import(
        client, h, "allocation_key", k_rows, k_cols, name="a.xlsx", kind={"S": "static"}
    )
    assert key_again["counts"] == {"unchanged": 1}
    k_other = [k_head, ["891", "ZK", "Zusatzschlüssel", "m2", "S", "01", "70", "01.01.2026"]]
    key_conflict = _import(
        client, h, "allocation_key", k_other, k_cols, name="b.xlsx", kind={"S": "static"}
    )
    assert key_conflict["counts"] == {"conflict": 1}
    summary = _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    assert "ZK" in {k["code"] for k in summary}

    # Zaehler: Kaltwasser 4711 an Einheit 01 mit Anfangsstand 12,5; Wiederholung unchanged;
    # unbekannte Zählerart (invalid).
    m_cols = _cols(
        property_number="Objekt",
        meter_type_code="Zählerart",
        number="Nummer",
        valid_from="Ab",
        unit_number="Einheit",
        reading_date="Datum",
        reading_value="Stand",
    )
    m_head = ["Objekt", "Zählerart", "Nummer", "Ab", "Einheit", "Datum", "Stand"]
    m_rows = [
        m_head,
        ["891", "cold_water", "4711", "01.01.2026", "01", "01.01.2026", "12,5"],
        ["891", "gibt_es_nicht", "4712", "01.01.2026", "01", None, None],
    ]
    meter_run = _import(client, h, "meter", m_rows, m_cols)
    assert meter_run["counts"] == {"created": 1, "invalid": 1}
    meter_again = _import(client, h, "meter", m_rows[:2], m_cols, name="m2.xlsx")
    assert meter_again["counts"] == {"unchanged": 1}
    meters = _ok(client.get(f"/api/v1/properties/{prop['id']}/meters", headers=h))
    assert [m["number"] for m in meters] == ["4711"]
    readings = _ok(client.get(f"/api/v1/meters/{meters[0]['id']}/readings", headers=h))
    assert len(readings) == 1
    assert float(readings[0]["value"]) == 12.5

    # Energieausweis: fills the empty certificate; same again unchanged; other class conflict.
    e_cols = _cols(
        property_number="Objekt",
        valid_until="Bis",
        issued_on="Von",
        energy_class="Klasse",
        building="Haus",
    )
    e_head = ["Objekt", "Bis", "Von", "Klasse", "Haus"]
    e_rows = [e_head, ["891", "30.06.2035", "01.07.2025", "c", "Haus"]]
    cert = _import(client, h, "energy_certificate", e_rows, e_cols)
    assert cert["counts"] == {"created": 1}
    cert_again = _import(client, h, "energy_certificate", e_rows, e_cols, name="e2.xlsx")
    assert cert_again["counts"] == {"unchanged": 1}
    e_other = [e_head, ["891", "30.06.2035", "01.07.2025", "D", "Haus"]]
    cert_conflict = _import(client, h, "energy_certificate", e_other, e_cols, name="e3.xlsx")
    assert cert_conflict["counts"] == {"conflict": 1}
    # Undo of the filling run is refused once the certificate was edited afterwards; here it
    # is untouched, so undo clears it again.
    _ok(client.post(f"/api/v1/imports/{cert['run_id']}/undo", headers=h))
    redo = _import(client, h, "energy_certificate", e_rows, e_cols, name="e4.xlsx")
    assert redo["counts"] == {"created": 1}

    # Dienstleister: Hausmeister ab 01.01.2026; Wiederholung unchanged; unbekannter Kontakt invalid.
    s_cols = _cols(
        property_number="Objekt",
        contact_external_id="Kontakt",
        contract_type_code="Art",
        valid_from="Ab",
        customer_number="KdNr",
    )
    s_head = ["Objekt", "Kontakt", "Art", "Ab", "KdNr"]
    s_rows = [
        s_head,
        ["891", "K891D", "caretaker", "01.01.2026", "K-77"],
        ["891", "KXXX", "caretaker", "01.01.2026", None],
    ]
    prov = _import(client, h, "service_provider", s_rows, s_cols)
    assert prov["counts"] == {"created": 1, "invalid": 1}
    prov_again = _import(client, h, "service_provider", s_rows[:2], s_cols, name="s2.xlsx")
    assert prov_again["counts"] == {"unchanged": 1}
    providers = _ok(client.get(f"/api/v1/properties/{prop['id']}/service-providers", headers=h))
    assert [p["customer_number"] for p in providers] == ["K-77"]
    _ok(client.post(f"/api/v1/imports/{prov['run_id']}/undo", headers=h))
    assert _ok(client.get(f"/api/v1/properties/{prop['id']}/service-providers", headers=h)) == []

    # Portalnutzer: no portal account exists -> staged_only with note, nothing is created.
    p_cols = _cols(contact_external_id="Kontakt", portal_status="Status")
    p_rows = [["Kontakt", "Status"], ["K891", "aktiv"]]
    portal = _import(client, h, "portal_user", p_rows, p_cols, portal_status={"aktiv": "active"})
    assert portal["counts"] == {"staged_only": 1}

    # Undo of the key run removes value first, then key (no leftovers).
    _ok(client.post(f"/api/v1/imports/{key_run['run_id']}/undo", headers=h))
    summary = _ok(client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h))
    assert "ZK" not in {k["code"] for k in summary}

    # Mandantentrennung: the other tenant sees no staging file of this tenant.
    source = _stage(client, other, "deposit", "x.xlsx", _xlsx([["A"], ["1"]]), XLSX)
    assert client.get(f"{BASE}/files/{source['id']}", headers=h).status_code == 404
