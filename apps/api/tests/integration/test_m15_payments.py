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
