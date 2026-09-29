"""lexoffice integration (M13-lexoffice, docs/integrations/lexoffice.md, docs/rules index).

Three tables, all tenant scoped (RLS, ADR 0002):

- ``LexofficeTenantConfig``: one row per tenant, the encrypted API key and the feature flag
  (``enabled``, default off, rule 0.1.1). Existence of a row is not enough by itself; ``enabled``
  must also be true, and export additionally needs release gate G1 open (money relevant, rule
  0.1.4, ``mhvp.core.release_gates``).
- ``LexofficeSyncRun``: protocol of every test connection, export and import run (rule 0.1.9,
  ADR 0004 style traceability), shown on the settings page ("letzte Läufe, Fehler").
- ``LexofficeExportLink``: dedup and audit trail for exported invoices/contacts (one lexoffice
  id per CRM entity and tenant). Import dedup instead reuses ``Document.source_system`` /
  ``Document.source_id`` (unique per tenant, migration 0011) with ``source_system="lexoffice"``
  and the lexoffice voucher id as ``source_id``; a duplicate document is refused there and the
  existing ``ReceiptDraft`` is reused, so no separate import table is needed.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


class LexofficeRunKind(StrEnum):
    TEST = "test"
    EXPORT_INVOICES = "export_invoices"
    EXPORT_CONTACTS = "export_contacts"
    IMPORT_RECEIPTS = "import_receipts"
    # Extension (rule INT-LEXO-01): queue batches, matching runs, lookups, files, drafts.
    CONTACT_MATCH = "contact_match"
    CONTACT_SYNC = "contact_sync"
    INVOICE_LOOKUP = "invoice_lookup"
    INVOICE_FILE = "invoice_file"
    INVOICE_DRAFT = "invoice_draft"
    PURGE = "purge"


class LexofficeRunStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"  # some items failed, see errors
    FAILED = "failed"


class LexofficeExportKind(StrEnum):
    INVOICE = "invoice"
    CONTACT = "contact"


class LexofficeLinkStatus(StrEnum):
    PROPOSED = "proposed"
    AMBIGUOUS = "ambiguous"
    REMOTE_ONLY = "remote_only"
    LINKED = "linked"
    PENDING = "pending"
    SYNCED = "synced"
    CONFLICT = "conflict"
    MANUAL_REQUIRED = "manual_required"
    ERROR = "error"
    REMOTE_MISSING = "remote_missing"
    UNLINKED_LOCAL = "unlinked_local"
    DISMISSED = "dismissed"


class LexofficeOutboxKind(StrEnum):
    CONTACT_CREATE = "contact_create"
    CONTACT_UPDATE = "contact_update"
    LOOKUP_INVOICE = "lookup_invoice"
    FETCH_INVOICE_FILE = "fetch_invoice_file"
    CREATE_INVOICE_DRAFT = "create_invoice_draft"
    REFRESH_LINK = "refresh_link"


class LexofficeOutboxStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    BLOCKED = "blocked"


class LexofficeInvoiceKind(StrEnum):
    """Invoice kinds mapped to a legal entity (operator decision 28.09.2026)."""

    BROKER = "broker"  # Maklerrechnungen
    CONSULTING = "consulting"  # Beratung
    MANAGEMENT = "management"  # Hausverwaltung


def _fk(target: str, *, nullable: bool = False, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


def _jsonb(default: str) -> Any:
    return mapped_column(
        JSONB,
        nullable=False,
        default=dict if default == "{}" else list,
        server_default=text(f"'{default}'::jsonb"),
    )


class LexofficeTenantConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    """One Lexware Office organisation. ``legal_entity_id`` NULL is the tenant default
    config (legacy ``/config`` endpoints); every other row belongs to one legal entity with
    its own API key (operator decision 28.09.2026, several organisations per tenant)."""

    __tablename__ = "lexoffice_tenant_config"
    __table_args__ = (
        Index(
            "uq_lexoffice_config_tenant_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("legal_entity_id IS NULL"),
        ),
        Index(
            "uq_lexoffice_config_tenant_entity",
            "tenant_id",
            "legal_entity_id",
            unique=True,
            postgresql_where=text("legal_entity_id IS NOT NULL"),
        ),
    )

    api_key: Mapped[str | None] = mapped_column(EncryptedText())
    legal_entity_id: Mapped[uuid.UUID | None] = _fk(
        "legal_entity.id", nullable=True, ondelete="RESTRICT"
    )
    label: Mapped[str | None] = mapped_column(String(120))
    organization_id: Mapped[str | None] = mapped_column(String(64))
    organization_name: Mapped[str | None] = mapped_column(String(200))
    profile_tax_type: Mapped[str | None] = mapped_column(String(32))
    profile_small_business: Mapped[bool | None] = mapped_column(Boolean)
    profile_business_features: Mapped[list[str]] = _jsonb("[]")
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    token_invalid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    avv_confirmed_on: Mapped[date | None] = mapped_column(Date)
    avv_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    avv_note: Mapped[str | None] = mapped_column(String(500))
    mailbox_id: Mapped[uuid.UUID | None] = _fk("mailbox.id", nullable=True, ondelete="SET NULL")
    sync_contacts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    sync_names: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    invoice_copies: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    invoice_drafts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    app_base_url: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        default="https://app.lexware.de",
        server_default="https://app.lexware.de",
    )
    base_url: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        default="https://api.lexware.io",
        server_default="https://api.lexware.io",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_message: Mapped[str | None] = mapped_column(Text)


class LexofficeSyncRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """One protocol row per test/export/import run (settings page "letzte Läufe, Fehler")."""

    __tablename__ = "lexoffice_sync_run"
    __table_args__ = (Index("ix_lexoffice_sync_run_tenant_created", "tenant_id", "created_at"),)

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    counts: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    errors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    started_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LexofficeExportLink(IdMixin, TimestampMixin, TenantMixin, Base):
    """One row per CRM entity successfully exported to lexoffice; prevents a second export of
    the same entity (idempotent, protokolliert) unless the caller explicitly re-exports."""

    __tablename__ = "lexoffice_export_link"
    __table_args__ = (
        Index(
            "uq_lexoffice_export_link_entity",
            "tenant_id",
            "entity_kind",
            "entity_id",
            unique=True,
        ),
    )

    entity_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    lexoffice_id: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[uuid.UUID | None] = _fk("lexoffice_sync_run.id", nullable=True)


class LexofficeInvoiceKindMapping(IdMixin, TimestampMixin, TenantMixin, Base):
    """Invoice kind (broker, consulting, management) to the invoicing legal entity; tenant
    configuration in the settings UI, seeded with the three kinds where the legal entities
    exist (operator decision 28.09.2026). No company name is hard coded here."""

    __tablename__ = "lexoffice_invoice_kind_mapping"
    __table_args__ = (Index("uq_lexoffice_invoice_kind_mapping", "tenant_id", "kind", unique=True),)

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    legal_entity_id: Mapped[uuid.UUID] = _fk("legal_entity.id", ondelete="CASCADE")


class LexofficeContactLink(IdMixin, TimestampMixin, TenantMixin, Base):
    """CRM contact to Lexware contact per config (legal entity). ``contact_id`` is NULL only
    for ``remote_only`` rows. Bank data is never part of any column here."""

    __tablename__ = "lexoffice_contact_link"
    __table_args__ = (
        Index(
            "uq_lexoffice_contact_link_contact",
            "tenant_id",
            "config_id",
            "contact_id",
            unique=True,
            postgresql_where=text("contact_id IS NOT NULL"),
        ),
        Index(
            "uq_lexoffice_contact_link_remote",
            "tenant_id",
            "config_id",
            "lexoffice_contact_id",
            unique=True,
            postgresql_where=text("lexoffice_contact_id IS NOT NULL"),
        ),
        Index("ix_lexoffice_contact_link_status", "tenant_id", "config_id", "sync_status"),
    )

    config_id: Mapped[uuid.UUID] = _fk("lexoffice_tenant_config.id", ondelete="CASCADE")
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", nullable=True, ondelete="CASCADE")
    lexoffice_contact_id: Mapped[str | None] = mapped_column(String(64))
    lexoffice_version: Mapped[int | None] = mapped_column(Integer)
    customer_number: Mapped[int | None] = mapped_column(Integer)
    vendor_number: Mapped[int | None] = mapped_column(Integer)
    sync_status: Mapped[str] = mapped_column(String(24), nullable=False)
    synced_contact_version: Mapped[int | None] = mapped_column(Integer)
    baseline_snapshot: Mapped[dict[str, Any]] = _jsonb("{}")
    remote_display: Mapped[dict[str, Any]] = _jsonb("{}")
    proposed_lexoffice_contact_id: Mapped[str | None] = mapped_column(String(64))
    match_reason: Mapped[str | None] = mapped_column(String(24))
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    candidates: Mapped[list[dict[str, Any]]] = _jsonb("[]")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    conflict: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class LexofficeOutbox(IdMixin, TimestampMixin, TenantMixin, Base):
    """Outbound queue (pattern ``schadenstool_outbox``). ``payload`` holds parameters only,
    never secrets, bank values or a contact snapshot."""

    __tablename__ = "lexoffice_outbox"
    __table_args__ = (
        Index("uq_lexoffice_outbox_key", "tenant_id", "idempotency_key", unique=True),
        Index("ix_lexoffice_outbox_due", "tenant_id", "status", "next_attempt_at"),
        Index("ix_lexoffice_outbox_target", "tenant_id", "target_kind", "target_id"),
    )

    config_id: Mapped[uuid.UUID] = _fk("lexoffice_tenant_config.id", ondelete="CASCADE")
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = _jsonb("{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = _jsonb("{}")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class LexofficeInvoiceDraft(IdMixin, TimestampMixin, TenantMixin, Base):
    """Ad hoc invoice draft created from the CRM (``POST /v1/invoices`` without finalize)."""

    __tablename__ = "lexoffice_invoice_draft"
    __table_args__ = (
        Index("ix_lexoffice_invoice_draft_tenant_created", "tenant_id", "created_at"),
        Index(
            "uq_lexoffice_invoice_draft_remote",
            "tenant_id",
            "lexoffice_invoice_id",
            unique=True,
            postgresql_where=text("lexoffice_invoice_id IS NOT NULL"),
        ),
    )

    config_id: Mapped[uuid.UUID] = _fk("lexoffice_tenant_config.id", ondelete="CASCADE")
    legal_entity_id: Mapped[uuid.UUID | None] = _fk("legal_entity.id", nullable=True)
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", nullable=True, ondelete="SET NULL")
    invoice_kind: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    lexoffice_invoice_id: Mapped[str | None] = mapped_column(String(64))
    lexoffice_version: Mapped[int | None] = mapped_column(Integer)
    deeplink: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class LexofficeInvoiceCopyRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    """Request for a copy of an issued invoice (mail intent or manual entry at the ticket).
    Own table instead of ``AiProposal`` because the proposal may come without an AI run."""

    __tablename__ = "lexoffice_invoice_copy_request"
    __table_args__ = (
        Index("ix_lexoffice_invoice_copy_ticket", "tenant_id", "ticket_id"),
        Index(
            "uq_lexoffice_invoice_copy_message",
            "tenant_id",
            "message_id",
            unique=True,
            postgresql_where=text("message_id IS NOT NULL AND status <> 'rejected'"),
        ),
    )

    ticket_id: Mapped[uuid.UUID] = _fk("ticket.id", ondelete="CASCADE")
    message_id: Mapped[uuid.UUID | None] = _fk("message.id", nullable=True, ondelete="SET NULL")
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    requester_contact_id: Mapped[uuid.UUID | None] = _fk(
        "contact.id", nullable=True, ondelete="SET NULL"
    )
    corrected_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lookup: Mapped[dict[str, Any]] = _jsonb("{}")
    verification: Mapped[dict[str, Any]] = _jsonb("{}")
    recipient_contact_id: Mapped[uuid.UUID | None] = _fk(
        "contact.id", nullable=True, ondelete="SET NULL"
    )
    sender_config_id: Mapped[uuid.UUID | None] = _fk(
        "lexoffice_tenant_config.id", nullable=True, ondelete="SET NULL"
    )
    # pending, found, ambiguous, not_found, draft_only, creditnote_only, fetching,
    # draft_ready, draft_in_lexoffice, failed, rejected
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    document_id: Mapped[uuid.UUID | None] = _fk("document.id", nullable=True, ondelete="SET NULL")
    xml_document_id: Mapped[uuid.UUID | None] = _fk(
        "document.id", nullable=True, ondelete="SET NULL"
    )
    reply_message_id: Mapped[uuid.UUID | None] = _fk(
        "message.id", nullable=True, ondelete="SET NULL"
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LexofficeRecurringPrep(IdMixin, TimestampMixin, TenantMixin, Base):
    """Prepared recurring invoice (Dauerrechnung) for a management fee. The Lexware public API
    offers recurring templates read only (GET /v1/recurring-templates, verified 29.09.2026),
    so the platform prepares contact, amount, interval and text with a checklist; a person
    creates the template in Lexware Office and records its id here."""

    __tablename__ = "lexoffice_recurring_prep"
    __table_args__ = (
        Index("uq_lexoffice_recurring_prep_fee", "tenant_id", "admin_fee_setting_id", unique=True),
    )

    admin_fee_setting_id: Mapped[uuid.UUID] = _fk("admin_fee_setting.id", ondelete="CASCADE")
    property_id: Mapped[uuid.UUID] = _fk("property.id", ondelete="CASCADE")
    config_id: Mapped[uuid.UUID | None] = _fk(
        "lexoffice_tenant_config.id", nullable=True, ondelete="SET NULL"
    )
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", nullable=True, ondelete="SET NULL")
    prepared: Mapped[dict[str, Any]] = _jsonb("{}")
    checklist: Mapped[list[dict[str, Any]]] = _jsonb("[]")
    # open, done, dismissed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    lexoffice_template_id: Mapped[str | None] = mapped_column(String(64))
    done_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
