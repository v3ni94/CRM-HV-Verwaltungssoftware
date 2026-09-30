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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
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
    )

    user_id: Mapped[uuid.UUID] = _fk("app_user.id")
    contact_id: Mapped[uuid.UUID] = _fk("contact.id")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="invited")
    invitation_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    invitation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M21-01: optional second factor by e-mail code on top of the magic link login, switched on
    # per account by the management (portal-admin); off by default (Produktschutz, docs/rules).
    magic_link_2fa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AccessGrant(IdMixin, TimestampMixin, TenantMixin, Base):
    """6.9.6: one matrix for UI, API, downloads, search and exports."""

    __tablename__ = "access_grant"
    __table_args__ = (Index("ix_access_grant_subject", "tenant_id", "account_id"),)

    account_id: Mapped[uuid.UUID] = _fk("portal_account.id", ondelete="CASCADE")
    scope_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # unit, contract, property, legal_entity
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
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
    __table_args__ = (UniqueConstraint("tenant_id", name="ux_portal_feature_setting_tenant"),)

    chat_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    chat_ai_prequalification_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    support_login_enabled: Mapped[bool] = mapped_column(
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
