"""Package AE09 (M24-08, P07-01, M12-L2): plan change within the year. Expected values by
hand: Hausgeld standing 100,00 EUR per month on unit 01 (MEA 600 of 1.000); March and April
2025 posted. Plan 2025 from 01.03.2025 with Hausgeld 3.000,00 EUR per year: unit 01 gets
3.000,00 * 600 / 1.000 / 12 = 150,00 per month, difference 50,00 per posted month, total
100,00 (claim). Unit 02 has no posted month, no row."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m24_hoa import A, H, OpenG4, _hoa_ledger, _ok, _owner

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae09a-{RUN}", name=f"AE09 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae09b-{RUN}", name=f"AE09b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ae09admin", a, "tenant_admin"),
            ("ae09second", a, "tenant_admin"),
            ("ae09reader", a, "read_only"),
            ("ae09other", b, "tenant_admin"),
        ):
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
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = base_settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
    ):
        yield closed, open_


def _count(engine: Engine, tenant: Any, table: str) -> int:
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def test_plan_change_difference_variants_gate_and_four_eyes(
    clients: tuple[TestClient, TestClient], world: World, migrator_engine: Engine
) -> None:
    closed, open_ = clients
    h = bearer(login(closed, world, "ae09admin"))
    h2 = bearer(login(closed, world, "ae09second"))
    hr = bearer(login(closed, world, "ae09reader"))
    ho = bearer(login(closed, world, "ae09other"))
    w = _hoa_ledger(closed, h, "791")
    mea, ledger, acc = w["keys"]["MEA"], w["ledger"], w["acc"]
    _, c1 = _owner(closed, h, w["property"], "01", "600", mea, {"hoa_fee": "100.00"})
    _owner(closed, h, w["property"], "02", "400", mea, {})
    _ok(
        closed.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": acc["060100"]},
            headers=h,
        )
    )
    for month in ("2025-03-01", "2025-04-01"):
        run = _ok(
            closed.post(
                f"{A}/receivable-runs",
                json={"period_month": month, "scope": "contract", "scope_id": c1["id"]},
                headers=h,
            ),
            201,
        )
        _ok(closed.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))

    plan = _ok(
        closed.post(
            f"{H}/plans",
            json={"ledger_id": ledger, "year": 2025, "valid_from": "2025-03-01"},
            headers=h,
        ),
        201,
    )
    _ok(
        closed.post(
            f"{H}/plans/{plan['id']}/items",
            json={
                "label": "Hausgeld",
                "component": "hoa_fee",
                "amount": "3000.00",
                "allocation_key_id": mea,
            },
            headers=h,
        ),
        201,
    )
    calc = _ok(closed.post(f"{H}/plans/{plan['id']}/calculate", headers=h))

    # Default variant: notice only.
    setting = _ok(closed.get(f"{H}/plan-change-settings", headers=h))
    assert setting["mode"] == "notice"
    diff = _ok(closed.get(f"{H}/plans/{plan['id']}/differences", headers=h))
    assert diff["total"] == "100.00"
    assert [
        (r["unit_number"], r["period_month"], r["difference"], r["kind"]) for r in diff["rows"]
    ] == [
        ("01", "2025-03-01", "50.00", "claim"),
        ("01", "2025-04-01", "50.00", "claim"),
    ]
    assert diff["rows"][0]["posted_amount"] == "100.00"
    assert diff["rows"][0]["new_amount"] == "150.00"
    # Reader may read, not draft; other tenant sees nothing; unknown query 422.
    _ok(closed.get(f"{H}/plans/{plan['id']}/differences", headers=hr))
    assert closed.post(f"{H}/plans/{plan['id']}/differences/draft", headers=hr).status_code == 403
    assert closed.get(f"{H}/plans/{plan['id']}/differences", headers=ho).status_code == 404
    assert (
        closed.get(f"{H}/plans/{plan['id']}/differences", params={"x": "1"}, headers=h).status_code
        == 422
    )
    assert (
        closed.put(f"{H}/plan-change-settings", json={"mode": "auto"}, headers=h).status_code == 422
    )
    assert (
        closed.put(f"{H}/plan-change-settings", json={"mode": "due_now"}, headers=hr).status_code
        == 403
    )

    # Not resolved yet: no draft.
    _ok(closed.put(f"{H}/plan-change-settings", json={"mode": "due_now"}, headers=h))
    assert closed.post(f"{H}/plans/{plan['id']}/differences/draft", headers=h).status_code == 409

    _ok(
        closed.post(
            f"{H}/plans/{plan['id']}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    resolution = _ok(
        closed.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2025-05-10",
                "subject": "Wirtschaftsplan 2025",
                "wording": "Der Wirtschaftsplan 2025 wird beschlossen.",
                "status": "positive",
                "subject_type": "economic_plan",
                "subject_id": plan["id"],
                "snapshot_hash": calc["snapshot_hash"],
            },
            headers=h,
        ),
        201,
    )
    _ok(
        closed.post(
            f"{H}/plans/{plan['id']}/transition",
            json={"target": "resolved", "resolution_id": resolution["id"]},
            headers=h,
        )
    )
    preview = _ok(closed.get(f"{H}/plans/{plan['id']}/apply/preview", headers=h))
    assert (preview["plan_change_mode"], preview["differences_total"]) == ("due_now", "100.00")

    # Notice variant refuses drafts.
    _ok(closed.put(f"{H}/plan-change-settings", json={"mode": "notice"}, headers=h))
    assert closed.post(f"{H}/plans/{plan['id']}/differences/draft", headers=h).status_code == 409

    journal_before = _count(migrator_engine, world.tenant_a, "journal_entry")
    items_before = _count(migrator_engine, world.tenant_a, "receivable_item")
    _ok(closed.put(f"{H}/plan-change-settings", json={"mode": "due_now"}, headers=h))
    drafted = _ok(closed.post(f"{H}/plans/{plan['id']}/differences/draft", headers=h), 201)
    assert (drafted["created"], drafted["proposed_due"]) == (2, "2025-06-01")
    again = _ok(closed.post(f"{H}/plans/{plan['id']}/differences/draft", headers=h), 201)
    assert again["created"] == 0  # idempotent
    drafts = _ok(closed.get(f"{H}/plans/{plan['id']}/differences", headers=h))["drafts"]
    assert [d["status"] for d in drafts] == ["draft", "draft"]
    first = drafts[0]["id"]

    # Approval: G4 closed -> refused; creator -> four eyes; reader -> 403; other tenant -> 404.
    assert closed.post(f"{H}/plan-differences/{first}/approve", headers=h2).status_code == 403
    four_eyes = open_.post(f"{H}/plan-differences/{first}/approve", headers=h)
    assert four_eyes.status_code in (403, 409)
    assert "Ersteller" in four_eyes.text
    assert open_.post(f"{H}/plan-differences/{first}/approve", headers=hr).status_code == 403
    assert open_.post(f"{H}/plan-differences/{first}/approve", headers=ho).status_code == 404
    approved = _ok(open_.post(f"{H}/plan-differences/{first}/approve", headers=h2))
    assert approved["status"] == "approved"
    assert open_.post(f"{H}/plan-differences/{first}/reject", headers=h2).status_code == 409
    rejected = _ok(open_.post(f"{H}/plan-differences/{drafts[1]['id']}/reject", headers=h2))
    assert rejected["status"] == "rejected"
    # Nothing posted by drafts or approval.
    assert _count(migrator_engine, world.tenant_a, "journal_entry") == journal_before
    assert _count(migrator_engine, world.tenant_a, "receivable_item") == items_before
