"""Bankkontenauswahl: accounts per property and legal entity with balance and latest
transactions, assignment set and released, default per property (Hausgeld/Miete) and per
legal entity. Tenant separation, legal entity separation and permissions. No payment (G2)."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import (
    PASSWORD,
    RUN,
    World,
    bearer,
    login,
    login_password_only,
)
from tests.integration.test_m5_contracts import _party
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m11_banking import _camt, _ntry, _upload

pytestmark = pytest.mark.integration
B = "/api/v1/banking"
P = "/api/v1/properties"
IBAN_HOA = "DE02120300000000202051"
IBAN_RENT = "DE89370400440532013000"
IBAN_OTHER = "DE75512108001245126199"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"bas-{RUN}", name=f"BankSel {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"bas2-{RUN}", name=f"BankSel2 {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("basadmin", a, "tenant_admin"),
            ("basacc", a, "accountant_no_banking"),
            ("basclerk", a, "clerk_no_accounting"),
            ("basother", b, "tenant_admin"),
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
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _property(c: TestClient, h: dict[str, str], number: str, kind: str) -> dict[str, Any]:
    return _ok(
        c.post(
            P,
            json={"number": number, "name": f"Objekt {number}", "management_type": kind},
            headers=h,
        ),
        201,
    )


def _entity(prop: dict[str, Any], kind: str) -> str:
    return str(next(e["id"] for e in prop["legal_entities"] if e["kind"] == kind))


def _account(
    c: TestClient, h: dict[str, str], prop: dict[str, Any], entity: str, kind: str, iban: str
) -> str:
    return str(
        _ok(
            c.post(
                f"{P}/{prop['id']}/bank-accounts",
                json={
                    "legal_entity_id": entity,
                    "kind": kind,
                    "iban": iban,
                    "holder": f"Inhaber {kind}",
                    "bank_name": "Testbank",
                    "valid_from": "2020-01-01",
                },
                headers=h,
            ),
            201,
        )["id"]
    )


def test_list_assign_defaults_and_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "basadmin"))
    hoa_prop = _property(client, h, "901", "hoa")
    hoa_entity = _entity(hoa_prop, "hoa")
    hoa_account = _account(client, h, hoa_prop, hoa_entity, "hoa", IBAN_HOA)

    rent_prop = _property(client, h, "902", "rental")
    party_id, _ = _party(client, h, "Volker")
    owner = _ok(
        client.post(
            f"{P}/{rent_prop['id']}/owners",
            json={"party_id": party_id, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    rent_entity = str(owner["legal_entity_id"])
    rent_account = _account(client, h, rent_prop, rent_entity, "rent", IBAN_RENT)

    # A statement import gives the HOA account a balance and transactions (B09 data, read only).
    doc = _upload(
        client,
        h,
        "stmt.xml",
        _camt(
            "S-1",
            IBAN_HOA,
            "1000.00",
            "1700.00",
            [_ntry("R1", "700.00", "CRDT", "2026-01-15", IBAN_OTHER, "Hausgeld Januar")],
        ),
    )
    _ok(client.post(f"{B}/imports", json={"document_id": doc}, headers=h), 201)

    # List per property: home property, balance from the statement, latest transactions.
    listed = _ok(client.get(f"{B}/accounts", params={"property_id": hoa_prop["id"]}, headers=h))
    assert [a["id"] for a in listed] == [hoa_account]
    item = listed[0]
    assert item["balance"] == "1700.00"
    assert item["balance_source"] == "statement"
    assert item["source"] == "manual"
    assert item["iban_masked"].endswith("2051")
    assert [t["amount"] for t in item["recent_transactions"]] == ["700.00"]
    assert item["recent_transactions"][0]["purpose"] == "Hausgeld Januar"
    assert item["legal_entity_id"] == hoa_entity
    assert item["default_for_legal_entity"] is False

    # List per legal entity.
    by_entity = _ok(client.get(f"{B}/accounts", params={"legal_entity_id": rent_entity}, headers=h))
    assert [a["id"] for a in by_entity] == [rent_account]
    assert by_entity[0]["balance"] is None  # no invented balance

    # Search by holder text.
    found = _ok(client.get(f"{B}/accounts", params={"q": "Inhaber rent"}, headers=h))
    assert [a["id"] for a in found] == [rent_account]

    # Default per property and purpose: Hausgeld only for HOA accounts, Miete only for rent.
    r = client.put(
        f"{B}/accounts/{rent_account}/assignments",
        json={"property_id": rent_prop["id"], "purpose": "hausgeld", "is_default": True},
        headers=h,
    )
    assert r.status_code == 422, r.text
    out = _ok(
        client.put(
            f"{B}/accounts/{rent_account}/assignments",
            json={"property_id": rent_prop["id"], "purpose": "miete", "is_default": True},
            headers=h,
        )
    )
    assert out["assignments"] == [
        {
            "property_id": rent_prop["id"],
            "property_number": "902",
            "property_name": "Objekt 902",
            "purpose": "miete",
            "is_default": True,
        }
    ]
    out = _ok(
        client.put(
            f"{B}/accounts/{hoa_account}/assignments",
            json={"property_id": hoa_prop["id"], "purpose": "hausgeld", "is_default": True},
            headers=h,
        )
    )
    assert out["assignments"][0]["purpose"] == "hausgeld"

    # Legal entity separation: the HOA account cannot be assigned to the rental property.
    r = client.put(
        f"{B}/accounts/{hoa_account}/assignments",
        json={"property_id": rent_prop["id"], "purpose": "general"},
        headers=h,
    )
    assert r.status_code == 422, r.text
    assert "Rechtsträgertrennung" in r.json()["detail"]

    # A second rental property of the same owner party may share the rent account (the owner
    # acts there through its own legal entity); the assignment is listed and released again.
    rent_prop2 = _property(client, h, "903", "rental")
    owner2 = _ok(
        client.post(
            f"{P}/{rent_prop2['id']}/owners",
            json={"party_id": party_id, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    assert owner2["legal_entity_id"] != rent_entity  # one legal entity per party and property
    out = _ok(
        client.put(
            f"{B}/accounts/{rent_account}/assignments",
            json={"property_id": rent_prop2["id"], "purpose": "miete", "is_default": True},
            headers=h,
        )
    )
    assert {a["property_id"] for a in out["assignments"]} == {
        rent_prop["id"],
        rent_prop2["id"],
    }
    listed2 = _ok(client.get(f"{B}/accounts", params={"property_id": rent_prop2["id"]}, headers=h))
    assert [a["id"] for a in listed2] == [rent_account]
    options = _ok(client.get(f"{P}/{rent_prop2['id']}/bank-account-options", headers=h))
    assert [a["id"] for a in options] == [rent_account]
    r = client.delete(f"{B}/accounts/{rent_account}/assignments/{rent_prop2['id']}", headers=h)
    assert r.status_code == 204, r.text
    assert (
        _ok(client.get(f"{B}/accounts", params={"property_id": rent_prop2["id"]}, headers=h)) == []
    )
    r = client.delete(f"{B}/accounts/{rent_account}/assignments/{rent_prop2['id']}", headers=h)
    assert r.status_code == 404

    # The home property cannot be released.
    r = client.delete(f"{B}/accounts/{rent_account}/assignments/{rent_prop['id']}", headers=h)
    assert r.status_code == 422

    # Default per legal entity: exactly one, switching moves the marker.
    hoa_account2 = _account(client, h, hoa_prop, hoa_entity, "hoa_fee", "DE72120300000000202052")
    out = _ok(
        client.put(
            f"{B}/accounts/{hoa_account}/legal-entity-default",
            json={"is_default": True},
            headers=h,
        )
    )
    assert out["default_for_legal_entity"] is True
    out = _ok(
        client.put(
            f"{B}/accounts/{hoa_account2}/legal-entity-default",
            json={"is_default": True},
            headers=h,
        )
    )
    assert out["default_for_legal_entity"] is True
    by_hoa = {
        a["id"]: a
        for a in _ok(client.get(f"{B}/accounts", params={"legal_entity_id": hoa_entity}, headers=h))
    }
    assert by_hoa[hoa_account]["default_for_legal_entity"] is False
    assert by_hoa[hoa_account2]["default_for_legal_entity"] is True
    out = _ok(
        client.put(
            f"{B}/accounts/{hoa_account2}/legal-entity-default",
            json={"is_default": False},
            headers=h,
        )
    )
    assert out["default_for_legal_entity"] is False

    # Default per property and purpose is unique: the second HOA account takes over.
    _ok(
        client.put(
            f"{B}/accounts/{hoa_account2}/assignments",
            json={"property_id": hoa_prop["id"], "purpose": "hausgeld", "is_default": True},
            headers=h,
        )
    )
    by_prop = {
        a["id"]: a
        for a in _ok(client.get(f"{B}/accounts", params={"property_id": hoa_prop["id"]}, headers=h))
    }
    assert by_prop[hoa_account]["assignments"][0]["is_default"] is False
    assert by_prop[hoa_account2]["assignments"][0]["is_default"] is True

    # Property page endpoint: accountants see money, clerks see the account without balance.
    acc_h = bearer(login_password_only(client, world, "basacc"))
    options = _ok(client.get(f"{P}/{hoa_prop['id']}/bank-account-options", headers=acc_h))
    assert {a["id"] for a in options} == {hoa_account, hoa_account2}
    assert next(a for a in options if a["id"] == hoa_account)["balance"] == "1700.00"
    clerk_h = bearer(login_password_only(client, world, "basclerk"))
    options = _ok(client.get(f"{P}/{hoa_prop['id']}/bank-account-options", headers=clerk_h))
    assert next(a for a in options if a["id"] == hoa_account)["balance"] is None
    assert next(a for a in options if a["id"] == hoa_account)["recent_transactions"] == []

    # Permissions: without accounting rights neither list nor assignment.
    assert client.get(f"{B}/accounts", headers=clerk_h).status_code == 403
    r = client.put(
        f"{B}/accounts/{hoa_account}/assignments",
        json={"property_id": hoa_prop["id"], "purpose": "general"},
        headers=clerk_h,
    )
    assert r.status_code == 403
    r = client.put(
        f"{B}/accounts/{hoa_account}/legal-entity-default",
        json={"is_default": True},
        headers=clerk_h,
    )
    assert r.status_code == 403

    # Tenant separation: the other tenant sees nothing and cannot assign.
    other_h = bearer(login(client, world, "basother"))
    assert _ok(client.get(f"{B}/accounts", headers=other_h)) == []
    assert (
        _ok(client.get(f"{B}/accounts", params={"property_id": hoa_prop["id"]}, headers=other_h))
        == []
    )
    r = client.put(
        f"{B}/accounts/{hoa_account}/assignments",
        json={"property_id": hoa_prop["id"], "purpose": "general"},
        headers=other_h,
    )
    assert r.status_code == 404
    r = client.put(
        f"{B}/accounts/{hoa_account}/legal-entity-default",
        json={"is_default": True},
        headers=other_h,
    )
    assert r.status_code == 404
    r = client.delete(f"{B}/accounts/{hoa_account}/assignments/{hoa_prop['id']}", headers=other_h)
    assert r.status_code == 404
    assert (
        client.get(f"{P}/{hoa_prop['id']}/bank-account-options", headers=other_h).status_code == 404
    )
