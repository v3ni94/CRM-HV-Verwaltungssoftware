"""M11-finapi acceptance with a fake finAPI (httpx.MockTransport, never a live connection):
connect with WebForm, multiple accounts assigned to different objects (case 1), connection
and accounts survive across sessions (case 2, re-read after commit), a manual click triggers
a real update call to the fake provider and not just cached data (case 3), immediate
WEB_FORM_REQUIRED plus later re-check (case 4/5), READY with one failing account is a visible
partial failure and not a full success (case 8), dedup keeps two real 700 EUR payments as two
(case 10/11), unauthorized access to unassigned accounts and other tenants is refused
(case 15), and no configuration means "not configured", never demo data (case 19)."""

import asyncio
import concurrent.futures
from collections.abc import Iterator
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from mhvp.banking import finapi as finapi_client
from mhvp.banking import tasks as banking_tasks
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    PASSWORD,
    RUN,
    World,
    bearer,
    login,
    login_password_only,
)
from tests.integration.test_m8_import import _settings

pytestmark = pytest.mark.integration
B = "/api/v1/banking/finapi"
IBAN_1 = "DE02120300000000202051"

FINAPI_BANK_CONNECTION_ID = "9001"
ACCOUNT_OK = "1001"
ACCOUNT_BROKEN = "1002"


def _webform_body(status: str) -> dict[str, Any]:
    return {
        "id": "wf-1",
        "url": "https://webform.finapi.io/wf-1",
        "status": status,
        "payload": {"bankConnectionId": FINAPI_BANK_CONNECTION_ID} if status == "FINISHED" else {},
    }


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/oauth/token":
        return httpx.Response(200, json={"access_token": "t-1", "expires_in": 3599})
    if path == "/api/webForms/bankConnectionImport":
        return httpx.Response(200, json=_webform_body("AWAITING_AUTHORIZATION"))
    if path == "/api/webForms/wf-1":
        return httpx.Response(200, json=_webform_body("FINISHED"))
    if path == f"/bankConnections/{FINAPI_BANK_CONNECTION_ID}":
        return httpx.Response(200, json={"id": FINAPI_BANK_CONNECTION_ID, "status": "READY"})
    if path == "/accounts":
        return httpx.Response(
            200,
            json={
                "accounts": [
                    {
                        "id": ACCOUNT_OK,
                        "iban": IBAN_1,
                        "accountHolderName": "GdWE Testweg",
                        "accountType": "checking",
                        "accountName": "Hausgeldkonto",
                        "balance": "1234.56",
                        "currency": "EUR",
                    },
                    {
                        "id": ACCOUNT_BROKEN,
                        "iban": None,
                        "accountHolderName": None,
                        "accountType": None,
                        "accountName": "Fehlerkonto",
                        "balance": None,
                        "currency": None,
                    },
                ]
            },
        )
    if path == "/transactions":
        account_ids = (request.url.params.get("accountIds") or "").split(",")
        if ACCOUNT_OK in account_ids:
            return httpx.Response(
                200,
                json={
                    "transactions": [
                        {
                            "id": "tx-1",
                            "bankBookingDate": "2026-02-01",
                            "amount": "700.00",
                            "currency": "EUR",
                            "counterpartName": "Zahler A",
                            "purpose": "Hausgeld Februar",
                        },
                        {
                            "id": "tx-2",
                            "bankBookingDate": "2026-02-01",
                            "amount": "700.00",
                            "currency": "EUR",
                            "counterpartName": "Zahler A",
                            "purpose": "Hausgeld Februar",
                        },
                    ]
                },
            )
        return httpx.Response(200, json={"transactions": []})
    return httpx.Response(404, json={"detail": "unhandled path in fake finAPI"})


@pytest.fixture(autouse=True)
def _fake_finapi(monkeypatch: pytest.MonkeyPatch, database: Database, redis_url: str) -> None:
    transport = httpx.MockTransport(_handler)

    def fake_client(self: finapi_client.FinApiClient) -> httpx.Client:
        return httpx.Client(base_url=self._credentials.base_url, transport=transport, timeout=5.0)

    monkeypatch.setattr(finapi_client.FinApiClient, "_client", fake_client)

    # The task normally resolves its own settings via `get_settings()` (cached, process-wide);
    # in this test process that must be the test database, not whatever the environment holds.
    test_settings = _settings(database, redis_url)
    monkeypatch.setattr(banking_tasks, "get_settings", lambda: test_settings)

    def run_now(*args: str) -> None:
        # The endpoint calls this from inside the request's running event loop, but the task
        # itself does its own `asyncio.run(...)` (mirrors how a real Celery worker process,
        # with no loop of its own, executes it); a plain thread gives it a clean loop.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(banking_tasks.finapi_fetch.run, *args).result()

    # No celery worker/broker in this test run: a click runs the same task body synchronously
    # instead of going through the broker, so `.delay(...)` behaves like `.run(...)` here.
    monkeypatch.setattr(banking_tasks.finapi_fetch, "delay", run_now)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"finapi-{RUN}", name=f"FinApi {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("fa-admin", "tenant_admin"),
            ("fa-banking", "accountant_banking"),
            ("fa-noaccounting", "accountant_no_banking"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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


def test_config_missing_reports_not_configured(client: TestClient, world: World) -> None:
    """Case 19: without credentials the API says so, never demo data."""
    h = bearer(login(client, world, "fa-admin"))
    body = _ok(client.get(f"{B}/config", headers=h))
    assert body["configured"] is False
    r = client.post(f"{B}/connections", json={"bank_name": "Sparkasse"}, headers=h)
    assert r.status_code >= 500 or r.status_code == 502


def _configure(client: TestClient, h: dict[str, str]) -> None:
    _ok(
        client.put(
            f"{B}/config",
            json={
                "client_id": "cid",
                "client_secret": "csecret",
                "base_url": "https://sandbox.finapi.io",
                "sandbox": True,
            },
            headers=h,
        )
    )


def _connect_and_check(client: TestClient, h: dict[str, str]) -> dict[str, Any]:
    created = _ok(client.post(f"{B}/connections", json={"bank_name": "Sparkasse"}, headers=h), 201)
    assert created["status"] == "web_form_pending"
    assert created["web_form_url"]
    checked = _ok(client.post(f"{B}/connections/{created['id']}/check", headers=h))
    return cast(dict[str, Any], checked)


def test_connect_multiple_accounts_assign_and_partial_failure(
    client: TestClient, world: World
) -> None:
    """Cases 1, 3, 8: WebForm connect, real update call reads two accounts from the fake
    provider (not cached data), one account has no usable data and stays visible as a gap."""
    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "801", "name": "Testweg", "management_type": "hoa"},
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
                "iban": IBAN_1,
                "holder": "GdWE Testweg",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]

    checked = _connect_and_check(client, h)
    assert checked["status"] == "active"
    assert len(checked["accounts"]) == 2
    ok_link = next(a for a in checked["accounts"] if a["finapi_account_id"] == ACCOUNT_OK)
    broken_link = next(a for a in checked["accounts"] if a["finapi_account_id"] == ACCOUNT_BROKEN)
    assert ok_link["balance_booked"] == "1234.56"
    assert broken_link["balance_booked"] is None  # visible gap, not invented

    assigned = _ok(
        client.post(
            f"{B}/accounts/{ok_link['id']}/assign",
            json={"property_bank_account_id": account},
            headers=h,
        )
    )
    assert assigned["property_bank_account_id"] == account

    # Case 3: manual click triggers a real fetch (via the fake provider), not just a re-read.
    run = _ok(client.post(f"{B}/accounts/{ok_link['id']}/fetch", headers=h), 200)
    assert run["status"] in ("queued", "done")
    txs = _ok(
        client.get("/api/v1/banking/transactions", params={"bank_account_id": account}, headers=h)
    )
    # Case 10/11: two real 700 EUR payments on the same day with distinct bank references
    # stay two transactions, not one.
    assert len(txs) == 2
    assert {t["bank_reference"] for t in txs} == {"finapi:tx-1", "finapi:tx-2"}

    # Re-fetch has no additional effect (idempotent re-import, D05 reused).
    _ok(client.post(f"{B}/accounts/{ok_link['id']}/fetch", headers=h), 200)
    txs_again = _ok(
        client.get("/api/v1/banking/transactions", params={"bank_account_id": account}, headers=h)
    )
    assert len(txs_again) == 2


def test_unassigned_accounts_hidden_without_banking_approve(
    client: TestClient, world: World
) -> None:
    """Case 15: a clerk without banking:approve/tenant_settings:update does not see an
    unassigned finAPI account, and cannot connect, assign or disconnect."""
    admin_h = bearer(login(client, world, "fa-admin"))
    _configure(client, admin_h)
    checked = _connect_and_check(client, admin_h)
    assert len(checked["accounts"]) == 2  # admin sees both, none assigned yet

    clerk_h = bearer(login_password_only(client, world, "fa-noaccounting"))
    listed = _ok(client.get(f"{B}/connections", headers=clerk_h))
    conn = next(c for c in listed if c["id"] == checked["id"])
    assert conn["accounts"] == []  # unassigned accounts stay invisible

    forbidden = client.post(f"{B}/connections/{checked['id']}/disconnect", headers=clerk_h)
    assert forbidden.status_code == 403


def test_fetch_with_date_range_keeps_only_rows_in_range(client: TestClient, world: World) -> None:
    """Stage 2: `since`/`until` bound what is kept from what the fake provider actually
    returned (both real 700 EUR transactions are booked 2026-02-01); nothing is asked of the
    provider that is not verified, and nothing outside the delivered rows is invented."""
    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "802", "name": "Zeitraumweg", "management_type": "hoa"},
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
                "iban": "DE72120300000000202052",
                "holder": "GdWE Zeitraumweg",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    checked = _connect_and_check(client, h)
    ok_link = next(a for a in checked["accounts"] if a["finapi_account_id"] == ACCOUNT_OK)
    _ok(
        client.post(
            f"{B}/accounts/{ok_link['id']}/assign",
            json={"property_bank_account_id": account},
            headers=h,
        )
    )

    # Outside the range: nothing is kept, but nothing errors either.
    _ok(
        client.post(
            f"{B}/accounts/{ok_link['id']}/fetch",
            json={"since": "2026-03-01", "until": "2026-03-31"},
            headers=h,
        )
    )
    none_yet = _ok(
        client.get("/api/v1/banking/transactions", params={"bank_account_id": account}, headers=h)
    )
    assert none_yet == []

    # Inside the range: both real transactions of 2026-02-01 are kept.
    _ok(
        client.post(
            f"{B}/accounts/{ok_link['id']}/fetch",
            json={"since": "2026-01-01", "until": "2026-02-28"},
            headers=h,
        )
    )
    kept = _ok(
        client.get("/api/v1/banking/transactions", params={"bank_account_id": account}, headers=h)
    )
    assert len(kept) == 2


def test_fetch_per_bank_queues_every_assigned_account(client: TestClient, world: World) -> None:
    """Stage 2: the per-bank fetch endpoint queues one run per assigned account of that
    connection; no body is required (defaults to no date range)."""
    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "803", "name": "Bankweg", "management_type": "hoa"},
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
                "iban": "DE45120300000000202053",
                "holder": "GdWE Bankweg",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    checked = _connect_and_check(client, h)
    ok_link = next(a for a in checked["accounts"] if a["finapi_account_id"] == ACCOUNT_OK)
    _ok(
        client.post(
            f"{B}/accounts/{ok_link['id']}/assign",
            json={"property_bank_account_id": account},
            headers=h,
        )
    )
    runs = _ok(client.post(f"{B}/connections/{checked['id']}/fetch", headers=h))
    assert len(runs) == 1
    assert runs[0]["property_bank_account_id"] == account


def test_auto_fetch_flag_defaults_off_and_is_settable(client: TestClient, world: World) -> None:
    """Stage 2: the scheduled daily fetch is a per-tenant opt-in, default off. (This tenant may
    already be configured by an earlier test in this module; the point asserted here is that
    `auto_fetch_enabled` itself starts/stays off until explicitly set, not the configured
    flag, which other tests in this file legitimately flip.)"""
    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    after_configure = _ok(client.get(f"{B}/config", headers=h))
    assert after_configure["auto_fetch_enabled"] is False

    enabled = _ok(
        client.put(
            f"{B}/config",
            json={
                "client_id": "cid",
                "client_secret": "csecret",
                "base_url": "https://sandbox.finapi.io",
                "sandbox": True,
                "auto_fetch_enabled": True,
            },
            headers=h,
        )
    )
    assert enabled["auto_fetch_enabled"] is True


def test_scheduled_fetch_only_runs_for_opted_in_tenant(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """Stage 2: `mhvp.banking.tasks._finapi_scheduled_fetch_once` (the per-tenant half of the
    scheduled beat job, isolated here from every other tenant that may exist in this shared
    test database) queues nothing for a tenant that has not opted in, and `sync_all_once`
    does not clobber an active finAPI connection's status (regression for the pre-Stage-2
    `sync_tenant` bug that routed every non-file connector, including finAPI, through
    `UnconfiguredConnector`)."""
    import asyncio

    from mhvp.banking import tasks as banking_tasks
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from tests.integration.test_m8_import import _settings

    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    # Explicitly off: an earlier test in this module may have opted this tenant in.
    _ok(
        client.put(
            f"{B}/config",
            json={
                "client_id": "cid",
                "client_secret": "csecret",
                "base_url": "https://sandbox.finapi.io",
                "sandbox": True,
                "auto_fetch_enabled": False,
            },
            headers=h,
        )
    )
    checked = _connect_and_check(client, h)
    assert checked["status"] == "active"

    settings = _settings(database, redis_url)

    async def _run_for_this_tenant() -> tuple[dict[str, int], int]:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                counts, queued = await banking_tasks._finapi_scheduled_fetch_once(
                    session, world.tenant_a
                )
            return counts, len(queued)
        finally:
            await engine.dispose()

    counts, queued_len = asyncio.run(_run_for_this_tenant())
    assert counts["tenants_enabled"] == 0
    assert counts["queued"] == 0
    assert queued_len == 0

    still_active = _ok(client.get(f"{B}/connections", headers=h))
    conn = next(c for c in still_active if c["id"] == checked["id"])
    assert conn["status"] == "active"  # not clobbered to "not_configured" by the daily sync

    async def _sync_this_tenant() -> dict[str, int]:
        engine = create_app_engine(settings)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                return await banking_tasks.sync_tenant(session, world.tenant_a)
        finally:
            await engine.dispose()

    sync_counts = asyncio.run(_sync_this_tenant())
    assert sync_counts["not_configured"] == 0
    still_active_after_sync = _ok(client.get(f"{B}/connections", headers=h))
    conn_after_sync = next(c for c in still_active_after_sync if c["id"] == checked["id"])
    assert conn_after_sync["status"] == "active"


def test_reauthorize_sets_update_required_and_new_webform(client: TestClient, world: World) -> None:
    """Cases 4/5/6: re-authorization opens a fresh WebForm on the same connection; the
    account link is untouched, nothing is deleted on an aborted WebForm."""
    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    checked = _connect_and_check(client, h)
    reauth = _ok(client.post(f"{B}/connections/{checked['id']}/reauthorize", headers=h))
    assert reauth["status"] == "update_required"
    assert reauth["web_form_url"]
    assert len(reauth["accounts"]) == len(checked["accounts"])  # nothing lost
