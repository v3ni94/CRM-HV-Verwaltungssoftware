"""GAJ-304 and GAJ-305 (Welle 23, AM12): invariants B06 and B07 (section 7.1) in the booking
core, own test world with prefix am12.

B06: the same postings in reversed order give the same cent results (trial balance, open
items). B07: trial balance, open items and account sheet as of a cut off stay the same after
a later payment and a later reversal.

Expected values by hand (rule 0.1.8): receivables 333,33 + 333,33 + 333,34 = 1.000,00 on
debtor and -1.000,00 on income 060100; payment 600,00 on 10.04. and its reversal on 15.04.
are after the cut off 31.03., so as of 31.03. bank 001200 = 0,00, debtor = 1.000,00; as of
30.04. bank = 0,00 again (600 - 600) and debtor = 1.000,00; as of 12.04. bank 600,00, debtor
400,00."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import _book, _entry, _hoa_ledger, _line, _ok

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
AMOUNTS = ["333.33", "333.33", "333.34"]


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"am12-a-{RUN}", name=f"AM12 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"am12-b-{RUN}", name=f"AM12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("am12admin"), display_name="am12admin", password=PASSWORD
        )
        world.users["am12admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _balances(c: TestClient, h: dict[str, str], ledger: str, as_of: str) -> dict[str, Decimal]:
    tb = _ok(c.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": as_of}, headers=h))
    assert tb["balanced"] is True
    return {a["number"]: Decimal(a["balance"]) for a in tb["accounts"]}


def _stock(c: TestClient, h: dict[str, str], ledger: str, as_of: str) -> list[Decimal]:
    rows = _ok(c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": as_of}, headers=h))
    return sorted(Decimal(r["remaining"]) for r in rows)


def _receivables(
    c: TestClient,
    h: dict[str, str],
    ledger: str,
    acc: dict[str, str],
    debtor: str,
    order: list[int],
) -> list[dict[str, Any]]:
    out = []
    for i in order:
        amount = AMOUNTS[i]
        out.append(
            _book(
                c,
                h,
                ledger,
                _entry(
                    "receivable",
                    f"2026-03-0{i + 1}",
                    [_line(debtor, amount), _line(acc["060100"], "0", amount)],
                    due_date="2026-03-10",
                ),
            )
        )
    return out


def test_b06_posting_order_does_not_change_cent_results(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "am12admin"))
    first, acc1, debtor1 = _hoa_ledger(client, h, "121")
    second, acc2, debtor2 = _hoa_ledger(client, h, "122")
    _receivables(client, h, first, acc1, debtor1, [0, 1, 2])
    _receivables(client, h, second, acc2, debtor2, [2, 1, 0])
    b1 = _balances(client, h, first, "2026-03-31")
    b2 = _balances(client, h, second, "2026-03-31")
    assert b1 == b2
    assert b1["060100"] == Decimal("-1000.00")
    assert _stock(client, h, first, "2026-03-31") == _stock(client, h, second, "2026-03-31")
    assert _stock(client, h, first, "2026-03-31") == [
        Decimal("333.33"),
        Decimal("333.33"),
        Decimal("333.34"),
    ]


def test_b07_cut_off_unchanged_after_later_payment_and_reversal(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "am12admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "123")
    debtor_no = next(n for n, i in acc.items() if i == debtor)
    receivable = _book(
        client,
        h,
        ledger,
        _entry(
            "receivable",
            "2026-03-01",
            [_line(debtor, "1000.00"), _line(acc["060100"], "0", "1000.00")],
            due_date="2026-03-03",
        ),
    )

    def sheet(end: str) -> dict[str, Any]:
        return _ok(  # type: ignore[no-any-return]
            client.get(
                f"{A}/ledgers/{ledger}/accounts/{debtor}/sheet",
                params={"start": "2026-03-01", "end": end},
                headers=h,
            )
        )

    tb_before = _balances(client, h, ledger, "2026-03-31")
    oi_before = _stock(client, h, ledger, "2026-03-31")
    sheet_before = sheet("2026-03-31")
    assert tb_before[debtor_no] == Decimal("1000.00")
    assert oi_before == [Decimal("1000.00")]
    assert Decimal(sheet_before["closing_balance"]) == Decimal("1000.00")

    oi_id = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )[0]["id"]
    payment = _book(
        client,
        h,
        ledger,
        _entry(
            "debtor_payment",
            "2026-04-10",
            [_line(acc["001200"], "600.00"), _line(debtor, "0", "600.00")],
            settlements=[{"open_item_id": oi_id, "amount": "600.00"}],
        ),
    )
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{payment['id']}/reverse",
            json={"reason": "Rücklastschrift", "booking_date": "2026-04-15"},
            headers=h,
        ),
        201,
    )

    # The cut off 31.03. reproduces exactly (trial balance, open items, account sheet).
    assert _balances(client, h, ledger, "2026-03-31") == tb_before
    assert _stock(client, h, ledger, "2026-03-31") == oi_before
    assert sheet("2026-03-31") == sheet_before
    # Between payment and reversal: bank 600,00, debtor 400,00.
    mid = _balances(client, h, ledger, "2026-04-12")
    assert (mid["001200"], mid[debtor_no]) == (Decimal("600.00"), Decimal("400.00"))
    assert _stock(client, h, ledger, "2026-04-12") == [Decimal("400.00")]
    # After the reversal: bank 0,00, debtor 1.000,00; the original entries stay posted.
    after = _balances(client, h, ledger, "2026-04-30")
    assert (after.get("001200", Decimal(0)), after[debtor_no]) == (Decimal(0), Decimal("1000.00"))
    assert _stock(client, h, ledger, "2026-04-30") == [Decimal("1000.00")]
    original = _ok(client.get(f"{A}/ledgers/{ledger}/entries/{receivable['id']}", headers=h))
    assert original["status"] == "posted"
