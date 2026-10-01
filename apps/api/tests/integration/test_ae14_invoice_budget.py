"""Wave 16 AE14 (P03-03, M14-02): budget comparison and resolution coverage of the factual review.

Expected values (recomputed by hand): plan item 2.000,00; earlier invoice 1.190,00; credit note
238,00; booked before 1.190,00 - 238,00 = 952,00; this invoice 1.190,00; remaining
2.000,00 - 952,00 - 1.190,00 = -142,00; total 2.142,00 > 2.000,00 (0 % tolerance), exceeded.
A resolution on another economic plan gives resolution_subject_mismatch.
"""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_w5_t05_invoice_factual import _invoice, _ok, _setup, _sql

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae14a-{RUN}", name=f"AE14 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae14b-{RUN}", name=f"AE14 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae14admin", a, "tenant_admin"),
            ("ae14approver", a, "tenant_admin"),
            ("ae14other", b, "tenant_admin"),
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


def _plan(engine: Engine, t: str, env: dict[str, Any]) -> tuple[str, str]:
    key = _sql(
        engine, t, "SELECT id FROM allocation_key WHERE property_id = :p LIMIT 1", p=env["property"]
    )
    if not key:
        key = _sql(
            engine,
            t,
            "INSERT INTO allocation_key (id, tenant_id, property_id, code, name, unit_of_measure,"
            " kind, sort_order, is_template_derived) VALUES (:id, :t, :p, 'AE', 'AE', 'qm',"
            " 'static', 0, false) RETURNING id",
            id=str(uuid.uuid4()),
            t=t,
            p=env["property"],
        )
    plan, item = str(uuid.uuid4()), str(uuid.uuid4())
    _sql(
        engine,
        t,
        "INSERT INTO economic_plan (id, tenant_id, ledger_id, year, valid_from, status, version)"
        " VALUES (:id, :t, :l, 2026, '2026-01-01', 'draft', 1)",
        id=plan,
        t=t,
        l=env["ledger"],
    )
    _sql(
        engine,
        t,
        "INSERT INTO economic_plan_item (id, tenant_id, plan_id, label, component, amount,"
        " allocation_key_id, account_id) VALUES (:id, :t, :p, 'Instandhaltung', 'hoa_fee',"
        " 2000.00, :k, :a)",
        id=item,
        t=t,
        p=plan,
        k=str(key[0][0]),
        a=env["acc"]["040100"],
    )
    return plan, item


def test_budget_comparison_and_resolution_coverage(
    client: TestClient, world: World, migrator_engine: Engine
) -> None:
    h = bearer(login(client, world, "ae14admin"))
    env = _setup(client, h, world, "714", approver="ae14approver")
    t = str(world.tenant_a)
    _plan_id, item = _plan(migrator_engine, t, env)
    res = str(uuid.uuid4())
    _sql(
        migrator_engine,
        t,
        "INSERT INTO resolution (id, tenant_id, legal_entity_id, number, decided_on, subject,"
        " wording, status, kind, votes, subject_type, subject_id) VALUES (:id, :t, :le, 3,"
        " '2025-11-01', 'Wirtschaftsplan', 'Plan beschlossen', 'positive', 'meeting', '{}',"
        " 'economic_plan', :other)",
        id=res,
        t=t,
        le=env["hoa"],
        other=str(uuid.uuid4()),
    )
    first = _ok(client.post(f"{A}/invoices", json=_invoice(env, plan_item_id=item), headers=h), 201)
    first_check = _ok(client.get(f"{A}/invoices/{first['id']}/factual-check", headers=h))
    assert Decimal(first_check["budget"]["booked_before"]) == Decimal("0.00")
    assert Decimal(first_check["budget"]["remaining"]) == Decimal("810.00")
    assert first_check["budget"]["exceeded"] is False
    credit = _ok(
        client.post(
            f"{A}/invoices",
            json=_invoice(
                env,
                plan_item_id=item,
                net="200.00",
                vat="38.00",
                gross="238.00",
                lines=[
                    {
                        "account_id": env["acc"]["040100"],
                        "net": "200.00",
                        "vat_percent": "19",
                        "vat": "38.00",
                        "text": "Gutschrift",
                    }
                ],
            ),
            headers=h,
        ),
        201,
    )
    # Fixture: a credit note needs a posted original (G1); the draft is marked as credit note
    # directly so the budget arithmetic can be checked without posting.
    _sql(
        migrator_engine,
        t,
        "UPDATE invoice SET kind = 'credit_note' WHERE id = :id",
        id=credit["id"],
    )
    third = _ok(
        client.post(
            f"{A}/invoices", json=_invoice(env, plan_item_id=item, resolution_id=res), headers=h
        ),
        201,
    )
    check = _ok(client.get(f"{A}/invoices/{third['id']}/factual-check", headers=h))
    budget = check["budget"]
    assert Decimal(budget["planned"]) == Decimal("2000.00")
    assert Decimal(budget["booked_before"]) == Decimal("952.00")
    assert Decimal(budget["invoice"]) == Decimal("1190.00")
    assert Decimal(budget["remaining"]) == Decimal("-142.00")
    assert budget["exceeded"] is True
    codes = {f["code"] for f in check["findings"]}
    assert {"budget_exceeded", "resolution_subject_mismatch"} <= codes
    assert check["resolution"]["number"] == 3
    assert check["resolution"]["effective"] is True
    assert check["resolution"]["subject_matches_plan"] is False
    assert check["automatic_release"] is False
    # Tenant separation: other tenant sees nothing.
    other = bearer(login(client, world, "ae14other"))
    assert client.get(f"{A}/invoices/{third['id']}/factual-check", headers=other).status_code == 404


def test_no_links_no_comparison(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae14admin"))
    env = _setup(client, h, world, "715", approver="ae14approver")
    inv = _ok(client.post(f"{A}/invoices", json=_invoice(env), headers=h), 201)
    check = _ok(client.get(f"{A}/invoices/{inv['id']}/factual-check", headers=h))
    assert check["budget"] is None
    assert check["resolution"] is None
    assert client.get(f"{A}/invoices/{inv['id']}/factual-check").status_code == 401
