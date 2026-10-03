"""AN16 (wave 24) with precomputed results: debtor credits in the liquidity preview (GAK-102),
bulk confirmation bound to a preview token with sums per legal entity (GAK-105), counter
account of overpayment remainder and discount (GAK-107), bank reconciliation by bank date and
unique ledger account (GAK-108).

Set (legal entity WEG, bank account 001210, one debtor):
  receivable R1 250.00 (01.01.2026), receivable R2 102.00 (02.01.2026)
  T1 300.00 on 05.01.2026 settles R1, remainder 50.00 stays credit on the debtor
  T2 100.00 on 06.01.2026 settles R2 with discount 2.00 to revenue 060100 (reason given)
  T3 200.00 on 07.01.2026 bulk booked against revenue 060100
Expected at 31.01.2026: bank 600.00, debtor balance 250 + 102 - 300 - 102 = -50.00, so
debtor_credits 50.00 and projected_free_funds 600.00 - 0.00 - 50.00 = 550.00. Moving the bank
day of T3 to 02.02.2026: ledger by bank date 400.00, difference 600 - 400 = 200.00, timing
difference 400 - 600 = -200.00."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine, text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
A = "/api/v1/accounting"
BANK = "DE91100000000123456789"
PAYER = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"an16-{RUN}", name=f"AN16 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("an16admin"), display_name="an16admin", password=PASSWORD
        )
        world.users["an16admin"] = uid
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _code(response: Any, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code, response.text


def test_an16_accounting_checks(client: TestClient, world: World, database: Database) -> None:
    h = bearer(login(client, world, "an16admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": f"{(int(RUN, 16) % 800) + 100:03d}",
                "name": "AN16 Haus",
                "management_type": "hoa",
            },
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
                "iban": BANK,
                "holder": "GdWE AN16",
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
                "first_name": "Ida",
                "last_name": f"N{RUN}",
                "bank_accounts": [{"iban": PAYER, "valid_from": "2020-01-01"}],
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
    unit = _unit(client, h, prop["id"], "01")
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
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
    accounts = {
        a["number"]: a for a in _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    }
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
    debtor = next(a["id"] for a in accounts.values() if a.get("unit_id") == unit)
    revenue = accounts["060100"]["id"]
    for day, amount in (("2026-01-01", "250.00"), ("2026-01-02", "102.00")):
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "receivable",
                    "booking_date": day,
                    "due_date": day,
                    "text": "Hausgeld",
                    "contract_id": contract["id"],
                    "lines": [
                        {"account_id": debtor, "debit": amount},
                        {"account_id": revenue, "credit": amount},
                    ],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    items = {
        i["amount"]: i["id"]
        for i in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h
            )
        )
    }
    statement = _camt(
        f"AN16-{RUN}",
        BANK,
        "0.00",
        "600.00",
        [
            _ntry(f"A1{RUN}", "300.00", "CRDT", "2026-01-05", PAYER, "Hausgeld"),
            _ntry(f"A2{RUN}", "100.00", "CRDT", "2026-01-06", PAYER, "Hausgeld Skonto"),
            _ntry(f"A3{RUN}", "200.00", "CRDT", "2026-01-07", PAYER, "Sonstiges"),
        ],
    )
    _ok(
        client.post(
            f"{B}/imports",
            json={"document_id": _upload(client, h, "an16.xml", statement)},
            headers=h,
        ),
        201,
    )
    txs = {t["bank_reference"]: t["id"] for t in _ok(client.get(f"{B}/transactions", headers=h))}
    t1, t2, t3 = txs[f"A1{RUN}"], txs[f"A2{RUN}"], txs[f"A3{RUN}"]

    # GAK-107: an overpayment remainder never goes to income.
    r1 = {"open_item_id": items["250.00"], "amount": "250.00"}
    _code(
        client.post(
            f"{B}/transactions/{t1}/book",
            json={"settlements": [r1], "counter_account_id": revenue},
            headers=h,
        ),
        422,
        "MHVP-BANK-0033",
    )
    _ok(client.post(f"{B}/transactions/{t1}/book", json={"settlements": [r1]}, headers=h), 201)
    # Discount: not to a personal account; to revenue only with a reason (no invoice terms).
    r2 = {"open_item_id": items["102.00"], "amount": "102.00"}
    disc = {"settlements": [r2], "discount": "2.00"}
    _code(
        client.post(
            f"{B}/transactions/{t2}/book", json={**disc, "counter_account_id": debtor}, headers=h
        ),
        422,
        "MHVP-BANK-0033",
    )
    _code(
        client.post(
            f"{B}/transactions/{t2}/book", json={**disc, "counter_account_id": revenue}, headers=h
        ),
        422,
        "MHVP-BANK-0033",
    )
    _ok(
        client.post(
            f"{B}/transactions/{t2}/book",
            json={**disc, "counter_account_id": revenue, "text": "Skonto 2,00 EUR laut Absprache"},
            headers=h,
        ),
        201,
    )

    # GAK-105: preview with sums per legal entity, booking only with the matching token.
    item3 = {"transaction_id": t3, "counter_account_id": revenue}
    preview = _ok(
        client.post(
            f"{B}/bulk-confirm",
            json={"preview": True, "items": [item3, {"transaction_id": t1}]},
            headers=h,
        )
    )
    assert preview["exceptions"] == [t1]
    assert preview["bookable_count"] == 1
    assert preview["bookable_transaction_ids"] == [t3]
    assert preview["totals_by_legal_entity"] == [
        {"legal_entity_id": hoa, "count": 2, "incoming": "500.00", "outgoing": "0.00"}
    ]
    token = preview["preview_id"]
    _code(
        client.post(f"{B}/bulk-confirm", json={"preview": False, "items": [item3]}, headers=h),
        409,
        "MHVP-BANK-0031",
    )
    _code(
        client.post(
            f"{B}/bulk-confirm",
            json={"preview": False, "items": [item3, {"transaction_id": t1}], "preview_id": token},
            headers=h,
        ),
        409,
        "MHVP-BANK-0032",
    )
    changed = {**item3, "text": "geändert"}
    _code(
        client.post(
            f"{B}/bulk-confirm",
            json={"preview": False, "items": [changed], "preview_id": token},
            headers=h,
        ),
        409,
        "MHVP-BANK-0031",
    )
    expired = "1." + token.partition(".")[2]
    _code(
        client.post(
            f"{B}/bulk-confirm",
            json={"preview": False, "items": [item3], "preview_id": expired},
            headers=h,
        ),
        409,
        "MHVP-BANK-0031",
    )
    done = _ok(
        client.post(
            f"{B}/bulk-confirm",
            json={"preview": False, "items": [item3], "preview_id": token},
            headers=h,
        )
    )
    assert [r["ok"] for r in done["results"]] == [True]
    assert done["totals_by_legal_entity"][0]["incoming"] == "200.00"

    # GAK-102: the overpayment is bound, not free.
    liq = _ok(
        client.get(f"{A}/ledgers/{ledger}/liquidity", params={"as_of": "2026-01-31"}, headers=h)
    )
    assert Decimal(liq["free_funds"]) == Decimal("600.00")
    assert Decimal(liq["expected_inflows"]) == Decimal("0.00")
    assert Decimal(liq["debtor_credits"]) == Decimal("50.00")
    assert Decimal(liq["projected_free_funds"]) == Decimal("550.00")
    report = _ok(
        client.get(
            f"{A}/ledgers/{ledger}/reports/liquidity", params={"as_of": "2026-01-31"}, headers=h
        )
    )
    assert Decimal(report["debtor_credits"]) == Decimal("50.00")
    before = _ok(
        client.get(f"{A}/ledgers/{ledger}/liquidity", params={"as_of": "2026-01-04"}, headers=h)
    )
    assert Decimal(before["debtor_credits"]) == Decimal("0.00")

    # GAK-108: booking date basis (default) and bank date basis.
    recon = f"{B}/accounts/{bank_id}/reconciliation"
    row = _ok(client.get(recon, headers=h))[0]
    assert row["date_basis"] == "booking_date"
    assert row["ledger_status"] == "linked"
    assert Decimal(row["ledger_balance"]) == Decimal("600.00")
    assert Decimal(row["ledger_difference"]) == Decimal("0.00")
    assert Decimal(row["timing_difference"]) == Decimal("0.00")
    engine = create_engine(database.migrator_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.tenant_a)}
            )
            # AP05 / GAL-104: the booking date is frozen by bank_transaction_guard (0462); the
            # test shifts it only to simulate a later bank date.
            conn.execute(
                text("ALTER TABLE bank_transaction DISABLE TRIGGER bank_transaction_guard")
            )
            conn.execute(
                text("UPDATE bank_transaction SET booking_date = '2026-02-02' WHERE id = :id"),
                {"id": t3},
            )
            conn.execute(text("ALTER TABLE bank_transaction ENABLE TRIGGER bank_transaction_guard"))
    finally:
        engine.dispose()
    by_bank = _ok(client.get(recon, params={"basis": "bank_date"}, headers=h))[0]
    assert Decimal(by_bank["ledger_balance"]) == Decimal("400.00")
    assert Decimal(by_bank["ledger_difference"]) == Decimal("200.00")
    assert Decimal(by_bank["timing_difference"]) == Decimal("-200.00")
    by_booking = _ok(client.get(recon, headers=h))[0]
    assert Decimal(by_booking["ledger_difference"]) == Decimal("0.00")
    assert Decimal(by_booking["timing_difference"]) == Decimal("-200.00")
    assert client.get(recon, params={"basis": "value"}, headers=h).status_code == 422

    # A second ledger account on the same bank account: no silent choice.
    second = client.post(
        f"{A}/ledgers/{ledger}/accounts",
        json={
            "number": "001211",
            "name": "WEG-Bank 2",
            "category": "bank",
            "type": "asset",
            "property_bank_account_id": bank_id,
        },
        headers=h,
    )
    if second.status_code == 201:
        _code(client.get(recon, headers=h), 409, "MHVP-BANK-0034")
        checks = _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))
        assert any("nicht eindeutig" in f for f in checks["bank_findings"]), checks
    else:
        # The account API already refuses a second link; the guard stays as defence in depth.
        assert second.status_code in (409, 422), second.text
