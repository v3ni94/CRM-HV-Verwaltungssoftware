"""M12 acceptance with an independent synthetic set: unambiguous hit (contract number, payer
IBAN, full amount), IBAN plus amount only (manual), third party partial payment (manual),
ambiguous purpose with two contracts (manual). Automation only with tenant opt-in and an
active, approved rule with limit and test evidence; coverage and error rate reported apart."""

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
BANK = "DE02120300000000202051"
PAYERS = ["DE89370400440532013000", "DE75512108001245126199", "DE02500105170137075030"]
STRANGER = "DE12500105170648489890"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"mt-{RUN}", name=f"Match {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("m12admin", "tenant_admin"), ("m12acc", "accountant_no_banking")]:
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


def test_matching_set_and_controlled_automation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "m12admin"))
    acc_user = bearer(login(client, world, "m12acc"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "721", "name": "Matchhaus", "management_type": "hoa"},
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
                "holder": "GdWE Matchhaus",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
    contracts = []
    for i, iban in enumerate(PAYERS, start=1):
        contact = _ok(
            client.post(
                "/api/v1/contacts",
                json={
                    "kind": "person",
                    "first_name": f"Eig{i}",
                    "last_name": f"M{RUN}",
                    "bank_accounts": [{"iban": iban, "valid_from": "2020-01-01"}],
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
        unit = _unit(client, h, prop["id"], f"0{i}")
        contracts.append(
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
            )
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
    debtors = {a["unit_id"]: a["id"] for a in accounts.values() if a["category"] == "debtor"}
    for c, amount in zip(contracts, ["250.00", "250.00", "300.00"], strict=True):
        draft = _ok(
            client.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "receivable",
                    "booking_date": "2026-01-01",
                    "text": "Hausgeld Januar",
                    "contract_id": c["id"],
                    "lines": [
                        {"account_id": debtors[c["unit_id"]], "debit": amount},
                        {"account_id": accounts["060100"]["id"], "credit": amount},
                    ],
                },
                headers=h,
            ),
            201,
        )
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))

    n1, n2 = contracts[0]["number"], contracts[1]["number"]
    statement = _camt(
        "M-1",
        BANK,
        "0.00",
        "900.00",
        [
            _ntry("T1", "250.00", "CRDT", "2026-01-05", PAYERS[0], f"Hausgeld {n1}"),
            _ntry("T2", "250.00", "CRDT", "2026-01-05", PAYERS[1], "Hausgeld Januar"),
            _ntry(
                "T3",
                "100.00",
                "CRDT",
                "2026-01-06",
                STRANGER,
                f"Teilzahlung {contracts[2]['number']}",
            ),
            _ntry("T4", "300.00", "CRDT", "2026-01-07", STRANGER, f"{n1} und {n2}"),
        ],
    )
    _ok(
        client.post(
            f"{B}/imports", json={"document_id": _upload(client, h, "m.xml", statement)}, headers=h
        ),
        201,
    )
    txs = {t["bank_reference"]: t for t in _ok(client.get(f"{B}/transactions", headers=h))}

    def best(ref: str) -> Any:
        return _ok(client.get(f"{B}/transactions/{txs[ref]['id']}/candidates", headers=h))

    t1 = best("T1")
    assert t1["unambiguous_open_item_id"] is not None
    assert "Vertragsnummer im Verwendungszweck" in t1["candidates"][0]["reasons"]
    assert best("T2")["unambiguous_open_item_id"] is None  # IBAN and amount alone are no proof
    assert best("T2")["candidates"]
    assert best("T3")["unambiguous_open_item_id"] is None  # partial payment stays manual
    assert best("T4")["unambiguous_open_item_id"] is None  # ambiguous purpose

    # Automation is off by default: nothing is posted.
    assert _ok(client.post(f"{B}/auto-post", headers=h)) == {"enabled": False, "posted": 0}
    _ok(client.put(f"{B}/automation", json={"enabled": True, "reason": "Test M12"}, headers=h))
    assert _ok(client.post(f"{B}/auto-post", headers=h))["posted"] == 0  # no active rule

    rule = _ok(
        client.post(
            f"{B}/rules",
            json={"name": "Hausgeld", "legal_entity_id": hoa, "purpose_regex": "Hausgeld"},
            headers=h,
        ),
        201,
    )
    assert rule["approval_state"] == "proposed"
    assert client.post(f"{B}/rules/{rule['id']}/approve", headers=h).status_code == 403  # own rule
    evidence = _upload(client, h, "nachweis.xml", b"<nachweis>Testlauf M12</nachweis>")
    early = client.post(
        f"{B}/rules/{rule['id']}/activate",
        json={"max_amount": "500", "test_evidence_document_id": evidence},
        headers=acc_user,
    )
    assert early.status_code == 409
    _ok(client.post(f"{B}/rules/{rule['id']}/approve", headers=acc_user))
    _ok(
        client.post(
            f"{B}/rules/{rule['id']}/activate",
            json={"max_amount": "500", "test_evidence_document_id": evidence},
            headers=acc_user,
        )
    )
    auto = _ok(client.post(f"{B}/auto-post", headers=h))
    assert auto["posted"] == 1  # only T1
    booked = _ok(client.get(f"{B}/transactions", params={"status": "booked"}, headers=h))
    assert [t["bank_reference"] for t in booked] == ["T1"]
    assert _ok(client.post(f"{B}/auto-post", headers=h))["posted"] == 0  # no second effect

    # Manual confirmation: T3 partial with explicit settlement; T4 as overpayment credit.
    t3_item = best("T3")["candidates"][0]
    _ok(
        client.post(
            f"{B}/transactions/{txs['T3']['id']}/book",
            json={"settlements": [{"open_item_id": t3_item["open_item_id"], "amount": "100.00"}]},
            headers=h,
        ),
        201,
    )
    again = client.post(
        f"{B}/transactions/{txs['T3']['id']}/book", json={"settlements": []}, headers=h
    )
    assert again.status_code == 409
    preview = _ok(
        client.post(
            f"{B}/bulk-confirm",
            json={
                "items": [
                    {
                        "transaction_id": txs["T2"]["id"],
                        "settlements": [
                            {
                                "open_item_id": best("T2")["candidates"][0]["open_item_id"],
                                "amount": "250.00",
                            }
                        ],
                    },
                    {"transaction_id": txs["T1"]["id"]},
                ]
            },
            headers=h,
        )
    )
    assert preview["preview"] is True
    assert preview["count"] == 2
    assert preview["total"] == "500.00"
    assert txs["T1"]["id"] in preview["exceptions"]
    done = _ok(
        client.post(
            f"{B}/bulk-confirm",
            json={
                "preview": False,
                "items": [
                    {
                        "transaction_id": txs["T2"]["id"],
                        "settlements": [
                            {
                                "open_item_id": best("T2")["candidates"][0]["open_item_id"],
                                "amount": "250.00",
                            }
                        ],
                    },
                    {"transaction_id": txs["T1"]["id"]},
                ],
            },
            headers=h,
        )
    )
    assert [r["ok"] for r in done["results"]] == [
        True,
        False,
    ]  # T1 already booked: only that one fails

    open_after = _ok(
        client.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )
    assert [Decimal(i["remaining"]) for i in open_after] == [Decimal("200.00")]  # 300 - 100
    assert _ok(client.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True

    learned = _ok(client.post(f"{B}/transactions/{txs['T2']['id']}/learn", headers=h), 201)
    assert learned["approval_state"] == "proposed"
    assert client.post(f"{B}/transactions/{txs['T4']['id']}/learn", headers=h).status_code == 409

    m = _ok(client.get(f"{B}/matching/metrics", headers=h))
    assert m["incoming"] == 4
    assert m["auto_booked"] == 1
    assert m["coverage"] == 0.25
    assert m["error_rate"] == 0.0
    _ok(client.post(f"{B}/rules/{rule['id']}/disable", headers=h))
