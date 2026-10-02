"""AH05 (wave 19): GAG-08 (GAE-11) and GAG-15 (GAF-16).

Expected values by hand (independent of the code):

* GAG-08, year 2026, units 01 and 02 (MEA 1.000 each), reserve advance 200,00 per unit and
  month, unit 01 bound to reserve "Dach", unit 02 not bound. January 2026 posted. A CAMT.053
  statement of the community bank account (opening 0,00, closing 250,00) carries 200,00 from
  owner 01 and 50,00 from owner 02; both are booked through the bank posting
  (POST /banking/transactions/{id}/book) against the open items. Resolved plan 2026:
  reserves Dach 600,00 and Fassade 400,00.
  -> bank account 001210 balance 200,00 + 50,00 = 250,00; contributions_paid 250,00;
     contributions_paid_by_reserve {Dach: 200,00}; unassigned 250,00 - 200,00 = 50,00;
     Dach paid 200,00 (bound), open bound 600,00 - 200,00 = 400,00; open items 0,00 and
     150,00 (200,00 - 50,00), only the 150,00 remains.
* GAG-15: resolution with subject kind annual_statement, tally by heads 3 yes, 1 no. No
  stored rule, so the default rule (simple majority, heads) applies: 3 > 1 -> "erreicht".
  The new statement version naming that resolution returns the check; the resolution status
  stays "positive". GET /hoa/resolutions/{id}/majority-check: reader 200, caretaker without
  accounting:read 403, other tenant 404, unknown query parameter 422.
"""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import Engine, text

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m8_import import _settings as base_settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload
from tests.integration.test_m24_hoa import A, H, _book_cost, _hoa_ledger, _ok, _owner

pytestmark = pytest.mark.integration

B = "/api/v1/banking"
BANK = "DE02370400440532055500"
PAYER = "DE93370400440532055511"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ah05a-{RUN}", name=f"AH05 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ah05b-{RUN}", name=f"AH05 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ah05admin", a, "tenant_admin"),
            ("ah05second", a, "tenant_admin"),
            ("ah05reader", a, "read_only"),
            ("ah05care", a, "caretaker"),
            ("ah05other", b, "tenant_admin"),
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
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(base_settings(database, redis_url))) as c:
            yield c


def _sql(engine: Engine, tenant: Any, statement: str, **params: Any) -> None:
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        conn.execute(text(statement), params)


def _resolved_plan(
    c: TestClient, h: dict[str, str], h2: dict[str, str], w: dict[str, Any], items: list[Any]
) -> None:
    plan = _ok(
        c.post(
            f"{H}/plans",
            json={"ledger_id": w["ledger"], "year": 2026, "valid_from": "2026-01-01"},
            headers=h,
        ),
        201,
    )
    for item in items:
        body = {"allocation_key_id": w["keys"]["MEA"], **item}
        _ok(c.post(f"{H}/plans/{plan['id']}/items", json=body, headers=h), 201)
    calc = _ok(c.post(f"{H}/plans/{plan['id']}/calculate", headers=h))
    _ok(
        c.post(
            f"{H}/plans/{plan['id']}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    resolution = _ok(
        c.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2025-12-10",
                "subject": "Wirtschaftsplan 2026",
                "wording": "Der Wirtschaftsplan 2026 wird beschlossen.",
                "status": "positive",
                "subject_type": "economic_plan",
                "subject_id": plan["id"],
                "snapshot_hash": calc["snapshot_hash"],
            },
            headers=h,
        ),
        201,
    )
    _ok(
        c.post(
            f"{H}/plans/{plan['id']}/transition",
            json={"target": "resolved", "resolution_id": resolution["id"]},
            headers=h,
        )
    )


def test_gag08_statement_with_reserve_payment_via_bank(
    client: TestClient, world: World, migrator_engine: Engine
) -> None:
    c = client
    h = bearer(login(c, world, "ah05admin"))
    h2 = bearer(login(c, world, "ah05second"))
    w = _hoa_ledger(c, h, "985")
    mea, ledger, acc = w["keys"]["MEA"], w["ledger"], w["acc"]
    _, c1 = _owner(c, h, w["property"], "01", "1000", mea, {"reserve": "200.00"})
    _, c2 = _owner(c, h, w["property"], "02", "1000", mea, {"reserve": "200.00"})
    bank = _ok(
        c.post(
            f"/api/v1/properties/{w['property']}/bank-accounts",
            json={
                "legal_entity_id": w["hoa"],
                "kind": "hoa",
                "iban": BANK,
                "holder": "GdWE 985",
                "valid_from": "2020-01-01",
            },
            headers=h,
        ),
        201,
    )["id"]
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
    _ok(
        c.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "reserve", "account_id": acc["060200"]},
            headers=h,
        )
    )
    dach = _ok(c.post(f"{H}/reserves", json={"ledger_id": ledger, "name": "Dach"}, headers=h), 201)
    fassade = _ok(
        c.post(f"{H}/reserves", json={"ledger_id": ledger, "name": "Fassade"}, headers=h), 201
    )
    _sql(  # Zweckbindung only for unit 01
        migrator_engine,
        world.tenant_a,
        "UPDATE contract_payment SET reserve_id = :r "
        "WHERE contract_id = :c AND payment_type_code = 'reserve'",
        r=dach["id"],
        c=c1["id"],
    )
    for contract in (c1, c2):
        run = _ok(
            c.post(
                f"{A}/receivable-runs",
                json={
                    "period_month": "2026-01-01",
                    "scope": "contract",
                    "scope_id": contract["id"],
                },
                headers=h,
            ),
            201,
        )
        _ok(c.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    items = _ok(
        c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-01-31"}, headers=h)
    )
    by_contract = {i["contract_id"]: i for i in items if i["remaining"] == "200.00"}
    statement = _camt(
        f"AH05-{RUN}",
        BANK,
        "0.00",
        "250.00",
        [
            _ntry("R1", "200.00", "CRDT", "2026-01-05", PAYER, f"Ruecklage {c1['number']}"),
            _ntry("R2", "50.00", "CRDT", "2026-01-06", PAYER, f"Ruecklage {c2['number']}"),
        ],
    )
    _ok(
        c.post(f"{B}/imports", json={"document_id": _upload(c, h, "r.xml", statement)}, headers=h),
        201,
    )
    txs = {t["bank_reference"]: t for t in _ok(c.get(f"{B}/transactions", headers=h))}
    for ref, contract, pay in (("R1", c1, "200.00"), ("R2", c2, "50.00")):
        _ok(
            c.post(
                f"{B}/transactions/{txs[ref]['id']}/book",
                json={
                    "settlements": [
                        {"open_item_id": by_contract[contract["id"]]["id"], "amount": pay}
                    ]
                },
                headers=h,
            ),
            201,
        )
    _resolved_plan(
        c,
        h,
        h2,
        w,
        [
            {"label": "Dach", "component": "reserve", "amount": "600.00", "reserve_id": dach["id"]},
            {
                "label": "Fassade",
                "component": "reserve",
                "amount": "400.00",
                "reserve_id": fassade["id"],
            },
        ],
    )
    _book_cost(c, h, ledger, bank_account, acc["043000"], "1200.00", "2026-03-01")
    st = _ok(c.post(f"{H}/statements", json={"ledger_id": ledger, "year": 2026}, headers=h), 201)
    _ok(
        c.post(
            f"{H}/statements/{st['id']}/costs",
            json={
                "label": "Bewirtschaftung",
                "amount": "1200.00",
                "allocation_key_id": mea,
                "basis": "Teilungserklärung, MEA",
                "account_id": acc["043000"],
            },
            headers=h,
        ),
        201,
    )
    snap = _ok(c.post(f"{H}/statements/{st['id']}/calculate", headers=h))["snapshot"]
    reserve = snap["reserve"]
    assert reserve["contributions_paid"] == "250.00"
    assert reserve["contributions_paid_by_reserve"] == {dach["id"]: "200.00"}
    assert reserve["contributions_paid_unassigned"] == "50.00"
    pos = {p["name"]: p for p in reserve["positions"]}
    assert pos["Dach"]["contributions_paid"] == "200.00"
    assert pos["Dach"]["contributions_paid_bound"] is True
    assert pos["Fassade"]["contributions_paid_bound"] is False
    payments = _ok(
        c.get(f"{H}/ledgers/{ledger}/reserve-payments", params={"year": 2026}, headers=h)
    )
    rows = {r["name"]: r for r in payments["reserves"]}
    assert (rows["Dach"]["paid_bound"], rows["Dach"]["open_bound"]) == ("200.00", "400.00")
    assert payments["paid_unassigned"] == "50.00"
    remaining = [
        i["remaining"]
        for i in _ok(
            c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-12-31"}, headers=h)
        )
    ]
    assert remaining == ["150.00"]
    balances = {
        r["number"]: Decimal(r["balance"])
        for r in _ok(
            c.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": "2026-01-31"}, headers=h)
        )["accounts"]
    }
    assert balances["001210"] == Decimal("250.00")
    # Booked bank transactions cannot be booked twice (B08).
    again = c.post(f"{B}/transactions/{txs['R1']['id']}/book", json={"settlements": []}, headers=h)
    assert again.status_code == 409


def test_gag15_new_version_majority_check(client: TestClient, world: World) -> None:
    c = client
    h = bearer(login(c, world, "ah05admin"))
    w = _hoa_ledger(c, h, "986")
    resolution = _ok(
        c.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2026-05-10",
                "subject": "Korrektur Jahresabrechnung 2025",
                "wording": "Die korrigierte Jahresabrechnung 2025 wird beschlossen.",
                "status": "positive",
                "subject_kind": "annual_statement",
                "votes": {"principle": "head", "yes": "3", "no": "1"},
            },
            headers=h,
        ),
        201,
    )
    st = _ok(
        c.post(f"{H}/statements", json={"ledger_id": w["ledger"], "year": 2025}, headers=h), 201
    )
    nv = _ok(
        c.post(
            f"{H}/statements/{st['id']}/new-version",
            json={"resolution_id": resolution["id"]},
            headers=h,
        ),
        201,
    )
    assert nv["version"] == st["version"] + 1
    check = nv["correction_majority_check"]
    assert check["result"] == "erreicht"
    assert check["standard_rule"] is True
    plain = _ok(c.post(f"{H}/statements/{nv['id']}/new-version", headers=h), 201)
    assert plain["correction_majority_check"] is None

    url = f"{H}/resolutions/{resolution['id']}/majority-check"
    reader = bearer(login(c, world, "ah05reader"))
    out = _ok(c.get(url, headers=reader))
    assert out["current"]["result"] == "erreicht"
    assert out["stored"]["result"] == "erreicht"
    # No automatic status change by the check.
    listed = _ok(c.get(f"{H}/resolutions", params={"legal_entity_id": w["hoa"]}, headers=h))
    assert {r["id"]: r["status"] for r in listed}[resolution["id"]] == "positive"
    assert c.get(url, headers=bearer(login(c, world, "ah05care"))).status_code == 403
    other = bearer(login(c, world, "ah05other", world.tenant_b))
    assert c.get(url, headers=other).status_code == 404
    assert c.get(url, params={"x": "1"}, headers=h).status_code == 422
    # A resolution of another tenant cannot be named as correction basis (RLS, 404).
    ost = _hoa_ledger(c, other, "987")
    foreign = _ok(
        c.post(f"{H}/statements", json={"ledger_id": ost["ledger"], "year": 2025}, headers=other),
        201,
    )
    assert (
        c.post(
            f"{H}/statements/{foreign['id']}/new-version",
            json={"resolution_id": resolution["id"]},
            headers=other,
        ).status_code
        == 404
    )
