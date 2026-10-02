"""AF06: G1 behaviour of recurring-invoices/generate (GAA-06) and register state in the G1
checklist (GAA-03). Own world with prefix af06; expected values are fixed."""

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
        a, _ = await services.provision_tenant(factory, slug=f"af06a-{RUN}", name=f"AF06 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af06b-{RUN}", name=f"AF06 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("af06admin", a, "tenant_admin"),
            ("af06approver", a, "tenant_admin"),
            ("af06reader", a, "read_only"),
            ("af06other", b, "tenant_admin"),
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
            json={"number": number, "name": f"AF06 {number}", "management_type": "hoa"},
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
                "company_name": f"AF06 Dienst {number} {RUN} GmbH",
                "bank_accounts": [{"iban": IBAN, "valid_from": "2020-01-01"}],
            },
            headers=h,
        ),
        201,
    )
    approve_bank_accounts(c, bearer(login(c, world, "af06approver")), provider["id"])
    bank = _ok(c.get(f"/api/v1/contacts/{provider['id']}", headers=h))["bank_accounts"][0]["id"]
    return {
        "number": number,
        "property": prop["id"],
        "ledger": ledger,
        "acc": acc,
        "provider": provider["id"],
        "bank": bank,
    }


def _plan(c: TestClient, h: dict[str, str], env: dict[str, Any]) -> str:
    plan = {
        "ledger_id": env["ledger"],
        "provider_contact_id": env["provider"],
        "account_id": env["acc"]["043000"],
        "gross": "119.00",
        "vat_percent": "19",
        "start_date": "2026-01-31",
        "text": "Wartung",
    }
    return str(_ok(c.post(f"{A}/recurring-invoices", json=plan, headers=h), 201)["id"])


def test_generate_is_draft_with_plan_number_and_reject_mode(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "af06admin"))
    env = _setup(client, h, world, "916")
    plan_id = _plan(client, h, env)
    run = _ok(client.post(f"{A}/recurring-invoices/{plan_id}/generate", headers=h), 201)
    assert run["number"].startswith("PLAN-")
    assert run["draft_number"] is True
    assert run["g1_open"] is False
    assert run["journal_entry_id"] is None
    _ok(
        client.put(
            f"{A}/rent-invoices/numbering-mode", json={"mode": "reject_when_g1_closed"}, headers=h
        )
    )
    refused = client.post(f"{A}/recurring-invoices/{plan_id}/generate", headers=h)
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "MHVP-GATE-0001", refused.text
    other = bearer(login(client, world, "af06other"))
    assert (
        client.post(f"{A}/recurring-invoices/{plan_id}/generate", headers=other).status_code == 404
    )
    reader = bearer(login(client, world, "af06reader"))
    assert (
        client.post(f"{A}/recurring-invoices/{plan_id}/generate", headers=reader).status_code == 403
    )


def test_g1_checklist_reads_register_state(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "af06admin"))
    state = _ok(client.get(f"{A}/g1-opening", headers=h))
    reg = state["acceptance_register"]
    assert reg["link"] == "/plattform/abnahme"
    assert reg["cases_total"] == 58
    assert reg["released_total"] == 0
    assert reg["g1_passed"] == 0
    assert state["cases_passed"] == 0
