"""M13-01 to M13-03 (7.5 Sollstellung): pro rata receivables, non monthly instalments and VAT
with the tenant rule switch (default off) behind release gate G1.

Expected values (precomputed, see tests/unit/test_m13_proration.py and docs/rules/M13-0x.md):
- tenancy from 15.03.2026 with 500,00 rent: calendar days 500 x 17 / 31 = 274,19; the same
  start with the contract rule 30/360: 500 x 16 / 30 = 266,67;
- amount change 500,00 until 15.03., 600,00 from 16.03.: 241,94 + 309,67 = 551,61 (rounding
  difference -0,01 on the last segment);
- quarterly schedule anchored 01.01.2026, 300,00 per month, in advance: 900,00 due 03.01.,
  nothing in February and March;
- commercial tenancy with VAT option, 1.000,00 net and 19 %: 190,00 tax, 1.190,00 gross,
  net on the revenue account, tax on the mapped tax account, debtor with the gross amount.

With the rules off every such item stays manual (existing behaviour, test_m13_receivables);
with the rules on but gate G1 closed the run can be previewed but not posted (403).
"""

import asyncio
import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m5_contracts import _party, _unit

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
T = "/api/v1/tenant/settings"


class OpenG1:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"rr-{RUN}", name=f"Regeln {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        uid = await services.create_user(
            factory, email=world.email("m13rules"), display_name="m13r", password=PASSWORD
        )
        world.users["m13rules"] = uid
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
def clients(database: Database, redis_url: str) -> Iterator[tuple[TestClient, TestClient]]:
    settings = _settings(database, redis_url)
    with (
        TestClient(create_app(settings)) as closed,
        TestClient(create_app(settings, release_gate_resolver=OpenG1())) as open_,
    ):
        yield closed, open_


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _rules(c: TestClient, h: dict[str, str], **rules: Any) -> None:
    body = {
        "enabled": True,
        "proration_method": "calendar_days",
        "vat_enabled": False,
        "payment_interval": None,
        "monthly_preview_enabled": False,
        **rules,
    }
    out = _ok(c.patch(T, json={"receivable_rules": body}, headers=h))
    assert out["receivable_rules"] == body


def _rental(c: TestClient, h: dict[str, str], number: str) -> tuple[dict[str, Any], str]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"Miethaus {number}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    owner, _ = _party(c, h, f"Vermieter{number}", "company")
    entity = _ok(
        c.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )["legal_entity_id"]
    return prop, str(entity)


def _tenancy(
    c: TestClient,
    h: dict[str, str],
    prop: str,
    unit_no: str,
    start: str,
    payments: list[tuple[str, str, str, str | None]],
    *,
    schedule: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    unit = _unit(c, h, prop, unit_no)
    party, _ = _party(c, h, f"M{unit_no}")
    contract = _ok(
        c.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party,
                "start_date": start,
                **extra,
            },
            headers=h,
        ),
        201,
    )
    for net, vat, valid_from, valid_to in payments:
        gross = str(Decimal(net) * (1 + Decimal(vat) / 100))
        _ok(
            c.post(
                f"/api/v1/contracts/{contract['id']}/payments",
                json={
                    "payment_type_code": "rent",
                    "net": net,
                    "vat_percent": vat,
                    "gross": gross,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                },
                headers=h,
            ),
            201,
        )
    _ok(
        c.post(
            f"/api/v1/contracts/{contract['id']}/schedules",
            json={"valid_from": start, "due_day": 3, **(schedule or {})},
            headers=h,
        ),
        201,
    )
    return contract  # type: ignore[no-any-return]


def _ledger(c: TestClient, h: dict[str, str], entity: str) -> tuple[str, dict[str, str]]:
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers",
            json={"legal_entity_id": entity, "template_id": template["id"]},
            headers=h,
        ),
        201,
    )["id"]
    acc = {a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    _ok(
        c.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "rent", "account_id": acc["060300"]},
            headers=h,
        )
    )
    return str(ledger), acc


def _run(c: TestClient, h: dict[str, str], month: str, scope: str, scope_id: str) -> Any:
    return _ok(
        c.post(
            f"{A}/receivable-runs",
            json={"period_month": month, "scope": scope, "scope_id": scope_id},
            headers=h,
        ),
        201,
    )


def _balances(c: TestClient, h: dict[str, str], ledger: str, as_of: str) -> dict[str, str]:
    tb = _ok(c.get(f"{A}/ledgers/{ledger}/trial-balance", params={"as_of": as_of}, headers=h))
    return {a["number"]: a["balance"] for a in tb["accounts"] if Decimal(a["balance"]) != 0}


def test_m13_01_proration_per_contract_rule_and_gate(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    closed, open_ = clients
    h = bearer(login(closed, world, "m13rules"))
    assert _ok(closed.get(T, headers=h))["receivable_rules"] == {
        "enabled": False,
        "proration_method": "calendar_days",
        "vat_enabled": False,
        "payment_interval": None,
        "monthly_preview_enabled": False,  # P02-03
    }
    prop, entity = _rental(closed, h, "741")
    start = _tenancy(
        closed, h, prop["id"], "01", "2026-03-15", [("500.00", "0", "2026-03-15", None)]
    )
    t360 = _tenancy(
        closed,
        h,
        prop["id"],
        "02",
        "2026-03-15",
        [("500.00", "0", "2026-03-15", None)],
        proration_method="thirty_360",
    )
    assert t360["proration_method"] == "thirty_360"
    assert start["proration_method"] is None
    change = _tenancy(
        closed,
        h,
        prop["id"],
        "03",
        "2026-01-01",
        [("500.00", "0", "2026-01-01", "2026-03-15"), ("600.00", "0", "2026-03-16", None)],
    )
    ledger, _ = _ledger(closed, h, entity)

    # Rules off (default): every partial month stays manual, nothing is computed (7.5).
    before = _run(closed, h, "2026-03-01", "property", prop["id"])
    assert {i["status"] for i in before["items"]} == {"manual"}
    assert before["calculation"]["rules"]["enabled"] is False
    assert all(i["net_amount"] is None for i in before["items"])

    _rules(closed, h)
    run = _run(closed, h, "2026-03-01", "property", prop["id"])
    assert run["calculation"]["rules"]["enabled"] is True
    by_id = {i["contract_id"]: i for i in run["items"]}
    assert len(by_id) == 3
    a = by_id[start["id"]]
    assert (a["status"], a["amount"], a["net_amount"], a["vat_amount"]) == (
        "ready",
        "274.19",
        "274.19",
        "0.00",
    )
    assert (a["period_start"], a["period_end"], a["due_date"]) == (
        "2026-03-15",
        "2026-03-31",
        "2026-03-03",
    )
    assert by_id[t360["id"]]["amount"] == "266.67"
    c = by_id[change["id"]]
    assert (c["status"], c["amount"], c["period_start"], c["period_end"]) == (
        "ready",
        "551.61",
        "2026-03-01",
        "2026-03-31",
    )
    assert run["totals"]["ready"] == {"count": 3, "amount": "1092.47"}
    # Calculation path on the run: segments, fractions and the rounding difference.
    paths = {p["contract_number"]: p for p in run["calculation"]["items"]}
    seg = paths[start["number"]]["month"]["segments"]
    assert [s["days"] for s in seg] == [17]
    assert seg[0]["fraction"] == "0.54838710"
    assert seg[0]["exact"] == "274.19354839"
    assert paths[t360["number"]]["proration_method"] == "thirty_360"
    assert paths[t360["number"]]["month"]["segments"][0]["base_days"] == 30
    changed = paths[change["number"]]["month"]
    assert [s["rounded"] for s in changed["segments"]] == ["241.94", "309.67"]
    assert changed["segments"][1]["adjustment"] == "-0.01"
    assert changed["exact_total"] == "551.61290322"

    # Draft behind G1: computed items cannot be posted while the gate is closed.
    assert closed.post(f"{A}/receivable-runs/{run['id']}/post", headers=h).status_code == 403
    assert _ok(closed.get(f"{A}/receivable-runs/{run['id']}", headers=h))["status"] == "preview"
    posted = _ok(open_.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    assert posted["status"] == "posted"
    assert {i["status"] for i in posted["items"]} == {"posted"}
    items = _ok(
        closed.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-03-31"}, headers=h)
    )
    assert sorted(i["remaining"] for i in items) == ["266.67", "274.19", "551.61"]
    assert _balances(closed, h, ledger, "2026-03-31")["060300"] in ("-1092.47", "1092.47")
    assert _ok(closed.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True

    # April: full months again, the change contract carries 600,00 (B08: March not repeated).
    april = _run(closed, h, "2026-04-01", "contract", change["id"])
    assert [(i["amount"], i["status"]) for i in april["items"]] == [("600.00", "ready")]
    assert april["calculation"]["items"][0]["month"]["full_month"] is True


def test_m13_01a_schedule_takes_over_tenant_default_payment_interval(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    """M13-01a: ein Zahlungsplan ohne eigene ``interval``-Angabe übernimmt den Mandanten-
    Standard aus ``receivable_rules.payment_interval``; ohne Mandantenvorgabe bleibt es
    monatlich (bisheriges Verhalten)."""
    closed, _ = clients
    h = bearer(login(closed, world, "m13rules"))
    _rules(closed, h, enabled=False, payment_interval=None)
    prop, _ = _rental(closed, h, "744")
    no_default = _tenancy(
        closed, h, prop["id"], "01", "2026-01-01", [("300.00", "0", "2026-01-01", None)]
    )
    [plan] = _ok(closed.get(f"/api/v1/contracts/{no_default['id']}", headers=h))["schedules"]
    assert plan["interval"] == "monthly"

    _rules(closed, h, enabled=False, payment_interval="quarterly")
    with_default = _tenancy(
        closed, h, prop["id"], "02", "2026-01-01", [("300.00", "0", "2026-01-01", None)]
    )
    [plan2] = _ok(closed.get(f"/api/v1/contracts/{with_default['id']}", headers=h))["schedules"]
    assert plan2["interval"] == "quarterly"

    # An explicit interval on the schedule always wins over the tenant default.
    explicit = _tenancy(
        closed,
        h,
        prop["id"],
        "03",
        "2026-01-01",
        [("300.00", "0", "2026-01-01", None)],
        schedule={"interval": "annual"},
    )
    [plan3] = _ok(closed.get(f"/api/v1/contracts/{explicit['id']}", headers=h))["schedules"]
    assert plan3["interval"] == "annual"
    _rules(closed, h, enabled=False, payment_interval=None)


def test_m13_02_quarterly_instalment_in_advance(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    closed, _ = clients
    h = bearer(login(closed, world, "m13rules"))
    _rules(closed, h)
    prop, entity = _rental(closed, h, "742")
    quarterly = _tenancy(
        closed,
        h,
        prop["id"],
        "01",
        "2026-01-01",
        [("300.00", "0", "2026-01-01", None)],
        schedule={"interval": "quarterly", "payment_mode": "advance", "amount_basis": "per_month"},
    )
    [plan] = _ok(closed.get(f"/api/v1/contracts/{quarterly['id']}", headers=h))["schedules"]
    assert (plan["interval"], plan["payment_mode"], plan["amount_basis"]) == (
        "quarterly",
        "advance",
        "per_month",
    )
    _ledger(closed, h, entity)

    jan = _run(closed, h, "2026-01-01", "contract", quarterly["id"])
    [item] = jan["items"]
    assert (item["status"], item["amount"], item["due_date"]) == ("ready", "900.00", "2026-01-03")
    assert (item["period_start"], item["period_end"]) == ("2026-01-01", "2026-03-31")
    path = jan["calculation"]["items"][0]["instalment"]
    assert path["payment_mode"] == "advance"
    assert [m["total"] for m in path["months"]] == ["300.00", "300.00", "300.00"]
    for month in ("2026-02-01", "2026-03-01"):
        assert _run(closed, h, month, "contract", quarterly["id"])["items"] == []
    assert _run(closed, h, "2026-04-01", "contract", quarterly["id"])["items"][0]["amount"] == (
        "900.00"
    )

    # Rules off: the non monthly interval is a manual item again.
    _rules(closed, h, enabled=False)
    off = _run(closed, h, "2026-01-01", "contract", quarterly["id"])
    assert off["items"][0]["status"] == "manual"
    assert "Nicht monatliches Intervall" in off["items"][0]["message"]


def test_m13_03_vat_on_commercial_tenancy(
    clients: tuple[TestClient, TestClient], world: World, database: Database, redis_url: str
) -> None:
    from tests.integration.test_m14_invoices import _set_vat_option

    closed, open_ = clients
    h = bearer(login(closed, world, "m13rules"))
    _rules(closed, h, vat_enabled=False)
    prop, entity = _rental(closed, h, "743")
    shop = _tenancy(
        closed,
        h,
        prop["id"],
        "01",
        "2020-01-01",
        [("1000.00", "19", "2020-01-01", None)],
        vat_option="commercial_full_vat",
    )
    no_option = _tenancy(
        closed, h, prop["id"], "02", "2020-01-01", [("100.00", "19", "2020-01-01", None)]
    )
    ledger, acc = _ledger(closed, h, entity)

    def item(contract: dict[str, Any]) -> Any:
        return _run(closed, h, "2026-06-01", "contract", contract["id"])["items"][0]

    # VAT rule not released: manual with the VAT reason (D45 stays valid).
    first = item(shop)
    assert first["status"] == "manual"
    assert "Umsatzsteuer" in first["message"]
    assert "nicht freigegeben" in first["message"]
    # Tax rate without an option on the contract is never posted by rule.
    _rules(closed, h, vat_enabled=True)
    assert item(no_option)["status"] == "manual"
    assert "ohne Umsatzsteueroption am Vertrag" in item(no_option)["message"]
    # Ledger without VAT option, then without tax account: blocked, not computed away.
    blocked = item(shop)
    assert (blocked["status"], blocked["message"]) == (
        "blocked",
        "Buchungskreis ohne Umsatzsteueroption",
    )
    asyncio.run(_set_vat_option(_settings(database, redis_url), world.tenant_a, ledger))
    assert "vat_output" in item(shop)["message"]
    tax = _ok(
        closed.post(
            f"{A}/ledgers/{ledger}/accounts",
            json={
                "number": "017600",
                "name": "Umsatzsteuer Sollstellung",
                "category": "tax",
                "type": "liability",
            },
            headers=h,
        ),
        201,
    )
    wrong = closed.put(
        f"{A}/ledgers/{ledger}/payment-type-accounts",
        json={"payment_type_code": "vat_output", "account_id": acc["060300"]},
        headers=h,
    )
    assert wrong.status_code == 422  # tax must go to a tax account
    _ok(
        closed.put(
            f"{A}/ledgers/{ledger}/payment-type-accounts",
            json={"payment_type_code": "vat_output", "account_id": tax["id"]},
            headers=h,
        )
    )
    run = _run(closed, h, "2026-06-01", "contract", shop["id"])
    [ready] = run["items"]
    assert (ready["status"], ready["net_amount"]) == ("ready", "1000.00")
    assert Decimal(ready["vat_percent"]) == Decimal("19")
    assert (ready["vat_amount"], ready["amount"]) == ("190.00", "1190.00")
    vat = run["calculation"]["items"][0]["vat"]
    assert (vat["net"], vat["vat"], vat["gross"]) == ("1000.00", "190.00", "1190.00")
    assert Decimal(vat["vat_percent"]) == Decimal("19")
    assert closed.post(f"{A}/receivable-runs/{run['id']}/post", headers=h).status_code == 403
    posted = _ok(open_.post(f"{A}/receivable-runs/{run['id']}/post", headers=h))
    assert posted["items"][0]["status"] == "posted"
    balances = _balances(closed, h, ledger, "2026-06-30")
    assert Decimal(balances["060300"]).copy_abs() == Decimal("1000.00")
    assert Decimal(balances["017600"]).copy_abs() == Decimal("190.00")
    items = _ok(
        closed.get(f"{A}/ledgers/{ledger}/open-items", params={"as_of": "2026-06-30"}, headers=h)
    )
    assert [i["remaining"] for i in items] == ["1190.00"]
    assert _ok(closed.get(f"{A}/ledgers/{ledger}/checks", headers=h))["ok"] is True
    _rules(closed, h, enabled=False)
