"""GA05-01 to GA05-03 (7.1 B03, B04, B09): numbering report, versioned notes on posted
entries, subledger reconciliation. Expected values by hand (rule 0.1.8):

* receivable 100,00 on the debtor, payment 40,00 settling it, payment 30,00 without
  settlement: ledger balance 100 - 40 - 30 = 30,00; open item remaining 100 - 40 = 60,00;
  difference 30 - 60 = -30,00 (unapplied payment, shown, not an error);
* reversal of the 40,00 payment: balance 70,00, remaining 100,00, difference -30,00;
* number 3 moved to 8 (manipulated, 4 is the reversal): gaps 3, 5, 6, 7 and counter 4 against
  highest number 8.
"""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import A, _book, _code, _entry, _hoa_ledger, _line, _ok

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"g5-{RUN}", name=f"GA05 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"g5b-{RUN}", name=f"GA05b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ga05admin", a, "tenant_admin"),
            ("ga05reader", a, "read_only"),
            ("ga05other", b, "tenant_admin"),
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


def _manipulate(database: Database, tenant: uuid.UUID, sql: str, params: dict[str, Any]) -> None:
    """Test only: bypass the posting guards as table owner to simulate a damaged register."""
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            conn.execute(text("ALTER TABLE journal_entry DISABLE TRIGGER USER"))
            conn.execute(text(sql), params)
            conn.execute(text("ALTER TABLE journal_entry ENABLE TRIGGER USER"))
    finally:
        engine.dispose()


def test_numbering_and_subledger_checks(
    client: TestClient, world: World, database: Database
) -> None:
    h = bearer(login(client, world, "ga05admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "951")
    receivable = _book(
        client,
        h,
        ledger,
        _entry(
            "receivable",
            "2026-02-01",
            [_line(debtor, "100.00"), _line(acc["060100"], "0", "100.00")],
        ),
    )
    oi = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-02-28"}, headers=h)
    )[0]["id"]
    pay = _book(
        client,
        h,
        ledger,
        _entry(
            "debtor_payment",
            "2026-02-10",
            [_line(acc["001200"], "40.00"), _line(debtor, "0", "40.00")],
            settlements=[{"open_item_id": oi, "amount": "40.00"}],
        ),
    )
    _book(
        client,
        h,
        ledger,
        _entry(
            "debtor_payment",
            "2026-02-12",
            [_line(acc["001200"], "30.00"), _line(debtor, "0", "30.00")],
        ),
    )
    checks = _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))
    assert (checks["ok"], checks["findings"]) == (True, [])
    row = next(r for r in checks["subledger"] if r["account_id"] == debtor)
    assert Decimal(row["ledger_balance"]) == Decimal("30.00")
    assert Decimal(row["open_items_remaining"]) == Decimal("60.00")
    assert Decimal(row["difference"]) == Decimal("-30.00")
    assert [r["account_id"] for r in checks["subledger_differences"]] == [debtor]
    # As of a date before the payments: balance and remaining 100,00, no difference.
    early = _ok(
        client.get(f"{A}/ledgers/{ledger}/checks", params={"as_of": "2026-02-05"}, headers=h)
    )
    row = next(r for r in early["subledger"] if r["account_id"] == debtor)
    assert Decimal(row["difference"]) == Decimal("0.00")

    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{pay['id']}/reverse",
            json={"reason": "Fehlbuchung Test", "reason_code": "input_error"},
            headers=h,
        ),
        201,
    )
    after = _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))
    assert after["findings"] == []
    row = next(r for r in after["subledger"] if r["account_id"] == debtor)
    assert (Decimal(row["ledger_balance"]), Decimal(row["open_items_remaining"])) == (
        Decimal("70.00"),
        Decimal("100.00"),
    )
    assert receivable["number"] == 1

    # GA05-01: a damaged register is reported (number 3 moved to 8).
    entries = _ok(
        client.get(f"{A}/ledgers/{ledger}/entries", params={"status": "posted"}, headers=h)
    )
    third = next(e for e in entries if e["number"] == 3)
    _manipulate(
        database,
        world.tenant_a,
        "UPDATE journal_entry SET number = 8 WHERE id = :i",
        {"i": third["id"]},
    )
    try:
        damaged = _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))
        assert damaged["ok"] is False
        assert [f for f in damaged["findings"] if f.startswith("Nummernlücke")] == [
            f"Nummernlücke 2026-{n} im Buchungsregister" for n in (3, 5, 6, 7)
        ]
        assert any("Zählerstand 4 weicht von höchster Nummer 8" in f for f in damaged["findings"])
    finally:
        _manipulate(
            database,
            world.tenant_a,
            "UPDATE journal_entry SET number = 3 WHERE id = :i",
            {"i": third["id"]},
        )
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True
    # Other tenant: 404.
    other = bearer(login(client, world, "ga05other"))
    assert client.get(f"{A}/ledgers/{ledger}/checks", headers=other).status_code == 404


def test_versioned_entry_notes(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "ga05admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "952")
    body = _entry(
        "custom", "2026-03-01", [_line(debtor, "10.00"), _line(acc["060100"], "0", "10.00")]
    )
    draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
    url = f"{A}/ledgers/{ledger}/entries/{draft['id']}/notes"
    refused = client.post(url, json={"body": "Vermerk"}, headers=h)
    assert refused.status_code == 409
    assert _code(refused) == "MHVP-ACC-0009"
    entry = _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    url = f"{A}/ledgers/{ledger}/entries/{entry['id']}/notes"
    assert client.post(url, json={"body": "   "}, headers=h).status_code == 422
    assert client.post(url, json={"body": "x", "extra": 1}, headers=h).status_code == 422
    first = _ok(client.post(url, json={"body": "Beleg nachgereicht"}, headers=h), 201)
    assert (first["version"], first["supersedes_id"]) == (1, None)
    second = _ok(
        client.post(
            url,
            json={"body": "Beleg nachgereicht am 02.03.2026", "supersedes_id": first["id"]},
            headers=h,
        ),
        201,
    )
    assert (second["version"], second["note_key"], second["supersedes_id"]) == (
        2,
        first["note_key"],
        first["id"],
    )
    stale = client.post(url, json={"body": "Konflikt", "supersedes_id": first["id"]}, headers=h)
    assert stale.status_code == 409
    assert _code(stale) == "MHVP-ACC-0010"
    notes = _ok(client.get(url, headers=h))
    assert [(n["version"], n["is_current"]) for n in notes] == [(1, False), (2, True)]
    assert notes[0]["body"] == "Beleg nachgereicht"
    # Financial content unchanged.
    again = _ok(client.get(f"{A}/ledgers/{ledger}/entries/{entry['id']}", headers=h))
    assert (again["text"], again["lines"]) == (entry["text"], entry["lines"])
    # Authorization and tenant separation.
    reader = bearer(login(client, world, "ga05reader"))
    assert client.get(url, headers=reader).status_code == 200
    assert client.post(url, json={"body": "x"}, headers=reader).status_code == 403
    other = bearer(login(client, world, "ga05other"))
    assert client.get(url, headers=other).status_code == 404
    assert client.post(url, json={"body": "x"}, headers=other).status_code == 404
    # Append only, even for the table owner.
    engine = create_engine(database.migrator_url)
    try:
        with engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(world.tenant_a)}
            )
            update = text("UPDATE journal_entry_note SET body = 'x' WHERE id = :i")
            with pytest.raises(Exception, match="append-only"):
                conn.execute(update, {"i": first["id"]})
    finally:
        engine.dispose()
