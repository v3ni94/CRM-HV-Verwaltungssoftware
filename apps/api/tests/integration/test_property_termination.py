"""Objekt deaktivieren (operator 27.09.2026): terminate records notice, end of management,
successors and the notice letter and sets the property to terminated; lists hide terminated
properties except for the superadmin with include_terminated; reactivation is reserved to
the superadmin; tenant separation and audit rows. Rows are invented."""

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
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration
AUDIT = "/api/v1/tenant/audit-log"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"pt-{RUN}", name=f"Beendigung {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"pt2-{RUN}", name=f"Fremd {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "ptadmin": (False, [(a, "tenant_admin")]),
            "ptreader": (False, [(a, "read_only")]),
            "ptother": (False, [(b, "tenant_admin")]),
            "ptsuper": (True, [(a, "tenant_admin")]),
        }
        for name, (is_admin, memberships) in specs.items():
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            for tenant_id, role in memberships:
                await services.add_member(
                    factory, tenant_id=tenant_id, user_id=uid, role_codes=[role], actor_user_id=None
                )
        await services.set_superadmin(
            factory, user_id=world.users["ptsuper"], granted=True, actor_user_id=None
        )
        return world
    finally:
        await engine.dispose()


async def _revoke(settings: Any, world: World) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    engine = create_app_engine(settings)
    try:
        await services.set_superadmin(
            create_session_factory(engine),
            user_id=world.users["ptsuper"],
            granted=False,
            actor_user_id=None,
        )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> Iterator[World]:
    settings = _settings(database, redis_url)
    built = asyncio.run(_world(settings))
    yield built
    # Only one superadmin at a time (ADR 0011): release the marker for other modules.
    asyncio.run(_revoke(settings, built))


@pytest.fixture
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if response.content else None


def _prop(client: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    body = {
        "number": number,
        "name": f"Beendigung {number}",
        "management_type": "hoa",
        "street": "Rheinpromenade",
        "house_number": number.lstrip("0"),
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }
    return _ok(client.post("/api/v1/properties", json=body, headers=h), 201)


def _contact(client: TestClient, h: dict[str, str], last_name: str) -> str:
    body = {"kind": "person", "first_name": "Nach", "last_name": f"{last_name}{RUN}"}
    return str(_ok(client.post("/api/v1/contacts", json=body, headers=h), 201)["id"])


def _document(client: TestClient, h: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/documents",
        files={"file": ("kuendigung.pdf", b"%PDF-1.4 fake notice", "application/pdf")},
        data={"title": "Kündigung Verwaltung"},
        headers=h,
    )
    return str(_ok(response, 201)["id"])


def _listed(client: TestClient, h: dict[str, str], prop_id: str, **params: Any) -> bool:
    page = _ok(client.get("/api/v1/properties", params={"page_size": 200, **params}, headers=h))
    return any(item["id"] == prop_id for item in page["items"])


def _termination(**overrides: Any) -> dict[str, Any]:
    return {
        "terminated_by": "hoa",
        "notice_date": "2026-09-01",
        "effective_date": "2026-12-31",
        "note": "Beschluss der Eigentümerversammlung",
        **overrides,
    }


def test_terminate_records_details_hides_from_list_and_audits(
    client: TestClient, world: World
) -> None:
    h = bearer(login(client, world, "ptadmin"))
    prop = _prop(client, h, "601")
    manager = _contact(client, h, "Verwalter")
    owner = _contact(client, h, "Eigentuemer")
    document = _document(client, h)
    assert client.get(f"/api/v1/properties/{prop['id']}/termination", headers=h).status_code == 404

    body = _termination(
        successor_manager_contact_id=manager,
        successor_owner_contact_id=owner,
        notice_document_id=document,
    )
    out = _ok(client.post(f"/api/v1/properties/{prop['id']}/terminate", json=body, headers=h))
    assert out["terminated_by"] == "hoa"
    assert out["previous_status"] == "onboarding"
    assert out["successor_manager_name"] == f"Verwalter{RUN}, Nach"
    assert out["successor_owner_name"] == f"Eigentuemer{RUN}, Nach"
    assert out["notice_document_title"] == "Kündigung Verwaltung"
    assert out["created_by"] == str(world.users["ptadmin"])
    assert out["reactivated_at"] is None

    detail = _ok(client.get(f"/api/v1/properties/{prop['id']}", headers=h))
    assert detail["status"] == "terminated"
    assert detail["managed_to"] == "2026-12-31"
    read = _ok(client.get(f"/api/v1/properties/{prop['id']}/termination", headers=h))
    assert read["id"] == out["id"]

    # Hidden from the list for everyone but the superadmin; include_terminated is ignored.
    assert not _listed(client, h, prop["id"])
    assert not _listed(client, h, prop["id"], include_terminated=True)
    assert not _listed(client, h, prop["id"], status="terminated")

    # A second termination is refused; the old status endpoint cannot leave terminated.
    again = client.post(f"/api/v1/properties/{prop['id']}/terminate", json=body, headers=h)
    assert again.status_code == 409
    assert again.json()["code"] == "MHVP-PROP-0001"

    rows = _ok(
        client.get(AUDIT, params={"entity_type": "property", "entity_id": prop["id"]}, headers=h)
    )
    assert any(
        r["changes"].get("status", {}).get("new") == "terminated"
        and r["changes"].get("managed_to", {}).get("new") == "2026-12-31"
        for r in rows
    ), rows


def test_validation_permission_and_tenant_separation(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ptadmin"))
    prop = _prop(client, h, "602")
    wrong_dates = client.post(
        f"/api/v1/properties/{prop['id']}/terminate",
        json=_termination(effective_date="2026-08-31"),
        headers=h,
    )
    assert wrong_dates.status_code == 422
    assert wrong_dates.json()["code"] == "MHVP-PROP-0004"
    unknown = client.post(
        f"/api/v1/properties/{prop['id']}/terminate",
        json=_termination(successor_manager_contact_id="0192abcd-0000-7000-8000-000000000001"),
        headers=h,
    )
    assert unknown.status_code == 404

    reader = bearer(login(client, world, "ptreader"))
    assert (
        client.post(
            f"/api/v1/properties/{prop['id']}/terminate", json=_termination(), headers=reader
        ).status_code
        == 403
    )
    other = bearer(login(client, world, "ptother"))
    assert (
        client.post(
            f"/api/v1/properties/{prop['id']}/terminate", json=_termination(), headers=other
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/properties/{prop['id']}", headers=h).json()["status"] == (
        "onboarding"
    )
    _ok(client.post(f"/api/v1/properties/{prop['id']}/terminate", json=_termination(), headers=h))
    assert (
        client.get(f"/api/v1/properties/{prop['id']}/termination", headers=other).status_code == 404
    )
    assert (
        client.get(f"/api/v1/properties/{prop['id']}/termination", headers=reader).status_code
        == 200
    )


def test_reactivation_only_by_superadmin(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ptadmin"))
    prop = _prop(client, h, "603")
    _ok(client.post(f"/api/v1/properties/{prop['id']}/terminate", json=_termination(), headers=h))

    denied = client.post(f"/api/v1/properties/{prop['id']}/reactivate", headers=h)
    assert denied.status_code == 403
    assert denied.json()["code"] == "MHVP-PROP-0003"

    superadmin = bearer(login(client, world, "ptsuper", tenant_id=world.tenant_a))
    me = _ok(client.get("/api/v1/auth/me", headers=superadmin))
    assert me["is_superadmin"] is True
    assert _ok(client.get("/api/v1/auth/me", headers=h))["is_superadmin"] is False

    # The superadmin sees terminated properties only with include_terminated.
    assert not _listed(client, superadmin, prop["id"])
    assert _listed(client, superadmin, prop["id"], include_terminated=True)
    assert _listed(client, superadmin, prop["id"], status="terminated")

    # Not terminated: refused even for the superadmin.
    fresh = _prop(client, h, "604")
    refused = client.post(f"/api/v1/properties/{fresh['id']}/reactivate", headers=superadmin)
    assert refused.status_code == 409
    assert refused.json()["code"] == "MHVP-PROP-0002"

    back = _ok(client.post(f"/api/v1/properties/{prop['id']}/reactivate", headers=superadmin))
    assert back["status"] == "onboarding"
    assert back["managed_to"] is None
    assert client.get(f"/api/v1/properties/{prop['id']}/termination", headers=h).status_code == 404
    assert _listed(client, h, prop["id"])
    rows = _ok(
        client.get(AUDIT, params={"entity_type": "property", "entity_id": prop["id"]}, headers=h)
    )
    assert any(r["changes"].get("status", {}).get("old") == "terminated" for r in rows), rows

    # A new termination after reactivation is possible again (history keeps both rows).
    _ok(client.post(f"/api/v1/properties/{prop['id']}/terminate", json=_termination(), headers=h))
