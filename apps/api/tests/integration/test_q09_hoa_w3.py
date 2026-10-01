"""Package Q09 (Lückenliste 30.09.2026): M24-01 payments per reserve, M24-03 Gesamtabrechnung
on the letterhead, M24-04 comparison, P07-03 quarterly advances, M25-07 notification and owner
check. Expected values by hand (year 2025, units 01 and 02, MEA 1.000 each):

* reserve advance 200,00 EUR per unit and month, bound to "Dach" (unit 01) and "Fassade"
  (unit 02); January 2025 posted; unit 01 pays 200,00, unit 02 pays 50,00 -> paid per reserve
  200,00 and 50,00, total 250,00, nothing unassigned.
* plan 2027: Hausgeld 6.000,00 EUR and reserve 1.200,00 EUR per year, quarterly: monthly
  300,00 and 60,00 for unit 01 (600/1000), instalment 900,00 and 180,00.
"""

import asyncio
import io
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pypdf import PdfReader
from sqlalchemy import Engine, text

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m6_documents import COMPANY
from tests.integration.test_m8_import import BUCKET
from tests.integration.test_m8_import import _settings as s3_settings
from tests.integration.test_m24_hoa import (
    A,
    H,
    OpenG4,
    _book_cost,
    _hoa_ledger,
    _ok,
    _owner,
)

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q09-{RUN}", name=f"Q09 {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name in ("q09admin", "q09second"):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
            )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(base_settings(database, redis_url)))


@pytest.fixture
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = base_settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
    ):
        yield closed, open_


@pytest.fixture
def s3_clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    """Closed and G4 open client with object storage (letterhead logo, documents)."""
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        settings = s3_settings(database, redis_url)
        with (
            TestClient(create_app(settings)) as closed,
            TestClient(create_app(settings, release_gate_resolver=OpenG4())) as open_,
        ):
            yield closed, open_


def _sql(engine: Engine, tenant: Any, statement: str, **params: Any) -> Any:
    """Run SQL as the migrator with the tenant bound (the tables force row level security)."""
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        result = conn.execute(text(statement), params)
        return result.all() if result.returns_rows else None


def _pdf_text(content: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


def test_paid_per_reserve_and_gesamtabrechnung_pdf(
    s3_clients: tuple[TestClient, TestClient],
    world: World,
    migrator_engine: Engine,
) -> None:
    closed, open_ = s3_clients
    h = bearer(login(closed, world, "q09admin"))
    h2 = bearer(login(closed, world, "q09second"))
    w = _hoa_ledger(closed, h, "761")
    mea, ledger, acc = w["keys"]["MEA"], w["ledger"], w["acc"]
    _, c1 = _owner(
        closed, h, w["property"], "01", "1000", mea, {"hoa_fee": "100.00", "reserve": "200.00"}
    )
    _, c2 = _owner(
        closed, h, w["property"], "02", "1000", mea, {"hoa_fee": "100.00", "reserve": "200.00"}
    )
    for code, number in (("hoa_fee", "060100"), ("reserve", "060200")):
        _ok(
            closed.put(
                f"{A}/ledgers/{ledger}/payment-type-accounts",
                json={"payment_type_code": code, "account_id": acc[number]},
                headers=h,
            )
        )
    dach = _ok(
        closed.post(f"{H}/reserves", json={"ledger_id": ledger, "name": "Dach"}, headers=h), 201
    )
    fassade = _ok(
        closed.post(f"{H}/reserves", json={"ledger_id": ledger, "name": "Fassade"}, headers=h), 201
    )
    for contract, reserve in ((c1, dach), (c2, fassade)):  # Zweckbindung of the standing amounts
        _sql(
            migrator_engine,
            world.tenant_a,
            "UPDATE contract_payment SET reserve_id = :r "
            "WHERE contract_id = :c AND payment_type_code = 'reserve'",
            r=reserve["id"],
            c=contract["id"],
        )
    for c in (c1, c2):
        run = _ok(
            closed.post(
                f"{A}/receivable-runs",
                json={"period_month": "2025-01-01", "scope": "contract", "scope_id": c["id"]},
                headers=h,
            ),
            201,
        )
        _ok(closed.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    bound = _sql(
        migrator_engine,
        world.tenant_a,
        "SELECT count(*) FROM receivable_item WHERE reserve_id IS NOT NULL",
    )[0][0]
    assert bound == 2  # the item carries the binding on

    items = _ok(
        closed.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-01-31"}, headers=h)
    )
    reserve_items = [i for i in items if i["remaining"] == "200.00"]
    assert len(reserve_items) == 2  # hoa_fee items are 100,00
    by_contract = {i["contract_id"]: i for i in reserve_items}
    for contract, pay in ((c1, "200.00"), (c2, "50.00")):
        item = by_contract[contract["id"]]
        draft = _ok(
            closed.post(
                f"{A}/ledgers/{ledger}/entries",
                json={
                    "kind": "debtor_payment",
                    "booking_date": "2025-01-05",
                    "text": "Zahlung Rücklage",
                    "lines": [
                        {"account_id": acc["001201"], "debit": pay},
                        {"account_id": item["account_id"], "credit": pay},
                    ],
                    "settlements": [{"open_item_id": item["id"], "amount": pay}],
                },
                headers=h,
            ),
            201,
        )
        _ok(closed.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    _book_cost(closed, h, ledger, acc["001200"], acc["043000"], "1200.00", "2025-03-01")
    st = _ok(
        closed.post(f"{H}/statements", json={"ledger_id": ledger, "year": 2025}, headers=h), 201
    )
    _ok(
        closed.post(
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
    snap: dict[str, Any] = _ok(closed.post(f"{H}/statements/{st['id']}/calculate", headers=h))[
        "snapshot"
    ]
    reserve = snap["reserve"]
    assert reserve["contributions_paid"] == "250.00"
    assert reserve["contributions_paid_by_reserve"] == {
        dach["id"]: "200.00",
        fassade["id"]: "50.00",
    }
    assert reserve["contributions_paid_unassigned"] == "0.00"
    positions = {p["name"]: p for p in reserve["positions"]}
    assert positions["Dach"]["contributions_paid"] == "200.00"
    assert positions["Dach"]["contributions_paid_bound"] is True
    assert positions["Fassade"]["paid_change"] == "50.00"

    # Gesamtabrechnung PDF: after the internal approval, G4 and the tenant letterhead.
    sid = st["id"]
    _ok(
        closed.post(
            f"{H}/statements/{sid}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    assert closed.get(f"{H}/statements/{sid}/pdf", headers=h).status_code == 403  # G4 closed
    blocked = open_.get(f"{H}/statements/{sid}/pdf", headers=h)
    assert blocked.status_code == 422, blocked.text  # no letterhead, no invented company data
    _ok(closed.patch("/api/v1/tenant/settings", json={"company": COMPANY}, headers=h))
    pdf = open_.get(f"{H}/statements/{sid}/pdf", headers=h)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    body = _pdf_text(pdf.content)
    assert "Gesamtabrechnung 2025" in body
    assert str(COMPANY["name"]) in body
    assert "ENTWURF" in body
    assert "Dach" in body
    assert "Fassade" in body
    assert "1.200,00 EUR" in body
    assert "250,00 EUR" in body


def test_total_pdf_unknown_statement_404(
    s3_clients: tuple[TestClient, TestClient],
    world: World,
) -> None:
    _, open_ = s3_clients
    h = bearer(login(open_, world, "q09admin"))
    response = open_.get(f"{H}/statements/00000000-0000-7000-8000-000000000000/pdf", headers=h)
    assert response.status_code == 404


def test_plan_comparison_and_quarterly_apply_with_reserve_binding(
    clients: tuple[TestClient, TestClient],
    world: World,
    migrator_engine: Engine,
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "q09admin"))
    h2 = bearer(login(client, world, "q09second"))
    w = _hoa_ledger(client, h, "762")
    mea, ledger = w["keys"]["MEA"], w["ledger"]
    _, c1 = _owner(client, h, w["property"], "01", "600", mea, {})
    _owner(client, h, w["property"], "02", "400", mea, {})
    dach = _ok(
        client.post(f"{H}/reserves", json={"ledger_id": ledger, "name": "Dach"}, headers=h), 201
    )

    def make_plan(year: int, valid_from: str, hoa_fee: str, **extra: Any) -> dict[str, Any]:
        plan = _ok(
            client.post(
                f"{H}/plans",
                json={"ledger_id": ledger, "year": year, "valid_from": valid_from, **extra},
                headers=h,
            ),
            201,
        )
        for component, amount, reserve in (
            ("hoa_fee", hoa_fee, None),
            ("reserve", "1200.00", dach["id"]),
        ):
            item = {
                "label": component,
                "component": component,
                "amount": amount,
                "allocation_key_id": mea,
            }
            if reserve:
                item["reserve_id"] = reserve
            _ok(client.post(f"{H}/plans/{plan['id']}/items", json=item, headers=h), 201)
        return plan

    # Comparison with the previous plan: Hausgeld 6.000,00 against 5.000,00.
    previous = make_plan(2026, "2026-01-01", "5000.00")
    _ok(client.post(f"{H}/plans/{previous['id']}/calculate", headers=h))
    plan = make_plan(
        2027,
        "2027-01-01",
        "6000.00",
        payment_rhythm="quarterly",
        due_day=3,
        basis_plan_id=previous["id"],
    )
    calc = _ok(client.post(f"{H}/plans/{plan['id']}/calculate", headers=h))
    rows = {r["component"]: r for r in calc["snapshot"]["totals_comparison"]["rows"]}
    assert calc["snapshot"]["totals_comparison"]["basis_kind"] == "plan"
    assert (rows["hoa_fee"]["basis_amount"], rows["hoa_fee"]["deviation"]) == ("5000.00", "1000.00")
    assert rows["hoa_fee"]["deviation_percent"] == "20.00"
    assert rows["reserve"]["deviation"] == "0.00"
    unit1 = next(u for u in calc["snapshot"]["units"] if u["unit_number"] == "01")
    assert unit1["reserve_split"] == {dach["id"]: "720.00"}

    _ok(
        client.post(
            f"{H}/plans/{plan['id']}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    resolution = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2026-11-15",
                "subject": "Wirtschaftsplan 2027",
                "wording": "Der Wirtschaftsplan 2027 wird beschlossen.",
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
        client.post(
            f"{H}/plans/{plan['id']}/transition",
            json={"target": "resolved", "resolution_id": resolution["id"]},
            headers=h,
        )
    )
    preview = _ok(client.get(f"{H}/plans/{plan['id']}/apply/preview", headers=h))
    by = {(r["unit_number"], r["component"]): r for r in preview["rows"]}
    assert (by[("01", "hoa_fee")]["new"], by[("01", "hoa_fee")]["instalment"]) == (
        "300.00",
        "900.00",
    )
    assert by[("01", "reserve")]["rhythm"] == "quarterly"
    assert by[("01", "reserve")]["instalment"] == "180.00"
    done = _ok(
        client.post(
            f"{H}/plans/{plan['id']}/apply",
            json={"confirm": True, "snapshot_hash": calc["snapshot_hash"]},
            headers=h2,
        )
    )
    assert done["payments_created"] == 4
    assert done["schedules_set"] == 2
    payments = _ok(client.get(f"/api/v1/contracts/{c1['id']}/payments", headers=h))
    reserve_payment = next(
        p
        for p in payments
        if p["payment_type_code"] == "reserve" and p["valid_from"] == "2027-01-01"
    )
    assert reserve_payment["reserve_id"] == dach["id"]
    assert reserve_payment["gross"] == "60.00"
    schedules = _sql(
        migrator_engine,
        world.tenant_a,
        "SELECT interval::text, due_day, payment_mode, amount_basis, valid_from::text, "
        "valid_to::text FROM payment_schedule WHERE contract_id = :c ORDER BY valid_from",
        c=c1["id"],
    )
    assert [tuple(s) for s in schedules] == [
        ("monthly", 3, "advance", "per_month", "2020-01-01", "2026-12-31"),
        ("quarterly", 3, "advance", "per_month", "2027-01-01", None),
    ]


def test_quarterly_plan_needs_first_of_month(
    clients: tuple[TestClient, TestClient],
    world: World,
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "q09admin"))
    h2 = bearer(login(client, world, "q09second"))
    w = _hoa_ledger(client, h, "763")
    mea = w["keys"]["MEA"]
    _owner(client, h, w["property"], "01", "1000", mea, {})
    plan = _ok(
        client.post(
            f"{H}/plans",
            json={
                "ledger_id": w["ledger"],
                "year": 2027,
                "valid_from": "2027-02-15",
                "payment_rhythm": "yearly",
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{H}/plans/{plan['id']}/items",
            json={
                "label": "x",
                "component": "hoa_fee",
                "amount": "100.00",
                "allocation_key_id": mea,
            },
            headers=h,
        ),
        201,
    )
    calc = _ok(client.post(f"{H}/plans/{plan['id']}/calculate", headers=h))
    _ok(
        client.post(
            f"{H}/plans/{plan['id']}/transition", json={"target": "internally_approved"}, headers=h2
        )
    )
    res = _ok(
        client.post(
            f"{H}/resolutions",
            json={
                "legal_entity_id": w["hoa"],
                "decided_on": "2027-01-15",
                "subject": "Plan",
                "wording": "Der Wirtschaftsplan wird beschlossen.",
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
        client.post(
            f"{H}/plans/{plan['id']}/transition",
            json={"target": "resolved", "resolution_id": res["id"]},
            headers=h,
        )
    )
    refused = client.post(
        f"{H}/plans/{plan['id']}/apply",
        json={"confirm": True, "snapshot_hash": calc["snapshot_hash"]},
        headers=h2,
    )
    assert refused.status_code == 409
    assert "Monatsersten" in refused.json()["detail"]
