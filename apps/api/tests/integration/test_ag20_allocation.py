"""AG20 (wave 18): GAE-11 rest and GAE-12 rest.

Expected values by hand (independent of the code):

* GAE-11, year 2025, units 01 and 02 (MEA 1.000 each), reserve advance 200,00 per unit and
  month. Unit 01's standing amount is bound to reserve "Dach", unit 02's is not bound.
  January 2025 posted; bank payments: unit 01 pays 200,00, unit 02 pays 50,00.
  Resolved plan 2025: reserve items Dach 600,00 and Fassade 400,00.
  -> contributions_paid 200,00 + 50,00 = 250,00; paid_by_reserve {Dach: 200,00};
     unassigned 250,00 - 200,00 = 50,00.
  With variant plan_ratio_proposal the 50,00 split 600:400 -> Dach 30,00, Fassade 20,00
  (50 * 600 / 1000 = 30,00; 50 * 400 / 1000 = 20,00, no rounding rest); with proposal Dach
  200,00 + 30,00 = 230,00, Fassade 0,00 + 20,00 = 20,00. Nothing is posted by the proposal.
* GAE-12: unit 01 owner A since 2020, inheritance to B on 01.05.2026. Plan 2026 valid from
  01.06.2026, resolution 15.04.2026. The takeover uses the owner at valid_from (B). Proposal
  with rule inheritance=by_resolution_date: owner on 15.04.2026 = A (differs); with
  manual_release: B (no difference); switch off: no proposal field.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from mhvp.main import create_app
from tests.integration.conftest import Database
from tests.integration.test_af08_hoa import _transfer
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m24_hoa import A, H, _book_cost, _hoa_ledger, _ok, _owner

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.platform import services

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag20a-{RUN}", name=f"AG20 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag20b-{RUN}", name=f"AG20 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ag20admin", a, "tenant_admin"),
            ("ag20second", a, "tenant_admin"),
            ("ag20reader", a, "read_only"),
            ("ag20other", b, "tenant_admin"),
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
    with TestClient(create_app(base_settings(database, redis_url))) as c:
        yield c


def _sql(engine: Engine, tenant: Any, statement: str, **params: Any) -> Any:
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        result = conn.execute(text(statement), params)
        return result.all() if result.returns_rows else None


def _resolved_plan(
    c: TestClient,
    h: dict[str, str],
    h2: dict[str, str],
    w: dict[str, Any],
    year: int,
    valid_from: str,
    decided_on: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    plan = _ok(
        c.post(
            f"{H}/plans",
            json={"ledger_id": w["ledger"], "year": year, "valid_from": valid_from},
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
                "decided_on": decided_on,
                "subject": f"Wirtschaftsplan {year}",
                "wording": f"Der Wirtschaftsplan {year} wird beschlossen.",
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
    return dict(plan)


def test_gae11_statement_with_bound_payment_and_plan_ratio_proposal(
    client: TestClient, world: World, migrator_engine: Engine
) -> None:
    c = client
    h = bearer(login(c, world, "ag20admin"))
    h2 = bearer(login(c, world, "ag20second"))
    w = _hoa_ledger(c, h, "981")
    mea, ledger, acc = w["keys"]["MEA"], w["ledger"], w["acc"]
    _, c1 = _owner(c, h, w["property"], "01", "1000", mea, {"reserve": "200.00"})
    _, c2 = _owner(c, h, w["property"], "02", "1000", mea, {"reserve": "200.00"})
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
                    "period_month": "2025-01-01",
                    "scope": "contract",
                    "scope_id": contract["id"],
                },
                headers=h,
            ),
            201,
        )
        _ok(c.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    items = _ok(
        c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-01-31"}, headers=h)
    )
    by_contract = {i["contract_id"]: i for i in items if i["remaining"] == "200.00"}
    for contract, pay in ((c1, "200.00"), (c2, "50.00")):
        item = by_contract[contract["id"]]
        draft = _ok(
            c.post(
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
        _ok(c.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    _resolved_plan(
        c,
        h,
        h2,
        w,
        2025,
        "2025-01-01",
        "2024-12-10",
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
    _book_cost(c, h, ledger, acc["001200"], acc["043000"], "1200.00", "2025-03-01")
    st = _ok(c.post(f"{H}/statements", json={"ledger_id": ledger, "year": 2025}, headers=h), 201)
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
    _ok(c.put(f"{H}/reserve-payment-settings", json={"mode": "plan_ratio_proposal"}, headers=h))
    try:
        snap = _ok(c.post(f"{H}/statements/{st['id']}/calculate", headers=h))["snapshot"]
        payments = _ok(
            c.get(f"{H}/ledgers/{ledger}/reserve-payments", params={"year": 2025}, headers=h)
        )
    finally:
        _ok(c.put(f"{H}/reserve-payment-settings", json={"mode": "bound_only"}, headers=h))
    reserve = snap["reserve"]
    assert reserve["contributions_paid"] == "250.00"
    assert reserve["contributions_paid_by_reserve"] == {dach["id"]: "200.00"}
    assert reserve["contributions_paid_unassigned"] == "50.00"
    pos = {p["name"]: p for p in reserve["positions"]}
    assert (pos["Dach"]["contributions_planned"], pos["Fassade"]["contributions_planned"]) == (
        "600.00",
        "400.00",
    )
    assert pos["Dach"]["contributions_paid"] == "200.00"
    assert pos["Dach"]["contributions_paid_bound"] is True
    assert pos["Fassade"]["contributions_paid_bound"] is False
    assert pos["Dach"]["contributions_paid_proposal"] == "30.00"
    assert pos["Fassade"]["contributions_paid_proposal"] == "20.00"
    assert pos["Dach"]["contributions_paid_with_proposal"] == "230.00"
    assert pos["Fassade"]["contributions_paid_with_proposal"] == "20.00"
    assert payments["source"] == "statement"
    assert payments["paid_unassigned"] == "50.00"
    rows = {r["name"]: r for r in payments["reserves"]}
    assert (rows["Dach"]["paid_bound"], rows["Dach"]["open_bound"]) == ("200.00", "400.00")
    assert rows["Fassade"]["paid_with_proposal"] == "20.00"
    # The proposal posts nothing: the bound item stays as it is (remaining 0,00 and 150,00).
    remaining = sorted(
        i["remaining"]
        for i in _ok(
            c.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2025-12-31"}, headers=h)
        )
    )
    assert remaining == ["150.00"]
    # Statement allocation proposal: switch off -> 409; on, but no resolution -> 409.
    url = f"{H}/statements/{st['id']}/allocation-proposal"
    assert c.get(url, headers=h).status_code == 409
    _ok(c.put(f"{H}/allocation-proposal-settings", json={"enabled": True}, headers=h))
    try:
        assert c.get(url, headers=h).status_code == 409
        assert c.get(url, params={"x": "1"}, headers=h).status_code == 422
    finally:
        _ok(c.put(f"{H}/allocation-proposal-settings", json={"enabled": False}, headers=h))


def test_gae12_plan_takeover_allocation_proposal(client: TestClient, world: World) -> None:
    c = client
    h = bearer(login(c, world, "ag20admin"))
    h2 = bearer(login(c, world, "ag20second"))
    hr = bearer(login(c, world, "ag20reader"))
    ho = bearer(login(c, world, "ag20other"))
    w = _hoa_ledger(c, h, "982")
    _, old = _owner(c, h, w["property"], "01", "1000", w["keys"]["MEA"], {})
    from tests.integration.test_m5_contracts import _party

    party_b, _ = _party(c, h, "AG20Erbe")
    new = _transfer(c, h, old["id"], party_b, "inheritance")
    plan = _resolved_plan(
        c,
        h,
        h2,
        w,
        2026,
        "2026-06-01",
        "2026-04-15",
        [{"label": "Hausgeld", "component": "hoa_fee", "amount": "1200.00"}],
    )
    preview_url = f"{H}/plans/{plan['id']}/apply/preview"

    def row() -> dict[str, Any]:
        rows = _ok(c.get(preview_url, headers=h))["rows"]
        (only,) = [r for r in rows if r["component"] == "hoa_fee"]
        return dict(only)

    # Default: switch off, no proposal field, takeover owner is B.
    setting = _ok(c.get(f"{H}/allocation-proposal-settings", headers=h))
    assert setting["enabled"] is False
    off = row()
    assert "allocation_proposal" not in off
    assert off["contract_id"] == new["id"]
    # Validation, permission, tenant separation of the switch.
    s = f"{H}/allocation-proposal-settings"
    assert c.put(s, json={"enabled": True, "x": 1}, headers=h).status_code == 422
    assert c.put(s, json={"enabled": True}, headers=hr).status_code == 403
    _ok(c.put(s, json={"enabled": True}, headers=h))
    try:
        assert _ok(c.get(s, headers=ho))["enabled"] is False
        manual = row()["allocation_proposal"]
        assert manual == {
            "proposed": {"contract_id": new["id"], "contract_number": new["number"]},
            "differs": False,
        }
        _ok(
            c.put(
                f"{H}/acquisition-rules/inheritance",
                json={"variant": "by_resolution_date"},
                headers=h,
            )
        )
        try:
            proposed = row()
            assert proposed["contract_id"] == new["id"]  # used owner unchanged
            assert proposed["allocation_proposal"]["proposed"]["contract_id"] == old["id"]
            assert proposed["allocation_proposal"]["differs"] is True
        finally:
            _ok(
                c.put(
                    f"{H}/acquisition-rules/inheritance",
                    json={"variant": "manual_release"},
                    headers=h,
                )
            )
        assert c.get(preview_url, headers=ho).status_code == 404
    finally:
        _ok(c.put(s, json={"enabled": False}, headers=h))
