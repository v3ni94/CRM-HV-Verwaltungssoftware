"""GAG-38 (rules H01, H03): endpoint tests for POST /metering/assignments/{id}/remote-confirm
and POST /statements/{id}/heating/import-consumptions. Covered per endpoint: happy path,
permission (403), tenant separation (404), validation (422), module switch respectively draft
lock. Own test world (prefix ah17), artificial data only, no provider is called."""

import asyncio
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mhvp.main import create_app
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login
from tests.integration.test_m17_heating import _setup

pytestmark = pytest.mark.integration
M = "/api/v1/metering"
S = "/api/v1/statements"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ah17a-{RUN}", name=f"AH17 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ah17b-{RUN}", name=f"AH17 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("ah17admin", a, "tenant_admin"),
            ("ah17reader", a, "read_only"),
            ("ah17clerk", a, "clerk_no_accounting"),
            ("ah17other", b, "tenant_admin"),
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _code(response: Any, status: int, code: str | None = None) -> None:
    assert response.status_code == status, response.text
    if code is not None:
        assert response.json()["code"] == code, response.text


def _enable(client: TestClient, h: dict[str, str], on: bool) -> None:
    _ok(client.patch("/api/v1/tenant/settings", json={"metering_module_enabled": on}, headers=h))


def test_remote_confirm_endpoint(client: TestClient, world: World) -> None:
    h = bearer(login(client, world, "ah17admin"))
    _enable(client, h, True)
    prop = _ok(
        client.post(
            "/api/v1/properties",
            json={"number": "917", "name": f"Fernhaus {RUN}", "management_type": "rental"},
            headers=h,
        ),
        201,
    )
    conn = _ok(
        client.post(
            f"{M}/connections",
            json={
                "display_name": f"ista AH17 {RUN}",
                "provider_code": "ista",
                "environment": "test",
                "customer_references": ["0000170"],
                "config": {"adapter": "fake"},
            },
            headers=h,
        ),
        201,
    )
    row = _ok(
        client.post(
            f"{M}/assignments",
            json={
                "connection_id": conn["id"],
                "property_id": prop["id"],
                "external_number": "0001717",
                "service_scope": "heating",
                "valid_from": "2026-01-01",
            },
            headers=h,
        ),
        201,
    )
    assert row["remote_confirmed"] is False
    url = f"{M}/assignments/{row['id']}/remote-confirm"
    body = {"version": row["version"], "verification_basis": "Antwort Messdienst 01.10.2026"}

    # Validation: basis required, unknown fields refused, version required.
    _code(client.post(url, json={**body, "verification_basis": ""}, headers=h), 422)
    _code(client.post(url, json={**body, "extra": 1}, headers=h), 422)
    _code(client.post(url, json={"verification_basis": "x"}, headers=h), 422)
    # Permission: read only role cannot record the confirmation.
    reader = bearer(login(client, world, "ah17reader"))
    _code(client.post(url, json=body, headers=reader), 403)
    # Tenant separation: the assignment of tenant A does not exist for tenant B.
    other = bearer(login(client, world, "ah17other"))
    _enable(client, other, True)
    _code(client.post(url, json=body, headers=other), 404)
    _code(client.post(f"{M}/assignments/{uuid.uuid4()}/remote-confirm", json=body, headers=h), 404)
    # Module switch off locks the write (gate of the module).
    _enable(client, h, False)
    _code(client.post(url, json=body, headers=h), 403, "MHVP-METR-0001")
    _enable(client, h, True)
    unchanged = _ok(client.get(f"{M}/assignments/{row['id']}", headers=h))
    assert unchanged["remote_confirmed"] is False and unchanged["version"] == row["version"]  # noqa: PT018

    done = _ok(client.post(url, json=body, headers=h))
    assert done["remote_confirmed"] is True
    assert done["remote_confirmed_at"] is not None
    assert done["verification_basis"] == "Antwort Messdienst 01.10.2026"
    assert done["version"] == row["version"] + 1
    # A stale version is refused (optimistic locking), nothing is overwritten.
    _code(client.post(url, json=body, headers=h), 409)


async def _seed(
    settings: Any, tenant_id: uuid.UUID, property_id: str, units: dict[str, str]
) -> None:
    """Metering assignment with period consumptions 2025: unit 01 heating 1.000 kWh (one
    occupancy, goes to that occupancy), unit 02 heating 900 kWh over the whole period (two
    occupancies, becomes a unit total), unit 01 hot water missing (stays missing)."""
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction
    from mhvp.metering.models import (
        MeteringConnection,
        MeteringConsumptionValue,
        MeteringExternalBillingUnit,
        MeteringPropertyAssignment,
        MeteringUnitAssignment,
    )

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            conn = MeteringConnection(
                tenant_id=tenant_id,
                display_name="Messdienst AH17",
                provider_code="test",
                environment="test",
            )
            session.add(conn)
            await session.flush()
            ebu = MeteringExternalBillingUnit(
                tenant_id=tenant_id, connection_id=conn.id, external_number="AH17-1"
            )
            session.add(ebu)
            await session.flush()
            pa = MeteringPropertyAssignment(
                tenant_id=tenant_id,
                connection_id=conn.id,
                property_id=uuid.UUID(property_id),
                external_billing_unit_id=ebu.id,
                service_scope="heating",
                valid_from=date(2024, 1, 1),
                status="confirmed",
            )
            session.add(pa)
            await session.flush()
            ua: dict[str, uuid.UUID] = {}
            for number, unit_id in units.items():
                row = MeteringUnitAssignment(
                    tenant_id=tenant_id,
                    property_assignment_id=pa.id,
                    unit_id=uuid.UUID(unit_id),
                    external_unit_number=f"NE-{number}",
                    valid_from=date(2024, 1, 1),
                    status="confirmed",
                )
                session.add(row)
                await session.flush()
                ua[number] = row.id
            for number, kind, value, value_kind in [
                ("01", "heating", Decimal("1000"), "actual"),
                ("02", "heating", Decimal("900"), "estimated"),
                ("01", "hot_water", None, "missing"),
            ]:
                session.add(
                    MeteringConsumptionValue(
                        tenant_id=tenant_id,
                        property_assignment_id=pa.id,
                        unit_assignment_id=ua[number],
                        period_from=date(2025, 1, 1),
                        period_to=date(2025, 12, 31),
                        kind=kind,
                        unit_of_measure="kWh" if kind == "heating" else "m3",
                        reading_type="period_consumption",
                        source="test",
                        value=value,
                        value_kind=value_kind,
                    )
                )
    finally:
        await engine.dispose()


async def _set_status(settings: Any, tenant_id: uuid.UUID, statement_id: str, status: str) -> None:
    from sqlalchemy import update

    from mhvp.billing.models import Statement
    from mhvp.billing.status import StatementStatus
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
            await session.execute(
                update(Statement)
                .where(Statement.id == uuid.UUID(statement_id))
                .values(status=StatementStatus(status))
            )
    finally:
        await engine.dispose()


def test_import_consumptions_endpoint(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    h = bearer(login(client, world, "ah17admin"))
    st_id, _ = _setup(client, h)
    url = f"{S}/{st_id}/heating/import-consumptions"
    prop = _ok(client.get(f"{S}/{st_id}", headers=h))["property_id"]
    units = {
        u["number"]: u["id"] for u in _ok(client.get(f"/api/v1/properties/{prop}/units", headers=h))
    }

    # Without a metering assignment the import is refused, never filled with zeros.
    _code(client.post(url, json={}, headers=h), 422)
    # Validation: unknown fields and wrong types.
    _code(client.post(url, json={"extra": True}, headers=h), 422)
    _code(client.post(url, json={"heating_kinds": "heating"}, headers=h), 422)
    # Permission: a role without accounting:create is refused.
    clerk = bearer(login(client, world, "ah17clerk"))
    _code(client.post(url, json={}, headers=clerk), 403)
    # Tenant separation: statement of tenant A is not found for tenant B.
    other = bearer(login(client, world, "ah17other"))
    _code(client.post(url, json={}, headers=other), 404)

    asyncio.run(_seed(settings, world.tenant_a, prop, units))
    result = _ok(client.post(url, json={}, headers=h))
    assert result["import"]["taken"] == 2
    assert len(result["import"]["skipped"]) == 1  # missing hot water stays missing
    heating = _ok(client.get(f"{S}/{st_id}/heating", headers=h))
    keys = {o["unit_number"] + o["from"]: o["key"] for o in heating["occupants"]}
    entry = heating["consumptions"][keys["012025-01-01"]]
    assert Decimal(entry["heating"]) == Decimal("1000")
    assert entry["heating_kind"] == "actual"
    assert entry["source"] == "metering:test"
    assert "hot_water" not in entry
    total = heating["unit_totals"][units["02"]]
    assert Decimal(total["heating"]) == Decimal("900")
    assert total["heating_kind"] == "estimated"
    # Repeating the import is idempotent for the same values.
    again = _ok(client.post(url, json={}, headers=h))
    assert again["import"]["taken"] == 2
    assert again["consumptions"] == result["consumptions"]

    # Draft lock: after the statement left the draft status the import is refused.
    asyncio.run(_set_status(settings, world.tenant_a, st_id, "calculated"))
    _code(client.post(url, json={}, headers=h), 409)
