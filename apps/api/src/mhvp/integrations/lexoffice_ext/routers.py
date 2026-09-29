"""API of the Lexware Office extension (rule INT-LEXO-01), prefix ``/integrations/lexoffice``.

Permissions: configs ``tenant_settings:read`` / ``tenant_settings:update``; links, matching,
decisions, conflicts and remote search ``contacts:update``; contact status ``contacts:read``;
runs ``accounting:read``; invoice drafts and recurring preparations ``accounting:create``;
invoice copies ``tickets:update`` (accept additionally ``communication:update``, link
recipient ``contacts:update``). Every write only queues rows except the connection test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Mailbox
from mhvp.contacts.models import Contact
from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.integrations.lexoffice_async import LexofficeError, LexofficeValidationError
from mhvp.integrations.lexoffice_ext import invoice_copy, invoice_drafts, matching, tasks
from mhvp.integrations.lexoffice_ext import schemas as s
from mhvp.integrations.lexoffice_ext import services as svc
from mhvp.integrations.models import (
    LexofficeContactLink,
    LexofficeInvoiceCopyRequest,
    LexofficeInvoiceDraft,
    LexofficeInvoiceKind,
    LexofficeInvoiceKindMapping,
    LexofficeLinkStatus,
    LexofficeOutbox,
    LexofficeRecurringPrep,
    LexofficeSyncRun,
    LexofficeTenantConfig,
)
from mhvp.properties.models import LegalEntity
from mhvp.tickets.models import Ticket

router = APIRouter(prefix="/integrations/lexoffice", tags=["Schnittstellen"])

SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_WRITE = require_permission("tenant_settings:update")
CONTACTS_READ = require_permission("contacts:read")
CONTACTS_UPDATE = require_permission("contacts:update")
ACCOUNTING_READ = require_permission("accounting:read")
ACCOUNTING_CREATE = require_permission("accounting:create")
TICKETS_UPDATE = require_permission("tickets:update")
COMMUNICATION_UPDATE = require_permission("communication:update")

KIND_LABELS = {
    LexofficeInvoiceKind.BROKER.value: "Maklerrechnungen",
    LexofficeInvoiceKind.CONSULTING.value: "Beratung",
    LexofficeInvoiceKind.MANAGEMENT.value: "Hausverwaltung",
}


def _redis(request: Request) -> Any | None:
    resources = getattr(request.app.state, "resources", None)
    return getattr(resources, "redis", None)


async def _entity_name(session: AsyncSession, entity_id: uuid.UUID | None) -> str | None:
    if entity_id is None:
        return None
    entity = await session.get(LegalEntity, entity_id)
    return entity.name if entity is not None else None


async def _config_out(
    session: AsyncSession, config: LexofficeTenantConfig, message: str | None = None
) -> s.ConfigOut:
    return s.ConfigOut(
        id=config.id,
        legal_entity_id=config.legal_entity_id,
        legal_entity_name=await _entity_name(session, config.legal_entity_id),
        label=config.label,
        base_url=config.base_url,
        app_base_url=config.app_base_url,
        enabled=config.enabled,
        api_key_set=bool(config.api_key),
        api_key_last4=config.api_key_last4,
        token_invalid=config.token_invalid,
        organization_id=config.organization_id,
        organization_name=config.organization_name,
        profile_tax_type=config.profile_tax_type,
        profile_small_business=config.profile_small_business,
        profile_business_features=list(config.profile_business_features or []),
        has_invoicing=svc.has_invoicing(config),
        avv_confirmed_on=config.avv_confirmed_on,
        avv_confirmed_by=config.avv_confirmed_by,
        avv_note=config.avv_note,
        mailbox_id=config.mailbox_id,
        sync_contacts=config.sync_contacts,
        sync_names=config.sync_names,
        invoice_copies=config.invoice_copies,
        invoice_drafts=config.invoice_drafts,
        last_tested_at=config.last_tested_at,
        last_test_ok=config.last_test_ok,
        last_test_message=config.last_test_message,
        message=message,
    )


async def _tenant_config(
    session: AsyncSession, principal: TenantPrincipal, config_id: uuid.UUID
) -> LexofficeTenantConfig:
    config = await svc.get_config(session, config_id)
    if config is None or config.tenant_id != principal.tenant_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return config


async def apply_config(
    session: AsyncSession,
    config: LexofficeTenantConfig,
    body: s.ConfigIn,
    principal: TenantPrincipal,
    settings: Any,
) -> str | None:
    """Section 4.5 rules: key rotation resets the organisation binding and disables until a
    new test succeeds; enabling needs AVV, key, test and a safe base URL."""
    message: str | None = None
    if body.legal_entity_id is not None and body.legal_entity_id != config.legal_entity_id:
        entity = await session.get(LegalEntity, body.legal_entity_id)
        if entity is None or entity.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Gesellschaft nicht gefunden.")
        config.legal_entity_id = body.legal_entity_id
    if body.label is not None:
        config.label = body.label.strip()[:120] or None
    if body.base_url:
        config.base_url = svc.check_base_url(body.base_url, settings)
    if body.clear_api_key:
        config.api_key = None
        config.api_key_last4 = None
        config.enabled = False
    elif body.api_key is not None:
        key = body.api_key.strip()
        config.api_key = key
        config.api_key_last4 = key[-4:]
        config.token_invalid = False
        config.organization_id = None
        config.organization_name = None
        config.profile_tax_type = None
        config.profile_small_business = None
        config.profile_business_features = []
        config.last_test_ok = None
        config.last_test_message = None
        config.enabled = False
        message = "Verbindungstest erforderlich"
        await svc.audit(
            session,
            principal.tenant_id,
            "key_rotated",
            entity_id=config.id,
            actor=principal.user_id,
        )
    if body.clear_mailbox:
        config.mailbox_id = None
    elif body.mailbox_id is not None:
        mailbox = await session.get(Mailbox, body.mailbox_id)
        if mailbox is None or mailbox.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Postfach nicht gefunden.")
        config.mailbox_id = body.mailbox_id
    if body.avv_confirmed_on is not None and body.avv_confirmed_on != config.avv_confirmed_on:
        config.avv_confirmed_on = body.avv_confirmed_on
        config.avv_confirmed_by = principal.user_id
    if body.avv_note is not None:
        config.avv_note = body.avv_note.strip() or None
    config.sync_contacts = body.sync_contacts
    config.sync_names = body.sync_names
    if (body.invoice_copies or body.invoice_drafts) and not svc.has_invoicing(config):
        raise ProblemError(
            ErrorCodes.VALIDATION, detail="Lexware Organisation ohne Rechnungsfunktion"
        )
    config.invoice_copies = body.invoice_copies
    config.invoice_drafts = body.invoice_drafts
    if body.enabled:
        if config.avv_confirmed_on is None or config.avv_confirmed_by is None:
            raise ProblemError(ErrorCodes.LEXOFFICE_AVV_MISSING)
        if not config.api_key:
            raise ProblemError(
                ErrorCodes.VALIDATION,
                detail="Ohne API Schlüssel kann die Anbindung nicht aktiviert werden.",
            )
        if message is not None:
            config.enabled = False  # rotated key: a new test must succeed first
        else:
            if config.last_test_ok is not True or config.token_invalid:
                raise ProblemError(ErrorCodes.LEXOFFICE_CONNECTION_TEST_REQUIRED)
            svc.check_base_url(config.base_url, settings)
            config.enabled = True
    else:
        config.enabled = False
    await session.flush()
    await svc.audit(
        session,
        principal.tenant_id,
        "config_changed",
        entity_id=config.id,
        actor=principal.user_id,
        payload={
            "enabled": config.enabled,
            "sync_contacts": config.sync_contacts,
            "sync_names": config.sync_names,
            "invoice_copies": config.invoice_copies,
            "invoice_drafts": config.invoice_drafts,
        },
    )
    return message


# Configs -----------------------------------------------------------------------------------


@router.get("/configs", summary="Lexware Office Organisationen je Gesellschaft")
async def list_configs(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> list[s.ConfigOut]:
    async with tenant_tx(request, principal) as session:
        return [
            await _config_out(session, c)
            for c in await svc.list_configs(session, principal.tenant_id)
        ]


@router.post("/configs", status_code=201, summary="Lexware Office Organisation anlegen")
async def create_config(
    body: s.ConfigIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS_WRITE)
) -> s.ConfigOut:
    async with tenant_tx(request, principal) as session:
        existing = await session.scalar(
            select(LexofficeTenantConfig).where(
                LexofficeTenantConfig.tenant_id == principal.tenant_id,
                (
                    LexofficeTenantConfig.legal_entity_id == body.legal_entity_id
                    if body.legal_entity_id is not None
                    else LexofficeTenantConfig.legal_entity_id.is_(None)
                ),
            )
        )
        if existing is not None:
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Für diese Gesellschaft gibt es bereits eine Konfiguration.",
            )
        if body.legal_entity_id is not None:
            entity = await session.get(LegalEntity, body.legal_entity_id)
            if entity is None or entity.tenant_id != principal.tenant_id:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Gesellschaft nicht gefunden.")
        # The legal entity is part of the row before the first flush (partial unique indexes).
        config = LexofficeTenantConfig(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            legal_entity_id=body.legal_entity_id,
        )
        session.add(config)
        await session.flush()
        message = await apply_config(session, config, body, principal, request.app.state.settings)
        return await _config_out(session, config, message)


@router.get("/configs/{config_id}", summary="Lexware Office Organisation lesen")
async def get_config(
    config_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> s.ConfigOut:
    async with tenant_tx(request, principal) as session:
        return await _config_out(session, await _tenant_config(session, principal, config_id))


@router.put("/configs/{config_id}", summary="Lexware Office Organisation ändern")
async def put_config(
    config_id: uuid.UUID,
    body: s.ConfigIn,
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_WRITE),
) -> s.ConfigOut:
    async with tenant_tx(request, principal) as session:
        config = await _tenant_config(session, principal, config_id)
        message = await apply_config(session, config, body, principal, request.app.state.settings)
        return await _config_out(session, config, message)


@router.post("/configs/{config_id}/test", summary="Verbindung testen (Organisation prüfen)")
async def check_config_connection(
    config_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(SETTINGS_WRITE)
) -> s.ConfigOut:
    async with tenant_tx(request, principal) as session:
        config = await _tenant_config(session, principal, config_id)
        await svc.check_connection(
            session,
            config,
            request.app.state.settings,
            actor=principal.user_id,
            redis=_redis(request),
        )
        return await _config_out(session, config)


@router.get("/configs/{config_id}/runs", summary="Letzte Läufe")
async def config_runs(
    config_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(ACCOUNTING_READ)
) -> list[s.RunOut]:
    async with tenant_tx(request, principal) as session:
        await _tenant_config(session, principal, config_id)
        rows = await session.scalars(
            select(LexofficeSyncRun)
            .where(LexofficeSyncRun.tenant_id == principal.tenant_id)
            .order_by(LexofficeSyncRun.created_at.desc())
            .limit(50)
        )
        return [s.RunOut.model_validate(r) for r in rows]


@router.get("/legal-entities", summary="Gesellschaften des Mandanten (für die Zuordnung)")
async def legal_entities(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> list[s.LegalEntityOut]:
    async with tenant_tx(request, principal) as session:
        rows = await session.scalars(
            select(LegalEntity)
            .where(LegalEntity.tenant_id == principal.tenant_id, LegalEntity.property_id.is_(None))
            .order_by(LegalEntity.name)
        )
        return [s.LegalEntityOut(id=r.id, kind=str(r.kind.value), name=r.name) for r in rows]


# Invoice kind mapping ------------------------------------------------------------------------


async def _mappings(session: AsyncSession, tenant_id: uuid.UUID) -> list[s.InvoiceKindMappingOut]:
    await svc.ensure_default_mappings(session, tenant_id)
    rows = {
        m.kind: m
        for m in await session.scalars(
            select(LexofficeInvoiceKindMapping).where(
                LexofficeInvoiceKindMapping.tenant_id == tenant_id
            )
        )
    }
    out: list[s.InvoiceKindMappingOut] = []
    for kind in LexofficeInvoiceKind:
        mapping = rows.get(kind.value)
        config_id = None
        if mapping is not None:
            config_id = await session.scalar(
                select(LexofficeTenantConfig.id).where(
                    LexofficeTenantConfig.tenant_id == tenant_id,
                    LexofficeTenantConfig.legal_entity_id == mapping.legal_entity_id,
                )
            )
        out.append(
            s.InvoiceKindMappingOut(
                kind=kind.value,
                label=KIND_LABELS[kind.value],
                legal_entity_id=mapping.legal_entity_id if mapping else None,
                legal_entity_name=await _entity_name(session, mapping.legal_entity_id)
                if mapping
                else None,
                config_id=config_id,
            )
        )
    return out


@router.get("/invoice-kinds", summary="Zuordnung Rechnungsart zu Gesellschaft")
async def list_invoice_kinds(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> list[s.InvoiceKindMappingOut]:
    async with tenant_tx(request, principal) as session:
        return await _mappings(session, principal.tenant_id)


@router.put("/invoice-kinds", summary="Zuordnung Rechnungsart zu Gesellschaft setzen")
async def put_invoice_kinds(
    body: list[s.InvoiceKindMappingIn],
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_WRITE),
) -> list[s.InvoiceKindMappingOut]:
    async with tenant_tx(request, principal) as session:
        for item in body:
            mapping = await session.scalar(
                select(LexofficeInvoiceKindMapping).where(
                    LexofficeInvoiceKindMapping.tenant_id == principal.tenant_id,
                    LexofficeInvoiceKindMapping.kind == item.kind,
                )
            )
            if item.legal_entity_id is None:
                if mapping is not None:
                    await session.delete(mapping)
                continue
            entity = await session.get(LegalEntity, item.legal_entity_id)
            if entity is None or entity.tenant_id != principal.tenant_id:
                raise ProblemError(ErrorCodes.VALIDATION, detail="Gesellschaft nicht gefunden.")
            if mapping is None:
                session.add(
                    LexofficeInvoiceKindMapping(
                        tenant_id=principal.tenant_id,
                        kind=item.kind,
                        legal_entity_id=item.legal_entity_id,
                    )
                )
            else:
                mapping.legal_entity_id = item.legal_entity_id
        await session.flush()
        await svc.audit(
            session,
            principal.tenant_id,
            "config_changed",
            entity_id=None,
            actor=principal.user_id,
            payload={"invoice_kinds": [i.kind for i in body]},
        )
        return await _mappings(session, principal.tenant_id)


# Outbox --------------------------------------------------------------------------------------


@router.get("/outbox", summary="Warteschlange")
async def list_outbox(
    request: Request,
    principal: TenantPrincipal = Depends(SETTINGS_WRITE),
    config_id: uuid.UUID | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> s.Page:
    async with tenant_tx(request, principal) as session:
        query = select(LexofficeOutbox).where(LexofficeOutbox.tenant_id == principal.tenant_id)
        if config_id is not None:
            query = query.where(LexofficeOutbox.config_id == config_id)
        if status:
            query = query.where(LexofficeOutbox.status == status)
        total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = await session.scalars(
            query.order_by(LexofficeOutbox.created_at.desc()).offset((page - 1) * size).limit(size)
        )
        return s.Page(
            items=[s.OutboxOut.model_validate(r) for r in rows], total=total, page=page, size=size
        )


@router.post("/outbox/{row_id}/retry", summary="Eintrag erneut versuchen")
async def retry_outbox(
    row_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(SETTINGS_WRITE)
) -> s.OutboxOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(LexofficeOutbox, row_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        await svc.retry_row(session, row)
        await session.flush()
        tasks.enqueue_process(principal.tenant_id, row.config_id)
        return s.OutboxOut.model_validate(row)


# Contact links -------------------------------------------------------------------------------


@router.post("/configs/{config_id}/contacts/match", status_code=202, summary="Abgleich starten")
async def start_match(
    config_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
    body: s.MatchIn | None = None,
) -> dict[str, Any]:
    async with tenant_tx(request, principal) as session:
        config = await _tenant_config(session, principal, config_id)
        if not svc.feature_on(config, "sync_contacts"):
            raise ProblemError(ErrorCodes.LEXOFFICE_FEATURE_DISABLED)
        run = await matching.start_match_run(session, config, principal.user_id)
        scope = body.scope if body else "customers_and_vendors"
        tasks.enqueue_match(principal.tenant_id, config.id, run.id, scope)
        return {"run_id": run.id, "status": "running"}


async def _link_out(
    session: AsyncSession, link: LexofficeContactLink, config: LexofficeTenantConfig
) -> s.LinkOut:
    contact = await session.get(Contact, link.contact_id) if link.contact_id else None
    version = contact.version if contact is not None else None
    return s.LinkOut(
        id=link.id,
        config_id=link.config_id,
        contact_id=link.contact_id,
        contact_display_name=contact.display_name if contact else None,
        lexoffice_contact_id=link.lexoffice_contact_id,
        lexoffice_version=link.lexoffice_version,
        customer_number=link.customer_number,
        vendor_number=link.vendor_number,
        sync_status=link.sync_status,
        synced_contact_version=link.synced_contact_version,
        contact_version=version,
        diverged=bool(
            version is not None
            and link.synced_contact_version is not None
            and version > link.synced_contact_version
        ),
        remote_display=link.remote_display or {},
        match_reason=link.match_reason,
        match_score=link.match_score,
        candidates=list(link.candidates or []),
        conflict=link.conflict,
        last_synced_at=link.last_synced_at,
        last_error=link.last_error,
        deeplink=(
            svc.deeplink(config, "contact", link.lexoffice_contact_id)
            if link.lexoffice_contact_id
            else None
        ),
    )


@router.get("/configs/{config_id}/contacts/links", summary="Kontaktzuordnungen")
async def list_links(
    config_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
    status: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
) -> s.Page:
    async with tenant_tx(request, principal) as session:
        config = await _tenant_config(session, principal, config_id)
        query = select(LexofficeContactLink).where(LexofficeContactLink.config_id == config.id)
        if status == "diverged":
            query = query.join(Contact, Contact.id == LexofficeContactLink.contact_id).where(
                LexofficeContactLink.synced_contact_version.is_not(None),
                Contact.version > LexofficeContactLink.synced_contact_version,
            )
        elif status:
            query = query.where(LexofficeContactLink.sync_status == status)
        if q:
            pattern = f"%{q.strip()}%"
            query = query.outerjoin(Contact, Contact.id == LexofficeContactLink.contact_id).where(
                or_(
                    Contact.display_name.ilike(pattern),
                    LexofficeContactLink.remote_display["name"].astext.ilike(pattern),
                )
            )
        total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
        rows = await session.scalars(
            query.order_by(LexofficeContactLink.updated_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = [await _link_out(session, r, config) for r in rows]
        return s.Page(items=items, total=total, page=page, size=size)


async def _link(
    session: AsyncSession, principal: TenantPrincipal, config_id: uuid.UUID, link_id: uuid.UUID
) -> tuple[LexofficeTenantConfig, LexofficeContactLink]:
    config = await _tenant_config(session, principal, config_id)
    link = await session.get(LexofficeContactLink, link_id)
    if link is None or link.config_id != config.id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return config, link


@router.post(
    "/configs/{config_id}/contacts/links/{link_id}/decide", summary="Zuordnung entscheiden"
)
async def decide_link(
    config_id: uuid.UUID,
    link_id: uuid.UUID,
    body: s.DecideIn,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
) -> s.LinkOut:
    async with tenant_tx(request, principal) as session:
        config, link = await _link(session, principal, config_id, link_id)
        if body.action == "link":
            await matching.link_existing(
                session,
                link,
                lexoffice_contact_id=body.lexoffice_contact_id,
                contact_id=body.contact_id,
                actor=principal.user_id,
            )
        elif body.action == "create_remote":
            contact_id = body.contact_id or link.contact_id
            if contact_id is None:
                raise ProblemError(ErrorCodes.VALIDATION, detail="CRM Kontakt fehlt.")
            if (
                link.contact_id != contact_id
                and link.sync_status == LexofficeLinkStatus.REMOTE_ONLY.value
            ):
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Zeile ist ein Lexware Kontakt ohne CRM Kontakt."
                )
            link = await matching.create_remote(
                session, config, contact_id, list(body.roles), principal.user_id
            )
        elif body.action == "create_local":
            if link.sync_status != LexofficeLinkStatus.REMOTE_ONLY.value:
                raise ProblemError(
                    ErrorCodes.CONFLICT,
                    detail="Nur für Kontakte, die nur in Lexware Office existieren.",
                )
            contact = await _create_local_contact(session, principal, link, list(body.roles))
            link.contact_id = contact.id
            link.sync_status = LexofficeLinkStatus.PENDING.value
            link.decided_by = principal.user_id
            link.decided_at = datetime.now(UTC)
            await matching._refresh_row(session, link, principal.user_id)
        else:
            if link.sync_status not in matching.DECIDABLE:
                raise ProblemError(
                    ErrorCodes.CONFLICT, detail="Diese Zeile ist bereits entschieden."
                )
            link.sync_status = LexofficeLinkStatus.DISMISSED.value
            link.decided_by = principal.user_id
            link.decided_at = datetime.now(UTC)
        await session.flush()
        await svc.audit(
            session,
            principal.tenant_id,
            "link_decided",
            entity_type="lexoffice_link",
            entity_id=link.id,
            actor=principal.user_id,
            payload={"action": body.action},
        )
        tasks.enqueue_process(principal.tenant_id, config.id)
        return await _link_out(session, link, config)


async def _create_local_contact(
    session: AsyncSession, principal: TenantPrincipal, link: LexofficeContactLink, roles: list[str]
) -> Contact:
    """Person decision: a CRM contact from the remote display only (no bank data, no notes)."""
    from mhvp.contacts import services as contact_services
    from mhvp.contacts.models import ContactKind
    from mhvp.contacts.schemas import ContactIn, EmailIn

    display = link.remote_display or {}
    name = str(display.get("name") or "").strip()
    if not name:
        raise ProblemError(ErrorCodes.VALIDATION, detail="Lexware Kontakt ohne Namen.")
    if display.get("kind") == "company":
        data = ContactIn(kind=ContactKind.COMPANY, company_name=name)
    else:
        parts = name.rsplit(" ", 1)
        data = ContactIn(
            kind=ContactKind.PERSON,
            first_name=parts[0] if len(parts) == 2 else None,
            last_name=parts[-1],
        )
    if display.get("email"):
        data = data.model_copy(
            update={"emails": [EmailIn(email=str(display["email"]), is_primary=True)]}
        )
    contact = Contact(
        tenant_id=principal.tenant_id, created_by=principal.user_id, kind=data.kind, display_name=""
    )
    contact_services.apply_fields(contact, data)
    session.add(contact)
    await session.flush()
    await contact_services.write_children(
        session, principal.tenant_id, contact.id, data, actor_user_id=principal.user_id
    )
    await emit(
        session,
        tenant_id=principal.tenant_id,
        type="contact.created",
        entity_type="contact",
        entity_id=contact.id,
        actor_user_id=principal.user_id,
        payload={"kind": contact.kind.value, "source": "lexoffice"},
    )
    contact.source_system = "lexoffice"
    contact.source_id = (link.lexoffice_contact_id or "")[:64] or None
    await session.flush()
    return contact


@router.post(
    "/configs/{config_id}/contacts/links/{link_id}/retry", summary="Zuordnung erneut abgleichen"
)
async def retry_link(
    config_id: uuid.UUID,
    link_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
) -> s.LinkOut:
    async with tenant_tx(request, principal) as session:
        config, link = await _link(session, principal, config_id, link_id)
        if link.sync_status not in ("error", "manual_required", "remote_missing", "conflict"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Nur fehlerhafte Zuordnungen.")
        link.sync_status = LexofficeLinkStatus.PENDING.value
        link.conflict = None
        await matching._refresh_row(session, link, principal.user_id)
        await session.flush()
        tasks.enqueue_process(principal.tenant_id, config.id)
        return await _link_out(session, link, config)


@router.post("/configs/{config_id}/contacts/links/{link_id}/push", summary="Jetzt abgleichen")
async def push_link(
    config_id: uuid.UUID,
    link_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
) -> s.LinkOut:
    async with tenant_tx(request, principal) as session:
        config, link = await _link(session, principal, config_id, link_id)
        if link.sync_status not in ("linked", "synced", "error"):
            raise ProblemError(ErrorCodes.LEXOFFICE_CONTACT_NOT_LINKED)
        fields = (
            {"name", "address", "email", "phone"}
            if config.sync_names
            else {"address", "email", "phone"}
        )
        await matching.push(session, link, fields=fields, force=False, actor=principal.user_id)
        await session.flush()
        tasks.enqueue_process(principal.tenant_id, config.id)
        return await _link_out(session, link, config)


@router.post(
    "/configs/{config_id}/contacts/links/{link_id}/resolve-conflict", summary="Konflikt auflösen"
)
async def resolve_conflict(
    config_id: uuid.UUID,
    link_id: uuid.UUID,
    body: s.ResolveIn,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
) -> s.LinkOut:
    async with tenant_tx(request, principal) as session:
        config, link = await _link(session, principal, config_id, link_id)
        if link.sync_status != LexofficeLinkStatus.CONFLICT.value or not link.conflict:
            raise ProblemError(ErrorCodes.CONFLICT, detail="Kein offener Konflikt.")
        fields = set(link.conflict.keys())
        if body.resolution == "keep_crm":
            await matching.push(session, link, fields=fields, force=True, actor=principal.user_id)
        else:
            baseline = dict(link.baseline_snapshot or {})
            for field, values in link.conflict.items():
                remote_value = values.get("lexoffice")
                if field == "name" and isinstance(remote_value, dict):
                    baseline.update(remote_value)
                elif field == "address":
                    baseline["billing_address"] = remote_value
                else:
                    baseline[field] = (
                        {"list": None, "value": remote_value}
                        if isinstance(remote_value, str)
                        else remote_value
                    )
            link.baseline_snapshot = baseline
            contact = await session.get(Contact, link.contact_id) if link.contact_id else None
            link.synced_contact_version = (
                contact.version if contact else link.synced_contact_version
            )
            link.sync_status = LexofficeLinkStatus.SYNCED.value
        link.conflict = None
        link.last_error = None
        await session.flush()
        await svc.audit(
            session,
            principal.tenant_id,
            "conflict_resolved",
            entity_type="lexoffice_link",
            entity_id=link.id,
            actor=principal.user_id,
            payload={"resolution": body.resolution, "fields": sorted(fields)},
        )
        tasks.enqueue_process(principal.tenant_id, config.id)
        return await _link_out(session, link, config)


@router.post("/configs/{config_id}/contacts/links/push-batch", summary="Abweichende abgleichen")
async def push_batch(
    config_id: uuid.UUID,
    body: s.PushBatchIn,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
) -> dict[str, int]:
    async with tenant_tx(request, principal) as session:
        config = await _tenant_config(session, principal, config_id)
        links = await session.scalars(
            select(LexofficeContactLink).where(
                LexofficeContactLink.config_id == config.id,
                LexofficeContactLink.contact_id.in_(body.contact_ids),
                LexofficeContactLink.sync_status.in_(["linked", "synced", "error"]),
            )
        )
        fields = (
            {"name", "address", "email", "phone"}
            if config.sync_names
            else {"address", "email", "phone"}
        )
        count = 0
        for link in links:
            await matching.push(session, link, fields=fields, force=False, actor=principal.user_id)
            count += 1
        await session.flush()
        tasks.enqueue_process(principal.tenant_id, config.id)
        return {"queued": count}


@router.get("/configs/{config_id}/contacts/search", summary="Lexware Kontakt suchen")
async def search_remote(
    config_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
    q: str = Query(min_length=3, max_length=120),
) -> list[s.RemoteSearchOut]:
    async with tenant_tx(request, principal) as session:
        config = await _tenant_config(session, principal, config_id)
        if not svc.feature_on(config, "sync_contacts"):
            raise ProblemError(ErrorCodes.LEXOFFICE_FEATURE_DISABLED)
        client = svc.client_for(config, request.app.state.settings, redis=_redis(request))
        try:
            page = (
                await client.list_contacts(email=q)
                if "@" in q
                else await client.list_contacts(name=q)
            )
        except LexofficeValidationError as exc:
            raise ProblemError(ErrorCodes.VALIDATION, detail=exc.message) from exc
        except LexofficeError as exc:
            raise ProblemError(ErrorCodes.LEXOFFICE_UNAVAILABLE, detail=exc.redacted()) from exc
        out: list[s.RemoteSearchOut] = []
        for item in page.get("content") or []:
            if not isinstance(item, dict):
                continue
            remote = matching.remote_from_json(item)
            out.append(
                s.RemoteSearchOut(
                    id=remote.id,
                    display_name=str(remote.display.get("name") or ""),
                    customer_number=remote.customer_number,
                    vendor_number=remote.vendor_number,
                    city=remote.display.get("city"),
                    zip=remote.display.get("zip"),
                    email=remote.display.get("email"),
                )
            )
        return out[:50]


@router.get("/contacts/{contact_id}/lexoffice", summary="Lexware Office Status eines Kontakts")
async def contact_status(
    contact_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(CONTACTS_READ)
) -> list[s.ContactStatusOut]:
    async with tenant_tx(request, principal) as session:
        contact = await session.get(Contact, contact_id)
        if contact is None or contact.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        out: list[s.ContactStatusOut] = []
        for config in await svc.list_configs(session, principal.tenant_id):
            link = await session.scalar(
                select(LexofficeContactLink).where(
                    LexofficeContactLink.config_id == config.id,
                    LexofficeContactLink.contact_id == contact_id,
                )
            )
            out.append(
                s.ContactStatusOut(
                    config_id=config.id,
                    label=config.label or config.organization_name,
                    legal_entity_id=config.legal_entity_id,
                    sync_status=link.sync_status if link else None,
                    last_synced_at=link.last_synced_at if link else None,
                    diverged=bool(
                        link
                        and link.synced_contact_version is not None
                        and contact.version > link.synced_contact_version
                    ),
                    deeplink=(
                        svc.deeplink(config, "contact", link.lexoffice_contact_id)
                        if link and link.lexoffice_contact_id
                        else None
                    ),
                    last_error=link.last_error if link else None,
                    link_id=link.id if link else None,
                )
            )
        return out


# Invoice drafts -------------------------------------------------------------------------------


def _fmt(value: Any) -> str:
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} EUR"


async def _preview(
    session: AsyncSession, principal: TenantPrincipal, body: s.InvoiceDraftIn
) -> tuple[LexofficeTenantConfig, s.InvoiceDraftPreviewOut]:
    config = await invoice_drafts.resolve_config(
        session, principal.tenant_id, config_id=body.config_id, invoice_kind=body.invoice_kind
    )
    payload, totals, from_link = await invoice_drafts.build(
        session,
        config,
        contact_id=body.contact_id,
        voucher_date=body.voucher_date,
        tax_type=body.tax_type,
        line_items=[i.model_dump() for i in body.line_items],
        shipping=body.shipping.model_dump(),
        title=body.title,
        introduction=body.introduction,
        remark=body.remark,
    )
    return config, s.InvoiceDraftPreviewOut(
        config_id=config.id,
        legal_entity_id=config.legal_entity_id,
        legal_entity_name=await _entity_name(session, config.legal_entity_id),
        payload=payload,
        address_from_link=from_link,
        net=_fmt(totals["net"]),
        tax=_fmt(totals["tax"]),
        gross=_fmt(totals["gross"]),
        note="Summen werden von Lexware Office berechnet, Anzeige zur Kontrolle",
    )


@router.post("/invoice-drafts/preview", summary="Rechnungsentwurf vorschauen")
async def preview_draft(
    body: s.InvoiceDraftIn,
    request: Request,
    principal: TenantPrincipal = Depends(ACCOUNTING_CREATE),
) -> s.InvoiceDraftPreviewOut:
    async with tenant_tx(request, principal) as session:
        _, preview = await _preview(session, principal, body)
        return preview


@router.post(
    "/invoice-drafts", status_code=202, summary="Rechnungsentwurf in Lexware Office anlegen"
)
async def create_draft(
    body: s.InvoiceDraftIn,
    request: Request,
    principal: TenantPrincipal = Depends(ACCOUNTING_CREATE),
) -> s.InvoiceDraftOut:
    async with tenant_tx(request, principal) as session:
        config, preview = await _preview(session, principal, body)
        draft = await invoice_drafts.create_draft(
            session,
            config,
            contact_id=body.contact_id,
            invoice_kind=body.invoice_kind,
            payload=preview.payload,
            actor=principal.user_id,
        )
        await session.flush()
        tasks.enqueue_process(principal.tenant_id, config.id)
        return s.InvoiceDraftOut.model_validate(draft)


@router.get("/invoice-drafts", summary="Rechnungsentwürfe")
async def list_drafts(
    request: Request,
    principal: TenantPrincipal = Depends(ACCOUNTING_READ),
    config_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[s.InvoiceDraftOut]:
    async with tenant_tx(request, principal) as session:
        query = select(LexofficeInvoiceDraft).where(
            LexofficeInvoiceDraft.tenant_id == principal.tenant_id
        )
        if config_id is not None:
            query = query.where(LexofficeInvoiceDraft.config_id == config_id)
        if status:
            query = query.where(LexofficeInvoiceDraft.status == status)
        rows = await session.scalars(
            query.order_by(LexofficeInvoiceDraft.created_at.desc()).limit(200)
        )
        return [s.InvoiceDraftOut.model_validate(r) for r in rows]


@router.get("/invoice-drafts/{draft_id}", summary="Rechnungsentwurf lesen")
async def get_draft(
    draft_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(ACCOUNTING_READ)
) -> s.InvoiceDraftOut:
    async with tenant_tx(request, principal) as session:
        draft = await session.get(LexofficeInvoiceDraft, draft_id)
        if draft is None or draft.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        return s.InvoiceDraftOut.model_validate(draft)


# Recurring preparations -----------------------------------------------------------------------


def _prep_out(
    row: LexofficeRecurringPrep, config: LexofficeTenantConfig | None
) -> s.RecurringPrepOut:
    out = s.RecurringPrepOut.model_validate(row)
    if row.lexoffice_template_id and config is not None:
        out.deeplink = svc.deeplink(config, "recurring", row.lexoffice_template_id)
    return out


@router.get("/recurring-preps", summary="Vorbereitete Dauerrechnungen")
async def list_recurring(
    request: Request,
    principal: TenantPrincipal = Depends(ACCOUNTING_READ),
    status: str | None = None,
) -> list[s.RecurringPrepOut]:
    async with tenant_tx(request, principal) as session:
        query = select(LexofficeRecurringPrep).where(
            LexofficeRecurringPrep.tenant_id == principal.tenant_id
        )
        if status:
            query = query.where(LexofficeRecurringPrep.status == status)
        rows = (
            await session.scalars(
                query.order_by(LexofficeRecurringPrep.created_at.desc()).limit(200)
            )
        ).all()
        out: list[s.RecurringPrepOut] = []
        for row in rows:
            config = (
                await session.get(LexofficeTenantConfig, row.config_id) if row.config_id else None
            )
            out.append(_prep_out(row, config))
        return out


@router.post("/recurring-preps/{prep_id}/done", summary="Dauerrechnung in Lexware Office angelegt")
async def recurring_done(
    prep_id: uuid.UUID,
    body: s.RecurringDoneIn,
    request: Request,
    principal: TenantPrincipal = Depends(ACCOUNTING_CREATE),
) -> s.RecurringPrepOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(LexofficeRecurringPrep, prep_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.status = "done"
        row.lexoffice_template_id = body.lexoffice_template_id.strip()
        row.done_by = principal.user_id
        row.done_at = datetime.now(UTC)
        row.checklist = [{**item, "done": True} for item in row.checklist]
        await session.flush()
        config = await session.get(LexofficeTenantConfig, row.config_id) if row.config_id else None
        return _prep_out(row, config)


@router.post("/recurring-preps/{prep_id}/dismiss", summary="Vorbereitung verwerfen")
async def recurring_dismiss(
    prep_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(ACCOUNTING_CREATE)
) -> s.RecurringPrepOut:
    async with tenant_tx(request, principal) as session:
        row = await session.get(LexofficeRecurringPrep, prep_id)
        if row is None or row.tenant_id != principal.tenant_id:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row.status = "dismissed"
        row.done_by = principal.user_id
        row.done_at = datetime.now(UTC)
        await session.flush()
        return _prep_out(row, None)


# Invoice copies ------------------------------------------------------------------------------


async def _ticket(
    session: AsyncSession, principal: TenantPrincipal, ticket_id: uuid.UUID
) -> Ticket:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None or ticket.tenant_id != principal.tenant_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return ticket


async def _request(
    session: AsyncSession, principal: TenantPrincipal, request_id: uuid.UUID
) -> LexofficeInvoiceCopyRequest:
    row = await session.get(LexofficeInvoiceCopyRequest, request_id)
    if row is None or row.tenant_id != principal.tenant_id:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return row


@router.get("/tickets/{ticket_id}/invoice-copies", summary="Rechnungskopie Anfragen eines Tickets")
async def list_invoice_copies(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(TICKETS_UPDATE)
) -> list[s.InvoiceCopyOut]:
    async with tenant_tx(request, principal) as session:
        await _ticket(session, principal, ticket_id)
        rows = await session.scalars(
            select(LexofficeInvoiceCopyRequest)
            .where(LexofficeInvoiceCopyRequest.ticket_id == ticket_id)
            .order_by(LexofficeInvoiceCopyRequest.created_at.desc())
        )
        return [s.InvoiceCopyOut.model_validate(r) for r in rows]


@router.post(
    "/tickets/{ticket_id}/invoice-copies", status_code=201, summary="Rechnungskopie anfordern"
)
async def create_invoice_copy(
    ticket_id: uuid.UUID,
    body: s.InvoiceCopyIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKETS_UPDATE),
) -> s.InvoiceCopyOut:
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, principal, ticket_id)
        message = None
        if body.message_id is not None:
            from mhvp.communication.models import Message

            message = await session.get(Message, body.message_id)
            if (
                message is None
                or message.tenant_id != principal.tenant_id
                or message.ticket_id != ticket.id
            ):
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        row = await invoice_copy.create_request(
            session,
            principal.tenant_id,
            ticket,
            body.invoice_number,
            message=message,
            actor=principal.user_id,
        )
        for config_id in {uuid.UUID(c) for c in row.lookup.get("pending_configs") or []}:
            tasks.enqueue_process(principal.tenant_id, config_id)
        return s.InvoiceCopyOut.model_validate(row)


@router.post(
    "/invoice-copies/{request_id}/correct", summary="Rechnungsnummer oder Anfragenden korrigieren"
)
async def correct_invoice_copy(
    request_id: uuid.UUID,
    body: s.InvoiceCopyCorrectIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKETS_UPDATE),
) -> s.InvoiceCopyOut:
    async with tenant_tx(request, principal) as session:
        row = await _request(session, principal, request_id)
        await invoice_copy.correct(
            session,
            row,
            invoice_number=body.invoice_number,
            requester_contact_id=body.requester_contact_id,
            selected_invoice_id=body.selected_invoice_id,
            actor=principal.user_id,
        )
        await session.flush()
        for config_id in {uuid.UUID(c) for c in row.lookup.get("pending_configs") or []}:
            tasks.enqueue_process(principal.tenant_id, config_id)
        return s.InvoiceCopyOut.model_validate(row)


@router.post("/invoice-copies/{request_id}/link-recipient", summary="Rechnungsempfänger zuordnen")
async def link_recipient(
    request_id: uuid.UUID,
    body: s.LinkRecipientIn,
    request: Request,
    principal: TenantPrincipal = Depends(CONTACTS_UPDATE),
) -> s.InvoiceCopyOut:
    async with tenant_tx(request, principal) as session:
        row = await _request(session, principal, request_id)
        hit = invoice_copy.selected_hit(row)
        if hit is None or not hit.get("address_contact_id"):
            raise ProblemError(ErrorCodes.CONFLICT, detail="Kein Lexware Kontakt an der Rechnung.")
        config = await _tenant_config(session, principal, uuid.UUID(hit["config_id"]))
        remote_id = str(hit["address_contact_id"])
        link = await session.scalar(
            select(LexofficeContactLink).where(
                LexofficeContactLink.config_id == config.id,
                LexofficeContactLink.lexoffice_contact_id == remote_id,
            )
        )
        if (
            link is not None
            and link.contact_id not in (None, body.contact_id)
            and link.sync_status in matching.UNTOUCHED
        ):
            raise ProblemError(
                ErrorCodes.CONFLICT,
                detail="Lexware Kontakt ist bereits mit einem anderen Kontakt verknüpft.",
            )
        if link is None:
            link = LexofficeContactLink(
                tenant_id=principal.tenant_id,
                config_id=config.id,
                sync_status=LexofficeLinkStatus.PROPOSED.value,
                lexoffice_contact_id=remote_id,
                proposed_lexoffice_contact_id=remote_id,
            )
            session.add(link)
            await session.flush()
        if link.sync_status not in matching.UNTOUCHED:
            await matching.link_existing(
                session,
                link,
                lexoffice_contact_id=remote_id,
                contact_id=body.contact_id,
                actor=principal.user_id,
            )
        await invoice_copy.verify(session, row)
        await session.flush()
        tasks.enqueue_process(principal.tenant_id, config.id)
        return s.InvoiceCopyOut.model_validate(row)


@router.post(
    "/invoice-copies/{request_id}/accept",
    status_code=202,
    summary="PDF abrufen und Antwortentwurf erstellen",
)
async def accept_invoice_copy(
    request_id: uuid.UUID,
    request: Request,
    principal: TenantPrincipal = Depends(TICKETS_UPDATE),
    _communication: TenantPrincipal = Depends(COMMUNICATION_UPDATE),
) -> s.InvoiceCopyOut:
    async with tenant_tx(request, principal) as session:
        row = await _request(session, principal, request_id)
        await invoice_copy.accept(session, row, principal.user_id)
        await session.flush()
        if row.sender_config_id is not None:
            tasks.enqueue_process(principal.tenant_id, row.sender_config_id)
        return s.InvoiceCopyOut.model_validate(row)


@router.post("/invoice-copies/{request_id}/reject", summary="Anfrage ablehnen")
async def reject_invoice_copy(
    request_id: uuid.UUID,
    body: s.InvoiceCopyRejectIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKETS_UPDATE),
) -> s.InvoiceCopyOut:
    async with tenant_tx(request, principal) as session:
        row = await _request(session, principal, request_id)
        await invoice_copy.reject(session, row, body.reason, principal.user_id)
        await session.flush()
        return s.InvoiceCopyOut.model_validate(row)
