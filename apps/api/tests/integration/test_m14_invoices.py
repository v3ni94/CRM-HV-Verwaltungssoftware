"""M14: incoming invoices. PÜ01 findings, PÜ02/PÜ03 review steps per version (PÜ05), release by
a second person bound to payment fields (6.9.9), changed IBAN needs separate confirmation
(PÜ04), duplicates flagged, correction supersedes, D12 partial and final invoice
(5.950,00 total, 2.380,00 partial -> 3.570,00 remaining, expense 5.950,00 not 8.330,00),
cash discount 2 % of 1.190,00 = 23,80 until the discount date, recurring plan drafts."""

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

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
KNOWN = "DE89370400440532013000"
CHANGED = "DE75512108001245126199"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"iv-{RUN}", name=f"Beleg {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m14admin", "tenant_admin"), ("m14acc", "accountant_no_banking")]:
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


def _review_all(c: TestClient, h: dict[str, str], inv: str, result: str = "ok") -> Any:
    out = None
    for step in ("completeness", "factual", "arithmetic_tax"):
        out = _ok(
            c.post(
                f"{A}/invoices/{inv}/reviews",
                json={"step": step, "result": result, "reason": f"{step} geprüft"},
                headers=h,
            ),
            201,
        )
    return out


def test_invoice_review_release_post_and_d12(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m14admin"))
    acc_user = bearer(login(client, world, "m14acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "741", "name": "Belegehaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Hausmeister {RUN} GmbH",
                "bank_accounts": [{"iban": KNOWN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]

    base = {
        "ledger_id": ledger,
        "provider_contact_id": provider,
        "number": "R-100",
        "invoice_date": "2026-02-01",
        "due_date": "2026-02-15",
        "service_from": "2026-01-01",
        "service_to": "2026-01-31",
        "net": "1000.00",
        "vat": "190.00",
        "gross": "1190.00",
        "discount_percent": "2",
        "discount_until": "2026-02-08",
        "payee_iban": KNOWN,
        "lines": [
            {
                "account_id": acc["040100"],
                "net": "1000.00",
                "vat_percent": "19",
                "vat": "190.00",
                "text": "Hausmeister Januar",
            }
        ],
    }
    inv = _ok(client.post(f"{A}/invoices", json=base, headers=h), 201)
    assert inv["findings"] == ["Originalbeleg fehlt"]  # PÜ01 hint only
    assert inv["review_status"] == "open"
    wrong = _ok(
        client.post(
            f"{A}/invoices",
            json={**base, "number": "R-101", "vat": "180.00", "gross": "1180.00"},
            headers=h,
        ),
        201,
    )
    assert any("Summe der Steuer" in f for f in wrong["findings"])

    # PÜ05: partial review, query, then closed; nothing turns green automatically.
    step = _ok(
        client.post(
            f"{A}/invoices/{inv['id']}/reviews",
            json={"step": "completeness", "result": "ok", "reason": "vollständig"},
            headers=h,
        ),
        201,
    )
    assert step["review_status"] == "partially_reviewed"
    q = _ok(
        client.post(
            f"{A}/invoices/{inv['id']}/reviews",
            json={"step": "factual", "result": "query", "reason": "Stundenzettel fehlen"},
            headers=h,
        ),
        201,
    )
    assert q["review_status"] == "query"
    assert client.post(f"{A}/invoices/{inv['id']}/release", headers=acc_user).status_code == 409
    closed = _review_all(client, h, inv["id"])
    assert closed["review_status"] == "closed_ok"
    assert client.post(f"{A}/invoices/{inv['id']}/post", headers=h).status_code == 403  # no release
    assert (
        client.post(f"{A}/invoices/{inv['id']}/release", headers=h).status_code == 403
    )  # own invoice
    released = _ok(client.post(f"{A}/invoices/{inv['id']}/release", headers=acc_user))
    assert released["released"] is True

    # Change of a payment field voids release and reviews (new version).
    changed = _ok(
        client.put(f"{A}/invoices/{inv['id']}", json={**base, "payee_iban": CHANGED}, headers=h)
    )
    assert changed["version"] == 2
    assert changed["released"] is False
    assert changed["review_status"] == "open"
    assert any("IBAN weicht" in f for f in changed["findings"])
    _review_all(client, h, inv["id"])
    assert (
        client.post(f"{A}/invoices/{inv['id']}/release", headers=acc_user).status_code == 409
    )  # IBAN unconfirmed
    assert client.post(f"{A}/invoices/{inv['id']}/confirm-iban", headers=h).status_code == 403
    confirmed = _ok(client.post(f"{A}/invoices/{inv['id']}/confirm-iban", headers=acc_user))
    assert confirmed["iban_confirmed"] is True
    _ok(client.post(f"{A}/invoices/{inv['id']}/release", headers=acc_user))
    posted = _ok(client.post(f"{A}/invoices/{inv['id']}/post", headers=h))
    assert posted["posting_status"] == "posted"
    assert client.post(f"{A}/invoices/{inv['id']}/post", headers=h).status_code == 409
    assert client.put(f"{A}/invoices/{inv['id']}", json=base, headers=h).status_code == 409
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-02-28"}, headers=h)
    )
    assert [(i["kind"], i["remaining"]) for i in items] == [("payable", "1190.00")]
    disc = _ok(
        client.get(
            f"{A}/invoices/{inv['id']}/discount", params={"pay_date": "2026-02-08"}, headers=h
        )
    )
    assert disc == {"discount": "23.80", "payable": "1166.20"}
    late = _ok(
        client.get(
            f"{A}/invoices/{inv['id']}/discount", params={"pay_date": "2026-02-09"}, headers=h
        )
    )
    assert late["discount"] == "0.00"

    # PÜ04: same number again is flagged, a correction that supersedes is not.
    dup = _ok(client.post(f"{A}/invoices", json={**base, "payee_iban": KNOWN}, headers=h), 201)
    assert dup["duplicate_of_id"] == inv["id"]
    corr = _ok(
        client.post(
            f"{A}/invoices",
            json={**base, "number": "R-101", "supersedes_id": wrong["id"]},
            headers=h,
        ),
        201,
    )
    assert corr["duplicate_of_id"] is None

    # D12: partial 2.380,00 posted, final 5.950,00 deducting it -> expense 3.570,00 more.
    part = _ok(
        client.post(
            f"{A}/invoices",
            json={
                **base,
                "number": "AB-1",
                "kind": "partial",
                "net": "2000.00",
                "vat": "380.00",
                "gross": "2380.00",
                "discount_percent": None,
                "discount_until": None,
                "lines": [
                    {
                        "account_id": acc["041400"],
                        "net": "2000.00",
                        "vat_percent": "19",
                        "vat": "380.00",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    _review_all(client, h, part["id"])
    _ok(client.post(f"{A}/invoices/{part['id']}/release", headers=acc_user))
    _ok(client.post(f"{A}/invoices/{part['id']}/post", headers=h))
    final = _ok(
        client.post(
            f"{A}/invoices",
            json={
                **base,
                "number": "SR-1",
                "kind": "final",
                "net": "5000.00",
                "vat": "950.00",
                "gross": "5950.00",
                "discount_percent": None,
                "discount_until": None,
                "deductions": [{"invoice_id": part["id"], "gross": "2380.00"}],
                "lines": [
                    {
                        "account_id": acc["041400"],
                        "net": "5000.00",
                        "vat_percent": "19",
                        "vat": "950.00",
                    }
                ],
            },
            headers=h,
        ),
        201,
    )
    _review_all(client, h, final["id"])
    _ok(client.post(f"{A}/invoices/{final['id']}/release", headers=acc_user))
    _ok(client.post(f"{A}/invoices/{final['id']}/post", headers=h))
    tb = _ok(
        client.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-12-31"}, headers=h)
    )
    by = {a["number"]: Decimal(a["balance"]) for a in tb["accounts"]}
    assert by["041400"] == Decimal("5950.00")
    payables = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h)
    )
    assert sorted(Decimal(i["remaining"]) for i in payables) == [
        Decimal("1190.00"),
        Decimal("2380.00"),
        Decimal("3570.00"),
    ]
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True
    creditor = [
        a
        for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
        if a["category"] == "creditor"
    ]
    assert [a["number"] for a in creditor] == ["070000"]

    # Recurring plan creates an unreviewed draft, never a posting.
    plan = _ok(
        client.post(
            f"{A}/recurring-invoices",
            json={
                "ledger_id": ledger,
                "provider_contact_id": provider,
                "account_id": acc["043000"],
                "gross": "80.00",
                "start_date": "2026-03-01",
                "text": "Strom Abschlag",
            },
            headers=h,
        ),
        201,
    )
    draft = _ok(client.post(f"{A}/recurring-invoices/{plan['id']}/generate", headers=h), 201)
    assert draft["kind"] == "recurring"
    assert draft["review_status"] == "open"
    assert draft["posting_status"] == "unposted"
    second = _ok(client.post(f"{A}/recurring-invoices/{plan['id']}/generate", headers=h), 201)
    assert second["invoice_date"] == "2026-04-01"
