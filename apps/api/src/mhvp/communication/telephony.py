"""Telefonie-Webhook, anbieterneutral (master prompt 13.5, M23, Lückenliste A70).

``POST /communication/webhooks/telephony`` (or ``.../telephony/{tenant_key}``) is outside the
tenant login by design: the telephone system (TAPI or SIP provider, provider open at the
operator, ``docs/integrations/telefonie.md``) calls it directly. Every delivery is checked like
the Paperless webhook (``mhvp.documents.paperless_webhook``):

* ``X-MHVP-Timestamp``: Unix seconds, at most ``WINDOW_SECONDS`` away from the server clock;
* ``X-MHVP-Signature``: ``sha256=<hex>`` of HMAC-SHA256(secret, ``"<timestamp>." + raw body``)
  with the secret stored per tenant in ``telephony_settings`` (write only, field encrypted);
* ``X-MHVP-Tenant`` (or the path segment): tenant slug or id.

A signature seen before within the window is refused as a replay (409), a body above
``MAX_BODY_BYTES`` with 413. The platform wide rate limit (``mhvp.core.ratelimit``) counts the
deliveries per client IP like every other unauthenticated request.

Events ``call.started``, ``call.ended`` and ``call.missed`` carry the number, the direction,
the duration (ended) and an optional provider reference. The number is normalised to E.164 and
compared with the phone numbers of the tenant's contacts: exactly one hit assigns the contact,
several hits are stored as candidates for a manual choice, no hit stays unknown. Every event is
written to ``call_log`` as a call note on the contact. A missed call, or a call of a contact
with an open ticket, produces a proposal "Rückruf" (``proposal_status = proposed``); a ticket is
only created when a person accepts the proposal (rule 0.1.6, no automatic ticket without a
rule). Conversation content is never accepted or stored (data protection); in lists the number
is masked for users without ``contacts:read``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from mhvp.contacts.models import Contact, ContactPhone
from mhvp.contacts.validation import InvalidValueError, normalise_phone
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.crypto import EncryptedText
from mhvp.core.db.base import Base
from mhvp.core.db.columns import IdMixin, TenantMixin, TimestampMixin
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.core.events import emit
from mhvp.core.numbering import next_number
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.platform.models import Tenant, TenantStatus
from mhvp.tickets.models import Priority, Ticket, TicketEvent, TicketSource, TicketStatus

log = logging.getLogger(__name__)

router = APIRouter(tags=["Telefonie"])
WEBHOOK = "/communication/webhooks/telephony"

WINDOW_SECONDS = 300
MAX_BODY_BYTES = 16 * 1024
SIGNATURE_HEADER = "X-MHVP-Signature"
TIMESTAMP_HEADER = "X-MHVP-Timestamp"
TENANT_HEADER = "X-MHVP-Tenant"
MAX_CANDIDATES = 10
CALLBACK_SLA_HOURS = 24
OPEN_TICKET_STATUSES = (TicketStatus.NEW, TicketStatus.IN_PROGRESS, TicketStatus.WAITING)

READ = require_permission("communication:read")
UPDATE = require_permission("communication:update")
CONTACTS_READ = require_permission("contacts:read")
TICKETS_CREATE = require_permission("tickets:create")
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")


# --- models -------------------------------------------------------------------------------


class CallEvent(StrEnum):
    STARTED = "started"
    ENDED = "ended"
    MISSED = "missed"


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


class ProposalStatus(StrEnum):
    NONE = "none"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class TelephonySettings(IdMixin, TimestampMixin, TenantMixin, Base):
    """Per tenant configuration of the telephony webhook. The secret is write only."""

    __tablename__ = "telephony_settings"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_telephony_settings_tenant"),)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_text("false")
    )
    provider_label: Mapped[str | None] = mapped_column(String(100))
    webhook_secret: Mapped[str | None] = mapped_column(EncryptedText())


class CallLog(IdMixin, TimestampMixin, TenantMixin, Base):
    """Call note on a contact (13.5): one row per delivered event; started and ended of the
    same provider reference are folded into one row. No conversation content."""

    __tablename__ = "call_log"
    __table_args__ = (
        Index("ix_call_log_tenant_started", "tenant_id", "started_at"),
        Index("ix_call_log_contact", "tenant_id", "contact_id"),
        Index(
            "uq_call_log_provider_ref",
            "tenant_id",
            "provider_ref",
            unique=True,
            postgresql_where=sa_text("provider_ref IS NOT NULL"),
        ),
        CheckConstraint("event IN ('started', 'ended', 'missed')", name="ck_call_log_event"),
        CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_call_log_direction"),
        CheckConstraint(
            "match_status IN ('matched', 'ambiguous', 'unknown')", name="ck_call_log_match"
        ),
        CheckConstraint(
            "proposal_status IN ('none', 'proposed', 'accepted', 'dismissed')",
            name="ck_call_log_proposal",
        ),
    )

    event: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    number_normalised: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    provider_ref: Mapped[str | None] = mapped_column(String(200))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contact.id", ondelete="SET NULL")
    )
    candidate_contact_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default=sa_text("'{}'")
    )
    match_status: Mapped[str] = mapped_column(String(16), nullable=False)
    related_ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ticket.id", ondelete="SET NULL")
    )
    proposal_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProposalStatus.NONE.value
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ticket.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)


# --- signature -----------------------------------------------------------------------------


def sign(secret: str, timestamp: int | str, body: bytes) -> str:
    """Signature value the telephone system must send (``docs/integrations/telefonie.md``)."""
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256)
    return f"sha256={digest.hexdigest()}"


def verify(secret: str, timestamp: str | None, signature: str | None, body: bytes) -> bool:
    if not timestamp or not signature or not signature.startswith("sha256="):
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - ts) > WINDOW_SECONDS:
        return False
    return hmac.compare_digest(sign(secret, ts, body), signature)


def _refuse() -> ProblemError:
    return ProblemError(ErrorCodes.WEBHOOK_SIGNATURE)


async def _resolve_tenant(factory: async_sessionmaker[AsyncSession], key: str | None) -> uuid.UUID:
    if not key:
        raise _refuse()
    async with platform_transaction(factory) as session:
        try:
            tenant_id: uuid.UUID | None = uuid.UUID(key)
        except ValueError:
            tenant_id = None
        query = select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE)
        query = (
            query.where(Tenant.id == tenant_id) if tenant_id else query.where(Tenant.slug == key)
        )
        found = await session.scalar(query)
    if found is None:
        raise _refuse()
    return found


# --- number handling ------------------------------------------------------------------------


def normalise_number(value: str) -> tuple[str, bool]:
    """E.164 where the number is valid, otherwise the trimmed raw value (max 64 chars)."""
    raw = " ".join(value.split())[:64]
    try:
        return normalise_phone(raw), True
    except InvalidValueError:
        return raw, False


def mask_number(number: str) -> str:
    """Country code and the last two digits stay visible: ``+49151****89``."""
    digits = [c for c in number if c.isdigit()]
    if len(digits) <= 4:
        return "*" * len(number)
    prefix = number[:5] if number.startswith("+") else number[:3]
    return f"{prefix}{'*' * 4}{''.join(digits[-2:])}"


async def match_contacts(session: AsyncSession, number: str) -> list[uuid.UUID]:
    """Contacts of the tenant (not deleted) with this E.164 number, ordered by name."""
    rows = await session.execute(
        select(ContactPhone.contact_id, Contact.display_name)
        .join(Contact, Contact.id == ContactPhone.contact_id)
        .where(ContactPhone.number == number, Contact.deleted_at.is_(None))
        .order_by(Contact.display_name, Contact.id)
    )
    seen: list[uuid.UUID] = []
    for contact_id, _name in rows.all():
        if contact_id not in seen:
            seen.append(contact_id)
    return seen[:MAX_CANDIDATES]


async def _open_ticket(session: AsyncSession, contact_id: uuid.UUID) -> uuid.UUID | None:
    found: uuid.UUID | None = await session.scalar(
        select(Ticket.id)
        .where(
            Ticket.contact_id == contact_id,
            Ticket.status.in_(list(OPEN_TICKET_STATUSES)),
            Ticket.merged_into_ticket_id.is_(None),
        )
        .order_by(Ticket.created_at.desc())
        .limit(1)
    )
    return found


# --- webhook payload ------------------------------------------------------------------------


class CallEventIn(BaseModel):
    """Provider neutral payload (``docs/integrations/telefonie.md``). Unknown fields are
    refused so that no conversation content can be smuggled in."""

    model_config = ConfigDict(extra="forbid")

    event: str = Field(pattern="^call\\.(started|ended|missed)$")
    number: str = Field(min_length=1, max_length=64)
    direction: CallDirection
    started_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=7 * 24 * 3600)
    provider_ref: str | None = Field(default=None, min_length=1, max_length=200)


async def record_call(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: CallEventIn
) -> tuple[CallLog, bool]:
    """Writes or updates the call note. Returns (row, created)."""
    event = payload.event.removeprefix("call.")
    number, normalised = normalise_number(payload.number)
    started_at = payload.started_at or datetime.now(UTC)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)

    row: CallLog | None = None
    if payload.provider_ref:
        row = await session.scalar(
            select(CallLog).where(CallLog.provider_ref == payload.provider_ref)
        )
    created = row is None
    if row is None:
        candidates = await match_contacts(session, number) if normalised else []
        if len(candidates) == 1:
            status, contact_id = MatchStatus.MATCHED, candidates[0]
        elif candidates:
            status, contact_id = MatchStatus.AMBIGUOUS, None
        else:
            status, contact_id = MatchStatus.UNKNOWN, None
        row = CallLog(
            tenant_id=tenant_id,
            event=event,
            direction=payload.direction.value,
            number=number,
            number_normalised=normalised,
            started_at=started_at,
            provider_ref=payload.provider_ref,
            contact_id=contact_id,
            candidate_contact_ids=candidates if status is MatchStatus.AMBIGUOUS else [],
            match_status=status.value,
            proposal_status=ProposalStatus.NONE.value,
        )
        session.add(row)
    else:
        row.event = event
    if payload.duration_seconds is not None:
        row.duration_seconds = payload.duration_seconds
    if row.contact_id is not None and row.related_ticket_id is None:
        row.related_ticket_id = await _open_ticket(session, row.contact_id)
    # Proposal "Rückruf": missed call, or a call of a contact with an open ticket. Never a
    # ticket by itself (rule 0.1.6); an accepted or dismissed proposal is not reopened.
    if row.proposal_status == ProposalStatus.NONE.value and (
        event == CallEvent.MISSED.value or row.related_ticket_id is not None
    ):
        row.proposal_status = ProposalStatus.PROPOSED.value
    await session.flush()
    await emit(
        session,
        tenant_id=tenant_id,
        type=f"call.{event}",
        entity_type="call_log",
        entity_id=row.id,
        actor_user_id=None,
        payload={
            "direction": row.direction,
            "match_status": row.match_status,
            "contact_id": str(row.contact_id) if row.contact_id else None,
            "proposal": row.proposal_status,
            "created": created,
        },
    )
    return row, created


async def _receive(request: Request, tenant_key: str | None) -> dict[str, Any]:
    resources = request.app.state.resources
    factory: async_sessionmaker[AsyncSession] = resources.session_factory
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise ProblemError(ErrorCodes.WEBHOOK_TOO_LARGE, detail="Webhook-Inhalt zu groß.")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ProblemError(ErrorCodes.WEBHOOK_TOO_LARGE, detail="Webhook-Inhalt zu groß.")
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    signature = request.headers.get(SIGNATURE_HEADER)
    tenant_id = await _resolve_tenant(factory, tenant_key or request.headers.get(TENANT_HEADER))

    async with tenant_transaction(factory, tenant_id) as session:
        settings_row = await session.scalar(select(TelephonySettings))
        secret = settings_row.webhook_secret if settings_row is not None else None
        enabled = bool(settings_row is not None and settings_row.enabled)
        if not enabled or not secret or not verify(secret, timestamp, signature, raw):
            log.warning("telephony webhook: disabled, invalid or missing signature")
            raise _refuse()

    assert signature is not None  # noqa: S101 - verified above
    marker = f"telephony-webhook:{tenant_id}:{hashlib.sha256(signature.encode()).hexdigest()}"
    fresh = await resources.redis.set(marker, "1", nx=True, ex=WINDOW_SECONDS * 2)
    if not fresh:
        raise ProblemError(ErrorCodes.WEBHOOK_REPLAY)

    try:
        payload = CallEventIn.model_validate_json(raw)
    except ValidationError as exc:
        details = exc.errors()
        where = ".".join(str(x) for x in details[0]["loc"]) if details else "body"
        reason = details[0]["msg"] if details else "ungültig"
        raise ProblemError(
            ErrorCodes.VALIDATION, detail=f"Telefonie-Ereignis ungültig ({where}: {reason})."
        ) from None

    async with tenant_transaction(factory, tenant_id) as session:
        row, created = await record_call(session, tenant_id=tenant_id, payload=payload)
        # Review 1.22 Nr. 18: the telephone system learns only that the event was recorded;
        # whether the number belongs to a contact stays inside the CRM (calls list).
        return {"status": "recorded" if created else "updated", "call_id": str(row.id)}


@router.post(WEBHOOK, summary="Telefonie-Webhook (HMAC je Mandant, anbieterneutral)")
async def receive(request: Request) -> dict[str, Any]:
    return await _receive(request, None)


@router.post(WEBHOOK + "/{tenant_key}", summary="Telefonie-Webhook (Mandant im Pfad)")
async def receive_for_tenant(tenant_key: str, request: Request) -> dict[str, Any]:
    return await _receive(request, tenant_key)


# --- settings -------------------------------------------------------------------------------


class TelephonySettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider_label: str | None = Field(default=None, max_length=100)
    # Write only: None keeps the stored secret, an empty string is refused.
    webhook_secret: str | None = Field(default=None, min_length=16, max_length=200)


class TelephonySettingsOut(BaseModel):
    enabled: bool
    provider_label: str | None
    has_webhook_secret: bool
    webhook_path: str


def _settings_out(row: TelephonySettings | None) -> TelephonySettingsOut:
    return TelephonySettingsOut(
        enabled=bool(row is not None and row.enabled),
        provider_label=row.provider_label if row is not None else None,
        has_webhook_secret=bool(row is not None and row.webhook_secret),
        webhook_path=f"/api/v1{WEBHOOK}",
    )


@router.get("/communication/telephony/settings", summary="Telefonie-Einstellungen")
async def get_settings(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> TelephonySettingsOut:
    async with tenant_tx(request, principal) as session:
        return _settings_out(await session.scalar(select(TelephonySettings)))


@router.put("/communication/telephony/settings", summary="Telefonie-Einstellungen speichern")
async def put_settings(
    body: TelephonySettingsIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> TelephonySettingsOut:
    async with tenant_tx(request, principal) as session:
        row = await session.scalar(select(TelephonySettings))
        if row is None:
            row = TelephonySettings(tenant_id=principal.tenant_id, created_by=principal.user_id)
            session.add(row)
        if body.webhook_secret is not None:
            row.webhook_secret = body.webhook_secret
        if body.enabled and not row.webhook_secret:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail="Ohne Geheimnis kann der Webhook nicht aktiv sein."
            )
        row.enabled = body.enabled
        row.provider_label = body.provider_label
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="telephony.settings_updated",
            entity_type="telephony_settings",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"enabled": row.enabled, "secret_changed": body.webhook_secret is not None},
        )
        return _settings_out(row)


# --- call list ------------------------------------------------------------------------------


class CallOut(BaseModel):
    id: uuid.UUID
    event: str
    direction: str
    number: str
    number_masked: bool
    started_at: datetime
    duration_seconds: int | None
    provider_ref: str | None
    contact_id: uuid.UUID | None
    contact_name: str | None
    candidate_contact_ids: list[uuid.UUID]
    candidate_names: list[str]
    match_status: str
    related_ticket_id: uuid.UUID | None
    proposal_status: str
    ticket_id: uuid.UUID | None
    note: str | None
    created_at: datetime


async def _names(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(
        select(Contact.id, Contact.display_name).where(Contact.id.in_(list(ids)))
    )
    return dict(rows.tuples().all())


async def _outs(session: AsyncSession, rows: list[CallLog], *, unmasked: bool) -> list[CallOut]:
    ids: set[uuid.UUID] = set()
    for row in rows:
        if row.contact_id:
            ids.add(row.contact_id)
        ids.update(row.candidate_contact_ids)
    names = await _names(session, ids)
    out: list[CallOut] = []
    for row in rows:
        out.append(
            CallOut(
                id=row.id,
                event=row.event,
                direction=row.direction,
                number=row.number if unmasked else mask_number(row.number),
                number_masked=not unmasked,
                started_at=row.started_at,
                duration_seconds=row.duration_seconds,
                provider_ref=row.provider_ref,
                contact_id=row.contact_id,
                contact_name=names.get(row.contact_id) if row.contact_id else None,
                candidate_contact_ids=list(row.candidate_contact_ids),
                candidate_names=[names.get(c, "") for c in row.candidate_contact_ids if c in names],
                match_status=row.match_status,
                related_ticket_id=row.related_ticket_id,
                proposal_status=row.proposal_status,
                ticket_id=row.ticket_id,
                note=row.note,
                created_at=row.created_at,
            )
        )
    return out


@router.get("/communication/calls", summary="Anrufliste des Mandanten")
async def list_calls(
    request: Request,
    principal: TenantPrincipal = Depends(READ),
    contact_id: uuid.UUID | None = None,
    event: str | None = Query(default=None, pattern="^(started|ended|missed)$"),
    proposal_status: str | None = Query(
        default=None, pattern="^(none|proposed|accepted|dismissed)$"
    ),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CallOut]:
    query = select(CallLog).order_by(CallLog.started_at.desc(), CallLog.id.desc()).limit(limit)
    if contact_id is not None:
        query = query.where(CallLog.contact_id == contact_id)
    if event is not None:
        query = query.where(CallLog.event == event)
    if proposal_status is not None:
        query = query.where(CallLog.proposal_status == proposal_status)
    async with tenant_tx(request, principal) as session:
        rows = list((await session.scalars(query)).all())
        return await _outs(session, rows, unmasked=principal.has("contacts:read"))


@router.get("/contacts/{contact_id}/calls", summary="Anrufliste eines Kontakts")
async def list_contact_calls(
    contact_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_READ),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CallOut]:
    async with tenant_tx(request, principal) as session:
        contact = await session.get(Contact, contact_id)
        if contact is None or contact.deleted_at is not None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        rows = list(
            (
                await session.scalars(
                    select(CallLog)
                    .where(CallLog.contact_id == contact_id)
                    .order_by(CallLog.started_at.desc(), CallLog.id.desc())
                    .limit(limit)
                )
            ).all()
        )
        return await _outs(session, rows, unmasked=True)


async def _call(session: AsyncSession, call_id: uuid.UUID) -> CallLog:
    row = await session.get(CallLog, call_id)
    if row is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


class CallNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=4000)


@router.patch("/communication/calls/{call_id}", summary="Anrufnotiz bearbeiten")
async def patch_call(
    call_id: uuid.UUID,
    body: CallNoteIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> CallOut:
    async with tenant_tx(request, principal) as session:
        row = await _call(session, call_id)
        row.note = body.note
        row.updated_by = principal.user_id
        await session.flush()
        return (await _outs(session, [row], unmasked=principal.has("contacts:read")))[0]


class CallAssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: uuid.UUID


@router.post("/communication/calls/{call_id}/assign", summary="Anruf einem Kontakt zuordnen")
async def assign_call(
    call_id: uuid.UUID,
    body: CallAssignIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> CallOut:
    async with tenant_tx(request, principal) as session:
        row = await _call(session, call_id)
        contact = await session.get(Contact, body.contact_id)
        if contact is None or contact.deleted_at is not None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND, detail="Kontakt nicht gefunden.")
        row.contact_id = contact.id
        row.candidate_contact_ids = []
        row.match_status = MatchStatus.MATCHED.value
        row.updated_by = principal.user_id
        if row.related_ticket_id is None:
            row.related_ticket_id = await _open_ticket(session, contact.id)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="call.assigned",
            entity_type="call_log",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"contact_id": str(contact.id)},
        )
        return (await _outs(session, [row], unmasked=principal.has("contacts:read")))[0]


# --- proposal "Rückruf" ---------------------------------------------------------------------


class ProposalAcceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    priority: Priority = Priority.NORMAL


def _proposed(row: CallLog) -> None:
    if row.proposal_status != ProposalStatus.PROPOSED.value:
        raise ProblemError(ErrorCodes.CONFLICT, detail="Kein offener Rückruf-Vorschlag.")


@router.post(
    "/communication/calls/{call_id}/proposal/accept",
    status_code=201,
    summary="Rückruf-Vorschlag annehmen (Ticket anlegen)",
)
async def accept_proposal(
    call_id: uuid.UUID,
    body: ProposalAcceptIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKETS_CREATE),
) -> dict[str, Any]:
    from mhvp.sla.service import start_clock

    async with tenant_tx(request, principal) as session:
        row = await _call(session, call_id)
        _proposed(row)
        contact = await session.get(Contact, row.contact_id) if row.contact_id else None
        who = contact.display_name if contact else mask_number(row.number)
        ticket = Ticket(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            number=await next_number(session, principal.tenant_id, "ticket"),
            title=body.title or f"Rückruf {who}",
            priority=body.priority,
            source=TicketSource.PHONE,
            contact_id=row.contact_id,
            initiator_contact_id=row.contact_id,
            parent_ticket_id=row.related_ticket_id,
            internal_description=(
                f"Anruf {row.started_at.astimezone(UTC).strftime('%d.%m.%Y %H:%M')} UTC, "
                f"{'eingehend' if row.direction == 'inbound' else 'ausgehend'}, "
                f"{'verpasst' if row.event == 'missed' else 'geführt'}."
            ),
            sla_due_at=datetime.now(UTC) + timedelta(hours=CALLBACK_SLA_HOURS),
        )
        session.add(ticket)
        await session.flush()
        await start_clock(session, principal.tenant_id, ticket.id, ticket.priority)
        session.add(
            TicketEvent(
                tenant_id=principal.tenant_id,
                ticket_id=ticket.id,
                kind="created",
                user_id=principal.user_id,
                data={"routing": "call_proposal", "call_id": str(row.id)},
            )
        )
        row.ticket_id = ticket.id
        row.proposal_status = ProposalStatus.ACCEPTED.value
        row.updated_by = principal.user_id
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="ticket.created",
            entity_type="ticket",
            entity_id=ticket.id,
            actor_user_id=principal.user_id,
            payload={
                "number": ticket.number,
                "source": ticket.source.value,
                "call_id": str(row.id),
            },
        )
        await session.flush()
        return {
            "ticket_id": str(ticket.id),
            "number": ticket.number,
            "title": ticket.title,
            "call_id": str(row.id),
        }


@router.post(
    "/communication/calls/{call_id}/proposal/dismiss", summary="Rückruf-Vorschlag verwerfen"
)
async def dismiss_proposal(
    call_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(UPDATE)
) -> CallOut:
    async with tenant_tx(request, principal) as session:
        row = await _call(session, call_id)
        _proposed(row)
        row.proposal_status = ProposalStatus.DISMISSED.value
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="call.proposal_dismissed",
            entity_type="call_log",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={},
        )
        return (await _outs(session, [row], unmasked=principal.has("contacts:read")))[0]
