"""AE17 / M17-01: allocation agreements per tenancy and cost position, report before output.

Expected by hand: one tenancy (2024-01-01 open end), statement 2025. Cost item "Hausmeister"
on an account with catalogue type X. Without agreement: 1 blocking row (missing). Agreement
valid from 2025-01-01 covers the whole year: complete. Agreement valid from 2025-07-01 covers
only half: blocking (expired). Excluded agreement: not blocking."""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mhvp.billing import betrkv
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m17_betrkv_advance_proposals import _post_costs
from tests.integration.test_m17_operating_costs import (
    S,
    _account,
    _ok,
    _rental_world,
    _statement,
)

pytestmark = pytest.mark.integration
CODE = betrkv.catalogue()[0]["code"]


class OpenG3:
    async def is_open(self, tenant_id: UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G3


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae17a-{RUN}", name=f"AE17 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae17b-{RUN}", name=f"AE17 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae17admin", a, "tenant_admin"),
            ("ae17other", b, "tenant_admin"),
            ("ae17read", a, "read_only"),
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


def _agreement(**extra: Any) -> dict[str, Any]:
    return {
        "operating_cost_type": CODE,
        "clause_reference": "§ 4 Mietvertrag",
        "valid_from": "2024-01-01",
        **extra,
    }


def _statement_with_item(client: TestClient, h: dict[str, str], w: dict[str, Any]) -> str:
    account = _account(
        client, h, w["ledger"], "042000", "Hausmeister", allocation_category="allocable_other"
    )
    _ok(
        client.put(
            f"/api/v1/billing/operating-cost-types/accounts/{account}",
            json={"operating_cost_type": CODE},
            headers=h,
        )
    )
    _post_costs(client, h, w["ledger"], [{"account_id": account, "debit": "100.00"}])
    st = _statement(client, h, w["ledger"])
    _ok(
        client.post(
            f"{S}/{st['id']}/cost-items",
            json={
                "label": "Hausmeister",
                "amount": "100.00",
                "account_id": account,
                "allocation_key_id": w["keys"]["WFL"],
                "basis": "§ 4 Mietvertrag",
            },
            headers=h,
        ),
        201,
    )
    return str(st["id"])


def test_crud_validation_and_separation(
    clients: tuple[TestClient, TestClient], world: World
) -> None:
    client, _ = clients
    h = bearer(login(client, world, "ae17admin"))
    w = _rental_world(client, h, "861")
    url = f"/api/v1/contracts/{w['contract']['id']}/allocation-agreements"
    row = _ok(client.post(url, json=_agreement(), headers=h), 201)
    assert row["clause_reference"] == "§ 4 Mietvertrag"
    assert client.post(url, json=_agreement(valid_from="2025-01-01"), headers=h).status_code == 409
    # missing clause for an agreed position, unknown type, wrong period: 422
    for bad in (
        {**_agreement(), "clause_reference": None},
        _agreement(operating_cost_type="unbekannt"),
        _agreement(valid_to="2023-01-01"),
    ):
        assert client.post(url, json=bad, headers=h).status_code == 422
    assert client.get(f"{url}?foo=1", headers=h).status_code == 422
    patched = _ok(client.patch(f"{url}/{row['id']}", json={"valid_to": "2024-12-31"}, headers=h))
    assert patched["valid_to"] == "2024-12-31"
    assert len(_ok(client.get(url, headers=h))["items"]) == 1
    # read only role: 403; other tenant: 404
    ro = bearer(login(client, world, "ae17read"))
    assert client.post(url, json=_agreement(valid_from="2026-01-01"), headers=ro).status_code == 403
    other = bearer(login(client, world, "ae17other"))
    assert client.get(url, headers=other).status_code == 404
    assert client.delete(f"{url}/{row['id']}", headers=h).status_code == 204


def test_bulk_dry_run_and_skip(clients: tuple[TestClient, TestClient], world: World) -> None:
    client, _ = clients
    h = bearer(login(client, world, "ae17admin"))
    w = _rental_world(client, h, "862")
    bulk = f"/api/v1/properties/{w['property']}/allocation-agreements/bulk"
    body = {
        "items": [{"operating_cost_type": CODE, "clause_reference": "§ 5"}],
        "valid_from": "2024-01-01",
    }
    preview = _ok(client.post(bulk, json=body, headers=h))
    assert (preview["dry_run"], preview["created"], preview["skipped"]) == (True, 1, 0)
    url = f"/api/v1/contracts/{w['contract']['id']}/allocation-agreements"
    assert _ok(client.get(url, headers=h))["items"] == []
    done = _ok(client.post(bulk, json={**body, "dry_run": False}, headers=h))
    assert (done["created"], done["skipped"]) == (1, 0)
    again = _ok(client.post(bulk, json={**body, "dry_run": False}, headers=h))
    assert (again["created"], again["skipped"]) == (0, 1)
    assert len(_ok(client.get(url, headers=h))["items"]) == 1


def test_report_and_block(clients: tuple[TestClient, TestClient], world: World) -> None:
    closed, open_ = clients
    h = bearer(login(closed, world, "ae17admin"))
    w = _rental_world(closed, h, "863")
    st = _statement_with_item(closed, h, w)
    report = f"{S}/{st}/allocation-basis-report"
    first = _ok(closed.get(report, headers=h))
    assert (first["complete"], first["missing_count"]) == (False, 1)
    assert first["rows"][0]["state"] == "missing"
    # blocked: issue transition and info sheet (G3 open)
    _ok(open_.post(f"{S}/{st}/calculate", headers=h))
    ho = bearer(login(open_, world, "ae17admin"))
    blocked = open_.post(f"{S}/{st}/info-sheet", headers=ho)
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "MHVP-BILL-0015"
    t = open_.post(f"{S}/{st}/transition", json={"target": "issued"}, headers=ho)
    assert t.status_code == 409
    assert t.json()["code"] == "MHVP-BILL-0015"
    # partially covering agreement still blocks
    url = f"/api/v1/contracts/{w['contract']['id']}/allocation-agreements"
    row = _ok(closed.post(url, json=_agreement(valid_from="2025-07-01"), headers=h), 201)
    assert _ok(closed.get(report, headers=h))["rows"][0]["state"] == "expired"
    # full coverage completes
    _ok(closed.patch(f"{url}/{row['id']}", json={"valid_from": "2025-01-01"}, headers=h))
    assert _ok(closed.get(report, headers=h))["complete"] is True
    # excluded does not block
    _ok(closed.patch(f"{url}/{row['id']}", json={"status": "excluded"}, headers=h))
    assert _ok(closed.get(report, headers=h))["rows"][0]["state"] == "excluded"
    # switch off: missing basis no longer blocks (set missing again by deleting is blocked
    # after calculation only by an issued statement, here the statement is still calculated)
    # a statement past draft keeps its agreements: delete is refused, the period is moved instead
    assert closed.delete(f"{url}/{row['id']}", headers=h).status_code == 409
    _ok(closed.patch(f"{url}/{row['id']}", json={"valid_from": "2026-01-01"}, headers=h))
    assert _ok(closed.get(report, headers=h))["rows"][0]["state"] == "missing"
    setting = "/api/v1/billing/allocation-basis-setting"
    assert _ok(closed.get(setting, headers=h)) == {"block_output": True}
    _ok(closed.put(setting, json={"block_output": False}, headers=h))
    assert _ok(closed.get(report, headers=h))["blocking_enabled"] is False
    filed = open_.post(f"{S}/{st}/info-sheet", headers=ho)
    # no block any more; the object storage is not part of this test (503 without it)
    assert filed.status_code in (201, 503), filed.text
    _ok(closed.put(setting, json={"block_output": True}, headers=h))
