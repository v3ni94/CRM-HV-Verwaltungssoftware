"""AB11 (GA10-03, GA12-06): both states of the direct filing switch, tenant separation and
logging of the filing; parallel and repeated runs of the consumption information and document
intake jobs per tenant (own world, prefix ab11)."""

import asyncio
import io
import uuid
from collections.abc import Iterator
from typing import Any

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select, text

from mhvp.billing.models import ConsumptionInfo
from mhvp.core import crypto
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import DomainEvent, emit
from mhvp.documents import intake
from mhvp.documents.models import Document, DocumentLink
from mhvp.main import create_app
from mhvp.platform import services
from mhvp.platform.models import TenantSettings
from mhvp.properties.models import Property
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import PASSWORD, RUN, World, bearer, login
from tests.integration.test_m2_platform import _settings as base_settings
from tests.integration.test_m5_contracts import _property, _unit

pytestmark = pytest.mark.integration
BUCKET = "mhvp-ab11"


def _settings(database: Database, redis_url: str) -> Any:
    return base_settings(
        database,
        redis_url,
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket=BUCKET,
        document_max_bytes=200_000,
    )


async def _world(settings: Any) -> World:
    crypto.set_master_key(b"k" * 32)
    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        a, _ = await services.provision_tenant(factory, slug=f"ab11a-{RUN}", name=f"AB11 A {RUN}")
        b, _ = await services.provision_tenant(factory, slug=f"ab11b-{RUN}", name=f"AB11 B {RUN}")
        world = World(tenant_a=a, tenant_b=b, app_url=settings.database_url.get_secret_value())
        for name, tenant in [("ab11admin", a), ("ab11other", b)]:
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


@pytest.fixture(scope="module")
def client(database: Database, redis_url: str) -> Iterator[TestClient]:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        with TestClient(create_app(_settings(database, redis_url))) as test_client:
            yield test_client


def _ok(response: Any, status: int = 201) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def _upload(client: TestClient, h: dict[str, str], name: str, *lines: str) -> str:
    buffer = io.BytesIO()
    canvas = Canvas(buffer)
    for i, line in enumerate(lines):
        canvas.drawString(72, 720 - 16 * i, line)
    canvas.save()
    doc = _ok(
        client.post(
            "/api/v1/documents",
            files={"file": (name, buffer.getvalue(), "application/pdf")},
            headers=h,
        )
    )
    return str(doc["id"])


def _run(settings: Any, tenant: uuid.UUID, work: Any) -> Any:
    async def go() -> Any:
        crypto.set_master_key(b"k" * 32)
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant) as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(go())


def _propose(settings: Any, tenant: uuid.UUID, doc_id: str, switch: dict[str, Any] | None) -> str:
    async def work(session: Any) -> str:
        row = await session.scalar(select(TenantSettings))
        row.sources = (
            {**row.sources, intake.AUTO_FILE_KEY: switch}
            if switch
            else {k: v for k, v in row.sources.items() if k != intake.AUTO_FILE_KEY}
        )
        document = await session.get(Document, uuid.UUID(doc_id))
        result = await intake.analyse(session, tenant, document, source="mailbox")
        proposal = await intake.propose(session, tenant, document, result)
        return str(proposal.decision.value)

    return str(_run(settings, tenant, work))


def _links(settings: Any, tenant: uuid.UUID, doc_id: str) -> list[tuple[str, str]]:
    async def work(session: Any) -> list[tuple[str, str]]:
        rows = await session.scalars(
            select(DocumentLink).where(DocumentLink.document_id == uuid.UUID(doc_id))
        )
        return [(link.entity_type, str(link.entity_id)) for link in rows]

    return list(_run(settings, tenant, work))


def _filed_events(settings: Any, tenant: uuid.UUID) -> int:
    async def work(session: Any) -> int:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(DomainEvent)
                .where(DomainEvent.type == "document.intake_auto_filed")
            )
            or 0
        )

    return int(_run(settings, tenant, work))


def test_direct_filing_both_switch_states_and_tenant_separation(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    settings = _settings(database, redis_url)
    ha = bearer(login(client, world, "ab11admin"))
    hb = bearer(login(client, world, "ab11other"))
    prop_a = _property(client, ha, "841", "rental")
    _property(client, ha, "842", "rental")
    prop_b = _property(client, hb, "841", "rental")  # same number in the other tenant

    clear = ("Hinweis zu Objekt 841 und Hausordnung",)
    # Switch off (default): proposal only, nothing linked, nothing logged.
    d_off = _upload(client, ha, "Brief aus.pdf", *clear)
    assert _propose(settings, world.tenant_a, d_off, None) == "pending"
    assert _links(settings, world.tenant_a, d_off) == []
    assert _filed_events(settings, world.tenant_a) == 0

    # Switch on, below the threshold (bare number in the body: 0.55 < 0.9): proposal only.
    d_weak = _upload(client, ha, "Brief schwach.pdf", "Bitte um Rueckruf wegen 841")
    on = {"enabled": True, "threshold": 0.9}
    assert _propose(settings, world.tenant_a, d_weak, on) == "pending"
    assert _links(settings, world.tenant_a, d_weak) == []

    # Switch on, two objects above the threshold: not unique, proposal only.
    d_two = _upload(client, ha, "Brief zwei.pdf", "Objekt 841 und Objekt 842 betroffen")
    assert _propose(settings, world.tenant_a, d_two, on) == "pending"
    assert _links(settings, world.tenant_a, d_two) == []
    assert _filed_events(settings, world.tenant_a) == 0

    # Switch on, one clear object above the threshold: filed directly and logged.
    d_on = _upload(client, ha, "Brief an.pdf", *clear)
    assert _propose(settings, world.tenant_a, d_on, on) == "accepted"
    assert _links(settings, world.tenant_a, d_on) == [("property", prop_a["id"])]
    assert _filed_events(settings, world.tenant_a) == 1

    # Tenant separation: the switch of tenant A does not file in tenant B; B's own object
    # number resolves to B's property only.
    d_b = _upload(client, hb, "Brief B.pdf", *clear)
    assert _propose(settings, world.tenant_b, d_b, None) == "pending"
    assert _links(settings, world.tenant_b, d_b) == []
    assert _filed_events(settings, world.tenant_b) == 0
    d_b2 = _upload(client, hb, "Brief B2.pdf", *clear)
    assert _propose(settings, world.tenant_b, d_b2, on) == "accepted"
    assert _links(settings, world.tenant_b, d_b2) == [("property", prop_b["id"])]
    assert _filed_events(settings, world.tenant_a) == 1
    assert _filed_events(settings, world.tenant_b) == 1
    # Document of A is not visible in B.
    assert client.get(f"/api/v1/documents/{d_on}", headers=hb).status_code == 404


def test_document_intake_parallel_and_repeated_runs_have_one_effect(
    world: World, database: Database, redis_url: str, monkeypatch: Any
) -> None:
    """Two simultaneous runs per tenant and a repeat index each external file once (advisory
    lock per tenant and job; the check for a known file is then safe)."""
    settings = _settings(database, redis_url)
    tenant = world.tenant_a
    key = f"ab11-{RUN}"

    async def fake_process(
        session: Any, blobs: Any, settings_: Any, tenant_id: uuid.UUID, client: Any
    ) -> dict[str, int]:
        seen = await session.scalar(
            select(func.count()).select_from(DomainEvent).where(DomainEvent.type == key)
        )
        # GAM-612: keep the window between check and write open until the other run waits for
        # the advisory lock (event instead of a fixed sleep); without a waiter the old 0.3 s
        # bound still applies, so the expectation is unchanged.
        waiting = text(
            "SELECT EXISTS (SELECT 1 FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid"
            " WHERE NOT l.granted AND l.locktype = 'advisory'"
            " AND a.datname = current_database() AND a.pid <> pg_backend_pid())"
        )

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 0.3  # same upper bound as the former fixed sleep
        while loop.time() < deadline and not await session.scalar(waiting):  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        if not seen:
            await emit(
                session,
                tenant_id=tenant_id,
                type=key,
                entity_type="document",
                entity_id=None,
                actor_user_id=None,
                payload={},
            )
        return {intake.SOURCE_PAPERLESS: 0, intake.SOURCE_DRIVE: 0, intake.SOURCE_MAILBOX: 0}

    async def no_distribution(*args: Any, **kwargs: Any) -> int:
        return 0

    from mhvp.documents import distribution

    monkeypatch.setattr(intake, "process_tenant_inbox", fake_process)
    monkeypatch.setattr(distribution, "distribute_shared_mailboxes", no_distribution)

    class _Http:
        async def aclose(self) -> None:
            return None

    async def runs() -> None:
        await asyncio.gather(
            intake.process_inbox_once(settings, client=_Http(), blobs=object()),  # type: ignore[arg-type]
            intake.process_inbox_once(settings, client=_Http(), blobs=object()),  # type: ignore[arg-type]
        )
        await intake.process_inbox_once(settings, client=_Http(), blobs=object())  # type: ignore[arg-type]

    async def effects(session: Any) -> int:
        return int(
            await session.scalar(
                select(func.count()).select_from(DomainEvent).where(DomainEvent.type == key)
            )
            or 0
        )

    asyncio.run(runs())
    assert _run(settings, tenant, effects) == 1


def test_consumption_info_parallel_and_repeated_runs_create_each_row_once(
    client: TestClient, world: World, database: Database, redis_url: str
) -> None:
    from datetime import date

    from mhvp.billing import consumption_info_tasks as tasks

    settings = _settings(database, redis_url)
    tenant = world.tenant_b
    hb = bearer(login(client, world, "ab11other"))
    prop = _property(client, hb, "851", "rental")
    _unit(client, hb, prop["id"], "1")
    other_building = _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/buildings", json={"name": "Haus 2"}, headers=hb
        )
    )
    _ok(
        client.post(
            f"/api/v1/properties/{prop['id']}/units",
            json={
                "building_id": other_building["id"],
                "number": "2",
                "label": "WE 2",
                "unit_type": "apartment",
            },
            headers=hb,
        )
    )

    async def enable(session: Any) -> None:
        row = await session.scalar(select(TenantSettings))
        row.consumption_info_enabled = True
        for p in await session.scalars(select(Property)):
            p.consumption_info_enabled = True

    _run(settings, tenant, enable)

    async def rows(session: Any) -> int:
        return int(await session.scalar(select(func.count()).select_from(ConsumptionInfo)) or 0)

    today = date(2026, 10, 3)

    async def runs() -> list[dict[str, int]]:
        first = await asyncio.gather(
            tasks.run_once(settings, today), tasks.run_once(settings, today)
        )
        again = await tasks.run_once(settings, today)  # repeat after the first runs
        return [*first, again]

    results = asyncio.run(runs())
    assert _run(settings, tenant, rows) == 2  # one row per unit and month
    assert results[-1]["created"] == 0
    assert sum(r["created"] for r in results[:2]) >= 2
