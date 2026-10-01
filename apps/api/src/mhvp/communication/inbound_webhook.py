"""Inbound webhook for classified mails of the legacy mail program (M20-04, AE38).

``POST /api/v1/mail/inbound/sources/{source_id}/classified-mails`` takes one mail that the
legacy program ("Mail optimierung", docs/integrations/mail-optimierung.md) has already
classified. The delivery books nothing, sends nothing and deletes nothing: it stores the mail
like any other inbound mail (``mhvp.communication.services.ingest_parsed``: contact and object
assignment, thread by ``In-Reply-To`` and ``References``, ticket kennung ``TNR#``, ticket
according to the source switch ``auto_ticket``, domain event ``message.received`` for the
automation rules). The classification of the sender is kept as a proposal in
``classification.external`` and never overrides the platform's own classification.

Checks in this order (contract: docs/integrations/inbound-mail-webhook.md):

1. API key bound to the tenant with the right ``mail_inbound:ingest`` (401 without a valid key,
   403 without the right or with a user token instead of a key).
2. Size limit 1 MiB, by ``Content-Length`` and by the bytes actually read (413).
3. Source of the key's tenant (404, also for the source of another tenant, row level security).
4. HMAC ``X-MHVP-Signature: t=<unix>,v1=<hex>`` over ``"<t>." + raw body`` with the secret of the
   source (``mhvp.core.webhooks.sign``, constant time comparison), timestamp tolerance five
   minutes against replays of captured requests (401).
5. Source switched on (409).
6. Body is a JSON object that fits the schema (422).
7. Idempotency by ``event_id`` (unique per source, claim by ``INSERT .. ON CONFLICT DO NOTHING``
   in the same transaction as the mail): the same content again answers 200 with the stored
   result, another content under the same ``event_id`` answers 409.
"""

import hashlib
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from mhvp.communication.models import InboundMailEvent, InboundMailSource, Mailbox
from mhvp.core import webhooks
from mhvp.core.auth import tokens
from mhvp.core.auth.permissions import MAIL_INBOUND_INGEST
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.ids import uuid7
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, FieldError, ProblemError
from mhvp.core.text import clean_json, strip_nul

log = logging.getLogger(__name__)
router = APIRouter(prefix="/mail/inbound", tags=["Postfach Eingang"])

INGEST = require_permission(MAIL_INBOUND_INGEST)
SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_UPDATE = require_permission("tenant_settings:update")

SIGNATURE_HEADER = webhooks.SIGNATURE_HEADER
# Same window as the outgoing webhooks (docs/integrations/webhooks.md: five minutes).
TOLERANCE_SECONDS = 300
MAX_BODY_BYTES = 1024 * 1024
MAX_HEADER_LENGTH = 200
SECRET_BYTES = 32
_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+$")


# --- signature and hash ---------------------------------------------------------------------


def sign_delivery(secret: str, raw: bytes, *, timestamp: int | None = None) -> str:
    """Header value the sender must put into ``X-MHVP-Signature`` (same function as the
    outgoing webhooks, ``mhvp.core.webhooks.sign``)."""
    return webhooks.sign(secret, raw, int(time.time()) if timestamp is None else timestamp)


def verify_signature(
    secret: str, raw: bytes, header: str | None, *, now: int | None = None
) -> bool:
    """Constant time check of ``t=<unix>,v1=<hex>`` with a tolerance of ``TOLERANCE_SECONDS``
    in both directions. Missing, oversized, malformed, non ASCII or stale headers are
    rejected without an exception."""
    if not header or len(header) > MAX_HEADER_LENGTH:
        return False
    try:
        return webhooks.verify(
            secret,
            raw,
            header,
            now=int(time.time()) if now is None else now,
            tolerance=TOLERANCE_SECONDS,
        )
    except (TypeError, ValueError):  # non ASCII header text, absurd timestamp
        return False


def canonical_hash(document: Any) -> str:
    """SHA-256 over the canonical JSON (sorted keys, no whitespace): a retry that only
    differs in key order or whitespace is the same delivery."""
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


# --- schemas --------------------------------------------------------------------------------


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _address(value: str) -> str:
    cleaned = (strip_nul(value) or "").strip().lower()
    if not _ADDRESS.match(cleaned) or len(cleaned) > 320:
        raise ValueError("keine gültige E-Mail-Adresse")
    return cleaned


class InboundMailContent(_In):
    """The mail itself, as the legacy program read it. Header values are taken over as they
    are; the platform recomputes threading, assignment and its own classification."""

    message_id: str | None = Field(default=None, max_length=998)
    in_reply_to: str | None = Field(default=None, max_length=998)
    references: str | None = Field(default=None, max_length=20000)
    from_address: str = Field(max_length=320)
    reply_to: str | None = Field(default=None, max_length=320)
    to: list[str] = Field(default_factory=list, max_length=100)
    cc: list[str] = Field(default_factory=list, max_length=100)
    subject: str | None = Field(default=None, max_length=998)
    body_text: str | None = Field(default=None, max_length=100000)
    body_html: str | None = Field(default=None, max_length=400000)
    received_at: AwareDatetime | None = None
    auto_submitted: bool = False
    attachment_count: int | None = Field(default=None, ge=0, le=1000)

    @field_validator("from_address")
    @classmethod
    def _from(cls, value: str) -> str:
        return _address(value)

    @field_validator("reply_to")
    @classmethod
    def _reply_to(cls, value: str | None) -> str | None:
        return None if value is None or not value.strip() else _address(value)

    @field_validator("to", "cc")
    @classmethod
    def _recipients(cls, value: list[str]) -> list[str]:
        return [_address(item) for item in value]


class InboundMailClassification(_In):
    """Classification of the legacy program: a proposal, never a decision. It is stored under
    ``classification.external`` of the message and shown beside the platform's own result."""

    category: str | None = Field(default=None, max_length=100)
    process: str | None = Field(default=None, max_length=100)
    urgency: Literal["low", "normal", "urgent"] | None = None
    summary: str | None = Field(default=None, max_length=2000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    labels: list[str] = Field(default_factory=list, max_length=20)
    ticket_number: int | None = Field(default=None, ge=1, le=2_147_483_647)

    @field_validator("labels")
    @classmethod
    def _labels(cls, value: list[str]) -> list[str]:
        if any(len(item) > 64 for item in value):
            raise ValueError("Ein Etikett ist länger als 64 Zeichen.")
        return value


class InboundMailEventIn(_In):
    event_id: str = Field(min_length=1, max_length=200, pattern=r"^[\x21-\x7e]+$")
    source_ref: str | None = Field(default=None, max_length=200)
    classified_at: AwareDatetime | None = None
    mail: InboundMailContent
    classification: InboundMailClassification = Field(default_factory=InboundMailClassification)


class InboundMailReceiptOut(BaseModel):
    event_id: str
    replayed: bool
    message_created: bool
    message_id: uuid.UUID | None
    ticket_id: uuid.UUID | None


def _source_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = (strip_nul(value) or "").strip()
    if not cleaned:
        raise ValueError("Der Name darf nicht leer sein.")
    return cleaned


class InboundMailSourceCreate(_In):
    name: str = Field(min_length=1, max_length=200)
    mailbox_id: uuid.UUID | None = None
    auto_ticket: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return str(_source_name(value))


class InboundMailSourceUpdate(_In):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None
    mailbox_id: uuid.UUID | None = None
    auto_ticket: bool | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return _source_name(value)


class InboundMailSourceOut(BaseModel):
    id: uuid.UUID
    name: str
    active: bool
    mailbox_id: uuid.UUID | None
    auto_ticket: bool
    last_received_at: datetime | None
    secret_rotated_at: datetime | None
    created_at: datetime
    delivery_path: str


class InboundMailSourceCreated(InboundMailSourceOut):
    """Shown once: the secret is stored encrypted and never returned again."""

    secret: str


class InboundMailEventOut(BaseModel):
    id: uuid.UUID
    event_id: str
    message_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    message_created: bool
    replay_count: int
    last_replayed_at: datetime | None
    created_at: datetime


# --- helpers --------------------------------------------------------------------------------


def _not_found() -> ProblemError:
    return ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)


def _delivery_path(source_id: uuid.UUID) -> str:
    return f"/api/v1/mail/inbound/sources/{source_id}/classified-mails"


def _source_out(row: InboundMailSource) -> InboundMailSourceOut:
    return InboundMailSourceOut(
        id=row.id,
        name=row.name,
        active=row.active,
        mailbox_id=row.mailbox_id,
        auto_ticket=row.auto_ticket,
        last_received_at=row.last_received_at,
        secret_rotated_at=row.secret_rotated_at,
        created_at=row.created_at,
        delivery_path=_delivery_path(row.id),
    )


def _event_out(row: InboundMailEvent) -> InboundMailEventOut:
    return InboundMailEventOut(
        id=row.id,
        event_id=row.event_id,
        message_id=row.message_id,
        ticket_id=row.ticket_id,
        message_created=row.message_created,
        replay_count=row.replay_count,
        last_replayed_at=row.last_replayed_at,
        created_at=row.created_at,
    )


async def _read_limited(request: Request) -> bytes:
    """Raw body with a hard cap: refused by ``Content-Length`` before reading and by the bytes
    actually received (chunked bodies carry no length)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise ProblemError(ErrorCodes.WEBHOOK_TOO_LARGE, detail="Webhook-Inhalt zu groß.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise ProblemError(ErrorCodes.WEBHOOK_TOO_LARGE, detail="Webhook-Inhalt zu groß.")
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_document(raw: bytes) -> tuple[dict[str, Any], InboundMailEventIn]:
    try:
        document = json.loads(raw)
    except (ValueError, RecursionError):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Inhalt ist kein JSON.") from None
    if not isinstance(document, dict):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Der Inhalt ist kein JSON-Objekt.")
    try:
        return document, InboundMailEventIn.model_validate(document)
    except ValidationError as exc:
        errors = [
            FieldError(
                location=["body", *[str(part) for part in item["loc"]]],
                field=".".join(str(part) for part in item["loc"]),
                code=str(item["type"]),
                message=str(item["msg"]),
            )
            for item in exc.errors()[:20]
        ]
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Das Mailereignis ist ungültig.", errors=errors
        ) from None


def to_parsed(payload: InboundMailEventIn) -> dict[str, Any]:
    """Shape that ``ingest_parsed`` expects (see ``mhvp.communication.mail.parse``). The
    recipient list holds To and Cc together like the parser of an .eml does."""
    mail = payload.mail
    recipients = list(dict.fromkeys([*mail.to, *mail.cc]))

    def text(value: str | None, limit: int) -> str | None:
        return (strip_nul(value) or "")[:limit] or None

    return {
        "from": mail.from_address,
        "reply_to": mail.reply_to,
        "to": recipients,
        "cc": list(mail.cc),
        "subject": text(mail.subject, 998),
        "body": (strip_nul((mail.body_text or "").strip()) or "")[:100000],
        "body_html": text(mail.body_html, 400000),
        "message_id": text(mail.message_id, 998),
        "in_reply_to": text(mail.in_reply_to, 998),
        "references": text(" ".join((mail.references or "").split()), 20000),
        "received_at": mail.received_at,
        "attachments": [],
        "inline_skipped": 0,
        "auto_submitted": mail.auto_submitted,
    }


def _external(payload: InboundMailEventIn, source: InboundMailSource) -> dict[str, Any]:
    """What the sender claims; kept apart from the platform's own ``classification`` keys."""
    external = payload.classification.model_dump(exclude_none=True)
    if not external.get("labels"):
        external.pop("labels", None)
    if payload.mail.attachment_count is not None:
        external["attachment_count"] = payload.mail.attachment_count
    result: dict[str, Any] = {
        "source": {
            "kind": "inbound_webhook",
            "source_id": str(source.id),
            "source_name": source.name,
            "event_id": payload.event_id,
        },
        "external": external,
    }
    if payload.source_ref:
        result["source"]["source_ref"] = payload.source_ref
    if payload.classified_at:
        result["source"]["classified_at"] = payload.classified_at.isoformat()
    return clean_json(result)  # type: ignore[no-any-return]


# --- delivery -------------------------------------------------------------------------------


@router.post(
    "/sources/{source_id}/classified-mails",
    summary="Klassifizierte Mail des Bestandsprogramms entgegennehmen",
    status_code=201,
    responses={
        200: {"description": "Dasselbe Ereignis erneut gesendet, gespeichertes Ergebnis"},
        401: {"description": "Schlüssel oder Signatur ungültig"},
        404: {"description": "Quelle unbekannt (auch Quelle eines anderen Mandanten)"},
        409: {"description": "Ereignis-ID mit anderem Inhalt oder Quelle deaktiviert"},
        413: {"description": "Inhalt größer als 1 MiB"},
    },
)
async def receive_classified_mail(
    source_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: TenantPrincipal = Depends(INGEST),
) -> InboundMailReceiptOut:
    from mhvp.communication.services import ingest_parsed

    if principal.api_key_id is None:
        # A machine endpoint: a signed in user never delivers, the key carries the grant.
        raise ProblemError(
            ErrorCodes.FORBIDDEN, developer_message="Only an API key may deliver inbound mails."
        )
    raw = await _read_limited(request)
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        source = await session.get(InboundMailSource, source_id)
        if source is None:  # unknown, or a source of another tenant (RLS)
            raise _not_found()
        if not verify_signature(source.secret, raw, request.headers.get(SIGNATURE_HEADER)):
            log.warning("inbound mail webhook rejected", extra={"source_id": str(source_id)})
            raise ProblemError(ErrorCodes.WEBHOOK_SIGNATURE)
        if not source.active:
            raise ProblemError(ErrorCodes.INBOUND_MAIL_SOURCE_INACTIVE)
        document, payload = _parse_document(raw)
        digest = canonical_hash(document)
        claimed = await session.scalar(
            pg_insert(InboundMailEvent)
            .values(
                id=uuid7(),
                tenant_id=principal.tenant_id,
                source_id=source.id,
                event_id=payload.event_id,
                payload_sha256=digest,
                message_created=True,
                replay_count=0,
            )
            .on_conflict_do_nothing(index_elements=["source_id", "event_id"])
            .returning(InboundMailEvent.id)
        )
        if claimed is None:
            existing = await session.scalar(
                select(InboundMailEvent).where(
                    InboundMailEvent.source_id == source.id,
                    InboundMailEvent.event_id == payload.event_id,
                )
            )
            if existing is None:  # pragma: no cover - the claiming transaction rolled back
                raise ProblemError(ErrorCodes.CONFLICT)
            if existing.payload_sha256 != digest:
                raise ProblemError(ErrorCodes.INBOUND_MAIL_EVENT_CONFLICT)
            # Atomic counter: parallel retries must not overwrite each other's increment.
            await session.execute(
                update(InboundMailEvent)
                .where(InboundMailEvent.id == existing.id)
                .values(
                    replay_count=InboundMailEvent.replay_count + 1,
                    last_replayed_at=datetime.now(UTC),
                )
            )
            response.status_code = 200
            return InboundMailReceiptOut(
                event_id=existing.event_id,
                replayed=True,
                message_created=existing.message_created,
                message_id=existing.message_id,
                ticket_id=existing.ticket_id,
            )
        event = await session.get(InboundMailEvent, claimed)
        assert event is not None  # noqa: S101 - just inserted in this transaction
        row, created = await ingest_parsed(
            session,
            None,
            settings,
            tenant_id=principal.tenant_id,
            actor_user_id=None,
            parsed=to_parsed(payload),
            document_id=None,
            mailbox_id=source.mailbox_id,
            auto_ticket=source.auto_ticket,
        )
        if created:
            row.classification = dict(row.classification) | _external(payload, source)
        event.message_id, event.ticket_id, event.message_created = row.id, row.ticket_id, created
        source.last_received_at = datetime.now(UTC)
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="inbound_mail.received",
            entity_type="inbound_mail_event",
            entity_id=event.id,
            actor_user_id=None,
            payload={
                "source_id": str(source.id),
                "message_id": str(row.id),
                "ticket_id": str(row.ticket_id) if row.ticket_id else None,
                "created": created,
                "api_key_id": str(principal.api_key_id),
            },
        )
        return InboundMailReceiptOut(
            event_id=payload.event_id,
            replayed=False,
            message_created=created,
            message_id=row.id,
            ticket_id=row.ticket_id,
        )


# --- administration of the sources ----------------------------------------------------------


@router.get(
    "/sources",
    summary="Mailquellen des Bestandsprogramms",
    dependencies=[Depends(strict_query)],
)
async def list_sources(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> list[InboundMailSourceOut]:
    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(select(InboundMailSource).order_by(InboundMailSource.created_at))
        ).all()
        return [_source_out(row) for row in rows]


async def _check_mailbox(session: Any, mailbox_id: uuid.UUID | None) -> None:
    if mailbox_id is not None and await session.get(Mailbox, mailbox_id) is None:
        raise _not_found()


@router.post("/sources", status_code=201, summary="Mailquelle anlegen (Geheimnis einmalig)")
async def create_source(
    body: InboundMailSourceCreate,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> InboundMailSourceCreated:
    secret = tokens.new_opaque_secret(SECRET_BYTES)
    async with tenant_tx(request, principal) as session:
        await _check_mailbox(session, body.mailbox_id)
        name = body.name
        if await session.scalar(select(InboundMailSource.id).where(InboundMailSource.name == name)):
            raise ProblemError(ErrorCodes.CONFLICT)
        row = InboundMailSource(
            tenant_id=principal.tenant_id,
            name=name,
            secret=secret,
            active=True,
            mailbox_id=body.mailbox_id,
            auto_ticket=body.auto_ticket,
            created_by=principal.user_id,
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError:
            raise ProblemError(ErrorCodes.CONFLICT) from None
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="inbound_mail_source.created",
            entity_type="inbound_mail_source",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"name": row.name, "auto_ticket": row.auto_ticket},
        )
        return InboundMailSourceCreated(**_source_out(row).model_dump(), secret=secret)


@router.patch("/sources/{source_id}", summary="Mailquelle ändern")
async def update_source(
    source_id: uuid.UUID,
    body: InboundMailSourceUpdate,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> InboundMailSourceOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(InboundMailSource, source_id)
        if row is None:
            raise _not_found()
        changed: list[str] = []
        if "name" in body.model_fields_set and body.name is not None:
            name = body.name
            clash = await session.scalar(
                select(InboundMailSource.id).where(
                    InboundMailSource.name == name, InboundMailSource.id != row.id
                )
            )
            if clash is not None:
                raise ProblemError(ErrorCodes.CONFLICT)
            row.name = name
            changed.append("name")
        if "active" in body.model_fields_set and body.active is not None:
            row.active = body.active
            changed.append("active")
        if "auto_ticket" in body.model_fields_set and body.auto_ticket is not None:
            row.auto_ticket = body.auto_ticket
            changed.append("auto_ticket")
        if "mailbox_id" in body.model_fields_set:
            await _check_mailbox(session, body.mailbox_id)
            row.mailbox_id = body.mailbox_id
            changed.append("mailbox_id")
        row.updated_by = principal.user_id
        await session.flush()
        if changed:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="inbound_mail_source.updated",
                entity_type="inbound_mail_source",
                entity_id=row.id,
                actor_user_id=principal.user_id,
                payload={"fields": sorted(changed)},
            )
        return _source_out(row)


@router.post(
    "/sources/{source_id}/rotate-secret",
    summary="Geheimnis der Mailquelle erneuern (altes sofort ungültig)",
)
async def rotate_secret(
    source_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_UPDATE),
) -> InboundMailSourceCreated:
    secret = tokens.new_opaque_secret(SECRET_BYTES)
    async with tenant_tx(request, principal) as session:
        row = await session.get(InboundMailSource, source_id)
        if row is None:
            raise _not_found()
        row.secret = secret
        row.secret_rotated_at = datetime.now(UTC)
        row.updated_by = principal.user_id
        await session.flush()
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="inbound_mail_source.secret_rotated",
            entity_type="inbound_mail_source",
            entity_id=row.id,
            actor_user_id=principal.user_id,
        )
        return InboundMailSourceCreated(**_source_out(row).model_dump(), secret=secret)


@router.get(
    "/sources/{source_id}/events",
    summary="Empfangsprotokoll einer Mailquelle",
    dependencies=[Depends(strict_query)],
)
async def list_events(
    source_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_READ),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[InboundMailEventOut]:
    async with tenant_tx(request, principal) as session:
        if await session.get(InboundMailSource, source_id) is None:
            raise _not_found()
        rows = (
            await session.scalars(
                select(InboundMailEvent)
                .where(InboundMailEvent.source_id == source_id)
                .order_by(InboundMailEvent.created_at.desc(), InboundMailEvent.id.desc())
                .limit(limit)
            )
        ).all()
        return [_event_out(row) for row in rows]
