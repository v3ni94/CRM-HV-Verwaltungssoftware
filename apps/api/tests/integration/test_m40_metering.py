"""Messdienstleister module, stage 1 (master prompt Messdienstleister section 13, cases 1, 2,
3, 4, 5, 6, 8, 9 and 12). Artificial data only; the ``fake`` adapter is a mock, no sandbox or
production system of any provider is called (end to end checks with real access are not
executed, see docs/integrations/messdienstleister.md)."""

import asyncio
import io
import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.metering import tasks as metering_tasks
from mhvp.metering.tasks import run_sync_job_once
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, World, _settings, bearer, client, login

pytestmark = pytest.mark.integration
__all__ = ["client"]

SECRET = f"geheim-{RUN}-api-key"


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _problem(response: Any, status: int, code: str) -> Any:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["code"] == code, body
    return body


@pytest.fixture
def admin(client: TestClient, world: World) -> dict[str, str]:
    h = bearer(login(client, world, "admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"metering_module_enabled": True}, headers=h))
    return h


def _property(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    existing = _ok(client.get("/api/v1/properties", params={"search": number}, headers=h))
    for row in existing if isinstance(existing, list) else existing.get("items", []):
        if row.get("number") == number:
            if "building_id" not in row:
                buildings = _ok(client.get(f"/api/v1/properties/{row['id']}/buildings", headers=h))
                row["building_id"] = buildings[0]["id"]
            return row
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": number,
                "name": f"Messhaus {number}",
                "management_type": "rental",
                "street": "Zählerweg",
                "house_number": "1",
                "postal_code": "40789",
                "city": "Monheim am Rhein",
            },
            headers=h,
        ),
        201,
    )
    building = _ok(
        client.post(f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus"}, headers=h),
        201,
    )
    prop["building_id"] = building["id"]
    return prop


def _unit(client: TestClient, h: dict[str, str], prop: dict[str, Any], number: str) -> str:
    return _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": prop["building_id"],
                "number": number,
                "unit_type": "apartment",
                "floor": "1",
            },
            headers=h,
        ),
        201,
    )["id"]


def _connection(
    client: TestClient, h: dict[str, str], name: str, *, secrets: bool = True, **extra: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "display_name": name,
        "provider_code": "ista",
        "environment": "test",
        "customer_references": ["0000123"],
        "config": {"adapter": "fake"},
        "account_release": {"consumption": True, "billing_result": True},
    }
    if secrets:
        body["secrets"] = {"api_key": SECRET}
    body.update(extra)
    return _ok(client.post("/api/v1/metering/connections", json=body, headers=h), 201)


def _assign(
    client: TestClient, h: dict[str, str], conn: dict[str, Any], prop: dict[str, Any], **extra: Any
) -> Any:
    body = {
        "connection_id": conn["id"],
        "property_id": prop["id"],
        "external_number": "0004711",
        "service_scope": "heating",
        "valid_from": "2026-01-01",
    }
    body.update(extra)
    return client.post("/api/v1/metering/assignments", json=body, headers=h)


def test_module_switch_locks_writes(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "admin"))
    _ok(client.patch("/api/v1/tenant/settings", json={"metering_module_enabled": False}, headers=h))
    _problem(
        client.post(
            "/api/v1/metering/connections",
            json={"display_name": "x", "provider_code": "other"},
            headers=h,
        ),
        403,
        "MHVP-METR-0001",
    )
    # reading the catalogue stays possible
    providers = _ok(client.get("/api/v1/metering/providers", headers=h))
    codes = {p["code"] for p in providers}
    assert {"ista", "techem", "kalo", "brunata_minol", "brunata_metrona", "other"} <= codes
    ista = next(p for p in providers if p["code"] == "ista")
    assert "erneut prüfen" in ista["research_note"]
    assert all(f["adapter_implemented"] is False for f in ista["functions"])
    techem = next(p for p in providers if p["code"] == "techem")
    assert {f["documented_support"] for f in techem["functions"]} == {"documentation_required"}
    assert not any(f["documented_support"] == "no" for p in providers for f in p["functions"])


def test_case_1_2_9_connections_secrets_and_leading_zeros(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    a = _connection(client, admin, f"ista Konto A {RUN}")
    b = _connection(client, admin, f"ista Konto B {RUN}", customer_references=["0000999"])
    assert a["id"] != b["id"] and a["secret_names"] == ["api_key"]  # noqa: PT018
    assert SECRET not in json.dumps(a) and SECRET not in json.dumps(b)  # noqa: PT018
    listing = _ok(client.get("/api/v1/metering/connections", headers=admin))
    assert SECRET not in json.dumps(listing)
    assert {c["id"] for c in listing} >= {a["id"], b["id"]}
    p7 = _property(client, admin, "907")
    p8 = _property(client, admin, "908")
    row_a = _ok(_assign(client, admin, a, p7), 201)
    row_b = _ok(_assign(client, admin, b, p8, external_number="0004711"), 201)
    # same external number on two accounts of the same provider stays separate
    assert row_a["external_billing_unit_id"] != row_b["external_billing_unit_id"]
    assert row_a["property_number"] == "907" and row_a["external_number"] == "0004711"  # noqa: PT018
    export = client.get(
        "/api/v1/metering/assignments-export", params={"property_id": p7["id"]}, headers=admin
    )
    assert export.status_code == 200
    assert '"0004711"' in export.text and '"907"' in export.text  # noqa: PT018
    # secrets can be replaced but never read; replacing marks the test stale
    _ok(client.post(f"/api/v1/metering/connections/{a['id']}/test", headers=admin))
    replaced = _ok(
        client.put(
            f"/api/v1/metering/connections/{a['id']}/secrets",
            json={"secrets": {"api_key": "neu-" + SECRET}},
            headers=admin,
        )
    )
    assert replaced["test_stale"] is True and "neu-" not in json.dumps(replaced)  # noqa: PT018
    detail = _ok(client.get(f"/api/v1/metering/connections/{a['id']}", headers=admin))
    assert "api_key" in detail["secret_names"] and SECRET not in json.dumps(detail)  # noqa: PT018


def test_case_3_same_record_in_object_tab_and_central_view_with_versions(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    conn = _connection(client, admin, f"ista Zentral {RUN}")
    prop = _property(client, admin, "909")
    row = _ok(_assign(client, admin, conn, prop, external_number="0009001"), 201)
    by_property = _ok(
        client.get(
            "/api/v1/metering/assignments", params={"property_id": prop["id"]}, headers=admin
        )
    )
    central = client.get(
        "/api/v1/metering/assignments", params={"search": "0009001", "page_size": 10}, headers=admin
    )
    assert central.headers["X-Total-Count"] == "1"
    assert [r["id"] for r in by_property] == [row["id"]] == [r["id"] for r in central.json()]
    first = _ok(
        client.patch(
            f"/api/v1/metering/assignments/{row['id']}",
            json={
                "version": row["version"],
                "status": "confirmed",
                "verification_basis": "Abrechnung 2025 geprüft",
            },
            headers=admin,
        )
    )
    assert first["status"] == "confirmed" and first["version"] == row["version"] + 1  # noqa: PT018
    assert first["remote_confirmed"] is False  # local confirmation is not a remote check
    # a concurrent editor with the old version is refused, nothing is lost
    _problem(
        client.patch(
            f"/api/v1/metering/assignments/{row['id']}",
            json={"version": row["version"], "note": "verloren?"},
            headers=admin,
        ),
        409,
        "MHVP-METR-0003",
    )
    again = _ok(client.get(f"/api/v1/metering/assignments/{row['id']}", headers=admin))
    assert again["note"] is None and again["verification_basis"] == "Abrechnung 2025 geprüft"  # noqa: PT018


def test_case_4_multiple_units_conflicts_and_provider_change(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    ista = _connection(client, admin, f"ista Wechsel {RUN}")
    kalo = _ok(
        client.post(
            "/api/v1/metering/connections",
            json={
                "display_name": f"KALO neu {RUN}",
                "provider_code": "kalo",
                "environment": "test",
            },
            headers=admin,
        ),
        201,
    )
    prop = _property(client, admin, "910")
    heating = _ok(_assign(client, admin, ista, prop, external_number="0004711"), 201)
    water = _ok(
        _assign(client, admin, ista, prop, external_number="0004712", service_scope="cold_water"),
        201,
    )
    assert heating["external_billing_unit_id"] != water["external_billing_unit_id"]
    # same scope and overlapping period on the same property is refused
    _problem(
        _assign(client, admin, ista, prop, external_number="0004799", valid_from="2026-06-01"),
        409,
        "MHVP-METR-0002",
    )
    # cross property use of the same external unit needs explicit grouping
    other = _property(client, admin, "911")
    _problem(_assign(client, admin, ista, other, external_number="0004711"), 409, "MHVP-METR-0002")
    changed = _ok(
        client.post(
            f"/api/v1/metering/assignments/{heating['id']}/change-provider",
            json={
                "version": heating["version"],
                "change_date": "2027-01-01",
                "new_connection_id": kalo["id"],
                "new_external_number": "K-000077",
            },
            headers=admin,
        )
    )
    assert changed["previous"]["valid_to"] == "2026-12-31"
    assert changed["current"]["valid_from"] == "2027-01-01"
    assert changed["current"]["provider_code"] == "kalo"
    assert changed["current"]["external_number"] == "K-000077"
    listing = _ok(
        client.get(
            "/api/v1/metering/assignments", params={"property_id": prop["id"]}, headers=admin
        )
    )
    assert {r["id"] for r in listing} == {heating["id"], water["id"], changed["current"]["id"]}
    # the grouped case: same external unit on two properties with disjoint unit scopes
    group = str(uuid.uuid4())
    u1 = _unit(client, admin, prop, "01")
    u2 = _unit(client, admin, other, "01")
    _ok(
        _assign(
            client,
            admin,
            ista,
            prop,
            external_number="0005555",
            service_scope="smoke_detectors",
            group_id=group,
            unit_scope=[u1],
        ),
        201,
    )
    _ok(
        _assign(
            client,
            admin,
            ista,
            other,
            external_number="0005555",
            service_scope="smoke_detectors",
            group_id=group,
            unit_scope=[u2],
        ),
        201,
    )


def test_case_5_unit_assignment_versus_occupant_change_and_vacancy(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    conn = _connection(client, admin, f"ista Einheiten {RUN}")
    prop = _property(client, admin, "912")
    unit_id = _unit(client, admin, prop, "02")
    assignment = _ok(_assign(client, admin, conn, prop, external_number="0004720"), 201)
    base = f"/api/v1/metering/assignments/{assignment['id']}/units"
    ua = _ok(
        client.post(
            base,
            json={
                "unit_id": unit_id,
                "external_unit_number": "0001",
                "valid_from": "2026-01-01",
                "occupancy_status": "occupied",
            },
            headers=admin,
        ),
        201,
    )
    assert ua["external_unit_number"] == "0001" and ua["unit_number"] == "02"  # noqa: PT018
    # occupant change: only recipients and occupancy change, the mapping stays
    moved = _ok(
        client.patch(
            f"/api/v1/metering/unit-assignments/{ua['id']}",
            json={"version": ua["version"], "occupancy_status": "vacant"},
            headers=admin,
        )
    )
    assert moved["external_unit_number"] == "0001" and moved["unit_id"] == unit_id  # noqa: PT018
    assert moved["occupancy_status"] == "vacant"
    assert (
        client.patch(
            f"/api/v1/metering/unit-assignments/{ua['id']}",
            json={"version": moved["version"], "external_unit_number": "0002"},
            headers=admin,
        ).status_code
        == 422
    )
    # owner use and unclear remain distinct states, never collapsed into vacancy
    for status in ("owner_use", "unclear"):
        moved = _ok(
            client.patch(
                f"/api/v1/metering/unit-assignments/{ua['id']}",
                json={"version": moved["version"], "occupancy_status": status},
                headers=admin,
            )
        )
        assert moved["occupancy_status"] == status
    # the same unit cannot be mapped twice in the same period
    _problem(
        client.post(
            base,
            json={"unit_id": unit_id, "external_unit_number": "0009", "valid_from": "2026-03-01"},
            headers=admin,
        ),
        409,
        "MHVP-METR-0002",
    )
    assert len(_ok(client.get(base, headers=admin))) == 1


def test_case_6_and_12_sync_clearing_and_read_only_test(
    client: TestClient,
    world: World,
    admin: dict[str, str],
    database: Database,
    redis_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No broker in this run: the queued job is executed explicitly below (worker body).
    monkeypatch.setattr(metering_tasks.run_sync_job_task, "delay", lambda *args: None)
    prop = _property(client, admin, "913")
    unit_id = _unit(client, admin, prop, "03")
    records = [
        {
            "external_billing_unit": "0004730",
            "external_unit_number": "0001",
            "period_from": "2026-01-01",
            "period_to": "2026-01-31",
            "kind": "heating",
            "unit_of_measure": "kWh",
            "value": "12.5",
        },
        {
            "external_billing_unit": "0004730",
            "external_unit_number": "0001",
            "period_from": "2026-02-01",
            "period_to": "2026-02-28",
            "kind": "heating",
            "unit_of_measure": "kWh",
            "value": None,
            "value_kind": "missing",
        },
        {
            "external_billing_unit": "0009999",
            "external_unit_number": None,
            "period_from": "2026-01-01",
            "period_to": "2026-01-31",
            "kind": "heating",
            "unit_of_measure": "kWh",
            "value": "1",
        },
        {
            "type": "billing_result",
            "external_billing_unit": "0004730",
            "external_unit_number": "0001",
            "period_from": "2026-01-01",
            "period_to": "2026-12-31",
            "amount": "1234.56",
            "external_document_ref": "DOC-1",
        },
    ]
    conn = _connection(
        client, admin, f"ista Abruf {RUN}", config={"adapter": "fake", "fake_records": records}
    )
    # case 12: without a successful test no fetch is available; a missing credential never succeeds
    bare = _connection(client, admin, f"ista ohne Zugang {RUN}", secrets=False)
    test = _ok(client.post(f"/api/v1/metering/connections/{bare['id']}/test", headers=admin))
    assert test["outcome"] == "credentials_missing" and test["functions_released"] == []  # noqa: PT018
    caps = {c["function"]: c for c in test["connection"]["capabilities"]}
    assert caps["consumption"]["available"] is False
    _problem(
        client.post(
            "/api/v1/metering/sync-jobs",
            json={"connection_id": bare["id"], "data_kind": "consumption"},
            headers=admin,
        ),
        409,
        "MHVP-METR-0004",
    )
    # a connection test orders nothing: no job, no billing result, no data
    test = _ok(client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=admin))
    assert test["outcome"] == "ok" and "Objektzugriff" in test["detail"]  # noqa: PT018
    caps = {c["function"]: c for c in test["connection"]["capabilities"]}
    assert caps["consumption"]["available"] is True
    assert caps["billing_input"]["available"] is False  # writing functions stay off
    assert caps["roles"]["available"] is False
    assert (
        client.post(
            "/api/v1/metering/sync-jobs",
            json={"connection_id": conn["id"], "data_kind": "billing_input"},
            headers=admin,
        ).status_code
        == 422
    )
    jobs = client.get(
        "/api/v1/metering/sync-jobs", params={"connection_id": conn["id"]}, headers=admin
    )
    assert jobs.headers["X-Total-Count"] == "0"
    assignment = _ok(_assign(client, admin, conn, prop, external_number="0004730"), 201)
    _ok(
        client.post(
            f"/api/v1/metering/assignments/{assignment['id']}/units",
            json={"unit_id": unit_id, "external_unit_number": "0001", "valid_from": "2026-01-01"},
            headers=admin,
        ),
        201,
    )
    job = _ok(
        client.post(
            "/api/v1/metering/sync-jobs",
            json={
                "connection_id": conn["id"],
                "data_kind": "consumption",
                "property_ids": [prop["id"]],
            },
            headers=admin,
        ),
        202,
    )
    assert job["status"] == "queued"
    # double click: the same job is not queued twice
    _problem(
        client.post(
            "/api/v1/metering/sync-jobs",
            json={
                "connection_id": conn["id"],
                "data_kind": "consumption",
                "property_ids": [prop["id"]],
            },
            headers=admin,
        ),
        409,
        "MHVP-METR-0008",
    )
    settings = _settings(database, redis_url)
    status = asyncio.run(run_sync_job_once(settings, world.tenant_a, uuid.UUID(job["id"])))
    assert status == "succeeded"
    done = _ok(client.get(f"/api/v1/metering/sync-jobs/{job['id']}", headers=admin))
    assert done["status"] == "succeeded" and [p["part"] for p in done["parts"]] == [  # noqa: PT018
        "fetch",
        "store",
        "clearing",
    ]
    values = _ok(
        client.get(f"/api/v1/metering/assignments/{assignment['id']}/consumption", headers=admin)
    )
    by_period = {v["period_from"]: v for v in values}
    assert (  # noqa: PT018
        by_period["2026-01-01"]["value"] == "12.50000000"
        and by_period["2026-01-01"]["value_kind"] == "actual"
    )
    assert (  # noqa: PT018
        by_period["2026-02-01"]["value"] is None
        and by_period["2026-02-01"]["value_kind"] == "missing"
    )
    clearing = _ok(
        client.get(
            "/api/v1/metering/clearing-items", params={"connection_id": conn["id"]}, headers=admin
        )
    )
    assert [c["external_identifier"] for c in clearing] == ["0009999"]
    # re-run: identical values are not stored twice
    job2 = _ok(
        client.post(
            "/api/v1/metering/sync-jobs",
            json={
                "connection_id": conn["id"],
                "data_kind": "consumption",
                "property_ids": [prop["id"]],
            },
            headers=admin,
        ),
        202,
    )
    asyncio.run(run_sync_job_once(settings, world.tenant_a, uuid.UUID(job2["id"])))
    assert (
        len(
            _ok(
                client.get(
                    f"/api/v1/metering/assignments/{assignment['id']}/consumption", headers=admin
                )
            )
        )
        == 2
    )
    # billing results arrive as reviewable data with exact decimals and no posting
    job3 = _ok(
        client.post(
            "/api/v1/metering/sync-jobs",
            json={
                "connection_id": conn["id"],
                "data_kind": "billing_result",
                "property_ids": [prop["id"]],
            },
            headers=admin,
        ),
        202,
    )
    asyncio.run(run_sync_job_once(settings, world.tenant_a, uuid.UUID(job3["id"])))
    results = _ok(
        client.get(
            f"/api/v1/metering/assignments/{assignment['id']}/billing-results", headers=admin
        )
    )
    assert (  # noqa: PT018
        len(results) == 1
        and results[0]["amount"] == "1234.56"
        and results[0]["review_status"] == "imported"
    )
    connection = _ok(client.get(f"/api/v1/metering/connections/{conn['id']}", headers=admin))
    assert set(connection["last_sync"]) == {"consumption", "billing_result"}
    # resolving a clearing item records the decision only
    resolved = _ok(
        client.post(
            f"/api/v1/metering/clearing-items/{clearing[0]['id']}/resolve",
            json={"status": "dismissed", "note": "Fremde Liegenschaft"},
            headers=admin,
        )
    )
    assert resolved["status"] == "dismissed"
    # a conflict on an assignment blocks every fetch of that scope
    current = _ok(client.get(f"/api/v1/metering/assignments/{assignment['id']}", headers=admin))
    _ok(
        client.patch(
            f"/api/v1/metering/assignments/{assignment['id']}",
            json={"version": current["version"], "status": "conflict"},
            headers=admin,
        )
    )
    _problem(
        client.post(
            "/api/v1/metering/sync-jobs",
            json={
                "connection_id": conn["id"],
                "data_kind": "consumption",
                "property_ids": [prop["id"]],
            },
            headers=admin,
        ),
        409,
        "MHVP-METR-0006",
    )


def test_case_8_9_tenant_permission_and_environment_boundaries(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    conn = _connection(client, admin, f"ista Grenzen {RUN}")
    prop = _property(client, admin, "914")
    assignment = _ok(_assign(client, admin, conn, prop, external_number="0004740"), 201)
    other_tenant = bearer(login(client, world, "both", tenant_id=world.tenant_b))
    assert (
        client.get(f"/api/v1/metering/connections/{conn['id']}", headers=other_tenant).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/metering/assignments/{assignment['id']}", headers=other_tenant
        ).status_code
        == 404
    )
    assert conn["id"] not in {
        c["id"] for c in _ok(client.get("/api/v1/metering/connections", headers=other_tenant))
    }
    reader = bearer(login(client, world, "reader"))
    assert (
        client.get(f"/api/v1/metering/connections/{conn['id']}", headers=reader).status_code == 200
    )
    assert (
        client.post(
            "/api/v1/metering/connections",
            json={"display_name": "x", "provider_code": "other"},
            headers=reader,
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/v1/metering/connections/{conn['id']}/test", headers=reader).status_code
        == 403
    )
    assert _assign(client, reader, conn, prop, external_number="0004741").status_code == 403
    assert (
        client.post(
            "/api/v1/metering/sync-jobs",
            json={"connection_id": conn["id"], "data_kind": "consumption"},
            headers=reader,
        ).status_code
        == 403
    )
    # production never runs against the fake adapter (test and production stay apart)
    prod = _connection(client, admin, f"ista Produktion {RUN}", environment="production")
    test = _ok(client.post(f"/api/v1/metering/connections/{prod['id']}/test", headers=admin))
    assert test["outcome"] == "not_implemented"
    assert SECRET not in json.dumps(test)


def test_csv_import_preview_apply_and_duplicates(
    client: TestClient, world: World, admin: dict[str, str]
) -> None:
    name = f"ista Import {RUN}"
    conn = _connection(client, admin, name)
    prop = _property(client, admin, "915")
    template = client.get("/api/v1/metering/assignments-import/template", headers=admin)
    assert template.status_code == 200 and template.text.startswith("property_number;")  # noqa: PT018
    csv_text = (
        "property_number;connection_name;external_number;service_scope;valid_from;valid_to\r\n"
        f"915;{name};0004750;heating;01.01.2026;\r\n"
        f"915;{name};0004750;heating;01.01.2026;\r\n"
        f"999;{name};=1+1;heating;2026-01-01;\r\n"
    )
    files = {"file": ("zuordnungen.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    preview = _ok(
        client.post("/api/v1/metering/assignments-import/preview", files=files, headers=admin)
    )
    assert (preview["ok_count"], preview["duplicate_count"], preview["error_count"]) == (1, 1, 1)
    assert preview["rows"][1]["messages"] == ["Doppelte Zeile in der Datei."]
    # the preview stored nothing
    assert (
        client.get(
            "/api/v1/metering/assignments", params={"property_id": prop["id"]}, headers=admin
        ).headers["X-Total-Count"]
        == "0"
    )
    files = {"file": ("zuordnungen.csv", io.BytesIO(csv_text.encode()), "text/csv")}
    _problem(
        client.post("/api/v1/metering/assignments-import/apply", files=files, headers=admin),
        422,
        "MHVP-METR-0007",
    )
    good = "\r\n".join(csv_text.split("\r\n")[:3]) + "\r\n"
    files = {"file": ("zuordnungen.csv", io.BytesIO(good.encode()), "text/csv")}
    applied = _ok(
        client.post("/api/v1/metering/assignments-import/apply", files=files, headers=admin)
    )
    assert len(applied["created_ids"]) == 1 and applied["duplicate_count"] == 1  # noqa: PT018
    listing = _ok(
        client.get(
            "/api/v1/metering/assignments", params={"property_id": prop["id"]}, headers=admin
        )
    )
    assert listing[0]["external_number"] == "0004750" and listing[0]["origin"] == "import"  # noqa: PT018
    files = {"file": ("zuordnungen.csv", io.BytesIO(good.encode()), "text/csv")}
    again = _ok(
        client.post("/api/v1/metering/assignments-import/apply", files=files, headers=admin)
    )
    assert again["created_ids"] == [] and again["duplicate_count"] == 2  # noqa: PT018
    export = client.get(
        "/api/v1/metering/assignments-export", params={"property_id": prop["id"]}, headers=admin
    )
    assert '"0004750"' in export.text and "=1+1" not in export.text  # noqa: PT018
    assert conn["id"]
