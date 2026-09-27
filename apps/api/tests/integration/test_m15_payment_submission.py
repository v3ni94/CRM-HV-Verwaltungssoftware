"""M15-01, M15-03 (V2): synthetic payment run through every stage up to the file, with the
bank sandbox replaced by the public ISO 20022 XSDs. Ten credit transfers (pain.001 in the
version configured per bank account) and ten SEPA Core direct debits with mandates
(pain.008.001.02) are created, released by two persons, generated, checked against the XSD,
handed out only behind G2 with a download log, and confirmed as submitted by hand
(FileDownloadSubmitter). FinTS and EBICS submitters refuse (MHVP-BANK-0017). No money moves:
open items stay open until a bank debit proves the execution (D06)."""

import asyncio
import hashlib
from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.banking import payments
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m15_direct_debits import _contract, _payer, _receivables

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
D = "/api/v1/accounting/direct-debits"
OWN = "DE02120300000000202051"
CREDITOR_ID = "TESTGLAEUBIGERID0002"
XSD_DIR = Path(__file__).resolve().parents[1] / "data" / "iso20022"
TRANSFERS = 10
PAYERS = 5  # two open items (hoa_fee, reserve) per contract give ten direct debits


class OpenG1G2:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in (ReleaseGate.G1, ReleaseGate.G2)


def iban(account: int, blz: str = "37040044") -> str:
    """Synthetic but checksum valid German IBAN (mod 97), never a real account."""
    bban = f"{blz}{account:010d}"
    digits = "".join(str(int(c, 36)) for c in f"{bban}DE00")
    check = 98 - int(digits) % 97
    return f"DE{check:02d}{bban}"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"psub-{RUN}", name=f"Sub {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [
            ("psadmin", "tenant_admin"),
            ("psacc", "accountant_banking"),
            ("psapprover", "tenant_admin"),
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


def _xsd_errors(version: str, data: bytes) -> list[str]:
    xmlschema = pytest.importorskip("xmlschema")
    schema = xmlschema.XMLSchema(str(XSD_DIR / f"{version}.xsd"))
    return [str(e)[:200] for e in schema.iter_errors(data)]


def test_synthetic_payment_run_to_file(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "psadmin"))
    acc_user = bearer(login(client, world, "psacc"))
    approver = bearer(login(client, world, "psapprover"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "781", "name": "Sandboxhaus", "management_type": "hoa"},
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
                "bic": "BYLADEM1001",
                "holder": "GdWE Sandboxhaus",
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
    gh = bearer(login(gated, world, "psacc"))
    gh_admin = bearer(login(gated, world, "psadmin"))
    _ok(  # leading system needs G1 (open only on the gated client)
        gated.post(
            f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=gh_admin
        )
    )
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }

    # Format per bank account is operator input; unsupported versions are refused.
    default = _ok(client.get(f"{B}/payment-bank-config/{bank}", headers=h))
    assert default["pain001_version"] == "pain.001.001.09"
    assert default["supported"]["pain001"] == ["pain.001.001.03", "pain.001.001.09"]
    bad = client.put(
        f"{B}/payment-bank-config/{bank}", json={"pain001_version": "pain.001.001.99"}, headers=h
    )
    assert bad.status_code == 422, bad.text
    config = _ok(
        client.put(
            f"{B}/payment-bank-config/{bank}",
            json={
                "pain001_version": "pain.001.001.03",
                "pain008_version": "pain.008.001.02",
                "submission_channel": "file",
                "notes": "Testsystem, Version laut Bankgespräch (zu bestätigen)",
            },
            headers=h,
        )
    )
    assert config["pain001_version"] == "pain.001.001.03"

    # --- Ten credit transfers ---------------------------------------------------------
    orders: list[str] = []
    for i in range(TRANSFERS):
        provider = _ok(
            client.post(
                "/api/v1/contacts",
                json={
                    "kind": "company",
                    "company_name": f"Dienst {i} {RUN} GmbH & Co",
                    "bank_accounts": [{"iban": iban(1000 + i), "valid_from": "2020-01-01"}],
                },
                headers=h,
            ),
            201,
        )["id"]
        approve_bank_accounts(client, approver, provider)
        gross = f"{100 + i * 11}.{(i * 7) % 100:02d}"
        inv = _ok(
            client.post(
                f"{A}/invoices",
                json={
                    "ledger_id": ledger,
                    "provider_contact_id": provider,
                    "number": f"S-{i}",
                    "invoice_date": "2026-02-01",
                    "due_date": "2026-02-20",
                    "service_from": "2026-01-01",
                    "net": gross,
                    "vat": "0.00",
                    "gross": gross,
                    "payee_iban": iban(1000 + i),
                    "lines": [{"account_id": acc["040300"], "net": gross}],
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
        order = _ok(
            client.post(
                f"{B}/payment-orders",
                json={
                    "invoice_id": inv,
                    "property_bank_account_id": bank,
                    "execution_date": "2026-02-05" if i % 2 else "2026-02-06",
                },
                headers=h,
            ),
            201,
        )
        orders.append(order["id"])

    # Four eyes before any file: one approval is not enough.
    for oid in orders:
        _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=h))
    half = gated.post(f"{B}/payment-batches", json={"order_ids": orders}, headers=gh)
    assert half.status_code == 403, half.text
    assert half.json()["code"] == "MHVP-GATE-0002"
    for oid in orders:
        assert (
            _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=acc_user))["status"]
            == "approved"
        )

    # G2 closed: no file, no download, no submission.
    closed = client.post(f"{B}/payment-batches", json={"order_ids": orders}, headers=acc_user)
    assert closed.status_code == 403, closed.text
    assert closed.json()["code"] == "MHVP-GATE-0001"

    batch = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": orders}, headers=gh), 201)
    assert batch["format"] == "pain.001.001.03"  # configured version, not the default
    assert batch["status"] == "file_generated"
    assert batch["transaction_count"] == TRANSFERS
    expected_sum = sum(Decimal(f"{100 + i * 11}.{(i * 7) % 100:02d}") for i in range(TRANSFERS))
    assert Decimal(batch["control_sum"]) == expected_sum
    assert batch["file_sha256"] == hashlib.sha256(batch["xml"].encode()).hexdigest()
    assert batch["document_id"]
    assert _xsd_errors("pain.001.001.03", batch["xml"].encode()) == []
    assert payments.validate_pain001(batch["xml"].encode()) == []
    assert batch["xml"].count("<CdtTrfTxInf>") == TRANSFERS
    assert batch["xml"].count("<PmtInf>") == 2  # one block per execution date
    assert "<BIC>BYLADEM1001</BIC>" in batch["xml"]
    assert "Dienst 0 " in batch["xml"]
    assert "&amp;" not in batch["xml"]  # SEPA character set
    open_items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h)
    )
    assert len([i for i in open_items if Decimal(i["remaining"]) > 0]) >= TRANSFERS  # D06

    # Download: closed gate 403; open gate handed out, logged and checksum verified.
    blocked = client.get(f"{B}/payment-batches/{batch['id']}/file", headers=acc_user)
    assert blocked.status_code == 403, blocked.text
    assert blocked.json()["code"] == "MHVP-GATE-0001"
    no_download = gated.post(
        f"{B}/payment-batches/{batch['id']}/submit", json={"reference": "X"}, headers=gh
    )
    assert no_download.status_code == 409, no_download.text
    assert no_download.json()["code"] == "MHVP-BANK-0018"
    file = gated.get(f"{B}/payment-batches/{batch['id']}/file", headers=gh)
    assert file.status_code == 200, file.text
    assert file.headers["X-Content-SHA256"] == batch["file_sha256"]
    assert file.content == batch["xml"].encode()
    detail = _ok(client.get(f"{B}/payment-batches/{batch['id']}", headers=h))
    assert len(detail["downloads"]) == 1
    assert detail["downloads"][0]["user_id"] == str(world.users["psacc"])
    assert detail["downloads"][0]["file_sha256"] == batch["file_sha256"]
    assert batch["id"] in {b["id"] for b in _ok(client.get(f"{B}/payment-batches", headers=h))}

    # Submission: FinTS and EBICS are scaffolds; the file channel needs a bank reference.
    for channel in ("fints", "ebics"):
        refused = gated.post(
            f"{B}/payment-batches/{batch['id']}/submit", json={"channel": channel}, headers=gh
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "MHVP-BANK-0017"
    missing_ref = gated.post(f"{B}/payment-batches/{batch['id']}/submit", json={}, headers=gh)
    assert missing_ref.status_code == 422, missing_ref.text
    submitted = _ok(
        gated.post(
            f"{B}/payment-batches/{batch['id']}/submit",
            json={"reference": "Onlinebanking Protokoll 4711"},
            headers=gh,
        )
    )
    assert submitted["submitted"] is True
    assert submitted["status"] == "submitted"
    assert submitted["submission_channel"] == "file"
    assert submitted["submitted_by"] == str(world.users["psacc"])
    statuses = {
        o["status"]
        for o in _ok(client.get(f"{B}/payment-orders", headers=h))
        if o["id"] in set(orders)
    }
    assert statuses == {"submitted"}
    twice = gated.post(
        f"{B}/payment-batches/{batch['id']}/submit", json={"reference": "again"}, headers=gh
    )
    assert twice.status_code == 409, twice.text
    assert twice.json()["code"] == "MHVP-BANK-0018"
    assert len([i for i in open_items if Decimal(i["remaining"]) > 0]) >= TRANSFERS  # still D06

    # --- Ten SEPA Core direct debits with mandates ----------------------------------------
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    for i in range(PAYERS):
        party, _ = _payer(client, h, f"Zahler{i}", iban(2000 + i), {}, approver)
        _contract(client, h, prop["id"], f"{i + 1:02d}", party)
    _receivables(client, h, ledger, "2026-03-01")
    _ok(
        client.put(
            f"{D}/creditor-ids/legal-entities/{hoa}",
            json={"sepa_creditor_id": CREDITOR_ID},
            headers=h,
        )
    )
    collection = (local_today() + timedelta(days=7)).isoformat()
    base = {"ledger_id": ledger, "collection_date": collection, "lead_days": 5}
    run = _ok(client.post(f"{D}", json={**base, "property_bank_account_id": bank}, headers=h), 201)
    assert run["transaction_count"] == PAYERS * 2 == 10
    assert Decimal(run["control_sum"]) == Decimal("350.00") * PAYERS
    assert run["format"] == "pain.008.001.02"
    _ok(client.post(f"{D}/{run['id']}/approve", headers=h))
    assert client.post(f"{D}/{run['id']}/file", headers=h).status_code == 403  # four eyes
    _ok(client.post(f"{D}/{run['id']}/approve", headers=acc_user))
    generated = _ok(client.post(f"{D}/{run['id']}/file", headers=h))
    assert generated["status"] == "file_generated"
    assert client.get(f"{D}/{run['id']}/file", headers=h).status_code == 403  # G2 closed
    dd_file = gated.get(f"{D}/{run['id']}/file", headers=gh_admin)
    assert dd_file.status_code == 200, dd_file.text
    assert _xsd_errors("pain.008.001.02", dd_file.content) == []
    assert dd_file.text.count("<DrctDbtTxInf>") == 10
    assert dd_file.text.count("<MndtId>") == 10
    assert f"<Id>{CREDITOR_ID}</Id>" in dd_file.text
    assert _ok(client.get(f"{D}/{run['id']}", headers=h))["status"] == "exported"
