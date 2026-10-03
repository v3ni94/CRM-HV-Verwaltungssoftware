"""AP12 (GAK-104 rest, GAM-605): posting of an approved write off and its reversal.

Posting needs the tenant switch ``accounting.write_off_posting`` (default off), a counter
account set by the tenant (no default, AN15-02 open), gate G1 and the amount and counter
account confirmed from the preview. Expected results are fixed: the item amount stays as
booked, the remaining amount after posting is 0.00 EUR, exactly one entry exists after two
parallel calls, a failed posting leaves nothing behind (rollback), the reversal restores the
remaining amount without changing the posted entry. Tenant separation 404, read only 403,
validation 422."""

import asyncio
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
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
W = "/api/v1/accounting/open-item-write-offs"
T = "/api/v1/accounting/tax/settings"


@dataclass
class ApWorld(World):
    def email(self, name: str) -> str:
        return f"ap12{name}-{RUN}@example.org"


class Gates:
    def __init__(self, *gates: ReleaseGate) -> None:
        self.gates = gates

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in self.gates


async def _world(settings: Any) -> ApWorld:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ap12-{RUN}", name=f"AP12 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ap12b-{RUN}", name=f"AP12B {RUN}")
        world = ApWorld(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
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
def world(database: Database, redis_url: str) -> ApWorld:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[dict[str, TestClient]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url)
        with (
            TestClient(create_app(settings, release_gate_resolver=Gates())) as closed,
            TestClient(create_app(settings, release_gate_resolver=Gates(ReleaseGate.G1))) as g1,
        ):
            yield {"closed": closed, "g1": g1}


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _item(c: TestClient, h: dict[str, str], ledger: str, item_id: str) -> dict[str, Any] | None:
    items = _ok(
        c.get(
            f"{A}/ledgers/{ledger}/open-items",
            params={"as_of": local_today().isoformat()},
            headers=h,
        )
    )
    return next((i for i in items if i["id"] == item_id), None)


def _parallel(fn: Any, n: int = 2) -> list[Any]:
    barrier = threading.Barrier(n)

    def run(_: int) -> Any:
        barrier.wait()
        return fn()

    with ThreadPoolExecutor(n) as pool:
        return list(pool.map(run, range(n)))


def _approved(c: TestClient, world: ApWorld, number: str) -> dict[str, Any]:
    ctx = _dd_setup(c, world, number)
    h, ledger = ctx["h"], ctx["ledger"]
    approver = bearer(login(c, world, "prapprover"))
    items = _ok(
        c.get(
            f"{A}/ledgers/{ledger}/open-items",
            params={"as_of": local_today().isoformat()},
            headers=h,
        )
    )
    item = next(i for i in items if i["kind"] == "receivable")
    body = {
        "open_item_id": item["id"],
        "effective_on": (local_today() - timedelta(days=1)).isoformat(),
        "reason": "Uneinbringlich nach erfolgloser Vollstreckung",
    }
    proposal = _ok(c.post(W, json=body, headers=h), 201)
    settings = _ok(c.get(T, headers=h))
    settings.update(write_off_approval_enabled=True)
    _ok(c.put(T, json=settings, headers=h))
    done = _ok(
        c.post(f"{W}/{proposal['id']}/decision", json={"decision": "approve"}, headers=approver)
    )
    assert done["status"] == "approved"
    accounts = _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    cost = next(a for a in accounts if a["category"] == "cost" and a["active"])
    return {
        **ctx,
        "approver": approver,
        "item": item,
        "write_off": done,
        "cost": cost,
    }


def test_write_off_posting_switch_gate_preview_parallel_rollback_reversal(
    clients: dict[str, TestClient], world: ApWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    c, closed = clients["g1"], clients["closed"]
    ctx = _approved(c, world, "931")
    h, ledger, approver = ctx["h"], ctx["ledger"], ctx["approver"]
    item, wo, cost = ctx["item"], ctx["write_off"], ctx["cost"]
    reader = bearer(login(c, world, "prreader"))
    other = bearer(login(c, world, "prother"))
    amount = wo["amount"]
    assert amount == item["remaining"]
    post_url = f"{W}/{wo['id']}/posting"
    pv_url = f"{W}/{wo['id']}/posting-preview"
    s_url = f"{W}/settings"

    # Defaults: switch off, no counter account (AN15-02 not decided).
    assert _ok(c.get(s_url, headers=reader)) == {
        "posting_enabled": False,
        "counter_account_number": None,
        "question": "AN15-02",
    }
    preview = _ok(c.get(pv_url, headers=h))
    assert preview["blockers"] == ["posting_switch_off", "counter_account_undecided"]
    assert preview["posting_allowed"] is False
    body = {"expected_amount": amount, "counter_account_id": cost["id"]}
    locked = c.post(post_url, json=body, headers=approver)
    assert locked.status_code == 409, locked.text
    assert locked.json()["code"] == "MHVP-ACC-0044"

    # Settings: read only 403, validation 422, tenant separation.
    new = {"posting_enabled": True, "counter_account_number": cost["number"]}
    assert c.put(s_url, json=new, headers=reader).status_code == 403
    bad = {**new, "counter_account_number": "abc"}
    assert c.put(s_url, json=bad, headers=h).status_code == 422
    assert c.put(s_url, json={**new, "x": 1}, headers=h).status_code == 422
    # Counter account must not be the receivable account itself.
    _ok(c.put(s_url, json={**new, "counter_account_number": item["account_number"]}, headers=h))
    assert _ok(c.get(pv_url, headers=h))["blockers"] == ["counter_account_invalid"]
    _ok(c.put(s_url, json=new, headers=h))
    assert _ok(c.get(s_url, headers=other))["posting_enabled"] is False

    preview = _ok(c.get(pv_url, headers=h))
    assert preview["blockers"] == []
    assert preview["posting_allowed"] is True
    assert preview["lines"][0]["account_id"] == cost["id"]
    assert preview["lines"][0]["amount"] == preview["lines"][1]["amount"] == amount
    closed_h = bearer(login(closed, world, "prapprover"))
    assert _ok(closed.get(pv_url, headers=closed_h))["blockers"] == ["gate_g1_closed"]

    # Route checks: gate, permission, tenant, validation, preview mismatch.
    gate = closed.post(post_url, json=body, headers=closed_h)
    assert gate.status_code == 403
    assert gate.json()["code"] == "MHVP-GATE-0001"
    assert c.post(post_url, json=body, headers=reader).status_code == 403
    assert c.post(post_url, json=body, headers=other).status_code == 404
    assert c.post(f"{W}/{uuid4()}/posting", json=body, headers=h).status_code == 404
    assert c.post(post_url, json={**body, "expected_amount": "-1"}, headers=h).status_code == 422
    wrong = c.post(post_url, json={**body, "expected_amount": "0.01"}, headers=approver)
    assert wrong.status_code == 409
    assert wrong.json()["code"] == "MHVP-ACC-0044"

    # Rollback: a failure inside the posting leaves no entry and no settlement.
    from mhvp.accounting import services as acc

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("abort after draft")

    monkeypatch.setattr(acc, "post", boom)
    aborted = c.post(post_url, json=body, headers=approver)
    assert aborted.status_code == 500  # unhandled error, sanitised problem
    monkeypatch.undo()
    after_abort = _item(c, h, ledger, item["id"])
    assert after_abort is not None
    assert after_abort["remaining"] == amount
    assert _ok(c.get(pv_url, headers=h))["posting_entry_id"] is None

    # Parallel: two postings at once, exactly one entry; the second is a repeat (B08).
    results = _parallel(lambda: c.post(post_url, json=body, headers=approver))
    payloads = [_ok(r) for r in results]
    assert len({p["journal_entry_id"] for p in payloads}) == 1
    assert sorted(p["repeated"] for p in payloads) == [False, True]
    entry_id = payloads[0]["journal_entry_id"]
    assert _item(c, h, ledger, item["id"]) is None  # remaining 0.00 EUR
    again = _ok(c.post(post_url, json=body, headers=approver))
    assert again["repeated"] is True
    assert again["journal_entry_id"] == entry_id
    entry = _ok(c.get(f"{A}/ledgers/{ledger}/entries/{entry_id}", headers=h))
    assert entry["status"] == "posted"
    lines = {(ln["account_id"], ln["debit"], ln["credit"]) for ln in entry["lines"]}
    assert lines == {(cost["id"], amount, "0.00"), (item["account_id"], "0.00", amount)}
    listed = _ok(c.get(W, params={"open_item_id": item["id"]}, headers=reader))[0]
    assert listed["posting_entry_id"] == entry_id
    assert listed["posting_effect"] is True
    assert _ok(c.get(pv_url, headers=h))["blockers"] == ["already_posted"]

    # Reversal instead of overwriting; parallel calls give one reversal.
    rev_url = f"{post_url}/reversal"
    rev = {"reason": "Zahlung nach Ausbuchung eingegangen"}
    assert c.post(rev_url, json={"reason": "kurz"}, headers=h).status_code == 422
    assert c.post(rev_url, json=rev, headers=reader).status_code == 403
    assert c.post(rev_url, json=rev, headers=other).status_code == 404
    gate = closed.post(rev_url, json=rev, headers=closed_h)
    assert gate.status_code == 403
    results = _parallel(lambda: c.post(rev_url, json=rev, headers=approver))
    payloads = [_ok(r) for r in results]
    assert len({p["reversal_id"] for p in payloads}) == 1
    assert sorted(p["repeated"] for p in payloads) == [False, True]
    reopened = _item(c, h, ledger, item["id"])
    assert reopened is not None
    assert reopened["remaining"] == reopened["amount"] == item["amount"]
    original = _ok(c.get(f"{A}/ledgers/{ledger}/entries/{entry_id}", headers=h))
    assert original["status"] == "posted"
    assert {(ln["account_id"], ln["debit"], ln["credit"]) for ln in original["lines"]} == lines
    listed = _ok(c.get(W, params={"open_item_id": item["id"]}, headers=h))[0]
    assert listed["posting_reversal_id"] == payloads[0]["reversal_id"]

    _ok(c.put(s_url, json={"posting_enabled": False, "counter_account_number": None}, headers=h))
