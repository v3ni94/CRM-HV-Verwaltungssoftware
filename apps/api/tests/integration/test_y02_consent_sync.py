"""Y02 (T03-02, M11-08): daily comparison of the consent expiry with the provider, per tenant
switch (default off), writes only on change. Fake client only, no network."""

# ruff: noqa: F811

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mhvp.banking import tasks as banking_tasks
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.workspace.services import local_today
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import World, bearer, login
from tests.integration.test_m8_import import _settings
from tests.integration.test_m11_finapi import (
    _configure,
    _connect_and_check,
    _consent_notifications,
    _fake_finapi,  # noqa: F401
    _run_reminders,
    _set_consent,
    client,  # noqa: F401
)
from tests.integration.test_m11_finapi import (
    _world as _finapi_world,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def world(database: Database, redis_url: str) -> World:
    # Own tenants and users (prefix y02): the finAPI world cannot be provisioned twice
    # in one process.
    return asyncio.run(_finapi_world(_settings(database, redis_url), prefix="y02"))


B = "/api/v1/banking/consent-sync/settings"


class _FakeProvider:
    def __init__(self, details: dict[str, Any] | None = None, fail: bool = False) -> None:
        self.details = details or {}
        self.fail = fail
        self.calls = 0

    def get_bank_connection(self, ref: str) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise ProblemError(ErrorCodes.FINAPI_UNAVAILABLE)
        return {"id": ref, "status": "READY", **self.details}


def _run_sync(database: Database, redis_url: str, tenant_id: Any, provider: Any) -> dict[str, int]:
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    settings = _settings(database, redis_url)

    async def _go() -> dict[str, int]:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as s:
                return await banking_tasks.sync_consent_from_provider(s, tenant_id, provider)
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def _read(database: Database, redis_url: str, tenant_id: Any, fa_id: str) -> tuple[Any, int]:
    from mhvp.banking.models import FinApiConnection
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.core.events import DomainEvent

    settings = _settings(database, redis_url)

    async def _go() -> tuple[Any, int]:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as s:
                fa = await s.get(FinApiConnection, uuid.UUID(fa_id))
                assert fa is not None
                n = await s.scalar(
                    select(func.count())
                    .select_from(DomainEvent)
                    .where(
                        DomainEvent.type == banking_tasks.CONSENT_SYNC_EVENT_TYPE,
                        DomainEvent.entity_id == fa.bank_connection_id,
                    )
                )
                return fa.consent_valid_until, int(n or 0)
        finally:
            await engine.dispose()

    return asyncio.run(_go())


def test_switch_default_off_permissions_and_separation(client: TestClient, world: World) -> None:
    admin = bearer(login(client, world, "fa-admin"))
    other = bearer(login(client, world, "fb-admin"))
    assert client.get(B, headers=admin).json() == {"enabled": False}
    # accountant without tenant_settings:update may not switch; invalid body is rejected
    banking = bearer(login(client, world, "fa-banking"))
    assert client.put(B, json={"enabled": True}, headers=banking).status_code == 403
    assert client.put(B, json={"enabled": "ja bitte"}, headers=admin).status_code == 422
    assert client.put(B, json={}, headers=admin).status_code == 422
    assert client.put(B, json={"enabled": True}, headers=admin).json() == {"enabled": True}
    assert client.get(B, headers=admin).json() == {"enabled": True}
    # other tenant keeps its own default
    assert client.get(B, headers=other).json() == {"enabled": False}
    assert client.put(B, json={"enabled": False}, headers=admin).json() == {"enabled": False}
    assert client.get("/api/v1/tenant/settings", headers=admin).status_code in (200, 404)


def test_sync_writes_only_on_change_and_feeds_reminder(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    checked = _connect_and_check(client, h)
    today = local_today()
    expiry = today + timedelta(days=5)

    # provider delivers a date: stored, event written once
    provider = _FakeProvider({"consentExpiresAt": f"{expiry.isoformat()}T10:00:00.000Z"})
    counts = _run_sync(database, redis_url, world.tenant_a, provider)
    assert counts["changed"] >= 1
    assert counts["errors"] == 0
    stored, events = _read(database, redis_url, world.tenant_a, checked["id"])
    assert stored == expiry
    assert events == 1

    # same date again: nothing written, no second event
    counts = _run_sync(database, redis_url, world.tenant_a, provider)
    assert counts["changed"] == 0
    assert counts["unchanged"] >= 1
    assert _read(database, redis_url, world.tenant_a, checked["id"]) == (expiry, 1)

    # no date delivered keeps the stored one; provider error is counted, nothing changes
    assert _run_sync(database, redis_url, world.tenant_a, _FakeProvider())["no_date"] >= 1
    assert _run_sync(database, redis_url, world.tenant_a, _FakeProvider(fail=True))["errors"] >= 1
    assert _read(database, redis_url, world.tenant_a, checked["id"]) == (expiry, 1)

    # reminder and task work on the synced date as before, once
    _run_reminders(database, redis_url, world.tenant_a, today)
    _run_reminders(database, redis_url, world.tenant_a, today)
    assert len(_consent_notifications(client, h, checked["bank_connection_id"])) == 1

    # a renewed date from the provider replaces the manual one
    renewed = expiry + timedelta(days=90)
    _set_consent(database, redis_url, world.tenant_a, checked["id"], expiry)
    _run_sync(
        database,
        redis_url,
        world.tenant_a,
        _FakeProvider({"consentValidUntil": renewed.isoformat()}),
    )
    assert _read(database, redis_url, world.tenant_a, checked["id"])[0] == renewed


def test_once_job_respects_tenant_switch(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "fa-admin"))
    _configure(client, h)
    _connect_and_check(client, h)
    settings = _settings(database, redis_url)
    assert client.put(B, json={"enabled": False}, headers=h).status_code == 200
    off = asyncio.run(banking_tasks.consent_provider_sync_once(settings))
    assert client.put(B, json={"enabled": True}, headers=h).status_code == 200
    on = asyncio.run(banking_tasks.consent_provider_sync_once(settings))
    try:
        assert on["tenants"] == off["tenants"] + 1
        assert on["checked"] > off["checked"]
    finally:
        client.put(B, json={"enabled": False}, headers=h)
