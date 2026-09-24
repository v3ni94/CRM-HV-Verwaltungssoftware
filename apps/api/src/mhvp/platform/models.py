"""Platform and tenant administration models (section 5, milestone M2).

Platform tables (no RLS, section 5.3): tenant, tenant_domain, app_user, membership,
refresh_token, oidc_client, oidc_authorization_code. All other tables are tenant scoped.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


def _enum(cls: type[StrEnum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class GateRequestStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


# Platform tables -----------------------------------------------------------------------


class Tenant(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenant"

    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        _enum(TenantStatus, "tenant_status"), nullable=False, default=TenantStatus.ACTIVE
    )


class TenantDomain(IdMixin, TimestampMixin, Base):
    """Host names resolving to a tenant (portal domains, section 3.3)."""

    __tablename__ = "tenant_domain"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    host: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="portal")


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "app_user"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    totp_secret: Mapped[str | None] = mapped_column(EncryptedText())
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Last accepted TOTP time step: a code is accepted once (replay protection, RFC 6238).
    totp_last_step: Mapped[int | None] = mapped_column(Integer)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Membership(IdMixin, TimestampMixin, Base):
    """User in a tenant. Platform level: login lists memberships before a tenant is chosen."""

    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        _enum(MembershipStatus, "membership_status"),
        nullable=False,
        default=MembershipStatus.ACTIVE,
    )


class RefreshToken(IdMixin, Base):
    """Rotating refresh token; one family per login session (device list)."""

    __tablename__ = "refresh_token"
    __table_args__ = (Index("ix_refresh_token_family_id", "family_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE")
    )
    user_agent: Mapped[str | None] = mapped_column(String(300))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OidcClient(IdMixin, TimestampMixin, Base):
    """Relying party of the platform OIDC provider (existing tools, section 3.4)."""

    __tablename__ = "oidc_client"

    client_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    redirect_uris: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    client_secret_hash: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class OidcAuthorizationCode(IdMixin, Base):
    __tablename__ = "oidc_authorization_code"

    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[str | None] = mapped_column(String(255))
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Tenant scoped tables ------------------------------------------------------------------


class Role(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "role"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String(63), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("role.id", ondelete="SET NULL")
    )


class RolePermission(IdMixin, TenantMixin, Base):
    __tablename__ = "role_permission"
    __table_args__ = (UniqueConstraint("tenant_id", "role_id", "resource", "action"),)

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), nullable=False
    )
    resource: Mapped[str] = mapped_column(String(63), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)


class MembershipRole(IdMixin, TenantMixin, Base):
    __tablename__ = "membership_role"
    __table_args__ = (UniqueConstraint("tenant_id", "membership_id", "role_id"),)

    membership_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("membership.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("role.id", ondelete="CASCADE"), nullable=False
    )


class TenantSettings(IdMixin, TimestampMixin, TenantMixin, Base):
    """Tenant configuration (section 5.2); JSON documents validated by pydantic schemas."""

    __tablename__ = "tenant_settings"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    company: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    branding: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    sources: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # 6.9.4: automatic postings are off unless explicitly released.
    auto_posting_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # AI provider routing (9.1): anthropic_first, openai_first, alternate, anthropic_only,
    # openai_only. The "_first" and "alternate" strategies fall back to the other provider when
    # the budget is exhausted or the provider fails; "_only" strategies never switch.
    ai_routing: Mapped[str] = mapped_column(
        String(24), nullable=False, default="anthropic_first", server_default="anthropic_first"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ApiKey(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "api_key"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReleaseGateRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    """Opening a release gate G1 to G5 for a documented scope (18.0, ADR 0003)."""

    __tablename__ = "release_gate_request"

    gate: Mapped[str] = mapped_column(String(2), nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[GateRequestStatus] = mapped_column(
        _enum(GateRequestStatus, "gate_request_status"),
        nullable=False,
        default=GateRequestStatus.REQUESTED,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_comment: Mapped[str | None] = mapped_column(Text)
