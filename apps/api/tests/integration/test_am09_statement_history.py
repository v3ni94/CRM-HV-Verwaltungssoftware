"""AM09 (GAJ-501, GAJ-502): historical statements and resolutions are filed and checked, the
reconciliation report carries master data counters. Synthetic exports; column headers are
invented for the test and say nothing about real Immoware24 exports (AM09-01 open).
Expected figures are fixed in the comments (rule 0.1.8)."""

import asyncio
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
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m8_import import BASE, BUCKET, XLSX, _settings, _stage, _xlsx
from tests.integration.test_m10_ledger import _prop
from tests.integration.test_q08_import_history import _map, _ok

pytestmark = pytest.mark.integration
HIST = f"{BASE}/history"
RECON = "/api/v1/imports/reconciliation-reports"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"9am09-{RUN}", name=f"AM09 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"9am09b-{RUN}", name=f"AM09b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "am09admin": (a, "tenant_admin"),
            "am09reader": (a, "read_only"),
            "am09other": (b, "tenant_admin"),
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


S_COLS = {
    "property_number": "Objekt",
    "kind": "Art",
    "period_start": "Von",
    "period_end": "Bis",
    "version": "Version",
    "unit_number": "Einheit",
    "result_amount": "Ergebnis",
    "resolution_ref": "Beschluss",
}
S_HEAD = ["Objekt", "Art", "Von", "Bis", "Version", "Einheit", "Ergebnis", "Beschluss"]
R_COLS = {
    "property_number": "Objekt",
    "resolved_on": "Datum",
    "item_number": "TOP",
    "title": "Gegenstand",
    "reference": "Nr",
    "result": "Ergebnis",
}
R_HEAD = ["Objekt", "Datum", "TOP", "Gegenstand", "Nr", "Ergebnis"]
KINDS = {"JA": "hoa_annual", "WP": "hoa_budget"}


def test_am09_fields_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "am09admin"))
    fields = _ok(client.get(f"{BASE}/fields", headers=h))
    req = {rt: {f["name"] for f in fields[rt] if f["required"]} for rt in fields}
    assert req["historical_statement"] == {"property_number", "kind", "period_start", "period_end"}
    assert req["resolution"] == {"property_number", "resolved_on", "item_number", "title"}
    reader = bearer(login(client, world, "am09reader"))
    # Unknown query parameter and unknown kind are 422; the read only role may read.
    assert client.get(f"{HIST}/statements?foo=1", headers=h).status_code == 422
    assert client.get(f"{HIST}/statements?kind=x", headers=h).status_code == 422
    assert client.get(f"{HIST}/statements", headers=reader).status_code == 200


def test_am09_statements_resolutions_check_and_reconciliation(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "am09admin"))
    other = bearer(login(client, world, "am09other"))
    prop = _prop(client, h, "893", "hoa")
    _unit(client, h, prop["id"], "01")

    # Beschluesse: TOP 3 vom 15.05.2025 Nr B-2025-3 (created), unknown object 999 (invalid).
    res_rows = [
        R_HEAD,
        ["893", "15.05.2025", "3", "Jahresabrechnung 2024", "B-2025-3", "A"],
        ["999", "15.05.2025", "4", "X", "", "A"],
    ]
    res = _import(client, h, "resolution", res_rows, R_COLS, result={"A": "accepted"})
    assert res["counts"] == {"created": 1, "invalid": 1}
    again = _import(
        client, h, "resolution", res_rows[:2], R_COLS, name="r2.xlsx", result={"A": "accepted"}
    )
    assert again["counts"] == {"unchanged": 1}
    changed = [R_HEAD, ["893", "15.05.2025", "3", "Anderer Titel", "B-2025-3", "A"]]
    conflict = _import(
        client, h, "resolution", changed, R_COLS, name="r3.xlsx", result={"A": "accepted"}
    )
    assert conflict["counts"] == {"conflict": 1}

    # Abrechnungen 2024: unit 01 version 1 (+123,45, ref B-2025-3), version 2 (+100,00, same ref),
    # unit 07 unknown on the platform (created with hint, ref missing), budget without ref,
    # period reversed (invalid). Expected findings: resolution_missing 1 (B-9), unit_unknown 1,
    # resolution_ref_empty 1 (WP), several_versions 1 => 4.
    st_rows = [
        S_HEAD,
        ["893", "JA", "01.01.2024", "31.12.2024", "1", "01", "123,45", "B-2025-3"],
        ["893", "JA", "01.01.2024", "31.12.2024", "2", "01", "100,00", "B-2025-3"],
        ["893", "JA", "01.01.2024", "31.12.2024", "1", "07", "-5,00", "B-9"],
        ["893", "WP", "01.01.2025", "31.12.2025", "", "", "", ""],
        ["893", "JA", "01.01.2024", "31.12.2023", "1", "", "", ""],
    ]
    st = _import(client, h, "historical_statement", st_rows, S_COLS, kind=KINDS)
    assert st["counts"] == {"created": 4, "invalid": 1}
    st2 = _import(
        client, h, "historical_statement", st_rows[:2], S_COLS, name="s2.xlsx", kind=KINDS
    )
    assert st2["counts"] == {"unchanged": 1}

    listed = _ok(client.get(f"{HIST}/statements?property_id={prop['id']}", headers=h))
    assert len(listed) == 4
    assert {s["result_amount"] for s in listed} == {"123.45", "100.00", "-5.00", None}
    assert len(_ok(client.get(f"{HIST}/resolutions", headers=h))) == 1
    assert _ok(client.get(f"{HIST}/statements", headers=other)) == []  # RLS

    check = _ok(client.get(f"{HIST}/statements/check?property_id={prop['id']}", headers=h))
    codes = sorted(f["code"] for f in check["findings"])
    assert codes == [
        "resolution_missing",
        "resolution_ref_empty",
        "several_versions",
        "unit_unknown",
    ]
    assert check["totals"] == {"statements": 4, "resolutions": 1, "findings": 4}
    other_check = _ok(client.get(f"{HIST}/statements/check", headers=other))
    assert other_check["totals"] == {"statements": 0, "resolutions": 0, "findings": 0}

    # GAJ-502: the report runs without journal or bank rows and counts master data per type.
    report = _ok(client.post(RECON, json={}, headers=h), 201)
    full = _ok(client.get(f"{RECON}/{report['id']}", headers=h))
    md = full["master_data"]
    types = {t["report_type"]: t for t in md["types"]}
    # Newest statement file s2: 1 unchanged row, nothing open. Newest resolution file r3: conflict.
    assert types["historical_statement"]["open_rows"] == 0
    assert types["resolution"]["open_rows"] == 1
    assert types["resolution"]["deviates"]
    assert md["platform"]["properties"] == 1
    assert md["platform"]["units"] == 1
    assert full["totals"]["master_data_open"] == md["open_differences"] >= 1

    # Undo removes the filed rows of the first statement run (nothing references them).
    _ok(client.post(f"/api/v1/imports/{st['run_id']}/undo", headers=h))
    assert _ok(client.get(f"{HIST}/statements", headers=h)) == []
