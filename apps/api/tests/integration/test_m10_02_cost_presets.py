"""M10-02 (operator decision 26.09.2026): cost accounts of the chart template are pre-set as a
DRAFT following the BetrKV catalogue (allocable with the customary key, everything else not
allocable, VAT option unset). The seed only fills fields that are still unset, never
overwrites operator edits, keeps tenants separate and shows the draft marker on the ledger
accounts. G1 and G3 stay closed; nothing here posts or settles."""

import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from mhvp.accounting.defaults import (
    A1_ACCOUNTS,
    BETRKV_TYPES,
    BETRKV_TYPES_WITHOUT_ACCOUNT,
    COSTS,
    DRAFT_NOTE,
    REVIEW_DRAFT,
    TEMPLATE_ACCOUNTS,
    fill_unset,
    merge_missing,
)
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.properties.defaults import ALLOCATION_KEYS
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_chart_template import _rental_owner_ledger
from tests.integration.test_m10_ledger import A, _hoa_ledger, _ok

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    """Own tenants and users (the M10 modules share one database in a test session)."""
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"cpre-{RUN}", name=f"Presets {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"cp2-{RUN}", name=f"Presets2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [("cpadmin", a, "tenant_admin"), ("cpother", b, "tenant_admin")]:
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


KEY_CODES = {code for code, *_ in ALLOCATION_KEYS}
COST_ROWS = {row["number"]: row for row in A1_ACCOUNTS if row["category"] == "cost"}


def test_betrkv_mapping_table_complete() -> None:
    """All 17 catalogue types are either mapped to an A.1 account or listed as missing."""
    assert set(BETRKV_TYPES) == set(range(1, 18))
    referenced = set()
    for _, _, _, _, betrkv in COSTS:
        for number in BETRKV_TYPES:
            if betrkv and f"Nr. {number} " in betrkv:
                referenced.add(number)
    assert referenced.isdisjoint(BETRKV_TYPES_WITHOUT_ACCOUNT)
    assert referenced | set(BETRKV_TYPES_WITHOUT_ACCOUNT) == set(BETRKV_TYPES)
    # Every cost account of annex A.1 has exactly one preset row.
    assert [n for n, *_ in COSTS] == list(COST_ROWS)


def test_cost_presets_follow_operator_decision() -> None:
    for number, _, allocation, key, betrkv in COSTS:
        row = COST_ROWS[number]
        assert row["vat_option"] == "none"  # VAT option stays open (M10-02)
        assert row["allocation_category"] == allocation
        assert row["allocation_key_code"] == key
        assert row["betrkv_reference"] == betrkv
        if allocation.startswith("allocable"):
            assert key in KEY_CODES
            assert row["statement_kind"] == "operating_costs"
            assert (row["review_status"], row["review_note"]) == (REVIEW_DRAFT, DRAFT_NOTE)
        elif allocation.startswith("non_allocable"):
            assert key is None
            assert row["statement_kind"] == "none"
            assert (row["review_status"], row["review_note"]) == (REVIEW_DRAFT, DRAFT_NOTE)
        else:  # mixed case stays unclassified, billing lock active (M17-01)
            assert (allocation, key) == ("none", None)
            assert row["review_status"] == "none"
    # Consumption keys only for heating, hot water and water; area otherwise.
    for number, _, allocation, key, _ in COSTS:
        if key and key.startswith("V_"):
            assert allocation in ("allocable_heating", "allocable_water"), number
    assert COST_ROWS["041400"]["allocation_category"] == "non_allocable_heating"
    assert COST_ROWS["041805"]["allocation_category"] == "none"


def _legacy(row: dict[str, Any]) -> dict[str, Any]:
    """A template row as stored before M10-02 (no presets, no key fields)."""
    old = {k: v for k, v in row.items() if k not in ("allocation_key_code", "betrkv_reference")}
    old.update(allocation_category="none", statement_kind="none", review_status="none")
    old["review_note"] = None
    return old


def test_fill_unset_fills_only_unset_and_keeps_edits() -> None:
    legacy = [_legacy(row) for row in A1_ACCOUNTS]
    edited = dict(_legacy(COST_ROWS["040100"]), allocation_category="non_allocable_other")
    edited_key = dict(_legacy(COST_ROWS["042100"]), allocation_key_code="PERS")
    rows = [r for r in legacy if r["number"] not in ("040100", "042100")] + [edited, edited_key]
    filled, changed = fill_unset(rows, TEMPLATE_ACCOUNTS)
    assert changed
    by_number = {r["number"]: r for r in filled}
    # Operator edit kept, but the still unset key is proposed and the row becomes a draft.
    assert by_number["040100"]["allocation_category"] == "non_allocable_other"
    assert by_number["040100"]["allocation_key_code"] == "WFL"
    assert by_number["040100"]["review_status"] == REVIEW_DRAFT
    # Operator chose persons for drinking water: key kept, category filled.
    assert by_number["042100"]["allocation_key_code"] == "PERS"
    assert by_number["042100"]["allocation_category"] == "allocable_water"
    # Untouched legacy rows equal the template rows now.
    assert by_number["041000"] == COST_ROWS["041000"]
    assert by_number["041805"]["review_status"] == "none"
    assert by_number["001300"]["review_status"] == "none"
    # Rows without a template counterpart stay as they are; idempotent second pass.
    extra = {"number": "045000", "name": "Eigenes Konto", "allocation_category": "none"}
    again, changed_again = fill_unset([*filled, extra], TEMPLATE_ACCOUNTS)
    assert not changed_again
    assert again[-1] == extra
    assert merge_missing(again, TEMPLATE_ACCOUNTS) == again + [
        r for r in TEMPLATE_ACCOUNTS if r["category"] != "cost" and r["number"] not in by_number
    ]


def _template_accounts(engine: Engine, tenant: Any, template_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        value = conn.execute(
            text("SELECT accounts FROM chart_of_accounts_template WHERE id = :id"),
            {"id": template_id},
        ).scalar_one()
    return list(value)


@pytest.fixture
def app_engine(database: Database) -> Iterator[Engine]:
    """Direct access as the runtime role (RLS applies with the tenant setting)."""
    engine = create_engine(database.app_url)
    yield engine
    engine.dispose()


def test_seed_fills_unset_keeps_operator_edit_and_separates_tenants(
    client: TestClient, world: World, app_engine: Engine
) -> None:
    h = bearer(login(client, world, "cpadmin"))
    other = bearer(login(client, world, "cpother"))
    mine = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    theirs = _ok(client.post(f"{A}/templates/default", headers=other), 201)
    # Simulate the pre M10-02 state plus an operator edit directly in the tenant's template.
    rows = [_legacy(r) if r["category"] == "cost" else r for r in mine["accounts"]]
    for row in rows:
        if row["number"] == "040300":
            row["allocation_category"] = "non_allocable_other"  # operator decided otherwise
            row["review_status"] = "none"
    with app_engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        updated = conn.execute(
            text(
                "UPDATE chart_of_accounts_template SET accounts = CAST(:a AS jsonb) WHERE id = :id"
            ),
            {"a": json.dumps(rows), "id": mine["id"]},
        ).rowcount
    assert updated == 1
    seeded = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    assert seeded["id"] == mine["id"]
    assert seeded["released"] is False
    by_number = {r["number"]: r for r in seeded["accounts"]}
    assert len(by_number) == len(TEMPLATE_ACCOUNTS)
    assert by_number["040300"]["allocation_category"] == "non_allocable_other"
    assert by_number["040300"]["allocation_key_code"] == "WFL"  # only the unset field
    assert by_number["041000"]["allocation_category"] == "allocable_heating"
    assert by_number["041000"]["allocation_key_code"] == "V_HEIZ"
    assert by_number["041000"]["review_status"] == REVIEW_DRAFT
    assert by_number["041000"]["review_note"] == DRAFT_NOTE
    assert by_number["041000"]["vat_option"] == "none"
    assert by_number["041805"]["allocation_category"] == "none"
    # Second run changes nothing (idempotent), stored rows equal the API answer.
    third = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    assert third["accounts"] == seeded["accounts"]
    assert _template_accounts(app_engine, world.tenant_a, mine["id"]) == seeded["accounts"]
    # The other tenant's template was neither edited nor changed by the first tenant's seed.
    stored = {r["number"]: r for r in _template_accounts(app_engine, world.tenant_b, theirs["id"])}
    assert stored["040300"]["allocation_category"] == "allocable_other"
    assert stored["040300"]["review_status"] == REVIEW_DRAFT
    assert theirs["id"] != mine["id"]


def test_ledger_accounts_show_cost_presets_as_draft(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "cpadmin"))
    _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _rental_owner_ledger(client, h, "743")
    accounts = {
        a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    assert accounts["040100"]["allocation_category"] == "allocable_other"
    assert accounts["040100"]["statement_kind"] == "operating_costs"
    assert accounts["040100"]["vat_option"] == "none"
    assert accounts["040100"]["review_status"] == REVIEW_DRAFT
    assert accounts["040100"]["review_note"] == DRAFT_NOTE
    assert accounts["041400"]["allocation_category"] == "non_allocable_heating"
    assert accounts["041400"]["review_status"] == REVIEW_DRAFT
    assert accounts["041805"]["allocation_category"] == "none"
    assert accounts["041805"]["review_status"] == "none"
    assert accounts["001300"]["review_status"] == "none"
    # HOA ledgers get the same cost presets (cost accounts apply to all entity kinds).
    hoa_ledger, _, _ = _hoa_ledger(client, h, "744")
    hoa = {a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{hoa_ledger}/accounts", headers=h))}
    assert hoa["042100"]["allocation_category"] == "allocable_water"
    assert hoa["042100"]["review_status"] == REVIEW_DRAFT
