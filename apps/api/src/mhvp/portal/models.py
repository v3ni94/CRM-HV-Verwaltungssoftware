"""Portal accounts, invitations, access matrix and change proposals (6.9.6, 14, M21, M22)."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
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
