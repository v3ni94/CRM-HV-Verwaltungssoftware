"""M19-01 (docs/rules/M19-01-sla-freigabe.md): SLA values per category and priority are drafts
until the management approves them; only approved rules govern clocks and escalation steps,
otherwise the clock runs without deadlines ("keine SLA" with a log hint).
"""

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
S = "/api/v1/sla"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"slaap-{RUN}", name=f"SLA A {RUN}")
        world = World(tenant_a=a, tenant_b=a, app_url=settings.database_url.get_secret_value())
        for name, role in [("slaapadmin", "tenant_admin"), ("slaapclerk", "standard")]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=a, user_id=uid, role_codes=[role], actor_user_id=None
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


def _rule(c: TestClient, h: dict[str, str], **extra: Any) -> dict[str, Any]:
    body = {
        "name": "Hoch",
        "priority": "high",
        "response_minutes": 60,
        "resolution_minutes": 600,
        "clock_type": "calendar",
        **extra,
    }
    return _ok(c.post(f"{S}/rules", json=body, headers=h), 201)  # type: ignore[no-any-return]


def _ticket(c: TestClient, h: dict[str, str], **extra: Any) -> dict[str, Any]:
    return _ok(  # type: ignore[no-any-return]
        c.post(
            "/api/v1/tickets",
            json={"title": "Dach undicht", "priority": "high", **extra},
            headers=h,
        ),
        201,
    )


def _clock(c: TestClient, h: dict[str, str], ticket_id: str) -> dict[str, Any]:
    return _ok(c.get(f"{S}/tickets/{ticket_id}/sla", headers=h))  # type: ignore[no-any-return]


def test_draft_rule_means_no_sla_until_management_approves(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "slaapadmin"))
    clerk = bearer(login(client, world, "slaapclerk"))

    rule = _rule(client, clerk)
    assert rule["approval_status"] == "draft"
    assert rule["approved_at"] is None
    assert rule["category"] is None

    # Draft: the clock starts, but without deadlines ("keine SLA"), so nothing escalates.
    before = _clock(client, admin, _ticket(client, clerk)["id"])
    assert before["rule_id"] is None
    assert before["due_response_at"] is None
    assert before["due_resolution_at"] is None
    assert before["state"] == "running"
    assert before["color"] == "green"

    # A clerk (standard role) cannot approve; the management (tenant_settings:update) can, and
    # only with an explicit confirmation.
    assert (
        client.post(f"{S}/rules/{rule['id']}/approve", json={"confirm": True}, headers=clerk)
    ).status_code == 403
    assert (
        client.post(f"{S}/rules/{rule['id']}/approve", json={"confirm": False}, headers=admin)
    ).status_code == 422
    approved = _ok(
        client.post(
            f"{S}/rules/{rule['id']}/approve",
            json={"confirm": True, "note": "GF 27.09.2026"},
            headers=admin,
        )
    )
    assert approved["approval_status"] == "approved"
    assert approved["approved_at"] is not None
    assert approved["approved_by"] == str(world.users["slaapadmin"])

    after = _clock(client, admin, _ticket(client, clerk)["id"])
    assert after["rule_id"] == rule["id"]
    assert after["due_response_at"] is not None
    assert after["due_resolution_at"] is not None

    # Changing the values drops the approval; toggling active alone keeps it.
    kept = _ok(
        client.patch(
            f"{S}/rules/{rule['id']}",
            json={
                "name": "Hoch",
                "priority": "high",
                "response_minutes": 60,
                "resolution_minutes": 600,
                "clock_type": "calendar",
                "active": True,
            },
            headers=clerk,
        )
    )
    assert kept["approval_status"] == "approved"
    changed = _ok(
        client.patch(
            f"{S}/rules/{rule['id']}",
            json={
                "name": "Hoch",
                "priority": "high",
                "response_minutes": 30,
                "resolution_minutes": 600,
                "clock_type": "calendar",
            },
            headers=clerk,
        )
    )
    assert changed["approval_status"] == "draft"
    assert changed["approved_at"] is None
    assert _clock(client, admin, _ticket(client, clerk)["id"])["rule_id"] is None

    # Revoking an approval is possible for the management only.
    _ok(client.post(f"{S}/rules/{rule['id']}/approve", json={"confirm": True}, headers=admin))
    assert client.post(f"{S}/rules/{rule['id']}/revoke-approval", headers=clerk).status_code == 403
    revoked = _ok(client.post(f"{S}/rules/{rule['id']}/revoke-approval", headers=admin))
    assert revoked["approval_status"] == "draft"


def test_category_rule_wins_over_general_rule_and_presets_are_drafts(
    client: TestClient, world: World
) -> None:
    admin = bearer(login(client, world, "slaapadmin"))
    general = _rule(client, admin, priority="urgent", name="Dringend allgemein")
    specific = _rule(
        client,
        admin,
        priority="urgent",
        name="Dringend Heizung",
        category="heizung",
        response_minutes=15,
        resolution_minutes=120,
    )
    # Same priority and category twice is a conflict; a different category is fine.
    assert (
        client.post(
            f"{S}/rules",
            json={
                "name": "Doppelt",
                "priority": "urgent",
                "category": "heizung",
                "response_minutes": 1,
                "resolution_minutes": 2,
            },
            headers=admin,
        ).status_code
        == 409
    )
    for rule in (general, specific):
        _ok(client.post(f"{S}/rules/{rule['id']}/approve", json={"confirm": True}, headers=admin))

    heating = _clock(
        client, admin, _ticket(client, admin, priority="urgent", category="heizung")["id"]
    )
    assert heating["rule_id"] == specific["id"]
    other = _clock(
        client, admin, _ticket(client, admin, priority="urgent", category="aufzug")["id"]
    )
    assert other["rule_id"] == general["id"]

    presets = _ok(client.post(f"{S}/rules/presets", headers=admin), 201)
    assert all(p["approval_status"] == "draft" for p in presets if p["id"] not in (general["id"],))
    listed = _ok(client.get(f"{S}/rules", headers=admin))
    assert {r["approval_status"] for r in listed} == {"draft", "approved"}
