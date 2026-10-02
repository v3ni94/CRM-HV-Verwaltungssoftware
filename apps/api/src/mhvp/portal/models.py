"""Portal accounts, invitations, access matrix and change proposals (6.9.6, 14, M21, M22)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class PortalAccount(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "portal_account"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id"),
        UniqueConstraint("tenant_id", "contact_id"),
        CheckConstraint(
            "status IN ('not_invited', 'invited', 'active', 'locked', 'expired', 'revoked')",
            name="status",
        ),
    )

    user_id: Mapped[uuid.UUID] = _fk("app_user.id")
    contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="invited")
    invitation_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    invitation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # GA02-07 (migration 0310): roles derived from the access grants (tenant, owner), time of
    # the invitation. The status is stored and maintained by mhvp.portal.status (6.2).
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), nullable=False, default=list, server_default=text("'{}'")
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M21-01: optional second factor by e-mail code on top of the magic link login, switched on
    # per account by the management (portal-admin); off by default (Produktschutz, docs/rules).
    magic_link_2fa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # GA11-01 (migration 0331): language chosen by the person, applied at login; null = browser.
    locale: Mapped[str | None] = mapped_column(String(8))


class AccessGrant(IdMixin, TimestampMixin, TenantMixin, Base):
    """6.9.6: one matrix for UI, API, downloads, search and exports."""

    __tablename__ = "access_grant"
    __table_args__ = (
        Index("ix_access_grant_subject", "tenant_id", "account_id"),
        # GA03-05: a document_class grant names the class (scope_id is then the legal entity).
        CheckConstraint(
            "scope_type <> 'document_class' OR document_class IS NOT NULL",
            name="document_class_scope",
        ),
    )

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    scope_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # unit, contract, property, legal_entity, document_class (6.9.6)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # GA03-05: document class (retention profile class) for scope_type document_class
    document_class: Mapped[str | None] = mapped_column(String(63))
    right: Mapped[str] = mapped_column(String(16), nullable=False)  # read, download, comment
    legal_basis: Mapped[str] = mapped_column(String(32), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # tenant, owner
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)


class ChangeRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    """Portal changes are proposals reviewed by the management, never self approved (14)."""

    __tablename__ = "portal_change_request"

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id")
    # address, phone, email, bank_account, meter_reading, invoice_submission
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # JSON; may contain an IBAN, therefore encrypted
    payload: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="proposed")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_note: Mapped[str | None] = mapped_column(Text)


class PortalReadReceipt(IdMixin, TimestampMixin, TenantMixin, Base):
    """Retrieval of a document through the portal (11.3, D34, A53).

    A row records only that a portal account opened or downloaded a document at a point in
    time. It is an indication ("Indiz"), never a delivery ("Zustellung") and never legally
    assessed receipt ("Zugang"): those stay in ``mhvp.communication`` (dispatch) and in the
    documented delivery date. Listing documents writes nothing; the expiry of an invitation
    writes nothing and triggers no legal consequence. No IP address is stored: a shortened
    address is not needed for the purpose and its lawfulness is not decided (rule 0.1.3).
    """

    __tablename__ = "portal_read_receipt"
    __table_args__ = (
        Index("ix_portal_read_receipt_document", "tenant_id", "document_id", "occurred_at"),
        CheckConstraint("kind IN ('opened', 'downloaded')", name="ck_portal_read_receipt_kind"),
    )

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    document_id: Mapped[uuid.UUID] = _fk("document.id", ondelete="CASCADE")
    # opened (metadata retrieved through the portal) or downloaded (content retrieved)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MagicLoginLink(IdMixin, TimestampMixin, TenantMixin, Base):
    """Magic link login (14 Portale, M21-01): a one time, time limited link e-mailed to the
    account's address, next to the existing password login (which stays available). Only the
    SHA-256 hash of the link token is stored, never the token itself (rule 0.1.13, no secret in
    the database in clear text); the API never returns it in a response body and the request
    log middleware never records a request body, so the raw token exists only in the outgoing
    mail. Single use (``used_at``) and 15 minutes valid (``expires_at``, docs/rules M21-01).

    The optional second factor (``PortalAccount.magic_link_2fa``) reuses the same row: an
    e-mail code is generated only after the link itself was verified, stored the same way
    (hash, 10 minutes, single use) and checked before a session is issued.
    """

    __tablename__ = "portal_magic_link"
    __table_args__ = (
        Index("ix_portal_magic_link_token", "tenant_id", "token_hash"),
        Index("ix_portal_magic_link_account", "tenant_id", "account_id"),
    )

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_hash: Mapped[str | None] = mapped_column(String(64))
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    code_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # GAI-310: wrong e-mail codes; at 5 the code and the link are invalid.
    code_failed_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )


class SepaMandateProposal(IdMixin, TimestampMixin, TenantMixin, Base):
    """A mandate confirmed in the portal, waiting for a staff decision (never active itself)."""

    __tablename__ = "portal_sepa_mandate_proposal"
    __table_args__ = (
        UniqueConstraint("tenant_id", "reference", name="ux_portal_sepa_mandate_reference"),
        Index("ix_portal_sepa_mandate_proposal_status", "tenant_id", "status"),
    )

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id")
    contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    contract_id: Mapped[uuid.UUID] = _fk("contract.id")
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id")
    creditor_id: Mapped[str] = mapped_column(String(35), nullable=False)
    reference: Mapped[str] = mapped_column(String(35), nullable=False)
    scheme: Mapped[str] = mapped_column(
        String(8), nullable=False, default="core", server_default="core"
    )
    sequence: Mapped[str] = mapped_column(
        String(16), nullable=False, default="recurrent", server_default="recurrent"
    )
    iban: Mapped[str] = mapped_column(EncryptedText(), nullable=False)
    iban_suffix: Mapped[str] = mapped_column(String(4), nullable=False)
    iban_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    bic: Mapped[str | None] = mapped_column(String(11))
    holder: Mapped[str] = mapped_column(String(200), nullable=False)
    mandate_text: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    evidence_document_id: Mapped[uuid.UUID] = _fk("document.id")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed", server_default="proposed"
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    contact_bank_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PortalFeatureSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """Portal feature switches per tenant (A.5 Verwalteransicht, M21-08). One row per tenant,
    all switches off by default (Produktschutz): chat at the ticket, AI pre-qualification of
    chat messages (additionally needs the approved AI provider with data processing
    agreement) and the read only support view (additionally needs the user's consent)."""

    __tablename__ = "portal_feature_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="ux_portal_feature_setting_tenant"),
        CheckConstraint(
            "owner_ticket_scope IN ('none', 'released', 'property')",
            name="owner_ticket_scope",
        ),
        CheckConstraint(
            "provider_rating_display IN ('off', 'staff', 'all')",
            name="provider_rating_display",
        ),
    )

    chat_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    chat_ai_prequalification_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    support_login_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # AE13 (P13-01, M21-06, migration 0369): rental income view for investors, off by default;
    # ticket scope of the owner view: none, released (visible_for owner) or property.
    owner_rental_income_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    owner_ticket_scope: Mapped[str] = mapped_column(
        String(16), nullable=False, default="released", server_default="released"
    )
    # AF15 (GAC-01, migration 0409): owner statements rental/SEV in the portal, off by default;
    # the output additionally needs release gate G3.
    owner_rental_statements_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # AG12 (AF25-02, migration 0430): owner statements whose legal entity is the community
    # itself (rental of common property) are shown to its owners only with this switch;
    # default off, decision AF25-02 open.
    owner_hoa_rental_statements_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # AG09 (GAF-36, migration 0427): receipt search of the owner per statement period, off by
    # default; the list additionally needs release gate G4.
    portal_owner_receipts_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # AE30 (AA14-02, migration 0386): display of the ratings of service providers (rating of a
    # completed work order). off (default): ratings stay internal at the work order; staff:
    # aggregated stars per provider for the management in the portal administration, never
    # shown to the provider or to third parties and never with the free text.
    provider_rating_display: Mapped[str] = mapped_column(
        String(16), nullable=False, default="off", server_default="off"
    )
    # AE28 (M7-06, SA-04, migration 0384): AI assistant for questions about the documents the
    # account may see (chat bot) and the privacy feature (released notice plus acknowledgement
    # per account) that the AI answer needs; both off by default (Produktschutz).
    chat_bot_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    privacy_feature_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # AF16 (GAC-02, migration 0410): released operating cost statements of the own tenancy
    # contracts in the tenant portal; off by default, additionally behind release gate G3.
    tenant_statement_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class PortalRepresentation(IdMixin, TimestampMixin, TenantMixin, Base):
    """Representative (Vertreter, Bevollmächtigter) of an owner (M21-05, 14 Eigentümer).

    The representative's portal account receives read only grants derived from the contracts
    of the represented contact, limited to the period of the power of attorney. The power of
    attorney document is mandatory (Vertretungsnachweis); revoking ends the access at once."""

    __tablename__ = "portal_representation"
    __table_args__ = (
        Index("ix_portal_representation_account", "tenant_id", "account_id"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_portal_representation_period"
        ),
        CheckConstraint("status IN ('active', 'revoked')", name="ck_portal_representation_status"),
    )

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    principal_contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    document_id: Mapped[uuid.UUID] = _fk("document.id")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    note: Mapped[str | None] = mapped_column(String(500))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PortalSupportConsent(IdMixin, TimestampMixin, TenantMixin, Base):
    """Consent of a portal user to a read only support view by the management (SA-02)."""

    __tablename__ = "portal_support_consent"
    __table_args__ = (Index("ix_portal_support_consent_account", "tenant_id", "account_id"),)

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PortalSupportAccess(IdMixin, TimestampMixin, TenantMixin, Base):
    """Log of every support view (SA-02): who, for which account, why, under which consent and
    which areas were shown. Rows are never changed or deleted by the application."""

    __tablename__ = "portal_support_access"
    __table_args__ = (Index("ix_portal_support_access_account", "tenant_id", "account_id"),)

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    consent_id: Mapped[uuid.UUID] = _fk("portal_support_consent.id", ondelete="RESTRICT")
    staff_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    areas: Mapped[str] = mapped_column(String(200), nullable=False)


class ProviderAvailability(IdMixin, TimestampMixin, TenantMixin, Base):
    """GA11-04 (14, Dienstleister Phase 4): availability window of a service provider, entered
    by the management and shown read only in the portal of the provider."""

    __tablename__ = "provider_availability"
    __table_args__ = (
        Index("ix_provider_availability_provider", "tenant_id", "provider_contact_id", "starts_at"),
        CheckConstraint("ends_at > starts_at", name="window"),
        CheckConstraint("kind IN ('available', 'unavailable')", name="kind"),
    )

    provider_contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="available")
    note: Mapped[str | None] = mapped_column(String(300))


class PortalChatPrivacyAck(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE28 (M7-06): acknowledgement of the released privacy notice for AI answers in the portal,
    per account and text version. A new approved version needs a new acknowledgement. The row
    proves only that the person took note; it is no consent decision and no legal basis."""

    __tablename__ = "portal_chat_privacy_ack"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "account_id", "text_block_id", name="ux_portal_chat_privacy_ack_text"
        ),
    )

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    text_block_id: Mapped[uuid.UUID] = _fk("legal_text_block.id", ondelete="RESTRICT")
    text_code: Mapped[str] = mapped_column(String(63), nullable=False)
    text_version: Mapped[int] = mapped_column(nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PortalChatLog(IdMixin, TimestampMixin, TenantMixin, Base):
    """AE28 (M7-06): log of every question to the portal assistant. The question is stored with
    IBAN, e-mail and phone masked (rule 0.1.13); the answer is the text shown to the person.
    ``technical_reason`` names why the AI stage did not run and is shown to the management only.
    Rows are never changed by the application; removal follows the retention decision (AE28-02)."""

    __tablename__ = "portal_chat_log"
    __table_args__ = (
        Index("ix_portal_chat_log_account", "tenant_id", "account_id", "created_at"),
        CheckConstraint("mode IN ('ai', 'search')", name="mode"),
        CheckConstraint(
            "status IN ('answered', 'not_answerable', 'failed', 'search_hits', 'no_sources', "
            "'pending', 'timeout')",
            name="status",
        ),
    )

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # GAE-29: claim marker of the worker job (set once, atomically; prevents a second provider call)
    job_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(40))
    technical_reason: Mapped[str | None] = mapped_column(String(500))
    # [{"document_id": ..., "title": ...}] of the checked sources, no excerpt (data minimisation)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    scope_documents: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
