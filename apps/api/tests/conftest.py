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


# --- AJ19 (GAI-612, GAI-616, GAI-617): test infrastructure guards ----------------------------

# Packages that are locked runtime dependencies; a test skipped because one of them is missing
# would hide a schema check (pain.001, pain.008, KoSIT) and fails when integration is required.
REQUIRED_TEST_PACKAGES = ("xmlschema",)


def _require_integration() -> bool:
    return os.environ.get("MHVP_REQUIRE_INTEGRATION") == "1"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "annex_d(*cases): annex D acceptance cases (e.g. 'D16') the test covers (rule 8)",
    )


def forbidden_skip_reason(reason: str) -> bool:
    """True if a skip reason must not occur in a run with MHVP_REQUIRE_INTEGRATION=1."""
    if "integration test not executed" in reason:
        return True
    return any(f"could not import '{name}'" in reason for name in REQUIRED_TEST_PACKAGES)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if not report.skipped or not _require_integration():
        return
    longrepr = report.longrepr
    reason = str(longrepr[2]) if isinstance(longrepr, tuple) else str(longrepr)
    if forbidden_skip_reason(reason):
        _FORBIDDEN_SKIPS.append(f"{report.nodeid}: {reason}")


_FORBIDDEN_SKIPS: list[str] = []


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _FORBIDDEN_SKIPS and _require_integration():
        print("\nAJ19 guard: tests skipped although MHVP_REQUIRE_INTEGRATION=1:")  # noqa: T201
        for line in _FORBIDDEN_SKIPS[:20]:
            print(f"  {line}")  # noqa: T201
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
