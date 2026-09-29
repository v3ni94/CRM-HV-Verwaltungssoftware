"""Ad hoc invoice drafts and recurring invoice preparation (rule INT-LEXO-01, section 8).

Drafts: ``POST /v1/invoices`` without ``finalize``; the invoicing legal entity comes from the
invoice kind mapping (broker, consulting, management) or from an explicit config. Recurring
invoices (Dauerrechnungen) for ongoing management already run in Lexware Office; the public
API offers recurring templates read only (``GET /v1/recurring-templates``, verified
29.09.2026), so when a management fee is entered on a property the platform prepares
contact, amount, interval and text with a checklist for the manual creation and stores the
template id a person records afterwards (docs/OPEN_QUESTIONS.md LEXO-07).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.accounting.models import AdminFeeSetting
from mhvp.contacts import services as contact_services
from mhvp.contacts.models import Contact, Party, PartyMember
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.integrations.lexoffice_async import LexofficeRejectedError, LexofficeUnavailableError
from mhvp.integrations.lexoffice_ext import payloads, services
from mhvp.integrations.models import (
    LexofficeContactLink,
    LexofficeInvoiceDraft,
    LexofficeInvoiceKind,
    LexofficeOutbox,
    LexofficeOutboxKind,
    LexofficeRecurringPrep,
    LexofficeTenantConfig,
)
from mhvp.properties.models import Property

INTERVAL_LABEL = {
    "monthly": "monatlich",
    "quarterly": "vierteljährlich",
    "yearly": "jährlich",
    "annual": "jährlich",
}


async def _link_for(
    session: AsyncSession, config: LexofficeTenantConfig, contact_id: uuid.UUID | None
) -> LexofficeContactLink | None:
    if contact_id is None:
        return None
    row: LexofficeContactLink | None = await session.scalar(
        select(LexofficeContactLink).where(
            LexofficeContactLink.config_id == config.id,
            LexofficeContactLink.contact_id == contact_id,
            LexofficeContactLink.sync_status.in_(["linked", "synced"]),
        )
    )
    return row


async def resolve_config(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    config_id: uuid.UUID | None,
    invoice_kind: str | None,
) -> LexofficeTenantConfig:
    if invoice_kind is not None:
        if invoice_kind not in {k.value for k in LexofficeInvoiceKind}:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Unbekannte Rechnungsart.")
        config = await services.config_for_invoice_kind(session, tenant_id, invoice_kind)
        if config_id is not None and config.id != config_id:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Rechnungsart und gewählte Lexware Organisation passen nicht zusammen.",
            )
        return config
    if config_id is None:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Rechnungsart oder Organisation wählen.")
    config = await services.require_config(session, config_id)
    if config.tenant_id != tenant_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return config


async def build(
    session: AsyncSession,
    config: LexofficeTenantConfig,
    *,
    contact_id: uuid.UUID | None,
    voucher_date: date,
    tax_type: str,
    line_items: list[dict[str, Any]],
    shipping: dict[str, Any],
    title: str | None,
    introduction: str | None,
    remark: str | None,
) -> tuple[dict[str, Any], dict[str, Decimal], bool]:
    """Payload, control totals and whether the address is the linked Lexware contact."""
    link = await _link_for(session, config, contact_id)
    address_contact_id = (
        link.lexoffice_contact_id if link is not None and link.customer_number is not None else None
    )
    fallback = None
    if address_contact_id is None and contact_id is not None:
        loaded = await contact_services.load(session, contact_id)
        if loaded is None or loaded.deleted_at is not None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        fallback = payloads.snapshot_from_contact(loaded)
        missing = payloads.validate_snapshot(fallback, {"address"})
        if missing:
            raise ProblemError(
                ErrorCodes.VALIDATION, detail=f"Rechnungsadresse unvollständig: {missing} fehlt."
            )
    try:
        payload = payloads.build_invoice_draft(
            voucher_date=voucher_date,
            tax_type=tax_type,  # type: ignore[arg-type]
            line_items=line_items,
            shipping=shipping,
            address_contact_id=address_contact_id,
            address_fallback=fallback,
            title=title,
            introduction=introduction,
            remark=remark,
        )
    except ValueError as exc:
        raise ProblemError(ErrorCodes.VALIDATION, detail=str(exc)) from exc
    return (
        payloads.json_ready(payload),
        payloads.invoice_totals(tax_type, line_items),
        address_contact_id is not None,
    )


async def create_draft(
    session: AsyncSession,
    config: LexofficeTenantConfig,
    *,
    contact_id: uuid.UUID | None,
    invoice_kind: str | None,
    payload: dict[str, Any],
    actor: uuid.UUID | None,
) -> LexofficeInvoiceDraft:
    if not services.feature_on(config, "invoice_drafts"):
        raise ProblemError(ErrorCodes.LEXOFFICE_FEATURE_DISABLED)
    draft = LexofficeInvoiceDraft(
        tenant_id=config.tenant_id,
        config_id=config.id,
        legal_entity_id=config.legal_entity_id,
        contact_id=contact_id,
        invoice_kind=invoice_kind,
        payload=payload,
        status="pending",
        created_by=actor,
    )
    session.add(draft)
    await session.flush()
    await services.enqueue(
        session,
        tenant_id=config.tenant_id,
        config_id=config.id,
        kind=LexofficeOutboxKind.CREATE_INVOICE_DRAFT,
        idempotency_key=f"invoice-draft-{draft.id}",
        target_kind="invoice_draft",
        target_id=draft.id,
        requested_by=actor,
    )
    return draft


@services.handler(LexofficeOutboxKind.CREATE_INVOICE_DRAFT)
async def create_invoice_draft(ctx: services.WorkerContext, row: LexofficeOutbox) -> None:
    draft = await ctx.session.get(LexofficeInvoiceDraft, row.target_id)
    if draft is None or draft.status == "created":
        services.fail(row, "Entwurf nicht gefunden oder bereits angelegt.")
        return
    try:
        result = await ctx.client.create_invoice(draft.payload)
    except LexofficeRejectedError as exc:
        draft.status = "failed"
        draft.last_error = exc.redacted()
        raise
    except LexofficeUnavailableError as exc:
        if not exc.maybe_processed:
            raise
        adopted = await _find_created(ctx, draft)
        if adopted is None:
            draft.status = "manual_required"
            draft.last_error = "Anlage möglicherweise erfolgt, bitte in Lexware Office prüfen"
            services.fail(row, draft.last_error, exc.status_code)
            return
        result = adopted
    remote_id = str(result.get("id") or "")
    if not remote_id:
        draft.status = "failed"
        draft.last_error = "Antwort ohne ID."
        services.fail(row, draft.last_error)
        return
    draft.lexoffice_invoice_id = remote_id
    draft.lexoffice_version = result.get("version")
    draft.deeplink = services.deeplink(ctx.config, "invoice_edit", remote_id)
    draft.status = "created"
    draft.last_error = None
    row.detail = {"lexoffice_invoice_id": remote_id}
    await services.audit(
        ctx.session,
        ctx.tenant_id,
        "invoice_draft_created",
        entity_type="lexoffice_outbox",
        entity_id=row.id,
        actor=row.requested_by,
        payload={"draft_id": str(draft.id), "lexoffice_invoice_id": remote_id},
    )


async def _find_created(
    ctx: services.WorkerContext, draft: LexofficeInvoiceDraft
) -> dict[str, Any] | None:
    contact_id = (draft.payload.get("address") or {}).get("contactId")
    if not contact_id:
        return None
    page = await ctx.client.list_voucherlist(
        "invoice",
        "draft",
        created_date_from=ctx.now.date().isoformat(),
        contact_id=str(contact_id),
        size=25,
    )
    totals = payloads.invoice_totals(
        str((draft.payload.get("taxConditions") or {}).get("taxType") or "net"),
        [
            {
                "unit_price": (i.get("unitPrice") or {}).get(
                    "netAmount", (i.get("unitPrice") or {}).get("grossAmount", 0)
                ),
                "quantity": i.get("quantity", 1),
                "tax_rate_percent": (i.get("unitPrice") or {}).get("taxRatePercentage", 0),
            }
            for i in draft.payload.get("lineItems") or []
        ],
    )
    for item in page.get("content") or []:
        if (
            isinstance(item, dict)
            and item.get("totalAmount") is not None
            and payloads.money(str(item["totalAmount"])) == totals["gross"]
        ):
            return {"id": item.get("id"), "version": None}
    return None


# Recurring invoice preparation ---------------------------------------------------------------


def _checklist(deeplink_base: str) -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "text": "In Lexware Office unter Verkauf, Dauerrechnungen eine neue Vorlage anlegen.",
            "done": False,
        },
        {
            "step": 2,
            "text": "Kontakt und Rechnungsadresse laut Vorbereitung wählen.",
            "done": False,
        },
        {
            "step": 3,
            "text": "Position, Betrag, Steuerart und Intervall laut Vorbereitung eintragen.",
            "done": False,
        },
        {
            "step": 4,
            "text": "Beginn der Dauerrechnung auf den Verwaltungsbeginn setzen.",
            "done": False,
        },
        {
            "step": 5,
            "text": (
                "Vorlage speichern und die ID aus dem Link "
                f"({deeplink_base}/permalink/recurring-templates/view/...) hier erfassen."
            ),
            "done": False,
        },
    ]


async def _debtor_contact(session: AsyncSession, fee: AdminFeeSetting) -> Contact | None:
    if fee.invoice_debtor_party_id is None:
        return None
    party = await session.get(Party, fee.invoice_debtor_party_id)
    if party is None:
        return None
    member = await session.scalar(
        select(PartyMember)
        .where(PartyMember.party_id == party.id)
        .order_by(PartyMember.created_at)
        .limit(1)
    )
    if member is None:
        return None
    return await session.get(Contact, member.contact_id)


async def prepare_recurring(
    session: AsyncSession, tenant_id: uuid.UUID, fee: AdminFeeSetting, actor: uuid.UUID | None
) -> LexofficeRecurringPrep | None:
    """Idempotent per fee setting; never raises into the fee creation."""
    existing = await session.scalar(
        select(LexofficeRecurringPrep).where(LexofficeRecurringPrep.admin_fee_setting_id == fee.id)
    )
    if existing is not None:
        return existing
    try:
        config: LexofficeTenantConfig | None = await services.config_for_invoice_kind(
            session, tenant_id, LexofficeInvoiceKind.MANAGEMENT.value
        )
    except ProblemError:
        config = None
    prop = await session.get(Property, fee.property_id)
    contact = await _debtor_contact(session, fee)
    amounts = {k: str(payloads.money(v)) for k, v in (fee.amounts_per_unit_type or {}).items()}
    prepared: dict[str, Any] = {
        "property": {
            "id": str(fee.property_id),
            "number": getattr(prop, "number", None),
            "name": getattr(prop, "name", None),
        },
        "contact": (
            {"id": str(contact.id), "display_name": contact.display_name}
            if contact is not None
            else None
        ),
        "amounts_per_unit_type": amounts,
        "vat_percent": str(fee.vat_percent),
        "interval": fee.interval,
        "interval_label": INTERVAL_LABEL.get(fee.interval, fee.interval),
        "start_date": fee.start_date.isoformat(),
        "end_date": fee.end_date.isoformat() if fee.end_date else None,
        "text": (
            f"Verwaltervergütung {getattr(prop, 'name', '') or ''} "
            f"({INTERVAL_LABEL.get(fee.interval, fee.interval)}) ab {fee.start_date:%d.%m.%Y}"
        ).strip(),
        "api_limitation": (
            "Die Lexware Office API stellt Dauerrechnungen nur lesend bereit "
            "(GET /v1/recurring-templates, geprüft am 29.09.2026); die Vorlage wird manuell "
            "in Lexware Office angelegt."
        ),
        "recurring_templates_url": (
            f"{(config.app_base_url if config else 'https://app.lexware.de').rstrip('/')}"
            "/permalink/recurring-templates"
        ),
    }
    if contact is not None and config is not None:
        link = await _link_for(session, config, contact.id)
        prepared["contact"]["lexoffice_contact_id"] = link.lexoffice_contact_id if link else None
        prepared["contact"]["deeplink"] = (
            services.deeplink(config, "contact", link.lexoffice_contact_id)
            if link and link.lexoffice_contact_id
            else None
        )
    row = LexofficeRecurringPrep(
        tenant_id=tenant_id,
        admin_fee_setting_id=fee.id,
        property_id=fee.property_id,
        config_id=config.id if config else None,
        contact_id=contact.id if contact else None,
        prepared=prepared,
        checklist=_checklist(config.app_base_url if config else "https://app.lexware.de"),
        status="open",
        created_by=actor,
    )
    session.add(row)
    await session.flush()
    return row
