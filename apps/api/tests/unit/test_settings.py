import pytest
from pydantic import SecretStr, ValidationError

from mhvp.core.config import Environment, Settings
from tests.conftest import make_settings


def test_secrets_are_not_rendered() -> None:
    settings = make_settings(
        database_url=SecretStr("postgresql+psycopg://mhvp_app:very-secret@db/mhvp"),
        s3_secret_access_key=SecretStr("also-secret"),
    )
    rendered = repr(settings) + str(settings.model_dump())
    assert "very-secret" not in rendered
    assert "also-secret" not in rendered


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MHVP_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(redis_url=SecretStr("redis://x"), celery_broker_url=SecretStr("memory://"))


@pytest.mark.parametrize("env", [Environment.STAGING, Environment.PROD])
def test_object_storage_required_outside_dev(env: Environment) -> None:
    with pytest.raises(ValidationError, match="MHVP_S3_"):
        make_settings(env=env)


def test_object_storage_configured_flag() -> None:
    settings = make_settings(
        s3_endpoint_url="http://objectstore:8333",
        s3_access_key_id=SecretStr("key"),
        s3_secret_access_key=SecretStr("secret"),
    )
    assert settings.s3_configured
    assert not make_settings().s3_configured


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MHVP_DATABASE_URL", "postgresql+psycopg://a@b/c")
    monkeypatch.setenv("MHVP_REDIS_URL", "redis://r")
    monkeypatch.setenv("MHVP_CELERY_BROKER_URL", "memory://")
    monkeypatch.setenv("MHVP_LOG_LEVEL", "DEBUG")
    settings = Settings()
    assert settings.log_level == "DEBUG"
    assert settings.database_url.get_secret_value() == "postgresql+psycopg://a@b/c"


def test_placeholder_secrets_refused_in_prod() -> None:
    storage = {
        "s3_endpoint_url": "http://objectstore:8333",
        "s3_access_key_id": SecretStr("key"),
        "s3_secret_access_key": SecretStr("secret"),
        "master_key": SecretStr("a2V5"),
        "jwt_private_key": SecretStr("pem"),
    }
    with pytest.raises(ValidationError, match="MHVP_DATABASE_URL still contains"):
        make_settings(
            env=Environment.PROD,
            database_url=SecretStr("postgresql+psycopg://mhvp_app:change-me@db/mhvp"),
            **storage,
        )
    prod = make_settings(env=Environment.PROD, **storage)
    assert prod.env is Environment.PROD
    dev = make_settings(database_url=SecretStr("postgresql+psycopg://a:change-me@db/x"))
    assert dev.env is Environment.TEST


def test_prod_requires_keys_and_no_private_webhooks() -> None:
    storage = {
        "s3_endpoint_url": "http://objectstore:8333",
        "s3_access_key_id": SecretStr("key"),
        "s3_secret_access_key": SecretStr("secret"),
    }
    with pytest.raises(ValidationError, match="MHVP_MASTER_KEY"):
        make_settings(env=Environment.PROD, **storage)
    with pytest.raises(ValidationError, match="PRIVATE_TARGETS"):
        make_settings(
            env=Environment.PROD,
            master_key=SecretStr("a2V5"),
            jwt_private_key=SecretStr("pem"),
            webhook_allow_private_targets=True,
            **storage,
        )
