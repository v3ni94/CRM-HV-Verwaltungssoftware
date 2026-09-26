"""Shared fixtures. Unit tests need no services; integration tests need a PostgreSQL that
was prepared with infra/postgres/bootstrap.sh (see docs/runbooks/local-development.md)."""

import os

import pytest
from pydantic import SecretStr

from mhvp.core.config import Environment, LogFormat, Settings


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "env": Environment.TEST,
        "log_format": LogFormat.JSON,
        "database_url": SecretStr(
            os.environ.get("MHVP_DATABASE_URL", "postgresql+psycopg://unit@127.0.0.1:1/unit")
        ),
        "migration_database_url": SecretStr(os.environ.get("MHVP_MIGRATION_DATABASE_URL", ""))
        or None,
        "redis_url": SecretStr(os.environ.get("MHVP_REDIS_URL", "redis://127.0.0.1:1/0")),
        "celery_broker_url": SecretStr("memory://"),
        "celery_result_backend": None,
        "s3_endpoint_url": None,
        "s3_access_key_id": None,
        "s3_secret_access_key": None,
        "health_check_timeout_seconds": 2.0,
        "rate_limit_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # moto and boto3 must never pick up real credentials from the environment.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
