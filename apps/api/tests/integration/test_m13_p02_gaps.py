"""M13-01, M13-02, M13-08 (7.5) and M13-03, M13-05, M13-06 (18 M13), S15-01 (15.1).

Expected values, computed by hand:
- Contract 01 posts March with hoa_fee 300,00 and reserve 50,00 (350,00). A later payment
  change to 320,00 from 01.03. yields one manual difference item +20,00 that points to the
  posted hoa_fee item; reserve (unchanged) yields nothing; the run posts nothing new.
- Items carry contract version 1, the payment plan id and the start of validity 01.03.2026.
- Fee: 2 apartments x 40,00 = 80,00 net, 19 % = 15,20, gross 95,20 per quarter. The quarter
  containing 15.02.2026 is 01.01. to 31.03.2026; a second invoice for it answers 409; after
  the cancellation the credit note mirrors -95,20 with its own number and the quarter can be
  invoiced again (third number).
"""

import asyncio
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _unit
from tests.integration.test_m13_receivables import _contract

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"p02-{RUN}", name=f"P02 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"p02b-{RUN}", name=f"P02b {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("p02admin", a, "tenant_admin"),
            ("p02care", a, "caretaker"),
            ("p02other", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_receivable_evidence_difference_and_run_list(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p02admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "021", "name": "Differenzhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    c1 = _contract(client, h, prop["id"], "01", "2020-01-01")
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
            json={"period_month": "2026-03-01", "scope": "property", "scope_id": prop["id"]},
            headers=h,
        ),
        201,
    )
    assert run["totals"]["ready"] == {"count": 2, "amount": "350.00"}
    for item in run["items"]:
        assert item["contract_version"] == 1  # M13-02 evidence
        assert item["payment_schedule_id"] is not None
        assert item["basis_valid_from"] == "2020-01-01"
        assert item["basis_reason"] == "initial"
    posted = _ok(client.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    hoa_item = next(i for i in posted["items"] if i["payment_type_code"] == "hoa_fee")

    # Plan change after posting (M13-01): 320,00 from 01.03.2026.
    _ok(
        client.post(
            f"/api/v1/contracts/{c1['id']}/payments",
            json={
                "payment_type_code": "hoa_fee",
                "net": "320.00",
                "gross": "320.00",
                "valid_from": "2026-03-01",
            },
            headers=h,
        ),
        201,
    )
    second = _ok(
        client.post(
            f"{A}/receivable-runs",
            json={"period_month": "2026-03-01", "scope": "property", "scope_id": prop["id"]},
            headers=h,
        ),
        201,
    )
    assert "ready" not in second["totals"]
    assert len(second["items"]) == 1
    diff = second["items"][0]
    assert diff["status"] == "manual"
    assert diff["difference_amount"] == "20.00"
    assert diff["difference_of_item_id"] == hoa_item["id"]
    assert diff["amount"] == "320.00"
    assert diff["basis_valid_from"] == "2026-03-01"
    assert "Storno" in diff["message"]
    again = _ok(client.post(f"{A}/receivable-runs/{second['id']}/post", headers=h))
    assert [i["status"] for i in again["items"]] == ["manual"]  # nothing posted by assumption

    # M13-08: list with filters, item filter on the detail.
    runs = client.get(
        f"{A}/receivable-runs",
        params={"period_month": "2026-03-15", "scope_id": prop["id"]},
        headers=h,
    )
    assert runs.status_code == 200, runs.text
    assert runs.headers["x-total-count"] == "2"
    assert [r["id"] for r in runs.json()] == [second["id"], run["id"]]
    only_posted = _ok(
        client.get(
            f"{A}/receivable-runs", params={"status": "posted", "scope_id": prop["id"]}, headers=h
        )
    )
    # Both runs were executed ("posted"); the second one posted nothing but keeps the status
    # of an executed run so that the difference item stays visible (newest first).
    assert [r["id"] for r in only_posted] == [second["id"], run["id"]]
    filtered = _ok(
        client.get(
            f"{A}/receivable-runs/{run['id']}",
            params={"payment_type_code": "reserve"},
            headers=h,
        )
    )
    assert [i["payment_type_code"] for i in filtered["items"]] == ["reserve"]
    assert client.get(f"{A}/receivable-runs", params={"status": "x"}, headers=h).status_code == 422
    other = bearer(login(client, world, "p02other"))
    assert _ok(client.get(f"{A}/receivable-runs", headers=other)) == []
    assert client.get(f"{A}/receivable-runs/{run['id']}", headers=other).status_code == 404


def test_admin_fee_settings_periods_and_credit_note(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "p02admin"))
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "022", "name": "Honorarhaus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    for no in ("01", "02"):
        _unit(client, h, prop["id"], no)
    fee = _ok(
        client.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-01-01",
                "vat_percent": "19",
                "amounts_per_unit_type": {"apartment": "30.00"},
            },
            headers=h,
        ),
        201,
    )
    url = f"{A}/admin-fees/{fee['id']}"
    # M13-03: read, change, validation, rights, other tenant.
    patched = _ok(
        client.patch(
            url,
            json={"interval": "quarterly", "amounts_per_unit_type": {"apartment": "40.00"}},
            headers=h,
        )
    )
    assert patched["interval"] == "quarterly"
    assert patched["amounts_per_unit_type"] == {"apartment": "40.00"}
    assert client.patch(url, json={"interval": "daily"}, headers=h).status_code == 422
    assert (
        client.patch(url, json={"min_amount": "90", "max_amount": "10"}, headers=h).status_code
        == 422
    )
    listed = _ok(client.get(f"{A}/admin-fees", params={"property_id": prop["id"]}, headers=h))
    assert [f["id"] for f in listed] == [fee["id"]]
    care = bearer(login(client, world, "p02care"))
    assert client.patch(url, json={"interval": "monthly"}, headers=care).status_code == 403
    other = bearer(login(client, world, "p02other"))
    assert client.get(url, headers=other).status_code == 404

    _ok(
        client.patch(
            "/api/v1/tenant/billing-settings",
            json={"invoice_prefix": "PZ", "vat_status": "regelbesteuert", "vat_id": "DE123456789"},
            headers=h,
        )
    )
    # M13-06: period preview and one invoice per quarter.
    preview = _ok(
        client.get(
            f"{A}/admin-fees-periods",
            params={"period_date": "2026-02-15", "property_id": prop["id"]},
            headers=h,
        )
    )
    row = preview["rows"][0]
    assert (row["period_start"], row["period_end"], row["status"]) == (
        "2026-01-01",
        "2026-03-31",
        "due",
    )
    assert row["draft"]["gross"] == "95.20"
    issue = f"{url}/invoice-issue"
    params = {"period_start": "2026-02-15", "invoice_date": "2026-04-02"}
    first = _ok(client.post(issue, params=params, headers=h))
    assert (first["period_start"], first["period_end"]) == ("2026-01-01", "2026-03-31")
    assert first["gross"] == "95.20"
    assert client.post(issue, params=params, headers=h).status_code == 409
    assert (
        client.post(issue, params={"period_start": "2025-06-01"}, headers=h).status_code == 422
    )  # before the fee starts
    assert client.delete(url, headers=h).status_code == 409  # invoices exist
    assert client.patch(url, json={"end_date": "2026-02-28"}, headers=h).status_code == 409

    # M13-05: list, detail, release, cancellation by credit note.
    invoices = _ok(
        client.get(f"{A}/admin-fee-invoices", params={"fee_setting_id": fee["id"]}, headers=h)
    )
    assert [i["number"] for i in invoices] == [first["number"]]
    assert client.get(f"{A}/admin-fee-invoices/{first['id']}", headers=other).status_code == 404
    released = _ok(client.post(f"{A}/admin-fee-invoices/{first['id']}/release", headers=h))
    assert released["status"] == "released"
    assert released["released_at"]
    assert (
        client.post(f"{A}/admin-fee-invoices/{first['id']}/release", headers=care).status_code
        == 403
    )
    assert (
        client.post(
            f"{A}/admin-fee-invoices/{first['id']}/cancel", json={"reason": ""}, headers=h
        ).status_code
        == 422
    )
    credit = _ok(
        client.post(
            f"{A}/admin-fee-invoices/{first['id']}/cancel",
            json={"reason": "Einheitenzahl korrigiert", "credit_note_date": "2026-04-10"},
            headers=h,
        ),
        201,
    )
    assert credit["kind"] == "credit_note"
    assert credit["gross"] == "-95.20"
    assert credit["net"] == "-80.00"
    assert credit["corrects_invoice_id"] == first["id"]
    assert credit["number"] != first["number"]
    assert credit["xrechnung_url"] is None
    detail = _ok(client.get(f"{A}/admin-fee-invoices/{first['id']}", headers=h))
    assert detail["cancelled_at"]
    assert detail["corrected_by_id"] == credit["id"]
    assert detail["gross"] == "95.20"  # the invoice itself is never changed
    assert (
        client.post(
            f"{A}/admin-fee-invoices/{first['id']}/cancel", json={"reason": "noch mal"}, headers=h
        ).status_code
        == 409
    )
    assert client.get(f"{A}/invoices/{credit['id']}/xrechnung.xml", headers=h).status_code == 409
    reissued = _ok(client.post(issue, params=params, headers=h))
    numbers = [first["number"], credit["number"], reissued["number"]]
    assert [int(n.rsplit("-", 1)[1]) for n in numbers] == sorted(
        int(n.rsplit("-", 1)[1]) for n in numbers
    )
    assert len(set(numbers)) == 3

    # A fee without invoices can be deleted; ending before the start is invalid.
    spare = _ok(
        client.post(
            f"{A}/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-05-01",
                "amounts_per_unit_type": {"apartment": "10.00"},
            },
            headers=h,
        ),
        201,
    )
    spare_url = f"{A}/admin-fees/{spare['id']}"
    assert client.patch(spare_url, json={"end_date": "2026-04-01"}, headers=h).status_code == 422
    assert client.delete(spare_url, headers=h).status_code == 204
    assert client.get(spare_url, headers=h).status_code == 404


def test_s15_01_monthly_receivable_preview_task(database: Database, redis_url: str) -> None:
    from mhvp.accounting.tasks import receivable_previews

    settings = _settings(database, redis_url)
    before = asyncio.run(receivable_previews(settings, date(2031, 7, 1)))
    assert before["runs"] >= 0  # other tenants without the switch create nothing

    async def _switch_on() -> None:
        from sqlalchemy import select

        from mhvp.core.db.engine import create_app_engine, create_session_factory
        from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
        from mhvp.platform.models import Tenant, TenantSettings

        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with platform_transaction(factory) as session:
                tenant_id = await session.scalar(
                    select(Tenant.id).where(Tenant.slug == f"p02-{RUN}")
                )
            async with tenant_transaction(factory, tenant_id) as session:
                row = await session.scalar(select(TenantSettings))
                assert row is not None
                row.receivable_rules = {
                    **(row.receivable_rules or {}),
                    "monthly_preview_enabled": True,
                }
        finally:
            await engine.dispose()

    asyncio.run(_switch_on())
    first = asyncio.run(receivable_previews(settings, date(2031, 8, 1)))
    assert first["tenants"] >= 1
    assert first["runs"] >= 1
    second = asyncio.run(receivable_previews(settings, date(2031, 8, 1)))
    assert second["runs"] == 0
    assert second["skipped"] >= 1  # idempotent per month
