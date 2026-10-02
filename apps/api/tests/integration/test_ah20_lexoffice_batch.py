"""AH20 (GAG-39): lexoffice ``links/push-batch`` and ``invoice-copies/{id}/link-recipient``.

Own world (prefix ``ah20lx``). Expected results: only linked, synced or error links of the
given contacts are queued; permission ``contacts:update`` is required (403), a foreign tenant
sees neither config nor request (404), bodies are validated (422), a request without a
Lexware contact on the invoice is refused (409), the recipient link is created otherwise.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.integrations import lexoffice_async as la
from mhvp.integrations.lexoffice_ext import ratelimit
from mhvp.integrations.lexoffice_ext import tasks as lx_tasks
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.properties.models import LegalEntity, LegalEntityKind
from tests.integration.conftest import Database
from tests.integration.test_lexoffice_ext import (
    BUCKET,
    L,
    _admin,
    _configure,
    _contact,
    _links,
    _ok,
    _settings,
    match,
    process,
)
from tests.integration.test_m2_platform import PASSWORD, RUN, World
from tests.lexoffice_fake import FakeLexoffice

pytestmark = pytest.mark.integration


async def _world(settings: Settings) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"ah20lx-a-{RUN}", name=f"AH20 LX A {RUN}"
        )
        b, _ = await services.provision_tenant(
            factory, slug=f"ah20lx-b-{RUN}", name=f"AH20 LX B {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("ah20lxadmin", "tenant_admin", a),
            ("ah20lxcare", "caretaker", a),
            ("ah20lxadminb", "tenant_admin", b),
        ]:
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
        for tenant in (a, b):
            async with tenant_transaction(factory, tenant) as session:
                session.add(
                    LegalEntity(
                        tenant_id=tenant,
                        kind=LegalEntityKind.MANAGER,
                        name=f"Verwaltung {tenant.hex[:4]}",
                    )
                )
        return world
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    return asyncio.run(_world(_settings(database, redis_url)))


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeLexoffice:
    server = FakeLexoffice()
    monkeypatch.setattr(la, "TRANSPORT", server.transport())
    monkeypatch.setattr(lx_tasks, "_send", lambda *a, **k: None)
    monkeypatch.setattr(ratelimit, "SLOT_SECONDS", 0.0)
    ratelimit.reset_local()
    return server


@pytest.fixture
def settings(database: Database, redis_url: str) -> Settings:
    return _settings(database, redis_url)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(settings)) as test_client:
            yield test_client


def _linked_contact(
    client: TestClient,
    world: World,
    fake: FakeLexoffice,
    settings: Settings,
    h: dict[str, str],
    config_id: str,
    last: str,
) -> Any:
    contact = _contact(client, h, last, f"{last.lower()}-{RUN}@example.org")
    fake.add_contact(
        person={"firstName": "Hardy", "lastName": last},
        emails={"business": [f"{last.lower()}-{RUN}@example.org"]},
    )
    started = _ok(client.post(f"{L}/configs/{config_id}/contacts/match", json={}, headers=h), 202)
    match(settings, world.tenant_a, uuid.UUID(config_id), uuid.UUID(started["run_id"]))
    proposed = [
        x
        for x in _links(client, h, config_id, status="proposed")
        if x["contact_id"] == contact["id"]
    ]
    assert len(proposed) == 1
    _ok(
        client.post(
            f"{L}/configs/{config_id}/contacts/links/{proposed[0]['id']}/decide",
            json={"action": "link"},
            headers=h,
        )
    )
    process(settings, world.tenant_a, uuid.UUID(config_id))
    return contact


def test_push_batch_permissions_validation_and_tenant_separation(
    client: TestClient, world: World, fake: FakeLexoffice, settings: Settings
) -> None:
    h = _admin(client, world, "ah20lxadmin")
    config = _configure(client, h, fake, label="AH20 Batch", sync_contacts=True)
    cid = config["id"]
    contact = _linked_contact(client, world, fake, settings, h, cid, "Batchperson")
    url = f"{L}/configs/{cid}/contacts/links/push-batch"
    # Happy path: the linked contact is queued; an unknown contact id is ignored.
    done = _ok(
        client.post(url, json={"contact_ids": [contact["id"], str(uuid.uuid4())]}, headers=h)
    )
    assert done == {"queued": 1}
    assert _ok(client.post(url, json={"contact_ids": [str(uuid.uuid4())]}, headers=h)) == {
        "queued": 0
    }
    # Permission (caretaker has no contacts:update), authentication, validation.
    care = _admin(client, world, "ah20lxcare")
    assert client.post(url, json={"contact_ids": [contact["id"]]}, headers=care).status_code == 403
    assert client.post(url, json={"contact_ids": [contact["id"]]}).status_code == 401
    assert client.post(url, json={"contact_ids": []}, headers=h).status_code == 422
    assert client.post(url, json={"contact_ids": ["kein-uuid"]}, headers=h).status_code == 422
    assert (
        client.post(url, json={"contact_ids": [contact["id"]], "x": 1}, headers=h).status_code
        == 422
    )
    # Tenant separation: another tenant gets 404 for this config; unknown config is 404.
    other = _admin(client, world, "ah20lxadminb")
    assert client.post(url, json={"contact_ids": [contact["id"]]}, headers=other).status_code == 404
    unknown = f"{L}/configs/{uuid.uuid4()}/contacts/links/push-batch"
    assert client.post(unknown, json={"contact_ids": [contact["id"]]}, headers=h).status_code == 404


def test_link_recipient_permissions_errors_and_happy_path(
    client: TestClient, world: World, fake: FakeLexoffice, settings: Settings
) -> None:
    h = _admin(client, world, "ah20lxadmin")
    entities = {r["kind"]: r["id"] for r in _ok(client.get(f"{L}/legal-entities", headers=h))}
    mailbox = _ok(
        client.post(
            "/api/v1/mail/mailboxes",
            json={"address": f"ah20-{RUN}@example.org", "kind": "imap"},
            headers=h,
        ),
        201,
    )
    config = _configure(
        client,
        h,
        fake,
        legal_entity_id=entities["manager"],
        label="AH20 Kopie",
        mailbox_id=mailbox["id"],
        sync_contacts=True,
        invoice_copies=True,
    )
    cid = config["id"]
    recipient = _contact(client, h, "Rechnungsempfaenger", f"rempf-{RUN}@example.org")
    requester = _contact(client, h, "Anfragender", f"anfr-{RUN}@example.org")
    remote = fake.add_contact(person={"firstName": "Rita", "lastName": "Remote"})
    fake.add_invoice(voucher_number="AH20-1", contact_id=remote["id"], contact_name="Rita Remote")
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Rechnungskopie", "contact_id": requester["id"]},
            headers=h,
        ),
        201,
    )
    # Request without hit: no Lexware contact on the invoice, link-recipient is refused (409).
    empty = _ok(
        client.post(
            f"{L}/tickets/{ticket['id']}/invoice-copies",
            json={"invoice_number": "AH20-UNBEKANNT"},
            headers=h,
        ),
        201,
    )
    body = {"contact_id": recipient["id"]}
    assert (
        client.post(
            f"{L}/invoice-copies/{empty['id']}/link-recipient", json=body, headers=h
        ).status_code
        == 409
    )
    # Request with hit.
    req = _ok(
        client.post(
            f"{L}/tickets/{ticket['id']}/invoice-copies",
            json={"invoice_number": "AH20-1"},
            headers=h,
        ),
        201,
    )
    process(settings, world.tenant_a, uuid.UUID(cid))
    url = f"{L}/invoice-copies/{req['id']}/link-recipient"
    # Permission, authentication, validation, tenant separation, unknown id.
    care = _admin(client, world, "ah20lxcare")
    assert client.post(url, json=body, headers=care).status_code == 403
    assert client.post(url, json=body).status_code == 401
    assert client.post(url, json={}, headers=h).status_code == 422
    assert client.post(url, json={"contact_id": "x"}, headers=h).status_code == 422
    other = _admin(client, world, "ah20lxadminb")
    assert client.post(url, json=body, headers=other).status_code == 404
    unknown = f"{L}/invoice-copies/{uuid.uuid4()}/link-recipient"
    assert client.post(unknown, json=body, headers=h).status_code == 404
    # Happy path: the Lexware contact of the invoice is now linked to the chosen contact.
    out = _ok(client.post(url, json=body, headers=h))
    assert out["id"] == req["id"]
    links = [x for x in _links(client, h, cid) if x["contact_id"] == recipient["id"]]
    assert len(links) == 1
    assert links[0]["lexoffice_contact_id"] == remote["id"]
