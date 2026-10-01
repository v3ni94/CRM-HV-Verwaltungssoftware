"""Q01 gap list 30.09.2026: central approval decisions (S69-02), person check of two approvers
with a warning (S69-03), maintained open item remainders as of a cut-off date (S69-04),
creditor account on adding a provider relation (M10-05), monthly preview switch (P02-03).

Expected values by hand (rule 0.1.8): receivable 1.000,00 EUR, payment 600,00 EUR on
10.01.2026: remainder as of 05.01.2026 = 1.000,00, as of 31.01.2026 = 400,00."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import A, _book, _entry, _hoa_ledger, _line, _ok

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
PROVIDER = "DE89370400440532013000"
OWN = "DE02120300000000202051"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q01-{RUN}", name=f"Q01 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q01b-{RUN}", name=f"Q01b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("q01admin", a, "tenant_admin"),
            ("q01acc", a, "accountant_banking"),
            ("q01approver", a, "tenant_admin"),
            ("q01reader", a, "read_only"),
            ("q01other", b, "tenant_admin"),
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


def _link_contact(world: World, name: str, contact_id: str) -> None:
    engine = create_engine(world.app_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE membership SET contact_id = :c WHERE user_id = :u AND tenant_id = :t"),
            {"c": contact_id, "u": world.users[name], "t": world.tenant_a},
        )
    engine.dispose()


def _property_of(c: TestClient, h: dict[str, str], ledger: str) -> str:
    return str(_ok(c.get(f"{A}/ledgers/{ledger}", headers=h))["property_id"])


def test_m10_05_creditor_account_on_provider_relation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q01admin"))
    ledger, _, _ = _hoa_ledger(client, h, "911")
    prop = _property_of(client, h, ledger)
    person = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "person", "last_name": f"Q01K{RUN}"}, headers=h
        ),
        201,
    )
    rel = _ok(
        client.post(
            f"/api/v1/properties/{prop}/service-providers",
            json={
                "contact_id": person["id"],
                "contract_type_code": "caretaker",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    accounts = _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    creditors = [a for a in accounts if a["category"] == "creditor"]
    assert len(creditors) == 1
    assert creditors[0]["number"].startswith("07")
    assert rel["creditor_account_id"] == creditors[0]["id"]


def test_p02_03_monthly_preview_switch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q01admin"))
    body = {
        "enabled": False,
        "proration_method": "calendar_days",
        "vat_enabled": False,
        "payment_interval": None,
        "monthly_preview_enabled": True,
    }
    out = _ok(client.patch("/api/v1/tenant/settings", json={"receivable_rules": body}, headers=h))
    assert out["receivable_rules"]["monthly_preview_enabled"] is True
    bad = client.patch(
        "/api/v1/tenant/settings",
        json={"receivable_rules": {**body, "monthly_preview_enabled": "vielleicht"}},
        headers=h,
    )
    assert bad.status_code == 422


def test_s69_04_open_item_balances(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q01admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "912")
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
    item = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )[0]
    _book(
        client,
        h,
        ledger,
        _entry(
            "debtor_payment",
            "2026-01-10",
            [_line(acc["001200"], "600.00"), _line(debtor, "0", "600.00")],
            settlements=[{"open_item_id": item["id"], "amount": "600.00"}],
        ),
    )
    assert receivable["status"] == "posted"
    url = f"{A}/ledgers/{ledger}/open-item-balances"
    assert _ok(client.get(url, headers=h))["as_of"] is None  # nothing refreshed yet
    early = _ok(client.post(f"{url}/refresh", json={"as_of": "2026-01-05"}, headers=h))
    assert [i["remaining"] for i in early["items"]] == ["1000.00"]
    late = _ok(client.post(f"{url}/refresh", json={"as_of": "2026-01-31"}, headers=h))
    assert [i["remaining"] for i in late["items"]] == ["400.00"]
    assert late["total_receivable"] == "400.00"
    assert late["total_payable"] == "0.00"
    # Repeating the refresh replaces the rows (idempotent), latest cut-off date by default.
    _ok(client.post(f"{url}/refresh", json={"as_of": "2026-01-31"}, headers=h))
    latest = _ok(client.get(url, headers=h))
    assert latest["as_of"] == "2026-01-31"
    assert len(latest["items"]) == 1
    assert (
        _ok(client.get(url, params={"as_of": "2026-01-05"}, headers=h))["items"][0]["remaining"]
        == "1000.00"
    )
    # Validation, permission, tenant separation.
    assert client.post(f"{url}/refresh", json={"as_of": "kein"}, headers=h).status_code == 422
    assert client.post(f"{url}/refresh", json={"x": 1}, headers=h).status_code == 422
    reader = bearer(login(client, world, "q01reader"))
    assert client.get(url, headers=reader).status_code == 200
    assert client.post(f"{url}/refresh", json={}, headers=reader).status_code == 403
    other = bearer(login(client, world, "q01other"))
    assert client.get(url, headers=other).status_code == 404
    assert client.post(f"{url}/refresh", json={}, headers=other).status_code == 404


def test_open_item_balance_job(database: Database, redis_url: str, world: World) -> None:
    from datetime import date

    from mhvp.accounting.tasks import open_item_balance_refresh_all

    out = asyncio.run(
        open_item_balance_refresh_all(_settings(database, redis_url), today=date(2026, 2, 1))
    )
    assert out["failed"] == 0
    assert out["ledgers"] >= 1


def test_s69_02_s69_03_decisions_and_person_warning(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q01admin"))
    acc_user = bearer(login(client, world, "q01acc"))
    ledger, acc, _ = _hoa_ledger(client, h, "913")
    prop = _property_of(client, h, ledger)
    ledger_row = _ok(client.get(f"{A}/ledgers/{ledger}", headers=h))
    bank = _ok(
        client.post(
            f"/api/v1/properties/{prop}/bank-accounts",
            json={
                "legal_entity_id": ledger_row["legal_entity_id"],
                "kind": "hoa",
                "iban": OWN,
                "holder": "GdWE 913",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Q01 Dienst {RUN} GmbH",
                "bank_accounts": [{"iban": PROVIDER, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, bearer(login(client, world, "q01approver")), provider)
    body = {
        "ledger_id": ledger,
        "provider_contact_id": provider,
        "number": "Q-1",
        "invoice_date": "2026-02-01",
        "due_date": "2026-02-20",
        "service_from": "2026-01-01",
        "net": "100.00",
        "vat": "0.00",
        "gross": "100.00",
        "payee_iban": PROVIDER,
        "lines": [{"account_id": acc["040300"], "net": "100.00"}],
    }
    inv = _ok(client.post(f"{A}/invoices", json=body, headers=h), 201)["id"]

    def reviews() -> None:
        for step in ("completeness", "factual", "arithmetic_tax"):
            _ok(
                client.post(
                    f"{A}/invoices/{inv}/reviews",
                    json={"step": step, "result": "ok", "reason": "geprüft"},
                    headers=h,
                ),
                201,
            )

    reviews()
    _ok(client.post(f"{A}/invoices/{inv}/release", headers=acc_user))
    q = {"subject_type": "invoice", "subject_id": inv}
    rows = _ok(client.get(f"{A}/approval-decisions", params=q, headers=h))
    assert [(r["step"], r["status"]) for r in rows] == [("release", "valid")]
    assert len(rows[0]["subject_snapshot_hash"]) == 64
    # A change of the invoice persists the fall back (status invalidated).
    _ok(client.put(f"{A}/invoices/{inv}", json={**body, "due_date": "2026-02-25"}, headers=h))
    rows = _ok(client.get(f"{A}/approval-decisions", params=q, headers=h))
    assert rows[0]["status"] == "invalidated"
    assert rows[0]["invalidated_at"] is not None
    reviews()
    _ok(client.post(f"{A}/invoices/{inv}/release", headers=acc_user))
    _ok(client.post(f"{A}/invoices/{inv}/post", headers=h))
    rows = _ok(client.get(f"{A}/approval-decisions", params=q, headers=h))
    assert [r["status"] for r in rows] == ["invalidated", "valid"]

    # S69-03: two users linked to two separate contacts with the same name and birth date.
    for name in ("q01admin", "q01acc"):
        contact = _ok(
            client.post(
                "/api/v1/contacts",
                json={
                    "kind": "person",
                    "first_name": "Erika",
                    "last_name": f"Doppel{RUN}",
                    "date_of_birth": "1980-05-01",
                },
                headers=h,
            ),
            201,
        )
        _link_contact(world, name, contact["id"])
    order = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv,
                "property_bank_account_id": bank,
                "execution_date": "2026-02-05",
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=h))
    approved = _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=acc_user))
    assert approved["status"] == "approved"  # warning, no block
    assert any(
        "gleicher Name und gleiches Geburtsdatum" in w for w in approved["approval_warnings"]
    )
    oq = {"subject_type": "payment_order", "subject_id": order["id"]}
    rows = _ok(client.get(f"{A}/approval-decisions", params=oq, headers=h))
    assert [r["status"] for r in rows] == ["valid", "valid"]
    assert rows[0]["legacy_ref_id"] is not None
    patched = _ok(
        client.patch(
            f"{B}/payment-orders/{order['id']}", json={"execution_date": "2026-02-06"}, headers=h
        )
    )
    assert patched["status"] == "draft"
    assert patched["approval_warnings"] == []
    rows = _ok(client.get(f"{A}/approval-decisions", params=oq, headers=h))
    assert {r["status"] for r in rows} == {"invalidated"}
    # Validation, tenant separation.
    bad = client.get(
        f"{A}/approval-decisions", params={"subject_type": "x", "subject_id": inv}, headers=h
    )
    assert bad.status_code == 422
    other = bearer(login(client, world, "q01other"))
    assert client.get(f"{A}/approval-decisions", params=oq, headers=other).status_code == 404
    reader = bearer(login(client, world, "q01reader"))
    assert client.get(f"{A}/approval-decisions", params=oq, headers=reader).status_code == 200
