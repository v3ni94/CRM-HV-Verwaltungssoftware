"""Invoice copies from Lexware Office (rule INT-LEXO-01, section 6 of the spec).

A request row (``LexofficeInvoiceCopyRequest``) comes from the deterministic mail detector
or from a manual entry at the ticket. The lookup worker searches the voucher list of every
config with ``invoice_copies``; verification is deterministic: the requester (the contact a
person assigned to the message or ticket) must be the invoice recipient known through the
contact link table. The from address is only a hint. The fetch worker stores the PDF (and
XRechnung XML) in the DMS and writes a reply draft addressed only to the recipient's known
primary e mail, with a forced second person approval and a recipient lock.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import AdminFeeInvoice
from mhvp.communication import mail
from mhvp.communication.models import Mailbox, Message
from mhvp.contacts.models import Contact, ContactEmail
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.documents.models import Document, DocumentCategory, DocumentSource, LinkRole
from mhvp.documents.services import check_upload, store_document
from mhvp.integrations.lexoffice_async import (
    LexofficeConflictError,
    LexofficeNotFoundError,
)
from mhvp.integrations.lexoffice_ext import services
from mhvp.integrations.models import (
    LexofficeContactLink,
    LexofficeInvoiceCopyRequest,
    LexofficeOutbox,
    LexofficeOutboxKind,
    LexofficeTenantConfig,
)
from mhvp.tickets.models import Ticket, TicketEvent, TicketReplyTemplate
from mhvp.tickets.tnr import subject_with_tnr

log = logging.getLogger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")
MAX_FILE_BYTES = 25 * 1024 * 1024
SOURCE_SYSTEM = "lexoffice"
CATEGORY_CODE = "lexoffice_invoice"
TEMPLATE_TOPIC = "lexoffice_invoice_copy"
COPYABLE_STATUSES = frozenset({"open", "paid", "paidoff", "voided", "overdue"})
LINK_STATES = frozenset({"linked", "synced", "pending", "error"})
DEFAULT_BODY = (
    "Sehr geehrte Damen und Herren,\n\n"
    "anbei erhalten Sie die gewünschte Kopie der Rechnung {rechnungsnummer} vom "
    "{rechnungsdatum} über {betrag}.\n\nMit freundlichen Grüßen"
)


def _event(
    session: AsyncSession,
    req: LexofficeInvoiceCopyRequest,
    kind: str,
    data: dict[str, Any],
    user_id: uuid.UUID | None = None,
) -> None:
    session.add(
        TicketEvent(
            tenant_id=req.tenant_id,
            ticket_id=req.ticket_id,
            kind=kind,
            data={"request_id": str(req.id), **data},
            user_id=user_id,
        )
    )


def format_amount(value: str | Decimal | None) -> str:
    if value is None:
        return ""
    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} EUR"


def format_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        return (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            .astimezone(BERLIN)
            .strftime("%d.%m.%Y")
        )
    except ValueError:
        return value[:10]


# Creation --------------------------------------------------------------------------------


async def enabled_configs(
    session: AsyncSession, tenant_id: uuid.UUID
) -> list[LexofficeTenantConfig]:
    return [
        c
        for c in await services.list_configs(session, tenant_id)
        if services.feature_on(c, "invoice_copies")
    ]


async def queue_for_message(session: AsyncSession, tenant_id: uuid.UUID, message: Message) -> None:
    """Inbound mail with ticket and detector hit: one request row, lookup rows queued."""
    if message.direction != "in" or message.ticket_id is None:
        return
    try:
        detected = mail.invoice_copy_request(message.subject, message.body)
        stored = message.suggestion or {}
        if detected is None and stored.get("intent") != "invoice_copy_requested":
            return
        number = (detected or {}).get("invoice_number") or stored.get("invoice_number")
        if not number:
            return
        configs = await enabled_configs(session, tenant_id)
        if not configs:
            return
        existing = await session.scalar(
            select(LexofficeInvoiceCopyRequest.id).where(
                LexofficeInvoiceCopyRequest.message_id == message.id,
                LexofficeInvoiceCopyRequest.status != "rejected",
            )
        )
        if existing is not None:
            return
        ticket = await session.get(Ticket, message.ticket_id)
        if ticket is None:
            return
        await create_request(session, tenant_id, ticket, str(number), message=message, actor=None)
    except Exception:  # pragma: no cover - never disturb mail intake
        log.exception("lexoffice: invoice copy detection failed")


async def create_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    ticket: Ticket,
    invoice_number: str,
    *,
    message: Message | None,
    actor: uuid.UUID | None,
) -> LexofficeInvoiceCopyRequest:
    configs = await enabled_configs(session, tenant_id)
    if not configs:
        raise ProblemError(ErrorCodes.LEXOFFICE_FEATURE_DISABLED)
    requester = (message.contact_id if message is not None else None) or ticket.contact_id
    req = LexofficeInvoiceCopyRequest(
        tenant_id=tenant_id,
        ticket_id=ticket.id,
        message_id=message.id if message is not None else None,
        invoice_number=invoice_number.strip()[:64],
        requester_contact_id=requester,
        status="pending",
        lookup={"status": "pending", "hits": [], "platform_hits": [], "pending_configs": []},
        verification={"status": "pending", "hint_from_address_match": None},
        created_by=actor,
    )
    session.add(req)
    await session.flush()
    req.lookup = {
        **req.lookup,
        "platform_hits": await platform_hits(session, tenant_id, req.invoice_number),
    }
    pending: list[str] = []
    for config in configs:
        await services.enqueue(
            session,
            tenant_id=tenant_id,
            config_id=config.id,
            kind=LexofficeOutboxKind.LOOKUP_INVOICE,
            idempotency_key=f"invoice-lookup-{req.id}-cfg{config.id}",
            target_kind="proposal",
            target_id=req.id,
            payload={"invoice_number": req.invoice_number},
            requested_by=actor,
        )
        pending.append(str(config.id))
    req.lookup = {**req.lookup, "pending_configs": pending}
    _event(
        session,
        req,
        "proposal_created",
        {"kind": "invoice_copy", "invoice_number": req.invoice_number},
        actor,
    )
    await session.flush()
    return req


async def platform_hits(
    session: AsyncSession, tenant_id: uuid.UUID, number: str
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    fee = await session.scalar(
        select(AdminFeeInvoice).where(
            AdminFeeInvoice.tenant_id == tenant_id, AdminFeeInvoice.number == number
        )
    )
    if fee is not None:
        hits.append(
            {"kind": "admin_fee_invoice", "id": str(fee.id), "title": f"Honorarrechnung {number}"}
        )
    docs = (
        await session.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id, Document.title.ilike(f"%{number}%"))
            .order_by(Document.created_at.desc())
            .limit(5)
        )
    ).all()
    for doc in docs:
        hits.append(
            {"kind": "document", "id": str(doc.id), "title": doc.title, "document_id": str(doc.id)}
        )
    return hits


# Lookup worker ----------------------------------------------------------------------------


@services.handler(LexofficeOutboxKind.LOOKUP_INVOICE)
async def lookup_invoice(ctx: services.WorkerContext, row: LexofficeOutbox) -> None:
    req = await ctx.session.get(LexofficeInvoiceCopyRequest, row.target_id)
    if req is None or req.status == "rejected":
        services.fail(row, "Anfrage nicht gefunden.")
        return
    number = str(row.payload.get("invoice_number") or req.invoice_number).strip()
    page = await ctx.client.list_voucherlist(
        "invoice,creditnote", "any", voucher_number=number, size=25
    )
    hits: list[dict[str, Any]] = []
    for item in page.get("content") or []:
        if not isinstance(item, dict) or str(item.get("voucherNumber") or "").strip() != number:
            continue
        kind = str(item.get("voucherType") or "invoice")
        hit: dict[str, Any] = {
            "config_id": str(ctx.config.id),
            "legal_entity_id": str(ctx.config.legal_entity_id)
            if ctx.config.legal_entity_id
            else None,
            "legal_entity_label": ctx.config.label or ctx.config.organization_name,
            "kind": kind,
            "lexoffice_invoice_id": str(item.get("id")),
            "voucher_number": number,
            "voucher_date": item.get("voucherDate"),
            "total_gross": str(item.get("totalAmount"))
            if item.get("totalAmount") is not None
            else None,
            "status": str(item.get("voucherStatus") or ""),
            "address_name": item.get("contactName"),
            "address_contact_id": item.get("contactId"),
            "electronic_document_profile": None,
            "deeplink": services.deeplink(ctx.config, "invoice", str(item.get("id"))),
        }
        if kind == "invoice":
            try:
                detail = await ctx.client.get_invoice(str(item.get("id")))
            except LexofficeNotFoundError:
                continue
            address = detail.get("address") or {}
            hit["address_name"] = address.get("name")
            hit["address_contact_id"] = address.get("contactId")
            hit["status"] = str(detail.get("voucherStatus") or hit["status"])
            hit["voucher_date"] = detail.get("voucherDate") or hit["voucher_date"]
            total = (detail.get("totalPrice") or {}).get("totalGrossAmount")
            if total is not None:
                hit["total_gross"] = str(total)
            hit["electronic_document_profile"] = (detail.get("xRechnung") or {}).get(
                "profile"
            ) or detail.get("electronicDocumentProfile")
        hits.append(hit)
    lookup = dict(req.lookup or {})
    others = [h for h in lookup.get("hits") or [] if h.get("config_id") != str(ctx.config.id)]
    lookup["hits"] = others + hits
    lookup["pending_configs"] = [
        c for c in lookup.get("pending_configs") or [] if c != str(ctx.config.id)
    ]
    if not lookup["pending_configs"]:
        lookup["status"] = _lookup_status(lookup["hits"])
        req.status = lookup["status"]
    req.lookup = lookup
    _event(
        ctx.session,
        req,
        "lexoffice_invoice_lookup",
        {"hits": len(hits), "config_id": str(ctx.config.id)},
    )
    await verify(ctx.session, req)
    await services.audit(
        ctx.session,
        ctx.tenant_id,
        "invoice_lookup",
        entity_type="lexoffice_outbox",
        entity_id=row.id,
        payload={"request_id": str(req.id), "hits": len(hits)},
    )


def _lookup_status(hits: list[dict[str, Any]]) -> str:
    invoices = [h for h in hits if h.get("kind") == "invoice"]
    final = [h for h in invoices if h.get("status") in COPYABLE_STATUSES]
    if len(final) == 1:
        return "found"
    if len(final) > 1:
        return "ambiguous"
    if invoices:
        return "draft_only"
    if hits:
        return "creditnote_only"
    return "not_found"


def selected_hit(req: LexofficeInvoiceCopyRequest) -> dict[str, Any] | None:
    hits = [h for h in req.lookup.get("hits") or [] if h.get("kind") == "invoice"]
    chosen = req.lookup.get("selected_invoice_id")
    if chosen:
        return next((h for h in hits if h.get("lexoffice_invoice_id") == chosen), None)
    final = [h for h in hits if h.get("status") in COPYABLE_STATUSES]
    return final[0] if len(final) == 1 else None


# Verification -------------------------------------------------------------------------------


async def verify(session: AsyncSession, req: LexofficeInvoiceCopyRequest) -> dict[str, Any]:
    hit = selected_hit(req)
    result: dict[str, Any] = {
        "status": "not_found",
        "hint_from_address_match": None,
        "warnings": [],
    }
    req.recipient_contact_id = None
    req.sender_config_id = None
    if hit is None:
        req.verification = result
        return result
    req.sender_config_id = uuid.UUID(hit["config_id"])
    remote_contact = hit.get("address_contact_id")
    if not remote_contact:
        result["status"] = "recipient_unresolved"
        req.verification = result
        return result
    link = await session.scalar(
        select(LexofficeContactLink).where(
            LexofficeContactLink.config_id == req.sender_config_id,
            LexofficeContactLink.lexoffice_contact_id == str(remote_contact),
            LexofficeContactLink.sync_status.in_(list(LINK_STATES)),
        )
    )
    if link is None or link.contact_id is None:
        result["status"] = "recipient_unresolved"
        req.verification = result
        return result
    recipient = await session.get(Contact, link.contact_id)
    if recipient is None or recipient.deleted_at is not None:
        result["status"] = "recipient_unresolved"
        req.verification = result
        return result
    req.recipient_contact_id = recipient.id
    emails = (
        await session.scalars(select(ContactEmail).where(ContactEmail.contact_id == recipient.id))
    ).all()
    primary = next((e.email for e in emails if e.is_primary), None)
    message = await session.get(Message, req.message_id) if req.message_id else None
    if message is not None and message.from_address_norm:
        result["hint_from_address_match"] = message.from_address_norm in {
            e.email.lower() for e in emails
        }
    result["recipient"] = {
        "contact_id": str(recipient.id),
        "display_name": recipient.display_name,
        "primary_email": primary,
    }
    if req.requester_contact_id == recipient.id:
        result["status"] = "verified"
    else:
        result["status"] = "requester_mismatch"
    if primary is None:
        result["warnings"].append(
            "Rechnungsempfänger hat keine bekannte E-Mail, bitte Kontakt ergänzen"
        )
    config = await session.get(LexofficeTenantConfig, req.sender_config_id)
    if config is not None and config.legal_entity_id is not None and config.mailbox_id is None:
        result["warnings"].append("Kein Postfach für diese Gesellschaft hinterlegt")
    result["sending_mailbox_id"] = (
        str(config.mailbox_id)
        if config is not None and config.mailbox_id
        else (str(message.mailbox_id) if message is not None and message.mailbox_id else None)
    )
    req.verification = result
    return result


async def correct(
    session: AsyncSession,
    req: LexofficeInvoiceCopyRequest,
    *,
    invoice_number: str | None,
    requester_contact_id: uuid.UUID | None,
    selected_invoice_id: str | None,
    actor: uuid.UUID | None,
) -> None:
    if req.status in ("fetching", "draft_ready"):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Die Anfrage ist bereits angenommen.")
    if requester_contact_id is not None:
        contact = await session.get(Contact, requester_contact_id)
        if contact is None or contact.deleted_at is not None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        req.requester_contact_id = requester_contact_id
        req.corrected_by = actor
    if selected_invoice_id:
        req.lookup = {**req.lookup, "selected_invoice_id": selected_invoice_id}
    if invoice_number and invoice_number.strip() != req.invoice_number:
        req.invoice_number = invoice_number.strip()[:64]
        req.status = "pending"
        pending: list[str] = []
        for config in await enabled_configs(session, req.tenant_id):
            await services.enqueue(
                session,
                tenant_id=req.tenant_id,
                config_id=config.id,
                kind=LexofficeOutboxKind.LOOKUP_INVOICE,
                idempotency_key=f"invoice-lookup-{req.id}-cfg{config.id}-{req.invoice_number}"[
                    :120
                ],
                target_kind="proposal",
                target_id=req.id,
                payload={"invoice_number": req.invoice_number},
                requested_by=actor,
            )
            pending.append(str(config.id))
        req.lookup = {
            "status": "pending",
            "hits": [],
            "platform_hits": await platform_hits(session, req.tenant_id, req.invoice_number),
            "pending_configs": pending,
        }
    _event(session, req, "proposal_corrected", {}, actor)
    await verify(session, req)


async def accept(
    session: AsyncSession, req: LexofficeInvoiceCopyRequest, actor: uuid.UUID | None
) -> None:
    """Reruns verification; refuses unless verified, found, primary e mail and mailbox known."""
    if req.status in ("fetching", "draft_ready"):
        raise ProblemError(ErrorCodes.CONFLICT, detail="Die Anfrage ist bereits angenommen.")
    result = await verify(session, req)
    hit = selected_hit(req)
    if hit is None or result["status"] != "verified":
        raise ProblemError(ErrorCodes.LEXOFFICE_RECIPIENT_UNVERIFIED)
    if hit.get("status") == "draft" or hit.get("status") not in COPYABLE_STATUSES:
        raise ProblemError(
            ErrorCodes.LEXOFFICE_RECIPIENT_UNVERIFIED,
            detail="Rechnung ist in Lexware Office noch nicht abgeschlossen.",
        )
    if not (result.get("recipient") or {}).get("primary_email"):
        raise ProblemError(
            ErrorCodes.LEXOFFICE_RECIPIENT_UNVERIFIED,
            detail="Rechnungsempfänger hat keine bekannte E-Mail, bitte Kontakt ergänzen",
        )
    if not result.get("sending_mailbox_id"):
        raise ProblemError(
            ErrorCodes.LEXOFFICE_RECIPIENT_UNVERIFIED,
            detail="Kein Postfach für diese Gesellschaft hinterlegt",
        )
    if req.sender_config_id is None:  # pragma: no cover - set by verify with a hit
        raise ProblemError(ErrorCodes.LEXOFFICE_RECIPIENT_UNVERIFIED)
    await services.enqueue(
        session,
        tenant_id=req.tenant_id,
        config_id=req.sender_config_id,
        kind=LexofficeOutboxKind.FETCH_INVOICE_FILE,
        idempotency_key=f"invoice-file-{req.id}",
        target_kind="proposal",
        target_id=req.id,
        payload={"lexoffice_invoice_id": hit["lexoffice_invoice_id"]},
        requested_by=actor,
    )
    req.status = "fetching"
    req.decided_by = actor
    req.decided_at = datetime.now(UTC)
    _event(session, req, "proposal_accepted", {"kind": "invoice_copy"}, actor)


async def reject(
    session: AsyncSession, req: LexofficeInvoiceCopyRequest, reason: str, actor: uuid.UUID | None
) -> None:
    req.status = "rejected"
    req.decided_by = actor
    req.decided_at = datetime.now(UTC)
    req.last_error = reason[:500]
    _event(
        session, req, "proposal_rejected", {"kind": "invoice_copy", "reason": reason[:500]}, actor
    )


# Fetch worker -------------------------------------------------------------------------------


async def _category(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    row = await session.scalar(
        select(DocumentCategory).where(
            DocumentCategory.tenant_id == tenant_id, DocumentCategory.code == CATEGORY_CODE
        )
    )
    if row is None:
        row = DocumentCategory(
            tenant_id=tenant_id, code=CATEGORY_CODE, name="Rechnung (Lexware Office)"
        )
        session.add(row)
        await session.flush()
    return row.id


async def _existing_document(
    session: AsyncSession, tenant_id: uuid.UUID, source_id: str
) -> Document | None:
    row: Document | None = await session.scalar(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.source_system == SOURCE_SYSTEM,
            Document.source_id == source_id,
        )
    )
    return row


async def _store(
    ctx: services.WorkerContext,
    req: LexofficeInvoiceCopyRequest,
    *,
    source_id: str,
    data: bytes,
    mime_type: str,
    title: str,
    filename: str,
    recipient_id: uuid.UUID,
    requested_by: uuid.UUID | None,
) -> Document:
    existing = await _existing_document(ctx.session, ctx.tenant_id, source_id)
    if existing is not None:
        return existing
    check_upload(mime_type, data, MAX_FILE_BYTES)
    document = await store_document(
        ctx.session,
        ctx.blobs,
        tenant_id=ctx.tenant_id,
        data=data,
        title=title,
        filename=filename,
        mime_type=mime_type,
        source=DocumentSource.IMPORT,
        category_id=await _category(ctx.session, ctx.tenant_id),
        links=[
            ("ticket", req.ticket_id, LinkRole.ATTACHMENT),
            ("contact", recipient_id, LinkRole.GENERATED),
        ],
        created_by=requested_by,
        scan_for_malware=True,
        settings=ctx.settings,
    )
    document.source_system = SOURCE_SYSTEM
    document.source_id = source_id
    await ctx.session.flush()
    return document


async def _template_body(session: AsyncSession, tenant_id: uuid.UUID) -> str:
    template = await session.scalar(
        select(TicketReplyTemplate).where(
            TicketReplyTemplate.tenant_id == tenant_id,
            TicketReplyTemplate.topic == TEMPLATE_TOPIC,
            TicketReplyTemplate.active.is_(True),
        )
    )
    return template.body if template is not None else DEFAULT_BODY


@services.handler(LexofficeOutboxKind.FETCH_INVOICE_FILE)
async def fetch_invoice_file(ctx: services.WorkerContext, row: LexofficeOutbox) -> None:
    req = await ctx.session.get(LexofficeInvoiceCopyRequest, row.target_id)
    if req is None or req.status != "fetching":
        services.fail(row, "Anfrage nicht im Status Abruf.")
        return
    result = await verify(ctx.session, req)
    hit = selected_hit(req)
    recipient = result.get("recipient") or {}
    if hit is None or result["status"] != "verified" or not recipient.get("primary_email"):
        req.status = "failed"
        req.last_error = "Rechnungsempfänger nicht bestätigt."
        services.fail(row, req.last_error)
        return
    invoice_id = str(hit["lexoffice_invoice_id"])
    recipient_id = uuid.UUID(recipient["contact_id"])
    try:
        pdf = await ctx.client.download_invoice_file(invoice_id, accept="application/pdf")
    except LexofficeConflictError as exc:
        req.status = "draft_in_lexoffice"
        req.lookup = {**req.lookup, "status": "draft_only"}
        req.last_error = (
            "Rechnung ist in Lexware Office noch nicht abgeschlossen, bitte dort fertigstellen"
        )
        _event(
            ctx.session,
            req,
            "lexoffice_invoice_file_failed",
            {"text": req.last_error, "deeplink": hit.get("deeplink")},
        )
        services.fail(row, req.last_error, exc.status_code)
        return
    except LexofficeNotFoundError as exc:
        req.status = "not_found"
        req.last_error = "Rechnung in Lexware Office nicht gefunden."
        _event(ctx.session, req, "lexoffice_invoice_file_failed", {"text": req.last_error})
        services.fail(row, req.last_error, exc.status_code)
        return
    number = req.invoice_number
    date_text = format_date(hit.get("voucher_date"))
    pdf_doc = await _store(
        ctx,
        req,
        source_id=f"invoice-file:{invoice_id}",
        data=pdf.content,
        mime_type="application/pdf",
        title=f"Rechnung {number} vom {date_text}".strip(),
        filename=pdf.filename or f"Rechnung-{number}.pdf",
        recipient_id=recipient_id,
        requested_by=row.requested_by,
    )
    req.document_id = pdf_doc.id
    attachments = [pdf_doc.id]
    if hit.get("electronic_document_profile") == "XRechnung":
        xml = await ctx.client.download_invoice_file(invoice_id, accept="*/*")
        xml_doc = await _store(
            ctx,
            req,
            source_id=f"invoice-xml:{invoice_id}",
            data=xml.content,
            mime_type="application/xml",
            title=f"E-Rechnung {number} (XML)",
            filename=xml.filename or f"Rechnung-{number}.xml",
            recipient_id=recipient_id,
            requested_by=row.requested_by,
        )
        req.xml_document_id = xml_doc.id
        attachments.append(xml_doc.id)
    ticket = await ctx.session.get(Ticket, req.ticket_id)
    inbound = await ctx.session.get(Message, req.message_id) if req.message_id else None
    mailbox_id = (
        uuid.UUID(result["sending_mailbox_id"]) if result.get("sending_mailbox_id") else None
    )
    mailbox = await ctx.session.get(Mailbox, mailbox_id) if mailbox_id else None
    body = (await _template_body(ctx.session, ctx.tenant_id)).format(
        rechnungsnummer=number,
        rechnungsdatum=date_text,
        betrag=format_amount(hit.get("total_gross")),
        name=recipient.get("display_name") or "",
        signatur=getattr(mailbox, "signature", "") or "",
    )
    subject = f"Ihre Rechnung {number}"
    if ticket is not None:
        subject = subject_with_tnr(subject, ticket.number)
    draft = Message(
        tenant_id=ctx.tenant_id,
        created_by=row.requested_by,
        direction="out",
        status="draft",
        mailbox_id=mailbox_id,
        to_addresses=[recipient["primary_email"]],
        cc_addresses=[],
        subject=subject[:998],
        body=body,
        in_reply_to=inbound.header_message_id if inbound is not None else None,
        thread_id=(inbound.thread_id or inbound.id) if inbound is not None else None,
        contact_id=recipient_id,
        property_id=ticket.property_id if ticket is not None else None,
        ticket_id=req.ticket_id,
        attachment_document_ids=attachments,
        author_approval_required=True,
    )
    ctx.session.add(draft)
    await ctx.session.flush()
    req.reply_message_id = draft.id
    req.status = "draft_ready"
    req.last_error = None
    _event(
        ctx.session, req, "proposal_reply_draft", {"message_id": str(draft.id)}, row.requested_by
    )
    _event(
        ctx.session,
        req,
        "lexoffice_invoice_file_ready",
        {"document_id": str(pdf_doc.id), "message_id": str(draft.id)},
        row.requested_by,
    )
    await services.audit(
        ctx.session,
        ctx.tenant_id,
        "invoice_file_fetched",
        entity_type="lexoffice_outbox",
        entity_id=row.id,
        actor=row.requested_by,
        payload={
            "lexoffice_invoice_id": invoice_id,
            "voucher_number": number,
            "recipient_contact_id": str(recipient_id),
            "target_address": recipient["primary_email"],
            "request_id": str(req.id),
            "message_id": str(draft.id),
        },
    )
    row.detail = {"document_id": str(pdf_doc.id), "message_id": str(draft.id)}


# Recipient lock -----------------------------------------------------------------------------


async def has_lexoffice_attachment(session: AsyncSession, message: Message) -> bool:
    ids = list(message.attachment_document_ids or [])
    if not ids:
        return False
    found = await session.scalar(
        select(Document.id)
        .where(Document.id.in_(ids), Document.source_system == SOURCE_SYSTEM)
        .limit(1)
    )
    return found is not None


async def assert_recipients_locked(
    session: AsyncSession,
    message: Message,
    *,
    to_addresses: list[str] | None = None,
    cc_addresses: list[str] | None = None,
) -> None:
    """A draft carrying a Lexware invoice file may only address the known e mails of its
    contact (MHVP-LEXO-0015). Called from PATCH, submit and approve."""
    if not await has_lexoffice_attachment(session, message):
        return
    if message.contact_id is None:
        raise ProblemError(ErrorCodes.LEXOFFICE_DRAFT_RECIPIENT_LOCKED)
    known = {
        e.lower()
        for e in await session.scalars(
            select(ContactEmail.email).where(ContactEmail.contact_id == message.contact_id)
        )
    }
    to = to_addresses if to_addresses is not None else list(message.to_addresses or [])
    cc = cc_addresses if cc_addresses is not None else list(message.cc_addresses or [])
    for address in [*to, *cc]:
        if str(address).strip().lower() not in known:
            raise ProblemError(ErrorCodes.LEXOFFICE_DRAFT_RECIPIENT_LOCKED)
    if not to:
        raise ProblemError(ErrorCodes.LEXOFFICE_DRAFT_RECIPIENT_LOCKED)
