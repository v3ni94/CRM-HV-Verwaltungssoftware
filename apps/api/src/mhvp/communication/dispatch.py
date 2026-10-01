"""Dispatch per channel, delivery evidence, communication history, calendar feed (M23).

Postal dispatch is recorded with evidence (for example registered mail number); a print and
mail provider is not connected (M23-01). E-mail dispatch prepares a draft for the mailbox
(M20); portal dispatch makes the document visible in the recipient's portal inbox."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import calendar_feed  # noqa: F401  (registers the token table)
from mhvp.communication.models import Dispatch, Message
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.blobs import BlobStore

router = APIRouter(tags=["Kommunikation"])
CREATE = require_permission("communication:create")
UPDATE = require_permission("communication:update")
READ_CONTACTS = require_permission("contacts:read")
# sms, registered (Einschreiben) and courier (Bote) have no provider: the dispatch is prepared
# and the delivery is recorded with evidence (M23-05). ``post`` can create the postal job.
CHANNELS = ("post", "email", "portal", "sms", "registered", "courier")
EVIDENCE = (
    "registered_mail",
    "courier",
    "hand_delivery",
    "email_log",
    "portal_read",
    "sms_log",
    "other",
)
# Evidence kinds that prove delivery per channel; channels not listed accept every kind.
CHANNEL_EVIDENCE: dict[str, tuple[str, ...]] = {
    "registered": ("registered_mail", "other"),
    "courier": ("courier", "hand_delivery", "other"),
    "sms": ("sms_log", "other"),
}


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DispatchIn(_In):
    document_id: uuid.UUID
    contact_id: uuid.UUID
    channel: str | None = Field(
        default=None, pattern="^(post|email|portal|sms|registered|courier)$"
    )
    # channel post: the postal job is created automatically (M23-05, default None = automatic).
    # Gates and rights of the postal module apply unchanged: without request context, without
    # release of an external provider or without communication:approve the dispatch stays
    # prepared and the job is created via POST /postal/jobs. True forces the submit (errors are
    # reported), False suppresses it.
    submit_postal: bool | None = None


class SerialDispatchIn(_In):
    items: list[DispatchIn] = Field(min_length=1, max_length=2000)
    # AC06: True marks the batch as advertising ("Werbung"); only contacts with a valid
    # marketing consent receive it, the others are skipped and counted. Mandatory
    # communication (statements, dunning, invitations) keeps the default False.
    advertising: bool = False


class SerialMergeIn(_In):
    """Template with placeholders merged per recipient, then dispatched (M23-03)."""

    template_id: uuid.UUID
    contact_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    channel: str | None = Field(
        default=None, pattern="^(post|email|portal|sms|registered|courier)$"
    )
    property_id: uuid.UUID | None = None
    unit_id: uuid.UUID | None = None
    letter_date: date | None = None
    reference: str | None = Field(default=None, max_length=50)
    fields: dict[str, str] = Field(default_factory=dict)
    signatory: list[str] = Field(default_factory=list, max_length=4)
    advertising: bool = False  # AC06, see SerialDispatchIn.advertising


class EvidenceIn(_In):
    status: str = Field(pattern="^(sent|delivered|failed)$")
    evidence_kind: str | None = Field(default=None, pattern="^(" + "|".join(EVIDENCE) + ")$")
    evidence_ref: str | None = Field(default=None, max_length=200)
    evidence_document_id: uuid.UUID | None = None
    occurred_at: datetime | None = None


def _out(d: Dispatch) -> dict[str, Any]:
    return {
        k: getattr(d, k)
        for k in (
            "id",
            "document_id",
            "contact_id",
            "channel",
            "status",
            "message_id",
            "batch",
            "evidence_kind",
            "evidence_ref",
            "evidence_document_id",
            "sent_at",
            "delivered_at",
        )
    }


def _consent_log() -> dict[str, Any]:
    """Counters of the consent checks of one request (AC06)."""
    return {
        "marketing_skipped": 0,
        "marketing_skipped_contact_ids": [],
        "email_fallback_to_post": 0,
        "email_fallback_contact_ids": [],
    }


def _grouped(batch: str, rows: list[Dispatch], log: dict[str, Any] | None = None) -> dict[str, Any]:
    """Rows per channel. The original channels always appear (also with 0), the newer ones
    (sms, registered, courier) only when used, so existing clients see the same keys."""
    groups: dict[str, list[dict[str, Any]]] = {c: [] for c in CHANNELS}
    for r in rows:
        groups[r.channel].append(_out(r))
    groups = {c: v for c, v in groups.items() if v or c in ("post", "email", "portal")}
    return {
        "batch": batch,
        "by_channel": groups,
        "counts": {c: len(v) for c, v in groups.items()},
        "consent": log or _consent_log(),
    }


async def _create(
    session: Any,
    principal: TenantPrincipal,
    item: DispatchIn,
    batch: str | None,
    request: Request | None = None,
    log: dict[str, Any] | None = None,
) -> Dispatch:
    from mhvp.contacts import consent_rules
    from mhvp.contacts.models import Contact, ContactEmail, ContactPhone
    from mhvp.documents.models import Document, DocumentLink, LinkRole

    contact = await session.get(Contact, item.contact_id)
    document = await session.get(Document, item.document_id)
    if contact is None or document is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    channel = item.channel or (
        contact.preferred_channel.value
        if contact.preferred_channel
        else await _tenant_default_channel(session)
    )
    if channel == "email":
        # AC06: documents go by e-mail only with a valid email_delivery consent or when the
        # tenant policy accepts a contractual agreement; otherwise the delivery falls back to
        # post and the reason is recorded as an event.
        decision = await consent_rules.email_delivery_decision(session, contact.id)
        if not decision.allowed:
            channel = "post"
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="dispatch.channel_fallback",
                entity_type="contact",
                entity_id=contact.id,
                actor_user_id=principal.user_id,
                payload={
                    "document_id": str(document.id),
                    "requested_channel": "email",
                    "channel": "post",
                    "reason": decision.reason,
                    "batch": batch,
                },
            )
            if log is not None:
                log["email_fallback_to_post"] += 1
                log["email_fallback_contact_ids"].append(str(contact.id))
    row = Dispatch(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        document_id=document.id,
        contact_id=contact.id,
        channel=channel,
        batch=batch,
    )
    linked = await session.scalar(
        select(DocumentLink.id).where(
            DocumentLink.document_id == document.id,
            DocumentLink.entity_type == "contact",
            DocumentLink.entity_id == contact.id,
        )
    )
    if linked is None:
        session.add(
            DocumentLink(
                tenant_id=principal.tenant_id,
                document_id=document.id,
                entity_type="contact",
                entity_id=contact.id,
                role=LinkRole.GENERATED,
            )
        )
    if channel == "email":
        address = await session.scalar(
            select(ContactEmail.email)
            .where(ContactEmail.contact_id == contact.id)
            .order_by(ContactEmail.is_primary.desc())
            .limit(1)
        )
        if address is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"{contact.display_name}: keine E-Mail-Adresse für den Versand.",
            )
        message = Message(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            direction="out",
            status="draft",
            to_addresses=[address],
            subject=document.title[:998],
            body="Anbei erhalten Sie unser Schreiben.",
            contact_id=contact.id,
            attachment_document_ids=[document.id],
        )
        session.add(message)
        await session.flush()
        row.message_id = message.id
    if channel == "portal":
        row.status, row.sent_at = "sent", datetime.now(UTC)  # visible in the portal inbox now
    if channel == "sms":
        phone = await session.scalar(
            select(ContactPhone.number)
            .where(ContactPhone.contact_id == contact.id)
            .order_by(ContactPhone.is_primary.desc())
            .limit(1)
        )
        if phone is None:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail=f"{contact.display_name}: keine Telefonnummer für den SMS Versand.",
            )
    session.add(row)
    await session.flush()
    if channel == "post" and item.submit_postal is not False:
        from mhvp.communication.postal import (
            PostalSubmitIn,
            provider_for,
            settings_row,
            submit,
        )

        explicit = item.submit_postal is True
        if request is None:
            if explicit:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Postauftrag hier nicht möglich.")
        else:
            automatic_ok = True
            if not explicit:
                settings = await settings_row(session, principal.tenant_id)
                provider = provider_for(settings)
                if provider.name != "manual":
                    automatic_ok = settings.enabled and principal.has("communication:approve")
            if automatic_ok:
                await submit(session, request, principal, PostalSubmitIn(dispatch_id=row.id))
    return row


async def create_dispatch(
    session: Any, principal: TenantPrincipal, item: DispatchIn, batch: str | None
) -> Dispatch:
    """Public entry for letters filed elsewhere (``mhvp.documents.letter_records``): same
    rules as the dispatch endpoints, one row per document and recipient."""
    return await _create(session, principal, item, batch)


async def expand_items(session: Any, items: list[DispatchIn]) -> list[DispatchIn]:
    """One item per resolved recipient (delivery rule of representatives), without repeats
    of the same document and contact. An explicit channel of the item also applies to the
    representative; without one each recipient's preferred channel counts."""
    from mhvp.contacts.recipients import resolve_recipients

    out: list[DispatchIn] = []
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for item in items:
        for recipient in await resolve_recipients(session, [item.contact_id]):
            key = (item.document_id, recipient.contact_id)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                DispatchIn(
                    document_id=item.document_id,
                    contact_id=recipient.contact_id,
                    channel=item.channel,
                    submit_postal=item.submit_postal,
                )
            )
    return out


@router.post("/dispatches", status_code=201, summary="Zustellung vorbereiten")
async def create(
    body: DispatchIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """The delivery rule of authorised representatives applies (M23-07): the first dispatch
    is returned, dispatches for further recipients in ``further_dispatches``."""
    async with tenant_tx(request, principal) as session:
        rows = [
            await _create(session, principal, item, None, request)
            for item in await expand_items(session, [body])
        ]
        return {**_out(rows[0]), "further_dispatches": [_out(r) for r in rows[1:]]}


@router.post("/dispatches/serial", status_code=201, summary="Serienversand je Zustellweg")
async def serial(
    body: SerialDispatchIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """Recipients follow the delivery rule of authorised representatives
    (``mhvp.contacts.recipients``): depending on the rule the represented contact, the
    representative or both receive the document; a contact reached twice gets it once."""
    batch = uuid.uuid4().hex[:16]
    log = _consent_log()
    async with tenant_tx(request, principal) as session:
        items = await expand_items(session, body.items)
        if body.advertising:
            items = await _marketing_filter(session, principal, items, batch, log)
        rows = [await _create(session, principal, item, batch, request, log) for item in items]
        return _grouped(batch, rows, log)


@router.post(
    "/dispatches/serial-merge",
    status_code=201,
    summary="Serienbrief aus Vorlage erzeugen und je Zustellweg versenden",
)
async def serial_merge(
    body: SerialMergeIn, request: Request, principal: TenantPrincipal = Depends(CREATE)
) -> dict[str, Any]:
    """One document per resolved recipient from the letter template (placeholders of the
    recipient, the entity and ``felder``), filed and linked like ``POST /letters``, each with
    its dispatch. Recipients follow the delivery rule of authorised representatives. Nothing
    is sent: e-mail becomes a draft, post a prepared dispatch, portal visibility follows the
    portal rules. One missing address or placeholder aborts the whole batch (no half batch)."""
    from mhvp.contacts.recipients import resolve_recipients
    from mhvp.documents import services as doc_services
    from mhvp.documents.routers import _letter, _template

    if not principal.has("documents:create"):
        raise ProblemError(ErrorCodes.FORBIDDEN, detail="Recht documents:create fehlt.")
    batch = uuid.uuid4().hex[:16]
    log = _consent_log()
    async with tenant_tx(request, principal) as session:
        template = await _template(session, body.template_id)
        head = await doc_services.letterhead(session, BlobStore(request.app.state.settings))
        letter_date = body.letter_date or datetime.now(UTC).date()
        rows: list[Dispatch] = []
        seen: set[uuid.UUID] = set()
        recipients = await resolve_recipients(session, body.contact_ids)
        allowed: set[uuid.UUID] | None = None
        if body.advertising:
            allowed = await _marketing_allowed(
                session, principal, [r.contact_id for r in recipients], batch, log
            )
        for recipient in recipients:
            if recipient.contact_id in seen:
                continue
            seen.add(recipient.contact_id)
            if allowed is not None and recipient.contact_id not in allowed:
                continue
            _, document = await _letter(
                session,
                request,
                principal,
                template,
                head,
                contact_id=recipient.contact_id,
                represents=recipient.represents,
                property_id=body.property_id,
                unit_id=body.unit_id,
                contract_id=None,
                letter_date=letter_date,
                reference=body.reference,
                fields=body.fields,
                signatory=body.signatory,
                store=True,
            )
            assert document is not None  # noqa: S101
            rows.append(
                await _create(
                    session,
                    principal,
                    DispatchIn(
                        document_id=document.id,
                        contact_id=recipient.contact_id,
                        channel=body.channel,
                    ),
                    batch,
                    request,
                    log,
                )
            )
        return _grouped(batch, rows, log)


@router.post(
    "/dispatches/{dispatch_id}/evidence", summary="Versand oder Zugang mit Nachweis erfassen"
)
async def evidence(
    dispatch_id: uuid.UUID,
    body: EvidenceIn,
    request: Request,
    principal: TenantPrincipal = Depends(UPDATE),
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        row = await session.get(Dispatch, dispatch_id, with_for_update=True)
        if row is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        if row.status == "delivered":
            raise ProblemError(ErrorCodes.CONFLICT, detail="Zugang ist bereits nachgewiesen.")
        if body.status == "delivered" and not (
            body.evidence_kind and (body.evidence_ref or body.evidence_document_id)
        ):
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Zugang nur mit Nachweis (Art und Referenz oder Beleg).",
            )
        allowed = CHANNEL_EVIDENCE.get(row.channel)
        if body.status == "delivered" and allowed is not None and body.evidence_kind not in allowed:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Nachweisart passt nicht zum Zustellweg (erlaubt: "
                + ", ".join(allowed)
                + ").",
            )
        at = body.occurred_at or datetime.now(UTC)
        row.status = body.status
        row.evidence_kind, row.evidence_ref, row.evidence_document_id = (
            body.evidence_kind,
            body.evidence_ref,
            body.evidence_document_id,
        )
        if body.status in ("sent", "delivered") and row.sent_at is None:
            row.sent_at = at
        if body.status == "delivered":
            row.delivered_at = at
            if row.message_id is not None:
                from mhvp.communication.receipts import mark_delivered

                linked = await session.get(Message, row.message_id)
                if linked is not None:
                    mark_delivered(linked, at)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type=f"dispatch.{body.status}",
            entity_type="dispatch",
            entity_id=row.id,
            actor_user_id=principal.user_id,
            payload={"evidence": body.evidence_kind},
        )
        await session.flush()
        return _out(row)


@router.get(
    "/contacts/{contact_id}/history",
    summary="Kommunikationshistorie des Kontakts",
    dependencies=[Depends(strict_query)],
)
async def history(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(READ_CONTACTS)
) -> list[dict[str, Any]]:
    from mhvp.tickets.models import Ticket

    async with tenant_tx(request, principal) as session:
        events: list[dict[str, Any]] = []
        if principal.has("communication:read"):
            for m in (
                await session.scalars(
                    # One entry per mail: linked copies from other own mailboxes share the
                    # contact (feedback 28.09.2026).
                    select(Message).where(
                        Message.contact_id == contact_id, Message.duplicate_of_id.is_(None)
                    )
                )
            ).all():
                events.append(
                    {
                        "kind": f"email_{m.direction}",
                        "at": m.received_at or m.sent_at or m.created_at,
                        "title": m.subject,
                        "id": m.id,
                        "status": m.status,
                    }
                )
            for d in (
                await session.scalars(select(Dispatch).where(Dispatch.contact_id == contact_id))
            ).all():
                events.append(
                    {
                        "kind": f"dispatch_{d.channel}",
                        "at": d.delivered_at or d.sent_at or d.created_at,
                        "title": str(d.document_id),
                        "id": d.id,
                        "status": d.status,
                    }
                )
        if principal.has("tickets:read"):
            for t in (
                await session.scalars(
                    select(Ticket).where(Ticket.initiator_contact_id == contact_id)
                )
            ).all():
                events.append(
                    {
                        "kind": "ticket",
                        "at": t.created_at,
                        "title": t.title,
                        "id": t.id,
                        "status": t.status.value,
                    }
                )
        return sorted(events, key=lambda e: e["at"], reverse=True)


def _ics_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", r"\;").replace(",", "\\,").replace("\n", "\\n")


async def build_ics(
    session: Any, user_id: uuid.UUID | None, *, contracts: bool, properties: bool
) -> str:
    """ICS text of own and shared entries and derived dates (shared by the logged in feed and
    the token feed of ``calendar_feed``)."""
    from sqlalchemy import or_

    from mhvp.workspace import services
    from mhvp.workspace.models import CalendarEntry

    today = services.local_today()
    end = today + timedelta(days=366)
    entries = (
        await session.scalars(
            select(CalendarEntry).where(
                or_(CalendarEntry.owner_user_id == user_id, CalendarEntry.shared),
                CalendarEntry.starts_on.between(today - timedelta(days=30), end),
            )
        )
    ).all()
    derived = await services.derived_dates(
        session,
        today - timedelta(days=30),
        end,
        contracts=contracts,
        properties=properties,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MHVP//Kalender//DE", "CALSCALE:GREGORIAN"]

    def event(uid: str, day: date, title: str) -> None:
        nxt = day + timedelta(days=1)
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}@mhvp",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                f"DTEND;VALUE=DATE:{nxt:%Y%m%d}",
                f"SUMMARY:{_ics_escape(title)}",
                "END:VEVENT",
            ]
        )

    for e in entries:
        event(str(e.id), e.starts_on, e.title)
    for d in derived:
        event(f"{d['kind']}-{d['entity_id']}", d["date"], d["title"])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


@router.get(
    "/workspace/calendar.ics", summary="Kalender als ICS (eigene, geteilte Termine, Fristen)"
)
async def calendar_ics(
    request: Request,
    principal: TenantPrincipal = Depends(require_permission("tenant_settings:read")),
) -> PlainTextResponse:
    async with tenant_tx(request, principal) as session:
        body = await build_ics(
            session,
            principal.user_id,
            contracts=principal.has("contracts:read"),
            properties=principal.has("properties:read"),
        )
    return PlainTextResponse(body, media_type="text/calendar")


async def _tenant_default_channel(session: AsyncSession) -> str:
    """GA01-08: tenant wide default delivery channel (``tenant_settings.sources``), else post."""
    from mhvp.platform.models import TenantSettings

    sources = await session.scalar(select(TenantSettings.sources)) or {}
    value = sources.get("default_delivery_channel")
    return value if value in ("post", "email", "portal") else "post"


async def _marketing_allowed(
    session: Any,
    principal: TenantPrincipal,
    contact_ids: list[uuid.UUID],
    batch: str,
    log: dict[str, Any],
) -> set[uuid.UUID]:
    """AC06: contacts of an advertising batch with a valid marketing consent. The skipped
    ones are counted in ``log`` and recorded once as ``dispatch.marketing_skipped``."""
    from mhvp.contacts.consent_rules import load_policy, marketing_permitted

    unique = list(dict.fromkeys(contact_ids))
    # AE34: the legal basis of the tenant decides (consent, or legitimate interest without
    # objection); the default is the restrictive variant, a valid consent.
    policy = await load_policy(session)
    allowed = await marketing_permitted(session, unique, policy)
    reason = (
        "marketing_objection_recorded"
        if policy.basis_for("marketing") == "legitimate_interest"
        else "marketing_consent_missing"
    )
    skipped = [c for c in unique if c not in allowed]
    if skipped:
        log["marketing_skipped"] += len(skipped)
        log["marketing_skipped_contact_ids"].extend(str(c) for c in skipped)
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="dispatch.marketing_skipped",
            entity_type="dispatch_batch",
            entity_id=None,
            actor_user_id=principal.user_id,
            payload={
                "batch": batch,
                "reason": reason,
                "count": len(skipped),
                "contact_ids": [str(c) for c in skipped],
            },
        )
    return allowed


async def _marketing_filter(
    session: Any,
    principal: TenantPrincipal,
    items: list[DispatchIn],
    batch: str,
    log: dict[str, Any],
) -> list[DispatchIn]:
    allowed = await _marketing_allowed(
        session, principal, [i.contact_id for i in items], batch, log
    )
    return [i for i in items if i.contact_id in allowed]
