"""M10 acceptance: ledger per legal entity (B01), balanced entries (B02), reversal instead of
overwrite with database guards (B03), gapless numbers under concurrency (B04), open items as
of a date (B07), no double effect on repeated clicks (B08), consistency checks (B09),
reviewed opening balances, locking, G1 for leading operation. Expected values are recomputed
by hand in the comments (rule 0.1.8): D04 transfer, D07 partial and overpayment."""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"l-{RUN}", name=f"Buch {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"l2-{RUN}", name=f"Buch2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("m10admin", a, "tenant_admin"),
            ("m10acc", a, "accountant_no_banking"),
            ("m10reader", a, "read_only"),
            ("m10clerk", a, "clerk_no_accounting"),
            ("m10other", b, "tenant_admin"),
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


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _code(response: Any) -> str:
    return str(response.json().get("code"))


def _prop(c: TestClient, h: dict[str, str], number: str, kind: str) -> dict[str, Any]:
    body = {"number": number, "name": f"Buchhaus {number}", "management_type": kind}
    return _ok(c.post("/api/v1/properties", json=body, headers=h), 201)  # type: ignore[no-any-return]


def _line(account: str, debit: str = "0", credit: str = "0") -> dict[str, str]:
    return {"account_id": account, "debit": debit, "credit": credit}


def _entry(kind: str, day: str, lines: list[dict[str, str]], **extra: Any) -> dict[str, Any]:
    return {"kind": kind, "booking_date": day, "text": f"{kind} {day}", "lines": lines, **extra}


def _book(c: TestClient, h: dict[str, str], ledger: str, body: dict[str, Any]) -> dict[str, Any]:
    draft = _ok(c.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h), 201)
    return _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))  # type: ignore[no-any-return]


def _accounts(c: TestClient, h: dict[str, str], ledger: str) -> dict[str, str]:
    rows = _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    return {a["number"]: a["id"] for a in rows}


def _hoa_ledger(c: TestClient, h: dict[str, str], number: str) -> tuple[str, dict[str, str], str]:
    prop = _prop(c, h, number, "hoa")
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(c, h, prop["id"], "01")
    owner, _ = _party(c, h, f"Eig{number}")
    _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": owner,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers",
            json={"legal_entity_id": hoa, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )
    accounts = _accounts(c, h, ledger["id"])
    debtor = next(n for n in accounts if n.startswith("09") and n != "009000" and n != "009999")
    return ledger["id"], accounts, accounts[debtor]


def test_ledger_per_legal_entity_open_items_and_reversal(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m10admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "701")
    assert {"001200", "008000", "060100", "009000"} <= set(acc)
    template = _ok(client.get(f"{A}/templates", headers=h))[0]
    assert template["released"] is False  # V8 open
    base = _ok(client.get(f"{A}/ledgers/{ledger}", headers=h))
    assert base["leading_system"] == "immoware24"

    # B02: unbalanced, single line, both sides.
    bad = client.post(
        f"{A}/ledgers/{ledger}/entries",
        json=_entry(
            "custom", "2026-01-05", [_line(debtor, "10"), _line(acc["060100"], "0", "9.99")]
        ),
        headers=h,
    )
    assert bad.status_code == 422
    assert _code(bad) == "MHVP-ACC-0001"
    both = _entry("custom", "2026-01-05", [_line(debtor, "1", "1"), _line(acc["060100"], "0", "0")])
    assert client.post(f"{A}/ledgers/{ledger}/entries", json=both, headers=h).status_code == 422
    fraction = _entry(
        "custom", "2026-01-05", [_line(debtor, "1.005"), _line(acc["060100"], "0", "1.005")]
    )
    assert client.post(f"{A}/ledgers/{ledger}/entries", json=fraction, headers=h).status_code == 422

    # D07: receivable 1.000,00; payment 600,00; payment 450,00 -> rest 0, credit 50,00.
    receivable = _book(
        client,
        h,
        ledger,
        _entry(
            "receivable",
            "2026-01-01",
            [_line(debtor, "1000.00"), _line(acc["060100"], "0", "1000.00")],
            due_date="2026-01-03",
        ),
    )
    assert receivable["number"] == 1
    item = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )
    assert len(item) == 1
    oi = item[0]["id"]
    assert Decimal(item[0]["remaining"]) == Decimal("1000.00")
    pay1 = _book(
        client,
        h,
        ledger,
        _entry(
            "debtor_payment",
            "2026-01-10",
            [_line(acc["001200"], "600.00"), _line(debtor, "0", "600.00")],
            settlements=[{"open_item_id": oi, "amount": "600.00"}],
        ),
    )
    rest = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-10"}, headers=h)
    )
    assert Decimal(rest[0]["remaining"]) == Decimal("400.00")
    too_much = _entry(
        "debtor_payment",
        "2026-01-20",
        [_line(acc["001200"], "450.00"), _line(debtor, "0", "450.00")],
        settlements=[{"open_item_id": oi, "amount": "450.00"}],
    )
    draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=too_much, headers=h), 201)
    assert (
        client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h).status_code
        == 422
    )
    _ok(client.delete(f"{A}/ledgers/{ledger}/entries/{draft['id']}", headers=h), 204)
    pay2 = _book(
        client,
        h,
        ledger,
        {**too_much, "settlements": [{"open_item_id": oi, "amount": "400.00"}]},
    )
    assert (
        _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h
            )
        )
        == []
    )
    # B07: as of 15.01. the rest of 400,00 is still open.
    mid = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-15"}, headers=h)
    )
    assert Decimal(mid[0]["remaining"]) == Decimal("400.00")
    tb = _ok(
        client.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-01-31"}, headers=h)
    )
    by = {a["number"]: a for a in tb["accounts"]}
    assert tb["balanced"] is True
    assert Decimal(by["060100"]["balance"]) == Decimal("-1000.00")  # credit 1.000, no extra income
    debtor_number = next(n for n, i in acc.items() if i == debtor)
    assert Decimal(by[debtor_number]["balance"]) == Decimal("-50.00")  # 1.000 - 600 - 450
    assert Decimal(by["001200"]["balance"]) == Decimal("1050.00")

    # B03: posted entries are immutable; reversal with reason.
    assert client.delete(f"{A}/ledgers/{ledger}/entries/{pay1['id']}", headers=h).status_code == 409
    assert (
        client.put(
            f"{A}/ledgers/{ledger}/entries/{pay1['id']}", json=too_much, headers=h
        ).status_code
        == 409
    )
    blocked = client.post(
        f"{A}/ledgers/{ledger}/entries/{receivable['id']}/reverse",
        json={"reason": "Falsch gebucht"},
        headers=h,
    )
    assert blocked.status_code == 409
    rev = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{pay2['id']}/reverse",
            json={"reason": "Rücklastschrift", "booking_date": "2026-02-02"},
            headers=h,
        ),
        201,
    )
    assert rev["kind"] == "reversal"
    assert rev["reverses_id"] == pay2["id"]
    assert rev["lines"][0]["credit"] == pay2["lines"][0]["debit"]
    again = client.post(
        f"{A}/ledgers/{ledger}/entries/{pay2['id']}/reverse", json={"reason": "doppelt"}, headers=h
    )
    assert again.status_code == 409
    assert (
        client.post(
            f"{A}/ledgers/{ledger}/entries/{rev['id']}/reverse",
            json={"reason": "zurück"},
            headers=h,
        ).status_code
        == 409
    )
    after = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-02-02"}, headers=h)
    )
    assert Decimal(after[0]["remaining"]) == Decimal("400.00")
    before = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )
    assert before == []  # history as of 31.01. is unchanged (B07)

    # Account sheet: opening + movements = closing (B09).
    sheet = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/accounts/{acc['001200']}/sheet",
            params={"start": "2026-01-15", "end": "2026-02-28"},
            headers=h,
        )
    )
    assert Decimal(sheet["opening_balance"]) == Decimal("600.00")
    assert Decimal(sheet["closing_balance"]) == Decimal("600.00")  # +450 then -450
    assert Decimal(sheet["opening_balance"]) + Decimal(sheet["debit"]) - Decimal(
        sheet["credit"]
    ) == Decimal(sheet["closing_balance"])
    checks = _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))
    assert checks == {"ok": True, "findings": []}

    # B01: a second legal entity has its own ledger; no cross postings or settlements.
    other_ledger, other_acc, _ = _hoa_ledger(client, h, "702")
    cross = _entry(
        "custom", "2026-01-05", [_line(debtor, "5"), _line(other_acc["060100"], "0", "5")]
    )
    wrong = client.post(f"{A}/ledgers/{other_ledger}/entries", json=cross, headers=h)
    assert wrong.status_code == 422
    assert _code(wrong) == "MHVP-ACC-0004"
    foreign = _entry(
        "debtor_payment",
        "2026-02-05",
        [_line(other_acc["001200"], "10"), _line(other_acc["060100"], "0", "10")],
        settlements=[{"open_item_id": oi, "amount": "10"}],
    )
    fdraft = _ok(client.post(f"{A}/ledgers/{other_ledger}/entries", json=foreign, headers=h), 201)
    fpost = client.post(f"{A}/ledgers/{other_ledger}/entries/{fdraft['id']}/post", headers=h)
    assert fpost.status_code == 422
    assert _code(fpost) == "MHVP-ACC-0004"
    duplicate = client.post(
        f"{A}/ledgers", json={"legal_entity_id": base["legal_entity_id"]}, headers=h
    )
    assert duplicate.status_code == 409

    # Tenant separation and permissions.
    other = bearer(login(client, world, "m10other"))
    assert client.get(f"{A}/ledgers/{ledger}", headers=other).status_code == 404
    reader = bearer(login(client, world, "m10reader"))
    assert client.get(f"{A}/ledgers/{ledger}/entries", headers=reader).status_code == 200
    assert (
        client.post(f"{A}/ledgers/{ledger}/entries", json=cross, headers=reader).status_code == 403
    )
    clerk = bearer(login(client, world, "m10clerk"))
    assert client.get(f"{A}/ledgers/{ledger}", headers=clerk).status_code == 403


def test_transfer_opening_balance_lock_and_gate(
    client: TestClient, world: World, database: Database
) -> None:
    h = bearer(login(client, world, "m10admin"))
    acc_user = bearer(login(client, world, "m10acc"))
    ledger, acc, debtor = _hoa_ledger(client, h, "703")
    bank_b = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={"number": "001202", "name": "Bank B", "category": "bank", "type": "asset"},
            headers=h,
        ),
        201,
    )["id"]
    dup = {"number": "001202", "name": "x", "category": "bank", "type": "asset"}
    assert client.post(f"{A}/ledgers/{ledger}/accounts", json=dup, headers=h).status_code == 409

    # Opening balances need a second person (reviewed opening balances).
    opening = _entry(
        "opening_balance",
        "2026-01-01",
        [
            _line(acc["001200"], "10000.00"),
            _line(bank_b, "20000.00"),
            _line(acc["009000"], "0", "30000.00"),
        ],
    )
    draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=opening, headers=h), 201)
    unapproved = client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h)
    assert unapproved.status_code == 403
    assert (
        client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/approve", headers=h).status_code
        == 403
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/approve", headers=acc_user))
    posted = _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    # B08: repeated click keeps the number and has no second effect.
    again = _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    assert again["number"] == posted["number"]

    # D04: transfer 1.000,00 from A to B -> A 9.000,00, B 21.000,00, total 30.000,00.
    _book(
        client,
        h,
        ledger,
        _entry(
            "bank_transfer",
            "2026-02-01",
            [_line(bank_b, "1000.00"), _line(acc["001200"], "0", "1000.00")],
        ),
    )
    tb = _ok(
        client.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-12-31"}, headers=h)
    )
    by = {a["number"]: Decimal(a["balance"]) for a in tb["accounts"]}
    assert by["001200"] == Decimal("9000.00")
    assert by["001202"] == Decimal("21000.00")
    assert by["001200"] + by["001202"] == Decimal("30000.00")
    assert not [a for a in tb["accounts"] if a["category"] in {"cost", "revenue"}]

    # Idempotency key returns the same draft.
    keyed = _entry(
        "custom",
        "2026-03-01",
        [_line(debtor, "5"), _line(acc["060100"], "0", "5")],
        idempotency_key="k1",
    )
    first = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=keyed, headers=h), 201)
    second = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=keyed, headers=h), 201)
    assert first["id"] == second["id"]

    # Database guards: posted lines cannot be changed even bypassing the API (B03).
    url = make_url(database.app_url).set(drivername="postgresql")
    with psycopg.connect(url.render_as_string(hide_password=False)) as conn:
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(world.tenant_a),))
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute(
                "UPDATE journal_line SET debit = 1 WHERE journal_entry_id = %s", (posted["id"],)
            )
        conn.rollback()
        conn.execute("SELECT set_config('app.tenant_id', %s, false)", (str(world.tenant_a),))
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("DELETE FROM journal_entry WHERE id = %s", (posted["id"],))
        conn.rollback()

    # Locking: no posting into the locked period; reversal gets an open date; no unlock.
    march = _ok(client.post(f"{A}/ledgers/{ledger}/entries/{first['id']}/post", headers=h))
    lock = _ok(
        client.post(f"{A}/ledgers/{ledger}/lock", json={"until": "2026-03-31"}, headers=acc_user)
    )
    assert lock["drafts_in_locked_period"] == 0
    late = _entry("custom", "2026-03-15", [_line(debtor, "7"), _line(acc["060100"], "0", "7")])
    late_draft = _ok(client.post(f"{A}/ledgers/{ledger}/entries", json=late, headers=h), 201)
    locked = client.post(f"{A}/ledgers/{ledger}/entries/{late_draft['id']}/post", headers=h)
    assert locked.status_code == 409
    assert _code(locked) == "MHVP-ACC-0002"
    in_lock = client.post(
        f"{A}/ledgers/{ledger}/entries/{march['id']}/reverse",
        json={"reason": "Korrektur", "booking_date": "2026-03-20"},
        headers=h,
    )
    assert in_lock.status_code == 409
    rev = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{march['id']}/reverse",
            json={"reason": "Korrektur"},
            headers=h,
        ),
        201,
    )
    assert rev["booking_date"] > "2026-03-31"
    assert (
        client.post(
            f"{A}/ledgers/{ledger}/lock", json={"until": "2026-01-31"}, headers=acc_user
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{A}/ledgers/{ledger}/lock", json={"until": "2026-04-30"}, headers=h
        ).status_code
        == 200
    )

    # Deactivated account cannot be used; accounts with postings cannot be deleted.
    assert client.delete(f"{A}/ledgers/{ledger}/accounts/{bank_b}", headers=h).status_code == 409
    _ok(client.patch(f"{A}/ledgers/{ledger}/accounts/{bank_b}", json={"active": False}, headers=h))
    unused = _entry("custom", "2026-06-01", [_line(bank_b, "1"), _line(acc["001200"], "0", "1")])
    assert client.post(f"{A}/ledgers/{ledger}/entries", json=unused, headers=h).status_code == 422

    # G1 closed: the platform cannot become the leading system.
    gate = client.post(
        f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=acc_user
    )
    assert gate.status_code == 403
    assert _code(gate) == "MHVP-GATE-0001"
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True


def test_gapless_numbers_under_concurrency(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Ten drafts posted in parallel sessions get numbers 1..n without gaps or duplicates."""
    from mhvp.accounting import services as svc
    from mhvp.accounting.models import JournalEntry, Ledger
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    h = bearer(login(client, world, "m10admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "704")
    ids = [
        _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json=_entry(
                    "custom", "2026-05-01", [_line(debtor, "1"), _line(acc["060100"], "0", "1")]
                ),
                headers=h,
            ),
            201,
        )["id"]
        for _ in range(10)
    ]

    async def run() -> list[int]:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)

        async def one(entry_id: str) -> int:
            async with tenant_transaction(factory, world.tenant_a) as session:
                led = await session.get(Ledger, uuid.UUID(ledger))
                entry = await session.get(JournalEntry, uuid.UUID(entry_id), with_for_update=True)
                assert led is not None
                assert entry is not None
                await svc.post(session, led, entry, None)
                return int(entry.number or 0)

        try:
            return list(await asyncio.gather(*(one(i) for i in ids)))
        finally:
            await engine.dispose()

    numbers = asyncio.run(run())
    assert sorted(numbers) == list(range(1, 11))
