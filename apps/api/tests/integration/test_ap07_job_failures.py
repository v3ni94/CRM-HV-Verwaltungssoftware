"""AP07 (GAM-504 to GAM-509): failures of background jobs are isolated per tenant, logged and
persisted (``job_failure``, ``task_failure``) and counted in the operator metrics.

Expected values by hand: a failure injected for tenant A writes exactly one ``job_failure`` row
for A with the job key and the exception class ``RuntimeError``; tenant B still runs and gets
no row. The metric counts of the last 24 hours rise by exactly the rows written here."""

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

import pytest
from sqlalchemy import func, select

from mhvp.core import job_failures as jf
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, _settings

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def tenants(database: Database, redis_url: str) -> dict[str, uuid.UUID]:
    settings = _settings(database, redis_url)

    async def build() -> dict[str, uuid.UUID]:
        engine = create_app_engine(settings)
        factory = create_session_factory(engine)
        try:
            a, _ = await services.provision_tenant(factory, slug=f"ap07a-{RUN}", name="AP07 A")
            b, _ = await services.provision_tenant(factory, slug=f"ap07b-{RUN}", name="AP07 B")
            return {"a": a, "b": b}
        finally:
            await engine.dispose()

    return asyncio.run(build())


def _failures(settings: Any, tenant_id: uuid.UUID, job: str) -> list[jf.JobFailure]:
    async def read() -> list[jf.JobFailure]:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenant_id) as session:
                rows = await session.scalars(select(jf.JobFailure).where(jf.JobFailure.job == job))
                return list(rows.all())
        finally:
            await engine.dispose()

    return asyncio.run(read())


def _fail_for(monkeypatch: pytest.MonkeyPatch, module: Any, bad: uuid.UUID) -> None:
    original = module.tenant_transaction

    @asynccontextmanager
    async def wrapped(factory: Any, tenant_id: uuid.UUID) -> Any:
        if tenant_id == bad:
            raise RuntimeError("ap07 injected failure")
        async with original(factory, tenant_id) as session:
            yield session

    monkeypatch.setattr(module, "tenant_transaction", wrapped)


def test_expire_mandates_isolates_and_records(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID], monkeypatch: Any
) -> None:
    from mhvp.contracts import tasks

    settings = _settings(database, redis_url)
    seen: list[uuid.UUID] = []

    async def fake(session: Any, today: date) -> int:
        tenant = await session.scalar(select(func.current_setting("app.tenant_id")))
        seen.append(uuid.UUID(tenant))
        return 0

    monkeypatch.setattr(tasks, "expire_due_mandates", fake)
    _fail_for(monkeypatch, tasks, tenants["a"])
    result = asyncio.run(tasks.expire_mandates_once(settings, today=date(2026, 10, 3)))
    assert result["expired"] == 0
    assert result["failed"] >= 1
    assert tenants["b"] in seen
    assert tenants["a"] not in seen
    rows = _failures(settings, tenants["a"], jf.JOB_EXPIRE_MANDATES)
    assert len(rows) == 1
    assert rows[0].error_type == "RuntimeError"
    assert _failures(settings, tenants["b"], jf.JOB_EXPIRE_MANDATES) == []


def test_event_consumers_record_failure(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID], monkeypatch: Any
) -> None:
    from mhvp.automation import tasks as automation_tasks
    from mhvp.banking import events_consumer

    settings = _settings(database, redis_url)

    async def poison(session: Any, tenant_id: uuid.UUID, **_: Any) -> dict[str, int]:
        if tenant_id == tenants["a"]:
            raise RuntimeError("poison event")
        return dict.fromkeys(
            ("events", "runs", "failed", "webhooks", "webhooks_failed", "handled"), 0
        )

    monkeypatch.setattr(automation_tasks, "process_tenant", poison)
    monkeypatch.setattr(events_consumer, "process_tenant", poison)
    from mhvp.banking import tasks as banking_tasks

    asyncio.run(automation_tasks.process_events_once(settings))
    asyncio.run(banking_tasks.process_events_once(settings))
    assert len(_failures(settings, tenants["a"], jf.JOB_AUTOMATION_EVENTS)) >= 1
    assert len(_failures(settings, tenants["a"], jf.JOB_BANKING_EVENTS)) >= 1
    assert _failures(settings, tenants["b"], jf.JOB_AUTOMATION_EVENTS) == []


def test_open_item_refresh_records_failure(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID], monkeypatch: Any
) -> None:
    from mhvp.accounting import tasks

    settings = _settings(database, redis_url)
    _fail_for(monkeypatch, tasks, tenants["a"])
    totals = asyncio.run(tasks.open_item_balance_refresh_all(settings, today=date(2026, 10, 3)))
    assert totals["failed"] >= 1
    assert len(_failures(settings, tenants["a"], jf.JOB_OPEN_ITEM_REFRESH)) == 1


def test_auto_post_failure_kept_on_run(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID], monkeypatch: Any
) -> None:
    from mhvp.banking import proposals, runner
    from mhvp.banking import tasks as banking_tasks

    settings = _settings(database, redis_url)

    async def no_proposals(session: Any, run_id: uuid.UUID) -> dict[str, int]:
        return {"computed": 0}

    async def disabled(session: Any) -> bool:
        return False

    async def broken(*_: Any, **__: Any) -> dict[str, Any]:
        raise RuntimeError("runner down")

    async def closed(tenant_id: uuid.UUID) -> bool:
        return False

    monkeypatch.setattr(proposals, "compute_for_run", no_proposals)
    monkeypatch.setattr(proposals, "learning_enabled", disabled)
    monkeypatch.setattr(runner, "run_for_tenant", broken)
    monkeypatch.setattr(banking_tasks, "_g1_open", closed)
    run_id = uuid.uuid4()
    counts = asyncio.run(banking_tasks.compute_proposals_once(settings, tenants["b"], run_id))
    assert counts["auto_post_failed"] == 1
    rows = _failures(settings, tenants["b"], jf.JOB_AUTO_POST)
    assert [r.ref_id for r in rows] == [run_id]


def test_receivable_run_takes_job_lock(
    database: Database, redis_url: str, tenants: dict[str, uuid.UUID], monkeypatch: Any
) -> None:
    from mhvp.accounting import receivables, tasks
    from mhvp.platform.models import TenantSettings

    settings = _settings(database, redis_url)

    async def switch_on() -> None:
        engine = create_app_engine(settings)
        try:
            async with tenant_transaction(create_session_factory(engine), tenants["a"]) as session:
                row = await session.scalar(select(TenantSettings))
                assert row is not None
                row.receivable_rules = {
                    **(row.receivable_rules or {}),
                    "monthly_preview_enabled": True,
                }
        finally:
            await engine.dispose()

    asyncio.run(switch_on())
    order: list[str] = []
    original = tasks.lock_job

    async def spy(session: Any, tenant_id: uuid.UUID, key: str) -> None:
        assert key == "accounting-receivable-run"
        order.append(f"lock:{tenant_id}")
        await original(session, tenant_id, key)

    async def preview(session: Any, *, tenant_id: uuid.UUID, **_: Any) -> None:
        order.append(f"preview:{tenant_id}")

    monkeypatch.setattr(tasks, "lock_job", spy)
    monkeypatch.setattr(receivables, "create_preview", preview)
    asyncio.run(tasks.receivable_previews(settings, today=date(2026, 10, 3)))
    a = str(tenants["a"])
    assert f"lock:{a}" in order
    assert f"preview:{a}" in order
    assert order.index(f"lock:{a}") < order.index(f"preview:{a}")
    assert f"lock:{tenants['b']}" not in order  # switch off: no lock, no run


def test_task_failure_signal_records_row(
    database: Database, redis_url: str, monkeypatch: Any
) -> None:
    from celery import Celery

    import mhvp.worker  # noqa: F401  (connects the task_failure handler)
    from mhvp.core import config

    settings = _settings(database, redis_url)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    app = Celery("ap07", set_as_current=False)
    name = f"mhvp.test.ap07_{uuid.uuid4().hex[:8]}"

    @app.task(name=name)
    def explode() -> None:
        raise KeyError("ap07")

    assert explode.apply().failed()

    async def count() -> int:
        engine = create_app_engine(settings)
        try:
            async with platform_transaction(create_session_factory(engine)) as session:
                query = (
                    select(func.count())
                    .select_from(jf.TaskFailure)
                    .where(jf.TaskFailure.task == name, jf.TaskFailure.error_type == "KeyError")
                )
                return int(await session.scalar(query) or 0)
        finally:
            await engine.dispose()

    assert asyncio.run(count()) == 1
