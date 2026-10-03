"""AP02: idempotent lexoffice export (GAL-201), base URL check at the API (GAL-202) and the
live mode switch per integration and tenant (GAL-207). Fake transport only, no network."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.integrations import lexoffice
from mhvp.integrations import routers as lx
from mhvp.integrations.models import (
    LexofficeExportKind,
    LexofficeExportLink,
    LexofficeSyncRun,
)
from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
LM = "/api/v1/integrations/live-modes"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ap02a-{RUN}", name=f"AP02 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ap02b-{RUN}", name=f"AP02 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ap02admin", a, "tenant_admin"),
            ("ap02reader", a, "read_only"),
            ("ap02other", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as c:
        yield c


class FakeVendor:
    """Creates vouchers; the first create answers with a timeout after it was processed."""

    def __init__(self) -> None:
        self.posts = 0
        self.vouchers: list[dict[str, Any]] = []
        self.timeout_next = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            self.posts += 1
            import json

            body = json.loads(request.content)
            created = {"id": f"lx-{self.posts}", "voucherNumber": body.get("voucherNumber")}
            self.vouchers.append(created)
            if self.timeout_next:
                self.timeout_next = False
                raise httpx.ReadTimeout("no answer", request=request)
            return httpx.Response(201, json={"id": created["id"]})
        if request.url.path == "/v1/voucherlist":
            number = request.url.params.get("voucherNumber")
            hits = [v for v in self.vouchers if v["voucherNumber"] == number]
            return httpx.Response(200, json={"content": hits, "paging": {"totalPages": 1}})
        return httpx.Response(404, json={})


def _vendor_client(monkeypatch: pytest.MonkeyPatch, fake: FakeVendor) -> lexoffice.LexofficeClient:
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(
        lexoffice.LexofficeClient,
        "_client",
        lambda self: httpx.Client(
            base_url=self._credentials.base_url, transport=transport, timeout=5.0
        ),
    )
    return lexoffice.LexofficeClient(
        lexoffice.LexofficeCredentials(api_key="k", base_url="https://api.lexware.io")
    )


def _attempt(
    world: World,
    client: lexoffice.LexofficeClient,
    kind: LexofficeExportKind,
    entity_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    force: bool = False,
) -> Any:
    """One export attempt in its own transaction, like one API request."""

    async def go() -> Any:
        engine = create_async_engine(world.app_url, poolclass=NullPool)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                run = LexofficeSyncRun(
                    tenant_id=world.tenant_a, kind="export_invoices", status="running"
                )
                session.add(run)
                await session.flush()
                principal = SimpleNamespace(tenant_id=world.tenant_a, user_id=None)
                return await lx._export_one(
                    session,
                    client,
                    principal,
                    run,
                    kind,
                    entity_id,
                    payload,
                    force,  # type: ignore[arg-type]
                )
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _link(world: World, entity_id: uuid.UUID) -> LexofficeExportLink | None:
    async def go() -> LexofficeExportLink | None:
        engine = create_async_engine(world.app_url, poolclass=NullPool)
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, world.tenant_a) as session:
                from sqlalchemy import select

                row: LexofficeExportLink | None = await session.scalar(
                    select(LexofficeExportLink).where(LexofficeExportLink.entity_id == entity_id)
                )
                return row
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_retry_after_timeout_returns_the_same_voucher(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeVendor()
    vendor = _vendor_client(monkeypatch, fake)
    invoice_id = uuid.uuid4()
    payload = {"type": "salesinvoice", "voucherNumber": f"RE-{RUN}-1"}

    first = _attempt(world, vendor, LexofficeExportKind.INVOICE, invoice_id, payload)
    assert first.ok is False
    assert first.outcome_unknown is True
    assert first.error_code == "MHVP-LEXO-0018"
    link = _link(world, invoice_id)
    assert link is not None
    assert link.status == "unknown"
    assert link.lexoffice_id is None
    assert link.idempotency_key == first.idempotency_key

    second = _attempt(world, vendor, LexofficeExportKind.INVOICE, invoice_id, payload)
    assert second.ok is True
    assert second.reconciled is True
    assert second.lexoffice_id == "lx-1"
    assert second.idempotency_key == first.idempotency_key

    third = _attempt(world, vendor, LexofficeExportKind.INVOICE, invoice_id, payload)
    assert third.ok is True
    assert third.skipped_duplicate is True
    assert third.lexoffice_id == "lx-1"
    assert fake.posts == 1, "a repetition must never create a second voucher"
    stored = _link(world, invoice_id)
    assert stored is not None
    assert stored.status == "exported"


def test_unknown_contact_is_never_created_twice_without_force(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeVendor()
    vendor = _vendor_client(monkeypatch, fake)
    contact_id = uuid.uuid4()
    first = _attempt(world, vendor, LexofficeExportKind.CONTACT, contact_id, {"x": 1})
    assert first.outcome_unknown is True
    again = _attempt(world, vendor, LexofficeExportKind.CONTACT, contact_id, {"x": 1})
    assert again.outcome_unknown is True
    assert fake.posts == 1
    forced = _attempt(world, vendor, LexofficeExportKind.CONTACT, contact_id, {"x": 1}, force=True)
    assert forced.ok is True
    assert fake.posts == 2


def test_invoice_without_number_stays_unknown(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeVendor()
    vendor = _vendor_client(monkeypatch, fake)
    invoice_id = uuid.uuid4()
    _attempt(world, vendor, LexofficeExportKind.INVOICE, invoice_id, {"type": "salesinvoice"})
    again = _attempt(world, vendor, LexofficeExportKind.INVOICE, invoice_id, {"type": "x"})
    assert again.outcome_unknown is True
    assert fake.posts == 1


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_base_url_attack_is_refused_at_the_api(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ap02admin"))
    for evil in (
        "http://attacker.test",
        "https://api.lexware.io@attacker.test",
        "https://attacker.test/?x=1",
    ):
        r = client.put(
            "/api/v1/integrations/lexoffice/config",
            json={"api_key": "secret-key", "base_url": evil, "enabled": False},
            headers=h,
        )
        assert r.status_code == 422, r.text
        assert "secret-key" not in r.text


def test_live_mode_switch(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ap02admin"))
    rows = _ok(client.get(LM, headers=h))
    assert [r["integration"] for r in rows] == ["lexoffice", "letterxpress", "finapi"]
    assert all(r["live_allowed"] and r["required_gate"] is None for r in rows)

    # validation and permissions
    assert client.put(f"{LM}/ftp", json={"live_allowed": True}, headers=h).status_code == 422
    assert (
        client.put(f"{LM}/lexoffice", json={"live_allowed": True, "required_gate": "G9"}, headers=h)
    ).status_code == 422
    assert client.get(LM, params={"x": 1}, headers=h).status_code == 422
    reader = bearer(login(client, world, "ap02reader"))
    assert (
        client.put(f"{LM}/lexoffice", json={"live_allowed": False}, headers=reader).status_code
        == 403
    )

    # lock lexoffice: the connection test is refused before any call
    _ok(
        client.put(
            "/api/v1/integrations/lexoffice/config",
            json={"api_key": "k-ap02", "enabled": False},
            headers=h,
        )
    )
    out = _ok(client.put(f"{LM}/lexoffice", json={"live_allowed": False}, headers=h))
    assert out[0]["live_allowed"] is False
    r = client.post("/api/v1/integrations/lexoffice/test", headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "MHVP-LEXO-0019"

    # bound to a closed gate: still locked
    _ok(
        client.put(f"{LM}/lexoffice", json={"live_allowed": True, "required_gate": "G1"}, headers=h)
    )
    r = client.post("/api/v1/integrations/lexoffice/test", headers=h)
    assert r.status_code == 409
    assert r.json()["gate"] == "G1"

    # LetterXpress: switching to live is refused while locked
    _ok(client.put(f"{LM}/letterxpress", json={"live_allowed": False}, headers=h))
    r = client.put("/api/v1/postal/settings", json={"mode": "live"}, headers=h)
    assert r.status_code == 409, r.text
    assert (
        client.put("/api/v1/postal/settings", json={"mode": "test"}, headers=h).status_code == 200
    )

    # tenant separation: tenant B still sees today's behaviour
    hb = bearer(login(client, world, "ap02other"))
    rows_b = _ok(client.get(LM, headers=hb))
    assert all(r["live_allowed"] and r["required_gate"] is None for r in rows_b)

    # back to today's behaviour
    _ok(client.put(f"{LM}/lexoffice", json={"live_allowed": True}, headers=h))
    _ok(client.put(f"{LM}/letterxpress", json={"live_allowed": True}, headers=h))
