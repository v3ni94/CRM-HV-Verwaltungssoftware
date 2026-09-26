"""M15 payment runs: four eyes on a snapshot (change voids approvals), file export only with G2
(closed by default, opened here by a test resolver), export and submission leave the payable
open (D06), execution proven by an imported debit settles once including cash discount,
rejection, partial execution and return (reversal reopens the item)."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _upload

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
OWN = "DE02120300000000202051"
PROVIDER = "DE89370400440532013000"


class OpenG1G2:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G1, ReleaseGate.G2)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pay-{RUN}", name=f"Zahl {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m15admin", "tenant_admin"), ("m15acc", "accountant_banking")]:
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG1G2())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _debit(ref: str, amount: str, e2e: str) -> str:
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>2026-02-06</Dt></BookgDt><AcctSvcrRef>{ref}</AcctSvcrRef><NtryDtls><TxDtls><Refs><EndToEndId>{e2e}</EndToEndId></Refs>
<RltdPties><Cdtr><Nm>Dienstleister</Nm></Cdtr><CdtrAcct><Id><IBAN>{PROVIDER}</IBAN></Id></CdtrAcct></RltdPties>
<RmtInf><Ustrd>Zahlung</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


def test_payment_run(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, gated = clients
    h = bearer(login(client, world, "m15admin"))
    acc_user = bearer(login(client, world, "m15acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "751", "name": "Zahlhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": OWN,
                "holder": "GdWE Zahlhaus",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001210",
                "name": "Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank,
            },
            headers=h,
        ),
        201,
    )
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Dienst {RUN} GmbH",
                "bank_accounts": [{"iban": PROVIDER, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]

    def invoice(number: str, gross: str, discount: bool = False) -> str:
        body = {
            "ledger_id": ledger,
            "provider_contact_id": provider,
            "number": number,
            "invoice_date": "2026-02-01",
            "due_date": "2026-02-20",
            "service_from": "2026-01-01",
            "net": gross,
            "vat": "0.00",
            "gross": gross,
            "payee_iban": PROVIDER,
            "lines": [{"account_id": acc["040300"], "net": gross}],
        }
        if discount:
            body |= {"discount_percent": "2", "discount_until": "2026-02-10"}
        inv = _ok(client.post(f"{A}/invoices", json=body, headers=h), 201)["id"]
        for step in ("completeness", "factual", "arithmetic_tax"):
            _ok(
                client.post(
                    f"{A}/invoices/{inv}/reviews",
                    json={"step": step, "result": "ok", "reason": "geprüft"},
                    headers=h,
                ),
                201,
            )
        _ok(client.post(f"{A}/invoices/{inv}/release", headers=acc_user))
        _ok(client.post(f"{A}/invoices/{inv}/post", headers=h))
        return str(inv)

    def remaining() -> list[Decimal]:
        return sorted(
            Decimal(i["remaining"])
            for i in _ok(
                client.get(
                    f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h
                )
            )
        )

    inv1 = invoice("Z-1", "1190.00", discount=True)
    order = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv1,
                "property_bank_account_id": bank,
                "execution_date": "2026-02-05",
            },
            headers=h,
        ),
        201,
    )
    assert order["amount"] == "1166.20"  # 1.190,00 - 2 % = 1.166,20
    assert order["discount"] == "23.80"
    assert (
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv1,
                "property_bank_account_id": bank,
                "execution_date": "2026-02-05",
            },
            headers=h,
        ).status_code
        == 409
    )

    # Four eyes on a snapshot; a change voids approvals.
    assert (
        _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=h))["approvals"] == 1
    )
    assert (
        _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=h))["status"]
        == "draft"
    )
    assert (
        _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=acc_user))["status"]
        == "approved"
    )
    patched = _ok(
        client.patch(
            f"{B}/payment-orders/{order['id']}", json={"execution_date": "2026-02-06"}, headers=h
        )
    )
    assert patched["status"] == "draft"
    assert patched["approvals"] == 0
    listed = _ok(client.get(f"{B}/payment-orders", params={"status": "draft"}, headers=h))
    assert order["id"] in {o["id"] for o in listed}
    assert all("counterpart_iban" not in o for o in listed)  # only the suffix leaves the API
    _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=h))
    _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=acc_user))

    # G2 closed: no payment file.
    closed = client.post(
        f"{B}/payment-batches", json={"order_ids": [order["id"]]}, headers=acc_user
    )
    assert closed.status_code == 403
    assert closed.json()["code"] == "MHVP-GATE-0001"
    gh = bearer(login(gated, world, "m15acc"))
    not_leading = gated.post(f"{B}/payment-batches", json={"order_ids": [order["id"]]}, headers=gh)
    assert not_leading.status_code == 409  # only the leading system pays (13.1)
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    batch = _ok(
        gated.post(f"{B}/payment-batches", json={"order_ids": [order["id"]]}, headers=gh), 201
    )
    assert '<InstdAmt Ccy="EUR">1166.20</InstdAmt>' in batch["xml"]
    assert batch["format"] == "pain.001.001.09"
    assert remaining() == [Decimal("1190.00")]  # D06: export does not pay
    _ok(
        gated.post(
            f"{B}/payment-batches/{batch['id']}/bank-status",
            json={"status": "submitted"},
            headers=gh,
        )
    )
    assert remaining() == [Decimal("1190.00")]
    no_proof = gated.post(
        f"{B}/payment-batches/{batch['id']}/bank-status", json={"status": "executed"}, headers=gh
    )
    assert no_proof.status_code == 422

    # Execution proven by the bank statement settles once, discount to 027000.
    stmt = _camt(
        "P-1", OWN, "5000.00", "3833.80", [_debit("D-1", "1166.20", order["end_to_end_id"])]
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "p1.xml", stmt)}, headers=h
        ),
        201,
    )
    tx = next(
        t for t in _ok(client.get(f"{B}/transactions", headers=h)) if t["bank_reference"] == "D-1"
    )
    done = _ok(
        gated.post(
            f"{B}/payment-batches/{batch['id']}/bank-status",
            json={"status": "executed", "bank_transaction_id": tx["id"]},
            headers=gh,
        )
    )
    assert done[0]["status"] == "executed"
    assert remaining() == []
    again = _ok(
        gated.post(
            f"{B}/payment-batches/{batch['id']}/bank-status",
            json={"status": "executed", "bank_transaction_id": tx["id"]},
            headers=gh,
        )
    )
    assert again[0]["journal_entry_id"] == done[0]["journal_entry_id"]
    tb = {
        a["number"]: Decimal(a["balance"])
        for a in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-12-31"}, headers=h
            )
        )["accounts"]
    }
    assert tb["027000"] == Decimal("-23.80")
    assert tb["001210"] == Decimal("-1166.20")

    # Rejection leaves the payable open; a new order is possible afterwards.
    inv2 = invoice("Z-2", "500.00")
    o2 = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv2,
                "property_bank_account_id": bank,
                "execution_date": "2026-02-06",
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{B}/payment-orders/{o2['id']}/approve", headers=h))
    _ok(client.post(f"{B}/payment-orders/{o2['id']}/approve", headers=acc_user))
    b2 = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": [o2["id"]]}, headers=gh), 201)
    rejected = _ok(
        gated.post(
            f"{B}/payment-batches/{b2['id']}/bank-status",
            json={"status": "rejected", "reason": "Deckung"},
            headers=gh,
        )
    )
    assert rejected[0]["status"] == "rejected"
    assert remaining() == [Decimal("500.00")]
    o3 = _ok(
        client.post(
            f"{B}/payment-orders",
            json={
                "invoice_id": inv2,
                "property_bank_account_id": bank,
                "execution_date": "2026-02-06",
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{B}/payment-orders/{o3['id']}/approve", headers=h))
    _ok(client.post(f"{B}/payment-orders/{o3['id']}/approve", headers=acc_user))
    b3 = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": [o3["id"]]}, headers=gh), 201)
    _ok(
        gated.post(
            f"{B}/payment-batches/{b3['id']}/bank-status", json={"status": "submitted"}, headers=gh
        )
    )

    # Partial execution: 300,00 of 500,00 -> 200,00 open.
    stmt2 = _camt("P-2", OWN, "3833.80", "3533.80", [_debit("D-2", "300.00", o3["end_to_end_id"])])
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "p2.xml", stmt2)}, headers=h
        ),
        201,
    )
    tx2 = next(
        t for t in _ok(client.get(f"{B}/transactions", headers=h)) if t["bank_reference"] == "D-2"
    )
    part = _ok(
        gated.post(
            f"{B}/payment-batches/{b3['id']}/bank-status",
            json={"status": "executed", "bank_transaction_id": tx2["id"]},
            headers=gh,
        )
    )
    assert part[0]["status"] == "partially_executed"
    assert remaining() == [Decimal("200.00")]

    # Return of the first payment reverses the posting and reopens the payable.
    ret = _ok(
        gated.post(
            f"{B}/payment-batches/{batch['id']}/bank-status",
            json={"status": "returned", "reason": "Konto erloschen"},
            headers=gh,
        )
    )
    assert ret[0]["status"] == "returned"
    assert remaining() == [Decimal("200.00"), Decimal("1190.00")]
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True


# --- Annex D cases D35 to D38 (A09, A10) ------------------------------------------------

PROVIDER2 = "DE75512108001245126199"
T = "/api/v1/tenant"


def _credit(ref: str, amount: str, e2e: str) -> str:
    return f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>2026-02-09</Dt></BookgDt><AcctSvcrRef>{ref}</AcctSvcrRef><NtryDtls><TxDtls><Refs><EndToEndId>{e2e}</EndToEndId></Refs>
<RltdPties><Dbtr><Nm>Dienstleister</Nm></Dbtr><DbtrAcct><Id><IBAN>{PROVIDER}</IBAN></Id></DbtrAcct></RltdPties>
<RmtInf><Ustrd>Rueckgabe Konto erloschen</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""


async def _twin_user(settings: Any, world: World, name: str, role: str) -> None:
    """A second account for D36; the linked contact is set by the test via SQL."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        uid = await services.create_user(
            factory, email=world.email(name), display_name=name, password=PASSWORD
        )
        world.users[name] = uid
        await services.add_member(
            factory, tenant_id=world.tenant_a, user_id=uid, role_codes=[role], actor_user_id=None
        )
    finally:
        await engine.dispose()


def _link_contact(world: World, name: str, contact_id: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(world.app_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE membership SET contact_id = :c WHERE user_id = :u AND tenant_id = :t"),
            {"c": contact_id, "u": world.users[name], "t": world.tenant_a},
        )
    engine.dispose()


def _events(client: TestClient, h: dict[str, str], kind: str) -> list[dict[str, Any]]:
    return list(_ok(client.get(f"{T}/events", params={"type": kind, "page_size": 200}, headers=h)))


def test_d35_to_d38_payment_release_and_bank_feedback(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    """D35 change of amount or IBAN after approval voids the approval; D36 a second account of
    the same person is no second approver; D37 rejection and partial execution settle only the
    confirmed part; D38 a return reverses the posting and reopens the payable."""
    client, gated = clients
    h = bearer(login(client, world, "m15admin"))
    acc_user = bearer(login(client, world, "m15acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "752", "name": "Zahlhaus D35", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    own = "DE12500105170648489890"
    bank = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": own,
                "holder": "GdWE Zahlhaus D35",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001210",
                "name": "Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank,
            },
            headers=h,
        ),
        201,
    )
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Dienst D35 {RUN} GmbH",
                "bank_accounts": [
                    {"iban": PROVIDER, "valid_from": "2020-01-01"},
                    {"iban": PROVIDER2, "valid_from": "2020-01-01"},
                ],
            },
            headers=h,
        ),
        201,
    )["id"]

    def invoice(number: str, gross: str) -> str:
        body = {
            "ledger_id": ledger,
            "provider_contact_id": provider,
            "number": number,
            "invoice_date": "2026-02-01",
            "due_date": "2026-02-20",
            "service_from": "2026-01-01",
            "net": gross,
            "vat": "0.00",
            "gross": gross,
            "payee_iban": PROVIDER,
            "lines": [{"account_id": acc["040300"], "net": gross}],
        }
        inv = _ok(client.post(f"{A}/invoices", json=body, headers=h), 201)["id"]
        for step in ("completeness", "factual", "arithmetic_tax"):
            _ok(
                client.post(
                    f"{A}/invoices/{inv}/reviews",
                    json={"step": step, "result": "ok", "reason": "geprüft"},
                    headers=h,
                ),
                201,
            )
        _ok(client.post(f"{A}/invoices/{inv}/release", headers=acc_user))
        _ok(client.post(f"{A}/invoices/{inv}/post", headers=h))
        return str(inv)

    def new_order(inv: str) -> dict[str, Any]:
        return dict(
            _ok(
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
        )

    def approve(order_id: str, headers: dict[str, str]) -> Any:
        return client.post(f"{B}/payment-orders/{order_id}/approve", headers=headers)

    def remaining() -> list[Decimal]:
        return sorted(
            Decimal(i["remaining"])
            for i in _ok(
                client.get(
                    f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h
                )
            )
        )

    # D35: a change of amount or payee IBAN after the release voids the release.
    inv1 = invoice("D35-1", "1000.00")
    order = new_order(inv1)
    assert _ok(approve(order["id"], h))["approvals"] == 1
    assert _ok(approve(order["id"], acc_user))["status"] == "approved"
    changed = _ok(
        client.patch(f"{B}/payment-orders/{order['id']}", json={"amount": "600.00"}, headers=h)
    )
    assert changed["status"] == "draft"  # D35 amount: release invalid, state before release
    assert changed["approvals"] == 0
    assert changed["amount"] == "600.00"
    _ok(approve(order["id"], h))
    assert _ok(approve(order["id"], acc_user))["status"] == "approved"
    changed = _ok(
        client.patch(
            f"{B}/payment-orders/{order['id']}", json={"counterpart_iban": PROVIDER2}, headers=h
        )
    )
    assert changed["status"] == "draft"  # D35 IBAN: release invalid
    assert changed["approvals"] == 0
    assert changed["counterpart_iban_suffix"] == PROVIDER2[-4:]
    unknown = client.patch(
        f"{B}/payment-orders/{order['id']}",
        json={"counterpart_iban": "DE02100500000054540402"},
        headers=h,
    )
    assert unknown.status_code == 409  # no unconfirmed IBAN on an order (PÜ04)
    too_much = client.patch(
        f"{B}/payment-orders/{order['id']}", json={"amount": "1000.01"}, headers=h
    )
    assert too_much.status_code == 422
    same = _ok(
        client.patch(f"{B}/payment-orders/{order['id']}", json={"amount": "600.00"}, headers=h)
    )
    assert same["status"] == "draft"  # no new state, still needs both releases
    invalidations = [
        e
        for e in _events(client, h, "payment_order.approvals_invalidated")
        if e["entity_id"] == order["id"]
    ]
    assert sorted(tuple(e["payload"]["fields"]) for e in invalidations) == [
        ("amount",),
        ("counterpart_iban",),
    ]

    # D36: a second account of the same person (same linked contact) is no second approver.
    asyncio.run(_twin_user(_settings(database, redis_url), world, "m15twin", "accountant_banking"))
    admin_contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Timo", "last_name": f"Admin {RUN}"},
            headers=h,
        ),
        201,
    )["id"]
    _link_contact(world, "m15admin", admin_contact)
    _link_contact(world, "m15twin", admin_contact)
    twin = bearer(login(client, world, "m15twin"))
    assert _ok(approve(order["id"], h))["approvals"] == 1
    blocked = approve(order["id"], twin)
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["code"] == "MHVP-GATE-0002"
    state = _ok(client.get(f"{B}/payment-orders", params={"status": "draft"}, headers=h))
    assert next(o for o in state if o["id"] == order["id"])["approvals"] == 1
    assert _ok(approve(order["id"], acc_user))["status"] == "approved"  # a real second person
    export_blocked = client.post(
        f"{B}/payment-batches", json={"order_ids": [order["id"]]}, headers=twin
    )
    assert export_blocked.status_code == 403  # G2 closed on the plain client anyway

    # D37 (a): the bank rejects the order; the payable stays fully open with a reason.
    gh = bearer(login(gated, world, "m15acc"))
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh))
    b1 = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": [order["id"]]}, headers=gh), 201)
    assert remaining() == [Decimal("1000.00")]
    rejected = _ok(
        gated.post(
            f"{B}/payment-batches/{b1['id']}/bank-status",
            json={"status": "rejected", "reason": "AC01 falsche Kontonummer"},
            headers=gh,
        )
    )
    assert rejected[0]["status"] == "rejected"
    assert remaining() == [Decimal("1000.00")]
    rej_events = [
        e for e in _events(client, h, "payment_order.rejected") if e["entity_id"] == order["id"]
    ]
    assert len(rej_events) == 1
    assert rej_events[0]["payload"] == {
        "reason": "AC01 falsche Kontonummer",
        "open_amount": "600.00",
    }
    _ok(
        gated.post(
            f"{B}/payment-batches/{b1['id']}/bank-status",
            json={"status": "rejected", "reason": "Wiederholung"},
            headers=gh,
        )
    )
    rej_events = [
        e for e in _events(client, h, "payment_order.rejected") if e["entity_id"] == order["id"]
    ]
    assert len(rej_events) == 1  # a repeated callback adds no second event for the order

    # D37 (b): the bank executes 400,00 of 1.000,00; only the confirmed part is settled.
    o2 = new_order(inv1)
    assert o2["amount"] == "1000.00"
    _ok(approve(o2["id"], h))
    _ok(approve(o2["id"], acc_user))
    b2 = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": [o2["id"]]}, headers=gh), 201)
    _ok(
        gated.post(
            f"{B}/payment-batches/{b2['id']}/bank-status", json={"status": "submitted"}, headers=gh
        )
    )
    stmt = _camt("D37", own, "2000.00", "1600.00", [_debit("D37-1", "400.00", o2["end_to_end_id"])])
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "d37.xml", stmt)}, headers=h
        ),
        201,
    )
    tx = next(
        t for t in _ok(client.get(f"{B}/transactions", headers=h)) if t["bank_reference"] == "D37-1"
    )
    part = _ok(
        gated.post(
            f"{B}/payment-batches/{b2['id']}/bank-status",
            json={"status": "executed", "bank_transaction_id": tx["id"], "reason": "Teilbetrag"},
            headers=gh,
        )
    )
    assert part[0]["status"] == "partially_executed"
    assert part[0]["executed_amount"] == "400.00"
    assert remaining() == [Decimal("600.00")]
    partial_events = [
        e
        for e in _events(client, h, "payment_order.partially_executed")
        if e["entity_id"] == o2["id"]
    ]
    assert len(partial_events) == 1
    assert partial_events[0]["payload"] == {
        "reason": "Teilbetrag",
        "executed_amount": "400.00",
        "open_amount": "600.00",
    }
    original = _ok(
        client.get(f"{A}/ledgers/{ledger}/entries/{part[0]['journal_entry_id']}", headers=h)
    )
    assert original["status"] == "posted"
    assert original["reversed_by_id"] is None

    # D38: the executed 400,00 come back. Fees are not netted: a differing credit is refused.
    stmt2 = _camt(
        "D38",
        own,
        "1600.00",
        "2395.00",
        [
            _credit("D38-fee", "395.00", o2["end_to_end_id"]),
            _credit("D38-1", "400.00", "NOTPROVIDED"),
        ],
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "d38.xml", stmt2)}, headers=h
        ),
        201,
    )
    txs = {t["bank_reference"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    fee_return = gated.post(
        f"{B}/payment-batches/{b2['id']}/bank-status",
        json={
            "status": "returned",
            "reason": "Konto erloschen",
            "bank_transaction_id": txs["D38-fee"]["id"],
        },
        headers=gh,
    )
    assert fee_return.status_code == 422, fee_return.text
    assert "Gebühren" in fee_return.json()["detail"]
    assert remaining() == [Decimal("600.00")]  # nothing changed by the refused call
    returned = _ok(
        gated.post(
            f"{B}/payment-batches/{b2['id']}/bank-status",
            json={
                "status": "returned",
                "reason": "Konto erloschen",
                "bank_transaction_id": txs["D38-1"]["id"],
            },
            headers=gh,
        )
    )
    assert returned[0]["status"] == "returned"
    assert remaining() == [Decimal("1000.00")]  # the payable is open again in full
    ret_events = [
        e for e in _events(client, h, "payment_order.returned") if e["entity_id"] == o2["id"]
    ]
    assert len(ret_events) == 1
    reversal = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/entries/{ret_events[0]['payload']['reversal_id']}", headers=h
        )
    )
    original_after = _ok(
        client.get(f"{A}/ledgers/{ledger}/entries/{part[0]['journal_entry_id']}", headers=h)
    )
    assert reversal["kind"] == "reversal"
    assert reversal["reverses_id"] == original_after["id"]
    assert reversal["reversal_reason"] == "Konto erloschen"
    assert original_after["reversed_by_id"] == reversal["id"]
    assert original_after["status"] == "posted"  # never edited, only reversed (0.1.7)
    assert [(ln["debit"], ln["credit"]) for ln in original_after["lines"]] == [
        (ln["debit"], ln["credit"]) for ln in original["lines"]
    ]
    assert [(ln["account_id"], ln["debit"], ln["credit"]) for ln in reversal["lines"]] == [
        (ln["account_id"], ln["credit"], ln["debit"]) for ln in original["lines"]
    ]
    txs = {t["bank_reference"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    assert txs["D38-1"]["status"] == "booked"  # the return credit is tied to the reversal
    assert txs["D38-1"]["journal_entry_id"] == reversal["id"]
    assert txs["D38-fee"]["status"] == "new"  # fee credit stays open until proven separately
    again = _ok(
        gated.post(
            f"{B}/payment-batches/{b2['id']}/bank-status",
            json={"status": "returned", "reason": "Wiederholung"},
            headers=gh,
        )
    )
    assert again[0]["status"] == "returned"
    assert remaining() == [Decimal("1000.00")]  # idempotent, no second reversal
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True
    # After the return a new order for the invoice is possible again.
    o3 = new_order(inv1)
    assert o3["amount"] == "1000.00"


def test_d52_payment_batch_only_from_leading_system(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """D52 (13.1, 6.9.10): a fully approved payment order in a comparison ledger (Immoware24
    leading) produces no pain.001 file even with G2 open; after the platform becomes leading the
    file is created, and once Immoware24 leads again a second file for the same ledger is refused,
    so no payment is triggered from both systems. Direct debit (pain.008) follows with A11."""
    client, gated = clients
    h = bearer(login(client, world, "m15admin"))
    acc_user = bearer(login(client, world, "m15acc"))
    gh = bearer(login(gated, world, "m15acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "755", "name": "Vergleichszahlhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": OWN,
                "holder": "GdWE Vergleichszahlhaus",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )
    assert ledger["leading_system"] == "immoware24"
    lid = ledger["id"]
    _ok(
        client.post(
            f"{A}/ledgers/{lid}/accounts",
            json={
                "number": "001210",
                "name": "Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank,
            },
            headers=h,
        ),
        201,
    )
    acc = {a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{lid}/accounts", headers=h))}
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Vergleichsdienst {RUN} GmbH",
                "bank_accounts": [{"iban": PROVIDER, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]

    def order(number: str) -> str:
        inv = _ok(
            client.post(
                f"{A}/invoices",
                json={
                    "ledger_id": lid,
                    "provider_contact_id": provider,
                    "number": number,
                    "invoice_date": "2026-02-01",
                    "due_date": "2026-02-20",
                    "net": "100.00",
                    "vat": "0.00",
                    "gross": "100.00",
                    "payee_iban": PROVIDER,
                    "lines": [{"account_id": acc["040300"], "net": "100.00"}],
                },
                headers=h,
            ),
            201,
        )["id"]
        for step in ("completeness", "factual", "arithmetic_tax"):
            _ok(
                client.post(
                    f"{A}/invoices/{inv}/reviews",
                    json={"step": step, "result": "ok", "reason": "geprüft"},
                    headers=h,
                ),
                201,
            )
        _ok(client.post(f"{A}/invoices/{inv}/release", headers=acc_user))
        _ok(client.post(f"{A}/invoices/{inv}/post", headers=h))
        oid = _ok(
            client.post(
                f"{B}/payment-orders",
                json={
                    "invoice_id": inv,
                    "property_bank_account_id": bank,
                    "execution_date": "2026-02-25",
                },
                headers=h,
            ),
            201,
        )["id"]
        _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=h))
        assert (
            _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=acc_user))["status"]
            == "approved"
        )
        return str(oid)

    first = order("D52-1")
    refused = gated.post(f"{B}/payment-batches", json={"order_ids": [first]}, headers=gh)
    assert refused.status_code == 409
    assert "führende System" in refused.json()["detail"]
    _ok(gated.post(f"{A}/ledgers/{lid}/leading", json={"leading_system": "mhvp"}, headers=gh))
    batch = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": [first]}, headers=gh), 201)
    assert '<InstdAmt Ccy="EUR">100.00</InstdAmt>' in batch["xml"]
    # Immoware24 takes the lead back: no further file from the platform for this ledger.
    _ok(client.post(f"{A}/ledgers/{lid}/leading", json={"leading_system": "immoware24"}, headers=h))
    second = order("D52-2")
    again = gated.post(f"{B}/payment-batches", json={"order_ids": [second]}, headers=gh)
    assert again.status_code == 409
