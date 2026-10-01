"""GA12-04: synthetic demo tenant (``make seed-demo``): sizes, drafts only, guards."""

import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mhvp.accounting.models import JournalEntry
from mhvp.banking.models import BankTransaction
from mhvp.contacts.models import Contact
from mhvp.core.db.engine import create_app_engine, create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.main import create_app
from mhvp.platform import demo_seed
from mhvp.platform.models import Tenant
from mhvp.properties.models import Property, Unit
from tests.integration.conftest import Database
from tests.integration.test_m2_platform import RUN, _settings

pytestmark = pytest.mark.integration


def test_unit_split_and_months_are_deterministic() -> None:
    assert demo_seed.unit_split() == [14, 13, 13]
    assert sum(demo_seed.unit_split()) == 40
    months = demo_seed.month_starts(date(2026, 10, 1))
    assert len(months) == 12
    assert months[0] == date(2025, 11, 1)
    assert months[-1] == date(2026, 10, 1)
    parsed = demo_seed.build_statements(list(demo_seed.TEST_IBANS), date(2026, 10, 1))
    transactions = [t for s in parsed.statements for t in s.transactions]
    assert len(transactions) == 200
    assert len({t.bank_reference for t in transactions}) == 200
    assert all(t.counterpart_iban and t.counterpart_iban.startswith("DE") for t in transactions)
    # fictitious bank code only, never a real bank
    assert all(t.counterpart_iban[4:12] == "10000000" for t in transactions)  # type: ignore[index]


def test_refused_without_switch_and_in_production(
    database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MHVP_DEMO_SEED", raising=False)
    monkeypatch.setenv("MHVP_DEMO_ADMIN_PASSWORD", "x")
    assert asyncio.run(demo_seed.run()) == 2  # switch missing
    monkeypatch.setenv("MHVP_DEMO_SEED", "1")
    monkeypatch.delenv("MHVP_DEMO_ADMIN_PASSWORD")
    assert asyncio.run(demo_seed.run()) == 2  # password missing
    monkeypatch.setenv("MHVP_DEMO_ADMIN_PASSWORD", "x")
    # an environment outside the allowed list (production) is refused
    monkeypatch.setattr(demo_seed, "ALLOWED_ENVIRONMENTS", frozenset())
    assert asyncio.run(demo_seed.run()) == 2


def test_demo_tenant_has_expected_size_and_only_drafts(
    database: Database, redis_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mhvp.core.config import get_settings

    slug = f"demo-{RUN}"
    monkeypatch.setattr(demo_seed, "DEMO_SLUG", slug)
    monkeypatch.setattr(demo_seed, "DEMO_ADMIN_EMAIL", f"demo-{RUN}@example.org")
    monkeypatch.setenv("MHVP_DEMO_SEED", "1")
    monkeypatch.setenv("MHVP_DEMO_ADMIN_PASSWORD", "Demo-Muster-Passwort-2026!x")
    get_settings.cache_clear()
    with TestClient(create_app(_settings(database, redis_url))) as client:
        assert asyncio.run(demo_seed.run(client, today=date(2026, 10, 1))) == 0
        # second run: tenant exists, nothing is added
        assert asyncio.run(demo_seed.run(client, today=date(2026, 10, 1))) == 0

    async def counts() -> dict[str, int]:
        engine = create_app_engine(_settings(database, redis_url))
        factory = create_session_factory(engine)
        try:
            async with platform_transaction(factory) as session:
                tenant_id = await session.scalar(select(Tenant.id).where(Tenant.slug == slug))
            assert tenant_id is not None
            async with tenant_transaction(factory, tenant_id) as session:
                out = {}
                for key, model in (
                    ("properties", Property),
                    ("units", Unit),
                    ("contacts", Contact),
                    ("bank", BankTransaction),
                    ("entries", JournalEntry),
                ):
                    out[key] = int(
                        await session.scalar(select(func.count()).select_from(model)) or 0
                    )
                out["posted"] = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(JournalEntry)
                        .where(JournalEntry.status != "draft")
                    )
                    or 0
                )
                return out
        finally:
            await engine.dispose()

    got = asyncio.run(counts())
    assert got["properties"] == 3
    assert got["units"] == 40
    assert got["contacts"] == 60
    assert got["bank"] == 200
    assert got["entries"] == 36  # 3 ledgers x 12 months
    assert got["posted"] == 0  # drafts only
