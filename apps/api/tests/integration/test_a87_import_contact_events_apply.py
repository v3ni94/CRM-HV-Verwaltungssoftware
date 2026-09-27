"""A87, second part: the staging import (`mhvp/imports/services.py`, `_apply_contact`) and the
objektakte differential import emit the same contact events as the manual API
(`contact.created`; `contact.updated` with field names only, values in the audit log). A test
run or preview leaves no event behind, a repeated apply emits nothing, and the events stay
inside the tenant."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import select

from mhvp.contacts.models import Contact
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import AuditLog, DomainEvent
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings

pytestmark = pytest.mark.integration
BUCKET = "mhvp-a87"
IMPORTS = "/api/v1/imports/immoware24"
SYNC = "/api/v1/objektakte/sync"
OBJEKTAKTE = "/api/v1/objektakte/imports"

CONTACT_COLUMNS = {
    "external_id": "ID",
    "kind": "Art",
    "first_name": "Vorname",
    "last_name": "Name",
    "company_name": "Firma",
}
CONTACTS_CSV = (
    f"ID;Art;Vorname;Name;Firma\nA87-1;P;Anna;Staging{RUN};\nA87-2;F;;;Staging {RUN} GmbH\n"
).encode()

_OBJECT = """
INSERT INTO `objects_managedobject` (`id`,`object_number`,`name`,`street`,`house_number`,
`postal_code`,`city`,`management_type`,`updated_at`)
VALUES (21,'871','Haus A87','Ereignisweg','1','40721','Hilden','weg','2026-09-01 08:00:00');
"""


def _owner(last_name: str, updated_at: str) -> str:
    return f"""
INSERT INTO `parties_owner` (`id`,`type`,`first_name`,`last_name`,`company_name`,`search_name`,
`updated_at`)
VALUES (301,'natural_person','Erika','{last_name}',NULL,'{last_name}, Erika','{updated_at}');
"""


DUMP_V1 = _OBJECT + _owner("Musterfrau", "2026-09-01 08:00:00")
DUMP_V2 = _OBJECT + _owner("Beispiel", "2026-09-05 08:00:00")


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
    )


async def _world(settings: Settings) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"a87c-{RUN}", name=f"A87 C {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"a87d-{RUN}", name=f"A87 D {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in (("a87admin", a), ("a87other", b)):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory,
                tenant_id=tenant,
                user_id=uid,
                role_codes=["tenant_admin"],
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
    return response.json()


async def _read_events(
    settings: Settings, tenant_id: uuid.UUID, source: str
) -> list[tuple[DomainEvent, AuditLog | None]]:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            events = list(
                (
                    await session.scalars(
                        select(DomainEvent)
                        .where(
                            DomainEvent.entity_type == "contact",
                            DomainEvent.payload["source"].astext == source,
                        )
                        .order_by(DomainEvent.occurred_at, DomainEvent.id)
                    )
                ).all()
            )
            out = []
            for event in events:
                audit = await session.scalar(select(AuditLog).where(AuditLog.event_id == event.id))
                out.append((event, audit))
            return out
    finally:
        await engine.dispose()


def _events(
    database: Database, redis_url: str, tenant_id: uuid.UUID, source: str
) -> list[tuple[DomainEvent, AuditLog | None]]:
    return asyncio.run(_read_events(_settings(database, redis_url), tenant_id, source))


async def _contact_by_source(settings: Settings, tenant_id: uuid.UUID, source_id: str) -> Contact:
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            contact = await session.scalar(
                select(Contact).where(
                    Contact.source_system == "objektakte", Contact.source_id == source_id
                )
            )
            assert contact is not None
            session.expunge(contact)
            return contact
    finally:
        await engine.dispose()


# Staging import ---------------------------------------------------------------------------


def _stage_contacts(client: TestClient, h: dict[str, str]) -> Any:
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": ("adressbuch.csv", CONTACTS_CSV, "text/csv")},
            headers=h,
        ),
        201,
    )
    source = _ok(
        client.post(
            f"{IMPORTS}/files",
            json={"document_id": doc["id"], "report_type": "contacts"},
            headers=h,
        ),
        201,
    )
    mapping = _ok(
        client.post(
            f"{IMPORTS}/mappings",
            json={
                "report_type": "contacts",
                "name": f"A87 {RUN} {uuid.uuid4().hex[:6]}",
                "columns": CONTACT_COLUMNS,
                "value_maps": {"kind": {"P": "person", "F": "company"}},
            },
            headers=h,
        ),
        201,
    )
    _ok(
        client.post(
            f"{IMPORTS}/files/{source['id']}/validate",
            json={"mapping_id": mapping["id"]},
            headers=h,
        )
    )
    return source


def test_staging_import_emits_contact_created_only_on_apply(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "a87admin", world.tenant_a))
    source = _stage_contacts(client, h)

    # Test run: same report as the apply, but the savepoint is rolled back, so no event.
    dry = _ok(client.post(f"{IMPORTS}/files/{source['id']}/test-run", headers=h))
    assert dry["test_run"] is True
    assert dry["counts"] == {"created": 2}
    assert _events(database, redis_url, world.tenant_a, "import.staging") == []

    applied = _ok(client.post(f"{IMPORTS}/files/{source['id']}/apply", headers=h), 201)
    assert applied["report"]["apply"]["counts"] == {"created": 2}
    events = _events(database, redis_url, world.tenant_a, "import.staging")
    assert [e.type for e, _ in events] == ["contact.created", "contact.created"]
    assert sorted(e.payload["kind"] for e, _ in events) == ["company", "person"]
    assert all(e.payload.keys() == {"kind", "source"} for e, _ in events)
    assert all(e.tenant_id == world.tenant_a for e, _ in events)
    assert all(e.actor_user_id == world.users["a87admin"] for e, _ in events)
    assert all(audit is None for _, audit in events)

    # Idempotent: the same file staged and applied again finds the contacts (unchanged) and
    # emits nothing; existing contacts are never overwritten by this import.
    again = _stage_contacts(client, h)
    applied_again = _ok(client.post(f"{IMPORTS}/files/{again['id']}/apply", headers=h), 201)
    assert applied_again["report"]["apply"]["counts"] == {"unchanged": 2}
    assert len(_events(database, redis_url, world.tenant_a, "import.staging")) == 2

    # Tenant separation: the other tenant sees no event of this import.
    assert _events(database, redis_url, world.tenant_b, "import.staging") == []


# objektakte differential import -----------------------------------------------------------


def _sync(client: TestClient, h: dict[str, str], dump: str) -> Any:
    return _ok(
        client.post(
            f"{SYNC}/runs",
            files={"file": ("objektakte.sql", dump.encode("utf-8"), "application/sql")},
            headers=h,
        )
    )


def test_objektakte_import_emits_contact_events_only_on_apply(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "a87admin", world.tenant_a))
    settings = _settings(database, redis_url)

    # Preview of the manual upload changes nothing and emits nothing.
    preview = _ok(
        client.post(
            OBJEKTAKTE,
            params={"mode": "preview"},
            files={"file": ("objektakte.sql", DUMP_V1.encode("utf-8"), "application/sql")},
            headers=h,
        )
    )
    assert preview["mode"] == "preview"
    assert _events(database, redis_url, world.tenant_a, "import.objektakte") == []

    first = _sync(client, h, DUMP_V1)
    assert first["created"]["contact"] == 1
    events = _events(database, redis_url, world.tenant_a, "import.objektakte")
    assert [e.type for e, _ in events] == ["contact.created"]
    created, created_audit = events[0]
    assert created.payload == {"kind": "person", "source": "import.objektakte"}
    assert created.actor_user_id == world.users["a87admin"]
    assert created_audit is None
    contact = asyncio.run(_contact_by_source(settings, world.tenant_a, "301"))
    assert created.entity_id == contact.id
    assert contact.version == 1

    # Idempotent: the same export again (rows at the water mark are re-read) emits nothing.
    second = _sync(client, h, DUMP_V1)
    assert second["created"] == {}
    assert second["updated"] == {}
    assert len(_events(database, redis_url, world.tenant_a, "import.objektakte")) == 1

    # A changed owner row newer than the water mark: contact.updated with field names only in
    # the payload, old and new values in the audit log, version bump as in PUT /contacts/{id}.
    third = _sync(client, h, DUMP_V2)
    assert third["updated"] == {"parties_owner": 1}
    events = _events(database, redis_url, world.tenant_a, "import.objektakte")
    assert [e.type for e, _ in events] == ["contact.created", "contact.updated"]
    updated, audit = events[-1]
    assert updated.entity_id == contact.id
    assert updated.payload == {
        "fields": ["display_name", "last_name"],
        "source": "import.objektakte",
    }
    assert audit is not None
    assert audit.changes == {
        "last_name": {"old": "Musterfrau", "new": "Beispiel"},
        "display_name": {"old": contact.display_name, "new": "Erika Beispiel"},
    }
    assert asyncio.run(_contact_by_source(settings, world.tenant_a, "301")).version == 2

    fourth = _sync(client, h, DUMP_V2)
    assert fourth["updated"] == {}
    assert len(_events(database, redis_url, world.tenant_a, "import.objektakte")) == 2

    # Tenant separation: nothing of this is visible from the other tenant; its own run emits
    # its own event only.
    other = bearer(login(client, world, "a87other", world.tenant_b))
    assert _events(database, redis_url, world.tenant_b, "import.objektakte") == []
    _sync(client, other, DUMP_V1)
    events_b = _events(database, redis_url, world.tenant_b, "import.objektakte")
    assert [e.type for e, _ in events_b] == ["contact.created"]
    assert events_b[0][0].entity_id != contact.id
    assert len(_events(database, redis_url, world.tenant_a, "import.objektakte")) == 2
