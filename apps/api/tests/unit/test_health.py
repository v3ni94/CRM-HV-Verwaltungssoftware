import asyncio
from pathlib import Path

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.core import health
from mhvp.core.config import Settings
from mhvp.core.health import HealthCheckFailedError
from mhvp.core.storage import create_s3_client
from tests.conftest import make_settings
from tests.unit.helpers import app_with_checks, ok_check


def test_live(settings: Settings) -> None:
    with TestClient(app_with_checks(settings)) as client:
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api", "version": settings.app_version}


def test_ready_all_ok(settings: Settings) -> None:
    checks = {"database": ok_check(), "redis": ok_check()}
    with TestClient(app_with_checks(settings, checks)) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == {"database", "redis"}
    assert all(c["status"] == "ok" and c["detail"] is None for c in body["checks"].values())


def test_ready_reports_failures_without_internals(settings: Settings) -> None:
    async def failing() -> None:
        raise HealthCheckFailedError("bucket missing")

    async def exploding() -> None:
        raise ConnectionError("tcp://mhvp_app:secret@10.0.0.5:5432 refused")

    async def hanging() -> None:
        await asyncio.sleep(5)

    checks = {"object_storage": failing, "database": exploding, "redis": hanging, "ok": ok_check()}
    fast = make_settings(health_check_timeout_seconds=0.05)
    with TestClient(app_with_checks(fast, checks)) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "fail"
    assert body["checks"]["object_storage"]["detail"] == "bucket missing"
    assert body["checks"]["database"]["detail"] == "unavailable"
    assert body["checks"]["redis"]["detail"] == "timeout"
    assert body["checks"]["ok"]["status"] == "ok"
    assert "secret" not in response.text
    assert "10.0.0.5" not in response.text


def test_ready_without_checks_is_not_ok(settings: Settings) -> None:
    with TestClient(app_with_checks(settings, {})) as client:
        response = client.get("/api/v1/health/ready")
    assert response.status_code == 503


def test_default_checks_are_wired(settings: Settings) -> None:
    from mhvp.main import create_app

    with TestClient(create_app(settings)) as client:
        checks = client.app.state.readiness_checks  # type: ignore[attr-defined]
    assert set(checks) == {"database", "database_role", "migrations", "redis", "object_storage"}


class FakeRedis:
    def __init__(self, answer: bool) -> None:
        self.answer = answer

    async def ping(self) -> bool:
        return self.answer


async def test_redis_check() -> None:
    await health.redis_check(FakeRedis(True))()  # type: ignore[arg-type]
    with pytest.raises(HealthCheckFailedError):
        await health.redis_check(FakeRedis(False))()  # type: ignore[arg-type]


def _s3_settings() -> Settings:
    return make_settings(
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket="mhvp-test",
    )


async def test_object_storage_check_not_configured(settings: Settings) -> None:
    with pytest.raises(HealthCheckFailedError, match="not configured"):
        await health.object_storage_check(settings, None)()


async def test_object_storage_check_with_s3() -> None:
    settings = _s3_settings()
    with mock_aws():
        client = create_s3_client(settings)
        with pytest.raises(HealthCheckFailedError, match="bucket missing"):
            await health.object_storage_check(settings, client)()
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="mhvp-test")
        await health.object_storage_check(settings, client)()


async def test_migrations_check_without_scripts(tmp_path: Path) -> None:
    health._alembic_heads.cache_clear()
    check = health.migrations_check(engine=None, config_path=tmp_path / "missing.ini")  # type: ignore[arg-type]
    with pytest.raises(HealthCheckFailedError, match="migration scripts not found"):
        await check()


def test_alembic_heads_of_repository() -> None:
    health._alembic_heads.cache_clear()
    heads = health._alembic_heads(Path("alembic.ini"))
    assert len(heads) == 1  # linear history
