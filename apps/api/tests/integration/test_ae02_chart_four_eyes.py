"""AE02 (M10-01, SA-08, P07-04, P07-05): four eyes release of the chart of accounts template,
multi key distribution validation, statement kind proposals and the coverage report."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/accounting/templates"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ae02-{RUN}", name=f"AE02 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae02f-{RUN}", name=f"AE02F {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ae02admin", a, "tenant_admin"),
            ("ae02admin2", a, "tenant_admin"),
            ("ae02reader", a, "read_only"),
            ("ae02other", b, "tenant_admin"),
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


def test_four_eyes_split_and_coverage(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ae02admin"))
    h2 = bearer(login(client, world, "ae02admin2"))
    reader = bearer(login(client, world, "ae02reader"))
    other = bearer(login(client, world, "ae02other"))
    template = _ok(client.post(f"{A}/default", headers=h), 201)
    tid = template["id"]
    assert template["four_eyes_required"] is True
    heating = {r["number"]: r for r in template["accounts"]}
    assert heating["041000"]["proposed_statement_kind"] == "heating"
    assert heating["041000"]["proposal_status"] == "vorschlag_freigabe_offen"
    assert heating["041000"]["statement_kind"] == "operating_costs"

    # Coverage report: proposals open, special_levy has no account, other tenant 404.
    report = _ok(client.get(f"{A}/{tid}/coverage-report", headers=reader))
    assert report["open_proposals"] >= 1
    assert "special_levy" in report["statement_kinds_without_account"]
    assert "heating" not in report["statement_kinds_without_account"]
    assert client.get(f"{A}/{tid}/coverage-report", headers=other).status_code == 404
    assert client.get(f"{A}/{tid}/coverage-report?x=1", headers=h).status_code == 422

    # Multi key distribution: sum must be 100, keys unique.
    accounts = [dict(r) for r in template["accounts"]]
    row = next(r for r in accounts if r["number"] == "041000")
    row["allocation_split"] = [
        {"key_code": "V_HEIZ", "share_percent": "70"},
        {"key_code": "WFL", "share_percent": "20"},
    ]
    bad = client.put(f"{A}/{tid}/accounts", json={"accounts": accounts}, headers=h)
    assert bad.status_code == 422
    row["allocation_split"] = [
        {"key_code": "V_HEIZ", "share_percent": "70"},
        {"key_code": "V_HEIZ", "share_percent": "30"},
    ]
    assert (
        client.put(f"{A}/{tid}/accounts", json={"accounts": accounts}, headers=h).status_code == 422
    )
    row["allocation_split"] = [
        {"key_code": "V_HEIZ", "share_percent": "70.5"},
        {"key_code": "WFL", "share_percent": "29.5"},
    ]
    row["statement_kind"] = "heating"
    row["proposal_status"] = "uebernommen"
    saved = _ok(client.put(f"{A}/{tid}/accounts", json={"accounts": accounts}, headers=h))
    assert (
        next(r for r in saved["accounts"] if r["number"] == "041000")["statement_kind"] == "heating"
    )
    assert (
        client.put(f"{A}/{tid}/accounts", json={"accounts": accounts}, headers=reader).status_code
        == 403
    )

    # Four eyes: submitter cannot release, a second person can.
    _ok(client.post(f"{A}/{tid}/submit-review", headers=h))
    same = client.post(f"{A}/{tid}/release", json={"comment": "x"}, headers=h)
    assert same.status_code == 409
    assert same.json()["code"] == "MHVP-ACC-0015"
    assert (
        client.put(
            f"{A}/{tid}/four-eyes", json={"required": False, "reason": "x"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{A}/{tid}/four-eyes", json={"required": False, "reason": "Grund"}, headers=reader
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"{A}/{tid}/four-eyes", json={"required": False, "reason": "Grund"}, headers=other
        ).status_code
        == 404
    )
    released = _ok(client.post(f"{A}/{tid}/release", json={"comment": "geprüft"}, headers=h2))
    assert released["released_by"] == str(world.users["ae02admin2"])
    # Released: switch frozen; new version inherits the switch.
    frozen = client.put(
        f"{A}/{tid}/four-eyes", json={"required": False, "reason": "Grund"}, headers=h
    )
    assert frozen.status_code == 409
    v2 = _ok(client.post(f"{A}/{tid}/versions", headers=h), 201)
    assert v2["four_eyes_required"] is True
    off = _ok(
        client.put(
            f"{A}/{v2['id']}/four-eyes",
            json={"required": False, "reason": "Eine Person"},
            headers=h,
        )
    )
    assert off["four_eyes_required"] is False
    _ok(client.post(f"{A}/{v2['id']}/submit-review", headers=h))
    assert _ok(client.post(f"{A}/{v2['id']}/release", json={}, headers=h))["status"] == "released"
