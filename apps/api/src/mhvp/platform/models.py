"""Platform and tenant administration models (section 5, milestone M2).

Platform tables (no RLS, section 5.3): tenant, tenant_domain, app_user, membership,
refresh_token, trusted_device, oidc_client, oidc_authorization_code. All other tables are
tenant scoped.
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
    # M35 Stufe 3 (docs/plans/M35-objektakte-uebernahme.md, rule stage,
    # docs/rules/M35-02.md): {"auto_apply_threshold": float 0..1}. Missing key falls back to
    # `mhvp.objektakte.classification.DEFAULT_AUTO_APPLY_THRESHOLD`.
    objektakte_classification: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


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
