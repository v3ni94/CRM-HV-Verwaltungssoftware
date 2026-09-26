"""Coverage: own legal entity and ledger of the managing company (A32, ``mhvp.tenant.
manager_entity``): status before setup, name from tenant master data (company name, else
tenant name, never a default), idempotent ensure, repair paths for older seeds (entity without
ledger, ledger without accounts), permission and tenant separation of the endpoints."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mhvp.accounting import services as acc
from mhvp.accounting.models import Ledger, LedgerAccount
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.problems import ProblemError
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.platform.models import TenantSettings
from mhvp.properties.models import LegalEntity, LegalEntityKind
from mhvp.tenant import manager_entity
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, _settings, bearer, login

pytestmark = pytest.mark.integration
T = "/api/v1/tenant/manager-entity"


async def _world(settings: Any) -> World:
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(
            factory, slug=f"covme-{RUN}", name=f"Cov Verwaltung {RUN}"
        )
        b, _ = await services.provision_tenant(
            factory, slug=f"covme2-{RUN}", name=f"Cov Zweite {RUN}"
        )
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant, role in [
            ("covmeadmin", a, "tenant_admin"),
            ("covmereader", a, "read_only"),
            ("covmeother", b, "tenant_admin"),
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
    with TestClient(create_app(_settings(database, redis_url))) as test_client:
        yield test_client


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _run(database: Database, redis_url: str, tenant_id: uuid.UUID, fn: Any) -> Any:
    """Runs ``fn(session)`` inside one tenant transaction of the app role."""

    async def go() -> Any:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, tenant_id) as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_status_not_set_up_and_name_from_master_data(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    h = bearer(login(client, world, "covmeadmin"))
    reader = bearer(login(client, world, "covmereader"))
    before = _ok(client.get(T, headers=reader))
    assert before == {
        "status": "nicht_eingerichtet",
        "name": None,
        "legal_entity_id": None,
        "ledger_id": None,
        "accounts_count": 0,
        "created": False,
    }

    async def name_paths(session: Any) -> tuple[str, str]:
        from_settings = await manager_entity.company_name(session, world.tenant_a)
        row = await session.scalar(select(TenantSettings))
        assert row is not None
        row.company = {**row.company, "name": "   "}
        await session.flush()
        from_tenant = await manager_entity.company_name(session, world.tenant_a)
        row.company = {**row.company, "name": f"Cov Hausverwaltung {RUN} GmbH"}
        await session.flush()
        return from_settings, from_tenant

    from_settings, from_tenant = _run(database, redis_url, world.tenant_a, name_paths)
    assert from_settings == f"Cov Verwaltung {RUN}"  # provisioning copied the name
    assert from_tenant == f"Cov Verwaltung {RUN}"  # fallback: tenant row, not a default

    # Setup through the API: name from the (now changed) company master data.
    assert client.post(T, headers=reader).status_code == 403
    first = _ok(client.post(T, headers=h))
    assert first["created"] is True
    assert first["status"] == "eingerichtet"
    assert first["name"] == f"Cov Hausverwaltung {RUN} GmbH"
    assert first["accounts_count"] > 0
    second = _ok(client.post(T, headers=h))
    assert second["created"] is False
    assert second["legal_entity_id"] == first["legal_entity_id"]
    assert second["accounts_count"] == first["accounts_count"]
    status = _ok(client.get(T, headers=h))
    assert status["status"] == "eingerichtet"
    assert status["created"] is False

    async def only_one(session: Any) -> int:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(LegalEntity)
                .where(LegalEntity.kind == LegalEntityKind.MANAGER)
            )
            or 0
        )

    assert _run(database, redis_url, world.tenant_a, only_one) == 1


def test_tenant_separation_of_manager_entity(client: TestClient, world: World) -> None:
    """Tenant A is set up (previous test); tenant B sees nothing and sets up its own."""
    other = bearer(login(client, world, "covmeother"))
    assert _ok(client.get(T, headers=other))["status"] == "nicht_eingerichtet"
    own = _ok(client.post(T, headers=other))
    assert own["created"] is True
    assert own["name"] == f"Cov Zweite {RUN}"
    a = _ok(client.get(T, headers=bearer(login(client, world, "covmeadmin"))))
    assert a["legal_entity_id"] != own["legal_entity_id"]
    assert a["ledger_id"] != own["ledger_id"]


def test_ensure_repairs_entity_without_ledger(database: Database, redis_url: str) -> None:
    """Older seed: a MANAGER legal entity exists but no ledger; ensure only adds the ledger."""

    async def go() -> None:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            tenant_id, _ = await services.provision_tenant(
                factory, slug=f"covme3-{RUN}", name=f"Cov Alt {RUN}"
            )
            async with tenant_transaction(factory, tenant_id) as session:
                entity = LegalEntity(
                    tenant_id=tenant_id,
                    kind=LegalEntityKind.MANAGER,
                    name="Alte Verwaltung",
                    property_id=None,
                )
                session.add(entity)
                await session.flush()
                entity_id = entity.id
                before = await manager_entity.status(session)
                assert before.status == manager_entity.STATUS_NOT_SET_UP
                assert before.legal_entity_id == entity_id
                assert before.ledger_id is None
                result = await manager_entity.ensure(session, tenant_id=tenant_id, user_id=None)
                assert result.created is True
                assert result.legal_entity_id == entity_id
                assert result.name == "Alte Verwaltung"  # existing name is kept
                assert result.ledger_id is not None
                assert result.accounts_count > 0
                again = await manager_entity.ensure(session, tenant_id=tenant_id, user_id=None)
                assert again.created is False
                assert again.ledger_id == result.ledger_id
        finally:
            await engine.dispose()

    asyncio.run(go())


def test_ensure_fills_empty_ledger_of_direct_seed(database: Database, redis_url: str) -> None:
    """Older direct seed: entity and ledger without accounts; ensure adds the default chart
    (only rows that apply to ``manager``) and records template id and version."""

    async def go() -> None:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            tenant_id, _ = await services.provision_tenant(
                factory, slug=f"covme4-{RUN}", name=f"Cov Leer {RUN}"
            )
            async with tenant_transaction(factory, tenant_id) as session:
                entity = LegalEntity(
                    tenant_id=tenant_id,
                    kind=LegalEntityKind.MANAGER,
                    name="Leere Verwaltung",
                    property_id=None,
                )
                session.add(entity)
                await session.flush()
                ledger = await acc.create_ledger(
                    session,
                    tenant_id=tenant_id,
                    user_id=None,
                    legal_entity_id=entity.id,
                    template=None,
                    fiscal_year_start_month=1,
                    migration_cutoff=None,
                )
                assert ledger.template_id is None
                empty = await manager_entity.status(session)
                assert empty.status == manager_entity.STATUS_SET_UP
                assert empty.accounts_count == 0
                result = await manager_entity.ensure(session, tenant_id=tenant_id, user_id=None)
                assert result.created is True
                assert result.ledger_id == ledger.id
                assert result.accounts_count > 0
                refreshed = await session.get(Ledger, ledger.id)
                assert refreshed is not None
                assert refreshed.template_id is not None
                assert refreshed.template_version == 1
                numbers = set(
                    await session.scalars(
                        select(LedgerAccount.number).where(LedgerAccount.ledger_id == ledger.id)
                    )
                )
                assert "001300" in numbers
                assert "060100" not in numbers  # Hausgeld belongs to the GdWE only
                assert (
                    await manager_entity.ensure(session, tenant_id=tenant_id, user_id=None)
                ).created is False
        finally:
            await engine.dispose()

    asyncio.run(go())


def test_company_name_refuses_empty_master_data(database: Database, redis_url: str) -> None:
    """Without a company name and with a blank tenant name nothing is invented."""
    from sqlalchemy import create_engine, text

    async def go(tenant_id: uuid.UUID) -> None:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            async with tenant_transaction(factory, tenant_id) as session:
                row = await session.scalar(select(TenantSettings))
                assert row is not None
                row.company = {**row.company, "name": None}
                await session.flush()
                with pytest.raises(ProblemError) as excinfo:
                    await manager_entity.company_name(session, tenant_id)
                assert "Mandantenstammdaten" in str(excinfo.value.detail)
                with pytest.raises(ProblemError):
                    await manager_entity.ensure(session, tenant_id=tenant_id, user_id=None)
                # rollback: nothing was created
                assert (await manager_entity.status(session)).status == (
                    manager_entity.STATUS_NOT_SET_UP
                )
        finally:
            await engine.dispose()

    async def provision() -> uuid.UUID:
        engine = create_app_engine(_settings(database, redis_url))
        try:
            factory = create_session_factory(engine)
            tenant_id, _ = await services.provision_tenant(
                factory, slug=f"covme5-{RUN}", name=f"Cov Namenlos {RUN}"
            )
            return tenant_id
        finally:
            await engine.dispose()

    tenant_id = asyncio.run(provision())
    sync = create_engine(database.migrator_url)
    try:
        with sync.begin() as conn:
            conn.execute(text("UPDATE tenant SET name = '   ' WHERE id = :id"), {"id": tenant_id})
        asyncio.run(go(tenant_id))
    finally:
        with sync.begin() as conn:
            conn.execute(
                text("UPDATE tenant SET name = :name WHERE id = :id"),
                {"id": tenant_id, "name": f"Cov Namenlos {RUN}"},
            )
        sync.dispose()
