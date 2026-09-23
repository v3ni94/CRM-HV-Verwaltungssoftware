"""Operational entry points: seed, role sync, key generation, gate resolver."""

import asyncio
import uuid

import pytest

from mhvp.core.auth import keys
from mhvp.core.config import get_settings
from mhvp.core.release_gates import ReleaseGate
from mhvp.platform import seed, sync_roles
from mhvp.platform.gates import DbReleaseGateResolver
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, database: Database, redis_url: str) -> None:
    monkeypatch.setenv("MHVP_DATABASE_URL", database.app_url)
    monkeypatch.setenv("MHVP_REDIS_URL", redis_url)
    monkeypatch.setenv("MHVP_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("MHVP_ENV", "test")
    get_settings.cache_clear()
    from mhvp.core import crypto

    crypto.set_master_key(b"k" * 32)


def test_seed_with_admin_and_role_sync(env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MHVP_SEED_ADMIN_EMAIL", f"seed-{uuid.uuid4().hex[:6]}@example.org")
    monkeypatch.setenv("MHVP_SEED_ADMIN_PASSWORD", "a long seed password")
    assert asyncio.run(seed.run()) == 0
    assert asyncio.run(seed.run()) == 0  # second run: admin exists, skipped
    assert asyncio.run(sync_roles.run()) == 0
    get_settings.cache_clear()


def test_db_gate_resolver_is_closed_without_approval(env: None) -> None:
    from mhvp.core.db.engine import create_app_engine, create_session_factory

    async def run() -> bool:
        engine = create_app_engine(get_settings())
        try:
            return await DbReleaseGateResolver(create_session_factory(engine)).is_open(
                uuid.uuid4(), ReleaseGate.G1
            )
        finally:
            await engine.dispose()

    assert asyncio.run(run()) is False
    get_settings.cache_clear()


def test_key_generation(capsys: pytest.CaptureFixture[str]) -> None:
    assert keys.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("MHVP_MASTER_KEY=")
    assert "BEGIN PRIVATE KEY" in out
