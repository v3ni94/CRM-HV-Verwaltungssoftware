"""EBICS connector scaffold: tenant switch, subscribers, keys and order log (M11-01, AE23).

Rule M11-11 (docs/rules/M11-11-ebics-connector.md), migration 0379. Private keys of the
subscriber are stored only as ``EncryptedText`` (AES-256-GCM with the tenant key derived from
``MHVP_MASTER_KEY``, section 3.5, S16-03-02) and are wiped when a key is retired; public keys,
the transport supplied letter hash and an internal SHA-256 of the public key stay for the audit
trail. A rotation never overwrites a key row: the old row gets ``retired_at`` and the new row is
inserted (S16-03-02 "Rotation automatisch erfasst"). Nothing here submits a payment (G2).
"""

import uuid
from datetime import date, datetime
from enum import StrEnum
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
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin


class EbicsSignatureKeyMode(StrEnum):
    """Where the private signature key (A005/A006) lives. ``external`` (default): with the
    signing person (chip card or removable medium, DK security recommendations 3.1.2), the
    platform keeps only the public key. ``server``: generated and stored encrypted by the
    platform; a variant pending the operator decision S16-03-02."""

    EXTERNAL = "external"
    SERVER = "server"


class EbicsSubscriberStatus(StrEnum):
    CREATED = "created"
    KEYS_READY = "keys_ready"
    INITIALISED = "initialised"
    ACTIVATED = "activated"
    BANK_KEYS_RECEIVED = "bank_keys_received"
    READY = "ready"
    SUSPENDED = "suspended"


class EbicsTenantSetting(IdMixin, TimestampMixin, TenantMixin, Base):
    """One row per tenant; no row means the defaults (switch off, signature key external)."""

    __tablename__ = "ebics_tenant_setting"
    __table_args__ = (
        UniqueConstraint("tenant_id"),
        CheckConstraint("signature_key_mode IN ('external', 'server')", name="signature_key_mode"),
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    signature_key_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="external", server_default="external"
    )


class EbicsSubscriber(IdMixin, TimestampMixin, TenantMixin, Base):
    """One EBICS subscriber (Teilnehmer) of one customer (Partner) at one bank host. The bank
    contract and access letter deliver host id, partner id, user id and URL; the platform
    never derives them. One subscriber may serve several accounts; statements are matched to
    internal bank accounts by IBAN on import."""

    __tablename__ = "ebics_subscriber"
    __table_args__ = (
        UniqueConstraint("tenant_id", "host_id", "partner_id", "ebics_user_id"),
        CheckConstraint("ebics_version IN ('2.5', '3.0')", name="ebics_version"),
        CheckConstraint("signature_version IN ('A005', 'A006')", name="signature_version"),
        CheckConstraint("key_bits IN (2048, 3072, 4096)", name="key_bits"),
        CheckConstraint("signature_key_mode IN ('external', 'server')", name="signature_key_mode"),
        CheckConstraint(
            "status IN ('created', 'keys_ready', 'initialised', 'activated', "
            "'bank_keys_received', 'ready', 'suspended')",
            name="status",
        ),
    )

    label: Mapped[str] = mapped_column(String(200), nullable=False)
    host_id: Mapped[str] = mapped_column(String(64), nullable=False)
    partner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ebics_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    ebics_version: Mapped[str] = mapped_column(String(8), nullable=False)
    signature_version: Mapped[str] = mapped_column(String(4), nullable=False)
    key_bits: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4096, server_default="4096"
    )
    signature_key_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="external", server_default="external"
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="created", server_default="created"
    )
    ini_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ini_sent_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ini_external: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    ini_note: Mapped[str | None] = mapped_column(Text)
    hia_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hia_sent_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    activated_on: Mapped[date | None] = mapped_column(Date)
    activation_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    activation_note: Mapped[str | None] = mapped_column(Text)
    bank_keys_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bank_keys_fetched_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    bank_keys_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bank_keys_verified_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    suspend_reason: Mapped[str | None] = mapped_column(Text)
    last_download_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EbicsKey(IdMixin, TimestampMixin, TenantMixin, Base):
    """A public key of the subscriber or the bank, with the encrypted private key for keys the
    platform generated. At most one active key per subscriber, owner and usage."""

    __tablename__ = "ebics_key"
    __table_args__ = (
        CheckConstraint("owner IN ('subscriber', 'bank')", name="owner"),
        CheckConstraint("usage IN ('signature', 'authentication', 'encryption')", name="usage"),
        CheckConstraint("source IN ('generated', 'uploaded', 'bank')", name="source"),
        Index(
            "uq_ebics_key_active",
            "tenant_id",
            "subscriber_id",
            "owner",
            "usage",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
        ),
    )

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ebics_subscriber.id"), nullable=False
    )
    owner: Mapped[str] = mapped_column(String(10), nullable=False)
    usage: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[str] = mapped_column(String(8), nullable=False)
    key_bits: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    public_key_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    private_key: Mapped[str | None] = mapped_column(EncryptedText())
    letter_hash: Mapped[str | None] = mapped_column(String(128))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    retire_reason: Mapped[str | None] = mapped_column(String(200))


class EbicsOrder(IdMixin, TimestampMixin, TenantMixin, Base):
    """Log of every EBICS order the platform attempted (INI, HIA, HPB, C53), append only."""

    __tablename__ = "ebics_order"
    __table_args__ = (
        CheckConstraint("order_type IN ('INI', 'HIA', 'HPB', 'C53')", name="order_type"),
        CheckConstraint("status IN ('done', 'failed')", name="status"),
        Index("ix_ebics_order_subscriber", "tenant_id", "subscriber_id", "created_at"),
    )

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ebics_subscriber.id"), nullable=False
    )
    order_type: Mapped[str] = mapped_column(String(8), nullable=False)
    btf: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    transport: Mapped[str | None] = mapped_column(String(40))
    transport_ref: Mapped[str | None] = mapped_column(String(100))
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error_code: Mapped[str | None] = mapped_column(String(20))
    error_detail: Mapped[str | None] = mapped_column(Text)
