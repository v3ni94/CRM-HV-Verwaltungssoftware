"""AE15 (Welle 16, Punkt 15): tenant switch for advances still open at statement issue
(D24, AC10-01, M17-03, P06-01). Own world (prefix ae15).

Model input as in the D24 gap test (annex D names no figure): advance 100,00 per month,
January and February 2025 due (200,00), January paid (100,00), February open (100,00), cost
share 120,00. Economically owed: 120,00 - 100,00 = 20,00 EUR.

* info_only (default): balance 120,00 - 100,00 = 20,00, open 100,00 stays -> combined view
  120,00 (the double claim D24 forbids; kept as default until AC10-01, see
  test_annex_d_gaps.test_d24_default_info_only_keeps_double_view_until_ac10_01).
* offset_reversal: balance 20,00, open 100,00 offset by a draft behind G3 -> 20,00.
* balance_against_due: balance 120,00 - 200,00 = -80,00, open 100,00 stays -> -80 + 100 = 20,00.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_annex_d_gaps import _d24_world, _open_remaining
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m17_operating_costs import OpenG3

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
S = "/api/v1/statements"
R = "/api/v1/billing/advance-rule"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae15-{RUN}", name=f"AE15 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae15-b-{RUN}", name=f"AE15 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("ae15admin", "tenant_admin", a),
            ("ae15acc", "accountant_no_banking", a),
            ("ae15read", "read_only", a),
            ("ae15other", "tenant_admin", b),
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG3())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _set_mode(client: TestClient, h: dict[str, str], mode: str) -> None:
    assert (
        _ok(client.put(R, json={"open_advance_mode": mode}, headers=h))["open_advance_mode"] == mode
    )


def _calc(client: TestClient, h: dict[str, str], number: str) -> tuple[dict[str, Any], Any]:
    w = _d24_world(client, h, number)
    result = _ok(client.post(f"{S}/{w['statement']['id']}/calculate", headers=h))
    (row,) = result["snapshot"]["results"]
    return w, row


def test_ae15_switch_api_default_validation_permission_and_tenant(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "ae15admin"))
    rule = _ok(client.get(R, headers=h))
    assert rule["open_advance_mode"] == "info_only"  # conservative default
    assert set(rule["open_advance_modes"]) == {
        "info_only",
        "offset_reversal",
        "balance_against_due",
    }
    assert client.put(R, json={"open_advance_mode": "write_off"}, headers=h).status_code == 422
    assert client.put(R, json={}, headers=h).status_code == 422
    read = bearer(login(client, world, "ae15read"))
    assert client.get(R, headers=read).status_code == 200
    assert (
        client.put(R, json={"open_advance_mode": "offset_reversal"}, headers=read).status_code
        == 403
    )
    _set_mode(client, h, "balance_against_due")
    assert _ok(client.get(R, headers=h))["surcharge_percent"] == "0.00"  # untouched
    other = bearer(login(client, world, "ae15other"))
    assert _ok(client.get(R, headers=other))["open_advance_mode"] == "info_only"
    _set_mode(client, h, "info_only")


def test_ae15_d24_info_only_default_keeps_today_and_discloses(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "ae15admin"))
    _set_mode(client, h, "info_only")
    w, row = _calc(client, h, "151")
    assert (row["open_advance_mode"], row["balance"], row["net_claim"]) == (
        "info_only",
        "20.00",
        "120.00",  # 20,00 + 100,00: open decision AC10-01 (no xfail marker)
    )
    assert row["offset_items"] == []
    assert _open_remaining(client, h, w["ledger"]) == Decimal("100.00")


def test_ae15_d24_balance_against_due_claims_the_open_amount_once(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "ae15admin"))
    _set_mode(client, h, "balance_against_due")
    try:
        w, row = _calc(client, h, "152")
    finally:
        _set_mode(client, h, "info_only")
    owed = Decimal(row["costs"]) - Decimal(row["advances_paid"])
    assert owed == Decimal("20.00")
    assert row["balance"] == "-80.00"  # 120,00 - 200,00
    open_now = _open_remaining(client, h, w["ledger"])
    assert open_now == Decimal("100.00")  # own legal ground, stays
    assert Decimal(row["balance"]) + open_now == owed
    assert Decimal(row["net_claim"]) == owed
    assert any("Gesamtsicht" in s for s in row["calculation_steps"])


def test_ae15_d24_offset_reversal_drafts_behind_g3_claim_once(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, gated = clients
    h = bearer(login(client, world, "ae15admin"))
    acc_user = bearer(login(client, world, "ae15acc"))
    _set_mode(client, h, "offset_reversal")
    try:
        w, row = _calc(client, h, "153")
    finally:
        _set_mode(client, h, "info_only")
    ledger, st = w["ledger"], w["statement"]
    assert (row["balance"], row["net_claim"]) == ("20.00", "20.00")
    (item,) = row["offset_items"]
    assert item["remaining"] == "100.00"
    # Calculation posts nothing; the open February item is still open.
    assert _open_remaining(client, h, ledger) == Decimal("120.00") - Decimal("20.00")
    result_account = _ok(
        client.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "060900",
                "name": "Ergebnis BK",
                "category": "revenue",
                "type": "income",
            },
            headers=h,
        ),
        201,
    )["id"]
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "statement_result", "account_id": result_account},
            headers=h,
        )
    )
    # The M17-01 allocation basis lock (other package, default on) is not under test here;
    # this world records no allocation agreements, so it is switched off for this tenant only.
    basis = client.put(
        "/api/v1/billing/allocation-basis-setting", json={"block_output": False}, headers=h
    )
    assert basis.status_code in (200, 404), basis.text
    _ok(
        client.post(
            f"{S}/{st['id']}/transition", json={"target": "internally_approved"}, headers=acc_user
        )
    )
    delivered = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    issue = client.post(
        f"{S}/{st['id']}/transition",
        json={"target": "issued", "delivered_at": delivered},
        headers=acc_user,
    )
    assert issue.status_code == 403  # G3 closed
    assert issue.json()["code"] == "MHVP-GATE-0001"
    gh = bearer(login(gated, world, "ae15acc"))
    _ok(
        gated.post(
            f"{S}/{st['id']}/transition",
            json={"target": "issued", "delivered_at": delivered},
            headers=gh,
        )
    )
    _ok(gated.post(f"{S}/{st['id']}/transition", json={"target": "due"}, headers=gh))
    body = {"booking_date": delivered, "due_date": delivered}
    ids = _ok(gated.post(f"{S}/{st['id']}/result-entries", json=body, headers=gh), 201)["entry_ids"]
    assert len(ids) == 2  # result 20,00 and offset 100,00, drafts only
    again = _ok(gated.post(f"{S}/{st['id']}/result-entries", json=body, headers=gh), 201)
    assert again["entry_ids"] == ids  # idempotent
    assert _open_remaining(client, h, ledger) == Decimal("100.00")  # drafts change nothing
    for entry_id in ids:
        entry = _ok(client.get(f"{A}/ledgers/{ledger}/entries/{entry_id}", headers=h))
        assert entry["status"] == "draft"
        _ok(client.post(f"{A}/ledgers/{ledger}/entries/{entry_id}/post", headers=h))
    owed = Decimal(row["costs"]) - Decimal(row["advances_paid"])
    assert _open_remaining(client, h, ledger) == owed  # 20,00: claimed once
