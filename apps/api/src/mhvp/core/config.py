"""Runtime settings from environment variables (prefix ``MHVP_``).

Connection strings and credentials are ``SecretStr`` so they never end up in logs or reprs.
No secret has a default value; missing required settings fail at startup.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
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
    model_config = SettingsConfigDict(
        env_prefix="MHVP_", extra="ignore", frozen=True, populate_by_name=True
    )

    env: Environment = Environment.DEV
    app_version: str = __version__
    log_level: LogLevel = "INFO"
    log_format: LogFormat = LogFormat.JSON
    # OpenTelemetry tracing (M9-02, section 16): off unless an OTLP/HTTP endpoint is set.
    otel_endpoint: str | None = None
    otel_service_name: str = "mhvp-api"

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
    # objektakte preview images (M35, open question M35-02): the worker side directory that
    # holds objektakte's ``/data/previews`` tree (``<document id>/<page>.jpg``); read only, the
    # takeover copies into the object store (`mhvp.objektakte.previews`).
    objektakte_previews_dir: str = "/data/previews"
    # objektakte local classification model (M35-01): ``<version>/model_a.joblib`` plus
    # ``labels.json``; read only when the per tenant flag is on (`mhvp.objektakte.local_model`).
    objektakte_models_dir: str = "/data/models"
    # objektakte read API (M29 Stufe 4, contract in docs/integrations/objektakte.md): base URL
    # (".../api/crm/v1/"), bearer token and the tenant (slug) whose data objektakte holds. The
    # integration is off while URL, token or tenant is empty. The names of the contract
    # (``OBJEKTAKTE_API_URL`` ...) are accepted next to the ``MHVP_`` prefixed ones.
    objektakte_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "objektakte_api_url", "MHVP_OBJEKTAKTE_API_URL", "OBJEKTAKTE_API_URL"
        ),
    )
    objektakte_api_token: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "objektakte_api_token", "MHVP_OBJEKTAKTE_API_TOKEN", "OBJEKTAKTE_API_TOKEN"
        ),
    )
    objektakte_webhook_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "objektakte_webhook_secret",
            "MHVP_OBJEKTAKTE_WEBHOOK_SECRET",
            "OBJEKTAKTE_WEBHOOK_SECRET",
        ),
    )
    objektakte_tenant: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "objektakte_tenant", "MHVP_OBJEKTAKTE_TENANT", "OBJEKTAKTE_TENANT"
        ),
    )
    objektakte_api_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # Upload of CRM documents to objektakte (26.09.2026): documents linked to exactly one property
    # go to objektakte for filing in Drive and Paperless instead of the CRM's own mirrors. Needs
    # the read API above and a token with documents:write; off by default.
    objektakte_upload_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "objektakte_upload_enabled",
            "MHVP_OBJEKTAKTE_UPLOAD_ENABLED",
            "OBJEKTAKTE_UPLOAD_ENABLED",
        ),
    )
    # Time of day (HH:MM, Celery timezone Europe/Berlin) of the daily reconciliation report of
    # the parallel operation (13.1, A68); read and compare only, no posting.
    import_reconciliation_time: str = Field(default="05:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    # Rate limits per minute (A49): operator configuration, not a legal rule. Authenticated
    # requests count per tenant and user or API key, unauthenticated ones per client address.
    # WebAuthn/passkeys (M2-03/S16-01): off until released by the operator (P14-02). RP ID is
    # the registrable domain shared by CRM and portal; origins are the exact allowed origins.
    webauthn_enabled: bool = False
    webauthn_rp_id: str | None = None
    webauthn_rp_name: str = "MH Verwaltungsplattform"
    webauthn_origins: list[str] = Field(default_factory=list)

    rate_limit_enabled: bool = True
    rate_limit_per_minute_user: int = Field(default=600, ge=1)
    rate_limit_per_minute_anonymous: int = Field(default=120, ge=1)
    # Only behind a proxy that overwrites X-Forwarded-For (Traefik); otherwise spoofable.
    rate_limit_trust_forwarded_for: bool = False
    # WebAuthn option endpoints (W01-01): each call stores a challenge in Redis, so they get a
    # tighter limit per client address and per user inside a fixed window.
    webauthn_options_limit_per_ip: int = Field(default=60, ge=1)
    webauthn_options_limit_per_user: int = Field(default=20, ge=1)
    webauthn_options_window_seconds: int = Field(default=300, ge=1)

    # Handover photos (M30-04): longest edge after scaling, metadata is always stripped.
    handover_image_max_edge: int = Field(default=2000, ge=100, le=20000)
    # OpenImmo 1.2.7 XSD stored by the operator (M26-02); the schema is copyrighted by the
    # OpenImmo e.V. and not bundled. Empty: exports get a structural check only, with the
    # operator notice "XSD nicht hinterlegt".
    openimmo_xsd_path: str | None = None

    health_check_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    # Malware scan with ClamAV before any document is stored (operator decision 27.09.2026,
    # ``mhvp.documents.scan``). ``off`` skips the scan (dev and tests only), ``warn`` stores
    # when clamd is unreachable and journals the gap, ``enforce`` refuses then (503). Staging
    # and prod require ``enforce``; the runbook is docs/runbooks/virenscan.md.
    clamav_mode: Literal["off", "warn", "enforce"] = "off"
    clamav_host: str = "clamav"
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_timeout_seconds: float = Field(default=30.0, gt=0, le=600)

    # Envelope encryption (3.5): base64 encoded 32 byte master key, never stored in the DB.
    master_key: SecretStr | None = None
    # ES256 private key (PEM) for access tokens and OIDC id tokens.
    jwt_private_key: SecretStr | None = None
    jwt_issuer: str = "http://api.localhost"
    access_token_ttl_seconds: int = Field(default=900, gt=0, le=3600)
    refresh_token_ttl_days: int = Field(default=30, gt=0, le=90)
    # Webhook targets on private networks are only allowed for local development and tests.
    webhook_allow_private_targets: bool = False
    # Restore test job ``ops.backup_verify`` (A67, M9, 15.1): daily 02:00 on the worker. Runs
    # ``scripts/backup-verify.sh`` (needs PGDATABASE, BACKUP_DIR and PGHOST or BACKUP_COMPOSE
    # in the worker environment). Default off: the job then records "not configured" in the
    # operating metrics instead of failing. Storage location and keys remain M9-02.
    backup_verify_enabled: bool = False
    backup_verify_script: str = "scripts/backup-verify.sh"
    backup_verify_timeout_seconds: int = Field(default=1800, ge=30, le=21600)
    # Google OAuth client of the platform for Gmail mailboxes (M20-01); the refresh token is
    # stored encrypted per mailbox.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    gmail_sync_batch: int = Field(default=50, ge=1, le=500)
    # Gmail back channel (rule M20-08): ``message_labels`` calls per reconcile run and the
    # largest inbox listing the reconcile walks before it stops with ``listing_too_large``.
    gmail_state_reconcile_limit: int = Field(default=200, ge=1, le=5000)
    gmail_reconcile_listing_max: int = Field(default=20000, ge=500, le=200000)
    # Gmail push notifications (operator decision 26.09.2026: new mails appear immediately).
    # ``gmail_pubsub_topic`` is the full Pub/Sub topic name ``projects/<id>/topics/<name>``
    # that the operator creates in the Google Cloud project of the OAuth client and grants
    # ``roles/pubsub.publisher`` to ``gmail-api-push@system.gserviceaccount.com``; empty
    # keeps push off (the 5 minute beat sync remains the only fetch). ``gmail_push_token`` is
    # the shared secret the push subscription sends to ``/integrations/gmail/push`` (query
    # ``token`` or header ``X-MHVP-Push-Token``); without it the endpoint refuses every
    # delivery. ``gmail_push_audience`` additionally verifies the Pub/Sub OIDC token
    # (``Authorization: Bearer``) against this audience (optional, needs Google's JWKS).
    gmail_pubsub_topic: str | None = None
    gmail_push_token: SecretStr | None = None
    gmail_push_audience: str | None = None
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
    # finAPI Access (M11-01, operator decision 26.09.2026: aggregator finAPI first, EBICS
    # later). Default base URLs by data center, used when a tenant leaves ``base_url`` empty in
    # ``FinApiTenantConfig``; the official sandbox and live hosts [laut finAPI-Doku,
    # docs/integrations/finapi.md]. Client credentials are never here: they are stored
    # encrypted per tenant. Read only: no payment initiation (G2 closed).
    finapi_base_url_sandbox: str = "https://sandbox.finapi.io"
    finapi_base_url_live: str = "https://live.finapi.io"
    # FinTS/HBCI PIN/TAN (M11-01 addendum, operator decision 27.09.2026): registration
    # number of the product with the Deutsche Kreditwirtschaft (free "Antrag auf
    # Produktregistrierung", docs/integrations/fints.md). Without it no FinTS connection is
    # possible (python-fints 4 refuses to start a dialog). Read only, G2 stays closed.
    fints_product_id: str | None = None
    fints_product_version: str = "1.0"

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
        # Operator decision 27.09.2026: no productive document store without malware scan.
        if self.clamav_mode != "enforce":
            raise ValueError("MHVP_CLAMAV_MODE must be enforce in staging and prod")
        return self

    @property
    def objektakte_api_configured(self) -> bool:
        token = self.objektakte_api_token.get_secret_value() if self.objektakte_api_token else ""
        return bool((self.objektakte_api_url or "").strip() and token.strip())

    @property
    def objektakte_upload_active(self) -> bool:
        return self.objektakte_upload_enabled and self.objektakte_api_configured

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_endpoint_url and self.s3_access_key_id and self.s3_secret_access_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # values come from the environment
