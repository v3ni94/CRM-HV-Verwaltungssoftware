"""M13-05 status cancelled and M13-07 revenue posting drafts of the Verwalterhonorar.

Expected results are computed by hand: 2 apartments x 40,00 EUR quarterly net 80,00 EUR,
19 % VAT 15,20 EUR, gross 95,20 EUR (as in test_q15_fee_documents). Payer side: expense
95,20 to payable 95,20 (no payer VAT account configured). Manager side with VAT account:
receivable 95,20 to revenue 80,00 and VAT 15,20. The credit note mirrors both sides.
"""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_q15_fee_documents import BUCKET, LEITWEG, _ok, _property, _settings

A = "/api/v1/accounting"


class OpenG1:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"t04a-{RUN}", name=f"T04 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"t04b-{RUN}", name=f"T04 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("t04admin", a, "tenant_admin"),
            ("t04care", a, "caretaker"),
            ("t04other", b, "tenant_admin"),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG1())) as open_,
        ):
            yield closed, open_


def _lines(client: TestClient, h: dict[str, str], ledger: str, entry: str) -> list[Any]:
    body = _ok(client.get(f"{A}/ledgers/{ledger}/entries/{entry}", headers=h))
    assert body["status"] == "draft"
    return sorted(
        (line["account_id"], Decimal(line["debit"]), Decimal(line["credit"]))
        for line in body["lines"]
    )


def test_fee_posting_drafts(clients: tuple[TestClient, TestClient], world: World) -> None:
    closed, c = clients
    h = bearer(login(c, world, "t04admin"))
    care = bearer(login(c, world, "t04care"))
    other = bearer(login(c, world, "t04other"))
    prop = _property(c, h, "904")
    for no in ("01", "02"):
        _unit(c, h, prop["id"], no)
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    payer_ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(
        c.patch(
            "/api/v1/tenant/settings",
            json={"company": {**COMPANY, "email": "info@example.org", "phone": "+49 2173 000000"}},
            headers=h,
        )
    )
    manager_ledger = _ok(c.post("/api/v1/tenant/manager-entity", headers=h))["ledger_id"]
    _ok(
        c.patch(
            "/api/v1/tenant/billing-settings",
            json={
                "invoice_prefix": "PT",
                "vat_status": "regelbesteuert",
                "vat_id": "DE123456789",
                "leitweg_id": LEITWEG,
                "payee_iban": "DE02120300000000202051",
            },
            headers=h,
        )
    )
    fee = _ok(
        c.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-01-01",
                "vat_percent": "19",
                "amounts_per_unit_type": {"apartment": "40.00"},
            },
            headers=h,
        ),
        201,
    )
    _ok(c.patch(f"{A}/admin-fees/{fee['id']}", json={"interval": "quarterly"}, headers=h))
    run = _ok(
        c.post(
            f"{A}/admin-fees-run",
            json={"period_date": "2026-02-15", "invoice_date": "2026-04-02", "confirm": True},
            headers=h,
        )
    )
    invoice = run["rows"][0]["invoice_id"]
    drafts_url = f"{A}/admin-fee-invoices/{invoice}/posting-drafts"

    # G1 closed: nothing happens.
    gate = closed.post(drafts_url, headers=h)
    assert gate.status_code == 403
    assert gate.json()["code"] == "MHVP-GATE-0001"
    # Not released: no draft.
    assert c.post(drafts_url, headers=h).status_code == 409
    _ok(c.post(f"{A}/admin-fee-invoices/{invoice}/release", headers=h))
    # No account assignment: no draft (no default chart assignment).
    missing = c.post(drafts_url, headers=h)
    assert missing.status_code == 409
    assert missing.json()["code"] == "MHVP-ACC-0007"
    assert _ok(c.get(f"{A}/admin-fee-posting-config", headers=h)) is None

    payer_acc = {
        a["number"]: a for a in _ok(c.get(f"{A}/ledgers/{payer_ledger}/accounts", headers=h))
    }
    manager_acc = [
        a for a in _ok(c.get(f"{A}/ledgers/{manager_ledger}/accounts", headers=h)) if a["active"]
    ]
    active_payer = sorted((n, a["type"]) for n, a in payer_acc.items() if a["active"])
    payer_numbers = [
        next(n for n, t in active_payer if t == "expense"),
        next(n for n, t in active_payer if t == "liability"),
    ]
    by_type = {
        kind: [a for a in manager_acc if a["type"] == kind]
        for kind in ("asset", "income", "liability", "expense")
    }
    receivable, revenue, vat = (by_type[k][0]["id"] for k in ("asset", "income", "liability"))
    config = {
        "manager_ledger_id": manager_ledger,
        "manager_receivable_account_id": receivable,
        "manager_revenue_account_id": revenue,
        "manager_vat_account_id": vat,
        "payer_expense_account_number": payer_numbers[0],
        "payer_payable_account_number": payer_numbers[1],
    }
    cfg_url = f"{A}/admin-fee-posting-config"
    assert c.put(cfg_url, json=config, headers=care).status_code == 403
    assert (
        c.put(cfg_url, json={**config, "payer_expense_account_number": "12"}, headers=h).status_code
        == 422
    )
    expense_id = by_type["expense"][0]["id"]
    # U01: account kinds are checked against the chart of accounts (422).
    for field, bad in (
        ("manager_receivable_account_id", expense_id),
        ("manager_revenue_account_id", expense_id),
        ("manager_vat_account_id", expense_id),
    ):
        kind = c.put(cfg_url, json={**config, field: bad}, headers=h)
        assert kind.status_code == 422, field
        assert "Kontoart" in str(kind.json()), kind.json()
    wrong = c.put(cfg_url, json={**config, "manager_ledger_id": payer_ledger}, headers=h)
    assert wrong.status_code == 422
    assert wrong.json()["code"] == "MHVP-ACC-0004"
    # Review W79: a payer account of the wrong kind is refused when the drafts are created.
    swapped = {
        **config,
        "payer_expense_account_number": payer_numbers[1],
        "payer_payable_account_number": payer_numbers[0],
    }
    _ok(c.put(cfg_url, json=swapped, headers=h))
    kind = c.post(drafts_url, headers=h)
    assert kind.status_code == 409, kind.text
    assert "Kontoart" in kind.json()["detail"]
    saved = _ok(c.put(cfg_url, json=config, headers=h))
    assert saved["manager_ledger_id"] == manager_ledger
    assert _ok(c.get(cfg_url, headers=other)) is None

    assert c.post(drafts_url, headers=care).status_code == 403
    assert c.post(drafts_url, headers=other).status_code == 404
    out = _ok(c.post(drafts_url, headers=h), 201)
    assert out["created"] is True
    expense = payer_acc[payer_numbers[0]]["id"]
    payable = payer_acc[payer_numbers[1]]["id"]
    g, n, v, z = Decimal("95.20"), Decimal("80.00"), Decimal("15.20"), Decimal("0")
    assert _lines(c, h, payer_ledger, out["payer_entry_id"]) == sorted(
        [(expense, g, z), (payable, z, g)]
    )
    assert _lines(c, h, manager_ledger, out["manager_entry_id"]) == sorted(
        [(receivable, g, z), (revenue, z, n), (vat, z, v)]
    )
    again = _ok(c.post(drafts_url, headers=h), 201)
    assert again["created"] is False
    assert again["payer_entry_id"] == out["payer_entry_id"]
    detail = _ok(c.get(f"{A}/admin-fee-invoices/{invoice}", headers=h))
    assert detail["manager_entry_id"] == out["manager_entry_id"]

    # Storno: status cancelled, credit note with its own mirrored drafts; nothing overwritten.
    credit = _ok(
        c.post(
            f"{A}/admin-fee-invoices/{invoice}/cancel",
            json={"reason": "Einheitenzahl korrigiert", "credit_note_date": "2026-04-10"},
            headers=h,
        ),
        201,
    )
    detail = _ok(c.get(f"{A}/admin-fee-invoices/{invoice}", headers=h))
    assert detail["status"] == "cancelled"
    assert detail["corrected_by_id"] == credit["id"]
    assert detail["payer_entry_id"] == out["payer_entry_id"]
    listed = _ok(c.get(f"{A}/admin-fee-invoices?status=cancelled", headers=h))
    assert [r["id"] for r in listed] == [invoice]
    assert c.post(f"{A}/admin-fee-invoices/{invoice}/release", headers=h).status_code == 409
    credit_url = f"{A}/admin-fee-invoices/{credit['id']}/posting-drafts"
    _ok(c.post(f"{A}/admin-fee-invoices/{credit['id']}/release", headers=h))
    # GAG-06 (GAE-02, P06-02): object period lock of the payer property covering the credit
    # note date refuses the drafts up front (409 MHVP-ACC-0030), only in mode object_period.
    locks = f"{A}/period-locks"
    _ok(
        c.post(
            locks,
            json={
                "ledger_id": payer_ledger,
                "property_id": prop["id"],
                "period_from": "2026-04-01",
                "period_to": "2026-04-30",
                "reason": "Abschluss April",
            },
            headers=h,
        ),
        201,
    )
    _ok(c.put(f"{locks}/settings", json={"lock_mode": "object_period"}, headers=h))
    locked = c.post(credit_url, headers=h)
    assert locked.status_code == 409, locked.text
    assert locked.json()["code"] == "MHVP-ACC-0030"
    assert _ok(c.get(f"{A}/admin-fee-invoices/{credit['id']}", headers=h))["payer_entry_id"] is None
    _ok(c.put(f"{locks}/settings", json={"lock_mode": "ledger_only"}, headers=h))
    mirrored = _ok(c.post(credit_url, headers=h), 201)
    assert _lines(c, h, payer_ledger, mirrored["payer_entry_id"]) == sorted(
        [(expense, z, g), (payable, g, z)]
    )
    assert _lines(c, h, manager_ledger, mirrored["manager_entry_id"]) == sorted(
        [(receivable, z, g), (revenue, n, z), (vat, v, z)]
    )
