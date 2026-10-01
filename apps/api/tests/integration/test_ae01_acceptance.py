"""Acceptance register (V16, AE01): draft, submit, release by a second person, frozen
released versions, append only results, markdown export, rights, tenant separation and
validation. Own world with prefix ``ae01``."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from mhvp.core.auth.permissions import ACCEPTANCE_APPROVE, SYSTEM_ROLES
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
B = "/api/v1/accounting/acceptance"


async def _world(settings: Any) -> World:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae01a-{RUN}", name=f"AE01 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae01b-{RUN}", name=f"AE01B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae01admin", a, "tenant_admin"),
            ("ae01expert", a, "acceptance_expert"),
            ("ae01expert2", a, "acceptance_expert"),
            ("ae01reader", a, "read_only"),
            ("ae01other", b, "tenant_admin"),
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


DRAFT = {
    "title": "Centverteilung",
    "inputs": {"betrag": "100.00", "anteile": ["1", "1", "1"]},
    "expected": {"verteilung": ["33.34", "33.33", "33.33"]},
    "source": "Anhang D, Fall D08; Rechenweg unabhängig vom System",
    "calculation": "100,00 / 3 = 33,33 Rest 0,01 an die erste Einheit",
}


def test_role_catalog_keeps_approve_away_from_admin() -> None:
    roles = {r.code: r for r in SYSTEM_ROLES}
    assert ACCEPTANCE_APPROVE in roles["acceptance_expert"].permissions
    assert ACCEPTANCE_APPROVE not in roles["tenant_admin"].permissions
    assert "acceptance:manage" not in roles["acceptance_expert"].permissions
    writes = [
        p
        for p in roles["acceptance_expert"].permissions
        if p.startswith("accounting:") and not p.endswith(":read")
    ]
    assert writes == []


def test_acceptance_register_flow(client: TestClient, world: World) -> None:
    adm = bearer(login(client, world, "ae01admin"))
    exp = bearer(login(client, world, "ae01expert"))
    exp2 = bearer(login(client, world, "ae01expert2"))
    rd = bearer(login(client, world, "ae01reader"))
    oth = bearer(login(client, world, "ae01other"))

    state = _ok(client.get(f"{B}/cases", headers=adm))
    assert state["cases_total"] == 58
    assert len(state["items"]) == 58
    assert state["released_total"] == 0
    assert state["passed_total"] == 0
    assert "V16" in state["note"]

    # Validation: unknown case, float amount, missing source, unknown query parameter.
    assert client.post(f"{B}/cases/D99/expected", json=DRAFT, headers=adm).status_code == 422
    bad = {**DRAFT, "expected": {"summe": 100.0}}
    assert client.post(f"{B}/cases/D08/expected", json=bad, headers=adm).status_code == 422
    nosrc = {k: v for k, v in DRAFT.items() if k != "source"}
    assert client.post(f"{B}/cases/D08/expected", json=nosrc, headers=adm).status_code == 422
    assert client.get(f"{B}/cases?foo=1", headers=adm).status_code == 422

    # Rights: reader may read, not write; expert may not draft; admin may not approve.
    _ok(client.get(f"{B}/cases", headers=rd))
    assert client.post(f"{B}/cases/D08/expected", json=DRAFT, headers=rd).status_code == 403
    assert client.post(f"{B}/cases/D08/expected", json=DRAFT, headers=exp).status_code == 403

    v1 = _ok(client.post(f"{B}/cases/D08/expected", json=DRAFT, headers=adm), 201)
    assert v1["version"] == 1
    assert v1["status"] == "draft"
    v1 = _ok(client.put(f"{B}/expected/{v1['id']}", json={**DRAFT, "title": "D08"}, headers=adm))
    assert v1["title"] == "D08"
    dec = {"decision": "approve", "name": "Fachkundige Person"}
    # Not submitted yet: 409; admin lacks approve: 403.
    assert (
        client.post(f"{B}/expected/{v1['id']}/decision", json=dec, headers=exp).status_code == 409
    )
    _ok(client.post(f"{B}/expected/{v1['id']}/submit", headers=adm))
    assert (
        client.post(f"{B}/expected/{v1['id']}/decision", json=dec, headers=adm).status_code == 403
    )
    assert client.put(f"{B}/expected/{v1['id']}", json=DRAFT, headers=adm).status_code == 409
    rel = _ok(client.post(f"{B}/expected/{v1['id']}/decision", json=dec, headers=exp))
    assert rel["status"] == "approved"
    assert rel["approved_by_name"] == "Fachkundige Person"

    # Result only by approve holder, on approved versions; floats refused.
    res = {"outcome": "passed", "software_version": "1.61.0", "name": "Fachkundige Person"}
    assert client.post(f"{B}/expected/{v1['id']}/results", json=res, headers=adm).status_code == 403
    bad_res = {**res, "actual": {"x": 1.5}}
    assert (
        client.post(f"{B}/expected/{v1['id']}/results", json=bad_res, headers=exp).status_code
        == 422
    )
    _ok(client.post(f"{B}/expected/{v1['id']}/results", json=res, headers=exp), 201)
    state = _ok(client.get(f"{B}/cases", headers=rd))
    assert state["released_total"] == 1
    assert state["passed_total"] == 1
    assert _ok(client.get(f"{B}/cases?status=approved", headers=rd))["items"][0]["case_id"] == "D08"

    # Version 2: admin drafts, a second expert releases; the old version becomes superseded
    # and the passed count follows the new version.
    v2 = _ok(client.post(f"{B}/cases/D08/expected", json=DRAFT, headers=adm), 201)
    assert v2["version"] == 2
    _ok(client.post(f"{B}/expected/{v2['id']}/submit", headers=adm))
    _ok(client.post(f"{B}/expected/{v2['id']}/decision", json=dec, headers=exp2))
    detail = _ok(client.get(f"{B}/cases/D08", headers=rd))
    assert [v["status"] for v in detail["versions"]] == ["superseded", "approved"]
    assert len(detail["results"]) == 1
    assert _ok(client.get(f"{B}/cases", headers=rd))["passed_total"] == 0
    assert client.post(f"{B}/expected/{v1['id']}/results", json=res, headers=exp).status_code == 409

    # Reject path.
    v3 = _ok(client.post(f"{B}/cases/D04/expected", json=DRAFT, headers=adm), 201)
    _ok(client.post(f"{B}/expected/{v3['id']}/submit", headers=adm))
    rj = _ok(
        client.post(
            f"{B}/expected/{v3['id']}/decision",
            json={"decision": "reject", "name": "Fachkundige Person", "note": "Quelle fehlt"},
            headers=exp,
        )
    )
    assert rj["status"] == "rejected"

    # Export.
    md = client.get(f"{B}/export.md", headers=rd)
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert "| D08 | Centverteilung | 2 |" in md.text

    # Tenant separation: other tenant sees nothing and gets 404 on foreign ids.
    assert _ok(client.get(f"{B}/cases", headers=oth))["released_total"] == 0
    assert client.put(f"{B}/expected/{v2['id']}", json=DRAFT, headers=oth).status_code == 404


def test_db_guard_freezes_released_versions(
    client: TestClient, world: World, database: Database
) -> None:
    from sqlalchemy import create_engine

    engine = create_engine(database.app_url)
    bind = text("SELECT set_config('app.tenant_id', :t, true)")
    tenant = {"t": str(world.tenant_a)}
    try:
        with engine.begin() as conn:
            conn.execute(bind, tenant)
            row = conn.execute(
                text("SELECT id FROM acceptance_expected WHERE status = 'approved' LIMIT 1")
            ).first()
        assert row is not None
        update = text("UPDATE acceptance_expected SET expected = '{}'::jsonb WHERE id = :i")
        with engine.connect() as conn:
            conn.execute(bind, tenant)
            with pytest.raises(DBAPIError):
                conn.execute(update, {"i": row[0]})
            conn.rollback()
        with engine.connect() as conn:
            conn.execute(bind, tenant)
            with pytest.raises(DBAPIError):
                conn.execute(text("DELETE FROM acceptance_result"))
            conn.rollback()
    finally:
        engine.dispose()
