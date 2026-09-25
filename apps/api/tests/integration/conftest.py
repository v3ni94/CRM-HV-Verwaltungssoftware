"""Integration fixtures against a real PostgreSQL prepared by infra/postgres/bootstrap.sh.

Without ``MHVP_DATABASE_URL`` / ``MHVP_MIGRATION_DATABASE_URL`` the tests are skipped and
reported as not executed; CI sets ``MHVP_REQUIRE_INTEGRATION=1`` so they fail instead.
"""

import asyncio
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.exc import OperationalError

REQUIRED = os.environ.get("MHVP_REQUIRE_INTEGRATION") == "1"


def _unavailable(reason: str) -> None:
    if REQUIRED:
        pytest.fail(f"integration environment required but unavailable: {reason}")
    pytest.skip(f"integration test not executed: {reason}")


@dataclass(frozen=True)
class Database:
    app_url: str
    migrator_url: str

    @property
    def migrator_role(self) -> str:
        return str(make_url(self.migrator_url).username)

    @property
    def app_role(self) -> str:
        return str(make_url(self.app_url).username)


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def database() -> Database:
    app_url = os.environ.get("MHVP_DATABASE_URL")
    migrator_url = os.environ.get("MHVP_MIGRATION_DATABASE_URL")
    if not app_url or not migrator_url:
        _unavailable("MHVP_DATABASE_URL and MHVP_MIGRATION_DATABASE_URL are not set")
        raise AssertionError  # unreachable, keeps type checkers satisfied
    db = Database(app_url=app_url, migrator_url=migrator_url)
    try:
        engine = create_engine(migrator_url)
        with engine.connect():
            pass
        engine.dispose()
    except OperationalError:
        _unavailable("PostgreSQL is not reachable")
    command.upgrade(alembic_config(migrator_url), "head")
    return db


@pytest.fixture(scope="session")
def redis_url() -> str:
    url = os.environ.get("MHVP_REDIS_URL")
    if not url:
        _unavailable("MHVP_REDIS_URL is not set")
        raise AssertionError
    return url


@pytest.fixture
def migrator_engine(database: Database) -> Iterator[Engine]:
    engine = create_engine(database.migrator_url)
    yield engine
    engine.dispose()


@pytest.fixture
def app_engine(database: Database) -> Iterator[Engine]:
    engine = create_engine(database.app_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def world(database: Database, redis_url: str) -> Any:
    """Shared platform world of test_m2_platform: built once per session so that modules
    reusing it (OIDC clients) do not re-register the same users."""
    from tests.integration.test_m2_platform import _build_world, _settings

    return asyncio.run(_build_world(_settings(database, redis_url)))
