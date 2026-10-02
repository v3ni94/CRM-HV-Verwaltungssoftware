"""AF21 (wave 17): GAB-05 import undo preview (dry run, nothing written), GAB-16 bulk endpoints
for units and document links (partial success report, no money effect), GAC-08 portal change
accepted emits contact.updated with field names for subscribers."""

import asyncio
import uuid
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import func, select

from mhvp.ai.models import ImportRun, ImportRunItem, ImportStatus
from mhvp.contacts.models import Contact
from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import DomainEvent
from mhvp.core.webhooks import WebhookDelivery, WebhookSubscription, enqueue_deliveries
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m5_contracts import _party, _unit
from tests.integration.test_m8_import import BUCKET, _settings
from tests.integration.test_m21_portal import _contact_of, _portal_user

pytestmark = pytest.mark.integration
P = "/api/v1/portal"
PA = "/api/v1/portal-admin"


async def _world(settings: Any) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"af21a-{RUN}", name=f"AF21 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"af21b-{RUN}", name=f"AF21 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("af21admin", a, "tenant_admin"),
            ("af21view", a, "read_only"),
            ("af21other", b, "tenant_admin"),
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


def _db(
    database: Database,
    redis_url: str,
    tenant_id: uuid.UUID,
    work: Callable[[Any], Coroutine[Any, Any, Any]],
) -> Any:
    settings = _settings(database, redis_url)

    async def go() -> Any:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _property(c: TestClient, h: dict[str, str], number: str) -> dict[str, Any]:
    return _ok(
        c.post(
            "/api/v1/properties",
            json={"number": number, "name": f"AF21-{number}", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )


def test_undo_preview_matches_undo_and_writes_nothing(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    admin = bearer(login(client, world, "af21admin"))
    view = bearer(login(client, world, "af21view"))
    other = bearer(login(client, world, "af21other"))
    _, bound = _party(client, admin, "Gebunden")  # contact is member of a party: stays
    free = _ok(
        client.post(
            "/api/v1/contacts",
            json={"kind": "person", "first_name": "Frei", "last_name": f"Test{RUN}"},
            headers=admin,
        ),
        201,
    )

    async def seed(session: Any) -> uuid.UUID:
        run = ImportRun(
            tenant_id=world.tenant_a,
            source="ai:extract_contacts",
            status=ImportStatus.APPLIED,
            document_ids=[],
            summary={},
        )
        session.add(run)
        await session.flush()
        for seq, contact_id in enumerate([uuid.UUID(bound["id"]), uuid.UUID(free["id"])], 1):
            session.add(
                ImportRunItem(
                    tenant_id=world.tenant_a,
                    import_run_id=run.id,
                    sequence=seq,
                    entity_type="contact",
                    entity_id=contact_id,
                )
            )
        return run.id

    run_id = str(_db(database, redis_url, world.tenant_a, seed))
    url = f"/api/v1/imports/{run_id}/undo-preview"
    preview = _ok(client.get(url, headers=admin))
    assert (preview["removable"], preview["kept"]) == (1, 1)
    by_id = {i["entity_id"]: i for i in preview["items"]}
    assert by_id[free["id"]]["removable"] is True
    assert by_id[free["id"]]["kept_reason"] is None
    assert by_id[bound["id"]]["removable"] is False
    assert by_id[bound["id"]]["kept_reason"] == "Mitglied einer Vertragspartei"
    # Dry run: the contact still exists, the run is untouched and no undo event was written.
    assert _ok(client.get(f"/api/v1/contacts/{free['id']}", headers=admin))["id"] == free["id"]
    run = _ok(client.get(f"/api/v1/imports/{run_id}", headers=admin))
    assert run["status"] == "applied"
    assert all(not i["undone"] and i["kept_reason"] is None for i in run["items"])
    assert _ok(client.get(url, headers=admin)) == preview  # repeatable
    # The real undo agrees with the preview.
    undone = _ok(client.post(f"/api/v1/imports/{run_id}/undo", headers=admin))
    assert undone["status"] == "partially_undone"
    assert {i["entity_id"]: i["kept_reason"] for i in undone["items"] if i["kept_reason"]} == {
        bound["id"]: "Mitglied einer Vertragspartei"
    }
    # A finished run, authorization, tenant separation, unknown id and unknown parameter.
    assert (
        client.get(f"/api/v1/imports/{uuid.uuid4()}/undo-preview", headers=admin).status_code == 404
    )
    assert client.get(url, headers=view).status_code == 403
    assert client.get(url, headers=other).status_code == 404
    assert client.get(url, params={"x": "1"}, headers=admin).status_code == 422


def test_bulk_units_partial_success_and_guards(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "af21admin"))
    view = bearer(login(client, world, "af21view"))
    other = bearer(login(client, world, "af21other"))
    prop = _property(client, admin, "921")
    u1, u2 = _unit(client, admin, prop["id"], "01"), _unit(client, admin, prop["id"], "02")
    missing = str(uuid.uuid4())
    report = _ok(
        client.post(
            "/api/v1/units/bulk",
            json={"ids": [u1, u2, missing, u1], "action": "set_floor", "value": "2. OG"},
            headers=admin,
        )
    )
    assert (report["total"], report["succeeded"], report["failed"]) == (3, 2, 1)
    failed = next(i for i in report["items"] if not i["ok"])
    assert failed["id"] == missing
    assert failed["code"]
    for unit_id in (u1, u2):
        unit = _ok(client.get(f"/api/v1/units/{unit_id}", headers=admin))
        assert unit["floor"] == "2. OG"
        assert unit["version"] == 2
    # Same value again: nothing changes (no new version), still reported as success.
    again = _ok(
        client.post(
            "/api/v1/units/bulk",
            json={"ids": [u1], "action": "set_floor", "value": "2. OG"},
            headers=admin,
        )
    )
    assert again["succeeded"] == 1
    assert _ok(client.get(f"/api/v1/units/{u1}", headers=admin))["version"] == 2
    cleared = _ok(
        client.post("/api/v1/units/bulk", json={"ids": [u1], "action": "set_floor"}, headers=admin)
    )
    assert cleared["succeeded"] == 1
    assert _ok(client.get(f"/api/v1/units/{u1}", headers=admin))["floor"] is None
    # Tenant separation: units of another tenant are not found.
    foreign = _ok(
        client.post(
            "/api/v1/units/bulk",
            json={"ids": [u2], "action": "set_floor", "value": "X"},
            headers=other,
        )
    )
    assert (foreign["succeeded"], foreign["failed"]) == (0, 1)
    assert _ok(client.get(f"/api/v1/units/{u2}", headers=admin))["floor"] == "2. OG"
    # Authorization, validation (no money field is offered).
    body = {"ids": [u1], "action": "set_floor", "value": "1"}
    assert client.post("/api/v1/units/bulk", json=body, headers=view).status_code == 403
    for bad in (
        {"ids": [u1], "action": "set_living_area", "value": "50"},
        {"ids": [], "action": "set_floor"},
        {"ids": [u1], "action": "set_floor", "extra": 1},
        {"ids": [u1], "action": "set_floor", "value": "x" * 21},
    ):
        assert client.post("/api/v1/units/bulk", json=bad, headers=admin).status_code == 422


def test_bulk_document_links(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "af21admin"))
    view = bearer(login(client, world, "af21view"))
    other = bearer(login(client, world, "af21other"))
    prop = _property(client, admin, "922")
    docs = [
        str(
            _ok(
                client.post(
                    "/api/v1/documents",
                    files={"file": (f"af21-{n}.txt", f"AF21 {n} {RUN}".encode(), "text/plain")},
                    headers=admin,
                ),
                201,
            )["id"]
        )
        for n in range(3)
    ]
    body = {"ids": [docs[0], docs[1], str(uuid.uuid4())], "entity_type": "property"}
    body["entity_id"] = prop["id"]
    report = _ok(client.post("/api/v1/documents/bulk-link", json=body, headers=admin))
    assert (report["total"], report["succeeded"], report["failed"]) == (3, 2, 1)
    for doc_id in docs[:2]:
        links = _ok(client.get(f"/api/v1/documents/{doc_id}", headers=admin))["links"]
        assert [(x["entity_type"], x["entity_id"], x["role"]) for x in links] == [
            ("property", prop["id"], "attachment")
        ]
    assert _ok(client.get(f"/api/v1/documents/{docs[2]}", headers=admin))["links"] == []
    # A second run reports the existing links as conflicts and links the remaining one.
    second = _ok(
        client.post(
            "/api/v1/documents/bulk-link", json={**body, "ids": [docs[0], docs[2]]}, headers=admin
        )
    )
    assert (second["succeeded"], second["failed"]) == (1, 1)
    assert next(i for i in second["items"] if not i["ok"])["id"] == docs[0]
    # Authorization, tenant separation (target and documents), validation.
    assert client.post("/api/v1/documents/bulk-link", json=body, headers=view).status_code == 403
    cross = client.post("/api/v1/documents/bulk-link", json=body, headers=other)
    assert cross.status_code in (404, 422)
    bad_target = {**body, "entity_id": str(uuid.uuid4())}
    assert client.post(
        "/api/v1/documents/bulk-link", json=bad_target, headers=admin
    ).status_code in (
        404,
        422,
    )
    assert (
        client.post(
            "/api/v1/documents/bulk-link", json={**body, "role": "original"}, headers=admin
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/documents/bulk-link", json={**body, "ids": []}, headers=admin
        ).status_code
        == 422
    )


def test_portal_change_emits_contact_updated_for_subscribers(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    admin = bearer(login(client, world, "af21admin"))
    prop = _property(client, admin, "923")
    unit = _unit(client, admin, prop["id"], "01")
    party, _ = _party(client, admin, "Portal")
    _ok(
        client.post(
            "/api/v1/contracts",
            json={
                "kind": "ownership",
                "unit_id": unit,
                "party_id": party,
                "start_date": "2020-01-01",
                "title_transfer_date": "2020-01-01",
                "acquisition_kind": "first_acquisition",
            },
            headers=admin,
        ),
        201,
    )
    contact_id = _contact_of(client, admin, party)
    owner = _portal_user(client, admin, world, "af21owner", contact_id)

    async def subscribe(session: Any) -> None:
        session.add(
            WebhookSubscription(
                tenant_id=world.tenant_a,
                url="https://hooks.example.test/af21",
                event_types=["contact.updated"],
                secret="s" * 32,
            )
        )

    _db(database, redis_url, world.tenant_a, subscribe)
    address = _ok(
        client.post(
            f"{P}/change-requests",
            json={
                "kind": "address",
                "payload": {
                    "street": "Musterweg",
                    "house_number": "1",
                    "postal_code": "40213",
                    "city": "Musterstadt",
                    "valid_from": "2026-09-01",
                },
            },
            headers=owner,
        ),
        201,
    )
    rejected = _ok(
        client.post(
            f"{P}/change-requests",
            json={"kind": "email", "payload": {"email": f"af21-no-{RUN}@example.invalid"}},
            headers=owner,
        ),
        201,
    )
    accepted = _ok(
        client.post(
            f"{P}/change-requests",
            json={"kind": "email", "payload": {"email": f"af21-{RUN}@example.invalid"}},
            headers=owner,
        ),
        201,
    )
    _ok(
        client.post(
            f"{PA}/change-requests/{rejected['id']}/decide", json={"accept": False}, headers=admin
        )
    )
    _ok(
        client.post(
            f"{PA}/change-requests/{address['id']}/decide", json={"accept": True}, headers=admin
        )
    )
    _ok(
        client.post(
            f"{PA}/change-requests/{accepted['id']}/decide", json={"accept": True}, headers=admin
        )
    )

    async def read(session: Any) -> tuple[list[dict[str, Any]], int, int]:
        events = (
            await session.scalars(
                select(DomainEvent).where(
                    DomainEvent.type == "contact.updated",
                    DomainEvent.entity_id == uuid.UUID(contact_id),
                )
            )
        ).all()
        queued = await enqueue_deliveries(session, world.tenant_a)
        deliveries = await session.scalar(select(func.count()).select_from(WebhookDelivery))
        return [e.payload for e in events], queued, deliveries or 0

    payloads, queued, deliveries = _db(database, redis_url, world.tenant_a, read)
    portal = [p for p in payloads if p.get("source") == "portal"]
    assert sorted(f for p in portal for f in p["fields"]) == ["addresses", "emails"]
    assert {p["change_request_id"] for p in portal} == {address["id"], accepted["id"]}
    assert "Musterweg" not in str(portal)  # field names only, never values
    assert "example.invalid" not in str(portal)
    assert queued >= 2
    assert deliveries >= 2
    # The rejected request emits nothing; the other tenant sees none of it.
    assert rejected["id"] not in {p.get("change_request_id") for p in portal}

    async def foreign(session: Any) -> int:
        return int(
            await session.scalar(
                select(func.count()).select_from(Contact).where(Contact.id == uuid.UUID(contact_id))
            )
            or 0
        )

    assert _db(database, redis_url, world.tenant_b, foreign) == 0
