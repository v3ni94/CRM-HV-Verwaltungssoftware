"""Query budget of list and detail endpoints (review 26.09.2026, performance).

A SQLAlchemy ``before_cursor_execute`` counter on the app engine records every statement of
one request. Lists and the start page must run a bounded number of statements independent of
the row count (no N+1): the budgets below are the accepted maxima, measured values are written
to ``docs/reviews/2026-09-26-performance.md``. Test data: 12 units with allocation values,
12 tenancies with payments and schedules, 12 journal entries, 12 invoices, one deposit with
movements, 12 parties of one contact."""

import asyncio
import os
import time
import uuid
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import (
    PASSWORD,
    RUN,
    World,
    _settings,
    bearer,
    login,
    login_password_only,
)
from tests.integration.test_m5_contracts import _party, _payment, _property, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
IBAN = "DE02120300000000202051"
N = 12
# Budget per request (statements including the tenant context of the transaction). A list
# must stay under 15 statements however many rows it returns (task 26.09.2026, item 4).
BUDGET = 15


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pf-{RUN}", name=f"Perf {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("pfadmin", "tenant_admin"), ("pfapprover", "tenant_admin")]:
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


class QueryCounter:
    """Counts statements on the app engine; the TestClient runs the app in another thread,
    the listener only appends to a list."""

    def __init__(self, client: TestClient) -> None:
        self.engine = cast(Any, client.app).state.resources.engine.sync_engine
        self.statements: list[str] = []

    def _listen(self, conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        self.statements.append(statement)

    def __enter__(self) -> "QueryCounter":
        event.listen(self.engine, "before_cursor_execute", self._listen)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(self.engine, "before_cursor_execute", self._listen)

    @property
    def count(self) -> int:
        return len(self.statements)


MEASUREMENTS: list[tuple[str, int, float]] = []


def _measure(
    client: TestClient, h: dict[str, str], label: str, path: str, **params: Any
) -> tuple[Any, int, dict[str, str]]:
    with QueryCounter(client) as counter:
        started = time.perf_counter()
        response = client.get(path, params=params or None, headers=h)
        duration = (time.perf_counter() - started) * 1000
    assert response.status_code == 200, response.text
    MEASUREMENTS.append((label, counter.count, duration))
    if os.environ.get("MHVP_PERF_DEBUG"):
        print(f"\n== {label}: {counter.count} statements")  # noqa: T201
        for statement in counter.statements:
            print("  ", " ".join(statement.split())[:160])  # noqa: T201
    return response.json(), counter.count, dict(response.headers)


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture(scope="module")
def data(client: TestClient, world: World) -> dict[str, Any]:
    h = bearer(login(client, world, "pfadmin"))
    approver = bearer(login(client, world, "pfapprover"))
    prop = _property(client, h, "901", "rental")
    owner, _ = _party(client, h, "Eigentuemer", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        )
    )
    keys = client.get(f"/api/v1/properties/{prop['id']}/allocation-keys", headers=h).json()
    mea = next(k for k in keys if k["code"] == "MEA")
    units: list[str] = []
    contracts: list[dict[str, Any]] = []
    tenants: list[str] = []
    payer: dict[str, Any] | None = None
    for i in range(N):
        unit = _unit(client, h, prop["id"], f"{i + 1:02d}")
        units.append(unit)
        _ok(
            client.post(
                f"/api/v1/units/{unit}/allocation-values",
                json={"allocation_key_id": mea["id"], "value": "10", "valid_from": "2020-01-01"},
                headers=h,
            )
        )
        tenant, contact = _party(client, h, f"Mieter{i}", iban=IBAN if i == 0 else None)
        if i == 0:
            payer = contact
        tenants.append(tenant)
        contract = _ok(
            client.post(
                "/api/v1/contracts",
                json={
                    "kind": "tenancy",
                    "unit_id": unit,
                    "party_id": tenant,
                    "start_date": "2026-01-01",
                },
                headers=h,
            )
        )
        contracts.append(contract)
        pay = f"/api/v1/contracts/{contract['id']}/payments"
        _ok(client.post(pay, json=_payment("800.00", "800.00", "2026-01-01"), headers=h))
        _ok(
            client.post(
                pay,
                json=_payment("150.00", "150.00", "2026-01-01", "operating_cost_advance"),
                headers=h,
            )
        )
        _ok(
            client.post(
                f"/api/v1/contracts/{contract['id']}/schedules",
                json={"valid_from": "2026-01-01", "due_day": 3},
                headers=h,
            )
        )
    assert payer is not None
    approve_bank_accounts(client, approver, payer["id"])
    entity = contracts[0]["legal_entity_id"]
    account_id = client.get(f"/api/v1/contacts/{payer['id']}", headers=h).json()["bank_accounts"][
        0
    ]["id"]
    mandate = _ok(
        client.post(
            "/api/v1/sepa-mandates",
            json={
                "party_id": tenants[0],
                "legal_entity_id": entity,
                "contact_bank_account_id": account_id,
                "reference": f"PF{RUN}"[:35],
                "creditor_id": "DE98ZZZ09999999999",
                "signed_at": "2026-01-01",
                "document_id": "0190a000-0000-7000-8000-000000000001",
            },
            headers=h,
        )
    )
    # Parties: one contact as member of N parties.
    member = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Multi", "last_name": f"Partei{RUN}"},
            headers=h,
        )
    )
    for i in range(N):
        other = _ok(
            client.post(
                "/api/v1/contacts",
                json={"kind": "person", "first_name": f"P{i}", "last_name": f"Mit{RUN}"},
                headers=h,
            )
        )
        _ok(
            client.post(
                "/api/v1/parties",
                json={
                    "members": [
                        {"contact_id": member["id"], "share_percent": "50"},
                        {"contact_id": other["id"], "share_percent": "50"},
                    ]
                },
                headers=h,
            )
        )
    # Ledger with N posted entries and N invoices.
    template = _ok(client.post(f"{A}/templates/default", headers=h))
    ledger = _ok(
        client.post(
            f"{A}/ledgers",
            json={"legal_entity_id": entity, "template_id": template["id"]},
            headers=h,
        )
    )["id"]
    account_rows = _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h), 200)
    cash = next(a["id"] for a in account_rows if a["category"] == "cash")
    expense = next(a["id"] for a in account_rows if a["category"] == "cost")
    for i in range(N):
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "custom",
                    "booking_date": f"2026-01-{i + 1:02d}",
                    "text": f"Buchung {i}",
                    "lines": [
                        {"account_id": expense, "debit": "10.00", "credit": "0"},
                        {"account_id": cash, "debit": "0", "credit": "10.00"},
                    ],
                },
                headers=h,
            )
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h), 200)
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Dienstleister {RUN} GmbH",
                "bank_accounts": [{"iban": IBAN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        )
    )["id"]
    approve_bank_accounts(client, approver, provider)
    for i in range(N):
        _ok(
            client.post(
                f"{A}/invoices",
                json={
                    "ledger_id": ledger,
                    "provider_contact_id": provider,
                    "number": f"PF-{i}",
                    "invoice_date": f"2026-02-{i + 1:02d}",
                    "net": "100.00",
                    "vat": "19.00",
                    "gross": "119.00",
                    "payee_iban": IBAN,
                    "lines": [
                        {
                            "account_id": expense,
                            "net": "100.00",
                            "vat_percent": "19",
                            "vat": "19.00",
                        }
                    ],
                },
                headers=h,
            )
        )
    return {
        "h": h,
        "property": prop["id"],
        "units": units,
        "contracts": contracts,
        "member": member["id"],
        "ledger": ledger,
        "mandate": mandate,
    }


def test_contracts_list_is_bounded(client: TestClient, data: dict[str, Any]) -> None:
    body, count, headers = _measure(client, data["h"], "GET /contracts", "/api/v1/contracts")
    assert len(body) == N
    assert body[0]["payments"]
    assert body[0]["schedules"]
    assert body[0]["debtor_account"]
    assert headers["x-total-count"] == str(N)
    assert count < BUDGET, f"{count} statements for {N} contracts"
    page, _, headers = _measure(
        client, data["h"], "GET /contracts?page=2", "/api/v1/contracts", page=2, page_size=5
    )
    assert len(page) == 5
    assert headers["x-total-count"] == str(N)
    assert headers["x-page"] == "2"
    versions, count, _ = _measure(
        client,
        data["h"],
        "GET /contracts/{id}/versions",
        f"/api/v1/contracts/{data['contracts'][0]['id']}/versions",
    )
    assert len(versions) == 1
    assert count < BUDGET


def test_units_list_is_bounded(client: TestClient, data: dict[str, Any]) -> None:
    body, count, _ = _measure(
        client,
        data["h"],
        "GET /properties/{id}/units",
        f"/api/v1/properties/{data['property']}/units",
    )
    assert len(body) == N
    assert all(u["allocation_values"] for u in body)
    assert count < BUDGET, f"{count} statements for {N} units"
    body, count, _ = _measure(
        client,
        data["h"],
        "GET /properties/{id}/units?as_of",
        f"/api/v1/properties/{data['property']}/units",
        as_of="2026-01-01",
    )
    assert len(body) == N
    assert count < BUDGET


def test_parties_list_is_bounded(client: TestClient, data: dict[str, Any]) -> None:
    body, count, _ = _measure(
        client, data["h"], "GET /parties?contact_id", "/api/v1/parties", contact_id=data["member"]
    )
    assert len(body) == N
    assert all(len(p["members"]) == 2 and p["members"][0]["display_name"] for p in body)
    assert count < BUDGET, f"{count} statements for {N} parties"


def test_journal_is_bounded(client: TestClient, data: dict[str, Any]) -> None:
    body, count, headers = _measure(
        client,
        data["h"],
        "GET /ledgers/{id}/entries",
        f"{A}/ledgers/{data['ledger']}/entries",
    )
    assert len(body) == N
    assert all(len(e["lines"]) == 2 for e in body)
    assert headers["x-total-count"] == str(N)
    assert count < BUDGET, f"{count} statements for {N} entries"
    page, _, headers = _measure(
        client,
        data["h"],
        "GET /ledgers/{id}/entries?page=2",
        f"{A}/ledgers/{data['ledger']}/entries",
        page=2,
        page_size=5,
    )
    assert len(page) == 5
    assert headers["x-page"] == "2"
    assert page[0]["number"] == body[5]["number"]


def test_invoices_list_is_bounded(client: TestClient, data: dict[str, Any]) -> None:
    body, count, headers = _measure(client, data["h"], "GET /invoices", f"{A}/invoices")
    assert len(body) == N
    assert all(len(i["lines"]) == 1 for i in body)
    assert headers["x-total-count"] == str(N)
    assert count < BUDGET, f"{count} statements for {N} invoices"


def test_mandates_list_is_bounded(client: TestClient, data: dict[str, Any]) -> None:
    body, count, headers = _measure(
        client, data["h"], "GET /sepa-mandates", "/api/v1/sepa-mandates"
    )
    assert body[0]["iban_masked"] == "DE02 **** **** 2051"
    assert headers["x-total-count"] == "1"
    assert count < BUDGET


def test_intake_proposals_list_is_bounded(client: TestClient, data: dict[str, Any]) -> None:
    _, count, _ = _measure(
        client, data["h"], "GET /documents/intake-proposals", "/api/v1/documents/intake-proposals"
    )
    assert count < BUDGET


def test_start_page_and_digest_are_bounded(client: TestClient, data: dict[str, Any]) -> None:
    _, count, _ = _measure(
        client, data["h"], "GET /workspace/dashboard", "/api/v1/workspace/dashboard"
    )
    assert count < BUDGET, f"dashboard: {count} statements"
    _, count, _ = _measure(client, data["h"], "GET /workspace/digest", "/api/v1/workspace/digest")
    assert count < BUDGET, f"digest: {count} statements"
    _, count, _ = _measure(
        client, data["h"], "GET /workspace/search", "/api/v1/workspace/search", q="Mieter"
    )
    assert count < BUDGET, f"search: {count} statements"
    _, count, _ = _measure(client, data["h"], "GET /documents", "/api/v1/documents")
    assert count < BUDGET
    _, count, _ = _measure(client, data["h"], "GET /contacts", "/api/v1/contacts")
    assert count < BUDGET
    _, count, _ = _measure(client, data["h"], "GET /properties", "/api/v1/properties")
    assert count < BUDGET


# Tenant and permission context (review 26.09.2026, open item 2) ---------------------------
#
# The bearer path resolves user, membership and host tenant on every request (locks are never
# cached) and serves roles and permissions from ``mhvp.core.auth.permission_cache`` (TTL at
# most 30 s, invalidated on role changes). Budget of the context up to the tenant domain
# lookup: 3 statements on a cache hit (user, membership, tenant domain) instead of 7 (plus
# set_config, roles, role inheritance, permissions); the eighth statement of the review is the
# set_config of the endpoint's own transaction.

AUTH_BUDGET_COLD = 7
AUTH_BUDGET_WARM = 3
ROLE_TABLES = ("membership_role", "role_permission")


def _auth_statements(counter: QueryCounter) -> list[str]:
    """Statements up to and including the tenant domain lookup of ``get_principal``."""
    out: list[str] = []
    for statement in counter.statements:
        out.append(statement)
        if "FROM tenant_domain" in statement:
            break
    return out


def _invite(
    client: TestClient, admin: dict[str, str], world: World, name: str, role: str
) -> tuple[uuid.UUID, uuid.UUID]:
    """Adds a member with a start password; returns (membership_id, user_id)."""
    created = _ok(
        client.post(
            "/api/v1/tenant/members",
            json={
                "email": world.email(name),
                "display_name": name,
                "password": PASSWORD,
                "role_codes": [role],
            },
            headers=admin,
        )
    )
    return uuid.UUID(created["membership_id"]), uuid.UUID(created["user_id"])


def test_permission_context_is_cached_per_process(client: TestClient, data: dict[str, Any]) -> None:
    from mhvp.core.auth.permission_cache import permission_cache

    permission_cache.clear()
    with QueryCounter(client) as cold:
        assert client.get("/api/v1/properties", headers=data["h"]).status_code == 200
    with QueryCounter(client) as warm:
        assert client.get("/api/v1/properties", headers=data["h"]).status_code == 200
    cold_auth = _auth_statements(cold)
    warm_auth = _auth_statements(warm)
    MEASUREMENTS.append(("Anmeldekontext kalt", len(cold_auth), 0.0))
    MEASUREMENTS.append(("Anmeldekontext warm", len(warm_auth), 0.0))
    assert len(cold_auth) == AUTH_BUDGET_COLD, cold_auth
    assert len(warm_auth) == AUTH_BUDGET_WARM, warm_auth
    assert any("membership_role" in s for s in cold_auth)
    assert not any(table in s for s in warm_auth for table in ROLE_TABLES)
    # Locks stay uncached: user and membership are read on the warm path as well.
    assert any("FROM app_user" in s for s in warm_auth)
    assert any("FROM membership " in s or "FROM membership\n" in s for s in warm_auth)
    assert warm.count == cold.count - (AUTH_BUDGET_COLD - AUTH_BUDGET_WARM)


def test_role_withdrawal_takes_effect_immediately(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    from mhvp.core.auth.permission_cache import permission_cache

    name = f"pfclerk{RUN}"
    membership_id, user_id = _invite(client, data["h"], world, name, "standard")
    h = bearer(login_password_only(client, world, name))
    assert client.get("/api/v1/contracts", headers=h).status_code == 200
    assert permission_cache.get(world.tenant_a, user_id, membership_id) is not None
    put = client.put(
        f"/api/v1/tenant/members/{membership_id}/roles",
        json={"role_codes": ["caretaker"]},
        headers=data["h"],
    )
    assert put.status_code == 204, put.text
    # Within the TTL, without waiting: the withdrawn permission is gone on the next request.
    denied = client.get("/api/v1/contracts", headers=h)
    assert denied.status_code == 403, denied.text
    assert client.get("/api/v1/properties", headers=h).status_code == 200


def test_membership_lock_takes_effect_immediately(
    client: TestClient, world: World, data: dict[str, Any]
) -> None:
    name = f"pflocked{RUN}"
    membership_id, _user_id = _invite(client, data["h"], world, name, "standard")
    h = bearer(login_password_only(client, world, name))
    assert client.get("/api/v1/properties", headers=h).status_code == 200
    locked = client.patch(
        f"/api/v1/tenant/members/{membership_id}",
        json={"status": "disabled"},
        headers=data["h"],
    )
    assert locked.status_code == 200, locked.text
    # The cache still holds the roles of the membership; the lock is read on every request.
    assert client.get("/api/v1/properties", headers=h).status_code in {401, 403}


def test_permission_cache_expires_and_is_bound_to_the_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mhvp.core.auth import permission_cache as module

    cache = module.PermissionCache(ttl_seconds=30)
    assert cache.ttl_seconds == 30
    assert module.PermissionCache(ttl_seconds=600).ttl_seconds == module.MAX_TTL_SECONDS
    tenant, user, membership = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    cache.put(tenant, user, membership, frozenset({"contracts:read"}), ("standard",))
    entry = cache.get(tenant, user, membership)
    assert entry is not None
    assert entry.roles == ("standard",)
    now[0] += 29.9
    assert cache.get(tenant, user, membership) is not None
    now[0] += 0.2
    assert cache.get(tenant, user, membership) is None  # expired after the TTL
    cache.put(tenant, user, membership, frozenset(), ())
    # A replaced membership (new id) never reuses the entry; the stale entry is dropped.
    assert cache.get(tenant, user, uuid.uuid4()) is None
    assert len(cache) == 0
    cache.put(tenant, user, membership, frozenset(), ())
    assert cache.invalidate(tenant, user) == 1
    cache.put(tenant, user, membership, frozenset(), ())
    cache.put(tenant, uuid.uuid4(), membership, frozenset(), ())
    assert cache.invalidate(tenant) == 2
    assert len(cache) == 0
    disabled = module.PermissionCache(ttl_seconds=0)
    disabled.put(tenant, user, membership, frozenset(), ())
    assert disabled.get(tenant, user, membership) is None


def test_zz_report_measurements() -> None:
    """Prints the measurements (``-s``) so the review document can be updated."""
    if os.environ.get("MHVP_PERF_REPORT"):
        for label, count, duration in MEASUREMENTS:
            print(f"| {label} | {count} | {duration:.1f} ms |")  # noqa: T201
