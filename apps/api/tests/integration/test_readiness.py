"""Readiness against the real database and Redis; S3 is simulated with moto."""

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from pydantic import SecretStr

from mhvp.main import create_app
from tests.conftest import make_settings
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration


def _settings(database_url: str, redis_url: str) -> object:
    return make_settings(
        database_url=SecretStr(database_url),
        redis_url=SecretStr(redis_url),
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
        s3_bucket="mhvp-ready",
    )


def test_ready_with_real_dependencies(database: Database, redis_url: str) -> None:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="mhvp-ready")
        app = create_app(_settings(database.app_url, redis_url))  # type: ignore[arg-type]
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
    body = response.json()
    assert response.status_code == 200, body
    assert body["status"] == "ok"
    assert set(body["checks"]) == {
        "database",
        "database_role",
        "migrations",
        "redis",
        "object_storage",
    }


def test_ready_fails_when_api_uses_owner_role(database: Database, redis_url: str) -> None:
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="mhvp-ready")
        app = create_app(_settings(database.migrator_url, redis_url))  # type: ignore[arg-type]
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
    body = response.json()
    assert response.status_code == 503
    assert body["checks"]["database_role"] == {
        "status": "fail",
        "latency_ms": body["checks"]["database_role"]["latency_ms"],
        "detail": "runtime role owns database objects",
    }
    assert body["checks"]["database"]["status"] == "ok"
