"""AG02 / GAC-05: leading system per ledger, property, process kind and valid-from date.
Own world with prefix ag02 (second person, G1 for the platform, RLS, rights, validation)."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.core.release_gates import ReleaseGate
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ag02a-{RUN}", name=f"AG02 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ag02b-{RUN}", name=f"AG02 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ag02admin", a, "tenant_admin"),
            ("ag02second", a, "tenant_admin"),
            ("ag02reader", a, "read_only"),
            ("ag02other", b, "tenant_admin"),
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


@pytest.fixture
def g1_client(database: Database, redis_url: str) -> Iterator[TestClient]:
    app = create_app(_settings(database, redis_url), release_gate_resolver=_OpenG1())
    with TestClient(app) as c:
        yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _ledger(c: TestClient, h: dict[str, str], number: str) -> tuple[str, str]:
    body = {"number": number, "name": f"AG02 Haus {number}", "management_type": "hoa"}
    prop = _ok(c.post("/api/v1/properties", json=body, headers=h), 201)
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    ledger = _ok(c.post(f"{A}/ledgers", json={"legal_entity_id": hoa}, headers=h), 201)
    return ledger["id"], prop["id"]


def _effective(c: TestClient, h: dict[str, str], ledger: str) -> dict[str, tuple[str, str]]:
    data = _ok(c.get(f"{A}/ledgers/{ledger}/leading-switches", headers=h))
    return {e["kind"]: (e["leading_system"], e["source"]) for e in data["effective"]}


def test_switch_four_eyes_g1_rls_and_validation(
    client: TestClient, g1_client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ag02admin"))
    ledger, prop = _ledger(client, h, "921")
    path = f"{A}/ledgers/{ledger}/leading-switches"
    # without rows: ledger flag for every kind (behaviour unchanged)
    eff = _effective(client, h, ledger)
    assert set(eff) == {"receivable_posting", "dunning", "direct_debit", "payment_order"}
    assert all(v == ("immoware24", "ledger") for v in eff.values())

    body = {"kind": "dunning", "leading_system": "mhvp", "valid_from": "2026-01-01"}
    # validation 422: unknown kind, unknown field, unknown query parameter
    assert client.post(path, json=body | {"kind": "x"}, headers=h).status_code == 422
    assert client.post(path, json=body | {"foo": 1}, headers=h).status_code == 422
    assert client.get(f"{path}?foo=1", headers=h).status_code == 422
    # unknown property: 404
    unknown = body | {"property_id": str(uuid.uuid4())}
    assert client.post(path, json=unknown, headers=h).status_code == 404
    # reader 403; other tenant 404
    r = bearer(login(client, world, "ag02reader"))
    assert client.post(path, json=body, headers=r).status_code == 403
    assert client.get(path, headers=r).status_code == 200
    o = bearer(login(client, world, "ag02other"))
    assert client.get(path, headers=o).status_code == 404
    assert client.post(path, json=body, headers=o).status_code == 404

    row = _ok(client.post(path, json=body | {"property_id": prop}, headers=h), 201)
    assert row["status"] == "requested"
    decide = f"{path}/{row['id']}/decide"
    # requested only: still the ledger flag
    assert _effective(client, h, ledger)["dunning"] == ("immoware24", "ledger")
    # same person 403 (four eyes), even with G1 open
    gh = bearer(login(g1_client, world, "ag02admin"))
    assert g1_client.post(decide, json={"approve": True}, headers=gh).status_code == 403
    # second person with G1 closed: 403 (the platform as leading system posts)
    s = bearer(login(client, world, "ag02second"))
    assert client.post(decide, json={"approve": True}, headers=s).status_code == 403
    assert client.post(decide, json={"approve": True}, headers=o).status_code == 404
    assert client.post(decide, json={"approve": True}, headers=r).status_code == 403
    # property row does not change the ledger wide view
    gs = bearer(login(g1_client, world, "ag02second"))
    done = _ok(g1_client.post(decide, json={"approve": True, "comment": "ok"}, headers=gs))
    assert done["status"] == "approved"
    assert done["decided_by"] == str(world.users["ag02second"])
    assert g1_client.post(decide, json={"approve": True}, headers=gs).status_code == 409
    assert _effective(client, h, ledger)["dunning"] == ("immoware24", "ledger")

    # ledger wide switch: approved with G1, effective from its date
    row = _ok(client.post(path, json=body, headers=h), 201)
    _ok(g1_client.post(f"{path}/{row['id']}/decide", json={"approve": True}, headers=gs))
    eff = _effective(client, h, ledger)
    assert eff["dunning"] == ("mhvp", "switch")
    assert eff["payment_order"] == ("immoware24", "ledger")
    # switch back to the old system needs no G1 but a second person; a rejection changes nothing
    back = {"kind": "dunning", "leading_system": "immoware24", "valid_from": "2099-01-01"}
    row = _ok(client.post(path, json=back, headers=h), 201)
    rej = _ok(client.post(f"{path}/{row['id']}/decide", json={"approve": False}, headers=s))
    assert rej["status"] == "rejected"
    row = _ok(client.post(path, json=back, headers=h), 201)
    _ok(client.post(f"{path}/{row['id']}/decide", json={"approve": True}, headers=s))
    assert _effective(client, h, ledger)["dunning"] == ("mhvp", "switch")  # future date
    items = _ok(client.get(path, headers=h))["items"]
    assert len(items) == 4


def test_is_leading_resolution(client: TestClient, g1_client: TestClient, world: World) -> None:
    """Central check: property row before ledger row, newest valid-from, fallback to the flag."""
    from mhvp.accounting import leading
    from mhvp.accounting.models import Ledger
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    h = bearer(login(client, world, "ag02admin"))
    gs = bearer(login(g1_client, world, "ag02second"))
    ledger_id, prop = _ledger(client, h, "922")
    path = f"{A}/ledgers/{ledger_id}/leading-switches"
    for body in (
        {"kind": "payment_order", "leading_system": "mhvp", "valid_from": "2026-03-01"},
        {
            "kind": "payment_order",
            "leading_system": "immoware24",
            "valid_from": "2026-01-01",
            "property_id": prop,
        },
    ):
        row = _ok(client.post(path, json=body, headers=h), 201)
        _ok(g1_client.post(f"{path}/{row['id']}/decide", json={"approve": True}, headers=gs))

    async def check() -> None:
        engine = create_app_engine(_settings_for(client))
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, world.tenant_a) as session:
                ledger = await session.get(Ledger, uuid.UUID(ledger_id))
                assert ledger is not None
                kind = leading.LeadingKind.PAYMENT_ORDER
                assert not await leading.is_leading(session, ledger, kind, date(2026, 2, 1))
                assert await leading.is_leading(session, ledger, kind, date(2026, 3, 1))
                pid = uuid.UUID(prop)
                assert not await leading.is_leading(session, ledger, kind, date(2026, 3, 1), pid)
                dd = leading.LeadingKind.DIRECT_DEBIT
                assert await leading.explicit(session, ledger, dd, date(2026, 3, 1)) is None
                assert not await leading.is_leading(session, ledger, dd, date(2026, 3, 1))
        finally:
            await engine.dispose()

    asyncio.run(check())


def _settings_for(client: TestClient) -> Any:
    return client.app.state.settings  # type: ignore[attr-defined]
