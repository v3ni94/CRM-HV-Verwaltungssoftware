"""AB13: platform audit trail (append-only), contract number format, tenant delivery default.

Expected values are fixed here: circle contract with prefix V, 5 digits, start 100 gives V-00100
for the first contract; a later change of the start value to 500 does not apply because the
circle is in use, the next number is V-00101."""

import asyncio
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _property, _unit
from tests.integration.test_m6_documents import BUCKET, _settings

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ab13a-{RUN}", name=f"AB13 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ab13b-{RUN}", name=f"AB13 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        specs = {
            "ab13admin": (False, a, "tenant_admin"),
            "ab13reader": (False, a, "read_only"),
            "ab13padmin": (True, None, None),
        }
        for name, (is_admin, tenant_id, role) in specs.items():
            uid = await services.create_user(
                factory,
                email=world.email(name),
                display_name=name,
                password=PASSWORD,
                is_platform_admin=is_admin,
            )
            world.users[name] = uid
            if tenant_id is not None:
                await services.add_member(
                    factory,
                    tenant_id=tenant_id,
                    user_id=uid,
                    role_codes=[role],
                    actor_user_id=None,
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
    return response.json() if response.content else None


def test_platform_audit_trail(client: TestClient, world: World, migrator_engine: Any) -> None:
    p = bearer(login(client, world, "ab13padmin"))
    t = bearer(login(client, world, "ab13admin"))
    audit = "/api/v1/platform/audit-events"
    base = f"/api/v1/platform/tenants/{world.tenant_a}"
    host = f"audit-{RUN}.kunde-ab13.test"
    cid = f"ab13-{RUN}"
    oidc = "/api/v1/platform/oidc-clients"
    try:
        created = _ok(client.post(base + "/domains", json={"host": host}, headers=p), 201)
        _ok(client.delete(f"{base}/domains/{created['id']}", headers=p), 204)
        _ok(
            client.patch(
                f"/api/v1/platform/tenants/{world.tenant_b}",
                json={"status": "suspended"},
                headers=p,
            )
        )
        _ok(
            client.patch(
                f"/api/v1/platform/tenants/{world.tenant_b}", json={"status": "active"}, headers=p
            )
        )
        body = {"client_id": cid, "name": "Audit", "redirect_uris": ["https://a.example.org/cb"]}
        made = _ok(client.post(oidc, json=body, headers=p), 201)
        rotated = _ok(client.post(f"{oidc}/{cid}/rotate-secret", headers=p))
        _ok(client.post(f"{oidc}/{cid}/deactivate", headers=p))
        # failed action leaves no event
        before = _ok(client.get(audit, headers=p))["total"]
        assert client.post(oidc, json=body, headers=p).status_code == 409
        assert _ok(client.get(audit, headers=p))["total"] == before

        everything = _ok(client.get(audit + "?limit=200", headers=p))
        mine = [
            e
            for e in everything["items"]
            if e["target_id"] in (str(world.tenant_a), str(world.tenant_b), cid)
        ]
        actions = sorted(e["action"] for e in mine)
        assert actions == sorted(
            [
                "oidc_client_created",
                "oidc_client_deactivated",
                "oidc_client_secret_rotated",
                "tenant_domain_added",
                "tenant_domain_removed",
                "tenant_status_changed",
                "tenant_status_changed",
            ]
        )
        assert all(e["actor_user_id"] == str(world.users["ab13padmin"]) for e in mine)
        status = [e for e in mine if e["action"] == "tenant_status_changed"]
        assert {(e["payload"]["from"], e["payload"]["to"]) for e in status} == {
            ("active", "suspended"),
            ("suspended", "active"),
        }
        # no secret anywhere in the trail
        dump = str(everything)
        assert made["client_secret"] not in dump
        assert rotated["client_secret"] not in dump
        assert "secret_hash" not in dump
        # pagination and filter
        page = _ok(client.get(audit + "?limit=1&offset=1", headers=p))
        assert len(page["items"]) == 1
        assert (page["limit"], page["offset"]) == (1, 1)
        assert page["total"] == everything["total"]
        only = _ok(client.get(audit + "?action=tenant_domain_added&limit=200", headers=p))
        assert only["items"]
        assert all(e["action"] == "tenant_domain_added" for e in only["items"])
        assert client.get(audit + "?limit=0", headers=p).status_code == 422
        assert client.get(audit + "?limit=201", headers=p).status_code == 422
        assert client.get(audit + "?offset=-1", headers=p).status_code == 422
        # permissions: tenant admin may neither read nor write
        assert client.get(audit, headers=t).status_code == 403
        assert client.get(audit).status_code == 401
        # rows are append-only, also for the migrator
        with migrator_engine.begin() as conn, pytest.raises(Exception, match="append-only"):
            conn.execute(text("UPDATE platform_audit_event SET action = 'x'"))
        with migrator_engine.begin() as conn, pytest.raises(Exception, match="append-only"):
            conn.execute(text("DELETE FROM platform_audit_event"))
    finally:
        with migrator_engine.begin() as conn:
            conn.execute(text("DELETE FROM oidc_client WHERE client_id = :c"), {"c": cid})


def test_contract_number_format_and_start_value(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ab13admin"))
    url = "/api/v1/tenant/number-formats"
    prop = _property(client, h, "813", "rental")
    units = [_unit(client, h, prop["id"], n) for n in ("01", "02", "03")]
    owner, _ = _party(client, h, "Vermieter", "company")
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/owners",
            json={"party_id": owner, "valid_from": "2020-01-01"},
            headers=h,
        ),
        201,
    )
    party, _ = _party(client, h, "Mieter")

    def contract(unit: str, start: str) -> str:
        created = client.post(
            "/api/v1/contracts",
            json={"kind": "tenancy", "unit_id": unit, "party_id": party, "start_date": start},
            headers=h,
        )
        return str(_ok(created, 201)["number"])

    put = client.put(
        url, json={"formats": {"contract": {"prefix": "V", "digits": 5, "start": 100}}}, headers=h
    )
    assert put.status_code == 200, put.text
    # unused circle: the start value applies to the first contract of the new format
    assert contract(units[0], "2026-01-01") == "V-00100"
    # circle in use: a changed start value does not apply, numbers continue
    put = client.put(
        url, json={"formats": {"contract": {"prefix": "V", "digits": 5, "start": 500}}}, headers=h
    )
    assert put.status_code == 200, put.text
    assert contract(units[1], "2026-01-01") == "V-00101"
    assert contract(units[2], "2026-01-01") == "V-00102"
    # reader may not change the format
    r = bearer(login(client, world, "ab13reader"))
    assert client.put(url, json={"formats": {}}, headers=r).status_code == 403
    # invoice circle stays locked (AA17-01)
    locked = client.put(
        url, json={"formats": {"invoice": {"prefix": "RE", "digits": 6}}}, headers=h
    )
    assert locked.status_code == 422


def test_tenant_delivery_default_in_dispatch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ab13admin"))
    _ok(
        client.put(
            "/api/v1/tenant/delivery-default", json={"default_delivery_channel": "email"}, headers=h
        )
    )
    address = {
        "street": "Rheinpromenade",
        "house_number": "13",
        "postal_code": "40789",
        "city": "Monheim am Rhein",
    }

    def contact(first: str, **extra: Any) -> str:
        body = {
            "kind": "person",
            "first_name": first,
            "last_name": f"Zustell{RUN}",
            "addresses": [address],
            **extra,
        }
        return str(_ok(client.post("/api/v1/contacts", json=body, headers=h), 201)["id"])

    plain = contact("Anna", emails=[{"email": f"anna.{RUN}@example.org", "is_primary": True}])
    prefers_post = contact("Bernd", preferred_channel="post")
    files = {"file": ("schreiben.pdf", b"%PDF-1.4 test", "application/pdf")}
    doc = str(_ok(client.post("/api/v1/documents", files=files, headers=h), 201)["id"])

    def dispatch(contact_id: str, **extra: Any) -> str:
        res = client.post(
            "/api/v1/dispatches",
            json={"document_id": doc, "contact_id": contact_id, **extra},
            headers=h,
        )
        return str(_ok(res, 201)["channel"])

    # tenant default applies without position channel and contact preference
    assert dispatch(plain) == "email"
    # contact preference wins over the tenant default
    assert dispatch(prefers_post) == "post"
    # position channel wins over contact preference and tenant default
    assert dispatch(prefers_post, channel="portal") == "portal"
    # default back to post: contact without preference follows
    _ok(
        client.put(
            "/api/v1/tenant/delivery-default", json={"default_delivery_channel": "post"}, headers=h
        )
    )
    assert dispatch(plain) == "post"
