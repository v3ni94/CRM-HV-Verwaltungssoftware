"""Lexware Office extension (rule INT-LEXO-01) against the in-process fake server
(``tests/lexoffice_fake.py``): configs per legal entity with AVV and connection test, invoice
kind to legal entity mapping, contact matching and decisions, one way push with version
conflict and content conflict, queue retry (429, 503) and token invalidation, invoice copy
with recipient verification and recipient lock, invoice drafts, recurring preparation,
permissions (403), tenant separation and the forbidden field guarantee."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.communication.models import Message
from mhvp.core.config import Settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.documents.blobs import BlobStore
from mhvp.integrations import lexoffice_async as la
from mhvp.integrations.lexoffice_ext import matching, ratelimit
from mhvp.integrations.lexoffice_ext import services as svc
from mhvp.integrations.lexoffice_ext import tasks as lx_tasks
from mhvp.integrations.models import (
    LexofficeContactLink,
    LexofficeInvoiceCopyRequest,
    LexofficeOutbox,
    LexofficeSyncRun,
    LexofficeTenantConfig,
)
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.properties.models import LegalEntity, LegalEntityKind
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.lexoffice_fake import BASE, FakeLexoffice

pytestmark = pytest.mark.integration
L = "/api/v1/integrations/lexoffice"
BUCKET = "mhvp-lexoffice"
FORBIDDEN = ("iban", "bic", "bank", "mandate", "taxnumber", "vatregistrationid")


def _settings(database: Database, redis_url: str) -> Settings:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        ai_inline=True,
    )


async def _world(settings: Settings) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"lx-a-{RUN}", name=f"LX A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"lx-b-{RUN}", name=f"LX B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, role, tenant in [
            ("lxoadmin", "tenant_admin", a),
            ("lxoadmin2", "tenant_admin", a),
            ("lxosupport", "support", a),
            ("lxocare", "caretaker", a),
            ("lxoadminb", "tenant_admin", b),
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
                session.add(
                    LegalEntity(
                        tenant_id=tenant,
                        kind=LegalEntityKind.RENTAL_OWNER,
                        name=f"Makler {tenant.hex[:4]}",
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


def run_tenant(
    settings: Settings, tenant_id: uuid.UUID, work: Callable[[AsyncSession], Awaitable[Any]]
) -> Any:
    async def _go() -> Any:
        engine = create_async_engine(settings.database_url.get_secret_value(), poolclass=NullPool)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def process(settings: Settings, tenant_id: uuid.UUID, config_id: uuid.UUID) -> dict[str, int]:
    blobs = BlobStore(settings)

    async def _work(session: AsyncSession) -> dict[str, int]:
        config = await session.get(LexofficeTenantConfig, config_id)
        assert config is not None
        return await svc.process_outbox(session, tenant_id, config, settings, blobs=blobs)

    out: dict[str, int] = run_tenant(settings, tenant_id, _work)
    return out


def match(
    settings: Settings, tenant_id: uuid.UUID, config_id: uuid.UUID, run_id: uuid.UUID
) -> dict[str, int]:
    async def _work(session: AsyncSession) -> dict[str, int]:
        config = await session.get(LexofficeTenantConfig, config_id)
        run = await session.get(LexofficeSyncRun, run_id)
        assert config is not None
        assert run is not None
        client = svc.client_for(config, settings)
        return await matching.run_match(session, tenant_id, config, client, run)

    out: dict[str, int] = run_tenant(settings, tenant_id, _work)
    return out


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _admin(client: TestClient, world: World, name: str = "lxoadmin") -> dict[str, str]:
    return bearer(login(client, world, name))


def _entities(client: TestClient, h: dict[str, str]) -> dict[str, str]:
    rows = _ok(client.get(f"{L}/legal-entities", headers=h))
    return {r["kind"]: r["id"] for r in rows}


def _configure(
    client: TestClient,
    h: dict[str, str],
    fake: FakeLexoffice,
    *,
    legal_entity_id: str | None = None,
    label: str = "HVM",
    mailbox_id: str | None = None,
    **switches: bool,
) -> Any:
    """Create (or reuse the config of that legal entity), test, then enable with switches
    (the documented order)."""
    body: dict[str, Any] = {
        "legal_entity_id": legal_entity_id,
        "label": label,
        "api_key": fake.api_key,
        "base_url": BASE,
        "avv_confirmed_on": "2026-09-28",
        "avv_note": "AVV vom 28.09.2026",
        "enabled": False,
    }
    if mailbox_id:
        body["mailbox_id"] = mailbox_id
    existing = [
        c
        for c in _ok(client.get(f"{L}/configs", headers=h))
        if c["legal_entity_id"] == legal_entity_id
    ]
    if existing:
        body.pop("legal_entity_id")
        created = _ok(client.put(f"{L}/configs/{existing[0]['id']}", json=body, headers=h))
    else:
        created = _ok(client.post(f"{L}/configs", json=body, headers=h), 201)
    _ok(client.post(f"{L}/configs/{created['id']}/test", headers=h))
    update = {
        "label": label,
        "avv_note": "AVV vom 28.09.2026",
        "enabled": True,
        "sync_contacts": switches.get("sync_contacts", True),
        "sync_names": switches.get("sync_names", False),
        "invoice_copies": switches.get("invoice_copies", False),
        "invoice_drafts": switches.get("invoice_drafts", False),
    }
    return _ok(client.put(f"{L}/configs/{created['id']}", json=update, headers=h))


def _contact(client: TestClient, h: dict[str, str], last: str, email: str, **extra: Any) -> Any:
    body = {
        "kind": "person",
        "first_name": "Hardy",
        "last_name": last,
        "addresses": [
            {
                "label": "postal",
                "street": "Hauptstraße",
                "house_number": "5",
                "postal_code": "40721",
                "city": "Hilden",
                "country": "DE",
                "is_primary": True,
            }
        ],
        "emails": [{"label": "work", "email": email, "is_primary": True}],
        "phones": [{"label": "mobile", "number": "+491701234567", "is_primary": True}],
        **extra,
    }
    return _ok(client.post("/api/v1/contacts", json=body, headers=h), 201)


def _patch_contact(client: TestClient, h: dict[str, str], contact: Any, **fields: Any) -> Any:
    """Person applied change through ``PUT /contacts/{id}`` (children keep the PUT route)."""
    current = _ok(client.get(f"/api/v1/contacts/{contact['id']}", headers=h))
    body: dict[str, Any] = {
        key: current[key]
        for key in (
            "kind",
            "salutation",
            "first_name",
            "last_name",
            "company_name",
            "language",
            "external_ids",
            "types",
            "roles",
            "tags",
        )
    }
    for key in ("addresses", "phones", "emails"):
        body[key] = [{k: v for k, v in item.items() if k != "id"} for item in current[key]]
    body.update(fields)
    return _ok(
        client.put(
            f"/api/v1/contacts/{contact['id']}",
            json=body,
            headers={**h, "If-Match": f'"{current["version"]}"'},
        )
    )


def _links(client: TestClient, h: dict[str, str], config_id: str, **params: Any) -> list[Any]:
    items: list[Any] = _ok(
        client.get(f"{L}/configs/{config_id}/contacts/links", params=params, headers=h)
    )["items"]
    return items


def _outbox(client: TestClient, h: dict[str, str], config_id: str) -> list[Any]:
    items: list[Any] = _ok(client.get(f"{L}/outbox", params={"config_id": config_id}, headers=h))[
        "items"
    ]
    return items


def _assert_no_forbidden_change(fake: FakeLexoffice) -> None:
    """No sent body carries a bank, mandate or tax key with a value different from the
    previously read remote object (rule INT-LEXO-01, forbidden field list)."""

    def forbidden_items(value: Any, path: str = "") -> dict[str, Any]:
        found: dict[str, Any] = {}
        if isinstance(value, dict):
            for key, item in value.items():
                sub = f"{path}.{key}" if path else key
                if any(f in key.lower() for f in FORBIDDEN):
                    found[sub] = item
                found.update(forbidden_items(item, sub))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                found.update(forbidden_items(item, f"{path}[{index}]"))
        return found

    for before, body in fake.put_log:
        assert forbidden_items(body) == forbidden_items(before), body
    for body in fake.bodies("POST", "/v1/contacts"):
        assert forbidden_items(body) == {}, body


# Configs -----------------------------------------------------------------------------------


def test_config_lifecycle_avv_test_key_rotation_and_permissions(
    client: TestClient, world: World, fake: FakeLexoffice, settings: Settings
) -> None:
    h = _admin(client, world)
    entities = _entities(client, h)
    # Enabling without AVV: MHVP-LEXO-0006.
    refused = client.post(
        f"{L}/configs",
        json={"label": "x", "api_key": fake.api_key, "base_url": BASE, "enabled": True},
        headers=h,
    )
    assert refused.status_code == 422
    assert refused.json()["code"] == "MHVP-LEXO-0006"
    created = _ok(
        client.post(
            f"{L}/configs",
            json={
                "legal_entity_id": entities["manager"],
                "label": "HVM",
                "api_key": fake.api_key,
                "base_url": BASE,
                "avv_confirmed_on": "2026-09-28",
                "enabled": False,
            },
            headers=h,
        ),
        201,
    )
    assert created["api_key_set"]
    assert created["api_key_last4"] == fake.api_key[-4:]
    assert fake.api_key not in json.dumps(created)
    assert created["avv_confirmed_by"] == str(world.users["lxoadmin"])
    assert created["message"] == "Verbindungstest erforderlich"
    # Duplicate legal entity: 409.
    dup = client.post(
        f"{L}/configs", json={"legal_entity_id": entities["manager"], "label": "x"}, headers=h
    )
    assert dup.status_code == 409
    # Enabling without a test: MHVP-LEXO-0014.
    no_test = client.put(f"{L}/configs/{created['id']}", json={"enabled": True}, headers=h)
    assert no_test.status_code == 422
    assert no_test.json()["code"] == "MHVP-LEXO-0014"
    tested = _ok(client.post(f"{L}/configs/{created['id']}/test", headers=h))
    assert tested["last_test_ok"] is True
    assert tested["organization_id"] == fake.organization_id
    assert tested["organization_name"] == fake.company_name
    assert tested["has_invoicing"] is True
    enabled = _ok(
        client.put(
            f"{L}/configs/{created['id']}", json={"enabled": True, "sync_contacts": True}, headers=h
        )
    )
    assert enabled["enabled"]
    assert enabled["sync_contacts"]
    # Private base URL refused (settings allow private targets in tests, so use a bad scheme).
    bad = client.put(
        f"{L}/configs/{created['id']}", json={"base_url": "ftp://x", "enabled": True}, headers=h
    )
    assert bad.status_code == 422
    # Key rotation resets organisation and disables until a new test.
    rotated = _ok(
        client.put(
            f"{L}/configs/{created['id']}",
            json={"api_key": "new-key-ab12", "enabled": True},
            headers=h,
        )
    )
    assert rotated["enabled"] is False
    assert rotated["organization_id"] is None
    assert rotated["api_key_last4"] == "ab12"
    assert rotated["message"] == "Verbindungstest erforderlich"
    # Test with the rotated (wrong) key: 401 marks the key invalid, no exception.
    failed = _ok(client.post(f"{L}/configs/{created['id']}/test", headers=h))
    assert failed["last_test_ok"] is False
    assert failed["token_invalid"] is True
    # Organisation mismatch while links exist: MHVP-LEXO-0013.
    _ok(client.put(f"{L}/configs/{created['id']}", json={"api_key": fake.api_key}, headers=h))
    _ok(client.post(f"{L}/configs/{created['id']}/test", headers=h))

    async def _link(session: AsyncSession) -> None:
        session.add(
            LexofficeContactLink(
                tenant_id=world.tenant_a,
                config_id=uuid.UUID(created["id"]),
                lexoffice_contact_id="remote-1",
                sync_status="remote_only",
            )
        )

    run_tenant(settings, world.tenant_a, _link)
    fake.organization_id = "other-org"
    mismatch = client.post(f"{L}/configs/{created['id']}/test", headers=h)
    assert mismatch.status_code == 409
    assert mismatch.json()["code"] == "MHVP-LEXO-0013"
    # Permissions: support reads, cannot write or test; caretaker cannot read.
    support = _admin(client, world, "lxosupport")
    assert _ok(client.get(f"{L}/configs", headers=support))
    assert (
        client.put(
            f"{L}/configs/{created['id']}", json={"enabled": False}, headers=support
        ).status_code
        == 403
    )
    assert client.post(f"{L}/configs/{created['id']}/test", headers=support).status_code == 403
    assert client.get(f"{L}/outbox", headers=support).status_code == 403
    assert client.get(f"{L}/configs", headers=_admin(client, world, "lxocare")).status_code == 403
    # Tenant separation.
    hb = _admin(client, world, "lxoadminb")
    assert _ok(client.get(f"{L}/configs", headers=hb)) == []
    assert client.get(f"{L}/configs/{created['id']}", headers=hb).status_code == 404
    assert _ok(client.get(f"{L}/outbox", headers=hb))["total"] == 0
    # Key stored encrypted: the raw column never contains the key.

    async def _raw(session: AsyncSession) -> Any:
        from sqlalchemy import text

        return await session.scalar(
            text("SELECT api_key FROM lexoffice_tenant_config WHERE id = :i"), {"i": created["id"]}
        )

    assert fake.api_key.encode() not in bytes(run_tenant(settings, world.tenant_a, _raw))
    # Legacy alias reads the tenant default config (none yet) with tenant_settings:read.
    assert _ok(client.get(f"{L}/config", headers=support))["enabled"] is False
    # Cleanup for the following tests: disable this config.
    _ok(client.put(f"{L}/configs/{created['id']}", json={"enabled": False}, headers=h))


def test_invoice_kind_mapping(client: TestClient, world: World, fake: FakeLexoffice) -> None:
    h = _admin(client, world)
    entities = _entities(client, h)
    kinds = {k["kind"]: k for k in _ok(client.get(f"{L}/invoice-kinds", headers=h))}
    # Seed: management maps to the manager legal entity; the others stay open.
    assert kinds["management"]["legal_entity_id"] == entities["manager"]
    assert kinds["broker"]["legal_entity_id"] is None
    assert kinds["consulting"]["legal_entity_id"] is None
    assert {k["label"] for k in kinds.values()} == {
        "Maklerrechnungen",
        "Beratung",
        "Hausverwaltung",
    }
    updated = {
        k["kind"]: k
        for k in _ok(
            client.put(
                f"{L}/invoice-kinds",
                json=[{"kind": "broker", "legal_entity_id": entities["rental_owner"]}],
                headers=h,
            )
        )
    }
    assert updated["broker"]["legal_entity_id"] == entities["rental_owner"]
    assert (
        client.put(
            f"{L}/invoice-kinds",
            json=[{"kind": "broker", "legal_entity_id": None}],
            headers=_admin(client, world, "lxosupport"),
        ).status_code
        == 403
    )
    # An unmapped kind refuses a draft with MHVP-LEXO-0017 before any call.
    draft = client.post(
        f"{L}/invoice-drafts/preview",
        json={
            "invoice_kind": "consulting",
            "voucher_date": "2026-09-29",
            "tax_type": "net",
            "line_items": [
                {
                    "name": "Beratung",
                    "quantity": "1",
                    "unit_name": "Stunde",
                    "unit_price": "100.00",
                    "tax_rate_percent": 19,
                }
            ],
            "shipping": {"type": "none"},
        },
        headers=h,
    )
    assert draft.status_code == 422
    assert draft.json()["code"] == "MHVP-LEXO-0017"
    assert fake.count("POST", "/v1/invoices") == 0


# Links and push ----------------------------------------------------------------------------


def test_match_decide_push_conflicts_and_retries(
    client: TestClient, world: World, fake: FakeLexoffice, settings: Settings
) -> None:
    h = _admin(client, world)
    fake.page_size = 2
    config = _configure(client, h, fake, label="Default", sync_contacts=True)
    cid = config["id"]
    harter = _contact(client, h, "Harter", "hardy@example.org")
    _contact(client, h, "Harter", "hardy2@example.org")  # second Harter: ambiguous by name
    muster = _contact(client, h, "Muster", "erika@example.org")
    remote_muster = fake.add_contact(
        person={"firstName": "Erika", "lastName": "Muster"},
        customer_number=10001,
        billing={"street": "Alt 1", "zip": "10115", "city": "Berlin", "countryCode": "DE"},
        emails={"private": ["erika@example.org"]},
        phones={"business": ["+4900"]},
        note="internal",
        taxNumber="123/456",
    )
    fake.add_contact(
        person={"firstName": "Hardy", "lastName": "Harter"},
        billing={"zip": "40721", "street": "H 5", "city": "Hilden", "countryCode": "DE"},
    )
    fake.add_contact(company={"name": "Nur Remote GmbH"}, customer_number=10003)
    fake.add_contact(company={"name": "Lieferant AG"}, customer_number=None, vendor_number=30001)
    started = _ok(
        client.post(
            f"{L}/configs/{cid}/contacts/match", json={"scope": "customers_and_vendors"}, headers=h
        ),
        202,
    )
    counts = match(settings, world.tenant_a, uuid.UUID(cid), uuid.UUID(started["run_id"]))
    assert counts["pages"] >= 3
    assert counts["remote"] == 4
    assert counts == {**counts, "proposed": 1, "ambiguous": 1, "remote_only": 2, "refreshed": 0}
    assert (
        client.post(
            f"{L}/configs/{cid}/contacts/match", json={}, headers=_admin(client, world, "lxocare")
        ).status_code
        == 403
    )
    proposed = _links(client, h, cid, status="proposed")
    assert len(proposed) == 1
    assert proposed[0]["contact_id"] == muster["id"]
    assert proposed[0]["match_reason"] == "email_exact"
    ambiguous = _links(client, h, cid, status="ambiguous")
    assert len(ambiguous) == 1
    assert len(ambiguous[0]["candidates"]) == 2
    # Decide: link -> refresh reads version 7 and the baseline, no PUT.
    link = _ok(
        client.post(
            f"{L}/configs/{cid}/contacts/links/{proposed[0]['id']}/decide",
            json={"action": "link"},
            headers=h,
        )
    )
    assert link["sync_status"] == "pending"
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 1
    linked = _links(client, h, cid, status="linked")
    assert linked[0]["lexoffice_version"] == 7
    assert linked[0]["customer_number"] == 10001
    assert linked[0]["deeplink"].endswith(f"/permalink/contacts/view/{remote_muster['id']}")
    assert fake.count("PUT") == 0
    again = client.post(
        f"{L}/configs/{cid}/contacts/links/{proposed[0]['id']}/decide",
        json={"action": "link"},
        headers=h,
    )
    assert again.status_code == 409
    # Dismiss writes nothing to Lexware.
    before_requests = len(fake.requests)
    _ok(
        client.post(
            f"{L}/configs/{cid}/contacts/links/{ambiguous[0]['id']}/decide",
            json={"action": "dismiss"},
            headers=h,
        )
    )
    assert len(fake.requests) == before_requests
    # PATCH address on the linked contact: one queue row with the documented key.
    muster_now = _ok(client.get(f"/api/v1/contacts/{muster['id']}", headers=h))
    patched = _patch_contact(
        client,
        h,
        muster_now,
        addresses=[
            {
                "label": "postal",
                "street": "Neue Straße",
                "house_number": "9",
                "postal_code": "40721",
                "city": "Hilden",
                "country": "DE",
                "is_primary": True,
            }
        ],
    )
    rows = [r for r in _outbox(client, h, cid) if r["kind"] == "contact_update"]
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"

    async def _key(session: AsyncSession) -> str:
        row = await session.get(LexofficeOutbox, uuid.UUID(rows[0]["id"]))
        assert row is not None
        return row.idempotency_key

    assert (
        run_tenant(settings, world.tenant_a, _key)
        == f"contact-{muster['id']}-cfg{cid}-v{patched['version']}"
    )
    # A name change without sync_names creates no row.
    patched = _patch_contact(client, h, patched, first_name="Erika-Maria")
    assert len([r for r in _outbox(client, h, cid) if r["kind"] == "contact_update"]) == 1
    # A second address change supersedes the first (fields carried along).
    patched = _patch_contact(
        client,
        h,
        patched,
        emails=[{"label": "work", "email": "erika.neu@example.org", "is_primary": True}],
    )
    rows = [r for r in _outbox(client, h, cid) if r["kind"] == "contact_update"]
    assert sorted(r["status"] for r in rows) == ["pending", "superseded"]
    # Worker: GET, merge, PUT with version 7 -> synced, version 8, only address and e mail.
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 1
    put_bodies = fake.bodies("PUT", "/v1/contacts/")
    assert len(put_bodies) == 1
    assert put_bodies[0]["version"] == 7
    assert put_bodies[0]["addresses"]["billing"] == [
        {"street": "Neue Straße 9", "zip": "40721", "city": "Hilden", "countryCode": "DE"}
    ]
    assert put_bodies[0]["emailAddresses"] == {"private": ["erika.neu@example.org"]}
    assert put_bodies[0]["person"]["firstName"] == "Erika"  # name not pushed
    assert put_bodies[0]["note"] == "internal"
    assert put_bodies[0]["taxNumber"] == "123/456"
    synced = _links(client, h, cid, status="synced")[0]
    assert synced["lexoffice_version"] == 8
    assert synced["synced_contact_version"] == patched["version"]
    sent_row = next(
        r
        for r in _outbox(client, h, cid)
        if r["status"] == "sent" and r["kind"] == "contact_update"
    )
    assert sent_row["detail"]["sent_fields"] == ["address", "email"]
    # Version conflict: the PUT meets 409 (remote edited between GET and PUT); the worker
    # re reads and sends the new version within the same attempt.
    patched = _patch_contact(
        client, h, patched, phones=[{"label": "work", "number": "+4921030000", "is_primary": True}]
    )
    fake.conflict_puts = 1
    puts_before_conflict = fake.count("PUT")
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 1
    assert fake.count("PUT") == puts_before_conflict + 2
    assert fake.bodies("PUT", "/v1/contacts/")[-2]["version"] == 8
    assert fake.bodies("PUT", "/v1/contacts/")[-1]["version"] == 9
    assert fake.bodies("PUT", "/v1/contacts/")[-1]["phoneNumbers"] == {"business": ["+4921030000"]}
    # Content conflict: remote changed the city since the baseline and differs from the CRM.
    remote_muster["addresses"]["billing"][0]["city"] = "Anderswo"
    patched = _patch_contact(
        client,
        h,
        patched,
        addresses=[
            {
                "label": "postal",
                "street": "Dritte Straße",
                "house_number": "1",
                "postal_code": "40721",
                "city": "Hilden",
                "country": "DE",
                "is_primary": True,
            }
        ],
    )
    puts_before = fake.count("PUT")
    out = process(settings, world.tenant_a, uuid.UUID(cid))
    assert out["failed"] == 1
    assert fake.count("PUT") == puts_before
    conflict = _links(client, h, cid, status="conflict")[0]
    assert conflict["conflict"]["address"]["lexoffice"]["city"] == "Anderswo"
    assert conflict["conflict"]["address"]["crm"]["city"] == "Hilden"
    # keep_lexoffice: no PUT, baseline updated, synced.
    resolved = _ok(
        client.post(
            f"{L}/configs/{cid}/contacts/links/{conflict['id']}/resolve-conflict",
            json={"resolution": "keep_lexoffice"},
            headers=h,
        )
    )
    assert resolved["sync_status"] == "synced"
    assert fake.count("PUT") == puts_before
    # Manual push then keep_crm path: force sends the CRM state.
    _ok(client.post(f"{L}/configs/{cid}/contacts/links/{conflict['id']}/push", headers=h))
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 1
    assert (
        fake.bodies("PUT", "/v1/contacts/")[-1]["addresses"]["billing"][0]["street"]
        == "Dritte Straße 1"
    )
    # 429 with Retry-After honoured, 503 retried, 401 stops the config.
    patched = _patch_contact(
        client,
        h,
        patched,
        emails=[{"label": "work", "email": "erika.drei@example.org", "is_primary": True}],
    )
    fake.fail_next.append((429, {"Retry-After": "120"}))
    out = process(settings, world.tenant_a, uuid.UUID(cid))
    assert out["retry"] == 1
    row = next(r for r in _outbox(client, h, cid) if r["status"] == "pending")
    assert datetime.fromisoformat(row["next_attempt_at"]) >= datetime.now(UTC) + timedelta(
        seconds=110
    )
    assert row["last_status_code"] == 429

    async def _due(session: AsyncSession) -> None:
        for r in await session.scalars(
            select(LexofficeOutbox).where(LexofficeOutbox.status == "pending")
        ):
            r.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)

    run_tenant(settings, world.tenant_a, _due)
    fake.fail_next.append((503, {}))
    assert process(settings, world.tenant_a, uuid.UUID(cid))["retry"] == 1
    run_tenant(settings, world.tenant_a, _due)
    fake.fail_next.append((401, {}))
    out = process(settings, world.tenant_a, uuid.UUID(cid))
    assert out["sent"] == 0
    cfg = _ok(client.get(f"{L}/configs/{cid}", headers=h))
    assert cfg["token_invalid"] is True
    assert [r for r in _outbox(client, h, cid) if r["status"] == "pending"]
    # Nothing is processed while the key is invalid.
    assert process(settings, world.tenant_a, uuid.UUID(cid)) == {
        "sent": 0,
        "retry": 0,
        "failed": 0,
        "skipped": 0,
    }
    # Revalidate and finish; 404 -> remote_missing.
    _ok(client.post(f"{L}/configs/{cid}/test", headers=h))
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 1
    del fake.contacts[remote_muster["id"]]
    patched = _patch_contact(
        client, h, patched, phones=[{"label": "work", "number": "+4921031111", "is_primary": True}]
    )
    assert process(settings, world.tenant_a, uuid.UUID(cid))["failed"] == 1
    assert _links(client, h, cid, status="remote_missing")[0]["contact_id"] == muster["id"]
    assert fake.count("POST", "/v1/contacts") == 0
    # create_remote for an unlinked contact with roles: POST body asserted, then linked.
    harter_link = _ok(
        client.post(
            f"{L}/configs/{cid}/contacts/links/{ambiguous[0]['id']}/decide",
            json={"action": "create_remote", "contact_id": harter["id"], "roles": ["customer"]},
            headers=h,
        )
    )
    assert harter_link["sync_status"] == "pending"
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 1
    posted = fake.bodies("POST", "/v1/contacts")[-1]
    assert posted["version"] == 0
    assert posted["roles"] == {"customer": {}}
    assert posted["person"] == {"firstName": "Hardy", "lastName": "Harter"}
    assert posted["emailAddresses"] == {"business": ["hardy@example.org"]}
    status = _ok(client.get(f"{L}/contacts/{harter['id']}/lexoffice", headers=h))
    assert status[0]["sync_status"] == "linked"
    assert status[0]["deeplink"]
    # Deleted contact: link unlinked_local, no call.
    calls = len(fake.requests)
    assert client.delete(f"/api/v1/contacts/{harter['id']}", headers=h).status_code == 204
    assert (
        _ok(client.get(f"{L}/contacts/{harter['id']}/lexoffice", headers=h))[0]["sync_status"]
        == "unlinked_local"
    )
    assert len(fake.requests) == calls
    _assert_no_forbidden_change(fake)
    # Worker under tenant B sees nothing of tenant A (RLS on the new tables).

    async def _b(session: AsyncSession) -> int:
        return len((await session.scalars(select(LexofficeOutbox))).all())

    assert run_tenant(settings, world.tenant_b, _b) == 0
    _ok(client.put(f"{L}/configs/{cid}", json={"enabled": False}, headers=h))


# Invoice copy --------------------------------------------------------------------------------


def test_invoice_copy_verification_fetch_and_recipient_lock(
    client: TestClient, world: World, fake: FakeLexoffice, settings: Settings
) -> None:
    h = _admin(client, world)
    entities = _entities(client, h)
    mailbox = _ok(
        client.post(
            "/api/v1/mail/mailboxes",
            json={"address": f"rechnung-{RUN}@example.org", "kind": "imap"},
            headers=h,
        ),
        201,
    )
    config = _configure(
        client,
        h,
        fake,
        legal_entity_id=entities["rental_owner"],
        label="Makler",
        mailbox_id=mailbox["id"],
        sync_contacts=True,
        invoice_copies=True,
    )
    cid = config["id"]
    recipient = _contact(client, h, "Empfänger", f"empfaenger-{RUN}@example.org")
    other = _contact(client, h, "Fremd", f"fremd-{RUN}@example.org")
    remote = fake.add_contact(
        person={"firstName": "Hardy", "lastName": "Empfänger"},
        emails={"business": [f"empfaenger-{RUN}@example.org"]},
    )
    fake.add_invoice(
        voucher_number="RE-1019",
        contact_id=remote["id"],
        contact_name="Hardy Empfänger",
        total_gross="1234.56",
    )
    fake.add_invoice(
        voucher_number="RE-10190", contact_id=remote["id"]
    )  # substring, must be filtered
    fake.add_invoice(voucher_number="RE-2000", status="draft", contact_id=remote["id"])
    fake.add_invoice(voucher_number="GS-1", voucher_type="creditnote", contact_id=remote["id"])
    # Link the recipient through the review list.
    started = _ok(client.post(f"{L}/configs/{cid}/contacts/match", json={}, headers=h), 202)
    match(settings, world.tenant_a, uuid.UUID(cid), uuid.UUID(started["run_id"]))
    proposed = _links(client, h, cid, status="proposed")[0]
    assert proposed["contact_id"] == recipient["id"]
    _ok(
        client.post(
            f"{L}/configs/{cid}/contacts/links/{proposed['id']}/decide",
            json={"action": "link"},
            headers=h,
        )
    )
    process(settings, world.tenant_a, uuid.UUID(cid))
    # Ticket of the wrong contact asks for the invoice: lookup finds exactly one hit.
    ticket = _ok(
        client.post(
            "/api/v1/tickets",
            json={"title": "Rechnungskopie", "contact_id": other["id"]},
            headers=h,
        ),
        201,
    )
    assert (
        client.post(
            f"{L}/tickets/{ticket['id']}/invoice-copies",
            json={"invoice_number": "RE-1019"},
            headers=_admin(client, world, "lxosupport"),
        ).status_code
        == 403
    )
    req = _ok(
        client.post(
            f"{L}/tickets/{ticket['id']}/invoice-copies",
            json={"invoice_number": "RE-1019"},
            headers=h,
        ),
        201,
    )
    assert req["status"] == "pending"
    assert req["requester_contact_id"] == other["id"]
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 1
    query = [r for r in fake.requests if r["path"] == "/v1/voucherlist"][-1]["query"]
    assert query["voucherType"] == ["invoice,creditnote"]
    assert query["voucherStatus"] == ["any"]
    assert query["voucherNumber"] == ["RE-1019"]
    req = _ok(client.get(f"{L}/tickets/{ticket['id']}/invoice-copies", headers=h))[0]
    assert req["status"] == "found"
    assert req["lookup"]["status"] == "found"
    assert [hit["voucher_number"] for hit in req["lookup"]["hits"]] == ["RE-1019"]
    assert req["verification"]["status"] == "requester_mismatch"
    assert req["verification"]["recipient"]["contact_id"] == recipient["id"]
    # Accept while the requester differs: MHVP-LEXO-0009, no download.
    downloads = fake.count("GET", "/v1/invoices/")
    refused = client.post(f"{L}/invoice-copies/{req['id']}/accept", headers=h)
    assert refused.status_code == 422
    assert refused.json()["code"] == "MHVP-LEXO-0009"
    assert fake.count("GET", "/v1/invoices/") == downloads
    # Correct the requester, then accept (caretaker lacks communication:update).
    _ok(
        client.post(
            f"{L}/invoice-copies/{req['id']}/correct",
            json={"requester_contact_id": recipient["id"]},
            headers=h,
        )
    )
    assert (
        client.post(
            f"{L}/invoice-copies/{req['id']}/accept", headers=_admin(client, world, "lxocare")
        ).status_code
        == 403
    )
    accepted = _ok(client.post(f"{L}/invoice-copies/{req['id']}/accept", headers=h), 202)
    assert accepted["status"] == "fetching"
    assert accepted["verification"]["status"] == "verified"
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 1
    done = _ok(client.get(f"{L}/tickets/{ticket['id']}/invoice-copies", headers=h))[0]
    assert done["status"] == "draft_ready"
    assert done["document_id"]
    assert done["reply_message_id"]

    async def _draft(session: AsyncSession) -> Message:
        row = await session.get(Message, uuid.UUID(done["reply_message_id"]))
        assert row is not None
        session.expunge(row)
        return row

    draft: Message = run_tenant(settings, world.tenant_a, _draft)
    assert draft.to_addresses == [f"empfaenger-{RUN}@example.org"]
    assert draft.cc_addresses == []
    assert draft.author_approval_required is True
    assert str(draft.mailbox_id) == mailbox["id"]
    assert (draft.subject or "").startswith("Ihre Rechnung RE-1019")
    assert f"TNR#{ticket['number']}" in (draft.subject or "")
    assert "1.234,56 EUR" in (draft.body or "")
    assert "15.09.2026" in (draft.body or "")
    assert [str(d) for d in draft.attachment_document_ids] == [done["document_id"]]

    async def _doc(session: AsyncSession) -> tuple[str, str, str | None]:
        from mhvp.documents.models import Document

        row = await session.get(Document, uuid.UUID(done["document_id"]))
        assert row is not None
        return row.title, row.mime_type, row.source_id

    title, mime, source_id = run_tenant(settings, world.tenant_a, _doc)
    assert title == "Rechnung RE-1019 vom 15.09.2026"
    assert mime == "application/pdf"
    assert source_id == f"invoice-file:{done['lookup']['hits'][0]['lexoffice_invoice_id']}"
    # Recipient lock: foreign address refused, own address allowed.
    locked = client.patch(
        f"/api/v1/mail/messages/{draft.id}/draft",
        json={"to_addresses": [f"fremd-{RUN}@example.org"]},
        headers=h,
    )
    assert locked.status_code == 422
    assert locked.json()["code"] == "MHVP-LEXO-0015"
    _ok(
        client.patch(
            f"/api/v1/mail/messages/{draft.id}/draft",
            json={"body": "Sehr geehrter Herr Empfänger, anbei die Kopie."},
            headers=h,
        )
    )
    own = _ok(
        client.patch(
            f"/api/v1/mail/messages/{draft.id}/draft",
            json={"to_addresses": [f"empfaenger-{RUN}@example.org"]},
            headers=h,
        )
    )
    assert own["to_addresses"] == [f"empfaenger-{RUN}@example.org"]
    # Second request for the same invoice reuses the stored document.
    ticket2 = _ok(
        client.post(
            "/api/v1/tickets", json={"title": "Nochmal", "contact_id": recipient["id"]}, headers=h
        ),
        201,
    )
    req2 = _ok(
        client.post(
            f"{L}/tickets/{ticket2['id']}/invoice-copies",
            json={"invoice_number": "RE-1019"},
            headers=h,
        ),
        201,
    )
    process(settings, world.tenant_a, uuid.UUID(cid))
    _ok(client.post(f"{L}/invoice-copies/{req2['id']}/accept", headers=h), 202)
    process(settings, world.tenant_a, uuid.UUID(cid))
    done2 = _ok(client.get(f"{L}/tickets/{ticket2['id']}/invoice-copies", headers=h))[0]
    assert done2["document_id"] == done["document_id"]
    # Draft only in Lexware: no document, state draft_in_lexoffice.
    req3 = _ok(
        client.post(
            f"{L}/tickets/{ticket2['id']}/invoice-copies",
            json={"invoice_number": "RE-2000"},
            headers=h,
        ),
        201,
    )
    process(settings, world.tenant_a, uuid.UUID(cid))
    req3 = _ok(client.get(f"{L}/tickets/{ticket2['id']}/invoice-copies", headers=h))[0]
    assert req3["id"] == req3["id"]
    assert req3["status"] == "draft_only"
    # Tenant B cannot see the request.
    assert (
        client.get(
            f"{L}/tickets/{ticket['id']}/invoice-copies", headers=_admin(client, world, "lxoadminb")
        ).status_code
        == 404
    )

    async def _count(session: AsyncSession) -> int:
        return len((await session.scalars(select(LexofficeInvoiceCopyRequest))).all())

    assert run_tenant(settings, world.tenant_b, _count) == 0
    _ok(client.put(f"{L}/configs/{cid}", json={"enabled": False}, headers=h))


def test_inbound_mail_detector_creates_request(
    client: TestClient, world: World, fake: FakeLexoffice, settings: Settings
) -> None:
    h = _admin(client, world)
    config = _configure(client, h, fake, label="Mail", sync_contacts=False, invoice_copies=True)
    contact = _contact(client, h, "Mailer", f"mailer-{RUN}@example.org")
    ticket = _ok(
        client.post(
            "/api/v1/tickets", json={"title": "Mail", "contact_id": contact["id"]}, headers=h
        ),
        201,
    )
    from mhvp.tickets import proposals as ticket_proposals

    async def _inbound(session: AsyncSession) -> None:
        message = Message(
            tenant_id=world.tenant_a,
            direction="in",
            status="new",
            from_address=f"mailer-{RUN}@example.org",
            to_addresses=["info@example.org"],
            subject="Rechnung",
            body="Bitte senden Sie mir die Rechnung RE-1019 nochmals zu.",
            contact_id=uuid.UUID(contact["id"]),
            ticket_id=uuid.UUID(ticket["id"]),
        )
        session.add(message)
        await session.flush()
        await ticket_proposals.queue_for_message(session, settings, world.tenant_a, message)

    run_tenant(settings, world.tenant_a, _inbound)
    rows = _ok(client.get(f"{L}/tickets/{ticket['id']}/invoice-copies", headers=h))
    assert len(rows) == 1
    assert rows[0]["invoice_number"] == "RE-1019"
    assert rows[0]["requester_contact_id"] == contact["id"]
    _ok(client.put(f"{L}/configs/{config['id']}", json={"enabled": False}, headers=h))


# Invoice drafts and recurring preparation ----------------------------------------------------


def test_invoice_drafts_by_kind_and_recurring_prep(
    client: TestClient, world: World, fake: FakeLexoffice, settings: Settings
) -> None:
    h = _admin(client, world)
    entities = _entities(client, h)
    _ok(
        client.put(
            f"{L}/invoice-kinds",
            json=[{"kind": "broker", "legal_entity_id": entities["rental_owner"]}],
            headers=h,
        )
    )
    broker_cfg = _configure(
        client,
        h,
        fake,
        legal_entity_id=entities["rental_owner"],
        label="Makler",
        sync_contacts=False,
        invoice_drafts=True,
    )
    manager_cfg = _configure(
        client,
        h,
        fake,
        legal_entity_id=entities["manager"],
        label="HVM",
        sync_contacts=False,
        invoice_drafts=False,
    )
    contact = _contact(client, h, "Kunde", f"kunde-{RUN}@example.org")
    body = {
        "invoice_kind": "broker",
        "contact_id": contact["id"],
        "voucher_date": "2026-09-29",
        "tax_type": "net",
        "line_items": [
            {
                "name": "Courtage",
                "quantity": "1",
                "unit_name": "Pauschale",
                "unit_price": "2500.00",
                "tax_rate_percent": 19,
            }
        ],
        "shipping": {"type": "service", "date": "2026-09-29"},
        "title": "Courtage",
    }
    preview = _ok(client.post(f"{L}/invoice-drafts/preview", json=body, headers=h))
    assert preview["config_id"] == broker_cfg["id"]
    assert preview["legal_entity_id"] == entities["rental_owner"]
    assert preview["gross"] == "2.975,00 EUR"
    assert preview["net"] == "2.500,00 EUR"
    assert preview["address_from_link"] is False
    assert preview["payload"]["address"]["name"] == "Hardy Kunde"
    assert "finalize" not in json.dumps(preview["payload"])
    # Management kind maps to the manager config whose draft switch is off: MHVP-LEXO-0016.
    off = client.post(f"{L}/invoice-drafts", json={**body, "invoice_kind": "management"}, headers=h)
    assert off.status_code == 403
    assert off.json()["code"] == "MHVP-LEXO-0016"
    assert (
        client.post(
            f"{L}/invoice-drafts", json=body, headers=_admin(client, world, "lxosupport")
        ).status_code
        == 403
    )
    draft = _ok(client.post(f"{L}/invoice-drafts", json=body, headers=h), 202)
    assert draft["status"] == "pending"
    assert draft["config_id"] == broker_cfg["id"]
    assert process(settings, world.tenant_a, uuid.UUID(broker_cfg["id"]))["sent"] == 1
    posted = [r for r in fake.requests if r["path"] == "/v1/invoices" and r["method"] == "POST"][-1]
    assert posted["query"] == {}
    assert posted["body"]["taxConditions"] == {"taxType": "net"}
    created = _ok(client.get(f"{L}/invoice-drafts/{draft['id']}", headers=h))
    assert created["status"] == "created"
    assert created["deeplink"].endswith(
        f"/permalink/invoices/edit/{created['lexoffice_invoice_id']}"
    )
    # 406 with details is final and parsed.
    fake.fail_next.append((406, {}))
    draft2 = _ok(client.post(f"{L}/invoice-drafts", json=body, headers=h), 202)
    assert process(settings, world.tenant_a, uuid.UUID(broker_cfg["id"]))["failed"] == 1
    assert _ok(client.get(f"{L}/invoice-drafts/{draft2['id']}", headers=h))["status"] == "failed"
    # Recurring preparation on a new management fee: read only API, checklist with link.
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "901", "name": "Neues Haus", "management_type": "hoa"},
            headers=h,
        ),
        201,
    )
    fee = _ok(
        client.post(
            "/api/v1/accounting/admin-fees",
            json={
                "property_id": prop["id"],
                "start_date": "2026-10-01",
                "amounts_per_unit_type": {"apartment": "25.00"},
                "vat_percent": "19",
            },
            headers=h,
        ),
        201,
    )
    assert fee["lexoffice_recurring_prep_id"]
    preps = _ok(client.get(f"{L}/recurring-preps", params={"status": "open"}, headers=h))
    prep = next(p for p in preps if p["id"] == fee["lexoffice_recurring_prep_id"])
    assert prep["config_id"] == manager_cfg["id"]
    assert prep["prepared"]["amounts_per_unit_type"] == {"apartment": "25.00"}
    assert prep["prepared"]["interval_label"] == "monatlich"
    assert "01.10.2026" in prep["prepared"]["text"]
    assert "GET /v1/recurring-templates" in prep["prepared"]["api_limitation"]
    assert len(prep["checklist"]) == 5
    assert not any(c["done"] for c in prep["checklist"])
    assert fake.count("POST", "/v1/recurring") == 0
    done = _ok(
        client.post(
            f"{L}/recurring-preps/{prep['id']}/done",
            json={"lexoffice_template_id": "rt-1"},
            headers=h,
        )
    )
    assert done["status"] == "done"
    assert done["deeplink"].endswith("/permalink/recurring-templates/view/rt-1")
    assert (
        client.get(f"{L}/recurring-preps", headers=_admin(client, world, "lxoadminb")).json() == []
    )
    for cfg in (broker_cfg, manager_cfg):
        _ok(client.put(f"{L}/configs/{cfg['id']}", json={"enabled": False}, headers=h))


def test_rate_limit_and_purge(
    client: TestClient,
    world: World,
    fake: FakeLexoffice,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ratelimit, "SLOT_SECONDS", 0.5)
    ratelimit.reset_local()
    h = _admin(client, world)
    config = _configure(client, h, fake, label="RL", sync_contacts=True)
    cid = config["id"]

    async def _rows(session: AsyncSession) -> None:
        for i in range(5):
            remote = fake.add_contact(company={"name": f"Firma {i}"})
            link = LexofficeContactLink(
                tenant_id=world.tenant_a,
                config_id=uuid.UUID(cid),
                lexoffice_contact_id=remote["id"],
                sync_status="pending",
            )
            session.add(link)
            await session.flush()
            session.add(
                LexofficeOutbox(
                    tenant_id=world.tenant_a,
                    config_id=uuid.UUID(cid),
                    kind="refresh_link",
                    idempotency_key=f"rl-{link.id}",
                    target_kind="link",
                    target_id=link.id,
                    status="pending",
                    next_attempt_at=datetime.now(UTC),
                )
            )
        # An old sent row for the purge.
        session.add(
            LexofficeOutbox(
                tenant_id=world.tenant_a,
                config_id=uuid.UUID(cid),
                kind="refresh_link",
                idempotency_key="old-row",
                target_kind="link",
                target_id=uuid.uuid4(),
                status="sent",
                next_attempt_at=datetime.now(UTC),
                updated_at=datetime.now(UTC) - timedelta(days=91),
            )
        )

    run_tenant(settings, world.tenant_a, _rows)
    fake.requests.clear()
    assert process(settings, world.tenant_a, uuid.UUID(cid))["sent"] == 5
    stamps = sorted(r["at"] for r in fake.requests)
    for i in range(2, len(stamps)):
        assert stamps[i] - stamps[i - 2] >= 0.95, "more than two calls within one second"

    async def _purge(session: AsyncSession) -> int:
        return await svc.purge(session, world.tenant_a, retention_days=90)

    assert run_tenant(settings, world.tenant_a, _purge) == 1
    assert [r for r in _outbox(client, h, cid) if r["status"] == "sent"]
    _ok(client.put(f"{L}/configs/{cid}", json={"enabled": False}, headers=h))
