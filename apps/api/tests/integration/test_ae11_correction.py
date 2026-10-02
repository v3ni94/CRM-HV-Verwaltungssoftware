"""AE11 (P02, D09): new statement version after a resolution change or court invalidity, with a
correction report per owner and the heating bridge as its own block. Display only.

Expected values by hand (rule 0.1.8), model object MEA 3.000 / 2.500, advances 2.800,00 each:
V1 costs 5.500,00 -> 3.000,00 / 2.500,00, result 200,00 / -300,00.
V2 adds a position of 500,00 by MEA: 500 * 3000 / 5500 = 272,73 and 500 * 2500 / 5500 = 227,27
(sum 500,00) -> 3.272,73 / 2.727,27, result 472,73 / -72,73, difference 272,73 / 227,27.
D09: paid 10.000,00, distributed 8.000,00, unexplained V1 -2.000,00; V2 with heating_accrual
-2.000,00 -> unexplained 0,00; difference of the unexplained rest +2.000,00."""

import asyncio
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_annex_d_hoa import H, _ok, _weg
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m24_hoa import _book_cost

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"ae11-{RUN}", name=f"AE11 Korrektur {RUN}"
        )
        b, _ = await services.provision_tenant(
            factory, slug=f"ae11b-{RUN}", name=f"AE11 Fremd {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role in (("ae11admin", "tenant_admin"), ("ae11reader", "read_only")):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
            )
        uid = await services.create_user(
            factory, email=world.email("ae11other"), display_name="other", password=PASSWORD
        )
        world.users["ae11other"] = uid
        await services.add_member(
            factory, tenant_id=b, user_id=uid, role_codes=["tenant_admin"], actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _statement(client: TestClient, h: dict[str, str], w: dict[str, Any]) -> dict[str, Any]:
    return _ok(
        client.post(
            f"{H}/statements",
            json={"ledger_id": w["ledger"], "year": 2025},
            headers=h,
        ),
        201,
    )


def _cost(client: TestClient, h: dict[str, str], w: dict[str, Any], sid: str, amount: str) -> None:
    _ok(
        client.post(
            f"{H}/statements/{sid}/costs",
            json={
                "label": f"Kosten {amount}",
                "amount": amount,
                "allocation_key_id": w["keys"]["MEA"],
                "basis": "Teilungserklärung, Verteilung nach MEA",
                "account_id": w["acc"]["041000"],
            },
            headers=h,
        ),
        201,
    )


def _calc(client: TestClient, h: dict[str, str], sid: str) -> dict[str, Any]:
    return _ok(client.post(f"{H}/statements/{sid}/calculate", headers=h))


def _enable(client: TestClient, h: dict[str, str]) -> None:
    _ok(client.put(f"{H}/correction-report-settings", json={"enabled": True}, headers=h))


def test_af08_switch_default_off(client: TestClient, world: World) -> None:
    """GAE-13: default off -> report 409; reader 403 on PUT; 422 on unknown fields; the other
    tenant keeps its own switch."""
    h = bearer(login(client, world, "ae11admin"))
    reader = bearer(login(client, world, "ae11reader"))
    other = bearer(login(client, world, "ae11other"))
    _ok(client.put(f"{H}/correction-report-settings", json={"enabled": False}, headers=h))
    assert _ok(client.get(f"{H}/correction-report-settings", headers=h))["enabled"] is False
    w = _weg(client, h, "819")
    v1 = _statement(client, h, w)
    _cost(client, h, w, v1["id"], "100.00")
    _calc(client, h, v1["id"])
    v2 = _ok(client.post(f"{H}/statements/{v1['id']}/new-version", headers=h), 201)
    _calc(client, h, v2["id"])
    url = f"{H}/statements/{v2['id']}/correction-report"
    assert client.get(url, params={"against": v1["id"]}, headers=h).status_code == 409
    put = f"{H}/correction-report-settings"
    assert client.put(put, json={"enabled": True}, headers=reader).status_code == 403
    assert client.put(put, json={"enabled": True, "x": 1}, headers=h).status_code == 422
    _enable(client, h)
    assert _ok(client.get(url, params={"against": v1["id"]}, headers=h))["new"]["version"] == 2
    assert _ok(client.get(put, headers=other))["enabled"] is False


def test_correction_report_per_owner_and_no_postings(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae11admin"))
    _enable(client, h)
    w = _weg(client, h, "811")
    v1 = _statement(client, h, w)
    _cost(client, h, w, v1["id"], "5500.00")
    _calc(client, h, v1["id"])
    v2 = _ok(
        client.post(
            f"{H}/statements/{v1['id']}/new-version",
            json={
                "reason": "resolution_changed",
                "basis": "Änderungsbeschluss laut Protokoll (Modellfall)",
            },
            headers=h,
        ),
        201,
    )
    assert (v2["version"], v2["supersedes_id"]) == (2, v1["id"])
    assert v2["correction_reason"] == "resolution_changed"
    _cost(client, h, w, v2["id"], "500.00")
    _calc(client, h, v2["id"])
    rep = _ok(
        client.get(
            f"{H}/statements/{v2['id']}/correction-report", params={"against": v1["id"]}, headers=h
        )
    )
    shares = sorted(
        (o["cost_share"]["old"], o["cost_share"]["new"], o["cost_share"]["difference"])
        for o in rep["owners"]
    )
    assert shares == [
        ("2500.00", "2727.27", "227.27"),
        ("3000.00", "3272.73", "272.73"),
    ]
    results = sorted((o["result"]["old"], o["result"]["new"]) for o in rep["owners"])
    assert results == [("-300.00", "-72.73"), ("200.00", "472.73")]
    assert Decimal(rep["sum_differences"]["cost_share"]) == Decimal("500.00")
    assert "Rechtsfolge" in rep["correction"]["legal_note"]
    assert rep["correction"]["reason"] == "resolution_changed"


def test_new_version_without_body_and_validation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae11admin"))
    _enable(client, h)
    w = _weg(client, h, "812")
    v1 = _statement(client, h, w)
    bad = client.post(
        f"{H}/statements/{v1['id']}/new-version", json={"reason": "invented"}, headers=h
    )
    assert bad.status_code == 422
    v2 = _ok(client.post(f"{H}/statements/{v1['id']}/new-version", headers=h), 201)
    assert v2["correction_reason"] is None
    unknown = client.get(
        f"{H}/statements/{v2['id']}/correction-report",
        params={"against": v1["id"], "x": "1"},
        headers=h,
    )
    assert unknown.status_code == 422
    # not calculated yet -> 409; same version -> 422
    not_calc = client.get(
        f"{H}/statements/{v2['id']}/correction-report", params={"against": v1["id"]}, headers=h
    )
    assert not_calc.status_code == 409
    same = client.get(
        f"{H}/statements/{v2['id']}/correction-report", params={"against": v2["id"]}, headers=h
    )
    assert same.status_code == 422


def test_authorization_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae11admin"))
    w = _weg(client, h, "813")
    v1 = _statement(client, h, w)
    reader = bearer(login(client, world, "ae11reader"))
    assert client.post(f"{H}/statements/{v1['id']}/new-version", headers=reader).status_code == 403
    other = bearer(login(client, world, "ae11other"))
    assert client.post(f"{H}/statements/{v1['id']}/new-version", headers=other).status_code == 404


def test_d09_heating_block_in_correction(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae11admin"))
    _enable(client, h)
    w = _weg(client, h, "814", cost="0.00")
    _book_cost(
        client, h, w["ledger"], w["acc"]["001200"], w["acc"]["041000"], "10000.00", "2025-02-10"
    )
    v1 = _statement(client, h, w)
    _cost(client, h, w, v1["id"], "8000.00")
    c1 = _calc(client, h, v1["id"])
    assert c1["snapshot"]["reconciliation"]["unexplained"] == "-2000.00"
    v2 = _ok(
        client.post(
            f"{H}/statements/{v1['id']}/new-version",
            json={"reason": "other", "basis": "Brennstoffbestand nachgetragen (Modellfall D09)"},
            headers=h,
        ),
        201,
    )
    _ok(
        client.put(
            f"{H}/statements/{v2['id']}/reconciliation-notes",
            json={
                "notes": [
                    {
                        "code": "heating_accrual",
                        "amount": "-2000.00",
                        "note": "Brennstoffbestand 31.12.2025, Zahlung 10.000,00 EUR, "
                        "Verbrauch 8.000,00 EUR (Modellfall D09).",
                    }
                ]
            },
            headers=h,
        )
    )
    _calc(client, h, v2["id"])
    rep = _ok(
        client.get(
            f"{H}/statements/{v2['id']}/correction-report", params={"against": v1["id"]}, headers=h
        )
    )
    heating = rep["heating"]
    assert heating["old"]["cash_outflows"] == heating["new"]["cash_outflows"] == "10000.00"
    assert heating["new"]["cost_distributed"] == "8000.00"
    assert (heating["old"]["unexplained"], heating["new"]["unexplained"]) == ("-2000.00", "0.00")
    assert heating["new"]["heating_accrual"] == "-2000.00"
    assert heating["difference"]["unexplained"] == "2000.00"
