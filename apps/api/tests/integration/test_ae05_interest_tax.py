"""AE05 / P01-01: withholding taxes on credit interest as amounts from the bank document.

Expected values by hand (rule 0.1.8): gross interest 100.00 EUR, Kapitalertragsteuer 25.00,
Solidaritätszuschlag 1.37, Kirchensteuer 0.00 (taken from the bank statement, no rate): bank
(reserve account) debit 100.00 - 25.00 - 1.37 = 73.63, tax account debit 25.00 and 1.37,
interest revenue credit 100.00. Reserve development 2026 shows withheld total 26.37."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m10_ledger import A, _hoa_ledger, _ok

pytestmark = pytest.mark.integration

H = "/api/v1/hoa"


async def _ae05_world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae05a-{RUN}", name=f"AE05 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae05b-{RUN}", name=f"AE05b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae05admin", a, "tenant_admin"),
            ("ae05reader", a, "read_only"),
            ("ae05other", b, "tenant_admin"),
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
    return asyncio.run(_ae05_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _tax_account(c: TestClient, h: dict[str, str], ledger: str, number: str) -> str:
    body = {"number": number, "name": f"Steuer {number}", "category": "tax", "type": "asset"}
    return str(_ok(c.post(f"{A}/ledgers/{ledger}/accounts", json=body, headers=h), 201)["id"])


def _interest(reserve_acc: str, revenue: str, **taxes: str) -> dict[str, Any]:
    return {
        "booking_date": "2026-03-31",
        "bank_account_id": reserve_acc,
        "interest_account_id": revenue,
        "amount": "100.00",
        "direction": "credit",
        "text": "Habenzinsen Rücklagenkonto Q1",
        **taxes,
    }


def test_interest_with_withholdings(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae05admin"))
    ledger, acc, _ = _hoa_ledger(client, h, "951")
    rows = _ok(client.get(f"{A}/ledgers/{ledger}/accounts", headers=h))
    revenue = next(r["id"] for r in rows if r["category"] == "revenue" and r["active"])
    reserve_acc = acc["001201"]
    url = f"{A}/ledgers/{ledger}/entries/interest"
    cfg_url = f"{A}/ledgers/{ledger}/interest-tax-config"

    # without configuration: no withholding accepted, gross booking unchanged
    empty = _ok(client.get(cfg_url, headers=h))
    assert empty["capital_gains_tax_account_id"] is None
    refused = client.post(
        url, json=_interest(reserve_acc, revenue, capital_gains_tax="25.00"), headers=h
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "MHVP-ACC-0011"

    kest = _tax_account(client, h, ledger, "026501")
    soli = _tax_account(client, h, ledger, "026502")
    # revenue account as tax account refused
    bad = client.put(cfg_url, json={"capital_gains_tax_account_id": revenue}, headers=h)
    assert bad.status_code == 422
    cfg = _ok(
        client.put(
            cfg_url,
            json={"capital_gains_tax_account_id": kest, "solidarity_tax_account_id": soli},
            headers=h,
        )
    )
    assert cfg["church_tax_account_id"] is None
    # church tax without account: refused
    no_church = client.post(url, json=_interest(reserve_acc, revenue, church_tax="2.00"), headers=h)
    assert no_church.status_code == 422
    # withholdings not below gross: refused
    too_much = client.post(
        url, json=_interest(reserve_acc, revenue, capital_gains_tax="100.00"), headers=h
    )
    assert too_much.status_code == 422
    # debit interest with withholding: refused
    cost = next(r["id"] for r in rows if r["category"] == "cost" and r["active"])
    debit = {**_interest(reserve_acc, cost, capital_gains_tax="1.00"), "direction": "debit"}
    assert client.post(url, json=debit, headers=h).status_code == 422
    # negative amount: 422 validation
    neg = client.post(url, json=_interest(reserve_acc, revenue, solidarity_tax="-1.00"), headers=h)
    assert neg.status_code == 422

    # AE40: a draft with withholdings can be deleted (the withholding row goes with it).
    throwaway = _ok(
        client.post(url, json=_interest(reserve_acc, revenue, capital_gains_tax="5.00"), headers=h),
        201,
    )
    gone = client.delete(f"{A}/ledgers/{ledger}/entries/{throwaway['id']}", headers=h)
    assert gone.status_code == 204, gone.text
    assert (
        client.get(
            f"{A}/ledgers/{ledger}/entries/{throwaway['id']}/interest-tax", headers=h
        ).status_code
        == 404
    )
    draft = _ok(
        client.post(
            url,
            json=_interest(reserve_acc, revenue, capital_gains_tax="25.00", solidarity_tax="1.37"),
            headers=h,
        ),
        201,
    )
    assert draft["status"] == "draft"
    lines = {line["account_id"]: line for line in draft["lines"]}
    assert lines[reserve_acc]["debit"] == "73.63"
    assert lines[kest]["debit"] == "25.00"
    assert lines[soli]["debit"] == "1.37"
    assert lines[revenue]["credit"] == "100.00"
    tax_url = f"{A}/ledgers/{ledger}/entries/{draft['id']}/interest-tax"
    tax = _ok(client.get(tax_url, headers=h))
    assert (tax["gross_amount"], tax["net_amount"], tax["church_tax"]) == (
        "100.00",
        "73.63",
        "0.00",
    )

    reserve = _ok(
        client.post(
            f"{H}/reserves",
            json={"ledger_id": ledger, "name": "Erhaltung", "account_id": reserve_acc},
            headers=h,
        ),
        201,
    )
    dev_url = f"{H}/reserves/{reserve['id']}/development?year=2026"
    # drafts are not shown
    assert (
        _ok(client.get(dev_url, headers=h))["years"][-1]["interest_tax_withheld"]["total"] == "0.00"
    )
    _ok(client.post(f"{A}/ledgers/{ledger}/entries/{draft['id']}/post", headers=h))
    withheld = _ok(client.get(dev_url, headers=h))["years"][-1]["interest_tax_withheld"]
    assert (withheld["capital_gains_tax"], withheld["solidarity_tax"], withheld["total"]) == (
        "25.00",
        "1.37",
        "26.37",
    )

    # read only: read allowed, write 403; other tenant: 404
    reader = bearer(login(client, world, "ae05reader"))
    assert client.get(cfg_url, headers=reader).status_code == 200
    assert client.put(cfg_url, json={}, headers=reader).status_code == 403
    other = bearer(login(client, world, "ae05other"))
    assert client.get(cfg_url, headers=other).status_code == 404
    assert client.get(tax_url, headers=other).status_code == 404


def test_interest_tax_summary_is_tenant_wide(client: TestClient, world: World) -> None:
    """GAE-38 (AF24): read only summary over all ledgers of the tenant, other tenant sees none."""
    h = bearer(login(client, world, "ae05admin"))
    summary_url = f"{A}/interest-tax-config"
    before = _ok(client.get(summary_url, headers=h))
    ledger, _, _ = _hoa_ledger(client, h, "952")
    mid = _ok(client.get(summary_url, headers=h))
    assert mid["ledgers_total"] == before["ledgers_total"] + 1
    assert mid["ledgers_configured"] == before["ledgers_configured"]
    kest = _tax_account(client, h, ledger, "026502")
    _ok(
        client.put(
            f"{A}/ledgers/{ledger}/interest-tax-config",
            json={"capital_gains_tax_account_id": kest},
            headers=h,
        )
    )
    after = _ok(client.get(summary_url, headers=h))
    assert after["ledgers_configured"] == before["ledgers_configured"] + 1
    reader = bearer(login(client, world, "ae05reader"))
    assert client.get(summary_url, headers=reader).status_code == 200
    assert client.get(summary_url + "?x=1", headers=h).status_code == 422
    other = bearer(login(client, world, "ae05other"))
    assert _ok(client.get(summary_url, headers=other)) == {
        "ledgers_total": 0,
        "ledgers_configured": 0,
    }
    assert client.get(summary_url).status_code == 401
