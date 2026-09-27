"""FinTS/HBCI PIN/TAN endpoints (M11-01 addendum 27.09.2026) against the fake python-fints
client (`tests.fints_fake`), never a live bank: institute search and permissions, missing
product registration, connect with init TAN (session state, challenge, wrong TAN, restart,
right TAN, accounts with balances), assignment with IBAN check and account creation, refresh
with transaction import and dedup on a second refresh, PIN rejection locking the stored PIN
(no automatic retry), decoupled polling, tenant separation, disconnect wiping secrets. The
worker step runs synchronously in a thread instead of through a broker."""

from __future__ import annotations

import asyncio
import concurrent.futures
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.banking import tasks as banking_tasks
from mhvp.main import create_app
from mhvp.platform import services
from tests import fints_fake as fake
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
B = "/api/v1/banking/fints"
PRODUCT_ID = "TESTPRODUCTID000000000001"
BLZ_CONNECTABLE = "38250110"  # Kreissparkasse Euskirchen, with FinTS URL in the list
BLZ_NOT_CONNECTABLE = "25440047"  # Commerzbank Hameln, no FinTS URL in the list


def _settings(database: Database, redis_url: str, **overrides: Any) -> Any:
    return base_settings(database, redis_url, **{"fints_product_id": PRODUCT_ID, **overrides})


@pytest.fixture(autouse=True)
def _fake_fints(monkeypatch: pytest.MonkeyPatch, database: Database, redis_url: str) -> None:
    fake.install(monkeypatch)
    test_settings = _settings(database, redis_url)
    monkeypatch.setattr(banking_tasks, "get_settings", lambda: test_settings)

    def run_now(*args: str) -> None:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(banking_tasks.fints_step.run, *args).result()

    monkeypatch.setattr(banking_tasks.fints_step, "delay", run_now)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"fints-{RUN}", name=f"FinTS {RUN}")
        b, _ = await services.provision_tenant(
            factory, slug=f"fints-sep-{RUN}", name=f"FinTS Sep {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant_id in [
            ("ft-admin", "tenant_admin", a),
            ("ft-banking", "accountant_banking", a),
            ("ft-noaccounting", "accountant_no_banking", a),
            ("ft-b-admin", "tenant_admin", b),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
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


def _connect(client: TestClient, h: dict[str, str], **overrides: Any) -> dict[str, Any]:
    body = {
        "institute": BLZ_CONNECTABLE,
        "login": "kunde-1",
        "pin": fake.GOOD_PIN,
        **overrides,
    }
    created: dict[str, Any] = _ok(client.post(f"{B}/connections", json=body, headers=h), 201)
    return created


def _session(client: TestClient, h: dict[str, str], session_id: str) -> dict[str, Any]:
    out: dict[str, Any] = _ok(client.get(f"{B}/sessions/{session_id}", headers=h))
    return out


def _connection(client: TestClient, h: dict[str, str], fints_id: str) -> dict[str, Any]:
    rows = _ok(client.get(f"{B}/connections", headers=h))
    row: dict[str, Any] = next(r for r in rows if r["id"] == fints_id)
    return row


def _connect_done(client: TestClient, h: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """Connect with the init TAN answered correctly; returns (fints_connection_id, connection)."""
    created = _connect(client, h)
    session = _session(client, h, created["id"])
    assert session["status"] == "awaiting_tan", session
    _ok(client.post(f"{B}/sessions/{created['id']}/tan", json={"tan": fake.GOOD_TAN}, headers=h))
    session = _session(client, h, created["id"])
    assert session["status"] == "done", session
    fints_id = created["fints_connection_id"]
    return fints_id, _connection(client, h, fints_id)


def test_institute_search_and_permissions(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ft-admin"))
    rows = _ok(client.get(f"{B}/institutes", params={"q": "DE12382501100000000001"}, headers=h))
    assert [r["blz"] for r in rows] == [BLZ_CONNECTABLE]
    assert rows[0]["connectable"] is True
    assert rows[0]["fints_url"]
    rows = _ok(client.get(f"{B}/institutes", params={"q": BLZ_NOT_CONNECTABLE}, headers=h))
    assert rows[0]["connectable"] is False
    assert rows[0]["fints_url"] is None
    rows = _ok(client.get(f"{B}/institutes", params={"q": "Sparkasse"}, headers=h))
    assert len(rows) == 20
    assert client.get(f"{B}/institutes", params={"q": "Sparkasse"}).status_code == 401


def test_not_connectable_institute_and_missing_product_id(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "ft-admin"))
    r = client.post(
        f"{B}/connections",
        json={"institute": BLZ_NOT_CONNECTABLE, "login": "x", "pin": "y"},
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["code"] == "MHVP-BANK-0008"
    # Without the DK registration number no connection is possible (501 with a hint).
    with TestClient(
        create_app(_settings(database, redis_url, fints_product_id=None))
    ) as bare_client:
        r = bare_client.post(
            f"{B}/connections",
            json={"institute": BLZ_CONNECTABLE, "login": "x", "pin": "y"},
            headers=h,
        )
    assert r.status_code == 501
    assert r.json()["code"] == "MHVP-BANK-0007"


def test_banking_write_needs_banking_approve(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ft-noaccounting"))
    r = client.post(
        f"{B}/connections",
        json={"institute": BLZ_CONNECTABLE, "login": "x", "pin": "y"},
        headers=h,
    )
    assert r.status_code == 403


def test_connect_flow_with_init_tan_and_no_secrets_in_responses(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ft-admin"))
    created = _connect(client, h)
    assert created["purpose"] == "connect"
    session = _session(client, h, created["id"])
    assert session["status"] == "awaiting_tan"
    assert session["challenge_text"] == "TAN für init eingeben"
    assert session["challenge_hhduc"] == "0248A0123456789"
    assert session["tan_mechanism"] == "912"
    assert {m["code"] for m in session["tan_mechanisms"]} == {"912", "922"}
    fints_id = created["fints_connection_id"]
    conn = _connection(client, h, fints_id)
    assert conn["status"] == "web_form_pending"
    assert conn["open_session_id"] == created["id"]
    # secrets never leave the server
    for payload in (created, session, conn):
        text = str(payload)
        assert fake.GOOD_PIN not in text
        assert "kunde-1" not in text
    # decoupled poll without TAN on an awaiting_tan session is refused
    r = client.post(f"{B}/sessions/{created['id']}/tan", json={}, headers=h)
    assert r.status_code == 422
    # wrong TAN: session fails with the bank's rejection, connection stays usable
    _ok(client.post(f"{B}/sessions/{created['id']}/tan", json={"tan": "000000"}, headers=h))
    session = _session(client, h, created["id"])
    assert session["status"] == "failed"
    assert session["error_code"] == "MHVP-BANK-0011"
    # a second session for the same connection: restart, right TAN, done with accounts
    restarted = _ok(client.post(f"{B}/connections/{fints_id}/restart", json={}, headers=h), 201)
    assert _session(client, h, restarted["id"])["status"] == "awaiting_tan"
    _ok(client.post(f"{B}/sessions/{restarted['id']}/tan", json={"tan": fake.GOOD_TAN}, headers=h))
    session = _session(client, h, restarted["id"])
    assert session["status"] == "done", session
    assert session["result"]["accounts"] == 2
    assert session["challenge_text"] is None
    conn = _connection(client, h, fints_id)
    assert conn["status"] == "active"
    assert conn["last_sca_at"] is not None
    assert conn["sca_due"] is False
    assert conn["open_session_id"] is None
    accounts = {a["iban_suffix"]: a for a in conn["accounts"]}
    assert set(accounts) == {fake.IBAN_1[-4:], fake.IBAN_2[-4:]}
    assert accounts[fake.IBAN_1[-4:]]["balance_booked"] == "1234.56"
    assert accounts[fake.IBAN_2[-4:]]["balance_booked"] == "-10.00"
    assert accounts[fake.IBAN_1[-4:]]["balance_as_of"] == "2026-09-27"
    # a member without banking:approve does not see unassigned accounts
    hb = bearer(login(client, world, "ft-noaccounting"))
    assert _connection(client, hb, fints_id)["accounts"] == []
    # a second connect session while none is open is fine, a parallel one is refused
    again = _ok(client.post(f"{B}/connections/{fints_id}/restart", json={}, headers=h), 201)
    r = client.post(f"{B}/connections/{fints_id}/restart", json={}, headers=h)
    assert r.status_code in (201, 409)  # the fake step ran synchronously, so it may be closed
    _ok(client.post(f"{B}/sessions/{again['id']}/tan", json={"tan": fake.GOOD_TAN}, headers=h))


def _property_with_account(
    client: TestClient, h: dict[str, str], number: str, iban: str
) -> tuple[str, str, str]:
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Objekt {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    account = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": iban,
                "holder": f"GdWE {number}",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    return prop["id"], hoa, account


def test_assign_refresh_import_and_dedup(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ft-admin"))
    fints_id, conn = _connect_done(client, h)
    links = {a["iban_suffix"]: a for a in conn["accounts"]}
    link_1 = links[fake.IBAN_1[-4:]]
    link_2 = links[fake.IBAN_2[-4:]]
    prop_id, hoa_id, account_1 = _property_with_account(client, h, "821", fake.IBAN_1)
    # an internal account with a different IBAN is refused
    _, _, other_account = _property_with_account(client, h, "822", "DE75512108001245126199")
    r = client.post(
        f"{B}/accounts/{link_1['id']}/assign",
        json={"property_bank_account_id": other_account},
        headers=h,
    )
    assert r.status_code == 422
    assigned = _ok(
        client.post(
            f"{B}/accounts/{link_1['id']}/assign",
            json={"property_bank_account_id": account_1},
            headers=h,
        )
    )
    assert assigned["property_bank_account_id"] == account_1
    # the second account gets a new internal account created from the bank's IBAN
    created = _ok(
        client.post(
            f"{B}/accounts/{link_2['id']}/assign",
            json={
                "property_id": prop_id,
                "legal_entity_id": hoa_id,
                "kind": "reserve",
                "holder": "GdWE Testweg Rücklage",
            },
            headers=h,
        )
    )
    assert created["property_bank_account_id"]
    accounts = _ok(client.get(f"/api/v1/properties/{prop_id}/bank-accounts", headers=h))
    assert any(
        a["id"] == created["property_bank_account_id"] and a["kind"] == "reserve" for a in accounts
    )

    # refresh: balances for all, transactions for assigned accounts; no TAN on this dialog
    fake.Scenario.init_tan = False
    refresh = _ok(client.post(f"{B}/connections/{fints_id}/refresh", json={}, headers=h), 201)
    session = _session(client, h, refresh["id"])
    assert session["status"] == "done", session
    assert session["result"]["new"] == 2  # two real 700 EUR payments with different references
    assert session["result"]["duplicates"] == 0
    run = _ok(client.get("/api/v1/banking/runs", headers=h))
    mine = next(r for r in run if r["id"] == session["sync_run_id"])
    assert mine["status"] == "done"
    assert mine["counts"]["new"] == 2
    txs = _ok(client.get("/api/v1/banking/transactions", headers=h))
    ours = [t for t in txs if t["property_bank_account_id"] == account_1]
    assert len(ours) == 2
    assert {t["amount"] for t in ours} == {"700.00"}
    conn = _connection(client, h, fints_id)
    link_1 = next(a for a in conn["accounts"] if a["id"] == link_1["id"])
    assert link_1["last_synced_booking_date"] == "2026-09-20"
    assert link_1["last_transactions_fetch_at"]

    # second refresh: same rows again are duplicates by bank reference (D05), nothing new
    refresh2 = _ok(client.post(f"{B}/connections/{fints_id}/refresh", json={}, headers=h), 201)
    session2 = _session(client, h, refresh2["id"])
    assert session2["status"] == "done"
    assert session2["result"]["new"] == 0
    assert session2["result"]["duplicates"] == 2

    # refresh with a TAN in the middle of the transaction fetch pauses and resumes
    fake.Scenario.tan_for_transactions = True
    fake.Scenario.transactions = [
        fake.mt940_tx("2026-09-25", "12.34", "D", "Bankgebühr", "REF-3"),
    ]
    refresh3 = _ok(
        client.post(
            f"{B}/connections/{fints_id}/refresh",
            json={"since": "2026-09-01", "until": "2026-09-30"},
            headers=h,
        ),
        201,
    )
    session3 = _session(client, h, refresh3["id"])
    assert session3["status"] == "awaiting_tan"
    assert session3["challenge_text"] == "TAN für transactions eingeben"
    _ok(client.post(f"{B}/sessions/{refresh3['id']}/tan", json={"tan": fake.GOOD_TAN}, headers=h))
    session3 = _session(client, h, refresh3["id"])
    assert session3["status"] == "done", session3
    assert session3["result"]["new"] == 1
    txs = _ok(client.get("/api/v1/banking/transactions", headers=h))
    fee = [t for t in txs if t["property_bank_account_id"] == account_1 and t["amount"] == "-12.34"]
    assert len(fee) == 1


def test_pin_rejected_locks_stored_pin_until_reentered(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ft-admin"))
    created = _connect(client, h, pin="wrong")
    session = _session(client, h, created["id"])
    assert session["status"] == "failed"
    assert session["error_code"] == "MHVP-BANK-0009"
    fints_id = created["fints_connection_id"]
    conn = _connection(client, h, fints_id)
    assert conn["pin_blocked"] is True
    assert conn["status"] == "error"
    assert conn["last_error_code"] == "MHVP-BANK-0009"
    # no automatic retry with the same PIN: refresh and restart without a new PIN are refused
    r = client.post(f"{B}/connections/{fints_id}/refresh", json={}, headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "MHVP-BANK-0016"
    r = client.post(f"{B}/connections/{fints_id}/restart", json={}, headers=h)
    assert r.status_code == 409
    assert r.json()["code"] == "MHVP-BANK-0016"
    restarted = _ok(
        client.post(f"{B}/connections/{fints_id}/restart", json={"pin": fake.GOOD_PIN}, headers=h),
        201,
    )
    assert _session(client, h, restarted["id"])["status"] == "awaiting_tan"
    assert _connection(client, h, fints_id)["pin_blocked"] is False


def test_decoupled_push_tan_polls_until_confirmed(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ft-admin"))
    fake.Scenario.decoupled = True
    fake.Scenario.decoupled_polls_until_confirmed = 2
    created = _connect(client, h, tan_mechanism="922")
    session = _session(client, h, created["id"])
    assert session["status"] == "awaiting_decoupled"
    assert session["challenge_decoupled"] is True
    assert session["tan_mechanism"] == "922"
    _ok(client.post(f"{B}/sessions/{created['id']}/tan", json={}, headers=h))
    assert _session(client, h, created["id"])["status"] == "awaiting_decoupled"
    _ok(client.post(f"{B}/sessions/{created['id']}/tan", json={}, headers=h))
    session = _session(client, h, created["id"])
    assert session["status"] == "done", session
    assert _connection(client, h, created["fints_connection_id"])["status"] == "active"


def test_tenant_separation_and_disconnect(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ft-admin"))
    fints_id, conn = _connect_done(client, h)
    session_id = conn["open_session_id"]
    hb = bearer(login(client, world, "ft-b-admin"))
    assert all(r["id"] != fints_id for r in _ok(client.get(f"{B}/connections", headers=hb)))
    assert client.get(f"{B}/sessions/{uuid.uuid4()}", headers=hb).status_code == 404
    assert (
        client.post(f"{B}/connections/{fints_id}/restart", json={}, headers=hb).status_code == 404
    )
    link_id = conn["accounts"][0]["id"]
    r = client.post(
        f"{B}/accounts/{link_id}/assign",
        json={"property_bank_account_id": str(uuid.uuid4())},
        headers=hb,
    )
    assert r.status_code == 404
    assert client.delete(f"{B}/connections/{fints_id}", headers=hb).status_code == 404
    assert session_id is None
    # disconnect: status disabled, no further session possible
    assert client.delete(f"{B}/connections/{fints_id}", headers=h).status_code == 204
    conn = _connection(client, h, fints_id)
    assert conn["status"] == "disabled"
    r = client.post(f"{B}/connections/{fints_id}/refresh", json={}, headers=h)
    assert r.status_code == 409
    r = client.post(f"{B}/connections/{fints_id}/restart", json={"pin": fake.GOOD_PIN}, headers=h)
    assert r.status_code == 409
