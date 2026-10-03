"""AQ09 (GAM-601 to GAM-604, rule 0.1.9): concurrency, retry, abort/rollback and historical
cut-off dates of the payment run, the direct debit run, the bank feedback and the return debit.

Expected values are fixed in advance (rule 0.1.8) and never taken from the API under test:

- GAM-601: two orders 1.000,00 EUR and 234,56 EUR; control sum 1.000,00 + 234,56 =
  1.234,56 EUR; two approvers at the same time give two approvals, two simultaneous batch
  creations give one file, two simultaneous submissions give one 200 and one 409, exactly one
  ``payment_batch.submitted`` event.
- GAM-602: a failure after the status change (event write fails) rolls the whole request
  back: run stays ``approved`` without document, payment orders stay ``approved`` without
  batch, open items unchanged (850,00 EUR); the retry creates exactly one file.
- GAM-603: the same return (same bank debit) reported twice in parallel and once more
  afterwards: one ``direct_debit_order.returned`` event; the settlement is reversed by a person
  (rule 0.1.7, no automatic posting) and two parallel reversals give exactly one reversal; the
  open item is open again by exactly the collection amount 850,00 EUR.
- GAM-604: collection booked 05.03.2026, return 12.03.2026: remaining as of 04.03. = 850,00,
  as of 10.03. = 0,00, as of 12.03. = 850,00 EUR.

Synthetic data only, no network."""

import asyncio
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
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
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m15_direct_debits import CREDITOR_ID, _payer

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"
D = "/api/v1/accounting/direct-debits"
P = "/api/v1/accounting/payment-runs"

# Fixed expectations (rule 0.1.8).
ORDER_1 = Decimal("1000.00")
ORDER_2 = Decimal("234.56")
CONTROL_SUM = "1234.56"  # 1.000,00 + 234,56
DEBIT = "850.00"
COLLECTED_ON = "2026-03-05"
RETURNED_ON = "2026-03-12"


def _iban(account: int, blz: str = "37040044") -> str:
    """Synthetic, checksum valid German IBAN (mod 97), never a real account."""
    bban = f"{blz}{account:010d}"
    digits = "".join(str(int(c, 36)) for c in f"{bban}DE00")
    return f"DE{98 - int(digits) % 97:02d}{bban}"


PAYER = _iban(9_209_001)
PROVIDER = _iban(9_209_002)


class Gates:
    def __init__(self, *gates: ReleaseGate) -> None:
        self.gates = gates

    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate in self.gates


G1 = Gates(ReleaseGate.G1)
G12 = Gates(ReleaseGate.G1, ReleaseGate.G2)


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"aq09-{RUN}", name=f"AQ09 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"aq09b-{RUN}", name=f"AQ09b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("aq09admin", a, "tenant_admin"),
            ("aq09acc", a, "accountant_banking"),
            ("aq09appr", a, "tenant_admin"),
            ("aq09other", b, "tenant_admin"),
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
def env(database: Database, redis_url: str) -> Iterator[dict[str, Any]]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = _settings(database, redis_url)
        with (
            TestClient(create_app(settings, release_gate_resolver=G1)) as g1,
            TestClient(
                create_app(settings, release_gate_resolver=G12), raise_server_exceptions=False
            ) as g12,
        ):
            yield {"g1": g1, "g12": g12, "settings": settings}


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _parallel(
    settings: Any, gates: Gates, calls: Sequence[Callable[..., Any]]
) -> list[tuple[int, Any]]:
    """Each call runs in its own app instance (own engine and pool), all at the same time."""

    def run(call: Callable[[TestClient], Any]) -> tuple[int, Any]:
        with TestClient(
            create_app(settings, release_gate_resolver=gates), raise_server_exceptions=False
        ) as own:
            r = call(own)
            try:
                return r.status_code, r.json()
            except ValueError:
                return r.status_code, r.text

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(run, calls))


async def _count_events(settings: Any, tenant: UUID, type_: str, entity_id: str) -> int:
    from sqlalchemy import func, select

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.events import DomainEvent

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant) as session:
            return int(
                await session.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(DomainEvent.type == type_, DomainEvent.entity_id == UUID(entity_id))
                )
                or 0
            )
    finally:
        await engine.dispose()


def _events(env: dict[str, Any], world: World, type_: str, entity_id: str) -> int:
    return asyncio.run(_count_events(env["settings"], world.tenant_a, type_, entity_id))


def _base(c: TestClient, h: dict[str, str], number: str) -> dict[str, str]:
    """Property, HOA, own bank account with ledger account 001210, leading ledger."""
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AQ09 Haus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank_iban = _iban(9_209_100 + int(number))
    bank = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": bank_iban,
                "holder": f"GdWE AQ09 {number}",
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
    bank_account = _ok(
        c.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001210",
                "name": "WEG-Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank,
            },
            headers=h,
        ),
        201,
    )["id"]
    return {
        "property": prop["id"],
        "hoa": hoa,
        "bank": bank,
        "bank_iban": bank_iban,
        "ledger": ledger,
        "bank_account": bank_account,
    }


# GAM-601 -------------------------------------------------------------------------------


def _two_orders(c: TestClient, world: World, base: dict[str, str]) -> list[str]:
    h = bearer(login(c, world, "aq09admin"))
    acc_user = bearer(login(c, world, "aq09acc"))
    approver = bearer(login(c, world, "aq09appr"))
    ledger = base["ledger"]
    acc = {a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"AQ09 Dienst {base['property']} {RUN} GmbH",
                "bank_accounts": [{"iban": PROVIDER, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )["id"]
    approve_bank_accounts(c, approver, provider)
    orders = []
    for no, gross in (("AQ09-1", ORDER_1), ("AQ09-2", ORDER_2)):
        inv = _ok(
            c.post(
                f"{A}/invoices",
                json={
                    "ledger_id": ledger,
                    "provider_contact_id": provider,
                    "number": no,
                    "invoice_date": "2026-02-01",
                    "due_date": "2026-02-20",
                    "service_from": "2026-01-01",
                    "net": str(gross),
                    "vat": "0.00",
                    "gross": str(gross),
                    "payee_iban": PROVIDER,
                    "lines": [{"account_id": acc["040300"], "net": str(gross)}],
                },
                headers=h,
            ),
            201,
        )["id"]
        for step in ("completeness", "factual", "arithmetic_tax"):
            _ok(
                c.post(
                    f"{A}/invoices/{inv}/reviews",
                    json={"step": step, "result": "ok", "reason": "geprüft"},
                    headers=h,
                ),
                201,
            )
        _ok(c.post(f"{A}/invoices/{inv}/release", headers=acc_user))
        _ok(c.post(f"{A}/invoices/{inv}/post", headers=h))
        orders.append(
            _ok(
                c.post(
                    f"{B}/payment-orders",
                    json={
                        "invoice_id": inv,
                        "property_bank_account_id": base["bank"],
                        "execution_date": "2026-02-05",
                    },
                    headers=h,
                ),
                201,
            )["id"]
        )
    return orders


def _orders_by_id(c: TestClient, h: dict[str, str], ids: list[str]) -> dict[str, Any]:
    return {o["id"]: o for o in _ok(c.get(f"{B}/payment-orders", headers=h)) if o["id"] in ids}


def test_payment_run_parallel_approve_and_submit(env: dict[str, Any], world: World) -> None:
    client, gated, settings = env["g1"], env["g12"], env["settings"]
    h = bearer(login(client, world, "aq09admin"))
    acc_user = bearer(login(client, world, "aq09acc"))
    gh = bearer(login(gated, world, "aq09acc"))
    base = _base(client, h, "921")
    ids = _two_orders(client, world, base)

    # Two approvers approve both orders at the same time: two approvals each, approved.
    calls = [
        (lambda c, o=oid, who=who: c.post(f"{B}/payment-orders/{o}/approve", headers=who))
        for oid in ids
        for who in (h, acc_user)
    ]
    results = _parallel(settings, G1, calls)
    assert [code for code, _ in results] == [200, 200, 200, 200], results
    state = _orders_by_id(client, h, ids)
    assert {o["status"] for o in state.values()} == {"approved"}
    assert {o["approvals"] for o in state.values()} == {2}
    # The same approver again from two instances at once counts once (B08).
    results = _parallel(
        settings,
        G1,
        [lambda c: c.post(f"{B}/payment-orders/{ids[0]}/approve", headers=acc_user)] * 2,
    )
    assert [code for code, _ in results] == [200, 200], results
    assert _orders_by_id(client, h, ids)[ids[0]]["approvals"] == 2

    # Two simultaneous file creations for the same orders: exactly one file.
    before = {b["id"] for b in _ok(client.get(f"{B}/payment-batches", headers=h))}
    results = _parallel(
        settings,
        G12,
        [lambda c: c.post(f"{B}/payment-batches", json={"order_ids": ids}, headers=gh)] * 2,
    )
    codes = sorted(code for code, _ in results)
    assert codes[0] == 201, results
    assert codes[1] in (403, 409), results
    batches = [
        b for b in _ok(client.get(f"{B}/payment-batches", headers=h)) if b["id"] not in before
    ]
    assert len(batches) == 1
    batch = batches[0]
    assert batch["transaction_count"] == 2
    assert batch["control_sum"] == CONTROL_SUM
    assert gated.get(f"{B}/payment-batches/{batch['id']}/file", headers=gh).status_code == 200

    # Two simultaneous submissions: one 200, one 409, one submitted event.
    results = _parallel(
        settings,
        G12,
        [
            lambda c: c.post(
                f"{B}/payment-batches/{batch['id']}/submit",
                json={"reference": "AQ09 A"},
                headers=gh,
            ),
            lambda c: c.post(
                f"{B}/payment-batches/{batch['id']}/submit",
                json={"reference": "AQ09 B"},
                headers=gh,
            ),
        ],
    )
    assert sorted(code for code, _ in results) == [200, 409], results
    assert next(b for c, b in results if c == 409)["code"] == "MHVP-BANK-0018"
    assert _events(env, world, "payment_batch.submitted", batch["id"]) == 1
    detail = _ok(client.get(f"{B}/payment-batches/{batch['id']}", headers=h))
    assert detail["status"] == "submitted"
    assert detail["control_sum"] == CONTROL_SUM  # unchanged by the parallel calls
    state = _orders_by_id(client, h, ids)
    assert {o["status"] for o in state.values()} == {"submitted"}
    assert sum(Decimal(o["amount"]) for o in state.values()) == ORDER_1 + ORDER_2
    # Another tenant sees nothing.
    other = bearer(login(client, world, "aq09other"))
    assert client.get(f"{B}/payment-batches/{batch['id']}", headers=other).status_code == 404


# Shared direct debit world (GAM-602 to GAM-604) ---------------------------------------


def _debit_world(c: TestClient, world: World, number: str) -> dict[str, Any]:
    """One payer with mandate, one receivable run of 850,00 EUR due 03.03.2026."""
    h = bearer(login(c, world, "aq09admin"))
    approver = bearer(login(c, world, "aq09appr"))
    base = _base(c, h, number)
    _ok(
        c.put(
            f"{D}/creditor-ids/legal-entities/{base['hoa']}",
            json={"sepa_creditor_id": CREDITOR_ID},
            headers=h,
        )
    )
    party, contact = _payer(c, h, f"Q{number}", PAYER, {}, approver)
    unit = _unit(c, h, base["property"], "01")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )["id"]
    acc = {
        a["number"]: a["id"]
        for a in _ok(c.get(f"{A}/ledgers/{base['ledger']}/accounts", headers=h))
    }
    _ok(
        c.put(
            f"{A}/ledgers/{base['ledger']}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": acc["060100"]},
            headers=h,
        )
    )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract}/payments",
            json={
                "payment_type_code": "hoa_fee",
                "net": DEBIT,
                "gross": DEBIT,
                "valid_from": "2026-03-01",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract}/schedules",
            json={"valid_from": "2026-03-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    run = _ok(c.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201)
    _ok(c.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    [item] = [
        i
        for i in _ok(
            c.get(
                f"{A}/ledgers/{base['ledger']}/open-items",
                params={"as_of": "2026-03-31"},
                headers=h,
            )
        )
        if i["kind"] == "receivable"
    ]
    assert item["amount"] == DEBIT
    assert item["remaining"] == DEBIT
    assert item["due_date"] == "2026-03-03"
    return {**base, "h": h, "contact": contact, "item": item["id"]}


def _approved_run(c: TestClient, world: World, ctx: dict[str, Any]) -> str:
    from mhvp.core.clock import local_today

    h = ctx["h"]
    acc_user = bearer(login(c, world, "aq09acc"))
    collection = local_today().toordinal() + 7
    from datetime import date

    run = _ok(
        c.post(
            D,
            json={
                "ledger_id": ctx["ledger"],
                "collection_date": date.fromordinal(collection).isoformat(),
                "lead_days": 5,
                "property_bank_account_id": ctx["bank"],
            },
            headers=h,
        ),
        201,
    )
    assert run["transaction_count"] == 1
    assert run["control_sum"] == DEBIT
    _ok(c.post(f"{D}/{run['id']}/approve", headers=h))
    assert _ok(c.post(f"{D}/{run['id']}/approve", headers=acc_user))["status"] == "approved"
    return str(run["id"])


def _remaining(c: TestClient, h: dict[str, str], ctx: dict[str, Any], as_of: str) -> str:
    items = _ok(
        c.get(f"{A}/ledgers/{ctx['ledger']}/open-items", params={"as_of": as_of}, headers=h)
    )
    hit = [i["remaining"] for i in items if i["id"] == ctx["item"]]
    return hit[0] if hit else "0.00"


# GAM-602 -------------------------------------------------------------------------------


class _InjectedError(RuntimeError):
    pass


def test_debit_run_submit_rollback_on_export_failure(
    env: dict[str, Any], world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mhvp.accounting import direct_debit_routers
    from mhvp.banking import routers as banking_routers

    client, gated = env["g1"], env["g12"]
    ctx = _debit_world(client, world, "922")
    h = ctx["h"]
    run_id = _approved_run(client, world, ctx)

    async def failing_emit(*args: Any, **kwargs: Any) -> None:
        raise _InjectedError("export aborted after status change")

    # Direct debit: the file is built, filed and the status set, then the event write fails.
    with monkeypatch.context() as m:
        m.setattr(direct_debit_routers, "emit", failing_emit)
        aborted = gated.post(f"{D}/{run_id}/file", headers=bearer(login(gated, world, "aq09admin")))
        assert aborted.status_code == 500, aborted.text
    state = _ok(client.get(f"{D}/{run_id}", headers=h))
    assert state["status"] == "approved"
    assert state["document_id"] is None
    assert state["approvals"] == 2
    assert _events(env, world, "direct_debit_run.file_generated", run_id) == 0
    assert _remaining(client, h, ctx, "2026-03-31") == DEBIT  # no open item change
    # Retry: exactly one file.
    retried = _ok(client.post(f"{D}/{run_id}/file", headers=h))
    assert retried["status"] == "file_generated"
    assert retried["document_id"]
    assert _events(env, world, "direct_debit_run.file_generated", run_id) == 1
    assert client.post(f"{D}/{run_id}/file", headers=h).status_code in (403, 409)
    assert _events(env, world, "direct_debit_run.file_generated", run_id) == 1
    assert _remaining(client, h, ctx, "2026-03-31") == DEBIT

    # Payment run: same abort when creating the payment file; orders stay approved.
    base = _base(client, h, "923")
    ids = _two_orders(client, world, base)
    acc_user = bearer(login(client, world, "aq09acc"))
    for oid in ids:
        _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=h))
        _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=acc_user))
    gh = bearer(login(gated, world, "aq09acc"))
    before = {b["id"] for b in _ok(client.get(f"{B}/payment-batches", headers=h))}
    with monkeypatch.context() as m:
        m.setattr(banking_routers, "emit", failing_emit)
        aborted = gated.post(f"{B}/payment-batches", json={"order_ids": ids}, headers=gh)
        assert aborted.status_code == 500, aborted.text
    assert {b["id"] for b in _ok(client.get(f"{B}/payment-batches", headers=h))} == before
    state_orders = _orders_by_id(client, h, ids)
    assert {o["status"] for o in state_orders.values()} == {"approved"}
    assert {o["batch_id"] for o in state_orders.values()} == {None}
    batch = _ok(gated.post(f"{B}/payment-batches", json={"order_ids": ids}, headers=gh), 201)
    assert batch["control_sum"] == CONTROL_SUM
    after = [b for b in _ok(client.get(f"{B}/payment-batches", headers=h)) if b["id"] not in before]
    assert len(after) == 1


def test_debit_file_abort_leaves_no_orphan_blob(
    env: dict[str, Any], world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mhvp.accounting import direct_debit_routers

    client = env["g1"]
    ctx = _debit_world(client, world, "926")
    run_id = _approved_run(client, world, ctx)
    s3 = boto3.client("s3", region_name="us-east-1")
    stored = int(s3.list_objects_v2(Bucket=BUCKET).get("KeyCount", 0))

    async def failing_emit(*args: Any, **kwargs: Any) -> None:
        raise _InjectedError("export aborted after status change")

    gated = env["g12"]
    with monkeypatch.context() as m:
        m.setattr(direct_debit_routers, "emit", failing_emit)
        aborted = gated.post(f"{D}/{run_id}/file", headers=bearer(login(gated, world, "aq09admin")))
        assert aborted.status_code == 500, aborted.text
    # Expected: 0 new objects (the abort leaves nothing behind).
    assert int(s3.list_objects_v2(Bucket=BUCKET).get("KeyCount", 0)) == stored


def test_payment_batch_abort_leaves_no_orphan_blob(
    env: dict[str, Any], world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AQ09-01 (AP26): the pain.001 blob written before the aborted commit is compensated."""
    from mhvp.banking import routers as banking_routers

    client = env["g1"]
    h = bearer(login(client, world, "aq09admin"))
    base = _base(client, h, "927")
    ids = _two_orders(client, world, base)
    acc_user = bearer(login(client, world, "aq09acc"))
    for oid in ids:
        _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=h))
        _ok(client.post(f"{B}/payment-orders/{oid}/approve", headers=acc_user))
    s3 = boto3.client("s3", region_name="us-east-1")
    stored = int(s3.list_objects_v2(Bucket=BUCKET).get("KeyCount", 0))

    async def failing_emit(*args: Any, **kwargs: Any) -> None:
        raise _InjectedError("payment file aborted after status change")

    gated = env["g12"]
    gh = bearer(login(gated, world, "aq09acc"))
    with monkeypatch.context() as m:
        m.setattr(banking_routers, "emit", failing_emit)
        aborted = gated.post(f"{B}/payment-batches", json={"order_ids": ids}, headers=gh)
        assert aborted.status_code == 500, aborted.text
    assert int(s3.list_objects_v2(Bucket=BUCKET).get("KeyCount", 0)) == stored
    # Retry succeeds and its committed file stays (no deletion of referenced documents).
    _ok(gated.post(f"{B}/payment-batches", json={"order_ids": ids}, headers=gh), 201)
    assert int(s3.list_objects_v2(Bucket=BUCKET).get("KeyCount", 0)) == stored + 1


# GAM-603 and GAM-604 ---------------------------------------------------------------------


def _camt(stmt_id: str, iban: str, entries: list[tuple[str, str, str, str]]) -> bytes:
    rows = []
    for ref, amount, ind, day in entries:
        party = "Dbtr" if ind == "CRDT" else "Cdtr"
        rows.append(
            f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>{ind}</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
<BookgDt><Dt>{day}</Dt></BookgDt><ValDt><Dt>{day}</Dt></ValDt><AcctSvcrRef>{ref}</AcctSvcrRef>
<NtryDtls><TxDtls><Refs><EndToEndId>NOTPROVIDED</EndToEndId></Refs>
<RltdPties><{party}><Nm>Zahler</Nm></{party}><{party}Acct><Id><IBAN>{PAYER}</IBAN></Id></{party}Acct></RltdPties>
<RmtInf><Ustrd>Hausgeld Lastschrift</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08"><BkToCstmrStmt>
<GrpHdr><MsgId>M-{stmt_id}</MsgId><CreDtTm>2026-03-31T08:00:00</CreDtTm></GrpHdr>
<Stmt><Id>{stmt_id}</Id><FrToDt><FrDtTm>2026-03-01T00:00:00</FrDtTm><ToDtTm>2026-03-31T23:59:59</ToDtTm></FrToDt>
<Acct><Id><IBAN>{iban}</IBAN></Id><Ccy>EUR</Ccy></Acct>
<Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">0.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-03-01</Dt></Dt></Bal>
<Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="EUR">0.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-03-31</Dt></Dt></Bal>
{"".join(rows)}</Stmt></BkToCstmrStmt></Document>""".encode()


def _returned_world(env: dict[str, Any], world: World, number: str) -> dict[str, Any]:
    """Exported run, collection credited 05.03. and booked against the open item, return
    debit 12.03. in the statement."""
    client, gated = env["g1"], env["g12"]
    ctx = _debit_world(client, world, number)
    h = ctx["h"]
    run_id = _approved_run(client, world, ctx)
    _ok(client.post(f"{D}/{run_id}/file", headers=h))
    gh = bearer(login(gated, world, "aq09admin"))
    assert gated.get(f"{D}/{run_id}/file", headers=gh).status_code == 200
    [order] = _ok(client.get(f"{D}/{run_id}/orders", headers=h))
    statement = _camt(
        f"AQ09-{number}-{RUN}",
        ctx["bank_iban"],
        [
            (f"C{number}{RUN}", DEBIT, "CRDT", COLLECTED_ON),
            (f"R{number}{RUN}", DEBIT, "DBIT", RETURNED_ON),
        ],
    )
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": (f"aq09-{number}.xml", statement, "application/xml")},
            headers=h,
        ),
        201,
    )["id"]
    _ok(client.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)
    txs = {t["bank_reference"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}
    credit, debit = txs[f"C{number}{RUN}"], txs[f"R{number}{RUN}"]
    booked = _ok(
        client.post(
            f"{B}/transactions/{credit['id']}/book",
            json={"settlements": [{"open_item_id": ctx["item"], "amount": DEBIT}]},
            headers=h,
        ),
        201,
    )
    entry_id = booked.get("journal_entry_id") or booked.get("id")
    assert entry_id
    _ok(
        client.post(
            f"{D}/{run_id}/bank-status",
            json={
                "status": "collected",
                "order_ids": [order["id"]],
                "bank_transaction_id": credit["id"],
            },
            headers=h,
        )
    )
    return {
        **ctx,
        "run": run_id,
        "order": order["id"],
        "debit_tx": debit["id"],
        "entry": str(entry_id),
    }


def test_return_feedback_idempotent_and_parallel(env: dict[str, Any], world: World) -> None:
    client, settings = env["g1"], env["settings"]
    ctx = _returned_world(env, world, "924")
    h = ctx["h"]
    assert _remaining(client, h, ctx, "2026-03-31") == "0.00"
    body = {
        "status": "returned",
        "order_ids": [ctx["order"]],
        "reason_code": "MD06",
        "returned_on": RETURNED_ON,
        "bank_transaction_id": ctx["debit_tx"],
    }
    url = f"{D}/{ctx['run']}/bank-status"
    results = _parallel(settings, G1, [lambda c: c.post(url, json=body, headers=h)] * 2)
    assert [code for code, _ in results] == [200, 200], results
    assert _ok(client.post(url, json=body, headers=h))  # third report: no effect (B08)
    assert _events(env, world, "direct_debit_order.returned", ctx["order"]) == 1
    rec = _ok(client.get(f"{D}/{ctx['run']}/reconciliation", headers=h))
    [row] = rec["orders"]
    assert row["bank_status"] == "returned"
    assert row["returned_on"] == RETURNED_ON
    assert row["return_transaction_id"] == ctx["debit_tx"]
    assert (
        row["finding"] == "Rücklastschrift nach Ausgleich: Ausgleichsbuchung per Storno korrigieren"
    )
    # Nothing is posted automatically (rule 0.1.7): the item is still settled.
    assert _remaining(client, h, ctx, "2026-03-31") == "0.00"

    # A person reverses the settlement; two parallel reversals give exactly one.
    rev = f"{A}/ledgers/{ctx['ledger']}/entries/{ctx['entry']}/reverse"
    rbody = {"reason": "Rücklastschrift MD06", "booking_date": RETURNED_ON}
    results = _parallel(settings, G1, [lambda c: c.post(rev, json=rbody, headers=h)] * 2)
    codes = sorted(code for code, _ in results)
    assert codes[0] == 201, results
    assert codes[1] in (409, 422), results
    assert _events(env, world, "journal_entry.reversed", ctx["entry"]) == 1
    assert _remaining(client, h, ctx, "2026-03-31") == DEBIT  # open again by 850,00 EUR
    rec = _ok(client.get(f"{D}/{ctx['run']}/reconciliation", headers=h))
    assert rec["orders"][0]["open_item_remaining"] == DEBIT
    assert rec["orders"][0]["finding"] is None
    other = bearer(login(client, world, "aq09other"))
    assert client.post(url, json=body, headers=other).status_code == 404


def test_return_as_of_before_and_after(env: dict[str, Any], world: World) -> None:
    client = env["g1"]
    ctx = _returned_world(env, world, "925")
    h = ctx["h"]
    _ok(
        client.post(
            f"{D}/{ctx['run']}/bank-status",
            json={
                "status": "returned",
                "order_ids": [ctx["order"]],
                "reason_code": "AC04",
                "returned_on": RETURNED_ON,
            },
            headers=h,
        )
    )
    _ok(
        client.post(
            f"{A}/ledgers/{ctx['ledger']}/entries/{ctx['entry']}/reverse",
            json={"reason": "Rücklastschrift AC04", "booking_date": RETURNED_ON},
            headers=h,
        ),
        201,
    )
    # Fixed expectations: before collection, between collection and return, from the return.
    assert _remaining(client, h, ctx, "2026-03-04") == DEBIT
    assert _remaining(client, h, ctx, "2026-03-10") == "0.00"
    assert _remaining(client, h, ctx, "2026-03-11") == "0.00"
    assert _remaining(client, h, ctx, RETURNED_ON) == DEBIT
    assert _remaining(client, h, ctx, "2026-03-31") == DEBIT
