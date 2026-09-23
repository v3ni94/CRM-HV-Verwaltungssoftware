import boto3
import pytest
from moto import mock_aws
from pydantic import SecretStr

from mhvp.core import storage_bootstrap
from mhvp.core.config import get_settings
from mhvp.core.storage import create_s3_client, ensure_bucket
from tests.conftest import make_settings


def test_create_client_requires_configuration() -> None:
    with pytest.raises(ValueError, match="not configured"):
        create_s3_client(make_settings())


def test_ensure_bucket_is_idempotent() -> None:
    settings = make_settings(
        s3_endpoint_url="https://s3.us-east-1.amazonaws.com",
        s3_access_key_id=SecretStr("testing"),
        s3_secret_access_key=SecretStr("testing"),
    )
    with mock_aws():
        client = create_s3_client(settings)
        assert ensure_bucket(client, "mhvp") is True
        assert ensure_bucket(client, "mhvp") is False
        names = [
            b["Name"] for b in boto3.client("s3", region_name="us-east-1").list_buckets()["Buckets"]
        ]
        assert names == ["mhvp"]


def _env(monkeypatch: pytest.MonkeyPatch, *, with_s3: bool) -> None:
    monkeypatch.setenv("MHVP_DATABASE_URL", "postgresql+psycopg://unit@127.0.0.1:1/unit")
    monkeypatch.setenv("MHVP_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("MHVP_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("MHVP_ENV", "test")
    for name in ("MHVP_S3_ENDPOINT_URL", "MHVP_S3_ACCESS_KEY_ID", "MHVP_S3_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    if with_s3:
        monkeypatch.setenv("MHVP_S3_ENDPOINT_URL", "https://s3.us-east-1.amazonaws.com")
        monkeypatch.setenv("MHVP_S3_ACCESS_KEY_ID", "testing")
        monkeypatch.setenv("MHVP_S3_SECRET_ACCESS_KEY", "testing")
    get_settings.cache_clear()


def test_bootstrap_job(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, with_s3=True)
    try:
        with mock_aws():
            assert storage_bootstrap.main() == 0
            assert storage_bootstrap.main() == 0
    finally:
        get_settings.cache_clear()


def test_bootstrap_job_fails_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch, with_s3=False)
    try:
        assert storage_bootstrap.main() == 1
    finally:
        get_settings.cache_clear()
