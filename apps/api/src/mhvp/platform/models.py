"""Platform and tenant administration models (section 5, milestone M2).

Platform tables (no RLS, section 5.3): tenant, tenant_domain, app_user, membership,
refresh_token, trusted_device, oidc_client, oidc_authorization_code. All other tables are
tenant scoped.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'failed')",
            name="verification_status",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    host: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="portal")
    # GA01-10: DNS check result (unverified, verified, failed), time and finding.
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unverified", server_default="unverified"
    )
    verification_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_finding: Mapped[str | None] = mapped_column(Text)


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = (
        Index(
            "uq_app_user_superadmin",
            "is_superadmin",
            unique=True,
            postgresql_where=text("is_superadmin"),
        ),
    )

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
    # Superadmin (ADR 0011, operator decision 26.09.2026): exactly one platform administrator
    # (partial unique index ``uq_app_user_superadmin``) may approve release gate requests alone
    # when the platform flag ``PlatformSettings.gate_superadmin_bypass`` is on. Granted only via
    # ``mhvp.platform.services.set_superadmin`` (seed or platform API), never by e-mail address.
    is_superadmin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # UI preferences bag (operator 27.09.2026, migration 0182): only the accepted keys in
    # ``mhvp.core.auth.routers`` are ever written; currently the collapsed/expanded state of the
    # main navigation groups (key ``nav_expanded_groups``, list of group ids).
    ui_preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class PlatformSettings(IdMixin, TimestampMixin, Base):
    """Platform wide switches (no tenant, no RLS; section 5.3). Exactly one row, created on
    first read. Every flag is a product safeguard decided by the operator, never a legal rule.

    ``gate_superadmin_bypass`` (ADR 0011, default false): with the flag on, the single
    superadmin (``User.is_superadmin``) may approve a release gate request he filed himself;
    the approval is recorded with ``four_eyes = false`` and the audit event carries
    ``superadmin_bypass = true``. With the flag off the four eyes rule of ADR 0003 applies
    unchanged. Changes are recorded in ``updated_by`` / ``version`` and in the application log.
    """

    __tablename__ = "platform_settings"

    gate_superadmin_bypass: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class PlatformAuditEvent(IdMixin, Base):
    """Append-only audit trail of platform actions without tenant context (AB13, GA01-10/12).

    Platform table, no RLS (section 5.3). ``payload`` never holds secrets.
    """

    __tablename__ = "platform_audit_event"
    __table_args__ = (Index("ix_platform_audit_event_occurred_at", "occurred_at"),)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )


class MaintenanceWindow(IdMixin, TimestampMixin, Base):
    """Announced maintenance window of the platform (GB16-01, section 16 availability).

    Platform table, no RLS (section 5.3). A window is never deleted, only cancelled, so the audit
    trail and the availability evaluation (planned downtime) stay traceable.
    """

    __tablename__ = "platform_maintenance_window"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_platform_maintenance_window_period"),
        CheckConstraint(
            "notice_hours IS NULL OR (notice_hours >= 0 AND notice_hours <= 720)",
            name="ck_platform_maintenance_window_notice",
        ),
        Index("ix_platform_maintenance_window_starts_at", "starts_at"),
    )

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text_de: Mapped[str] = mapped_column(Text, nullable=False)
    text_en: Mapped[str] = mapped_column(Text, nullable=False)
    notice_hours: Mapped[int | None] = mapped_column(Integer)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AvailabilityMeasurement(IdMixin, TimestampMixin, Base):
    """Monthly availability figure of one measuring point (GB16-02, target 99,5 percent).

    The figure is imported from the external monitoring (Uptime Kuma), never computed or invented
    here. One row per month and measuring point; changes are recorded in the platform audit.
    """

    __tablename__ = "platform_availability_measurement"
    __table_args__ = (
        UniqueConstraint("month", "probe", name="uq_platform_availability_measurement_month_probe"),
        CheckConstraint(
            "uptime_percent >= 0 AND uptime_percent <= 100",
            name="ck_platform_availability_measurement_percent",
        ),
    )

    month: Mapped[date] = mapped_column(Date, nullable=False)
    probe: Mapped[str] = mapped_column(String(20), nullable=False)
    uptime_percent: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    source_note: Mapped[str] = mapped_column(String(200), nullable=False)


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
    # The user's contact record in this tenant (operator 25.09.2026: every user is a contact).
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL")
    )
    # Kompetenzen des Mitglieds (operator 25.09.2026, docs/rules): Liste von Codes aus dem
    # Katalog ``mhvp.tickets.competences.COMPETENCE_CATALOGUE`` (ggf. um mandantenspezifische
    # Codes aus ``TenantSettings.competence_catalogue_extra`` erweitert). Steuert die
    # Themen-Zuweisung eingehender Tickets (E-Mail-Optimierung M20).
    competences: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Mobilnummer für SMS-Eskalationen an die Bereitschaft (M35).
    mobile_phone: Mapped[str | None] = mapped_column(String(40))
    # Zugriffsbereich je Rechtsträger (A37, M18-02, docs/rules/M18-05-steuerberaterzugang.md):
    # Liste von ``legal_entity.id`` als Strings. Nur für Rollen mit eingeschränktem Bereich
    # wirksam (``mhvp.core.auth.scope.SCOPED_ROLES``, heute Steuerberater); leere Liste
    # bedeutet dort kein Zugriff. Für alle anderen Rollen ohne Wirkung.
    legal_entity_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # Objektzuordnung (3.4, M2-02/S16-02, docs/rules/M2-02-objektzuordnung.md, migration 0263):
    # Liste von ``property.id`` als Strings. Leere Liste bedeutet keine Einschränkung; eine
    # nicht leere Liste beschränkt alle Rollen außer den Administratorrollen
    # (``mhvp.core.auth.scope.PROPERTY_UNSCOPED_ROLES``) auf diese Objekte.
    property_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # M20-03 (Betreiberentscheidung 26.09.2026, docs/rules/M20-06-mail-versand-nachweis.md,
    # Abschnitt Direktversand): Antworten aus dem Ticket dieses Mitglieds brauchen die Freigabe
    # einer zweiten Person (Grund ``azubi`` oder ``neuer_mitarbeiter``, optional befristet bis
    # ``reply_approval_until`` einschließlich). Ohne Kennzeichen sendet ein Mitglied mit
    # ``communication:approve`` seine Ticketantwort direkt. Pflege nur mit
    # ``tenant_settings:update``; jede Änderung als ``membership.reply_approval_changed``.
    reply_approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    reply_approval_reason: Mapped[str | None] = mapped_column(String(32))
    reply_approval_until: Mapped[date | None] = mapped_column(Date)
    # Position und Durchwahl für die E-Mail-Signatur (operator 27.09.2026, migration 0215,
    # ``mhvp.communication.signatures``): Freitext, Vorschläge aus dem Katalog
    # ``POSITION_CATALOGUE`` plus ``TenantSettings.position_catalogue_extra``.
    position: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(40))


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


class TrustedDevice(IdMixin, Base):
    """Trusted device for skipping TOTP after a successful login (Produktschutz, operator
    decision 25.09.2026). Platform table: it is checked before a tenant context exists, like
    ``refresh_token``. ``tenant_id`` is only informational (the tenant of the login it was
    created on) and never restricts which tenant the device may be used for."""

    __tablename__ = "trusted_device"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebAuthnCredential(IdMixin, Base):
    """Registered WebAuthn/passkey authenticator as optional second factor (3.4, M2-03/S16-01,
    migration 0263). Platform table like ``trusted_device`` (checked before a tenant context
    exists). Registration and assertion live in ``mhvp.core.auth.webauthn`` behind
    ``Settings.webauthn_enabled``."""

    __tablename__ = "webauthn_credential"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Credential ID and COSE public key, base64url without padding (WebAuthn Level 2).
    credential_id: Mapped[str] = mapped_column(String(1400), unique=True, nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    transports: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    aaguid: Mapped[str | None] = mapped_column(String(36))
    label: Mapped[str | None] = mapped_column(String(200))
    # Optional per credential (S16-01, migration 0298): the passkey may also sign in without a
    # password (discoverable credential with user verification). Default: second factor only.
    passwordless: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint(
            "ticket_reopen_window_days BETWEEN 0 AND 3650",
            name="ticket_reopen_window_days_range",
        ),
        # Gmail back channel (rule M20-08, migration 0224).
        CheckConstraint(
            "gmail_done_sync_mode IN ('off', 'record_only', 'done')",
            name="gmail_done_sync_mode_values",
        ),
        CheckConstraint(
            "gmail_settle_seconds BETWEEN 0 AND 3600", name="gmail_settle_seconds_range"
        ),
        CheckConstraint(
            "portal_second_factor IN ('account_choice', 'required')",
            name="portal_second_factor_values",
        ),
        CheckConstraint(
            "gmail_reconcile_grace_seconds BETWEEN 60 AND 3600",
            name="gmail_reconcile_grace_seconds_range",
        ),
        CheckConstraint(
            "export_retention_days IS NULL OR export_retention_days BETWEEN 1 AND 3650",
            name="export_retention_days_range",
        ),
    )

    # B20: second factor in the customer portal. ``account_choice`` (default, operator decision
    # 26.09.2026, M2-01) leaves the optional e-mail code to each portal account; ``required``
    # makes the tenant demand the e-mail code for every magic link login.
    portal_second_factor: Mapped[str] = mapped_column(
        String(16), nullable=False, default="account_choice", server_default="account_choice"
    )
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
    # Google OAuth client of the tenant for Gmail mailboxes (M20-01); env settings are the
    # platform wide fallback. The secret is encrypted and never returned by the API.
    google_client_id: Mapped[str | None] = mapped_column(String(200))
    google_client_secret: Mapped[str | None] = mapped_column(EncryptedText())
    # Kompetenzkatalog-Erweiterung des Mandanten (operator 25.09.2026): zusätzliche Codes, Shape
    # je Eintrag {"code": str, "label": str}. Keine Migration nötig, um weitere Kompetenzen
    # aufzunehmen; siehe ``mhvp.tickets.competences``.
    competence_catalogue_extra: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    # E-Mail-Signatur (operator 27.09.2026, migration 0215): manuell angelegte Positionen des
    # Mandanten (Liste von Strings) und die Signaturvorlage ``{"text": str|None, "html":
    # str|None, "logo_url": str|None}`` mit Platzhaltern; leer bedeutet Standard aus den
    # Firmendaten (``mhvp.communication.signatures``).
    position_catalogue_extra: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    signature_template: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Rechnungs-Weiterleitung (M20, operator 25.09.2026): Zieladresse, Absender-Positivliste und
    # Lernliste bestätigter Absender (siehe ``mhvp.communication.forwarding``). Shape:
    # {"enabled": bool, "forward_address": str | None, "sender_allowlist": [str],
    #  "learning_list": [str], "confirmed_counts": {str: int}}.
    invoice_forwarding: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # M7 fast table import (operator 25.09.2026, docs/rules/M7-06.md): CSV/XLSX contact imports
    # first run one small "map_columns" call, then process rows deterministically instead of
    # sending every row through the LLM. Default on; falls back to the chunked LLM path per run
    # when the mapping has low confidence or no header. Product safeguard, not a legal duty.
    ai_fast_table_import: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # M14-05 automatischer Belegeingang: bei true startet der Gmail-Abruf für neue PDF-Anhänge,
    # die nach der Heuristik in ``mhvp.communication.invoice_intake`` wie eine Rechnung aussehen,
    # je Anhang genau einen ``extract_invoice``-Lauf (nur Vorschlag). Standard aus; Aktivierung
    # und Kostenrahmen entscheidet der Betreiber.
    invoice_intake_auto: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # M7-09, M12-01 KI-Kontierung (``propose_posting``): Bankumsätze enthalten Personenbezug;
    # die Aufgabe läuft nur bei true und freigegebenem Anbieter mit AVV. Standard aus; das
    # Ergebnis ist immer nur ein Vorschlag (entity_type posting), nie eine Buchung.
    ai_posting_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Portalrechte je CRM-Rolle (Betreiberentscheidung 25.09.2026, M2-08 entschieden,
    # docs/rules/M2-07.md): Überschreibungen der eingebauten Grundeinstellung
    # (``mhvp.portal.staff_access.DEFAULT_STAFF_PORTAL_PERMISSIONS``). Shape:
    # {"<role_code>": ["documents:read", ...]}. Fehlende Rollen nutzen die Grundeinstellung.
    portal_role_permissions: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # M13-01 to M13-03 (migration 0177, docs/rules/M13-01.md to M13-03.md): receivable rules
    # of the tenant. Shape: {"enabled": bool, "proration_method": "calendar_days" |
    # "thirty_360" | "full_month", "vat_enabled": bool}. Default off: pro rata amounts, non
    # monthly instalments and VAT stay manual items until the operator releases the rules
    # (draft behind G1, tax adviser review open).
    receivable_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # M35 Stufe 3 (docs/plans/M35-objektakte-uebernahme.md, rule stage,
    # docs/rules/M35-02.md): {"auto_apply_threshold": float 0..1}. Missing key falls back to
    # `mhvp.objektakte.classification.DEFAULT_AUTO_APPLY_THRESHOLD`.
    objektakte_classification: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # M20-03 Notbremse (Betreiberentscheidung 26.09.2026, docs/rules/M20-06, Abschnitt
    # Direktversand): bei true brauchen alle Ticketantworten des Mandanten die Freigabe einer
    # zweiten Person, unabhängig vom Kennzeichen je Mitglied. Standard aus (Direktversand für
    # Mitglieder mit ``communication:approve`` ohne Kennzeichen). Änderung wird als
    # ``tenant_settings.updated`` protokolliert.
    ticket_reply_approval_all: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Wiedereröffnungsfenster in Kalendertagen (Betreiberentscheidung 28.09.2026, Regel M19-10,
    # Migration 0219): eine neue Mail öffnet ein abgeschlossenes Ticket nur wieder, wenn der
    # Abschluss höchstens so viele Tage zurückliegt (Betreiberzeitzone); sonst entsteht ein
    # Folgeticket mit Verweis auf den Vorgänger. Standard 30, 0 bedeutet immer Folgeticket.
    ticket_reopen_window_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default=text("30")
    )
    # Standardfrist der Bereitstellung von Einsichtspaketen in Tagen (P08-04, M25-07, PÜ13,
    # Migration 0287): NULL bedeutet ohne Ablauf. Gilt nur, wenn beim Erzeugen des Pakets keine
    # Frist angegeben ist; die Frist je Paket bleibt überschreibbar.
    inspection_package_default_days: Mapped[int | None] = mapped_column(Integer)
    # T01-01, migration 0301: retention of tenant export archives in days; NULL (default) means
    # no automatic deletion. Applied when an archive becomes ready (expires_at of the job) and
    # by the daily purge to ready archives without an expiry.
    export_retention_days: Mapped[int | None] = mapped_column(Integer)
    # Lernbeispiele aus Ticketabschlüssen (ADR 0010, M7-04, Regel M19-07, Migration 0134):
    # bei false wird beim Abschluss kein ``AiExample`` (Aufgabe ``ticket_resolution``)
    # gespeichert. Standard aus (Regel 0.1.3: Datenschutzregel offen); der Betreiber schaltet
    # je Mandant ein. Vorhandene Beispiele werden mit dem Schalter nicht gelöscht.
    ai_learning_examples_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Aufbewahrung der Lernbeispiele in Monaten (ADR 0010 Nachtrag 27.09.2026, Migration 0156):
    # der tägliche Lauf ``mhvp.ai.examples_retention`` löscht Beispiele, die älter sind.
    # Standard 24 Monate; Änderung wird als ``tenant_settings.updated`` protokolliert.
    ai_learning_examples_retention_months: Mapped[int] = mapped_column(
        Integer, nullable=False, default=24, server_default=text("24")
    )
    # Lernender Buchhalter (ADR 0014, Regel M12-04, Migration 0232): bei true schreibt die
    # Plattform je Bankumsatz das Vorschlags- und Entscheidungsprotokoll ``posting_decision``
    # (Snapshot der Stufe-1-Vorschläge, Entscheidung der Person mit Diff, Ablehnung mit
    # Grund). Standard aus, weil der Speicher Zahlerdaten (IBAN-Fingerabdrücke, Zwecktoken)
    # enthält und die Datenschutzprüfung des Betreibers offen ist (OPEN_QUESTIONS M12-06).
    # Änderung nur über ``PUT /banking/learning`` (accounting:approve plus
    # tenant_settings:update, Grund, Ereignis). Der Schalter bucht nichts und öffnet kein Gate.
    learning_bookkeeper_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Lern-Workflow (rule M9-11, migration 0218): number of consistent manual decisions of the
    # same sender without a contradicting decision after which a rule is proposed. Standard 5
    # (assumption A-071, docs/ASSUMPTIONS.md); a proposal never activates itself.
    rule_proposal_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default=text("5")
    )
    # Automatikstufen je Fallklasse (ADR 0014 Nachtrag S4, Regel M12-05, Migration 0241):
    # {"debtor_full": "L1", ...}; fehlende Klassen stehen auf L0. Anhebung nur über
    # ``bookkeeping_level_request`` (Antrag und Freigabe durch zwei Personen), Absenkung
    # sofort; Klassendeckel in ``mhvp.banking.levels.CLASS_CAPS``. Kein Gate.
    bookkeeping_automation: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Lernende Bankregeln (Regel M12-06, Migration 0241): Schwelle gleicher Entscheidungen bis
    # zum Regelvorschlag (Standard 5, Annahme A-086) und die niedrigere Schwelle für
    # wiederkehrende Muster mit gleicher Gegenpartei und gleichem Betrag (Standard 3, A-086).
    bank_rule_proposal_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default=text("5")
    )
    bank_rule_recurring_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default=text("3")
    )
    # Ausgangsautomatik gegen Sachkonto (Stufe L2b, OPEN_QUESTIONS M12-05): Standard aus; ohne
    # den Schalter bucht der Runner keine Klasse recurring_expense.
    auto_posting_outgoing_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Erledigungsarten der Erledigungsnotiz je Mandant (Regel M19-07, Entscheidung M19-04 vom
    # 26.09.2026, ``mhvp.tickets.resolution_kinds``). Shape:
    # {"disabled": ["<code eingebauter Art>", ...], "custom": [{"code": str, "label": str}, ...]}.
    # ``disabled`` darf ``sonstiges`` und ``zusammengefuehrt`` nicht enthalten, ``custom``
    # höchstens 30 Einträge mit Slug-Code (``^[a-z0-9][a-z0-9_]{1,31}$``), der keiner
    # eingebauten Art entspricht. Leeres Objekt bedeutet: alle eingebauten Arten aktiv.
    resolution_kinds: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # Hallo-Heidi-Anrufe (Betreiberauftrag 26.09.2026, ``mhvp.tickets.call_assistant``):
    # Erkennung der Gesprächsprotokoll-Mails. Shape: {"enabled": bool, "sender_patterns": [str],
    # "keywords": [str]}; fehlende Schlüssel nutzen die eingebauten Muster.
    call_assistant: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # M20-04 Vier-Augen-Prinzip beim Mailversand (mhvp.communication.mail_approval, Migration
    # 0173): ``all`` (jede ausgehende Mail braucht eine zweite Person), ``external_only`` (nur
    # Mails an Kontakte der Kategorie Behörde/Gericht/Investor, Standard) oder ``off``
    # (Verfasser darf eigene Entwürfe selbst versenden). Der Schalter steuert nur die
    # Identitätsprüfung; die Re-Authentifizierung bei der Freigabe gilt unabhängig davon immer.
    mail_approval_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="external_only", server_default="external_only"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Messdienstleister module (stage 1): all write endpoints of /metering stay locked until the
    # tenant switches the module on (default off, master prompt Messdienstleister section 14).
    metering_module_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Offline Erfassung des Übergabeprotokolls (rule M30-10, ADR 0016, migration 0245): with
    # true the CRM editor queues changes on the device while offline and the API accepts
    # queued items with X-Captured-At. Default off (operator decision 28.09.2026 with the data
    # protection conditions of the ADR).
    handover_offline_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Verbrauchsinformation nach § 6a HeizkostenV (rule H03, migration 0238): monthly job per
    # tenant (default off), portal notification (default off) and the operator's confirmation
    # that the template content was verified; tenants see nothing before that confirmation.
    consumption_info_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    consumption_info_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    consumption_info_template_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Umlaufbeschluss mit abgesenkter Mehrheit (M25-02, migration 0166): default off, the
    # circular resolution then stays unanimous in text form only.
    hoa_circular_lower_majority_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Einladungsfrist in Wochen (M25-03, migration 0187): draft default 3, source status
    # "to be verified"; the check only warns and asks for a documented reason.
    hoa_invitation_weeks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    # Virtuelle Versammlung (V13, migration 0187): default off, until then only presence and
    # hybrid meetings can be created.
    hoa_virtual_meetings_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # GA07-01 (migration 0308): lock a virtual meeting whose enabling resolution is valid for
    # more than three years after its date; default off (only a notice), legal question open.
    hoa_virtual_basis_term_lock_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # Rückkanal Gmail zu Plattform (rule M20-08, migration 0224, docs/rules/M20-08): mode
    # ``off`` (label changes are ignored), ``record_only`` (default: states and events are
    # recorded, nothing changes status) or ``done`` (a mail archived in Gmail by the
    # authoritative copies becomes done, optionally closing its ticket). ``done`` needs the
    # confirmed spike (``gmail_spike_confirmed_at``). The other switches guard the mode:
    # trash counts like archive, restoring in Gmail reopens, restoring from the CRM writes
    # INBOX back (default off), settle period and reconcile grace in seconds, work labels
    # that keep a mail open, auto close also of assigned tickets (default off).
    gmail_done_sync_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="record_only", server_default="record_only"
    )
    gmail_done_closes_ticket: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    gmail_done_on_trash: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    gmail_reopen_on_unarchive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    gmail_restore_inbox_on_reopen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    gmail_settle_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=180, server_default=text("180")
    )
    gmail_reconcile_grace_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=300, server_default=text("300")
    )
    gmail_keep_open_labels: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    gmail_close_assigned_tickets: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    gmail_spike_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gmail_spike_protocol_ref: Mapped[str | None] = mapped_column(String(500))


class VatStatus(StrEnum):
    UNSET = "unset"
    REGELBESTEUERT = "regelbesteuert"
    KLEINUNTERNEHMER = "kleinunternehmer"


class ChartOfAccountsKind(StrEnum):
    UNSET = "unset"
    SKR03 = "skr03"
    SKR04 = "skr04"


class TenantBillingSettings(IdMixin, TimestampMixin, TenantMixin, Base):
    """Rechnungsstellung und Steuer je Mandant (operator decision 25.09.2026, M13-04/M18-01).

    The invoicing entity is always the tenant the user is logged in as. Everything here is
    nullable/unset by default; no value is invented. Numbering is allocated gapless per
    ``invoice_prefix`` and calendar year via ``mhvp.accounting.numbering.allocate_invoice_number``
    (row locked counter, mirroring ``JournalNumberCounter``).
    """

    __tablename__ = "tenant_billing_settings"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    invoice_prefix: Mapped[str | None] = mapped_column(String(16))
    vat_status: Mapped[VatStatus] = mapped_column(
        _enum(VatStatus, "tenant_vat_status"),
        nullable=False,
        default=VatStatus.UNSET,
        server_default="unset",
    )
    # Encrypted at rest (EncryptedText); only the last 4 characters are ever returned by the API.
    vat_id: Mapped[str | None] = mapped_column(EncryptedText())
    tax_number: Mapped[str | None] = mapped_column(EncryptedText())
    # Leitweg-ID for XRechnung to public sector recipients (optional, not a secret).
    leitweg_id: Mapped[str | None] = mapped_column(String(64))
    # Payee IBAN of the invoicing tenant for XRechnung (BT-84, BR-61); encrypted at rest and
    # masked in the API like the tax identifiers (A12). Operator entry only, never invented.
    payee_iban: Mapped[str | None] = mapped_column(EncryptedText())
    # Mandatory note for Kleinunternehmer invoices (§ 19 UStG); the operator enters the wording.
    kleinunternehmer_note: Mapped[str | None] = mapped_column(Text)
    # DATEV Buchungsstapel export parameters (M18-01); export stays blocked until all three of
    # consultant_number, client_number and chart_of_accounts are set.
    datev_consultant_number: Mapped[str | None] = mapped_column(String(32))
    datev_client_number: Mapped[str | None] = mapped_column(String(32))
    datev_chart_of_accounts: Mapped[ChartOfAccountsKind] = mapped_column(
        _enum(ChartOfAccountsKind, "tenant_chart_of_accounts_kind"),
        nullable=False,
        default=ChartOfAccountsKind.UNSET,
        server_default="unset",
    )
    datev_account_length: Mapped[int | None] = mapped_column(Integer)
    datev_fiscal_year_start_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Tenant wide SEPA creditor identifier used when the collecting legal entity has none of
    # its own (M15-02, pain.008); operator entry only, format not verified (M15-01).
    sepa_creditor_id: Mapped[str | None] = mapped_column(String(35))


class InvoiceNumberCounter(IdMixin, TenantMixin, Base):
    """Gapless outgoing invoice numbering per tenant/prefix/year (operator decision 25.09.2026):
    format PREFIX-JJJJ-000001. The row is locked while a number is allocated, mirroring
    ``mhvp.accounting.models.JournalNumberCounter``."""

    __tablename__ = "invoice_number_counter"
    __table_args__ = (UniqueConstraint("tenant_id", "prefix", "year"),)

    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


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
    # False only for an approval by the superadmin without a second person (ADR 0011,
    # platform flag ``gate_superadmin_bypass``); true for every regular decision.
    four_eyes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # GA14-04, migration 0304: opening and revocation are kept separately so a revocation
    # never overwrites who opened the gate; ``evidence_document_id`` links the evidence.
    opened_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_comment: Mapped[str | None] = mapped_column(Text)
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document.id", ondelete="RESTRICT", name="fk_release_gate_request_evidence_doc"),
    )
    # GA14-02: structured scope, NULL means all (default); GA14-03: checklist code -> note.
    scope_property_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    scope_legal_entity_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True))
    )
    scope_functions: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)))
    checklist: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class TenantExportJob(IdMixin, TimestampMixin, TenantMixin, Base):
    """Full tenant export started by the tenant administrator (M2-01, 5.3). The archive is built
    by the Celery job ``mhvp.platform.tenant_export_job`` and kept in the object store."""

    __tablename__ = "tenant_export_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed', 'expired')",
            name="tenant_export_job_status",
        ),
        Index("ix_tenant_export_job_tenant", "tenant_id", "created_at"),
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued"
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(512))
    size: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # T01-01, migration 0301: end of retention of the archive in the object store (set when the
    # archive is ready and the tenant has ``export_retention_days``); NULL keeps it.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
