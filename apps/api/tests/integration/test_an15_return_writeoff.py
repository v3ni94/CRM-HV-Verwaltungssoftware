"""AN15: return debit evidence (GAK-101) and write off procedure of open items (GAK-104).

Return keeps the collection reference and records return date and actual fee without
overwriting (409 on a different value); the fee pass on is only shown as proposal with the
tenant switch, never posted. Write off: proposal without effect, approval only with switch,
second person and gate G1; the sub ledger check counts the item as written off only from its
effective date (B07). Tenant separation 404, read only 403, validation 422."""

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m15_payment_run import _dd_setup

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
D = "/api/v1/accounting/direct-debits"
P = "/api/v1/accounting/payment-runs"
W = "/api/v1/accounting/open-item-write-offs"
T = "/api/v1/accounting/tax/settings"


@dataclass
class AnWorld(World):
    def email(self, name: str) -> str:
        return f"an15{name}-{RUN}@example.org"


class Gates:
    def __init__(self, *gates: ReleaseGate) -> None:
        self.gates = gates

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in self.gates


async def _world(settings: Any) -> AnWorld:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"an15-{RUN}", name=f"AN15 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"an15b-{RUN}", name=f"AN15B {RUN}")
        world = AnWorld(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("pradmin", a, "tenant_admin"),
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
def world(database: Database, redis_url: str) -> AnWorld:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[dict[str, TestClient]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url)
        with (
            TestClient(create_app(settings, release_gate_resolver=Gates())) as closed,
            TestClient(create_app(settings, release_gate_resolver=Gates(ReleaseGate.G1))) as g1,
            TestClient(
                create_app(settings, release_gate_resolver=Gates(ReleaseGate.G1, ReleaseGate.G2))
            ) as g12,
        ):
            yield {"closed": closed, "g1": g1, "g12": g12}


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _row(rec: dict[str, Any], order_id: str) -> dict[str, Any]:
    return next(r for r in rec["orders"] if r["order_id"] == order_id)


def _exported_run(c: dict[str, TestClient], world: AnWorld, number: str) -> dict[str, Any]:
    client = c["g1"]
    ctx = _dd_setup(client, world, number)
    h = ctx["h"]
    approver = bearer(login(client, world, "prapprover"))
    collection = (local_today() + timedelta(days=7)).isoformat()
    _ok(client.put(f"{P}/bank-limits/{ctx['bank']}", json={"dd_lead_days_frst": 5}, headers=h))
    run = _ok(
        client.post(
            D,
            json={
                "ledger_id": ctx["ledger"],
                "collection_date": collection,
                "lead_days": 5,
                "property_bank_account_id": ctx["bank"],
            },
            headers=h,
        ),
        201,
    )
    _ok(client.post(f"{D}/{run['id']}/approve", headers=h))
    _ok(client.post(f"{D}/{run['id']}/approve", headers=approver))
    _ok(client.post(f"{D}/{run['id']}/file", headers=h))
    gh = bearer(login(c["g12"], world, "pradmin"))
    assert c["g12"].get(f"{D}/{run['id']}/file", headers=gh).status_code == 200
    return {**ctx, "run": run, "approver": approver}


def test_return_evidence_without_overwrite(clients: dict[str, TestClient], world: AnWorld) -> None:
    client = clients["g1"]
    ctx = _exported_run(clients, world, "915")
    h, run = ctx["h"], ctx["run"]
    first, second = run["orders"][0], run["orders"][1]
    url = f"{D}/{run['id']}/bank-status"
    yesterday = (local_today() - timedelta(days=1)).isoformat()
    future = (local_today() + timedelta(days=1)).isoformat()

    # Validation: return data only with a return, no future date, voucher must exist.
    bad = {"status": "collected", "order_ids": [first["id"]], "return_fee_amount": "3.00"}
    assert client.post(url, json=bad, headers=h).status_code == 422
    bad = {"status": "returned", "order_ids": [first["id"]], "returned_on": future}
    assert client.post(url, json=bad, headers=h).status_code == 422
    bad = {"status": "returned", "order_ids": [first["id"]], "return_fee_amount": "-1"}
    assert client.post(url, json=bad, headers=h).status_code == 422
    bad = {"status": "returned", "order_ids": [first["id"]], "return_fee_document_id": str(uuid4())}
    assert client.post(url, json=bad, headers=h).status_code == 404
    # Fee and date only for one order.
    assert (
        client.post(url, json={"status": "returned", "returned_on": yesterday}, headers=h)
    ).status_code == 422
    reader = bearer(login(client, world, "prreader"))
    body = {
        "status": "returned",
        "order_ids": [first["id"]],
        "reason_code": "MD06",
        "returned_on": yesterday,
        "return_fee_amount": "3.50",
    }
    assert client.post(url, json=body, headers=reader).status_code == 403
    other = bearer(login(client, world, "prother"))
    assert client.post(url, json=body, headers=other).status_code == 404

    rec = _ok(client.post(url, json=body, headers=h))
    row = _row(rec, first["id"])
    assert row["bank_status"] == "returned"
    assert row["returned_on"] == yesterday
    assert row["return_fee_amount"] == "3.50"
    assert row["return_fee_pass_on"] == "locked"  # AN15-01 switch off
    assert row["bank_transaction_id"] is None
    assert row["return_transaction_id"] is None
    # Repeat with the same values: no effect (B08); a different fee is not overwritten.
    _ok(client.post(url, json=body, headers=h))
    changed = {**body, "return_fee_amount": "9.00"}
    assert client.post(url, json=changed, headers=h).status_code == 409

    # Switch on: still only a proposal, nothing posted.
    settings = _ok(client.get(T, headers=h))
    assert settings["return_fee_pass_on_enabled"] is False
    settings.update(return_fee_pass_on_enabled=True)
    _ok(client.put(T, json=settings, headers=h))
    rec = _ok(client.get(f"{D}/{run['id']}/reconciliation", headers=reader))
    assert _row(rec, first["id"])["return_fee_pass_on"] == "proposal"
    settings.update(return_fee_pass_on_enabled=False)
    _ok(client.put(T, json=settings, headers=h))

    # camt.054: the booking date of the entry becomes the return date.
    xml = f"""<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.054.001.08">
<BkToCstmrDbtCdtNtfctn><GrpHdr><MsgId>AN15-{RUN}</MsgId></GrpHdr><Ntfctn><Id>1</Id>
<Ntry><Amt Ccy="EUR">{second["amount"]}</Amt><CdtDbtInd>DBIT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>{yesterday}</Dt></BookgDt>
<NtryDtls><TxDtls><Refs><EndToEndId>{second["end_to_end_id"]}</EndToEndId></Refs>
<RtrInf><Rsn><Cd>AC04</Cd></Rsn></RtrInf></TxDtls></NtryDtls></Ntry></Ntfctn>
</BkToCstmrDbtCdtNtfctn></Document>"""
    report = _ok(client.post(f"{P}/bank-status-reports", json={"xml": xml}, headers=h), 201)
    assert report["result"][0]["result"] == "returned"
    rec = _ok(client.get(f"{D}/{run['id']}/reconciliation", headers=h))
    assert _row(rec, second["id"])["returned_on"] == yesterday
    assert _row(rec, second["id"])["return_fee_amount"] is None


def test_write_off_proposal_four_eyes_and_as_of(
    clients: dict[str, TestClient], world: AnWorld
) -> None:
    client = clients["g1"]
    ctx = _dd_setup(client, world, "916")
    h, ledger = ctx["h"], ctx["ledger"]
    approver = bearer(login(client, world, "prapprover"))
    reader = bearer(login(client, world, "prreader"))
    other = bearer(login(client, world, "prother"))
    items = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/open-items",
            params={"as_of": local_today().isoformat()},
            headers=h,
        )
    )
    item = next(i for i in items if i["kind"] == "receivable")
    effective = (local_today() - timedelta(days=1)).isoformat()
    body = {
        "open_item_id": item["id"],
        "effective_on": effective,
        "reason": "Uneinbringlich nach erfolgloser Vollstreckung",
    }
    assert client.post(W, json={**body, "reason": "kurz"}, headers=h).status_code == 422
    future = (local_today() + timedelta(days=1)).isoformat()
    assert client.post(W, json={**body, "effective_on": future}, headers=h).status_code == 422
    assert client.post(W, json=body, headers=reader).status_code == 403
    assert client.post(W, json=body, headers=other).status_code == 404
    proposal = _ok(client.post(W, json=body, headers=h), 201)
    assert proposal["status"] == "proposed"
    assert proposal["posting_effect"] is False
    assert proposal["approval_enabled"] is False
    assert client.post(W, json=body, headers=h).status_code == 409  # one active proposal
    assert _ok(client.get(W, params={"open_item_id": item["id"]}, headers=reader))
    assert _ok(client.get(W, headers=other)) == []
    assert client.get(W, params={"foo": "1"}, headers=h).status_code == 422

    # AO01: posting preview, display only; counter account open (AN15-02), never postable.
    pv_url = f"{W}/{proposal['id']}/posting-preview"
    preview = _ok(client.get(pv_url, headers=reader))
    assert preview["posting_allowed"] is False
    assert preview["blockers"] == [
        "not_approved",
        "posting_switch_off",
        "counter_account_undecided",
    ]
    assert [ln["side"] for ln in preview["lines"]] == ["debit", "credit"]
    assert preview["lines"][0]["account_id"] is None
    assert preview["lines"][1]["account_id"] == item["account_id"]
    assert preview["lines"][1]["amount"] == preview["amount"] == proposal["amount"]
    assert client.get(pv_url, headers=other).status_code == 404
    assert client.get(f"{W}/{uuid4()}/posting-preview", headers=h).status_code == 404

    url = f"{W}/{proposal['id']}/decision"
    assert client.post(url, json={"decision": "approve"}, headers=other).status_code == 404
    assert client.post(url, json={"decision": "approve"}, headers=reader).status_code == 403
    assert client.post(url, json={"decision": "maybe"}, headers=h).status_code == 422
    # Switch off (AN15-02): approval refused, proposal stays without effect.
    assert client.post(url, json={"decision": "approve"}, headers=approver).status_code == 409
    checks = _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))
    assert checks["excluded"]["written_off"]["count"] == 0

    settings = _ok(client.get(T, headers=h))
    settings.update(write_off_approval_enabled=True)
    _ok(client.put(T, json=settings, headers=h))
    # Gate G1 closed: refused.
    closed = clients["closed"]
    ch = bearer(login(closed, world, "prapprover"))
    gate = closed.post(url, json={"decision": "approve"}, headers=ch)
    assert gate.status_code == 403, gate.text
    assert gate.json()["code"] == "MHVP-GATE-0001"
    # Four eyes: the proposing person cannot approve.
    assert client.post(url, json={"decision": "approve"}, headers=h).status_code == 409
    done = _ok(client.post(url, json={"decision": "approve", "note": "GF"}, headers=approver))
    assert done["status"] == "approved"
    assert done["decided_by"] is not None
    assert done["revocation_status"] == "locked"  # AO01: switch off, AN15-02 open
    preview = _ok(client.get(pv_url, headers=h))
    assert preview["blockers"] == ["posting_switch_off", "counter_account_undecided"]
    assert preview["posting_allowed"] is False
    closed_preview = _ok(closed.get(pv_url, headers=ch))
    assert closed_preview["blockers"] == [
        "gate_g1_closed",
        "posting_switch_off",
        "counter_account_undecided",
    ]
    assert client.post(url, json={"decision": "reject"}, headers=approver).status_code == 409

    # B07: written off only from the effective date onwards.
    before = (local_today() - timedelta(days=2)).isoformat()
    early = _ok(client.get(f"{A}/ledgers/{ledger}/checks", params={"as_of": before}, headers=h))
    assert early["excluded"]["written_off"]["count"] == 0
    now = _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))
    assert now["excluded"]["written_off"]["count"] == 1

    settings.update(write_off_approval_enabled=False)
    _ok(client.put(T, json=settings, headers=h))
