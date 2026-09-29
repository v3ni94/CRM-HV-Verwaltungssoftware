"""Bankverbindungen am Kontakt (CRM screen, M5-01 addendum 28.09.2026): add, change as new
version, end; four eyes for legal entity contacts and non approvers; system role Freigabe.

Expected values are fixed in the tests (rule 0.1.8): a released replacement ends the old row
the day before the new ``valid_from`` and hands over the default flag.
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

IBAN_A = "DE02120300000000202051"
IBAN_B = "DE02500105170137075030"
IBAN_C = "DE02100500000054540402"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"cba-{RUN}", name=f"Bank A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"cbb-{RUN}", name=f"Bank B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("clerk", a, "clerk_no_delete"),
            ("clerk2", a, "clerk_no_delete"),
            ("approver", a, "approver"),
            ("approver2", a, "approver"),
            ("boss", a, "tenant_admin"),
            ("viewer", a, "read_only"),
            ("other", b, "tenant_admin"),
        ]:
            uid = await services.create_user(
                factory, email=world.email(f"cb{name}"), display_name=name, password=PASSWORD
            )
            world.users[f"cb{name}"] = uid
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


def _person(suffix: str, **extra: Any) -> dict[str, Any]:
    return {
        "kind": "person",
        "first_name": "Karl",
        "last_name": f"Konto{suffix}{RUN}",
        "emails": [{"email": f"konto.{suffix}.{RUN}@example.org"}],
        "bank_accounts": [],
        **extra,
    }


def _create(client: TestClient, headers: dict[str, str], suffix: str, **extra: Any) -> str:
    created = client.post("/api/v1/contacts", json=_person(suffix, **extra), headers=headers)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _account(iban: str, valid_from: str = "2026-01-01", **extra: Any) -> dict[str, Any]:
    return {"iban": iban, "valid_from": valid_from, "holder": "Karl Konto", **extra}


def test_add_and_release_by_approver_role(client: TestClient, world: World) -> None:
    """Happy path: a clerk adds an account to an existing contact, the new system role
    Freigabe (contacts:approve, no contacts:update) releases it; the clerk cannot."""
    clerk = bearer(login(client, world, "cbclerk"))
    approver = bearer(login(client, world, "cbapprover"))
    contact_id = _create(client, clerk, "add")

    added = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts",
        json=_account(IBAN_A, is_default=True, label="Mietkonto"),
        headers=clerk,
    )
    assert added.status_code == 201, added.text
    account = added.json()
    assert account["approval_status"] == "pending"
    assert account["requested_by"] == str(world.users["cbclerk"])
    assert account["iban_masked"].endswith("2051")
    assert account["is_default"] is True
    assert account["replaces_account_id"] is None
    assert account["pending_change"] is None

    own = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/approve", headers=clerk
    )
    assert own.status_code == 403, own.text  # clerk_no_delete has no contacts:approve

    # The Freigabe role holds no write right on master data.
    denied = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts",
        json=_account(IBAN_B),
        headers=approver,
    )
    assert denied.status_code == 403, denied.text

    released = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/approve", headers=approver
    )
    assert released.status_code == 200, released.text
    assert released.json()["approval_status"] == "approved"
    assert released.json()["decided_by"] == str(world.users["cbapprover"])

    # Search finds the IBAN suffix like on PUT.
    listed = client.get("/api/v1/contacts", params={"q": "2051"}, headers=clerk)
    assert contact_id in {row["id"] for row in listed.json()["items"]}

    duplicate = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts", json=_account(IBAN_A), headers=clerk
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["code"] == "MHVP-CONT-0003"


def test_replace_creates_new_version_and_ends_old_on_release(
    client: TestClient, world: World
) -> None:
    clerk = bearer(login(client, world, "cbclerk"))
    approver = bearer(login(client, world, "cbapprover"))
    contact_id = _create(client, clerk, "rep", bank_accounts=[_account(IBAN_A, is_default=True)])
    old = client.get(f"/api/v1/contacts/{contact_id}", headers=clerk).json()["bank_accounts"][0]
    assert (
        client.post(
            f"/api/v1/contacts/{contact_id}/bank-accounts/{old['id']}/approve", headers=approver
        ).status_code
        == 200
    )

    too_early = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{old['id']}/replace",
        json=_account(IBAN_B, valid_from="2026-01-01"),
        headers=clerk,
    )
    assert too_early.status_code == 422, too_early.text

    replaced = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{old['id']}/replace",
        json=_account(IBAN_B, valid_from="2026-10-01", is_default=True),
        headers=clerk,
    )
    assert replaced.status_code == 201, replaced.text
    new = replaced.json()
    assert new["approval_status"] == "pending"
    assert new["replaces_account_id"] == old["id"]
    assert new["is_default"] is False  # handed over only on release

    # Old row untouched while pending; a second replacement is refused.
    accounts = {
        a["id"]: a
        for a in client.get(f"/api/v1/contacts/{contact_id}", headers=clerk).json()["bank_accounts"]
    }
    assert accounts[old["id"]]["valid_to"] is None
    assert accounts[old["id"]]["is_default"] is True
    again = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{old['id']}/replace",
        json=_account(IBAN_C, valid_from="2026-11-01"),
        headers=clerk,
    )
    assert again.status_code == 409, again.text
    assert again.json()["code"] == "MHVP-CONT-0002"

    released = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{new['id']}/approve", headers=approver
    )
    assert released.status_code == 200, released.text
    assert released.json()["approval_status"] == "approved"
    assert released.json()["is_default"] is True
    accounts = {
        a["id"]: a
        for a in client.get(f"/api/v1/contacts/{contact_id}", headers=clerk).json()["bank_accounts"]
    }
    assert accounts[old["id"]]["valid_to"] == "2026-09-30"  # day before new valid_from
    assert accounts[old["id"]]["is_default"] is False
    assert accounts[old["id"]]["iban_masked"].endswith("2051")  # history kept
    assert accounts[new["id"]]["iban_masked"].endswith("5030")


def test_end_direct_for_approver_and_four_eyes_for_clerk(client: TestClient, world: World) -> None:
    clerk = bearer(login(client, world, "cbclerk"))
    clerk2 = bearer(login(client, world, "cbclerk2"))
    boss = bearer(login(client, world, "cbboss"))
    approver = bearer(login(client, world, "cbapprover"))
    approver2 = bearer(login(client, world, "cbapprover2"))
    contact_id = _create(client, clerk, "end", bank_accounts=[_account(IBAN_A), _account(IBAN_B)])
    first, second = client.get(f"/api/v1/contacts/{contact_id}", headers=clerk).json()[
        "bank_accounts"
    ]
    for account in (first, second):
        assert (
            client.post(
                f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/approve",
                headers=approver,
            ).status_code
            == 200
        )

    # Tenant admin holds contacts:approve, the contact is no legal entity: applied at once.
    direct = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{first['id']}/end",
        json={"valid_to": "2026-12-31", "note": "Rückfrage am 28.09.2026 telefonisch"},
        headers=boss,
    )
    assert direct.status_code == 200, direct.text
    assert direct.json()["valid_to"] == "2026-12-31"
    assert direct.json()["pending_change"] is None

    # A clerk without contacts:approve only proposes; the change waits for a second person.
    proposed = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{second['id']}/end",
        json={"valid_to": "2026-11-30"},
        headers=clerk,
    )
    assert proposed.status_code == 200, proposed.text
    body = proposed.json()
    assert body["valid_to"] is None
    change = body["pending_change"]
    assert change is not None
    assert change["kind"] == "end"
    assert change["valid_to"] == "2026-11-30"
    assert change["status"] == "pending"
    assert change["requested_by"] == str(world.users["cbclerk"])

    # One pending change per account; the start page counts it for approvers.
    twice = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{second['id']}/end",
        json={"valid_to": "2026-10-31"},
        headers=clerk2,
    )
    assert twice.status_code == 409, twice.text
    assert twice.json()["code"] == "MHVP-CONT-0002"
    counts = client.get("/api/v1/workspace/approvals", headers=approver2).json()
    assert counts["bank_accounts"] >= 1

    decide = f"/api/v1/contacts/{contact_id}/bank-accounts/{second['id']}/changes/{change['id']}"
    assert client.post(f"{decide}/approve", headers=clerk).status_code == 403
    assert client.post(f"{decide}/approve", headers=clerk2).status_code == 403
    confirmed = client.post(f"{decide}/approve", headers=approver2)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["valid_to"] == "2026-11-30"
    assert confirmed.json()["pending_change"] is None
    again = client.post(f"{decide}/approve", headers=approver2)
    assert again.status_code == 409, again.text

    # Validation: valid_to before valid_from, invalid IBAN checksum.
    bad_date = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{first['id']}/end",
        json={"valid_to": "2025-12-31"},
        headers=boss,
    )
    assert bad_date.status_code in (409, 422), bad_date.text
    bad_iban = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts",
        json=_account("DE02120300000000202052"),
        headers=clerk,
    )
    assert bad_iban.status_code == 422, bad_iban.text


def test_legal_entity_contact_always_needs_second_person(client: TestClient, world: World) -> None:
    """The management company itself (contact type manager) is a legal entity: even a tenant
    admin only proposes the ending; the proposer never confirms (GATE_FOUR_EYES)."""
    boss = bearer(login(client, world, "cbboss"))
    approver = bearer(login(client, world, "cbapprover"))
    created = client.post(
        "/api/v1/contacts",
        json={
            "kind": "company",
            "company_name": f"Hausverwaltung Konto {RUN}",
            "types": ["manager"],
            "emails": [{"email": f"hv.konto.{RUN}@example.org"}],
            "bank_accounts": [_account(IBAN_C, holder="Hausverwaltung")],
        },
        headers=boss,
    )
    assert created.status_code == 201, created.text
    contact_id = created.json()["id"]
    account = created.json()["bank_accounts"][0]
    assert (
        client.post(
            f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/approve",
            headers=approver,
        ).status_code
        == 200
    )
    proposed = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/end",
        json={"valid_to": "2026-12-31"},
        headers=boss,
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["valid_to"] is None
    change = proposed.json()["pending_change"]
    assert change is not None
    assert change["requested_by"] == str(world.users["cbboss"])
    decide = f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/changes/{change['id']}"
    own = client.post(f"{decide}/approve", headers=boss)
    assert own.status_code == 403, own.text
    assert own.json()["code"] == "MHVP-GATE-0002"
    rejected = client.post(f"{decide}/reject", json={"reason": "Konto bleibt"}, headers=approver)
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["valid_to"] is None
    assert rejected.json()["pending_change"] is None

    # Ended or rejected accounts cannot be changed again.
    ended = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/end",
        json={"valid_to": "2026-01-31"},
        headers=boss,
    )
    assert ended.status_code == 200, ended.text  # proposal again (legal entity)
    change2 = ended.json()["pending_change"]
    assert (
        client.post(
            f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/changes/{change2['id']}/approve",
            headers=approver,
        ).status_code
        == 200
    )
    again = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/replace",
        json=_account(IBAN_A, valid_from="2026-10-01"),
        headers=boss,
    )
    assert again.status_code == 409, again.text
    assert again.json()["code"] == "MHVP-CONT-0001"


def test_authorization_and_tenant_separation(client: TestClient, world: World) -> None:
    clerk = bearer(login(client, world, "cbclerk"))
    viewer = bearer(login(client, world, "cbviewer"))
    other = bearer(login(client, world, "cbother"))
    contact_id = _create(client, clerk, "sep", bank_accounts=[_account(IBAN_A)])
    account = client.get(f"/api/v1/contacts/{contact_id}", headers=clerk).json()["bank_accounts"][0]

    assert (
        client.post(
            f"/api/v1/contacts/{contact_id}/bank-accounts", json=_account(IBAN_B), headers=viewer
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/end",
            json={"valid_to": "2026-12-31"},
            headers=viewer,
        ).status_code
        == 403
    )
    for path, body in (
        (f"/api/v1/contacts/{contact_id}/bank-accounts", _account(IBAN_B)),
        (
            f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/replace",
            _account(IBAN_B, valid_from="2026-10-01"),
        ),
        (
            f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/end",
            {"valid_to": "2026-12-31"},
        ),
    ):
        response = client.post(path, json=body, headers=other)
        assert response.status_code == 404, response.text


def test_put_rewrite_refused_while_change_pending(client: TestClient, world: World) -> None:
    """``PUT /contacts/{id}`` with ``bank_accounts`` deletes and recreates the rows; while an
    end request or a new version waits for the second person this is refused, so the four
    eyes request cannot vanish by cascade. Omitting ``bank_accounts`` still works."""
    clerk = bearer(login(client, world, "cbclerk"))
    approver = bearer(login(client, world, "cbapprover"))
    contact_id = _create(client, clerk, "put", bank_accounts=[_account(IBAN_A)])
    account = client.get(f"/api/v1/contacts/{contact_id}", headers=clerk).json()["bank_accounts"][0]
    assert (
        client.post(
            f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/approve",
            headers=approver,
        ).status_code
        == 200
    )
    proposed = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/end",
        json={"valid_to": "2026-12-31"},
        headers=clerk,
    )
    assert proposed.status_code == 200, proposed.text
    change = proposed.json()["pending_change"]
    assert change is not None

    rewrite = client.put(
        f"/api/v1/contacts/{contact_id}",
        json=_person("put", bank_accounts=[_account(IBAN_A)]),
        headers=clerk,
    )
    assert rewrite.status_code == 409, rewrite.text
    assert rewrite.json()["code"] == "MHVP-CONT-0002"
    body = _person("put")
    body.pop("bank_accounts")
    without = client.put(f"/api/v1/contacts/{contact_id}", json=body, headers=clerk)
    assert without.status_code == 200, without.text
    # The pending request survived and can still be decided.
    still = client.get(f"/api/v1/contacts/{contact_id}", headers=clerk).json()["bank_accounts"][0]
    assert still["pending_change"] is not None
    assert still["pending_change"]["id"] == change["id"]
    decided = client.post(
        f"/api/v1/contacts/{contact_id}/bank-accounts/{account['id']}/changes/{change['id']}/approve",
        headers=approver,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["valid_to"] == "2026-12-31"

    # Same for a pending new version (replace).
    contact2 = _create(client, clerk, "put2", bank_accounts=[_account(IBAN_B)])
    old = client.get(f"/api/v1/contacts/{contact2}", headers=clerk).json()["bank_accounts"][0]
    assert (
        client.post(
            f"/api/v1/contacts/{contact2}/bank-accounts/{old['id']}/approve", headers=approver
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/contacts/{contact2}/bank-accounts/{old['id']}/replace",
            json=_account(IBAN_C, valid_from="2026-10-01"),
            headers=clerk,
        ).status_code
        == 201
    )
    rewrite2 = client.put(
        f"/api/v1/contacts/{contact2}",
        json=_person("put2", bank_accounts=[_account(IBAN_B), _account(IBAN_C)]),
        headers=clerk,
    )
    assert rewrite2.status_code == 409, rewrite2.text
    assert rewrite2.json()["code"] == "MHVP-CONT-0002"
