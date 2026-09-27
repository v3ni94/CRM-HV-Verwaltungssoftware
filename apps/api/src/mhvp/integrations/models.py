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
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
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


class LexofficeRunStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"  # some items failed, see errors
    FAILED = "failed"


class LexofficeExportKind(StrEnum):
    INVOICE = "invoice"
    CONTACT = "contact"


def _fk(target: str, *, nullable: bool = False) -> Any:
    return mapped_column(UUID(as_uuid=True), ForeignKey(target), nullable=nullable)


class LexofficeTenantConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "lexoffice_tenant_config"
    __table_args__ = (Index("uq_lexoffice_tenant_config_tenant", "tenant_id", unique=True),)

    api_key: Mapped[str | None] = mapped_column(EncryptedText())
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
