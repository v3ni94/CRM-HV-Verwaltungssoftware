"""Wave 2 P03 (M14-01 to M14-09, S711-01, S711-04): further PÜ01 to PÜ05 checks at the
incoming invoice, credit note with its original, delegated review steps, creditor list and
statement, recurring plan lifecycle with month end, e-invoice validation record.

Expected values (recomputed by hand):
- cash discount 2 % of 1.190,00 = 23,80; stated 25,00 gives a finding.
- prepayment 100,00 and retention 59,50 on 1.190,00: payable 1.030,50.
- creditor after posting 1.190,00: balance 1.190,00, one open item of 1.190,00.
- credit note 200,00 on 1.190,00 is accepted; a second one of 1.000,00 exceeds (1.200,00).
- plan anchor 31.01.2026 monthly: 31.01., 28.02., 31.03.; service_to of the first 27.02.
- plan gross 119,00 at 19 %: net 100,00, VAT 19,00.
"""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

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
        a, _ = await services.provision_tenant(factory, slug=f"p3a-{RUN}", name=f"P03 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p3b-{RUN}", name=f"P03 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("p3admin", a, "tenant_admin"),
            ("p3approver", a, "tenant_admin"),
            ("p3reader", a, "read_only"),
            ("p3other", b, "tenant_admin"),
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


def _setup(c: TestClient, h: dict[str, str], world: World, number: str) -> dict[str, Any]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"P03 {number}", "management_type": "hoa"},
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
    approve_bank_accounts(c, bearer(login(c, world, "p3approver")), provider)
    return {"ledger": ledger, "acc": acc, "provider": provider}


def _invoice(env: dict[str, Any], **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ledger_id": env["ledger"],
        "provider_contact_id": env["provider"],
        "number": "P3-1",
        "invoice_date": "2026-02-01",
        "due_date": "2026-02-15",
        "service_from": "2026-01-01",
        "service_to": "2026-01-31",
        "net": "1000.00",
        "vat": "190.00",
        "gross": "1190.00",
        "payee_iban": KNOWN,
        "order_reference": "AUF-1",
        "service_place": "Musterstraße 1, Berlin",
        "issuer_vat_id": "DE123456789",
        "lines": [
            {
                "account_id": env["acc"]["040100"],
                "net": "1000.00",
                "vat_percent": "19",
                "vat": "190.00",
                "text": "Hausmeister",
            }
        ],
    }
    body.update(over)
    return body


def _release_and_post(c: TestClient, h: dict[str, str], ha: dict[str, str], inv: str) -> Any:
    for step in ("completeness", "factual", "arithmetic_tax"):
        _ok(
            c.post(
                f"{A}/invoices/{inv}/reviews",
                json={"step": step, "result": "ok", "reason": f"{step} geprüft"},
                headers=h,
            ),
            201,
        )
    _ok(c.post(f"{A}/invoices/{inv}/release", headers=ha))
    return _ok(c.post(f"{A}/invoices/{inv}/post", headers=h))


def test_pu01_to_pu03_fields_and_findings(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p3admin"))
    env = _setup(client, h, world, "831")
    inv = _ok(
        client.post(
            f"{A}/invoices",
            json=_invoice(
                env,
                discount_percent="2",
                discount_until="2026-02-08",
                discount_amount="25.00",
                prepaid_amount="100.00",
                retention_amount="59.50",
                reverse_charge=True,
                construction_withholding=True,
            ),
            headers=h,
        ),
        201,
    )
    assert Decimal(inv["discount_expected"]) == Decimal("23.80")
    assert "Skonto nachgerechnet 23.80 statt angegeben 25.00" in inv["findings"]
    assert Decimal(inv["payable_amount"]) == Decimal("1030.50")
    assert any(f.startswith("Reverse Charge gekennzeichnet, aber") for f in inv["findings"])
    assert any("Bauabzugsteuer" in f for f in inv["findings"])
    assert "Leistungsort fehlt (PÜ01)" not in inv["findings"]
    checklist = {i["item"]: i["present"] for i in inv["mandatory_checklist"]}
    assert checklist["service_place"]
    assert checklist["tax_data"]
    assert checklist["order"]
    assert checklist["original"] is False
    pay = _ok(
        client.get(
            f"{A}/invoices/{inv['id']}/discount", params={"pay_date": "2026-02-05"}, headers=h
        )
    )
    assert Decimal(pay["payable"]) == Decimal("1006.70")  # 1.030,50 - 23,80

    # Service period ending before its start is rejected (422), outside the year a hint.
    bad = client.post(
        f"{A}/invoices",
        json=_invoice(env, number="P3-2", service_from="2026-02-01", service_to="2026-01-01"),
        headers=h,
    )
    assert bad.status_code == 422
    over = _ok(
        client.post(
            f"{A}/invoices",
            json=_invoice(env, number="P3-3", service_from="2025-12-01", service_to="2026-01-31"),
            headers=h,
        ),
        201,
    )
    assert any("Wirtschaftsjahr" in f for f in over["findings"])


def test_contract_link_and_conflict_hints(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p3admin"))
    env = _setup(client, h, world, "832")
    contract = _ok(
        client.post(
            "/api/v1/service-contracts",
            json={
                "provider_contact_id": env["provider"],
                "title": "Hausmeistervertrag",
                "starts_at": "2026-01-15",
                "ends_at": "2026-12-31",
                "notice_period_days": 90,
            },
            headers=h,
        ),
        201,
    )["id"]
    inv = _ok(
        client.post(f"{A}/invoices", json=_invoice(env, service_contract_id=contract), headers=h),
        201,
    )
    assert "Leistungszeitraum beginnt vor dem Vertragsbeginn" in inv["findings"]
    assert inv["service_contract_id"] == contract

    # The issuer is also an owner: conflict of interest hint (PÜ02).
    owner = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Eigentümerdienst {RUN} GmbH",
                "roles": ["eigentuemer", "dienstleister"],
            },
            headers=h,
        ),
        201,
    )["id"]
    conflict = _ok(
        client.post(
            f"{A}/invoices",
            json=_invoice(env, number="P3-4", provider_contact_id=owner, payee_iban=None),
            headers=h,
        ),
        201,
    )
    assert any("zugleich als Eigentümer" in f for f in conflict["findings"])


def test_credit_note_needs_original_and_is_limited(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p3admin"))
    ha = bearer(login(client, world, "p3approver"))
    env = _setup(client, h, world, "833")
    original = _ok(client.post(f"{A}/invoices", json=_invoice(env), headers=h), 201)
    credit = {
        "kind": "credit_note",
        "number": "GS-1",
        "net": "168.07",
        "vat": "31.93",
        "gross": "200.00",
        "lines": [
            {
                "account_id": env["acc"]["040100"],
                "net": "168.07",
                "vat_percent": "19",
                "vat": "31.93",
                "text": "Gutschrift",
            }
        ],
    }
    missing = client.post(f"{A}/invoices", json=_invoice(env, **credit), headers=h)
    assert missing.status_code == 422
    first = _ok(
        client.post(
            f"{A}/invoices",
            json=_invoice(env, reference_invoice_id=original["id"], **credit),
            headers=h,
        ),
        201,
    )
    assert any("nicht gebucht" in f for f in first["findings"])
    _release_and_post(client, h, ha, original["id"])

    # Creditor list and statement after the posting of 1.190,00 (M14-08).
    creditors = _ok(
        client.get(
            f"{A}/ledgers/{env['ledger']}/creditors", params={"as_of": "2026-12-31"}, headers=h
        )
    )
    assert len(creditors) == 1
    assert Decimal(creditors[0]["balance"]) == Decimal("1190.00")
    assert creditors[0]["open_items"] == 1
    assert Decimal(creditors[0]["open_amount"]) == Decimal("1190.00")
    account = creditors[0]["account_id"]
    statement = _ok(
        client.get(
            f"{A}/ledgers/{env['ledger']}/creditors/{account}/statement",
            params={"start": "2026-01-01", "end": "2026-12-31"},
            headers=h,
        )
    )
    assert Decimal(statement["closing_balance"]) == Decimal("-1190.00")  # debit minus credit
    items = _ok(
        client.get(
            f"{A}/ledgers/{env['ledger']}/creditors/{account}/open-items",
            params={"as_of": "2026-12-31"},
            headers=h,
        )
    )
    assert [Decimal(i["remaining"]) for i in items] == [Decimal("1190.00")]

    # Second credit note of 1.000,00 would exceed the original (200 + 1.000 > 1.190).
    big = dict(credit, number="GS-2", net="840.34", vat="159.66", gross="1000.00")
    big["lines"] = [dict(credit["lines"][0], net="840.34", vat="159.66")]
    second = _ok(
        client.post(
            f"{A}/invoices",
            json=_invoice(env, reference_invoice_id=original["id"], **big),
            headers=h,
        ),
        201,
    )
    assert any("übersteigen die Ursprungsrechnung" in f for f in second["findings"])
    for step in ("completeness", "factual", "arithmetic_tax"):
        _ok(
            client.post(
                f"{A}/invoices/{second['id']}/reviews",
                json={"step": step, "result": "ok", "reason": "geprüft"},
                headers=h,
            ),
            201,
        )
    _ok(client.post(f"{A}/invoices/{second['id']}/release", headers=ha))
    blocked = client.post(f"{A}/invoices/{second['id']}/post", headers=h)
    assert blocked.status_code == 409, blocked.text

    # Tenant separation and read permission.
    other = bearer(login(client, world, "p3other"))
    assert client.get(f"{A}/ledgers/{env['ledger']}/creditors", headers=other).status_code == 404
    reader = bearer(login(client, world, "p3reader"))
    assert client.get(f"{A}/ledgers/{env['ledger']}/creditors", headers=reader).status_code == 200


def test_review_delegation_is_documented(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p3admin"))
    env = _setup(client, h, world, "834")
    inv = _ok(client.post(f"{A}/invoices", json=_invoice(env), headers=h), 201)
    half = client.post(
        f"{A}/invoices/{inv['id']}/reviews",
        json={
            "step": "factual",
            "result": "ok",
            "reason": "Leistung geprüft",
            "delegated_by": str(world.users["p3approver"]),
        },
        headers=h,
    )
    assert half.status_code == 422
    done = _ok(
        client.post(
            f"{A}/invoices/{inv['id']}/reviews",
            json={
                "step": "factual",
                "result": "ok",
                "reason": "Leistung geprüft",
                "delegated_by": str(world.users["p3approver"]),
                "delegation_reason": "Urlaubsvertretung",
                "reviewed_items": [{"kind": "page", "ref": "1"}, {"kind": "line", "ref": "1"}],
            },
            headers=h,
        ),
        201,
    )
    review = done["reviews"][0]
    assert review["delegation_reason"] == "Urlaubsvertretung"
    assert review["delegated_by"] == str(world.users["p3approver"])
    assert [i["ref"] for i in review["reviewed_items"]] == ["1", "1"]
    reader = bearer(login(client, world, "p3reader"))
    denied = client.post(
        f"{A}/invoices/{inv['id']}/reviews",
        json={"step": "factual", "result": "ok", "reason": "geprüft"},
        headers=reader,
    )
    assert denied.status_code == 403


def test_recurring_plan_lifecycle_month_end(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p3admin"))
    env = _setup(client, h, world, "835")
    plan = _ok(
        client.post(
            f"{A}/recurring-invoices",
            json={
                "ledger_id": env["ledger"],
                "provider_contact_id": env["provider"],
                "account_id": env["acc"]["043000"],
                "gross": "119.00",
                "vat_percent": "19",
                "start_date": "2026-01-31",
                "text": "Wartung",
                "order_reference": "V-7",
            },
            headers=h,
        ),
        201,
    )
    first = _ok(client.post(f"{A}/recurring-invoices/{plan['id']}/generate", headers=h), 201)
    assert first["invoice_date"] == "2026-01-31"
    assert first["service_to"] == "2026-02-27"
    assert Decimal(first["net"]) == Decimal("100.00")
    assert Decimal(first["vat"]) == Decimal("19.00")
    assert first["order_reference"] == "V-7"
    second = _ok(client.post(f"{A}/recurring-invoices/{plan['id']}/generate", headers=h), 201)
    assert second["invoice_date"] == "2026-02-28"
    read = _ok(client.get(f"{A}/recurring-invoices/{plan['id']}", headers=h))
    assert read["next_due"] == "2026-03-31"
    listed = _ok(
        client.get(f"{A}/recurring-invoices", params={"ledger_id": env["ledger"]}, headers=h)
    )
    assert [p["id"] for p in listed] == [plan["id"]]
    changed = _ok(
        client.patch(
            f"{A}/recurring-invoices/{plan['id']}", json={"text": "Wartung neu"}, headers=h
        )
    )
    assert changed["text"] == "Wartung neu"
    assert client.delete(f"{A}/recurring-invoices/{plan['id']}", headers=h).status_code == 409
    ended = _ok(
        client.post(
            f"{A}/recurring-invoices/{plan['id']}/end",
            json={"ended_at": "2026-03-01", "reason": "Vertrag gekündigt"},
            headers=h,
        )
    )
    assert ended["ended_at"] == "2026-03-01"
    assert (
        client.post(f"{A}/recurring-invoices/{plan['id']}/generate", headers=h).status_code == 409
    )
    assert (
        client.patch(
            f"{A}/recurring-invoices/{plan['id']}", json={"gross": "0"}, headers=h
        ).status_code
        == 422
    )
    other = bearer(login(client, world, "p3other"))
    assert client.get(f"{A}/recurring-invoices/{plan['id']}", headers=other).status_code == 404
    reader = bearer(login(client, world, "p3reader"))
    assert (
        client.post(
            f"{A}/recurring-invoices/{plan['id']}/end",
            json={"ended_at": "2026-03-01", "reason": "xyz"},
            headers=reader,
        ).status_code
        == 403
    )
    unused = _ok(
        client.post(
            f"{A}/recurring-invoices",
            json={
                "ledger_id": env["ledger"],
                "provider_contact_id": env["provider"],
                "account_id": env["acc"]["043000"],
                "gross": "10.00",
                "start_date": "2026-05-01",
                "text": "Unbenutzt",
            },
            headers=h,
        ),
        201,
    )
    assert client.delete(f"{A}/recurring-invoices/{unused['id']}", headers=h).status_code == 204
