"""AO02 (wave 25, GAK-107, GAK-108): stored tenant switches of the bank reconciliation.

Set (legal entity WEG, bank account 001210, two units of one owner, two debtor accounts):
  receivable U1 100.00 and U2 100.00 (01.01.2026)
  T1 250.00 on 05.01.2026 settles both, remainder 50.00 spread over two debtors
Without the clearing account switch the remainder needs an explicit counter account (422,
previous behaviour). With ``banking.clearing_account_number`` = 009999 (Durchlaufposten WEG,
transit) the remainder of 50.00 is credited to 009999. Revenue 060100 is refused as clearing
account (422). The stored basis ``bank_date`` is used without the query parameter; the query
parameter still overrides it."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

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
S = f"{B}/reconciliation-settings"
BANK = "DE91100000000123456789"
PAYER = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ao02-{RUN}", name=f"AO02 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in (("ao02admin", "tenant_admin"), ("ao02reader", "read_only")):
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
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_ao02_reconciliation_settings(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ao02admin"))
    reader = bearer(login(client, world, "ao02reader"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={
                "number": f"{(int(RUN, 16) % 800) + 100:03d}",
                "name": "AO02 Haus",
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
                "holder": "GdWE AO02",
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
                "first_name": "Ola",
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
    units = [_unit(client, h, prop["id"], n) for n in ("01", "02")]
    contracts = [
        _ok(
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
        )["id"]
        for unit in units
    ]

    # Defaults and validation before any chart exists.
    assert _ok(client.get(S, headers=h))["clearing_account_number"] is None
    assert _ok(client.get(S, headers=h))["reconciliation_basis"] == "booking_date"
    assert client.get(S, params={"x": "1"}, headers=h).status_code == 422
    bad = {"clearing_account_number": "009999", "reconciliation_basis": "booking_date"}
    assert client.put(S, json=bad, headers=h).status_code == 422  # no chart yet
    assert client.put(S, json={"reconciliation_basis": "value"}, headers=h).status_code == 422
    assert client.put(S, json={"clearing_account_number": "99"}, headers=h).status_code == 422
    assert client.put(S, json=bad, headers=reader).status_code == 403
    assert client.get(S, headers=reader).status_code in (200, 403)

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
    revenue = accounts["060100"]["id"]
    for unit, contract in zip(units, contracts, strict=True):
        debtor = next(a["id"] for a in accounts.values() if a.get("unit_id") == unit)
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "receivable",
                    "booking_date": "2026-01-01",
                    "due_date": "2026-01-01",
                    "text": "Hausgeld",
                    "contract_id": contract,
                    "lines": [
                        {"account_id": debtor, "debit": "100.00"},
                        {"account_id": revenue, "credit": "100.00"},
                    ],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    items = [
        i["id"]
        for i in _ok(
            client.get(
                f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h
            )
        )
    ]
    assert len(items) == 2
    statement = _camt(
        f"AO02-{RUN}",
        BANK,
        "0.00",
        "250.00",
        [_ntry(f"O1{RUN}", "250.00", "CRDT", "2026-01-05", PAYER, "Hausgeld")],
    )
    _ok(
        client.post(
            f"{B}/imports",
            json={"document_id": _upload(client, h, "ao02.xml", statement)},
            headers=h,
        ),
        201,
    )
    t1 = next(
        t["id"]
        for t in _ok(client.get(f"{B}/transactions", headers=h))
        if t["bank_reference"] == f"O1{RUN}"
    )
    body = {"settlements": [{"open_item_id": i, "amount": "100.00"} for i in items]}

    # GAK-107: without the switch the remainder over two debtors needs a counter account.
    assert client.post(f"{B}/transactions/{t1}/book", json=body, headers=h).status_code == 422

    options = _ok(client.get(S, headers=h))["clearing_account_options"]
    numbers = {o["number"]: o["category"] for o in options}
    assert numbers["009999"] == "transit"
    assert "060100" not in numbers
    wrong = {"clearing_account_number": "060100", "reconciliation_basis": "booking_date"}
    assert client.put(S, json=wrong, headers=h).status_code == 422
    saved = _ok(
        client.put(
            S,
            json={"clearing_account_number": "009999", "reconciliation_basis": "bank_date"},
            headers=h,
        )
    )
    assert saved["clearing_account_number"] == "009999"
    assert saved["reconciliation_basis"] == "bank_date"

    booked = _ok(client.post(f"{B}/transactions/{t1}/book", json=body, headers=h), 201)
    entry_id = booked.get("journal_entry_id") or booked.get("id")
    entry = _ok(client.get(f"{A}/ledgers/{ledger}/entries/{entry_id}", headers=h))
    clearing = accounts["009999"]["id"]
    lines = [ln for ln in entry["lines"] if ln["account_id"] == clearing]
    assert [Decimal(ln["credit"]) for ln in lines] == [Decimal("50.00")]

    # GAK-108: stored basis without query parameter, explicit parameter overrides.
    recon = f"{B}/accounts/{bank_id}/reconciliation"
    assert _ok(client.get(recon, headers=h))[0]["date_basis"] == "bank_date"
    row = _ok(client.get(recon, params={"basis": "booking_date"}, headers=h))[0]
    assert row["date_basis"] == "booking_date"
    assert Decimal(row["ledger_balance"]) == Decimal("250.00")
    assert Decimal(row["timing_difference"]) == Decimal("0.00")

    # Reset to the defaults.
    unchanged = _ok(client.put(S, json={}, headers=h))
    assert unchanged["clearing_account_number"] == "009999"
    assert unchanged["reconciliation_basis"] == "bank_date"
    partial = _ok(client.put(S, json={"reconciliation_basis": None}, headers=h))
    assert partial["clearing_account_number"] == "009999"
    reset = _ok(client.put(S, json={"clearing_account_number": None}, headers=h))
    assert reset["clearing_account_number"] is None
    assert reset["reconciliation_basis"] == "booking_date"
    assert _ok(client.get(recon, headers=h))[0]["date_basis"] == "booking_date"
