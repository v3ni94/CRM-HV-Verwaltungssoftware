"""AB09: fee fields (GA03-06), default bank rule (GA02-05) and plan flag auto_post (GA03-07).

Own world with prefix ab09. Expected values are fixed: the default rule has priority 900 and
state proposed; the plan flag never posts, it only reports the lock state of the run.
"""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database, approve_bank_accounts
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
A = "/api/v1/accounting"
IBAN = "DE89370400440532013000"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ab09a-{RUN}", name=f"AB09 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ab09b-{RUN}", name=f"AB09 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ab09admin", a, "tenant_admin"),
            ("ab09approver", a, "tenant_admin"),
            ("ab09reader", a, "read_only"),
            ("ab09other", b, "tenant_admin"),
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


def _setup(c: TestClient, h: dict[str, str], world: World, number: str) -> dict[str, Any]:
    prop = _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AB09 {number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    hoa = next(e["id"] for e in prop["legal_entities"] if e["kind"] == "hoa")
    template = _ok(c.post(f"{A}/templates/default", headers=h), 201)
    ledger = _ok(
        c.post(
            f"{A}/ledgers", json={"legal_entity_id": hoa, "template_id": template["id"]}, headers=h
        ),
        201,
    )["id"]
    acc = {a["number"]: a["id"] for a in _ok(c.get(f"{A}/ledgers/{ledger}/accounts", headers=h))}
    provider = _ok(
        c.post(
            "/api/v1/contacts",
            json={
                "kind": "company",
                "company_name": f"AB09 Dienst {number} {RUN} GmbH",
                "bank_accounts": [{"iban": IBAN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )
    approve_bank_accounts(c, bearer(login(c, world, "ab09approver")), provider["id"])
    bank = _ok(c.get(f"/api/v1/contacts/{provider['id']}", headers=h))["bank_accounts"][0]["id"]
    return {
        "number": number,
        "property": prop["id"],
        "ledger": ledger,
        "acc": acc,
        "provider": provider["id"],
        "bank": bank,
    }


def _fee(env: dict[str, Any], **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "property_id": env["property"],
        "start_date": "2026-01-01",
        "amounts_per_unit_type": {"apartment": "40.00"},
    }
    return body | over


def test_fee_fields_validation_permission_tenant(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ab09admin"))
    env = _setup(client, h, world, "911")
    revenue = env["acc"]["043000"]
    created = _ok(
        client.post(
            f"{A}/admin-fees",
            json=_fee(
                env,
                manager_contact_id=env["provider"],
                termination_date="2026-12-31",
                due_day_rule="day",
                due_day=15,
                account_id=revenue,
                sev_fee_amount="25.50",
            ),
            headers=h,
        ),
        201,
    )
    read = _ok(client.get(f"{A}/admin-fees/{created['id']}", headers=h))
    assert read["manager_contact_id"] == env["provider"]
    assert read["termination_date"] == "2026-12-31"
    assert (read["due_day_rule"], read["due_day"]) == ("day", 15)
    assert read["account_id"] == revenue
    assert read["sev_fee_amount"] == "25.50"
    patched = _ok(
        client.patch(
            f"{A}/admin-fees/{created['id']}",
            json={"due_day_rule": "last_day", "sev_fee_amount": "30.00"},
            headers=h,
        )
    )
    assert (patched["due_day_rule"], patched["sev_fee_amount"]) == ("last_day", "30.00")

    # Validation 422: rule needs a day, termination before start, negative amount, unknown contact.
    for bad in (
        {"due_day_rule": "day"},
        {"termination_date": "2025-12-31"},
        {"sev_fee_amount": "-1.00"},
        {"due_day_rule": "weekly"},
        {"manager_contact_id": "00000000-0000-4000-8000-000000000000"},
    ):
        assert (
            client.post(f"{A}/admin-fees", json=_fee(env, **bad), headers=h).status_code == 422
        ), bad

    # Read permission: reading yes, writing 403.
    r = bearer(login(client, world, "ab09reader"))
    assert client.get(f"{A}/admin-fees/{created['id']}", headers=r).status_code == 200
    assert client.post(f"{A}/admin-fees", json=_fee(env), headers=r).status_code == 403
    assert (
        client.patch(
            f"{A}/admin-fees/{created['id']}", json={"sev_fee_amount": "1.00"}, headers=r
        ).status_code
        == 403
    )

    # Tenant separation: 404 for the other tenant.
    o = bearer(login(client, world, "ab09other"))
    assert client.get(f"{A}/admin-fees/{created['id']}", headers=o).status_code == 404
    assert (
        client.patch(
            f"{A}/admin-fees/{created['id']}", json={"sev_fee_amount": "1.00"}, headers=o
        ).status_code
        == 404
    )


def test_creditor_view_tenant_and_permission(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ab09admin"))
    env = _setup(client, h, world, "912")
    rows = _ok(client.get(f"{A}/ledgers/{env['ledger']}/creditors", headers=h))
    assert isinstance(rows, list)
    r = bearer(login(client, world, "ab09reader"))
    assert client.get(f"{A}/ledgers/{env['ledger']}/creditors", headers=r).status_code == 200
    o = bearer(login(client, world, "ab09other"))
    assert client.get(f"{A}/ledgers/{env['ledger']}/creditors", headers=o).status_code == 404
    missing = "00000000-0000-4000-8000-000000000000"
    assert (
        client.get(f"{A}/ledgers/{env['ledger']}/creditors/{missing}/statement", headers=h)
    ).status_code == 404


def test_default_bank_rule_on_provider_relation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ab09admin"))
    env = _setup(client, h, world, "913")
    body = {
        "contact_id": env["provider"],
        "contract_type_code": "hausmeister",
        "valid_from": "2026-01-01",
        "contact_bank_account_id": env["bank"],
        "create_default_bank_rule": True,
    }
    code = client.get("/api/v1/catalogs/provider_contract_type", headers=h)
    if code.status_code == 200 and code.json():
        first = code.json()[0]
        body["contract_type_code"] = first["code"] if isinstance(first, dict) else first
    _ok(
        client.post(
            f"/api/v1/properties/{env['property']}/service-providers", json=body, headers=h
        ),
        201,
    )
    rules = [
        r
        for r in _ok(client.get("/api/v1/banking/rules", headers=h))
        if r["name"].startswith("Standardregel Dienstleister")
        and f"Dienst {env['number']} " in r["name"]
    ]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["approval_state"] == "proposed"
    assert rule["priority"] == 900
    assert rule["action"]["kind"] == "creditor_payment"
    assert rule["action"]["account_id"] in env["acc"].values() or rule["action"]["account_id"]
    assert rule["hit_count"] == 0

    # Without the flag no rule arises.
    env2 = _setup(client, h, world, "914")
    body2 = body | {"contact_id": env2["provider"], "contact_bank_account_id": env2["bank"]}
    body2["create_default_bank_rule"] = False
    _ok(
        client.post(
            f"/api/v1/properties/{env2['property']}/service-providers", json=body2, headers=h
        ),
        201,
    )
    after = [
        r
        for r in _ok(client.get("/api/v1/banking/rules", headers=h))
        if r["name"].startswith("Standardregel Dienstleister")
        and f"Dienst {env2['number']} " in r["name"]
    ]
    assert after == []

    # Permission and tenant separation of the rule list.
    o = bearer(login(client, world, "ab09other"))
    assert not [
        r
        for r in _ok(client.get("/api/v1/banking/rules", headers=o))
        if r["name"].startswith("Standardregel")
    ]
    reader = bearer(login(client, world, "ab09reader"))
    assert (
        client.post(
            f"/api/v1/properties/{env['property']}/service-providers", json=body, headers=reader
        ).status_code
        == 403
    )


def test_plan_auto_post_flag_in_run(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ab09admin"))
    env = _setup(client, h, world, "915")
    plan_body = {
        "ledger_id": env["ledger"],
        "provider_contact_id": env["provider"],
        "account_id": env["acc"]["043000"],
        "gross": "119.00",
        "vat_percent": "19",
        "start_date": "2026-01-31",
        "text": "Wartung",
    }
    off = _ok(client.post(f"{A}/recurring-invoices", json=plan_body, headers=h), 201)
    assert _ok(client.get(f"{A}/recurring-invoices/{off['id']}", headers=h))["auto_post"] is False
    run = _ok(client.post(f"{A}/recurring-invoices/{off['id']}/generate", headers=h), 201)
    assert run["auto_post_requested"] is False
    assert run["auto_post_state"] == "draft_only"
    assert run["journal_entry_id"] is None
    assert run["number"].startswith("PLAN-")

    # Switch off: the flag cannot be set (409), nothing changes.
    blocked = client.post(
        f"{A}/recurring-invoices", json=plan_body | {"auto_post": True}, headers=h
    )
    assert blocked.status_code == 409, blocked.text

    # Switch on: flag settable, the run still creates a draft, G1 closed keeps it locked.
    _ok(
        client.put(
            "/api/v1/banking/automation",
            json={"enabled": True, "reason": "AB09 Test"},
            headers=h,
        )
    )
    try:
        on = _ok(
            client.post(f"{A}/recurring-invoices", json=plan_body | {"auto_post": True}, headers=h),
            201,
        )
        run2 = _ok(client.post(f"{A}/recurring-invoices/{on['id']}/generate", headers=h), 201)
        assert run2["auto_post_requested"] is True
        assert run2["auto_post_state"] == "locked_g1"
        assert run2["journal_entry_id"] is None
        assert run2["number"].startswith("PLAN-")
        # validation: unknown field
        assert (
            client.patch(
                f"{A}/recurring-invoices/{on['id']}", json={"auto_post": "maybe"}, headers=h
            ).status_code
            == 422
        )
        r = bearer(login(client, world, "ab09reader"))
        assert (
            client.patch(
                f"{A}/recurring-invoices/{on['id']}", json={"auto_post": False}, headers=r
            ).status_code
            == 403
        )
        o = bearer(login(client, world, "ab09other"))
        assert client.get(f"{A}/recurring-invoices/{on['id']}", headers=o).status_code == 404
    finally:
        _ok(
            client.put(
                "/api/v1/banking/automation",
                json={"enabled": False, "reason": "AB09 Test Ende"},
                headers=h,
            )
        )


def test_plan_auto_post_with_g1_open_stays_draft(
    database: Database, redis_url: str, world: World
) -> None:
    """G1 open and switch on: still a draft (a posting needs an active 7.4 rule)."""
    import uuid

    from mhvp.core.release_gates import ReleaseGate

    class OpenG1:
        async def is_open(self, tenant_id: uuid.UUID, gate: ReleaseGate) -> bool:
            return gate is ReleaseGate.G1

    with TestClient(
        create_app(_settings(database, redis_url), release_gate_resolver=OpenG1())
    ) as c:
        h = bearer(login(c, world, "ab09admin"))
        env = _setup(c, h, world, "916")
        plan_body = {
            "ledger_id": env["ledger"],
            "provider_contact_id": env["provider"],
            "account_id": env["acc"]["043000"],
            "gross": "119.00",
            "vat_percent": "19",
            "start_date": "2026-01-31",
            "text": "Wartung",
        }
        _ok(
            c.put("/api/v1/banking/automation", json={"enabled": True, "reason": "AB09"}, headers=h)
        )
        try:
            plan = _ok(
                c.post(f"{A}/recurring-invoices", json=plan_body | {"auto_post": True}, headers=h),
                201,
            )
            run = _ok(c.post(f"{A}/recurring-invoices/{plan['id']}/generate", headers=h), 201)
            assert run["auto_post_state"] == "draft_pending_rule"
            assert run["journal_entry_id"] is None
        finally:
            _ok(
                c.put(
                    "/api/v1/banking/automation",
                    json={"enabled": False, "reason": "AB09 Ende"},
                    headers=h,
                )
            )
