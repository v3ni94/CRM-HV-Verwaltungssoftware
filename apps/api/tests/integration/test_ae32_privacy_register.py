"""AE32 (S711-10): Anbieter aus der Konfiguration, Übernahme ins Register ohne vorbelegte
Rechtsaussagen, Pflegefelder je Tätigkeit (Rollen GdWE, Verwalter, Betreiber, Rechtsgrundlage,
eingesetzte Auftragsverarbeiter), Drittland je Anbieter, Verzeichnis als Markdown und PDF.
Mandantentrennung (404, fremde Konnektoren unsichtbar), Leserecht 403, Validierung 422."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as _base_settings

pytestmark = pytest.mark.integration
P = "/api/v1/privacy"
SLUG_A = f"ae32a-{RUN}"


def _settings(database: Database, redis_url: str) -> Any:
    return _base_settings(
        database,
        redis_url,
        objektakte_api_url="https://objektakte.ae32.example/api/crm/v1/",
        objektakte_api_token=SecretStr("ae32-token"),
        objektakte_tenant=SLUG_A,
    )


async def _connectors(settings: Any, tenant_id: uuid.UUID) -> None:
    from mhvp.ai.models import AiProvider, AiProviderConfig
    from mhvp.banking.models import BankConnection, ConnectionStatus, Connector
    from mhvp.communication.models import Mailbox, PostalSettings
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.webhooks import WebhookSubscription
    from mhvp.documents.models import DmsConnection, StorageKind
    from mhvp.integrations.schadenstool.models import SchadenstoolTenantConfig
    from mhvp.letting.models import BrokerTenantConfig

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            session.add_all(
                [
                    Mailbox(
                        tenant_id=tenant_id,
                        address=f"ae32-{RUN}@example.org",
                        kind="gmail",
                        enabled=True,
                        calendar_enabled=True,
                    ),
                    Mailbox(
                        tenant_id=tenant_id,
                        address=f"ae32-imap-{RUN}@example.org",
                        kind="imap",
                        imap_host="imap.ae32.example",
                        enabled=False,
                    ),
                    DmsConnection(
                        tenant_id=tenant_id,
                        kind=StorageKind.PAPERLESS,
                        enabled=True,
                        base_url="https://paperless.ae32.example",
                        options={},
                    ),
                    AiProviderConfig(
                        tenant_id=tenant_id,
                        provider=AiProvider.ANTHROPIC,
                        models={},
                        task_tiers={},
                        endpoint_region="eu",
                        enabled=False,
                    ),
                    PostalSettings(
                        tenant_id=tenant_id, provider="letterxpress", enabled=False, mode="test"
                    ),
                    SchadenstoolTenantConfig(
                        tenant_id=tenant_id, base_url="https://schaden.ae32.example", enabled=True
                    ),
                    BrokerTenantConfig(
                        tenant_id=tenant_id,
                        provider="flowfact",
                        base_url="https://broker.ae32.example",
                        enabled=False,
                    ),
                    WebhookSubscription(
                        tenant_id=tenant_id,
                        url="https://hooks.ae32.example/in",
                        event_types=["contact.created"],
                        secret="ae32-hook-secret",
                        active=True,
                    ),
                    BankConnection(
                        tenant_id=tenant_id,
                        connector=Connector.EBICS,
                        bank_name="AE32 Bank",
                        status=ConnectionStatus.ACTIVE,
                    ),
                    BankConnection(
                        tenant_id=tenant_id,
                        connector=Connector.FINTS,
                        bank_name="AE32 FinTS Bank",
                        status=ConnectionStatus.ACTIVE,
                    ),
                ]
            )
    finally:
        await engine.dispose()


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=SLUG_A, name=f"AE32 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ae32b-{RUN}", name=f"AE32 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in (
            ("ae32admin", a, "tenant_admin"),
            ("ae32reader", a, "read_only"),
            ("ae32adminb", b, "tenant_admin"),
        ):
            uid = await services.create_user(
                factory, email=world.email(name), display_name=name, password=PASSWORD
            )
            world.users[name] = uid
            await services.add_member(
                factory, tenant_id=tenant, user_id=uid, role_codes=[role], actor_user_id=None
            )
    finally:
        await engine.dispose()
    await _connectors(settings, a)
    return world


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


def _reader(c: TestClient, world: World) -> dict[str, str]:
    """privacy:read only: no system role below the administrators carries it, so the reader
    gets a custom role with exactly this right (idempotent across the module)."""
    admin = bearer(login(c, world, "ae32admin"))
    code = f"ae32read_{RUN}"
    role = c.post(
        "/api/v1/tenant/roles",
        json={"code": code, "name": "Datenschutz lesen", "permissions": ["privacy:read"]},
        headers=admin,
    )
    assert role.status_code in (201, 409), role.text
    members = _ok(c.get("/api/v1/tenant/members", headers=admin))
    member = next(m for m in members if m["user_id"] == str(world.users["ae32reader"]))
    put = c.put(
        f"/api/v1/tenant/members/{member['membership_id']}/roles",
        json={"role_codes": ["read_only", code]},
        headers=admin,
    )
    assert put.status_code == 204, put.text
    return bearer(login(c, world, "ae32reader"))


def _sources(c: TestClient, h: dict[str, str]) -> dict[str, Any]:
    return {s["key"]: s for s in _ok(c.get(f"{P}/register/config-sources", headers=h))}


def test_config_sources_detected_and_synced(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "ae32admin"))
    reader = _reader(client, world)
    other = bearer(login(client, world, "ae32adminb"))

    found = _sources(client, admin)
    assert set(_sources(client, reader)) == set(found)
    expected = {
        "gmail",
        "google_calendar",
        "mail:imap.ae32.example",
        "paperless",
        "ai:anthropic",
        "postal:letterxpress",
        "objektakte",
        "schadenstool",
        "broker:flowfact",
        "webhook:hooks.ae32.example",
        "ebics",
        "fints",
    }
    assert expected <= set(found)
    # GAE-34: read only display of the consent legal basis per service
    assert found["gmail"]["consent_purposes"] == ["email_delivery"]
    assert found["gmail"]["consent_basis"]["email_delivery"] in {"consent", "contract"}
    assert found["schadenstool"]["consent_purposes"] == ["data_sharing"]
    assert found["ebics"]["consent_purposes"] == []
    assert found["broker:flowfact"]["active"] is False
    assert found["webhook:hooks.ae32.example"]["active"] is True
    assert "ae32-hook-secret" not in found["webhook:hooks.ae32.example"]["detail"]
    assert found["gmail"]["active"] is True
    assert found["postal:letterxpress"]["active"] is False
    assert found["objektakte"]["scope"] == "platform"
    assert all(found[k]["entry_id"] is None for k in expected)
    # technical facts only: no mailbox address, no token
    assert all(f"ae32-{RUN}@" not in s["detail"] for s in found.values())
    assert all("ae32-token" not in s["detail"] for s in found.values())
    # tenant B sees neither A's connectors nor the objektakte link of A
    assert not (expected & set(_sources(client, other)))

    # read right only: no takeover
    assert (
        client.post(f"{P}/register/config-sources/sync", json={}, headers=reader).status_code == 403
    )
    assert (
        client.post(
            f"{P}/register/config-sources/sync", json={"unknown": 1}, headers=admin
        ).status_code
        == 422
    )

    first = _ok(client.post(f"{P}/register/config-sources/sync", json={}, headers=admin))
    created = {e["source_key"]: e for e in first["created"]}
    assert {"gmail", "google_calendar", "paperless", "objektakte"} <= set(created)
    assert not {"mail:imap.ae32.example", "ai:anthropic", "postal:letterxpress"} & set(created)
    assert first["skipped_inactive"] >= 3
    for entry in created.values():
        assert entry["kind"] == "sub_processor"
        assert entry["avv_status"] == "none"
        assert entry["third_country_status"] == "open"
        assert entry["third_country"] is False
        assert entry["legal_review_status"] == "open"
        assert entry["legal_basis"] is None
        assert entry["source_detail"]

    # idempotent; inactive services only on request
    again = _ok(client.post(f"{P}/register/config-sources/sync", json={}, headers=admin))
    assert again["created"] == []
    more = _ok(
        client.post(
            f"{P}/register/config-sources/sync", json={"include_inactive": True}, headers=admin
        )
    )
    assert {e["source_key"] for e in more["created"]} >= {
        "mail:imap.ae32.example",
        "ai:anthropic",
        "postal:letterxpress",
    }

    # operator fields survive a later sync; source_key is not editable
    gmail = created["gmail"]
    body = {
        "kind": "sub_processor",
        "name": gmail["name"],
        "purpose": gmail["purpose"],
        "avv_status": "confirmed",
        "avv_confirmed_on": "2026-09-30",
        "third_country_status": "yes",
        "third_country_countries": "USA",
        "third_country_note": "Eintrag Betreiber",
    }
    updated = _ok(client.put(f"{P}/register/{gmail['id']}", json=body, headers=admin))
    assert updated["third_country"] is True
    assert updated["source_key"] == "gmail"
    _ok(client.post(f"{P}/register/config-sources/sync", json={}, headers=admin))
    rows = {e["id"]: e for e in _ok(client.get(f"{P}/register", headers=admin))}
    assert rows[gmail["id"]]["avv_status"] == "confirmed"
    assert rows[gmail["id"]]["third_country_countries"] == "USA"
    assert _sources(client, admin)["gmail"]["entry_id"] == gmail["id"]

    # tenant separation of the register
    assert gmail["id"] not in {e["id"] for e in _ok(client.get(f"{P}/register", headers=other))}
    assert client.put(f"{P}/register/{gmail['id']}", json=body, headers=other).status_code == 404
    assert client.put(f"{P}/register/{gmail['id']}", json=body, headers=reader).status_code == 403


def test_activity_maintenance_fields_and_validation(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "ae32admin"))
    other = bearer(login(client, world, "ae32adminb"))
    proc = _ok(
        client.post(
            f"{P}/register",
            json={"kind": "processor", "name": f"Druckerei {RUN}", "third_country": True},
            headers=admin,
        ),
        201,
    )
    assert proc["third_country_status"] == "yes"
    legacy = _ok(
        client.post(f"{P}/register", json={"kind": "processor", "name": "Alt"}, headers=admin), 201
    )
    assert legacy["third_country_status"] == "open"
    foreign = _ok(
        client.post(f"{P}/register", json={"kind": "processor", "name": "Fremd"}, headers=other),
        201,
    )
    activity = {
        "kind": "processing_activity",
        "name": f"Hausgeldabrechnung {RUN}",
        "purpose": "Abrechnung",
        "legal_basis": "Pflegefeld Test",
        "responsibilities": {"gdwe": "controller", "verwalter": "processor"},
        "responsibility_note": "Eintrag Betreiber",
        "processor_ids": [proc["id"], proc["id"]],
    }
    act = _ok(client.post(f"{P}/register", json=activity, headers=admin), 201)
    assert act["responsibilities"] == {"gdwe": "controller", "verwalter": "processor"}
    assert act["processor_ids"] == [proc["id"]]
    assert act["legal_basis"] == "Pflegefeld Test"

    def _post(body: dict[str, Any]) -> int:
        return client.post(f"{P}/register", json=body, headers=admin).status_code

    assert _post({**activity, "responsibilities": {"gdwe": "boss"}}) == 422
    assert _post({**activity, "responsibilities": {"mieter": "controller"}}) == 422
    assert _post({**activity, "third_country_status": "maybe"}) == 422
    assert _post({**activity, "data_categories": ["x" * 101]}) == 422
    assert _post({**activity, "processor_ids": [str(uuid.uuid4())]}) == 422
    assert _post({**activity, "processor_ids": [foreign["id"]]}) == 422
    assert _post({**activity, "processor_ids": [act["id"]]}) == 422
    bad = client.post(
        f"{P}/register",
        json={"kind": "processor", "name": "X", "responsibilities": {"gdwe": "controller"}},
        headers=admin,
    )
    assert bad.status_code == 422
    assert bad.json()["code"] == "MHVP-PRIV-0004"
    # an activity cannot list itself
    put = client.put(
        f"{P}/register/{act['id']}", json={**activity, "processor_ids": [act["id"]]}, headers=admin
    )
    assert put.status_code == 422


def test_records_markdown_and_pdf(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "ae32admin"))
    reader = _reader(client, world)
    other = bearer(login(client, world, "ae32adminb"))
    _ok(
        client.post(
            f"{P}/register",
            json={
                "kind": "processing_activity",
                "name": f"Mieterkommunikation {RUN}",
                "responsibilities": {"verwalter": "controller"},
            },
            headers=admin,
        ),
        201,
    )
    draft = _ok(client.get(f"{P}/processing-records", headers=reader))
    md = draft["markdown"]
    assert "V13" in md
    assert "Rolle Verwalter: Verantwortlicher" in md
    assert "Rolle GdWE (Gemeinschaft der Wohnungseigentümer): offen" in md
    assert f"Mieterkommunikation {RUN}: Rechtsgrundlage nicht erfasst" in md
    assert "Anbieter laut Konfiguration ohne Registereintrag" in md
    assert (
        f"Mieterkommunikation {RUN}"
        not in _ok(client.get(f"{P}/processing-records", headers=other))["markdown"]
    )

    pdf = client.get(f"{P}/processing-records/pdf", headers=reader)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]
    assert client.get(
        f"{P}/processing-records/pdf", params={"x": "1"}, headers=admin
    ).status_code in (
        401,
        422,
    )
    assert client.get(f"{P}/processing-records/pdf").status_code == 401
