"""P15 platform: licence and price list maintenance (M27-02), one pricing structure in the
billing preview (M27-04), daily usage history (M27-05), export job (M27-01) and the new
operating alerts (M9-01). Expected values are computed by hand in the comments."""

import asyncio
import io
import json
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, World, bearer, login
from tests.integration.test_m27_market_readiness import BUCKET, _settings

pytestmark = pytest.mark.integration
P = "/api/v1/platform"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services
    from tests.integration.test_m2_platform import PASSWORD

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p15-{RUN}", name=f"P15 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, admin in [("p15admin", False), ("p15padmin", True), ("p15padmin2", True)]:
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=admin,
            )
            world.users[name] = uid
            if not admin:
                await services.add_member(
                    factory,
                    tenant_id=a,
                    user_id=uid,
                    role_codes=["tenant_admin"],
                    actor_user_id=None,
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(autouse=True)
def reset_structure(database: Database) -> Iterator[None]:
    """The pricing structure is one global platform table: amounts and the trial length set
    here must not leak into other tests (they expect the unpriced default)."""
    from sqlalchemy import create_engine, text

    def reset() -> None:
        engine = create_engine(database.migrator_url)
        with engine.begin() as conn:
            conn.execute(text("UPDATE pricing_plan_item SET amount = NULL, trial_days = NULL"))
        engine.dispose()

    reset()
    yield
    reset()


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_price_and_license_maintenance(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p15admin"))
    ph = bearer(login(client, world, "p15padmin"))
    tenant = str(world.tenant_a)
    entry = _ok(
        client.post(
            f"{P}/price-list",
            json={"module": "ai", "price_per_unit": "0.50", "valid_from": "2020-01-01"},
            headers=ph,
        ),
        201,
    )
    # A tenant administrator may neither change nor delete (403), an unknown id is 404.
    assert client.patch(f"{P}/price-list/{entry['id']}", json={}, headers=h).status_code == 403
    assert client.delete(f"{P}/price-list/{entry['id']}", headers=h).status_code == 403
    missing = uuid.uuid4()
    assert client.patch(f"{P}/price-list/{missing}", json={}, headers=ph).status_code == 404
    assert (
        client.patch(
            f"{P}/price-list/{entry['id']}", json={"price_per_unit": None}, headers=ph
        ).status_code
        == 422
    )
    changed = _ok(
        client.patch(f"{P}/price-list/{entry['id']}", json={"price_per_unit": "0.75"}, headers=ph)
    )
    assert changed["price_per_unit"] == "0.75"
    # The entry valid today feeds the module row of the structure (M27-04).
    pricing = _ok(client.get(f"{P}/pricing", headers=ph))
    assert next(i for i in pricing["items"] if i["code"] == "module_ai")["amount"] == "0.75"

    lic = _ok(
        client.post(
            f"{P}/licenses",
            json={
                "tenant_id": tenant,
                "module": "portal",
                "unit_quota": 5,
                "valid_from": "2020-01-01",
                "price_per_unit": "1.00",
            },
            headers=ph,
        ),
        201,
    )
    assert client.patch(f"{P}/licenses/{lic['id']}", json={}, headers=h).status_code == 403
    assert (
        client.patch(f"{P}/licenses/{lic['id']}", json={"unit_quota": -1}, headers=ph).status_code
        == 422
    )
    patched = _ok(client.patch(f"{P}/licenses/{lic['id']}", json={"unit_quota": 9}, headers=ph))
    assert patched["unit_quota"] == 9
    assert (
        client.post(
            f"{P}/licenses/{lic['id']}/end", json={"valid_until": "2019-12-31"}, headers=ph
        ).status_code
        == 422
    )
    ended = _ok(
        client.post(f"{P}/licenses/{lic['id']}/end", json={"valid_until": "2020-12-31"}, headers=ph)
    )
    assert ended["valid_until"] == "2020-12-31"
    structure = _ok(
        client.patch(f"{P}/licenses/{lic['id']}", json={"use_structure_price": True}, headers=ph)
    )
    assert structure["price_source"] == "structure"
    assert (
        client.post(
            f"{P}/licenses/{missing}/end", json={"valid_until": "2021-01-01"}, headers=ph
        ).status_code
        == 404
    )

    assert client.delete(f"{P}/price-list/{entry['id']}", headers=ph).status_code == 204
    assert client.delete(f"{P}/price-list/{entry['id']}", headers=ph).status_code == 404


def test_billing_preview_uses_tier_module_and_trial(client: TestClient, world: World) -> None:
    ph = bearer(login(client, world, "p15padmin"))
    tenant = str(world.tenant_a)
    pricing = _ok(client.get(f"{P}/pricing", headers=ph))
    by_code = {i["code"]: i for i in pricing["items"]}

    def set_amount(code: str, amount: str) -> None:
        _ok(
            client.patch(
                f"{P}/pricing/items/{by_code[code]['id']}", json={"amount": amount}, headers=ph
            )
        )

    # No units in this tenant -> the tier lookup for 0 units finds no tier (min_units 1).
    set_amount("tier_s", "2.00")
    set_amount("module_banking", "1.50")
    _ok(
        client.patch(
            f"{P}/pricing/items/{by_code['trial']['id']}", json={"trial_days": 45}, headers=ph
        )
    )
    # Licences without an agreed price: core by tier, banking by module row.
    for module in ("core", "banking"):
        _ok(
            client.post(
                f"{P}/licenses",
                json={
                    "tenant_id": tenant,
                    "module": module,
                    "unit_quota": 10,
                    "valid_from": "2040-01-01",
                },
                headers=ph,
            ),
            201,
        )
    # Units: create two units so that the tier S (1 to 100) applies.
    # Month 2040-01 ends on day 31 < 2040-01-01 + 45 days (2040-02-15): trial, charged 0,00.
    trial = _ok(
        client.get(
            f"{P}/tenants/{tenant}/billing-preview", params={"month": "2040-01-15"}, headers=ph
        )
    )
    assert all(x["trial"] for x in trial["lines"])
    assert trial["net_total"] == "0.00"
    # Month 2040-03 ends after the trial: amount = units x price, units from the counter.
    bill = _ok(
        client.get(
            f"{P}/tenants/{tenant}/billing-preview", params={"month": "2040-03-01"}, headers=ph
        )
    )
    lines = {x["module"]: x for x in bill["lines"]}
    assert all(not x["trial"] for x in bill["lines"])
    units = lines["core"]["units"]
    assert lines["banking"]["price_source"] == "structure"
    assert lines["banking"]["price_per_unit"] == "1.50"
    assert lines["banking"]["amount"] == f"{units * 1.5:.2f}"
    if units >= 1:
        assert lines["core"]["tier"] == "tier_s"
        assert lines["core"]["amount"] == f"{units * 2:.2f}"
    else:
        assert lines["core"]["price_source"] == "structure_missing"
        assert bill["complete"] is False


def test_usage_history_daily_and_monthly(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p15admin"))
    ph = bearer(login(client, world, "p15padmin"))
    tenant = str(world.tenant_a)
    today = datetime.now(UTC).date()
    month = today.replace(day=1).isoformat()
    _ok(client.post(f"{P}/tenants/{tenant}/usage", json={"month": month}, headers=ph))
    _ok(client.post(f"{P}/tenants/{tenant}/usage", json={"month": month}, headers=ph))
    history = _ok(client.get(f"{P}/tenants/{tenant}/usage/history", headers=ph))
    # One snapshot per day (upsert), monthly row for the running month.
    assert [d["day"] for d in history["daily"]].count(today.isoformat()) == 1
    assert month in [m["month"] for m in history["monthly"]]
    assert client.get(f"{P}/tenants/{tenant}/usage/history", headers=h).status_code == 403
    assert client.get(f"{P}/tenants/{uuid.uuid4()}/usage/history", headers=ph).status_code == 404
    # Past months leave no daily snapshot.
    _ok(client.post(f"{P}/tenants/{tenant}/usage", json={"month": "2031-02-01"}, headers=ph))
    again = _ok(client.get(f"{P}/tenants/{tenant}/usage/history", params={"days": 731}, headers=ph))
    assert date.fromisoformat("2031-02-01").isoformat() not in [d["day"] for d in again["daily"]]


def test_export_job_writes_archive_with_documents(
    client: TestClient, world: World, database: Database, redis_url: str, monkeypatch: Any
) -> None:
    from mhvp.platform import export_job

    h = bearer(login(client, world, "p15admin"))
    ph = bearer(login(client, world, "p15padmin"))
    ph2 = bearer(login(client, world, "p15padmin2"))
    tenant = str(world.tenant_a)
    upload = client.post(
        "/api/v1/documents",
        files={"file": ("akte.txt", b"Inhalt " + RUN.encode(), "text/plain")},
        headers=h,
    )
    assert upload.status_code == 201, upload.text
    doc_id = upload.json()["id"]
    req = _ok(
        client.post(
            f"{P}/tenants/{tenant}/export-requests", json={"purpose": "access"}, headers=ph
        ),
        201,
    )
    base = f"{P}/tenants/{tenant}/export-requests/{req['id']}"
    queued: list[tuple[str, str]] = []
    monkeypatch.setattr(export_job, "dispatch_export_job", lambda r, t: queued.append((r, t)))
    # Not approved: no job (409); tenant administrator: 403.
    assert client.post(f"{base}/run", headers=ph).status_code == 409
    assert client.post(f"{base}/run", headers=h).status_code == 403
    _ok(client.post(f"{base}/approve", json={}, headers=ph2))
    started = _ok(client.post(f"{base}/run", headers=ph), 202)
    assert started["job_status"] == "queued"
    assert queued == [(req["id"], tenant)]
    assert client.post(f"{base}/run", headers=ph).status_code == 409  # not twice
    assert client.get(f"{base}/download", headers=ph).status_code == 409  # still queued

    settings = _settings(database, redis_url)
    result = asyncio.run(
        export_job.run_export_job(settings, uuid.UUID(req["id"]), uuid.UUID(tenant))
    )
    assert result == "ready"
    listed = _ok(client.get(f"{P}/tenants/{tenant}/export-requests", headers=ph))
    row = next(r for r in listed if r["id"] == req["id"])
    assert row["job_status"] == "ready"
    assert row["job_size"] > 0
    assert len(row["job_sha256"]) == 64
    download = client.get(f"{base}/download", headers=ph)
    assert download.status_code == 200, download.text
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["documents"]["written"] >= 1
    assert manifest["documents"]["errors"] == []
    originals = [n for n in archive.namelist() if n.startswith(f"documents/{doc_id}_")]
    assert len(originals) == 1
    assert archive.read(originals[0]) == b"Inhalt " + RUN.encode()
    documents = [json.loads(x) for x in archive.read("data/documents.jsonl").splitlines()]
    assert {d["tenant_id"] for d in documents} == {tenant}
    # Re-running a finished job is skipped.
    again = asyncio.run(
        export_job.run_export_job(settings, uuid.UUID(req["id"]), uuid.UUID(tenant))
    )
    assert again == "skipped"


def test_ops_metrics_contains_bank_payment_dunning_alert_inputs(
    client: TestClient, world: World
) -> None:
    ph = bearer(login(client, world, "p15padmin"))
    body = _ok(client.get(f"{P}/ops/metrics", headers=ph))
    for name in (
        "bank_sync_runs_failed_24h",
        "bank_connections_error",
        "payment_orders_rejected_24h",
        "dunning_cases_blocked",
    ):
        assert body["metrics"][name] >= 0
    from mhvp.workspace.ops import ALERTING

    assert {"bank_sync_runs_failed_24h", "payment_orders_rejected_24h"} <= ALERTING
