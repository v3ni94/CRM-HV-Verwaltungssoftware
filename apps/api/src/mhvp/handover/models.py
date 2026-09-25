"""Handover protocols (M30): digital Übergabeprotokoll for rental, sale and general handovers.

A protocol is a snapshot: address, unit and participant names are copied when the protocol is
created or a link is chosen and stay editable afterwards. Files (photos, attachments,
signatures, the final PDF) are documents of M6 linked to the protocol and its sub records;
this module never stores binary data. No field is mandatory (docs/plans/M30-uebergabeprotokoll.md).
"""

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, Time
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin

MONEY = Numeric(14, 2)

KINDS = ("rental", "sale", "general")
STATUSES = (
    "draft",
    "in_progress",
    "signature_pending",
    "completed",
    "sent",
    "archived",
    "cancelled",
)
LOCKED_STATUSES = frozenset({"completed", "sent", "archived", "cancelled"})
STEPS = (
    "object",
    "participants",
    "deposit",
    "internal",
    "meters",
    "rooms",
    "keys",
    "items",
    "notes",
    "attachments",
    "summary",
    "signatures",
)


def _fk(target: str, *, nullable: bool = True, ondelete: str | None = None) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable
    )


def _protocol_fk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("handover_protocol.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class HandoverProtocol(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "handover_protocol"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "number", "version", name="uq_handover_number_version"),
        Index("ix_handover_protocol_tenant_status", "tenant_id", "status"),
    )

    number: Mapped[str] = mapped_column(String(24), nullable=False)  # UP-JJJJMMTT-NNN
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_id: Mapped[uuid.UUID | None] = _fk("handover_protocol.id")
    change_reason: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="rental")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    current_step: Mapped[str] = mapped_column(String(20), nullable=False, default="object")

    # Links into the master data; the address below is a snapshot and stays editable.
    property_id: Mapped[uuid.UUID | None] = _fk("property.id", ondelete="SET NULL")
    unit_id: Mapped[uuid.UUID | None] = _fk("unit.id", ondelete="SET NULL")
    contract_id: Mapped[uuid.UUID | None] = _fk("contract.id", ondelete="SET NULL")
    listing_id: Mapped[uuid.UUID | None] = _fk("listing.id", ondelete="SET NULL")

    street: Mapped[str | None] = mapped_column(String(200))
    house_number: Mapped[str | None] = mapped_column(String(20))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    object_label: Mapped[str | None] = mapped_column(String(200))
    building: Mapped[str | None] = mapped_column(String(100))
    floor: Mapped[str | None] = mapped_column(String(20))
    unit_number: Mapped[str | None] = mapped_column(String(50))
    unit_label: Mapped[str | None] = mapped_column(String(100))
    unit_position: Mapped[str | None] = mapped_column(String(100))
    # Manual object (not in the managed portfolio, property_id/unit_id stay null): external
    # object number and the landlord/owner name, free text, editable, part of the PDF.
    external_object_number: Mapped[str | None] = mapped_column(String(100))
    owner_name: Mapped[str | None] = mapped_column(String(200))

    handover_date: Mapped[date | None] = mapped_column(Date)
    handover_start: Mapped[time | None] = mapped_column(Time)
    handover_end: Mapped[time | None] = mapped_column(Time)
    hide_time_information: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    handover_location: Mapped[str | None] = mapped_column(String(200))

    ticket_number: Mapped[str | None] = mapped_column(String(50))
    reference_number: Mapped[str | None] = mapped_column(String(100))
    management_number: Mapped[str | None] = mapped_column(String(100))
    rental_contract_number: Mapped[str | None] = mapped_column(String(100))
    # Internal: never part of the external PDF or a portal view.
    internal_contact: Mapped[str | None] = mapped_column(String(200))
    internal_note: Mapped[str | None] = mapped_column(Text)
    general_note: Mapped[str | None] = mapped_column(Text)

    # Deposit and refund account (entered only, no receivable, no payment: G1/G2 untouched).
    deposit_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    deposit_account_holder: Mapped[str | None] = mapped_column(String(200))
    deposit_iban: Mapped[str | None] = mapped_column(String(34))
    deposit_bic: Mapped[str | None] = mapped_column(String(11))
    deposit_bank_name: Mapped[str | None] = mapped_column(String(200))
    deposit_note: Mapped[str | None] = mapped_column(Text)
    deposit_iban_verified: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    deposit_separate_statement: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa_text("false")
    )

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_document_id: Mapped[uuid.UUID | None] = _fk("document.id", ondelete="SET NULL")
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    # Data takeover from U-Protokoll (M30 stage 4): "uprotokoll:<protocols.id>", unique per
    # tenant, makes the import idempotent (a re-run of the same dump changes nothing).
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)


class HandoverParticipant(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "handover_participant"

    protocol_id: Mapped[uuid.UUID] = _protocol_fk()
    contact_id: Mapped[uuid.UUID | None] = _fk("contact.id", ondelete="SET NULL")
    # moving_out, moving_in, seller, buyer, handing_over, taking_over, management, broker,
    # caretaker, proxy, witness, relative, expert, craftsman, other
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    salutation: Mapped[str | None] = mapped_column(String(50))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    company: Mapped[str | None] = mapped_column(String(200))
    street: Mapped[str | None] = mapped_column(String(200))
    house_number: Mapped[str | None] = mapped_column(String(20))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)


class HandoverMeter(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "handover_meter"

    protocol_id: Mapped[uuid.UUID] = _protocol_fk()
    meter_id: Mapped[uuid.UUID | None] = _fk("meter.id", ondelete="SET NULL")
    meter_type: Mapped[str | None] = mapped_column(String(63))  # electricity, gas, ...
    custom_type: Mapped[str | None] = mapped_column(String(100))
    number: Mapped[str | None] = mapped_column(String(100))
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(20))
    location: Mapped[str | None] = mapped_column(String(200))
    read_on: Mapped[date | None] = mapped_column(Date)
    read_at: Mapped[time | None] = mapped_column(Time)
    comment: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)


class HandoverRoom(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "handover_room"

    protocol_id: Mapped[uuid.UUID] = _protocol_fk()
    room_type: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(200))
    # ok, defective, not_checked, not_accessible, not_included
    condition: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)


class HandoverDefect(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "handover_defect"

    protocol_id: Mapped[uuid.UUID] = _protocol_fk()
    room_id: Mapped[uuid.UUID | None] = _fk("handover_room.id", ondelete="SET NULL")
    category: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(200))
    priority: Mapped[str | None] = mapped_column(String(10))  # info, low, medium, high, urgent
    responsibility: Mapped[str | None] = mapped_column(String(100))
    # pre_existing, new, acknowledged, rejected, unclear
    defect_status: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)


class HandoverKey(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "handover_key"

    protocol_id: Mapped[uuid.UUID] = _protocol_fk()
    key_type: Mapped[str | None] = mapped_column(String(100))
    custom_name: Mapped[str | None] = mapped_column(String(200))
    quantity: Mapped[int | None] = mapped_column(Integer)
    key_number: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(
        String(20)
    )  # handed_over, not_handed_over, to_follow
    comment: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)


class HandoverItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "handover_item"

    protocol_id: Mapped[uuid.UUID] = _protocol_fk()
    item_type: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(200))
    quantity: Mapped[int | None] = mapped_column(Integer)
    condition: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)


class HandoverNote(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "handover_note"

    protocol_id: Mapped[uuid.UUID] = _protocol_fk()
    # agreement, hint, defect, open_task, follow_up, payment, other
    category: Mapped[str | None] = mapped_column(String(20))
    text: Mapped[str | None] = mapped_column(Text)
    responsible_party: Mapped[str | None] = mapped_column(String(200))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(50))
    is_internal: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)


class HandoverSignature(IdMixin, TimestampMixin, TenantMixin, Base):
    """Signature image as document (PNG), hash and time recorded at capture (evidence)."""

    __tablename__ = "handover_signature"

    protocol_id: Mapped[uuid.UUID] = _protocol_fk()
    participant_id: Mapped[uuid.UUID | None] = _fk("handover_participant.id", ondelete="SET NULL")
    signer_name: Mapped[str | None] = mapped_column(String(200))
    signer_role: Mapped[str | None] = mapped_column(String(20))
    document_id: Mapped[uuid.UUID] = _fk("document.id", nullable=False, ondelete="RESTRICT")
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signed_location: Mapped[str | None] = mapped_column(String(200))
    comment: Mapped[str | None] = mapped_column(String(255))
    import_source: Mapped[str | None] = mapped_column(String(100), index=True)
