"""M15 payment run (7.5 Zahllauf): preview grouped by legal entity (M15-03), bulk draft orders
with per invoice failures, bank limits refusing the payment file (M15-04), payout without
invoice (M15-07), direct debit bank feedback and reconciliation (M15-01), pain.002/camt.054
import with idempotent repeat (M15-02), lead days per sequence type and pre-notification
distance (M15-06), weekly preview only for switched on tenants (S15-02). Tenant separation,
read only 403 and validation 422."""

import asyncio
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m15_direct_debits import CREDITOR_ID, OWN, PAYER_A, _contract, _payer

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
D = "/api/v1/accounting/direct-debits"
P = "/api/v1/accounting/payment-runs"
PROVIDER = "DE89370400440532013000"


class OpenG1:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


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
        a, _ = await services.provision_tenant(factory, slug=f"prun-{RUN}", name=f"Lauf {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"prunb-{RUN}", name=f"LaufB {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("pradmin", a, "tenant_admin"),
            ("pracc", a, "accountant_banking"),
            ("prapprover", a, "tenant_admin"),
            ("prreader", a, "read_only"),
            ("prother", b, "tenant_admin"),
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
            TestClient(create_app(settings, release_gate_resolver=OpenG1())) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG1G2())) as open_,
        ):
            yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(c: TestClient, h: dict[str, str], number: str) -> tuple[str, str, str, str]:
    """Property, HOA legal entity, bank account and leading ledger."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Laufhaus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": OWN,
                "holder": f"GdWE {number}",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    _ok(c.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    return str(prop["id"]), str(hoa), str(bank), str(ledger)


def _accounts(c: TestClient, h: dict[str, str], ledger: str) -> dict[str, str]:
    return {a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}


def test_preview_bulk_orders_limits_and_separation(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "pradmin"))
    acc_user = bearer(login(client, world, "pracc"))
    reader = bearer(login(client, world, "prreader"))
    other = bearer(login(client, world, "prother"))
    _, hoa, bank, ledger = _property(client, h, "861")
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
    acc = _accounts(client, h, ledger)
    provider = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"Laufdienst {RUN} GmbH",
                "bank_accounts": [{"iban": PROVIDER, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(client, bearer(login(client, world, "prapprover")), provider)
    today = local_today()

    def invoice(number: str, gross: str) -> str:
        body = {
            "ledger_id": ledger,
            "provider_contact_id": provider,
            "number": number,
            "invoice_date": today.isoformat(),
            "due_date": (today + timedelta(days=3)).isoformat(),
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

    inv1, inv2 = invoice("L-1", "600.00"), invoice("L-2", "500.00")

    preview = _ok(client.get(f"{P}/preview", params={"ledger_id": ledger}, headers=reader))
    [group] = preview["legal_entities"]
    assert group["legal_entity_id"] == hoa
    assert [a["id"] for a in group["bank_accounts"]] == [bank]
    assert {i["invoice_id"] for i in group["invoices"]} == {inv1, inv2}
    assert group["total"] == "1100.00"  # 600,00 + 500,00
    assert "Verification of Payee" in preview["verification_of_payee"]
    # Tenant separation: another tenant sees nothing and no bank account.
    assert _ok(client.get(f"{P}/preview", headers=other))["legal_entities"] == []
    assert client.get(f"{P}/bank-limits/{bank}", headers=other).status_code == 404

    body = {
        "execution_date": today.isoformat(),
        "items": [
            {"invoice_id": inv1, "property_bank_account_id": bank},
            {"invoice_id": inv2, "property_bank_account_id": bank},
        ],
    }
    assert client.post(f"{P}/orders", json=body, headers=reader).status_code == 403
    assert client.post(f"{P}/orders", json={"items": []}, headers=h).status_code == 422
    dup = {**body, "items": [body["items"][0], body["items"][0]]}
    assert client.post(f"{P}/orders", json=dup, headers=h).status_code == 422
    # Limits agreed with the bank: single order 550,00, reported as warning on creation.
    assert (
        client.put(
            f"{P}/bank-limits/{bank}", json={"single_order_limit": "550.00"}, headers=reader
        ).status_code
        == 403
    )
    limits = _ok(
        client.put(f"{P}/bank-limits/{bank}", json={"single_order_limit": "550.00"}, headers=h)
    )
    assert limits["single_order_limit"] == "550.00"
    assert limits["lead_times"]["source_status"] == "zu verifizieren"
    created = _ok(client.post(f"{P}/orders", json=body, headers=h), 201)
    assert len(created["created"]) == 2
    assert created["failed"] == []
    [warning] = created["limit_warnings"]  # 600,00 > 550,00; 500,00 stays below
    assert "600.00 EUR über dem Einzelauftragslimit 550.00 EUR" in warning
    # A repeat fails per invoice (order exists) without blocking anything else.
    again = _ok(client.post(f"{P}/orders", json=body, headers=h), 201)
    assert again["created"] == []
    assert len(again["failed"]) == 2
    assert (
        _ok(client.get(f"{P}/preview", params={"ledger_id": ledger}, headers=h))["legal_entities"]
        == []
    )  # items with an active order leave the preview

    # Both orders approved by two persons; the file above the limit is refused (409).
    ids = [o["id"] for o in created["created"]]
    for oid in ids:
        _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=h))
        _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=acc_user))
    gh = bearer(login(gated, world, "pracc"))
    refused = gated.post(f"{B}/payment-batches", json={"order_ids": ids}, headers=gh)
    assert refused.status_code == 409, refused.text
    assert "Einzelauftragslimit" in refused.json()["detail"]
    # Daily limit 1.000,00 < 600,00 + 500,00 = 1.100,00 is refused as well.
    _ok(
        client.put(
            f"{P}/bank-limits/{bank}",
            json={"single_order_limit": "1000.00", "daily_limit": "1000.00"},
            headers=h,
        )
    )
    refused = gated.post(f"{B}/payment-batches", json={"order_ids": ids}, headers=gh)
    assert refused.status_code == 409
    assert "Tageslimit" in refused.json()["detail"]
    _ok(client.put(f"{P}/bank-limits/{bank}", json={"daily_limit": "1100.00"}, headers=h))
    batch = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": ids}, headers=gh), 201)

    # pain.002 import: one rejected (AC04), one accepted; the repeat has no effect.
    orders = {o["id"]: o for o in _ok(client.get(f"{B}/payment-orders", headers=h))}
    e2e = [orders[i]["end_to_end_id"] for i in ids]
    xml = f"""<?xml version="1.0"?><Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.002.001.10">
<CstmrPmtStsRpt><GrpHdr><MsgId>ST-{RUN}</MsgId></GrpHdr>
<OrgnlGrpInfAndSts><OrgnlMsgId>{batch.get("message_id", "X")}</OrgnlMsgId></OrgnlGrpInfAndSts>
<OrgnlPmtInfAndSts><TxInfAndSts><OrgnlEndToEndId>{e2e[0]}</OrgnlEndToEndId><TxSts>RJCT</TxSts>
<StsRsnInf><Rsn><Cd>AC04</Cd></Rsn></StsRsnInf></TxInfAndSts>
<TxInfAndSts><OrgnlEndToEndId>{e2e[1]}</OrgnlEndToEndId><TxSts>ACSP</TxSts></TxInfAndSts>
</OrgnlPmtInfAndSts></CstmrPmtStsRpt></Document>"""
    assert (
        client.post(f"{P}/bank-status-reports", json={"xml": xml}, headers=reader).status_code
        == 403
    )
    assert (
        client.post(f"{P}/bank-status-reports", json={"xml": "<a>kein Bericht</a>"}, headers=h)
    ).status_code == 422
    report = _ok(client.post(f"{P}/bank-status-reports", json={"xml": xml}, headers=h), 201)
    assert report["created"] is True
    assert report["kind"] == "pain.002"
    assert [r["reported"] for r in report["result"]] == ["rejected", "accepted"]
    after = {o["id"]: o for o in _ok(client.get(f"{B}/payment-orders", headers=h))}
    assert after[ids[0]]["status"] == "rejected"
    assert after[ids[0]]["bank_status_reason_code"] == "AC04"
    assert after[ids[1]]["status"] == "accepted_by_bank"
    repeat = _ok(client.post(f"{P}/bank-status-reports", json={"xml": xml}, headers=h), 201)
    assert repeat["created"] is False
    assert repeat["id"] == report["id"]
    assert _ok(client.get(f"{P}/bank-status-reports", headers=other)) == []
    # The rejected invoice is payable again (D37: payable stays fully open).
    back = _ok(client.get(f"{P}/preview", params={"ledger_id": ledger}, headers=h))
    assert [i["invoice_id"] for g in back["legal_entities"] for i in g["invoices"]] == [inv1]

    # Payout without invoice is refused for an invoice's open item (M15-07).
    item = next(
        i
        for i in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2099-12-31"}, headers=h
            )
        )
        if i["kind"] == "payable"
    )
    contact = _ok(client.get(f"/api/v1/contacts/{provider}", headers=h))
    payout = {
        "open_item_id": item["id"],
        "contact_bank_account_id": contact["bank_accounts"][0]["id"],
        "property_bank_account_id": bank,
        "execution_date": today.isoformat(),
        "reason": "owner_payout",
    }
    # AK14 (GAI-402): payout orders are payment instructions behind G2.
    locked = client.post(f"{P}/payout-orders", json=payout, headers=h)
    assert locked.status_code == 403, locked.text
    assert (locked.json()["code"], locked.json()["gate"]) == ("MHVP-GATE-0001", "G2")
    refused = gated.post(f"{P}/payout-orders", json=payout, headers=gh)
    assert refused.status_code == 409, refused.text
    bad_reason = client.post(
        f"{P}/payout-orders",
        json={
            "open_item_id": item["id"],
            "contact_bank_account_id": contact["bank_accounts"][0]["id"],
            "property_bank_account_id": bank,
            "execution_date": today.isoformat(),
            "reason": "gift",
        },
        headers=h,
    )
    assert bad_reason.status_code == 422


def _dd_setup(c: TestClient, world: World, number: str) -> dict[str, Any]:
    h = bearer(login(c, world, "pradmin"))
    approver = bearer(login(c, world, "prapprover"))
    prop, hoa, bank, ledger = _property(c, h, number)
    _ok(
        c.put(
            f"{D}/creditor-ids/legal-entities/{hoa}",
            json={"sepa_creditor_id": CREDITOR_ID},
            headers=h,
        )
    )
    party, contact = _payer(c, h, f"R{number}", PAYER_A, {}, approver)
    contract = _contract(c, h, prop, "01", party)
    acc = _accounts(c, h, ledger)
    for code, number_ in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            c.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number_]},
                headers=h,
            )
        )
    run = _ok(c.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201)
    _ok(c.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    return {
        "h": h,
        "bank": bank,
        "ledger": ledger,
        "contact": contact,
        "contract": contract,
        "acc": acc,
    }


def test_direct_debit_feedback_lead_days_and_report(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, gated = clients
    ctx = _dd_setup(client, world, "862")
    h, bank, ledger = ctx["h"], ctx["bank"], ctx["ledger"]
    acc_user = bearer(login(client, world, "pracc"))
    reader = bearer(login(client, world, "prreader"))
    other = bearer(login(client, world, "prother"))
    collection = (local_today() + timedelta(days=7)).isoformat()
    body = {
        "ledger_id": ledger,
        "collection_date": collection,
        "lead_days": 5,
        "property_bank_account_id": bank,
    }
    # M15-06: FRST lead days of 10 agreed with the bank block a collection in 7 days.
    _ok(client.put(f"{P}/bank-limits/{bank}", json={"dd_lead_days_frst": 10}, headers=h))
    blocked = client.post(D, json=body, headers=h)
    assert blocked.status_code == 422, blocked.text
    _ok(
        client.put(
            f"{P}/bank-limits/{bank}",
            json={"dd_lead_days_frst": 5, "pre_notification_days": 10},
            headers=h,
        )
    )
    run = _ok(client.post(D, json=body, headers=h), 201)
    order = run["orders"][0]
    assert order["bank_status"] == "open"
    # Pre-notification 10 days agreed, 7 days left: refused.
    assert client.post(f"{D}/{run['id']}/pre-notifications", headers=h).status_code == 422
    _ok(client.post(f"{D}/{run['id']}/approve", headers=h))
    _ok(client.post(f"{D}/{run['id']}/approve", headers=acc_user))
    _ok(client.post(f"{D}/{run['id']}/file", headers=h))

    # Feedback only after the file was handed out.
    early = client.post(f"{D}/{run['id']}/bank-status", json={"status": "accepted"}, headers=h)
    assert early.status_code == 409
    gh = bearer(login(gated, world, "pradmin"))
    assert gated.get(f"{D}/{run['id']}/file", headers=gh).status_code == 200
    assert (
        client.post(
            f"{D}/{run['id']}/bank-status", json={"status": "accepted"}, headers=reader
        ).status_code
        == 403
    )
    assert (
        client.post(f"{D}/{run['id']}/bank-status", json={"status": "paid"}, headers=h).status_code
        == 422
    )
    assert client.get(f"{D}/{run['id']}/reconciliation", headers=other).status_code == 404
    rec = _ok(
        client.post(
            f"{D}/{run['id']}/bank-status",
            json={"status": "collected", "order_ids": [order["id"]]},
            headers=h,
        )
    )
    row = next(r for r in rec["orders"] if r["order_id"] == order["id"])
    assert row["bank_status"] == "collected"
    assert row["collected_amount"] == order["amount"]
    assert "noch nicht ausgeglichen" in row["finding"]
    other_row = next(r for r in rec["orders"] if r["order_id"] != order["id"])
    assert other_row["bank_status"] == "open"
    # Repeat has no effect (B08); without order ids the second collection is recorded too.
    _ok(client.post(f"{D}/{run['id']}/bank-status", json={"status": "collected"}, headers=h))

    # camt.054 return with reason MD06; the open item was never settled, so no finding.
    xml = f"""<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08">
<BkToCstmrDbtCdtNtfctn><GrpHdr><MsgId>N-{RUN}</MsgId></GrpHdr><Ntfctn><Id>1</Id>
<Ntry><Amt Ccy="EUR">{order["amount"]}</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<NtryDtls><TxDtls><Refs><EndToEndId>{order["end_to_end_id"]}</EndToEndId></Refs>
<RtrInf><Rsn><Cd>MD06</Cd></Rsn></RtrInf></TxDtls></NtryDtls></Ntry></Ntfctn>
</BkToCstmrDbtCdtNtfctn></Document>"""
    report = _ok(client.post(f"{P}/bank-status-reports", json={"xml": xml}, headers=h), 201)
    assert report["kind"] == "camt.054"
    assert report["result"][0]["result"] == "returned"
    rec = _ok(client.get(f"{D}/{run['id']}/reconciliation", headers=reader))
    row = next(r for r in rec["orders"] if r["order_id"] == order["id"])
    assert row["bank_status"] == "returned"
    assert row["reason_code"] == "MD06"
    assert row["finding"] is None
    assert rec["open_findings"] == 1  # the other collection is not yet settled


def test_payout_without_invoice_and_weekly_preview(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    closed, client = clients  # AK14 (GAI-402): payout orders need G2 open.
    ctx = _dd_setup(client, world, "863")
    h, bank, ledger = ctx["h"], ctx["bank"], ctx["ledger"]
    reader = bearer(login(client, world, "prreader"))
    acc_user = bearer(login(client, world, "pracc"))
    # Test fixture: a payable credit (e.g. from an owner statement) on the receivable run
    # entry; no API creates one yet (billing domain), so it is inserted directly.
    receivable = next(
        i
        for i in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2099-12-31"}, headers=h
            )
        )
        if i["kind"] == "receivable" and i.get("contract_id") == ctx["contract"]
    )
    engine = create_engine(database.migrator_url)
    with engine.begin() as conn:
        conn.execute(
            text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
        )
        row = conn.execute(
            text("SELECT tenant_id, journal_entry_id, booking_date FROM open_item WHERE id = :i"),
            {"i": receivable["id"]},
        ).one()
        payable_id = conn.execute(
            text(
                "INSERT INTO open_item (id, tenant_id, ledger_id, account_id, journal_entry_id, "
                "kind, booking_date, due_date, amount, contract_id, written_off) VALUES "
                "(gen_random_uuid(), :t, :l, :a, :j, 'payable', :d, :d, 123.45, :c, false) "
                "RETURNING id"
            ),
            {
                "t": row.tenant_id,
                "l": ledger,
                "a": ctx["acc"]["060200"],
                "j": row.journal_entry_id,
                "d": row.booking_date,
                "c": ctx["contract"],
            },
        ).scalar_one()
    engine.dispose()
    payee = ctx["contact"]["bank_accounts"][0]["id"]
    body = {
        "open_item_id": str(payable_id),
        "contact_bank_account_id": payee,
        "property_bank_account_id": bank,
        "execution_date": local_today().isoformat(),
        "reason": "statement_credit",
    }
    assert client.post(f"{P}/payout-orders", json=body, headers=reader).status_code == 403
    closed_h = bearer(login(closed, world, "pracc"))
    locked = closed.post(f"{P}/payout-orders", json=body, headers=closed_h)
    assert (locked.status_code, locked.json()["gate"]) == (403, "G2")
    deposit = client.post(
        f"{P}/payout-orders", json={**body, "reason": "deposit_refund"}, headers=h
    )
    assert deposit.status_code == 422  # deposit refunds only from the segregated account
    order = _ok(client.post(f"{P}/payout-orders", json=body, headers=h), 201)
    assert order["kind"] == "payout"
    assert order["amount"] == "123.45"
    assert order["payout_reason"] == "statement_credit"
    assert order["invoice_id"] is None
    assert client.post(f"{P}/payout-orders", json=body, headers=h).status_code == 409
    _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=h))
    approved = _ok(client.post(f"{B}/payment-orders/{order['id']}/approve", headers=acc_user))
    assert approved["status"] == "approved"

    # S15-02: weekly preview only for tenants that switched it on.
    from mhvp.banking.payment_run_tasks import weekly_previews

    assert _ok(client.get(f"{P}/settings", headers=reader))["weekly_preview_enabled"] is False
    assert (
        client.put(f"{P}/settings", json={"weekly_preview_enabled": True}, headers=reader)
    ).status_code == 403
    before = len(_ok(client.get(f"{P}/previews", headers=h)))
    asyncio.run(weekly_previews(_settings(database, redis_url)))
    assert len(_ok(client.get(f"{P}/previews", headers=h))) == before
    _ok(client.put(f"{P}/settings", json={"weekly_preview_enabled": True}, headers=h))
    asyncio.run(weekly_previews(_settings(database, redis_url)))
    previews = _ok(client.get(f"{P}/previews", headers=h))
    assert len(previews) == before + 1
    assert previews[0]["trigger"] == "schedule"
    assert "legal_entities" in previews[0]["summary"]
    assert _ok(client.get(f"{P}/previews", headers=bearer(login(client, world, "prother")))) == []
    _ok(client.post(f"{P}/previews", headers=h), 201)
