"""M13: receivable run with preview, posting once per contract, component and month (B08),
changed basis invalidates the preview, proration and non monthly intervals stay manual (7.5),
reversal, management fee draft. Expected values: 2 contracts x 300,00 hoa_fee + 50,00 reserve
= 700,00 posted; a contract starting on 15.03. is manual, not prorated."""

import asyncio
import time
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rc-{RUN}", name=f"Soll {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("m13admin"), display_name="m13", password=PASSWORD
        )
        world.users["m13admin"] = uid
        await services.add_member(
            factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
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


def _contract(
    c: TestClient, h: dict[str, str], prop: str, unit_no: str, start: str
) -> dict[str, Any]:
    unit = _unit(c, h, prop, unit_no)
    party, _ = _party(c, h, f"E{unit_no}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": start,
                "title_transfer_date": start,
                "acquisition_kind": "first_acquisition",
            },
            headers=h,
        ),
        201,
    )
    for code, amount in [("hoa_fee", "300.00"), ("reserve", "50.00")]:
        _ok(
            c.post(
                f"/api/v1/contracts/{contract['id']}/payments",
                json={
                    "payment_type_code": code,
                    "net": amount,
                    "gross": amount,
                    "valid_from": start,
                },
                headers=h,
            ),
            201,
        )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": start, "due_day": 3},
            headers=h,
        ),
        201,
    )
    return contract  # type: ignore[no-any-return]


def test_receivable_run(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m13admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "731", "name": "Sollhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    c1 = _contract(client, h, prop["id"], "01", "2020-01-01")
    _contract(client, h, prop["id"], "02", "2020-01-01")
    late = _contract(client, h, prop["id"], "03", "2026-03-15")
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

    blocked = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    assert (
        blocked["totals"]["blocked"]["count"] == 4
    )  # no revenue account mapped yet; contract 03 is manual
    assert (
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "hoa_fee", "account_id": acc["001200"]},
            headers=h,
        ).status_code
        == 422
    )
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    assert (
        client.post(f"{A}/receivable-runs/{blocked['id']}/post", headers=h).status_code == 409
    )  # stale preview

    started = time.monotonic()
    run = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    assert time.monotonic() - started < 120
    assert run["totals"]["ready"] == {"count": 4, "amount": "700.00"}
    manual = [i for i in run["items"] if i["status"] == "manual"]
    assert {i["contract_id"] for i in manual} == {late["id"]}
    assert "zeitanteilige" in manual[0]["message"]
    assert {i["due_date"] for i in run["items"] if i["status"] == "ready"} == {"2026-03-03"}

    posted = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    assert posted["status"] == "posted"
    again = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    assert again["items"] == posted["items"]  # repeated click: no second effect
    second = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-03-01"}, headers=h), 201
    )
    assert "ready" not in second["totals"]  # already posted for March
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )
    assert sum(Decimal(i["remaining"]) for i in items) == Decimal("700.00")
    assert {i["contract_id"] for i in items} == {
        c1["id"],
        posted["items"][2]["contract_id"],
    } or len(items) == 4

    # Reversal of the run reopens the period for a new run.
    rev = _ok(
        client.post(
            f"{A}/receivable-runs/{run['id']}/reverse",
            json={"reason": "Beschluss geändert", "booking_date": "2026-03-20"},
            headers=h,
        )
    )
    assert rev == {"reversed": 4, "status": "reversed"}
    assert (
        _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h
            )
        )
        == []
    )
    rerun = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "contract", "scope_id": c1["id"]},
            headers=h,
        ),
        201,
    )
    assert rerun["totals"]["ready"]["count"] == 2
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True

    # Management fee: 3 apartments x 25,00 = 75,00, minimum 100,00 applies; 19 % -> 19,00.
    fee = _ok(
        client.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-01-01",
                "vat_percent": "19",
                "min_amount": "100.00",
                "amounts_per_unit_type": {"apartment": "25.00"},
            },
            headers=h,
        ),
        201,
    )
    preview = _ok(client.get(f"{A}/admin-fees/{fee['id']}/invoice-preview", headers=h))
    assert preview["lines"][0]["amount"] == "75.00"
    assert preview["net"] == "100.00"
    assert preview["vat"] == "19.00"
    assert preview["gross"] == "119.00"
    assert preview["status"] == "draft"

    # M13-04: issuing an invoice number is blocked without a configured prefix, and blocked for
    # XRechnung until the VAT status (and, for regelbesteuert, tax data) is entered.
    assert client.post(f"{A}/admin-fees/{fee['id']}/invoice-issue", headers=h).status_code == 409
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={"invoice_prefix": "HVM"},
            headers=h,
        )
    )
    assert client.post(f"{A}/admin-fees/{fee['id']}/invoice-issue", headers=h).status_code == 409
    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={"vat_status": "regelbesteuert", "vat_id": "DE123456789"},
            headers=h,
        )
    )
    issued = _ok(client.post(f"{A}/admin-fees/{fee['id']}/invoice-issue", headers=h), 200)
    assert issued["number"] == f"HVM-{issued['invoice_date'][:4]}-000001"
    issued_2 = _ok(client.post(f"{A}/admin-fees/{fee['id']}/invoice-issue", headers=h), 200)
    assert issued_2["number"] == f"HVM-{issued['invoice_date'][:4]}-000002"

    billing = _ok(client.get("/api/v1/tenant/billing-settings", headers=h))
    assert billing["vat_id_masked"] == "…6789"


def _d48_world(client: TestClient, h: dict[str, str], number: str) -> tuple[str, str, str]:
    """Property with two full month contracts (2 x 350,00), ledger and revenue mapping.
    Returns property id, ledger id and the hoa_fee revenue account id."""
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Sollhaus {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    _contract(client, h, prop["id"], "01", "2020-01-01")
    _contract(client, h, prop["id"], "02", "2020-01-01")
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
    for code, account in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[account]},
                headers=h,
            )
        )
    return prop["id"], ledger, acc["060100"]


def _open_total(client: TestClient, h: dict[str, str], ledger: str, as_of: str) -> Decimal:
    items = _ok(client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": as_of}, headers=h))
    return sum((Decimal(i["remaining"]) for i in items), Decimal("0.00"))


def test_d48_receivable_run_concurrency_retry_and_idempotency(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """D48 (18 M10 Abnahme, B08): a concurrent run for the same period, a retry after an
    aborted run and a double API call with the same idempotency key each produce exactly one
    economic effect. Expected values: 2 contracts x (300,00 + 50,00) = 700,00 per month; after
    all three scenarios the open items are 700,00 for March, 700,00 for April and one draft of
    12,34 with the key ``d48-key``."""
    from concurrent.futures import ThreadPoolExecutor

    from mhvp.accounting import receivables
    from mhvp.accounting import services as acc_services
    from mhvp.accounting.models import ReceivableRun
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    h = bearer(login(client, world, "m13admin"))
    prop, ledger, revenue = _d48_world(client, h, "732")
    settings = _settings(database, redis_url)
    march = {"period_month": "2026-03-01", "scope": "property", "scope_id": prop}
    april_in = {"period_month": "2026-04-01", "scope": "property", "scope_id": prop}

    # Scenario 1: two previews for March, posted at the same time from two sessions. The second
    # one waits for the advisory lock, recomputes against the posted items and gets 409; no
    # half posted run, no double open items.
    runs = [
        _ok(client.post(f"{A}/receivable-runs", json=march, headers=h), 201)["id"] for _ in range(2)
    ]

    def post_in_own_client(run_id: str) -> tuple[int, Any]:
        with TestClient(create_app(settings)) as own:
            response = own.post(f"{A}/receivable-runs/{run_id}/post", headers=h)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(post_in_own_client, runs))
    assert sorted(code for code, _ in results) == [200, 409], results
    posted_body = next(body for code, body in results if code == 200)
    assert posted_body["status"] == "posted"
    assert _open_total(client, h, ledger, "2026-03-31") == Decimal("700.00")
    statuses = sorted(
        _ok(client.get(f"{A}/receivable-runs/{r}", headers=h))["status"] for r in runs
    )
    assert statuses == ["posted", "preview"]  # the loser stays an unposted preview

    # The same run posted twice at the same time: both calls answer with the identical result.
    winner = posted_body["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        twice = list(pool.map(post_in_own_client, [winner, winner]))
    assert [code for code, _ in twice] == [200, 200]
    assert twice[0][1]["items"] == twice[1][1]["items"]
    assert _open_total(client, h, ledger, "2026-03-31") == Decimal("700.00")

    # Scenario 2: April run aborts inside a savepoint after the first item (simulated posting
    # error), is rolled back and repeated in the same transaction: exactly one full effect.
    april = _ok(client.post(f"{A}/receivable-runs", json=april_in, headers=h), 201)
    assert april["totals"]["ready"] == {"count": 4, "amount": "700.00"}

    async def abort_then_retry() -> tuple[int, int]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        real_post = acc_services.post
        calls = {"n": 0, "fail_at": 2}

        async def counting_post(*args: Any, **kwargs: Any) -> Any:
            calls["n"] += 1
            if calls["n"] == calls["fail_at"]:
                raise RuntimeError("D48: simulated abort after the first item")
            return await real_post(*args, **kwargs)

        acc_services.post = counting_post
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                run = await session.get(ReceivableRun, uuid.UUID(april["id"]), with_for_update=True)
                assert run is not None
                try:
                    async with session.begin_nested():
                        await receivables.post_run(session, run, None)
                    raise AssertionError("abort expected")
                except RuntimeError:
                    pass
                aborted_calls = calls["n"]
                calls["fail_at"] = 0
                await session.refresh(run)
                assert run.status.value == "preview"
                await receivables.post_run(session, run, None)
                return aborted_calls, calls["n"]
        finally:
            acc_services.post = real_post
            await engine.dispose()

    aborted_calls, total_calls = asyncio.run(abort_then_retry())
    assert aborted_calls == 2  # one item posted, second aborted, both rolled back
    assert total_calls == 2 + 4
    april_after = _ok(client.get(f"{A}/receivable-runs/{april['id']}", headers=h))
    assert april_after["status"] == "posted"
    assert [i["status"] for i in april_after["items"]] == ["posted"] * 4
    assert len({i["journal_entry_id"] for i in april_after["items"]}) == 4
    assert _open_total(client, h, ledger, "2026-04-30") == Decimal("1400.00")
    open_april = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-04-30"}, headers=h)
    )
    assert len(open_april) == 8  # 4 per month, no duplicate from the aborted attempt
    assert client.post(f"{A}/receivable-runs/{april['id']}/post", headers=h).status_code == 200
    assert _open_total(client, h, ledger, "2026-04-30") == Decimal("1400.00")

    # Scenario 3: the same manual entry sent twice at the same time with one idempotency key
    # yields one draft; both callers get the same id (B08).
    debtor = next(
        a["id"]
        for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
        if a["category"] == "debtor" and a["number"] not in {"009000", "009999"}
    )
    body = {
        "kind": "receivable",
        "booking_date": "2026-05-02",
        "text": "D48 Doppelaufruf",
        "idempotency_key": "d48-key",
        "lines": [
            {"account_id": debtor, "debit": "12.34", "credit": "0"},
            {"account_id": revenue, "debit": "0", "credit": "12.34"},
        ],
    }

    def create_in_own_client(_: int) -> tuple[int, Any]:
        with TestClient(create_app(settings)) as own:
            response = own.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(pool.map(create_in_own_client, [1, 2]))
    assert [code for code, _ in created] == [201, 201], created
    assert created[0][1]["id"] == created[1][1]["id"]
    drafts = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/entries",
            params={"status": "draft", "start": "2026-05-01", "end": "2026-05-31"},
            headers=h,
        )
    )
    assert len(drafts) == 1
    assert (
        client.post(f"{A}/ledgers/{ledger}/entries", json=body, headers=h).json()["id"]
        == (created[0][1]["id"])
    )
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True


def test_d58_sev_admin_fee_debtor_and_payee(client: TestClient, world: World) -> None:
    """D58 (annex D, E13, 6.9.11): the management fee for an SEV owner distinguishes payer,
    invoice debtor and payee. Expected: the ownership contract with SEV carries the owner as
    ``sev_fee_debtor_party_id`` and the WEG as creditor of the Hausgeld; the tenancy in the
    same unit belongs to the SEV owner's own legal entity; the WEG fee draft (no debtor party)
    counts both apartments (2 x 25,00 = 50,00) and is a cost of the Gemeinschaft, while the SE
    fee draft with the owner as debtor counts only that owner's SEV unit (25,00), is a cost in
    the SEV owner's ledger and names the management tenant, never a party, as payee. An owner
    without SEV as debtor gets no fee (0,00), an unknown party is refused."""
    import uuid as _uuid

    h = bearer(login(client, world, "m13admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "733", "name": "SEV-Haus", "management_type": "hoa_with_sev"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit1 = _unit(client, h, prop["id"], "01")
    unit2 = _unit(client, h, prop["id"], "02")
    sev_owner, _ = _party(client, h, "SEVEig")
    weg_owner, _ = _party(client, h, "WEGEig")
    tenant, _ = _party(client, h, "SEVMieter")
    ownership = {
        "kind": "ownership",
        "start_date": "2020-01-01",
        "title_transfer_date": "2020-01-01",
        "acquisition_kind": "first_acquisition",
    }
    own1 = _ok(
        client.post(
            "/api/v1/contracts",
            json={**ownership, "unit_id": unit1, "party_id": sev_owner, "sev_enabled": True},
            headers=h,
        ),
        201,
    )
    assert own1["legal_entity_id"] == hoa  # Hausgeld creditor stays the GdWE
    assert own1["sev_fee_debtor_party_id"] == sev_owner  # the owner owes the SE fee
    own2 = _ok(
        client.post(
            "/api/v1/contracts",
            json={**ownership, "unit_id": unit2, "party_id": weg_owner},
            headers=h,
        ),
        201,
    )
    assert own2["sev_fee_debtor_party_id"] is None
    lease = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit1,
                "party_id": tenant,
                "start_date": "2024-01-01",
            },
            headers=h,
        ),
        201,
    )
    sev_entity = lease["legal_entity_id"]
    assert sev_entity != hoa  # the landlord is the SEV owner, not the GdWE

    fee_body = {
        "property_id": prop["id"],
        "start_date": "2026-01-01",
        "vat_percent": "0",
        "amounts_per_unit_type": {"apartment": "25.00"},
    }
    weg_fee = _ok(client.post(f"{A}/admin-fees", json=fee_body, headers=h), 201)
    weg = _ok(client.get(f"{A}/admin-fees/{weg_fee['id']}/invoice-preview", headers=h))
    assert weg["lines"] == [
        {"unit_type": "apartment", "count": 2, "rate": "25.00", "amount": "50.00"}
    ]
    assert weg["net"] == "50.00"
    assert weg["invoice_debtor_party_id"] is None
    assert weg["debtor_legal_entity_id"] == hoa
    assert weg["debtor_legal_entity_kind"] == "hoa"
    assert weg["payee_role"] == "manager"
    assert weg["payee_party_id"] is None
    assert weg["status"] == "draft"

    sev_fee = _ok(
        client.post(
            f"{A}/admin-fees", json={**fee_body, "invoice_debtor_party_id": sev_owner}, headers=h
        ),
        201,
    )
    sev = _ok(client.get(f"{A}/admin-fees/{sev_fee['id']}/invoice-preview", headers=h))
    assert sev["lines"] == [
        {"unit_type": "apartment", "count": 1, "rate": "25.00", "amount": "25.00"}
    ]
    assert sev["net"] == "25.00"
    assert sev["gross"] == "25.00"
    assert sev["invoice_debtor_party_id"] == sev_owner  # invoice debtor is the SEV owner
    assert sev["debtor_legal_entity_id"] == sev_entity  # cost in the SEV owner's ledger
    assert sev["debtor_legal_entity_kind"] == "sev_owner"
    assert sev["payee_role"] == "manager"  # the fee flows to the manager, never to a party
    assert sev["payee_party_id"] is None
    assert sev["status"] == "draft"

    # An owner without SEV owes no SE fee; a party that does not exist is refused.
    no_sev = _ok(
        client.post(
            f"{A}/admin-fees", json={**fee_body, "invoice_debtor_party_id": weg_owner}, headers=h
        ),
        201,
    )
    none = _ok(client.get(f"{A}/admin-fees/{no_sev['id']}/invoice-preview", headers=h))
    assert none["lines"] == []
    assert none["net"] == "0.00"
    assert none["debtor_legal_entity_id"] is None
    assert (
        client.post(
            f"{A}/admin-fees",
            json={**fee_body, "invoice_debtor_party_id": str(_uuid.uuid4())},
            headers=h,
        ).status_code
        == 404
    )


def test_d45_receivable_run_vat_option_without_tax_status_stays_manual(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """D45 (annex D, M13-03): a ledger with a VAT option but no maintained tax treatment
    posts no output VAT on receivables automatically. Expected: the component with 19 %
    (100,00 net, 119,00 gross) stays ``manual`` with the VAT reason, the component without
    VAT (50,00) is posted; after posting the open items are exactly 50,00, no tax account is
    touched and the manual item has no journal entry."""
    from tests.integration.test_m14_invoices import _set_vat_option

    h = bearer(login(client, world, "m13admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "734", "name": "Optionshaus Soll", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    unit = _unit(client, h, prop["id"], "01")
    party, _ = _party(client, h, "OptEig")
    contract = _ok(
        client.post(
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
    )
    for code, net, vat, gross in [
        ("hoa_fee", "100.00", "19", "119.00"),
        ("reserve", "50.00", "0", "50.00"),
    ]:
        _ok(
            client.post(
                f"/api/v1/contracts/{contract['id']}/payments",
                json={
                    "payment_type_code": code,
                    "net": net,
                    "vat_percent": vat,
                    "gross": gross,
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )
    _ok(
        client.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": "2020-01-01", "due_day": 3},
            headers=h,
        ),
        201,
    )
    template = _ok(client.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        client.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    asyncio.run(_set_vat_option(_settings(database, redis_url), world.tenant_a, ledger))
    assert _ok(client.get(f"{A}/ledgers/{ledger}", headers=h))["vat_mode"] == "option"
    acc = {
        a["number"]: a["id"] for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
    for code, number in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            client.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )

    run = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-06-01", "scope": "property", "scope_id": prop["id"]},
            headers=h,
        ),
        201,
    )
    by_code = {i["payment_type_code"]: i for i in run["items"]}
    assert by_code["hoa_fee"]["status"] == "manual"
    assert "Umsatzsteuer" in by_code["hoa_fee"]["message"]
    assert "nicht freigegeben" in by_code["hoa_fee"]["message"]
    assert by_code["reserve"]["status"] == "ready"
    assert run["totals"]["ready"] == {"count": 1, "amount": "50.00"}
    assert run["totals"]["manual"] == {"count": 1, "amount": "119.00"}

    posted = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    assert posted["status"] == "posted"
    after = {i["payment_type_code"]: i for i in posted["items"]}
    assert after["hoa_fee"]["status"] == "manual"
    assert after["hoa_fee"]["journal_entry_id"] is None  # never posted by assumption
    assert after["reserve"]["status"] == "posted"
    items = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-06-30"}, headers=h)
    )
    assert [i["remaining"] for i in items] == ["50.00"]
    tb = _ok(
        client.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-06-30"}, headers=h)
    )
    moved = {a["number"]: a["category"] for a in tb["accounts"] if Decimal(a["balance"]) != 0}
    assert "060100" not in moved  # no revenue with VAT posted
    assert "tax" not in set(moved.values())  # no tax account touched
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True


# A27 (M13-05): runtime of the receivable run with a synthetic portfolio ----------------------

LOAD_PROPERTIES = 67
LOAD_UNITS = 869
LOAD_LIMIT_SECONDS = 120.0


async def _load_world(settings: Any) -> World:
    """Own tenant with 67 HOA properties and 869 units, each with an ownership contract, two
    monthly components (hoa_fee 300,00, reserve 50,00), a schedule, a ledger from the default
    template and the revenue mapping. Built directly on the services and models, not via the
    API per unit, so that the preparation stays fast; contract and debtor numbers are assigned
    sequentially, the number sequences of this isolated tenant are not consumed."""
    from datetime import date

    from sqlalchemy import select

    from mhvp.accounting import services as acc
    from mhvp.accounting.models import LedgerAccount, PaymentTypeAccount
    from mhvp.contacts.models import Contact, ContactKind, Party, PartyMember, PartyRole
    from mhvp.contracts.models import (
        AcquisitionKind,
        Contract,
        ContractKind,
        ContractPayment,
        DebtorAccountReservation,
        DueDayRule,
        PaymentInterval,
        PaymentReason,
        PaymentSchedule,
    )
    from mhvp.contracts.services import DEBTOR_START
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.ids import uuid7
    from mhvp.properties import services as prop_svc
    from mhvp.properties.models import (
        Building,
        LegalEntity,
        ManagementType,
        Property,
        Unit,
        UnitType,
    )

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant, _ = await services.provision_tenant(
            factory, slug=f"rl-{RUN}", name=f"Soll Last {RUN}"
        )
        world = World(
            tenant_a=tenant, tenant_b=tenant, app_url=settings.database_url.get_secret_value()
        )
        uid = await services.create_user(
            factory, email=world.email("m13load"), display_name="m13load", password=PASSWORD
        )
        world.users["m13load"] = uid
        await services.add_member(
            factory, tenant_id=tenant, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        start = date(2020, 1, 1)
        base, extra = divmod(LOAD_UNITS, LOAD_PROPERTIES)
        async with tenant_transaction(factory, tenant) as session:
            template = await acc.default_template(session, tenant)
            serial = 0
            for p in range(LOAD_PROPERTIES):
                prop = Property(
                    id=uuid7(),
                    tenant_id=tenant,
                    number=f"{p + 1:03d}",
                    name=f"Lastobjekt {p + 1}",
                    management_type=ManagementType.HOA,
                )
                session.add(prop)
                await prop_svc.ensure_hoa_entity(session, prop)
                hoa = await session.scalar(
                    select(LegalEntity.id).where(LegalEntity.property_id == prop.id)
                )
                assert hoa is not None
                building = Building(id=uuid7(), tenant_id=tenant, property_id=prop.id, name="Haus")
                session.add(building)
                contracts: list[Contract] = []
                debtors: list[DebtorAccountReservation] = []
                for u in range(base + (1 if p < extra else 0)):
                    serial += 1
                    unit = Unit(
                        id=uuid7(),
                        tenant_id=tenant,
                        property_id=prop.id,
                        building_id=building.id,
                        number=f"{u + 1:02d}",
                        label=f"WE {u + 1:02d}",
                        unit_type=UnitType.APARTMENT,
                    )
                    contact = Contact(
                        id=uuid7(),
                        tenant_id=tenant,
                        kind=ContactKind.PERSON,
                        first_name="Eigentum",
                        last_name=f"Last {serial}",
                        display_name=f"Eigentum Last {serial}",
                    )
                    party = Party(id=uuid7(), tenant_id=tenant, name=contact.display_name)
                    member = PartyMember(
                        tenant_id=tenant,
                        party_id=party.id,
                        contact_id=contact.id,
                        role=PartyRole.PRIMARY,
                    )
                    debtor = DebtorAccountReservation(
                        id=uuid7(),
                        tenant_id=tenant,
                        legal_entity_id=hoa,
                        party_id=party.id,
                        unit_id=unit.id,
                        number=f"{DEBTOR_START + u:06d}",
                        name=f"{unit.label} {party.name}",
                    )
                    contract = Contract(
                        id=uuid7(),
                        tenant_id=tenant,
                        kind=ContractKind.OWNERSHIP,
                        property_id=prop.id,
                        unit_id=unit.id,
                        party_id=party.id,
                        legal_entity_id=hoa,
                        debtor_account_id=debtor.id,
                        number=f"L{serial:05d}",
                        start_date=start,
                        title_transfer_date=start,
                        acquisition_kind=AcquisitionKind.FIRST_ACQUISITION,
                    )
                    # No ORM relationships: master data first, then the contracts (FK order).
                    session.add_all([unit, contact, party, member])
                    debtors.append(debtor)
                    contracts.append(contract)
                for batch in (debtors, contracts):
                    await session.flush()
                    session.add_all(batch)
                await session.flush()
                for contract in contracts:
                    for code, amount in (("hoa_fee", "300.00"), ("reserve", "50.00")):
                        session.add(
                            ContractPayment(
                                tenant_id=tenant,
                                contract_id=contract.id,
                                payment_type_code=code,
                                net=Decimal(amount),
                                gross=Decimal(amount),
                                valid_from=start,
                                reason=PaymentReason.INITIAL,
                            )
                        )
                    session.add(
                        PaymentSchedule(
                            tenant_id=tenant,
                            contract_id=contract.id,
                            interval=PaymentInterval.MONTHLY,
                            due_day_rule=DueDayRule.DAY,
                            due_day=3,
                            valid_from=start,
                        )
                    )
                await session.flush()
                ledger = await acc.create_ledger(
                    session,
                    tenant_id=tenant,
                    user_id=uid,
                    legal_entity_id=hoa,
                    template=template,
                    fiscal_year_start_month=1,
                    migration_cutoff=None,
                )
                for code, number in (("hoa_fee", "060100"), ("reserve", "060200")):
                    account = await session.scalar(
                        select(LedgerAccount.id).where(
                            LedgerAccount.ledger_id == ledger.id, LedgerAccount.number == number
                        )
                    )
                    assert account is not None
                    session.add(
                        PaymentTypeAccount(
                            tenant_id=tenant,
                            ledger_id=ledger.id,
                            payment_type_code=code,
                            account_id=account,
                        )
                    )
            await session.flush()
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def load_world(database: Database, redis_url: str) -> World:
    started = time.perf_counter()
    world = asyncio.run(_load_world(_settings(database, redis_url)))
    print(f"\nA27 Aufbau Bestand: {time.perf_counter() - started:.1f} s")  # noqa: T201
    return world


@pytest.mark.slow
def test_a27_receivable_run_runtime_67_properties_869_units(
    client: TestClient, load_world: World
) -> None:
    """Acceptance M13 (18): monthly run for all properties under two minutes. Measured on the
    API path (preview and posting as the operator would run it) once per property with
    scope=property for July 2026 and once for all properties with scope=all for August 2026.
    Both measurements are printed to the test log; the limit applies to each of them."""
    h = bearer(login(client, load_world, "m13load"))
    props = _ok(client.get("/api/v1/properties", params={"page_size": 100}, headers=h))
    ids = [p["id"] for p in props["items"]]
    assert len(ids) == LOAD_PROPERTIES

    preview_s = post_s = 0.0
    ready = posted = 0
    for prop_id in ids:
        t0 = time.perf_counter()
        run = _ok(
            client.post(
                f"{A}/receivable-runs",
                json={"period_month": "2026-07-01", "scope": "property", "scope_id": prop_id},
                headers=h,
            ),
            201,
        )
        preview_s += time.perf_counter() - t0
        ready += run["totals"]["ready"]["count"]
        assert run["totals"]["count"] == run["totals"]["ready"]["count"]  # nothing blocked
        t0 = time.perf_counter()
        done = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
        post_s += time.perf_counter() - t0
        assert done["status"] == "posted"
        posted += sum(1 for i in done["items"] if i["status"] == "posted")
    assert ready == posted == LOAD_UNITS * 2
    print(  # noqa: T201 - measurement belongs in the test log (run with -s)
        f"\nA27 scope=property, 67 Läufe Juli 2026: Vorschau {preview_s:.1f} s, "
        f"Buchung {post_s:.1f} s, gesamt {preview_s + post_s:.1f} s, {posted} Positionen"
    )
    assert preview_s + post_s < LOAD_LIMIT_SECONDS

    t0 = time.perf_counter()
    run_all = _ok(
        client.post(f"{A}/receivable-runs", json={"period_month": "2026-08-01"}, headers=h), 201
    )
    all_preview_s = time.perf_counter() - t0
    assert run_all["totals"]["ready"]["count"] == LOAD_UNITS * 2
    t0 = time.perf_counter()
    done_all = _ok(client.post(f"{A}/receivable-runs/{run_all['id']}/post", headers=h))
    all_post_s = time.perf_counter() - t0
    assert done_all["status"] == "posted"
    assert sum(1 for i in done_all["items"] if i["status"] == "posted") == LOAD_UNITS * 2
    print(  # noqa: T201
        f"\nA27 scope=all, ein Lauf August 2026: Vorschau {all_preview_s:.1f} s, "
        f"Buchung {all_post_s:.1f} s, gesamt {all_preview_s + all_post_s:.1f} s"
    )
    assert all_preview_s + all_post_s < LOAD_LIMIT_SECONDS
