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
    # Directory on the worker that holds the objektakte export files (M35 Stufe 5). A tenant's
    # ``dump_path`` must lie inside it so that no tenant setting can point the worker at an
    # arbitrary file (another tenant's export, system files); see docs/reviews 26.09.2026.
    objektakte_dump_dir: str = "/data/objektakte-export"
    # Size limit of one export file the worker reads for the differential import (checked via
    # stat before reading). The upload path has its own 200 MB limit.
    objektakte_dump_max_bytes: int = Field(default=512 * 1024 * 1024, gt=0, le=4 * 1024**3)

    # Rate limits per minute (A49): operator configuration, not a legal rule. Authenticated
    # requests count per tenant and user or API key, unauthenticated ones per client address.
    rate_limit_enabled: bool = True
    rate_limit_per_minute_user: int = Field(default=600, ge=1)
    rate_limit_per_minute_anonymous: int = Field(default=120, ge=1)
    # Only behind a proxy that overwrites X-Forwarded-For (Traefik); otherwise spoofable.
    rate_limit_trust_forwarded_for: bool = False

    # Handover photos (M30-04): longest edge after scaling, metadata is always stripped.
    handover_image_max_edge: int = Field(default=2000, ge=100, le=20000)

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
    # Public URLs for the OAuth redirect (API callback) and the return to the CRM screen.
    api_public_url: str | None = None
    web_crm_url: str | None = None
    # Public URL of the portal (M21), used in invitation texts (M30-01); omitted if unset.
    web_portal_url: str | None = None
    # WhatsApp Business Platform (Meta Cloud API, M35): app level secrets shared by all
    # tenants of this Meta App; per tenant config (phone_number_id, access token, templates)
    # lives in ``mhvp.sla.models.WhatsAppConfig``. Webhook verification (GET) compares
    # ``hub.verify_token`` against this value; status updates (POST) are checked against
    # ``whatsapp_app_secret`` via the ``X-Hub-Signature-256`` header.
    whatsapp_verify_token: SecretStr | None = None
    whatsapp_app_secret: SecretStr | None = None
    whatsapp_api_base_url: str = "https://graph.facebook.com/v21.0"

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
