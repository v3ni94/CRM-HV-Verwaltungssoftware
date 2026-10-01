"""Wave 5 T05 (M14-02, 7.9.1 PÜ02): factual review of incoming invoices as findings.

Expected values (recomputed by hand):
- work order quote 1.000,00, invoice gross 1.190,00: deviation 190,00 > 0 % tolerance, finding;
  with 20 % price tolerance the allowed deviation is 200,00, no finding.
- budget limit 1.100,00 < 1.190,00: finding.
- plan item 2.000,00: first invoice 1.190,00 fits, second 1.190,00 gives 2.380,00 > 2.000,00.
- line 3 x 300,00 = 900,00 against stated 1.000,00: finding; 1.000,00 / 4 x 250,00 fits.
- recurring plan 119,00 monthly: invoices 01.02. and 01.04. are two months apart, finding.
- the factual check never changes the review status (stays open), automatic_release false.
"""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
KNOWN = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"t5a-{RUN}", name=f"T05 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"t5b-{RUN}", name=f"T05 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("t5admin", a, "tenant_admin"),
            ("t5approver", a, "tenant_admin"),
            ("t5reader", a, "read_only"),
            ("t5other", b, "tenant_admin"),
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
    return response.json()


def _sql(engine: Engine, tenant: Any, statement: str, **params: Any) -> Any:
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        result = conn.execute(text(statement), params)
        return result.all() if result.returns_rows else None


def _setup(
    c: TestClient, h: dict[str, str], world: World, number: str, approver: str = "t5approver"
) -> dict[str, Any]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"T05 {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Dienst {number} {RUN} GmbH",
                "bank_accounts": [{"iban": KNOWN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    if approver:
        approve_bank_accounts(c, bearer(login(c, world, approver)), provider)
    return {"ledger": ledger, "acc": acc, "provider": provider, "property": prop["id"], "hoa": hoa}


def _invoice(env: dict[str, Any], **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ledger_id": env["ledger"],
        "provider_contact_id": env["provider"],
        "number": f"T5-{uuid.uuid4().hex[:6]}",
        "invoice_date": "2026-02-01",
        "service_from": "2026-01-01",
        "service_to": "2026-01-31",
        "net": "1000.00",
        "vat": "190.00",
        "gross": "1190.00",
        "payee_iban": KNOWN,
        "service_place": "Musterstraße 1, Berlin",
        "issuer_vat_id": "DE123456789",
        "lines": [
            {
                "account_id": env["acc"]["040100"],
                "net": "1000.00",
                "vat_percent": "19",
                "vat": "190.00",
                "text": "Reparatur",
            }
        ],
    }
    body.update(over)
    return body


def _work_order(engine: Engine, tenant: Any, env: dict[str, Any], **cols: Any) -> str:
    oid = str(uuid.uuid4())
    _sql(
        engine,
        tenant,
        "INSERT INTO work_order (id, tenant_id, property_id, provider_contact_id, description,"
        " requires_board_approval, status, photo_document_ids, quote_amount, budget_limit)"
        " VALUES (:id, :t, :p, :c, 'Reparatur Dach', false, :s, '{}', :q, :b)",
        id=oid,
        t=str(tenant),
        p=env["property"],
        c=env["provider"],
        s=cols.get("status", "approved"),
        q=cols.get("quote"),
        b=cols.get("budget"),
    )
    return oid


def _codes(check: dict[str, Any]) -> set[str]:
    return {f["code"] for f in check["findings"]}


def test_work_order_price_tolerance_and_responsibility(
    client: TestClient, world: World, migrator_engine: Engine
) -> None:
    h = bearer(login(client, world, "t5admin"))
    env = _setup(client, h, world, "851")
    manager = str(world.users["t5approver"])
    _sql(
        migrator_engine,
        world.tenant_a,
        "UPDATE property SET manager_user_id = :m WHERE id = :p",
        m=manager,
        p=env["property"],
    )
    order = _work_order(migrator_engine, world.tenant_a, env, quote="1000.00", budget="1100.00")
    inv = _ok(client.post(f"{A}/invoices", json=_invoice(env, work_order_id=order), headers=h), 201)
    assert inv["work_order_id"] == order
    assert any("Angebot" in f for f in inv["findings"])
    assert any("Kostengrenze" in f for f in inv["findings"])
    assert "Auftrags- oder Vertragsbezug nicht angegeben (sachliche Prüfung)" not in inv["findings"]
    check = _ok(client.get(f"{A}/invoices/{inv['id']}/factual-check", headers=h))
    assert {"price_quote", "price_budget_limit"} <= _codes(check)
    assert check["suggested_reviewer_user_id"] == manager
    assert check["automatic_release"] is False
    assert _ok(client.get(f"{A}/invoices/{inv['id']}", headers=h))["review_status"] == "open"

    # Tolerance 20 %: 190,00 deviation on 1.000,00 is within 200,00.
    reader = bearer(login(client, world, "t5reader"))
    body = {"price_tolerance_percent": "20", "quantity_tolerance_percent": "0"}
    assert client.put(f"{A}/invoice-check-settings", json=body, headers=reader).status_code == 403
    bad = {"price_tolerance_percent": "-1", "quantity_tolerance_percent": "0"}
    assert client.put(f"{A}/invoice-check-settings", json=bad, headers=h).status_code == 422
    saved = _ok(client.put(f"{A}/invoice-check-settings", json=body, headers=h))
    assert Decimal(saved["price_tolerance_percent"]) == Decimal("20")
    check = _ok(client.get(f"{A}/invoices/{inv['id']}/factual-check", headers=h))
    assert "price_quote" not in _codes(check)
    assert "price_budget_limit" in _codes(check)
    _ok(
        client.put(
            f"{A}/invoice-check-settings",
            json={"price_tolerance_percent": "0", "quantity_tolerance_percent": "0"},
            headers=h,
        )
    )

    # Other tenant: invoice 404, own settings stay default, foreign order link 422.
    other = bearer(login(client, world, "t5other"))
    assert client.get(f"{A}/invoices/{inv['id']}/factual-check", headers=other).status_code == 404
    assert _ok(client.get(f"{A}/invoice-check-settings", headers=other))[
        "price_tolerance_percent"
    ] in ("0", "0.00000000")
    env_b = _setup(client, other, world, "851", approver="")
    resp = client.post(f"{A}/invoices", json=_invoice(env_b, work_order_id=order), headers=other)
    assert resp.status_code == 422, resp.text


def test_order_status_free_text_and_lines(
    client: TestClient, world: World, migrator_engine: Engine
) -> None:
    h = bearer(login(client, world, "t5admin"))
    env = _setup(client, h, world, "852")
    draft = _work_order(migrator_engine, world.tenant_a, env, status="quoted")
    lines = [
        {
            "account_id": env["acc"]["040100"],
            "net": "1000.00",
            "vat_percent": "19",
            "vat": "190.00",
            "quantity": "3",
            "unit_price": "300.00",
        }
    ]
    inv = _ok(
        client.post(
            f"{A}/invoices", json=_invoice(env, work_order_id=draft, lines=lines), headers=h
        ),
        201,
    )
    check = _ok(client.get(f"{A}/invoices/{inv['id']}/factual-check", headers=h))
    assert {"order_not_placed", "line_mismatch", "no_manager"} <= _codes(check)
    assert inv["lines"][0]["quantity"] == "3.00000000"
    lines[0].update({"quantity": "4", "unit_price": "250.00"})
    free = _ok(
        client.post(
            f"{A}/invoices", json=_invoice(env, order_reference="AUF-9", lines=lines), headers=h
        ),
        201,
    )
    codes = _codes(_ok(client.get(f"{A}/invoices/{free['id']}/factual-check", headers=h)))
    assert "order_free_text" in codes
    assert "line_mismatch" not in codes
    zero = dict(lines[0], quantity="0")
    assert (
        client.post(f"{A}/invoices", json=_invoice(env, lines=[zero]), headers=h).status_code == 422
    )


def test_resolution_and_budget(client: TestClient, world: World, migrator_engine: Engine) -> None:
    h = bearer(login(client, world, "t5admin"))
    env = _setup(client, h, world, "853")
    t = str(world.tenant_a)
    res = str(uuid.uuid4())
    _sql(
        migrator_engine,
        t,
        "INSERT INTO resolution (id, tenant_id, legal_entity_id, number, decided_on, subject,"
        " wording, status, kind, votes) VALUES (:id, :t, :le, 7, '2026-03-01', 'Dach',"
        " 'Dach wird repariert', 'contested', 'meeting', '{}')",
        id=res,
        t=t,
        le=env["hoa"],
    )
    key = _sql(
        migrator_engine,
        t,
        "SELECT id FROM allocation_key WHERE property_id = :p LIMIT 1",
        p=env["property"],
    )
    if not key:
        key = _sql(
            migrator_engine,
            t,
            "INSERT INTO allocation_key (id, tenant_id, property_id, code, name, unit_of_measure,"
            " kind, sort_order, is_template_derived) VALUES (:id, :t, :p, 'T5', 'T5', 'qm',"
            " 'static', 0, false) RETURNING id",
            id=str(uuid.uuid4()),
            t=t,
            p=env["property"],
        )
    plan, item = str(uuid.uuid4()), str(uuid.uuid4())
    _sql(
        migrator_engine,
        t,
        "INSERT INTO economic_plan (id, tenant_id, ledger_id, year, valid_from, status, version)"
        " VALUES (:id, :t, :l, 2026, '2026-01-01', 'draft', 1)",
        id=plan,
        t=t,
        l=env["ledger"],
    )
    _sql(
        migrator_engine,
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
    first = _ok(
        client.post(
            f"{A}/invoices", json=_invoice(env, resolution_id=res, plan_item_id=item), headers=h
        ),
        201,
    )
    codes = _codes(_ok(client.get(f"{A}/invoices/{first['id']}/factual-check", headers=h)))
    assert {"resolution_status", "resolution_before"} <= codes
    assert "budget_exceeded" not in codes
    second = _ok(
        client.post(f"{A}/invoices", json=_invoice(env, plan_item_id=item), headers=h), 201
    )
    assert any("Planansatz Instandhaltung 2.000,00 EUR" in f for f in second["findings"]), second[
        "findings"
    ]


def test_recurring_plan_rhythm(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "t5admin"))
    env = _setup(client, h, world, "854")
    plan = _ok(
        client.post(
            f"{A}/recurring-invoices",
            json={
                "ledger_id": env["ledger"],
                "provider_contact_id": env["provider"],
                "account_id": env["acc"]["040100"],
                "gross": "119.00",
                "interval_months": 1,
                "start_date": "2026-02-01",
                "text": "Wartung",
                "vat_percent": "19",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(client.post(f"{A}/recurring-invoices/{plan}/generate", headers=h), 201)
    small: dict[str, Any] = {
        "net": "100.00",
        "vat": "19.00",
        "gross": "119.00",
        "invoice_date": "2026-04-01",
        "service_from": "2026-04-01",
        "service_to": "2026-04-30",
        "lines": [
            {
                "account_id": env["acc"]["040100"],
                "net": "100.00",
                "vat_percent": "19",
                "vat": "19.00",
            }
        ],
    }
    unlinked = _ok(client.post(f"{A}/invoices", json=_invoice(env, **small), headers=h), 201)
    assert any("Rechnungsplan Wartung" in f for f in unlinked["findings"])
    linked = _ok(
        client.post(
            f"{A}/invoices", json=_invoice(env, recurring_plan_id=plan, **small), headers=h
        ),
        201,
    )
    assert linked["recurring_plan_id"] == plan
    codes = _codes(_ok(client.get(f"{A}/invoices/{linked['id']}/factual-check", headers=h)))
    assert "recurring_rhythm" in codes
    assert "recurring_amount" not in codes
    over = dict(small, gross="130.00", vat="30.00", net="100.00")
    odd = _ok(
        client.post(f"{A}/invoices", json=_invoice(env, recurring_plan_id=plan, **over), headers=h),
        201,
    )
    codes = _codes(_ok(client.get(f"{A}/invoices/{odd['id']}/factual-check", headers=h)))
    assert {"recurring_amount", "recurring_twice"} <= codes, (codes, odd["gross"])


def test_links_must_belong_to_invoice_object(
    client: TestClient, world: World, migrator_engine: Engine
) -> None:
    """U15-02: work order, resolution, plan item and invoice plan of another property or
    ledger in the same tenant are rejected with 422 MHVP-ACC-0008 (create and update)."""
    h = bearer(login(client, world, "t5admin"))
    own = _setup(client, h, world, "855")
    foreign = _setup(client, h, world, "856")
    t = str(world.tenant_a)
    order = _work_order(migrator_engine, world.tenant_a, foreign, quote="1000.00")
    res = str(uuid.uuid4())
    _sql(
        migrator_engine,
        t,
        "INSERT INTO resolution (id, tenant_id, legal_entity_id, number, decided_on, subject,"
        " wording, status, kind, votes) VALUES (:id, :t, :le, 8, '2026-01-01', 'Dach',"
        " 'Dach', 'valid', 'meeting', '{}')",
        id=res,
        t=t,
        le=foreign["hoa"],
    )
    key = _sql(
        migrator_engine,
        t,
        "INSERT INTO allocation_key (id, tenant_id, property_id, code, name, unit_of_measure,"
        " kind, sort_order, is_template_derived) VALUES (:id, :t, :p, 'V1', 'V1', 'qm',"
        " 'static', 0, false) RETURNING id",
        id=str(uuid.uuid4()),
        t=t,
        p=foreign["property"],
    )
    plan, item = str(uuid.uuid4()), str(uuid.uuid4())
    _sql(
        migrator_engine,
        t,
        "INSERT INTO economic_plan (id, tenant_id, ledger_id, year, valid_from, status, version)"
        " VALUES (:id, :t, :l, 2026, '2026-01-01', 'draft', 1)",
        id=plan,
        t=t,
        l=foreign["ledger"],
    )
    _sql(
        migrator_engine,
        t,
        "INSERT INTO economic_plan_item (id, tenant_id, plan_id, label, component, amount,"
        " allocation_key_id, account_id) VALUES (:id, :t, :p, 'Instandhaltung', 'hoa_fee',"
        " 2000.00, :k, :a)",
        id=item,
        t=t,
        p=plan,
        k=str(key[0][0]),
        a=foreign["acc"]["040100"],
    )
    rplan = _ok(
        client.post(
            f"{A}/recurring-invoices",
            json={
                "ledger_id": foreign["ledger"],
                "provider_contact_id": foreign["provider"],
                "account_id": foreign["acc"]["040100"],
                "gross": "119.00",
                "interval_months": 1,
                "start_date": "2026-02-01",
                "text": "Wartung",
                "vat_percent": "19",
            },
            headers=h,
        ),
        201,
    )["id"]
    links = {
        "work_order_id": order,
        "resolution_id": res,
        "plan_item_id": item,
        "recurring_plan_id": rplan,
    }
    for field, value in links.items():
        resp = client.post(f"{A}/invoices", json=_invoice(own, **{field: value}), headers=h)
        assert resp.status_code == 422, (field, resp.text)
        assert resp.json()["code"] == "MHVP-ACC-0008", field
        # The same links fit the foreign object itself.
        _ok(client.post(f"{A}/invoices", json=_invoice(foreign, **{field: value}), headers=h), 201)
    # Update path: an own invoice cannot be re-linked to a foreign order.
    inv = _ok(client.post(f"{A}/invoices", json=_invoice(own), headers=h), 201)
    resp = client.put(
        f"{A}/invoices/{inv['id']}", json=_invoice(own, work_order_id=order), headers=h
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "MHVP-ACC-0008"
    # Read only: 403 before any link check.
    reader = bearer(login(client, world, "t5reader"))
    assert client.post(f"{A}/invoices", json=_invoice(own), headers=reader).status_code == 403
