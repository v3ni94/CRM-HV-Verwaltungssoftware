"""Q12: generic list parameters (S12-03), bulk endpoints with partial success report (S12-05),
tenant job switches in the standard jobs (S15-03) and missing domain events (S12-01).

Expected values are fixed: three contacts (two companies "Alpha", "Beta", one person
"Zeller"), filter[kind]=company returns exactly Alpha and Beta, sort=-display_name puts Beta
first; a bulk tag on one own, one foreign and one unknown id reports 1 success, 2 failures
with a not found code each."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_contracts_search import _owner
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _property, _unit
from tests.integration.test_m8_import import BUCKET, _settings

pytestmark = pytest.mark.integration


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"q12-{RUN}", name=f"Q12 {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"q12b-{RUN}", name=f"Q12 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("q12admin", a, "tenant_admin"),
            ("q12reader", a, "read_only"),
            ("q12other", b, "tenant_admin"),
        ):
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
    import boto3
    from moto import mock_aws

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as c:
            yield c


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _events(database: Database, redis_url: str, tenant: uuid.UUID, type_: str) -> list[Any]:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.events import DomainEvent

    async def run() -> list[Any]:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            async with tenant_transaction(create_session_factory(engine), tenant) as session:
                return list(
                    (
                        await session.scalars(select(DomainEvent).where(DomainEvent.type == type_))
                    ).all()
                )
        finally:
            await engine.dispose()

    return asyncio.run(run())


def test_generic_list_parameters(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "q12admin"))
    for body in (
        {"kind": "company", "company_name": f"Alpha {RUN}"},
        {"kind": "company", "company_name": f"Beta {RUN}"},
        {"kind": "person", "first_name": "Zoe", "last_name": f"Zeller {RUN}"},
    ):
        _ok(client.post("/api/v1/contacts", json=body, headers=h), 201)
    page = _ok(
        client.get(
            "/api/v1/contacts",
            params={"filter[kind]": "company", "sort": "-display_name", "q": RUN},
            headers=h,
        )
    )
    names = [i["display_name"] for i in page["items"]]
    assert names == [f"Beta {RUN}", f"Alpha {RUN}"]
    sparse = _ok(
        client.get("/api/v1/contacts", params={"fields": "display_name", "q": RUN}, headers=h)
    )
    assert sparse["total"] == 3
    assert all(set(i) == {"id", "display_name"} for i in sparse["items"])
    # Unknown filter, sort, fields and include are refused, never silently ignored.
    for params in (
        {"filter[nope]": "x"},
        {"sort": "nope"},
        {"fields": "nope"},
        {"include": "nope"},
        {"filter[kind]": "robot"},
    ):
        response = client.get("/api/v1/contacts", params=params, headers=h)
        assert response.status_code == 422, (params, response.text)

    rental = _property(client, h, "921", "rental")
    _property(client, h, "922", "hoa")
    props = _ok(
        client.get(
            "/api/v1/properties",
            params={"filter[management_type]": "rental", "fields": "number"},
            headers=h,
        )
    )
    assert [i["number"] for i in props["items"]] == ["921"]
    assert client.get("/api/v1/properties", params={"sort": "x"}, headers=h).status_code == 422

    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": f"Q12 Ticket {RUN}", "property_id": rental["id"]},
            headers=h,
        ),
        201,
    )
    rows = client.get(
        "/api/v1/tickets",
        params={
            "include": "property",
            "fields": "title,property",
            "filter[property_id]": rental["id"],
            "sort": "-created_at",
        },
        headers=h,
    )
    assert rows.status_code == 200, rows.text
    assert rows.headers["X-Total-Count"] == "1"
    data = rows.json()
    assert data == [
        {
            "id": ticket["id"],
            "title": f"Q12 Ticket {RUN}",
            "property": data[0]["property"],
        }
    ]
    assert data[0]["property"]["number"] == "921"
    # Legacy sort values of the ticket list keep working.
    assert client.get("/api/v1/tickets", params={"sort": "urgency"}, headers=h).status_code == 200
    assert client.get("/api/v1/tickets", params={"include": "unit"}, headers=h).status_code == 422

    assert _ok(client.get("/api/v1/contracts", params={"filter[kind]": "tenancy"}, headers=h)) == []
    assert client.get("/api/v1/contracts", params={"filter[x]": "1"}, headers=h).status_code == 422
    docs = _ok(client.get("/api/v1/documents", params={"sort": "-title"}, headers=h))
    assert docs["total"] == 0
    assert client.get("/api/v1/documents", params={"filter[x]": "1"}, headers=h).status_code == 422
    assert (
        _ok(
            client.get(
                "/api/v1/accounting/invoices", params={"filter[review_status]": "open"}, headers=h
            )
        )
        == []
    )
    assert (
        client.get("/api/v1/accounting/invoices", params={"sort": "x"}, headers=h).status_code
        == 422
    )

    # Tenant separation: the other tenant sees none of these rows through the filters.
    ho = bearer(login(client, world, "q12other"))
    other = _ok(
        client.get("/api/v1/contacts", params={"filter[kind]": "company", "q": RUN}, headers=ho)
    )
    assert other["total"] == 0


def test_bulk_endpoints(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "q12admin"))
    ho = bearer(login(client, world, "q12other"))
    reader = bearer(login(client, world, "q12reader"))
    mine = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"Bulk {RUN}"}, headers=h
        ),
        201,
    )
    foreign = _ok(
        client.post(
            "/api/v1/contacts", json={"kind": "company", "company_name": f"Fremd {RUN}"}, headers=ho
        ),
        201,
    )
    unknown = str(uuid.uuid4())
    body = {"ids": [mine["id"], foreign["id"], unknown], "action": "add_tag", "tag": f"q12-{RUN}"}
    assert client.post("/api/v1/contacts/bulk", json=body, headers=reader).status_code == 403
    assert (
        client.post("/api/v1/contacts/bulk", json={**body, "ids": []}, headers=h).status_code == 422
    )
    report = _ok(client.post("/api/v1/contacts/bulk", json=body, headers=h))
    assert (report["total"], report["succeeded"], report["failed"]) == (3, 1, 2)
    by_id = {i["id"]: i for i in report["items"]}
    assert by_id[mine["id"]]["ok"] is True
    assert by_id[foreign["id"]]["ok"] is False
    assert by_id[foreign["id"]]["code"]
    tagged = _ok(client.get("/api/v1/contacts", params={"tag": f"q12-{RUN}"}, headers=h))
    assert [i["id"] for i in tagged["items"]] == [mine["id"]]
    removed = _ok(
        client.post("/api/v1/contacts/bulk", json={**body, "action": "remove_tag"}, headers=h)
    )
    assert removed["succeeded"] == 1
    assert (
        _ok(client.get("/api/v1/contacts", params={"tag": f"q12-{RUN}"}, headers=h))["total"] == 0
    )

    prop = _property(client, h, "923", "rental")
    report = _ok(
        client.post(
            "/api/v1/properties/bulk",
            json={"ids": [prop["id"], unknown], "action": "set_consumption_info", "value": True},
            headers=h,
        )
    )
    assert (report["succeeded"], report["failed"]) == (1, 1)
    assert report["items"][0]["ok"] is True

    _owner(client, h, prop["id"])
    unit = _unit(client, h, prop["id"], "01")
    contact = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "M", "last_name": f"Mieter {RUN}"},
            headers=h,
        ),
        201,
    )
    party = _ok(
        client.post(
            "/api/v1/parties", json={"members": [{"contact_id": contact["id"]}]}, headers=h
        ),
        201,
    )
    contract = _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "tenancy",
                "unit_id": unit,
                "party_id": party["id"],
                "start_date": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    cbody = {"ids": [contract["id"]], "action": "set_dunning_block", "value": True}
    assert client.post("/api/v1/contracts/bulk", json=cbody, headers=h).status_code == 422
    report = _ok(
        client.post("/api/v1/contracts/bulk", json={**cbody, "reason": "Ratenzahlung"}, headers=h)
    )
    assert report["succeeded"] == 1
    row = _ok(client.get(f"/api/v1/contracts/{contract['id']}", headers=h))
    assert row["dunning_block"] is True
    assert row["dunning_block_reason"] == "Ratenzahlung"
    # Foreign tenant: the contract is not found there, reported per item.
    report = _ok(client.post("/api/v1/contracts/bulk", json={**cbody, "reason": "x"}, headers=ho))
    assert (report["succeeded"], report["failed"]) == (0, 1)
    updated = _events(database, redis_url, world.tenant_a, "contract.updated")
    assert any(e.entity_id == uuid.UUID(contract["id"]) for e in updated)

    # S12-01: work_order.created and document.shared.
    order = _ok(
        client.post(
            "/api/v1/work-orders",
            json={
                "property_id": prop["id"],
                "provider_contact_id": mine["id"],
                "description": "Heizung prüfen",
            },
            headers=h,
        ),
        201,
    )
    created = _events(database, redis_url, world.tenant_a, "work_order.created")
    assert [e.entity_id for e in created] == [uuid.UUID(order["id"])]
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("q12.pdf", b"%PDF-1.4\n%q12\n", "application/pdf")},
            headers=h,
        ),
        201,
    )
    _ok(
        client.patch(f"/api/v1/documents/{doc['id']}", json={"visibility": ["internal"]}, headers=h)
    )
    assert _events(database, redis_url, world.tenant_a, "document.shared") == []
    _ok(client.patch(f"/api/v1/documents/{doc['id']}", json={"visibility": ["owner"]}, headers=h))
    shared = _events(database, redis_url, world.tenant_a, "document.shared")
    assert len(shared) == 1
    assert shared[0].payload["roles"] == "owner"


def test_job_switch_skips_tenant(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from mhvp.workspace.tasks import deadlines_once

    settings = _settings(database, redis_url)
    before = asyncio.run(deadlines_once(settings))["tenants"]
    h = bearer(login(client, world, "q12admin"))
    _ok(
        client.put(
            "/api/v1/automation/job-schedules/workspace-compliance-deadlines",
            json={"enabled": False},
            headers=h,
        )
    )
    after = asyncio.run(deadlines_once(settings))["tenants"]
    assert after == before - 1
