"""Claims adjuster ("Schadenstool", MDV/midive) integration tables (rule INT-SDT-01).

All tables are tenant scoped (RLS, ADR 0002, migration 0222):

- ``SchadenstoolTenantConfig``: connection (base URL, integration token, optional HMAC and
  webhook secrets, all encrypted with the master key), feature flag ``enabled`` (default off),
  AVV confirmation that must be recorded before enabling (rule 0.1.13), random webhook path id.
- ``SchadenstoolTicketLink``: one row per remote ticket (``mdvId``) or per local ticket queued
  for creation there. ``ticket_id`` is null while a remote ticket waits in the takeover queue.
- ``SchadenstoolItemLink``: comments and attachments exchanged, local id and remote id, so an
  item is sent once and an item coming back via webhook is not imported again (no echo).
- ``SchadenstoolOutbox``: outbound queue; a user action only writes a row, the job sends it.
- ``SchadenstoolEvent``: received webhook events (dedup by ``eventId``) and their processing.

Deviation note (rule 0.1.11): ``import_external_key`` (migration 0204) maps import keys only;
the exchange needs sync state per remote ticket, hence a dedicated link table.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


class LinkStatus(StrEnum):
    PENDING_CREATE = "pending_create"  # local ticket queued for POST /tickets
    LINKED = "linked"
    PENDING_TAKEOVER = "pending_takeover"  # remote ticket without local ticket, needs a member
    DISMISSED = "dismissed"
    ERROR = "error"


class ItemKind(StrEnum):
    COMMENT = "comment"
    ATTACHMENT = "attachment"


class Direction(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class OutboxKind(StrEnum):
    CREATE_TICKET = "create_ticket"
    COMMENT = "comment"
    ATTACHMENT = "attachment"
    STATUS = "status"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class EventStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    IGNORED = "ignored"
    FAILED = "failed"


def _uuid_fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


class SchadenstoolTenantConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "schadenstool_tenant_config"
    __table_args__ = (Index("uq_schadenstool_tenant_config_tenant", "tenant_id", unique=True),)

    base_url: Mapped[str | None] = mapped_column(String(300))
    token: Mapped[str | None] = mapped_column(EncryptedText())
    token_last4: Mapped[str | None] = mapped_column(String(4))
    hmac_secret: Mapped[str | None] = mapped_column(EncryptedText())
    webhook_secret: Mapped[str | None] = mapped_column(EncryptedText())
    webhook_path_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    avv_confirmed_on: Mapped[date | None] = mapped_column(Date)
    avv_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    avv_note: Mapped[str | None] = mapped_column(String(500))
    token_invalid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_test_message: Mapped[str | None] = mapped_column(Text)
    pull_watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_pull_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_pull_message: Mapped[str | None] = mapped_column(Text)


class SchadenstoolTicketLink(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "schadenstool_ticket_link"
    __table_args__ = (
        Index(
            "uq_schadenstool_ticket_link_remote",
            "tenant_id",
            "remote_id",
            unique=True,
            postgresql_where=text("remote_id IS NOT NULL"),
        ),
        Index(
            "uq_schadenstool_ticket_link_ticket",
            "tenant_id",
            "ticket_id",
            unique=True,
            postgresql_where=text("ticket_id IS NOT NULL"),
        ),
    )

    ticket_id: Mapped[uuid.UUID | None] = _uuid_fk("ticket.id", ondelete="CASCADE")
    remote_id: Mapped[str | None] = mapped_column(String(64))
    remote_external_id: Mapped[str | None] = mapped_column(String(64))
    object_external_id: Mapped[str | None] = mapped_column(String(64))
    remote_title: Mapped[str | None] = mapped_column(String(300))
    remote_status: Mapped[str | None] = mapped_column(String(64))
    remote_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(24), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    proposed_property_id: Mapped[uuid.UUID | None] = _uuid_fk("property.id", ondelete="SET NULL")
    proposed_ticket_id: Mapped[uuid.UUID | None] = _uuid_fk("ticket.id", ondelete="SET NULL")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SchadenstoolItemLink(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "schadenstool_item_link"
    __table_args__ = (
        Index("uq_schadenstool_item_link_local", "tenant_id", "kind", "local_id", unique=True),
        Index(
            "uq_schadenstool_item_link_remote",
            "tenant_id",
            "kind",
            "remote_id",
            unique=True,
            postgresql_where=text("remote_id IS NOT NULL"),
        ),
    )

    link_id: Mapped[uuid.UUID] = _uuid_fk(
        "schadenstool_ticket_link.id", nullable=False, ondelete="CASCADE"
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    local_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    remote_id: Mapped[str | None] = mapped_column(String(64))
    author_name: Mapped[str | None] = mapped_column(String(200))


class SchadenstoolOutbox(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "schadenstool_outbox"
    __table_args__ = (
        Index("uq_schadenstool_outbox_key", "tenant_id", "idempotency_key", unique=True),
        Index("ix_schadenstool_outbox_due", "tenant_id", "status", "next_attempt_at"),
    )

    link_id: Mapped[uuid.UUID] = _uuid_fk(
        "schadenstool_ticket_link.id", nullable=False, ondelete="CASCADE"
    )
    item_link_id: Mapped[uuid.UUID | None] = _uuid_fk(
        "schadenstool_item_link.id", ondelete="CASCADE"
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class SchadenstoolEvent(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "schadenstool_event"
    __table_args__ = (
        Index("uq_schadenstool_event_event_id", "tenant_id", "event_id", unique=True),
        Index("ix_schadenstool_event_status", "tenant_id", "status"),
    )

    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
