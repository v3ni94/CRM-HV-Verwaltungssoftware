"""AE06 (AC01-02): sub ledger check hides written off items and items of reversed entries
(tenant switch, default on) and counts them separately. Expected values by hand (rule 0.1.8):

* receivable A 100,00 and receivable B 50,00 on the debtor: balance 150,00, remaining 150,00;
* B written off (flag set by the table owner, simulating the write off): balance 150,00;
  hidden: remaining 100,00, difference 50,00, excluded 50,00 (1 item); shown: difference 0,00;
* A reversed and the reversal settlement removed (damaged register): balance 50,00 (100 - 100
  + 50), shown: remaining 150,00 (difference -100,00); hidden: A is excluded (100,00, 1 item),
  B is excluded as well, so remaining 0,00 and difference 50,00.
"""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from mhvp.accounting.audit_export import _subledger_reason
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import A, _book, _entry, _hoa_ledger, _line, _ok

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae06-{RUN}", name=f"AE06 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae06b-{RUN}", name=f"AE06b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae06admin", a, "tenant_admin"),
            ("ae06reader", a, "read_only"),
            ("ae06other", b, "tenant_admin"),
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


def _owner_sql(database: Database, tenant: uuid.UUID, sql: str, params: dict[str, Any]) -> None:
    """Test only: change rows as table owner, triggers off."""
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            for table in ("open_item", "open_item_settlement"):
                conn.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER USER"))
            conn.execute(text(sql), params)
            for table in ("open_item", "open_item_settlement"):
                conn.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER USER"))
    finally:
        engine.dispose()


def _row(client: TestClient, h: dict[str, str], ledger: str, debtor: str, **q: Any) -> Any:
    checks = _ok(client.get(f"{A}/ledgers/{ledger}/checks", params=q, headers=h))
    return checks, next(r for r in checks["subledger"] if r["account_id"] == debtor)


def test_written_off_and_reversed_items_switch(
    client: TestClient, world: World, database: Database
) -> None:
    h = bearer(login(client, world, "ae06admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "961")
    first = _book(
        client,
        h,
        ledger,
        _entry(
            "receivable",
            "2026-03-01",
            [_line(debtor, "100.00"), _line(acc["060100"], "0", "100.00")],
        ),
    )
    _book(
        client,
        h,
        ledger,
        _entry(
            "receivable",
            "2026-03-02",
            [_line(debtor, "50.00"), _line(acc["060100"], "0", "50.00")],
        ),
    )
    checks, row = _row(client, h, ledger, debtor)
    assert checks["exclude_written_off"] is True
    assert (row["ledger_balance"], row["difference"]) == ("150.00", "0.00")
    assert checks["excluded"]["written_off"]["count"] == 0

    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )
    second = next(i["id"] for i in items if Decimal(i["amount"]) == Decimal("50.00"))
    _owner_sql(
        database,
        world.tenant_a,
        "UPDATE open_item SET written_off = true WHERE id = :i",
        {"i": second},
    )
    checks, row = _row(client, h, ledger, debtor)
    assert Decimal(row["open_items_remaining"]) == Decimal("100.00")
    assert Decimal(row["difference"]) == Decimal("50.00")
    assert checks["excluded"]["written_off"] == {"count": 1, "amount": "50.00"}
    # Override per request: counted as before, difference 0,00.
    checks, row = _row(client, h, ledger, debtor, exclude_written_off="false")
    assert Decimal(row["difference"]) == Decimal("0.00")
    assert checks["exclude_written_off"] is False
    assert checks["excluded"]["written_off"]["count"] == 1  # still reported separately

    # Tenant switch off: default of the check follows it.
    settings = _ok(client.get(f"{A}/tax/settings", headers=h))
    settings["subledger_exclude_written_off"] = False
    settings.pop("approval_limits", None)
    _ok(client.put(f"{A}/tax/settings", json=settings, headers=h))
    checks, row = _row(client, h, ledger, debtor)
    assert checks["exclude_written_off"] is False
    assert Decimal(row["difference"]) == Decimal("0.00")
    settings["subledger_exclude_written_off"] = True
    _ok(client.put(f"{A}/tax/settings", json=settings, headers=h))

    # Reversed entry without reversal settlement (damaged register).
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{first['id']}/reverse",
            json={"reason": "Fehlbuchung Test", "reason_code": "input_error"},
            headers=h,
        ),
        201,
    )
    first_item = next(i["id"] for i in items if Decimal(i["amount"]) == Decimal("100.00"))
    _owner_sql(
        database,
        world.tenant_a,
        "DELETE FROM open_item_settlement WHERE open_item_id = :i",
        {"i": first_item},
    )
    checks, row = _row(client, h, ledger, debtor, exclude_written_off="false")
    assert Decimal(row["ledger_balance"]) == Decimal("50.00")
    assert Decimal(row["difference"]) == Decimal("-100.00")
    checks, row = _row(client, h, ledger, debtor)
    assert checks["excluded"]["reversed"] == {"count": 1, "amount": "100.00"}
    assert Decimal(row["open_items_remaining"]) == Decimal("0.00")
    assert Decimal(row["difference"]) == Decimal("50.00")
    # Hard invariants unchanged.
    assert checks["findings"] == []


def test_validation_rls_and_permission(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae06admin"))
    ledger, _, _ = _hoa_ledger(client, h, "962")
    bad = client.get(f"{A}/ledgers/{ledger}/checks", params={"nonsense": "1"}, headers=h)
    assert bad.status_code == 422
    assert (
        client.get(f"{A}/ledgers/{ledger}/checks", params={"exclude_written_off": "x"}, headers=h)
    ).status_code == 422
    other = bearer(login(client, world, "ae06other"))
    assert client.get(f"{A}/ledgers/{ledger}/checks", headers=other).status_code == 404
    reader = bearer(login(client, world, "ae06reader"))
    put = client.put(
        f"{A}/tax/settings", json={"subledger_exclude_written_off": False}, headers=reader
    )
    assert put.status_code == 403


def test_export_reason_column() -> None:
    base: dict[str, Any] = {
        "difference": "0.00",
        "excluded_applied": True,
        "excluded_written_off_count": 0,
        "excluded_reversed_count": 0,
    }
    assert _subledger_reason(base) == "ausgeglichen"
    row = {
        **base,
        "difference": "5.00",
        "excluded_written_off_count": 2,
        "excluded_reversed_count": 1,
    }
    assert (
        _subledger_reason(row)
        == "Differenz; 2 ausgebucht (nicht gezählt); 1 storniert (nicht gezählt)"
    )
    assert "enthalten" in _subledger_reason({**row, "excluded_applied": False})
