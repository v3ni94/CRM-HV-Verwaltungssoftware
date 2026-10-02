"""AF01 (GAC-06): a failed scheduled payment run preview is kept as evidence and counted in the
alerting metric ``payment_run_failed_24h``. Own world with prefix af01."""

import asyncio
from typing import Any

import pytest
from sqlalchemy import func, select

from mhvp.platform import services
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, _settings

pytestmark = pytest.mark.integration


async def _scenario(settings: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[int, int, str]:
    from mhvp.accounting.direct_debit_models import PaymentRunPreview, PaymentRunSetting
    from mhvp.banking import payment_run, payment_run_tasks
    from mhvp.core.db.engine import create_app_engine, create_session_factory
    from mhvp.core.db.tenancy import tenant_transaction

    engine = create_app_engine(settings)
    factory = create_session_factory(engine)
    try:
        tenant, _ = await services.provision_tenant(
            factory, slug=f"af01a-{RUN}", name=f"AF01 A {RUN}"
        )
        async with tenant_transaction(factory, tenant) as session:
            session.add(PaymentRunSetting(tenant_id=tenant, weekly_preview_enabled=True))

        async def boom(*_: Any, **__: Any) -> dict[str, Any]:
            raise RuntimeError("AF01 Testfehler")

        monkeypatch.setattr(payment_run, "preview", boom)
        result = await payment_run_tasks.weekly_previews(settings)
        async with tenant_transaction(factory, tenant) as session:
            rows = list(await session.scalars(select(PaymentRunPreview)))
            failed = await session.scalar(
                select(func.count()).where(PaymentRunPreview.trigger == "failed")
            )
        assert all(r.tenant_id == tenant for r in rows)
        error = next(r.summary["error"] for r in rows if r.trigger == "failed")
        return int(result["failed"]), int(failed or 0), str(error)
    finally:
        await engine.dispose()


def test_failed_payment_run_is_kept_and_alerting(
    database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mhvp.workspace.ops import ALERTING

    failed_runs, failed_rows, error = asyncio.run(
        _scenario(_settings(database, redis_url), monkeypatch)
    )
    assert failed_runs >= 1
    assert failed_rows == 1
    assert error == "RuntimeError: AF01 Testfehler"
    assert "payment_run_failed_24h" in ALERTING
