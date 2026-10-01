"""GA14-01 and GA14-06 (rule 0.1.4, 18.0, 19.2): jobs resolve release gates per tenant from
the database. Expected by hand: no approved request means closed; an approved G1 request of
tenant A opens G1 for A only (B stays closed, G2 stays closed); after revocation G1 is
closed again. The worker start installs the persistent resolver."""

import asyncio
import uuid
from typing import Any

import pytest

from mhvp.core import release_gates
from mhvp.core.release_gates import (
    JobDbReleaseGateResolver,
    ReleaseGate,
    ReleaseGateClosedError,
    release_gated,
)
from mhvp.platform import services
from mhvp.platform.models import GateRequestStatus, ReleaseGateRequest
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, _settings

pytestmark = pytest.mark.integration


async def _tenants(settings: Any) -> tuple[uuid.UUID, uuid.UUID]:
    from mhvp.core import crypto
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        a, _ = await services.provision_tenant(factory, slug=f"jg-{RUN}", name=f"Job A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"jg2-{RUN}", name=f"Job B {RUN}")
        return a, b
    finally:
        await engine.dispose()


async def _set_g1(settings: Any, tenant: uuid.UUID, status: GateRequestStatus | None) -> uuid.UUID:
    from sqlalchemy import update

    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant) as session:
            if status is GateRequestStatus.APPROVED:
                row = ReleaseGateRequest(
                    tenant_id=tenant,
                    gate=ReleaseGate.G1.value,
                    scope="Test GA14-01",
                    evidence="Testnachweis",
                    status=GateRequestStatus.APPROVED,
                    requested_by=uuid.uuid4(),
                    decided_by=uuid.uuid4(),
                )
                session.add(row)
                await session.flush()
                return row.id
            await session.execute(
                update(ReleaseGateRequest)
                .where(ReleaseGateRequest.tenant_id == tenant)
                .values(status=GateRequestStatus.REVOKED)
            )
            return tenant
    finally:
        await engine.dispose()


def test_job_resolver_follows_gate_per_tenant(
    database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mhvp.banking.tasks import _g1_open

    settings = _settings(database, redis_url)
    a, b = asyncio.run(_tenants(settings))
    monkeypatch.setattr(
        release_gates,
        "job_release_gate_resolver",
        JobDbReleaseGateResolver(settings.database_url.get_secret_value()),
    )
    calls: list[str] = []

    @release_gated(ReleaseGate.G1)
    def job(*, tenant_id: uuid.UUID | str) -> str:
        calls.append(str(tenant_id))
        return "ran"

    # Closed for both tenants without an approved request.
    assert asyncio.run(_g1_open(a)) is False
    with pytest.raises(ReleaseGateClosedError):
        job(tenant_id=a)

    asyncio.run(_set_g1(settings, a, GateRequestStatus.APPROVED))
    assert asyncio.run(_g1_open(a)) is True
    assert job(tenant_id=str(a)) == "ran"
    # Tenant separation and gate separation: B and G2 stay closed.
    assert asyncio.run(_g1_open(b)) is False
    with pytest.raises(ReleaseGateClosedError):
        job(tenant_id=b)
    resolver = release_gates.job_release_gate_resolver
    assert asyncio.run(resolver.is_open(a, ReleaseGate.G2)) is False

    asyncio.run(_set_g1(settings, a, None))
    assert asyncio.run(_g1_open(a)) is False
    with pytest.raises(ReleaseGateClosedError):
        job(tenant_id=a)
    assert calls == [str(a)]


def test_worker_start_installs_db_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    from mhvp import worker

    monkeypatch.setattr(
        release_gates, "job_release_gate_resolver", release_gates.ClosedReleaseGateResolver()
    )
    worker._install_job_gate_resolver()
    assert isinstance(release_gates.job_release_gate_resolver, JobDbReleaseGateResolver)


def test_job_resolver_fails_closed_on_database_error() -> None:
    resolver = JobDbReleaseGateResolver("postgresql+psycopg://nobody:x@127.0.0.1:1/none")

    async def check() -> None:
        await release_gates.ensure_release_gate_open(ReleaseGate.G1, uuid.uuid4(), resolver)

    with pytest.raises(ReleaseGateClosedError):
        asyncio.run(check())
