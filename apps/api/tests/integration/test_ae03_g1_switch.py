"""AE03: G1 checklist with responsible person and evidence, comparison report and the four eyes
automation switch (M12-09, BK2-03). Own world with prefix ae03."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.banking.automation_switch import outcome_of
from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
G1 = "/api/v1/accounting/g1-opening"
B = "/api/v1/banking/automation"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae03a-{RUN}", name=f"AE03 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae03b-{RUN}", name=f"AE03 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae03admin", a, "tenant_admin"),
            ("ae03second", a, "tenant_admin"),
            ("ae03reader", a, "read_only"),
            ("ae03other", b, "tenant_admin"),
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


class _OpenG1:
    async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
        return gate is ReleaseGate.G1


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_outcome_classification() -> None:
    assert outcome_of("accepted_unchanged", 0, [{}]) == "match"
    assert outcome_of("accepted_unchanged", 2, [{}, {}, {}]) == "other_proposal"
    assert outcome_of("modified", 0, [{}]) == "modified"
    assert outcome_of("accepted_unchanged", None, []) == "no_proposal"
    assert outcome_of("rejected", None, [{}]) == "rejected"
    assert outcome_of("auto_posted", 0, [{}]) == "auto_posted"
    assert outcome_of("reversed", 0, [{}]) == "reversed"
    for skipped in ("pending", "ignored", "expired"):
        assert outcome_of(skipped, 0, [{}]) is None


def test_checklist_responsible_and_evidence(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae03admin"))
    body = {
        "status": "passed",
        "confirmed_on": "2026-10-01",
        "confirmed_by_name": "AE03 Prüfer",
        "responsible_user_id": str(world.users["ae03second"]),
    }
    item = _ok(client.put(f"{G1}/items/vat_review", json=body, headers=h))
    assert item["responsible_user_id"] == str(world.users["ae03second"])
    assert item["evidence_missing"] is True
    item = _ok(
        client.put(
            f"{G1}/items/vat_review",
            json=body | {"evidence_ref": "docs/acceptance/kontenrahmen-pruefung.md"},
            headers=h,
        )
    )
    assert item["evidence_missing"] is False
    state = _ok(client.get(G1, headers=h))
    assert state["gate_checklist_ref"].startswith("docs/plans/GATE-CHECKLISTEN.md")
    vat = next(m for m in state["manual"] if m["item_key"] == "vat_review")
    assert vat["evidence_ref"] == "docs/acceptance/kontenrahmen-pruefung.md"
    assert state["items_without_responsible"] == state["cases_total"] + state["manual_total"] - 1
    # responsible person of another tenant: 422; unknown document: 404; unknown field: 422
    foreign = body | {"responsible_user_id": str(world.users["ae03other"])}
    assert client.put(f"{G1}/items/vat_review", json=foreign, headers=h).status_code == 422
    nodoc = body | {"evidence_document_id": str(uuid.uuid4())}
    assert client.put(f"{G1}/items/vat_review", json=nodoc, headers=h).status_code == 404
    assert client.put(f"{G1}/items/vat_review", json=body | {"x": 1}, headers=h).status_code == 422
    # reader 403; other tenant sees its own (empty) state
    r = bearer(login(client, world, "ae03reader"))
    assert client.put(f"{G1}/items/vat_review", json=body, headers=r).status_code == 403
    o = bearer(login(client, world, "ae03other"))
    other = _ok(client.get(G1, headers=o))
    assert next(m for m in other["manual"] if m["item_key"] == "vat_review")["status"] == "open"


def test_comparison_report_read_only(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae03admin"))
    rep = _ok(client.get(f"{B}/comparison?date_from=2026-01-01&date_to=2026-12-31", headers=h))
    assert rep["totals"] == dict.fromkeys(rep["outcomes"], 0)
    assert rep["match_rate"] is None
    assert rep["rows"] == []
    assert client.get(f"{B}/comparison?foo=1", headers=h).status_code == 422
    bad = client.get(f"{B}/comparison?date_from=2026-02-01&date_to=2026-01-01", headers=h)
    assert bad.status_code == 422
    r = bearer(login(client, world, "ae03reader"))
    assert client.get(f"{B}/comparison", headers=r).status_code == 200


def test_switch_needs_g1(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae03admin"))
    state = _ok(client.get(f"{B}/switch-requests", headers=h))
    assert state["g1_open"] is False
    assert state["can_request"] is False
    res = client.post(f"{B}/switch-requests", json={"reason": "AE03 Test"}, headers=h)
    assert res.status_code == 403
    assert res.json()["code"] == "MHVP-GATE-0001"


def test_put_never_switches_on(client: TestClient, world: World) -> None:
    """AF01 (GAA-01): PUT only switches off; switching on returns 409 with the request path."""
    h = bearer(login(client, world, "ae03admin"))
    res = client.put(B, json={"enabled": True, "reason": "AF01 direkt"}, headers=h)
    assert res.status_code == 409
    assert res.json()["code"] == "MHVP-BANK-0063"
    assert _ok(client.get(f"{B}/switch-requests", headers=h))["enabled"] is False
    assert client.put(B, json={"enabled": True}, headers=h).status_code == 422
    r = bearer(login(client, world, "ae03reader"))
    assert client.put(B, json={"enabled": False, "reason": "AF01"}, headers=r).status_code == 403
    assert _ok(client.put(B, json={"enabled": False, "reason": "AF01 aus"}, headers=h)) == {
        "enabled": False
    }


def test_put_on_blocked_even_with_g1_open(database: Database, redis_url: str, world: World) -> None:
    with TestClient(
        create_app(_settings(database, redis_url), release_gate_resolver=_OpenG1())
    ) as c:
        h = bearer(login(c, world, "ae03admin"))
        res = c.put(B, json={"enabled": True, "reason": "AF01 direkt"}, headers=h)
        assert res.status_code == 409
        assert res.json()["code"] == "MHVP-BANK-0063"


def test_switch_four_eyes_with_g1_open(database: Database, redis_url: str, world: World) -> None:
    with TestClient(
        create_app(_settings(database, redis_url), release_gate_resolver=_OpenG1())
    ) as c:
        h = bearer(login(c, world, "ae03admin"))
        s = bearer(login(c, world, "ae03second"))
        r = bearer(login(c, world, "ae03reader"))
        o = bearer(login(c, world, "ae03other"))
        assert c.post(f"{B}/switch-requests", json={"reason": "x"}, headers=h).status_code == 422
        assert c.post(f"{B}/switch-requests", json={"reason": "AE03"}, headers=r).status_code == 403
        req = _ok(c.post(f"{B}/switch-requests", json={"reason": "AE03 Antrag"}, headers=h), 201)
        dup = c.post(f"{B}/switch-requests", json={"reason": "AE03 zweiter"}, headers=h)
        assert dup.status_code == 409
        url = f"{B}/switch-requests/{req['id']}"
        own = c.post(f"{url}/approve", json={}, headers=h)
        assert own.status_code == 403
        assert own.json()["code"] == "MHVP-GATE-0002"
        assert c.post(f"{url}/approve", json={}, headers=o).status_code == 404
        assert c.post(f"{url}/other", json={}, headers=s).status_code == 404
        try:
            done = _ok(c.post(f"{url}/approve", json={"comment": "ok"}, headers=s))
            assert done["status"] == "approved"
            assert _ok(c.get(f"{B}/switch-requests", headers=h))["enabled"] is True
            assert _ok(c.get(f"{B}/levels", headers=h))["auto_posting_enabled"] is True
            assert c.post(f"{url}/reject", json={}, headers=s).status_code == 409
        finally:
            _ok(c.put(B, json={"enabled": False, "reason": "AE03 Ende"}, headers=h))
        assert _ok(c.get(f"{B}/switch-requests", headers=o))["items"] == []


def test_outgoing_put_never_switches_on(client: TestClient, world: World) -> None:
    """AG19 (AF25-01): PUT outgoing only switches off; on returns 409 MHVP-BANK-0064."""
    h = bearer(login(client, world, "ae03admin"))
    res = client.put(f"{B}/outgoing", json={"enabled": True, "reason": "AG19 direkt"}, headers=h)
    assert res.status_code == 409
    assert res.json()["code"] == "MHVP-BANK-0064"
    assert _ok(client.get(f"{B}/switch-requests", headers=h))["outgoing_enabled"] is False
    r = bearer(login(client, world, "ae03reader"))
    off = {"enabled": False, "reason": "AG19 aus"}
    assert client.put(f"{B}/outgoing", json=off, headers=r).status_code == 403
    assert _ok(client.put(f"{B}/outgoing", json=off, headers=h)) == {"enabled": False}
    body = {"reason": "AG19 Test", "target": "outgoing"}
    closed = client.post(f"{B}/switch-requests", json=body, headers=h)
    assert closed.status_code == 403
    assert closed.json()["code"] == "MHVP-GATE-0001"
    bad = {"reason": "AG19 Test", "target": "other"}
    assert client.post(f"{B}/switch-requests", json=bad, headers=h).status_code == 422


def test_outgoing_four_eyes_with_g1_open(database: Database, redis_url: str, world: World) -> None:
    with TestClient(
        create_app(_settings(database, redis_url), release_gate_resolver=_OpenG1())
    ) as c:
        h = bearer(login(c, world, "ae03admin"))
        s = bearer(login(c, world, "ae03second"))
        o = bearer(login(c, world, "ae03other"))
        body = {"reason": "AG19 Antrag", "target": "outgoing"}
        req = _ok(c.post(f"{B}/switch-requests", json=body, headers=h), 201)
        assert req["target"] == "outgoing"
        assert c.post(f"{B}/switch-requests", json=body, headers=h).status_code == 409
        state = _ok(c.get(f"{B}/switch-requests", headers=h))
        assert state["can_request_outgoing"] is False
        assert state["can_request"] is True  # the main target has no open request
        url = f"{B}/switch-requests/{req['id']}"
        own = c.post(f"{url}/approve", json={}, headers=h)
        assert own.status_code == 403
        assert own.json()["code"] == "MHVP-GATE-0002"
        assert c.post(f"{url}/approve", json={}, headers=o).status_code == 404
        try:
            done = _ok(c.post(f"{url}/approve", json={"comment": "ok"}, headers=s))
            assert done["status"] == "approved"
            after = _ok(c.get(f"{B}/switch-requests", headers=h))
            assert after["outgoing_enabled"] is True
            assert after["enabled"] is False  # the main switch stays untouched
            assert _ok(c.get(f"{B}/levels", headers=h))["auto_posting_outgoing_enabled"] is True
        finally:
            off = {"enabled": False, "reason": "AG19 Ende"}
            _ok(c.put(f"{B}/outgoing", json=off, headers=h))
        assert _ok(c.get(f"{B}/switch-requests", headers=h))["outgoing_enabled"] is False
