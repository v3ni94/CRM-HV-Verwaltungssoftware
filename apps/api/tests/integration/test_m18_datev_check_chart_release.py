"""M18-01 DATEV self check and M10-01/M10-02 chart of accounts release (V8, gate G1).

Export runs keep their file and can be checked; the stored report lists findings; the sample
batch downloads and passes the check. Templates move draft -> in_review -> released with
comment, a released version is immutable and a change creates a new version, gate G1 is not
approved without a released template, and nothing crosses tenants."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m18_datev_mapping import _ledger_with_postings

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
D = f"{A}/datev"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"dc-{RUN}", name=f"Check {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"dcf-{RUN}", name=f"Fremd2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("dcadmin", a, "tenant_admin"),
            ("dcacc", a, "accountant_no_banking"),
            ("dcreader", a, "read_only"),
            ("ddcadmin", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        for name in ("dcpadmin", "dcpadmin2"):
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=True,
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def test_datev_export_check_report_and_sample(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "dcadmin"))
    acc = bearer(login(client, world, "dcacc"))
    ledger, _ = _ledger_with_postings(client, h, acc)
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={
                "datev_consultant_number": "12345",
                "datev_client_number": "6789",
                "datev_chart_of_accounts": "skr03",
                "datev_account_length": 4,
            },
            headers=h,
        )
    )
    csv_text = "Konto;DATEV-Konto\r\n009000;9000\r\n001200;1200\r\n001201;1250\r\n"
    _ok(
        client.post(
            f"{A}/datev-mappings/import", json={"content": csv_text, "dry_run": False}, headers=h
        )
    )
    export = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/exports/datev",
            params={"start": "2026-01-01", "end": "2026-12-31"},
            headers=h,
        ),
        201,
    )
    runs = _ok(client.get(f"{D}/exports", headers=h))
    assert [r["id"] for r in runs] == [export["id"]]
    assert runs[0]["has_content"] is True
    assert runs[0]["check_status"] is None

    # No report yet.
    assert client.get(f"{D}/exports/{export['id']}/check", headers=h).status_code == 404
    checked = _ok(client.post(f"{D}/exports/{export['id']}/check", headers=h))
    report = checked["report"]
    # Konto/Gegenkonto pairs per booking (docs/rules/M18-06): three line opening balance
    # gives two rows, the two line fee one row.
    assert report["booking_rows"] == 3
    assert report["status"] in {"formal_ok", "mit_hinweisen", "fehlerhaft"}
    # Every row carries a Gegenkonto, so DC-14 must not fire on regular pairs (M18-06).
    assert not any(f["rule"] == "DC-14" for f in report["findings"])
    assert "Prüfbericht" in checked["text"]
    stored = _ok(client.get(f"{D}/exports/{export['id']}/check", headers=h))
    assert stored["report"]["findings"] == report["findings"]
    assert stored["checked_at"] is not None
    text = client.get(f"{D}/exports/{export['id']}/check", params={"format": "text"}, headers=h)
    assert text.status_code == 200
    assert text.text.startswith("Prüfbericht")
    download = client.get(f"{D}/exports/{export['id']}/download", headers=h)
    assert download.status_code == 200
    assert download.text.startswith('"EXTF";"700";"21";"Buchungsstapel";"7"')
    assert _ok(client.get(f"{D}/exports", headers=h))[0]["check_status"] == report["status"]

    # Ad hoc check of a broken file: every finding carries rule, line and source status.
    broken = download.text.replace('"EXTF"', '"DTVF"', 1)
    adhoc = _ok(client.post(f"{D}/check-file", json={"content": broken}, headers=h))
    assert any(f["rule"] == "DC-01" and f["line"] == 1 for f in adhoc["report"]["findings"])
    assert all(f["source"] in {"belegt", "zu_pruefen"} for f in adhoc["report"]["findings"])

    # Sample batch for the tax advisor: 20 fictional rows, no documented rule fails.
    sample = client.get(f"{D}/sample-batch", headers=h)
    assert sample.status_code == 200
    assert sample.headers["content-disposition"].endswith("EXTF_Buchungsstapel_Importtest.csv")
    assert sample.text.count("\r\n") == 22
    assert '"12345";"6789"' in sample.text.split("\r\n")[0]
    sample_check = _ok(client.get(f"{D}/sample-batch", params={"format": "check"}, headers=h))
    assert sample_check["report"]["errors"] == 0
    assert sample_check["report"]["booking_rows"] == 20

    # Permissions and tenant separation: read_only cannot check, other tenant sees nothing.
    reader = bearer(login(client, world, "dcreader"))
    assert client.post(f"{D}/exports/{export['id']}/check", headers=reader).status_code == 403
    assert client.get(f"{D}/sample-batch", headers=reader).status_code == 200
    other = bearer(login(client, world, "ddcadmin"))
    assert _ok(client.get(f"{D}/exports", headers=other)) == []
    assert client.post(f"{D}/exports/{export['id']}/check", headers=other).status_code == 404
    assert client.get(f"{D}/exports/{export['id']}/download", headers=other).status_code == 404


def test_chart_release_workflow_versions_gate_and_tenants(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "dcadmin"))
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    tid = template["id"]
    assert template["status"] == "draft"
    assert template["released"] is False

    # Gate G1 is not approved without a released chart of accounts (V8).
    padmin = bearer(login(client, world, "dcpadmin"))
    padmin2 = bearer(login(client, world, "dcpadmin2"))
    requested = _ok(
        client.post(
            "/api/v1/tenant/release-gates/requests",
            json={"gate": "G1", "scope": "Pilot Kontenrahmen", "evidence": "Testfall"},
            headers=padmin,
        ),
        201,
    )
    approve_url = f"/api/v1/platform/tenants/{world.tenant_a}/release-gates/requests/{requested['id']}/approve"
    refused = client.post(approve_url, json={"comment": "ohne"}, headers=padmin2)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "MHVP-GATE-0004"
    state = _ok(client.get("/api/v1/tenant/release-gates", headers=h))
    assert next(g for g in state if g["gate"] == "G1")["open"] is False
    # The request stays open (requested), nothing was decided.
    pending = _ok(client.get("/api/v1/tenant/release-gates/requests", headers=h))
    assert next(r for r in pending if r["id"] == requested["id"])["status"] == "requested"

    # Draft -> in_review -> back to draft -> in_review -> released with comment.
    in_review = _ok(client.post(f"{A}/templates/{tid}/submit-review", headers=h))
    assert in_review["status"] == "in_review"
    assert in_review["review_requested_at"] is not None
    # A template in review is frozen.
    frozen = client.put(
        f"{A}/templates/{tid}/accounts", json={"accounts": template["accounts"]}, headers=h
    )
    assert frozen.status_code == 409
    assert frozen.json()["code"] == "MHVP-BILL-0010"
    assert _ok(client.post(f"{A}/templates/{tid}/back-to-draft", headers=h))["status"] == "draft"
    _ok(client.post(f"{A}/templates/{tid}/submit-review", headers=h))
    # Release with a missing tax advisor document is refused.
    missing_doc = client.post(
        f"{A}/templates/{tid}/release",
        json={"comment": "x", "document_id": "01920000-0000-7000-8000-0000000000aa"},
        headers=h,
    )
    assert missing_doc.status_code == 404
    # AE02: four eyes, the submitter cannot release; the switch is turned off with a reason.
    same = client.post(f"{A}/templates/{tid}/release", json={"comment": "x"}, headers=h)
    assert same.status_code == 409
    assert same.json()["code"] == "MHVP-ACC-0015"
    _ok(
        client.put(
            f"{A}/templates/{tid}/four-eyes",
            json={"required": False, "reason": "Testmandant mit einer Person"},
            headers=h,
        )
    )
    released = _ok(
        client.post(
            f"{A}/templates/{tid}/release",
            json={"comment": "Freigabe nach Prüfung durch Steuerberatung (Test)"},
            headers=h,
        )
    )
    assert released["status"] == "released"
    assert released["released"] is True
    assert released["released_by"] == str(world.users["dcadmin"])
    assert released["release_comment"].startswith("Freigabe nach")
    # Idempotent: a second release keeps the first record.
    again = _ok(client.post(f"{A}/templates/{tid}/release", json={"comment": "nochmal"}, headers=h))
    assert again["release_comment"] == released["release_comment"]
    assert again["released_at"] == released["released_at"]

    # Now the gate can be approved by the second person.
    approved = _ok(client.post(approve_url, json={"comment": "geprüft"}, headers=padmin2))
    assert approved["status"] == "approved"
    _ok(
        client.post(
            f"/api/v1/tenant/release-gates/requests/{requested['id']}/revoke", json={}, headers=h
        )
    )

    # A released version is immutable; a change creates version 2 as draft.
    locked = client.put(
        f"{A}/templates/{tid}/accounts", json={"accounts": template["accounts"]}, headers=h
    )
    assert locked.status_code == 409
    assert locked.json()["code"] == "MHVP-BILL-0010"
    v2 = _ok(client.post(f"{A}/templates/{tid}/versions", headers=h), 201)
    assert (v2["version"], v2["status"], v2["supersedes_id"]) == (2, "draft", tid)
    accounts = [dict(row) for row in v2["accounts"]]
    accounts[0]["name"] = "Geändert im Test"
    changed = _ok(
        client.put(f"{A}/templates/{v2['id']}/accounts", json={"accounts": accounts}, headers=h)
    )
    assert changed["accounts"][0]["name"] == "Geändert im Test"
    duplicate = client.put(
        f"{A}/templates/{v2['id']}/accounts",
        json={"accounts": [accounts[0], accounts[0]]},
        headers=h,
    )
    assert duplicate.status_code == 422
    history = _ok(client.get(f"{A}/templates/{tid}/history", headers=h))
    assert [(t["version"], t["status"]) for t in history] == [(1, "released"), (2, "draft")]
    # Version 1 stays released and unchanged.
    v1 = next(t for t in history if t["version"] == 1)
    assert v1["accounts"][0]["name"] != "Geändert im Test"

    # Exports for the tax advisor.
    csv = client.get(f"{A}/templates/{tid}/export", headers=h)
    assert csv.status_code == 200
    assert csv.text.startswith("Kontonummer;Bezeichnung;")
    assert "kontenrahmen-a1-v1.csv" in csv.headers["content-disposition"]
    pdf = client.get(f"{A}/templates/{tid}/export", params={"format": "pdf"}, headers=h)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    # Permissions: read_only can read history and export but not change; other tenant: 404.
    reader = bearer(login(client, world, "dcreader"))
    assert client.get(f"{A}/templates/{tid}/history", headers=reader).status_code == 200
    assert client.post(f"{A}/templates/{v2['id']}/submit-review", headers=reader).status_code == 403
    other = bearer(login(client, world, "ddcadmin"))
    assert client.get(f"{A}/templates/{tid}/history", headers=other).status_code == 404
    assert client.post(f"{A}/templates/{tid}/versions", headers=other).status_code == 404
    assert client.get(f"{A}/templates/{tid}/export", headers=other).status_code == 404
    assert _ok(client.get(f"{A}/templates", headers=other)) == []
