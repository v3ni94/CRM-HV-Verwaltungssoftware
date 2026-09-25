"""Runtime settings from environment variables (prefix ``MHVP_``).

Connection strings and credentials are ``SecretStr`` so they never end up in logs or reprs.
No secret has a default value; missing required settings fail at startup.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mhvp import __version__


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class LogFormat(StrEnum):
    JSON = "json"
    CONSOLE = "console"


LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Value used in .env.example; refused in staging and prod.
PLACEHOLDER_SECRET = "change-me"  # noqa: S105 (marker, not a credential)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MHVP_", extra="ignore", frozen=True)

    env: Environment = Environment.DEV
    app_version: str = __version__
    log_level: LogLevel = "INFO"
    log_format: LogFormat = LogFormat.JSON

    # Runtime role (mhvp_app): never superuser, never table owner (ADR 0002).
    database_url: SecretStr
    # Owner role (mhvp_migrator): only used by Alembic and the migrate job.
    migration_database_url: SecretStr | None = None
    alembic_config: Path = Path("alembic.ini")

    redis_url: SecretStr
    celery_broker_url: SecretStr
    celery_result_backend: SecretStr | None = None

    # Object storage is addressed through the S3 API only (ADR 0005).
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_bucket: str = "mhvp"
    # Upload limit per document (A-016); larger files go through import runs later.
    # Run AI tasks inside the request instead of the worker (development and tests only).
    ai_inline: bool = False
    document_max_bytes: int = Field(default=50 * 1024 * 1024, gt=0, le=1024 * 1024 * 1024)

    health_check_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    # Envelope encryption (3.5): base64 encoded 32 byte master key, never stored in the DB.
    master_key: SecretStr | None = None
    # ES256 private key (PEM) for access tokens and OIDC id tokens.
    jwt_private_key: SecretStr | None = None
    jwt_issuer: str = "http://api.localhost"
    access_token_ttl_seconds: int = Field(default=900, gt=0, le=3600)
    refresh_token_ttl_days: int = Field(default=30, gt=0, le=90)
    # Webhook targets on private networks are only allowed for local development and tests.
    webhook_allow_private_targets: bool = False
    # Google OAuth client of the platform for Gmail mailboxes (M20-01); the refresh token is
    # stored encrypted per mailbox.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    gmail_sync_batch: int = Field(default=50, ge=1, le=500)

    # Banking-Provider finAPI Access (M31, rein lesend). Projektkonfiguration, keine
    # Standard-Variablennamen des Anbieters. Ohne Werte meldet die Anwendung
    # "Bankanbindung noch nicht eingerichtet"; kein stiller Demo-Modus.
    banking_finapi_base_url: str | None = None  # z. B. https://sandbox.finapi.io
    banking_finapi_client_id: SecretStr | None = None
    banking_finapi_client_secret: SecretStr | None = None
    banking_finapi_callback_base_url: str | None = (
        None  # oeffentliche API-Basis fuer Rueckleitungen
    )
    banking_fetch_overlap_days: int = Field(default=10, ge=0, le=90)
    # Abruf synchron im Request statt ueber Celery (Tests/kleine Umgebungen).
    banking_inline: bool = False

    # AI gateway input limits (M7). Defaults fit a 200k-token context window; raise them only
    # together with a routed model whose window matches (e.g. 1M tokens), see ai/gateway.py.
    ai_max_input_chars: int = Field(default=600_000, ge=100_000, le=10_000_000)
    ai_max_document_chars: int = Field(default=250_000, ge=50_000, le=5_000_000)
    # Public URLs for the OAuth redirect (API callback) and the return to the CRM screen.
    api_public_url: str | None = None
    web_crm_url: str | None = None

    @model_validator(mode="after")
    def _guard_shared_environments(self) -> "Settings":
        if self.env not in (Environment.STAGING, Environment.PROD):
            return self
        if not self.s3_configured:
            raise ValueError("MHVP_S3_* settings are required in staging and prod")
        if self.master_key is None or self.jwt_private_key is None:
            raise ValueError(
                "MHVP_MASTER_KEY and MHVP_JWT_PRIVATE_KEY are required in staging and prod"
            )
        if self.webhook_allow_private_targets:
            raise ValueError("MHVP_WEBHOOK_ALLOW_PRIVATE_TARGETS must be false in staging and prod")
        if self.ai_inline:
            raise ValueError("MHVP_AI_INLINE must be false in staging and prod")
        for name, value in self.__dict__.items():
            if isinstance(value, SecretStr) and PLACEHOLDER_SECRET in value.get_secret_value():
                raise ValueError(f"MHVP_{name.upper()} still contains the .env.example placeholder")
        return self

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_endpoint_url and self.s3_access_key_id and self.s3_secret_access_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # values come from the environment
