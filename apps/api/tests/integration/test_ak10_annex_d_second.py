"""AK10 (GAI-612, rule 0.1.8): second independent tests for the annex D cases D26 to D49
that so far were named by a single test. Each test uses its own scenario and its own
predefined expected values (computation in the docstring), not the numbers of the first
test. Own test world with the prefix ``ak10-RUN``; only helper functions of other modules
are reused, never their worlds."""

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
from tests.integration.test_h03_consumption_info import _owner, _seed_metering, _tenancy
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m10_ledger import _book, _entry, _hoa_ledger, _line
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m13_receivables import _contract

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
B = "/api/v1/banking"


class _OpenG1:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ak10-{RUN}", name=f"AK10 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ak10b-{RUN}", name=f"AK10 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ak10admin", a, "tenant_admin"),
            ("ak10admin2", a, "tenant_admin"),
            ("ak10read", a, "read_only"),
            ("ak10acc", a, "accountant_no_banking"),
            ("ak10other", b, "tenant_admin"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


@pytest.fixture
def gated(database: Database, redis_url: str) -> Iterator[TestClient]:
    """Client whose release gate resolver opens G1 only (dunning approval needs it)."""
    settings = _settings(database, redis_url)
    with TestClient(create_app(settings, release_gate_resolver=_OpenG1())) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _stock(c: TestClient, h: dict[str, str], ledger: str, as_of: str) -> list[Decimal]:
    rows = _ok(c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": as_of}, headers=h))
    return sorted(Decimal(r["remaining"]) for r in rows)


@pytest.mark.annex_d("D49")
def test_ak10_historical_stock_two_items_partial_payments(client: TestClient, world: World) -> None:
    """D49 second test: two receivables, payments and a reversal after the cut off.

    Receivable R1 250,00 on 02.05.2026, R2 480,00 on 06.05.2026.
    Payment 250,00 on R1 on 12.05.2026 (before the cut off 31.05.), payment 180,00 on R2 on
    03.06.2026 (after the cut off), reversal of that payment on 08.06.2026.
    Stock as of 31.05.: R1 250 - 250 = 0 (not listed), R2 480,00 -> [480,00].
    As of 05.06.: R2 480 - 180 = 300,00 -> [300,00]. As of 30.06. after the reversal:
    300 + 180 = 480,00 -> [480,00]. As of 31.05. after all later events: still [480,00].
    As of 04.05.: only R1 open -> [250,00]."""
    h = bearer(login(client, world, "ak10admin"))
    ledger, acc, debtor = _hoa_ledger(client, h, "949")
    revenue, bank = acc["060100"], acc["001200"]
    r1 = _book(
        client,
        h,
        ledger,
        _entry(
            "receivable",
            "2026-05-02",
            [_line(debtor, "250.00"), _line(revenue, "0", "250.00")],
            due_date="2026-05-03",
        ),
    )
    _book(
        client,
        h,
        ledger,
        _entry(
            "receivable",
            "2026-05-06",
            [_line(debtor, "480.00"), _line(revenue, "0", "480.00")],
            due_date="2026-05-07",
        ),
    )
    rows = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-05-31"}, headers=h)
    )
    by_amount = {Decimal(r["remaining"]): r["id"] for r in rows}
    oi1, oi2 = by_amount[Decimal("250.00")], by_amount[Decimal("480.00")]
    assert r1["status"] == "posted"
    _book(
        client,
        h,
        ledger,
        _entry(
            "debtor_payment",
            "2026-05-12",
            [_line(bank, "250.00"), _line(debtor, "0", "250.00")],
            settlements=[{"open_item_id": oi1, "amount": "250.00"}],
        ),
    )
    assert _stock(client, h, ledger, "2026-05-31") == [Decimal("480.00")]
    late = _book(
        client,
        h,
        ledger,
        _entry(
            "debtor_payment",
            "2026-06-03",
            [_line(bank, "180.00"), _line(debtor, "0", "180.00")],
            settlements=[{"open_item_id": oi2, "amount": "180.00"}],
        ),
    )
    assert _stock(client, h, ledger, "2026-05-31") == [Decimal("480.00")]
    assert _stock(client, h, ledger, "2026-06-05") == [Decimal("300.00")]
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/entries/{late['id']}/reverse",
            json={"reason": "Rückbuchung", "booking_date": "2026-06-08"},
            headers=h,
        ),
        201,
    )
    assert _stock(client, h, ledger, "2026-05-31") == [Decimal("480.00")]
    assert _stock(client, h, ledger, "2026-06-05") == [Decimal("300.00")]
    assert _stock(client, h, ledger, "2026-06-30") == [Decimal("480.00")]
    assert _stock(client, h, ledger, "2026-05-04") == [Decimal("250.00")]
    other = bearer(login(client, world, "ak10other"))
    assert (
        client.get(
            f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-05-31"}, headers=other
        ).status_code
        == 404
    )


def _receivable_world(
    c: TestClient, h: dict[str, str], number: str, units: tuple[str, ...] = ("11", "12", "13")
) -> tuple[str, str, list[str]]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AK10 {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    contracts = [_contract(c, h, prop["id"], unit_no, "2021-01-01")["id"] for unit_no in units]
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    for code, account in [("hoa_fee", "060100"), ("reserve", "060200")]:
        _ok(
            c.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[account]},
                headers=h,
            )
        )
    return prop["id"], ledger, contracts


@pytest.mark.annex_d("D48")
def test_ak10_receivable_run_repeat_and_stale_preview(client: TestClient, world: World) -> None:
    """D48 second test, sequential: repeated post, stale second preview, fresh preview.

    Three contracts x (hoa_fee 300,00 + reserve 50,00) = 6 items, 3 x 350,00 = 1.050,00 for
    May 2026. Posting the run twice gives the same items; a preview created before the post
    is stale (409); a new preview after the post has no ready item (count 0). Open items as of
    31.05.: 6 rows, 1.050,00. June run: another 1.050,00, as of 30.06. 12 rows, 2.100,00."""
    h = bearer(login(client, world, "ak10admin"))
    prop, ledger, _ = _receivable_world(client, h, "948")
    may = {"period_month": "2026-05-01", "scope": "property", "scope_id": prop}
    first = _ok(client.post(f"{A}/receivable-runs", json=may, headers=h), 201)
    stale = _ok(client.post(f"{A}/receivable-runs", json=may, headers=h), 201)
    assert first["totals"]["ready"] == {"count": 6, "amount": "1050.00"}
    once = _ok(client.post(f"{A}/receivable-runs/{first['id']}/post", headers=h))
    twice = _ok(client.post(f"{A}/receivable-runs/{first['id']}/post", headers=h))
    assert once["status"] == twice["status"] == "posted"
    assert once["items"] == twice["items"]
    assert client.post(f"{A}/receivable-runs/{stale['id']}/post", headers=h).status_code == 409
    fresh = _ok(client.post(f"{A}/receivable-runs", json=may, headers=h), 201)
    assert "ready" not in fresh["totals"]
    rows = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-05-31"}, headers=h)
    )
    assert (len(rows), sum(Decimal(r["remaining"]) for r in rows)) == (6, Decimal("1050.00"))
    june = _ok(
        client.post(f"{A}/receivable-runs", json=may | {"period_month": "2026-06-01"}, headers=h),
        201,
    )
    _ok(client.post(f"{A}/receivable-runs/{june['id']}/post", headers=h))
    rows = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-06-30"}, headers=h)
    )
    assert (len(rows), sum(Decimal(r["remaining"]) for r in rows)) == (12, Decimal("2100.00"))


@pytest.mark.annex_d("D39")
def test_ak10_payment_determination_beats_oldest_first(client: TestClient, world: World) -> None:
    """D39 second test: three Hausgeld items January 100,00, February 120,00, March 140,00.

    Payment 140,00 "Hausgeld März 2026 <Vertrag>": the named March item is the first candidate
    with the reason "Bestimmung aus Verwendungszweck"; booked as determined, January 100,00
    and February 120,00 stay open (oldest first would have settled January). Payment 60,00
    "Hausgeld Februar 2026 <Vertrag>": February first, booked as partial payment.
    Expected open items as of 31.03.: January 100,00, February 120 - 60 = 60,00; sum 160,00."""
    h = bearer(login(client, world, "ak10admin"))
    bank, payer = "DE77100500000054540410", "DE13370400440532013010"
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "939", "name": "AK10 D39", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    bank_id = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/bank-accounts",
            json={
                "legal_entity_id": hoa,
                "kind": "hoa",
                "iban": bank,
                "holder": "GdWE AK10 D39",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={
                "kind": "person",
                "first_name": "Tilg",
                "last_name": f"AK10D39{RUN}",
                "bank_accounts": [{"iban": payer, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": _unit(client, h, prop["id"], "01"),
                "party_id": party["id"],
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
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
    acc = {a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "001210",
                "name": "WEG-Bank",
                "category": "bank",
                "type": "asset",
                "property_bank_account_id": bank_id,
            },
            headers=h,
        ),
        201,
    )
    debtor = next(a["id"] for a in acc.values() if a["category"] == "debtor")
    entries: dict[str, str] = {}
    for month, day, amount in [
        ("Januar", "01", "100.00"),
        ("Februar", "02", "120.00"),
        ("März", "03", "140.00"),
    ]:
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "receivable",
                    "booking_date": f"2026-{day}-01",
                    "due_date": f"2026-{day}-03",
                    "text": f"Hausgeld {month}",
                    "contract_id": contract["id"],
                    "lines": [
                        {"account_id": debtor, "debit": amount},
                        {"account_id": acc["060100"]["id"], "credit": amount},
                    ],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
        entries[month] = draft["id"]
    items = {
        i["journal_entry_id"]: i["id"]
        for i in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h
            )
        )
    }
    n = contract["number"]
    statement = _camt(
        "AK10D39",
        bank,
        "0.00",
        "200.00",
        [
            _ntry("AK10D39-1", "140.00", "CRDT", "2026-03-05", payer, f"Hausgeld März 2026 {n}"),
            _ntry("AK10D39-2", "60.00", "CRDT", "2026-03-06", payer, f"Hausgeld Februar 2026 {n}"),
        ],
    )
    _ok(
        client.post(
            f"{B}/imports",
            json={"document_id": _upload(client, h, "ak10-d39.xml", statement)},
            headers=h,
        ),
        201,
    )
    txs = {t["bank_reference"]: t["id"] for t in _ok(client.get(f"{B}/transactions", headers=h))}
    for ref, month, amount in [("AK10D39-1", "März", "140.00"), ("AK10D39-2", "Februar", "60.00")]:
        cand = _ok(client.get(f"{B}/transactions/{txs[ref]}/candidates", headers=h))
        first = cand["candidates"][0]
        assert first["open_item_id"] == items[entries[month]]
        assert first["allocation_reason"] == "Bestimmung aus Verwendungszweck"
        assert cand["unambiguous_open_item_id"] in (None, items[entries[month]])
        _ok(
            client.post(
                f"{B}/transactions/{txs[ref]}/book",
                json={"settlements": [{"open_item_id": items[entries[month]], "amount": amount}]},
                headers=h,
            ),
            201,
        )
    after = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )
    assert sorted((i["journal_entry_id"], i["remaining"]) for i in after) == sorted(
        [(entries["Januar"], "100.00"), (entries["Februar"], "60.00")]
    )
    assert sum(Decimal(i["remaining"]) for i in after) == Decimal("160.00")
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True


@pytest.mark.annex_d("D40")
def test_ak10_dunning_two_contracts_no_side_claim(gated: TestClient, world: World) -> None:
    """D40 second test: two contracts, April 2026 run, dunning run on 22.04.2026.

    Two contracts x (300,00 + 50,00) = 700,00 open. No fee amount and no Basiszinssatz are
    maintained: interest on with a spread but without base rate is refused (MHVP-CORE-0004),
    each proposed case shows fee 0,00, interest 0,00, total 350,00; approval by a second
    user books no fee entry and no invoice draft; open items stay one per payment type,
    2 x 50,00 + 2 x 300,00 = 700,00, all of kind receivable."""
    h = bearer(login(gated, world, "ak10admin"))
    acc_user = bearer(login(gated, world, "ak10acc"))
    prop, ledger, contracts = _receivable_world(gated, h, "940", units=("21", "22"))
    _ok(gated.post(f"{A}/ledgers/{ledger}/leading", json={"leading_system": "mhvp"}, headers=h))
    run = _ok(
        gated.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-04-01", "scope": "property", "scope_id": prop},
            headers=h,
        ),
        201,
    )
    _ok(gated.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    if _ok(gated.get(f"{A}/dunning-settings", headers=h))["status"] == "nicht eingerichtet":
        _ok(gated.post(f"{A}/dunning-settings/presets", json={}, headers=h), 201)
    preset = _ok(
        gated.post(f"{A}/dunning-settings/presets", json={"property_id": prop}, headers=h), 201
    )
    assert all(lv["fee_amount"] is None for lv in preset["levels"])
    refused = gated.put(
        f"{A}/dunning-settings",
        json={"property_id": prop, "interest_enabled": True, "interest_spread": "9"},
        headers=h,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "MHVP-CORE-0004"
    lead = _ok(gated.post(f"{A}/dunning-runs", json={"run_date": "2026-04-22"}, headers=h), 201)
    mine = [c for c in lead["cases"] if c["contract_id"] in contracts]
    assert sorted(c["contract_id"] for c in mine) == sorted(contracts)
    for case in mine:
        assert (case["fee_amount"], case["interest_amount"], case["total"]) == (
            "0.00",
            "0.00",
            "350.00",
        )
    approved = _ok(gated.post(f"{A}/dunning-runs/{lead['id']}/approve", headers=acc_user))
    assert all(
        c["fee_entry_id"] is None and c["fee_invoice_draft_id"] is None
        for c in approved["cases"]
        if c["contract_id"] in contracts
    )
    drafts = _ok(gated.get(f"{A}/ledgers/{ledger}/entries", params={"status": "draft"}, headers=h))
    assert [e for e in drafts if e["kind"] == "dunning_fee"] == []
    rows = _ok(
        gated.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-04-30"}, headers=h)
    )
    assert (
        sorted(Decimal(r["remaining"]) for r in rows)
        == [Decimal("50.00")] * 2 + [Decimal("300.00")] * 2
    )
    assert {r["kind"] for r in rows} == {"receivable"}


@pytest.mark.annex_d("D28")
def test_ak10_rule_version_cut_off_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    """D28 second test, selection by cut off date with two later published versions.

    Register: v1 since ever, v2 valid from 01.07.2027, v3 valid from 01.01.2029 (published
    now, effective later). Expected by period start: 01.01.2026 and 31.12.2026 -> v1,
    30.06.2027 -> v1 (one day before v2), 01.07.2027 -> v2, 31.12.2028 -> v2, 01.01.2029 -> v3.
    After the register is restored, every period, including 2029, falls back to v1."""
    from datetime import date

    from mhvp.billing import calc as billing_calc

    base = billing_calc.RULE_VERSIONS
    v1 = billing_calc.rule_version(date(2026, 1, 1))
    monkeypatch.setattr(
        billing_calc,
        "RULE_VERSIONS",
        (*base, (date(2027, 7, 1), "ak10-v2"), (date(2029, 1, 1), "ak10-v3")),
    )
    expected = {
        date(2026, 1, 1): v1,
        date(2026, 12, 31): v1,
        date(2027, 6, 30): v1,
        date(2027, 7, 1): "ak10-v2",
        date(2028, 12, 31): "ak10-v2",
        date(2029, 1, 1): "ak10-v3",
    }
    assert {d: billing_calc.rule_version(d) for d in expected} == expected
    monkeypatch.setattr(billing_calc, "RULE_VERSIONS", base)
    assert billing_calc.rule_version(date(2029, 1, 1)) == v1


@pytest.mark.annex_d("D26")
def test_ak10_consumption_info_hand_delivery_boundary(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    """D26 second test: substitute process with hand delivery on the first day of the month.

    One rental unit without portal account, consumption information for 08.2025 generated
    twice (repeat creates no second row): 1 month, 1 row, 1 undelivered. Channel "sms" and a
    delivery day 31.07.2025 (before the month) are refused (422), the read only user gets 403,
    the other tenant 404. Hand delivery on 01.08.2025 (first admissible day) with evidence is
    stored; afterwards 0 undelivered."""
    c = client
    h = bearer(login(c, world, "ak10admin"))
    pid = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": "926", "name": "AK10 D26", "management_type": "rental"},
            headers=h,
        ),
        201,
    )["id"]
    _owner(c, h, pid)
    building = _ok(
        c.post(f"/api/v1/properties/{pid}/buildings", json={"name": "Haus"}, headers=h), 201
    )["id"]
    unit = _ok(
        c.post(
            f"/api/v1/properties/{pid}/units",
            json={"building_id": building, "number": "01", "unit_type": "apartment"},
            headers=h,
        ),
        201,
    )["id"]
    party, _ = _party(c, h, "AK10OhnePortal")
    _tenancy(c, h, unit, party, "2024-03-01")
    asyncio.run(_seed_metering(_settings(database, redis_url), world.tenant_a, pid, unit))
    base = f"/api/v1/properties/{pid}/consumption-info"
    _ok(c.patch("/api/v1/tenant/settings", json={"consumption_info_enabled": True}, headers=h))
    _ok(c.put(f"{base}/settings", json={"enabled": True}, headers=h))
    _ok(c.post(f"{base}/run", json={"month": "2025-08-01"}, headers=h))
    _ok(c.post(f"{base}/run", json={"month": "2025-08-01"}, headers=h))
    listing = _ok(c.get(base, headers=h))
    assert [m["undelivered"] for m in listing["months"]] == [1]
    (row,) = listing["rows"]
    url = f"{base}/{row['id']}/delivery"
    delivery = {
        "channel": "hand_delivery",
        "delivered_on": "2025-08-01",
        "evidence": "Übergabe an Mieter, Quittung vom 01.08.2025",
    }
    assert c.put(url, json=delivery | {"channel": "sms"}, headers=h).status_code == 422
    assert c.put(url, json=delivery | {"delivered_on": "2025-07-31"}, headers=h).status_code == 422
    assert c.put(url, json=delivery, headers=bearer(login(c, world, "ak10read"))).status_code == 403
    assert (
        c.put(url, json=delivery, headers=bearer(login(c, world, "ak10other"))).status_code == 404
    )
    stored = _ok(c.put(url, json=delivery, headers=h))
    assert (stored["delivery_channel"], stored["delivered_on"]) == ("hand_delivery", "2025-08-01")
    assert [m["undelivered"] for m in _ok(c.get(base, headers=h))["months"]] == [0]
