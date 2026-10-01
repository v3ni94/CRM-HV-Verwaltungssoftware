"""Claims adjuster link (rule INT-SDT-01): settings, ticket actions, takeover queue.

Settings need ``tenant_settings:read``/``tenant_settings:update``; ticket actions
``tickets:update``; the takeover decision ``tickets:create``. Ticket actions only queue work
(202); the outbound job talks to the adjuster. Only the connection test calls their API inline.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.core.auth.principal import TenantPrincipal, require_permission, tenant_tx
from mhvp.core.listparams import strict_query
from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.webhooks import UnsafeWebhookTargetError, check_target
from mhvp.integrations.schadenstool import schemas as s
from mhvp.integrations.schadenstool import services as svc
from mhvp.integrations.schadenstool.models import (
    LinkStatus,
    OutboxStatus,
    SchadenstoolItemLink,
    SchadenstoolOutbox,
    SchadenstoolTenantConfig,
    SchadenstoolTicketLink,
)
from mhvp.integrations.schadenstool.status_map import remote_status_label
from mhvp.tickets.models import Ticket, TicketComment

log = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/schadenstool", tags=["Schadenbearbeiter"])

SETTINGS_READ = require_permission("tenant_settings:read")
SETTINGS_WRITE = require_permission("tenant_settings:update")
TICKET_READ = require_permission("tickets:read")
TICKET_UPDATE = require_permission("tickets:update")
TICKET_CREATE = require_permission("tickets:create")


def webhook_path(config: SchadenstoolTenantConfig | None, tenant_id: uuid.UUID) -> str:
    if config is None:
        return ""
    return f"/api/v1/integrations/schadenstool/webhook/{tenant_id}/{config.webhook_path_id}"


def _config_out(config: SchadenstoolTenantConfig | None, tenant_id: uuid.UUID) -> s.ConfigOut:
    if config is None:
        return s.ConfigOut(
            base_url=None,
            enabled=False,
            token_set=False,
            token_last4=None,
            token_invalid=False,
            hmac_secret_set=False,
            webhook_secret_set=False,
            webhook_path="",
            avv_confirmed_on=None,
            avv_confirmed_by=None,
            avv_note=None,
            last_tested_at=None,
            last_test_ok=None,
            last_test_message=None,
            last_pull_at=None,
            last_pull_message=None,
        )
    return s.ConfigOut(
        base_url=config.base_url,
        enabled=config.enabled,
        token_set=bool(config.token),
        token_last4=config.token_last4,
        token_invalid=config.token_invalid,
        hmac_secret_set=bool(config.hmac_secret),
        webhook_secret_set=bool(config.webhook_secret),
        webhook_path=webhook_path(config, tenant_id),
        avv_confirmed_on=config.avv_confirmed_on,
        avv_confirmed_by=config.avv_confirmed_by,
        avv_note=config.avv_note,
        last_tested_at=config.last_tested_at,
        last_test_ok=config.last_test_ok,
        last_test_message=config.last_test_message,
        last_pull_at=config.last_pull_at,
        last_pull_message=config.last_pull_message,
    )


@router.get("/config", summary="Anbindung Schadenbearbeiter lesen")
async def get_config(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_READ)
) -> s.ConfigOut:
    async with tenant_tx(request, principal) as session:
        return _config_out(await svc.get_config(session, principal.tenant_id), principal.tenant_id)


@router.put("/config", summary="Anbindung Schadenbearbeiter einrichten")
async def put_config(
    body: s.ConfigIn, request: Request, principal: TenantPrincipal = Depends(SETTINGS_WRITE)
) -> s.ConfigOut:
    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        config = await svc.get_config(session, principal.tenant_id)
        if config is None:
            config = SchadenstoolTenantConfig(
                tenant_id=principal.tenant_id, webhook_path_id=uuid.uuid4()
            )
            session.add(config)
        if body.base_url is not None:
            url = body.base_url.strip().rstrip("/")
            try:
                check_target(
                    url, allow_private=settings.webhook_allow_private_targets, resolve=False
                )
            except (UnsafeWebhookTargetError, ValueError) as exc:
                raise ProblemError(
                    ErrorCodes.VALIDATION, detail="Die Basisadresse ist nicht zulässig."
                ) from exc
            config.base_url = url or None
        if body.token is not None:
            config.token = body.token.strip()
            config.token_last4 = config.token[-4:]
            config.token_invalid = False
        if body.clear_hmac_secret:
            config.hmac_secret = None
        elif body.hmac_secret is not None:
            config.hmac_secret = body.hmac_secret
        if body.webhook_secret is not None:
            config.webhook_secret = body.webhook_secret
        if body.avv_confirmed_on is not None and body.avv_confirmed_on != config.avv_confirmed_on:
            config.avv_confirmed_on = body.avv_confirmed_on
            config.avv_confirmed_by = principal.user_id
        if body.avv_note is not None:
            config.avv_note = body.avv_note.strip() or None
        if body.enabled:
            if config.avv_confirmed_on is None or config.avv_confirmed_by is None:
                raise ProblemError(ErrorCodes.SCHADENSTOOL_AVV_MISSING)
            if not config.base_url or not config.token or not config.webhook_secret:
                raise ProblemError(
                    ErrorCodes.VALIDATION,
                    detail="Zum Aktivieren sind Basisadresse, Token und Webhook-Geheimnis nötig.",
                )
        was_enabled = config.enabled
        config.enabled = body.enabled
        await session.flush()
        await svc._audit(
            session,
            principal.tenant_id,
            "config_changed",
            entity_id=None,
            actor=principal.user_id,
            payload={"enabled": config.enabled, "was_enabled": was_enabled},
        )
        return _config_out(config, principal.tenant_id)


@router.post("/config/test", summary="Verbindung zum Schadenbearbeiter testen")
async def check_connection(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_WRITE)
) -> s.ConfigOut:
    async with tenant_tx(request, principal) as session:
        config = await svc.get_config(session, principal.tenant_id)
        if config is None or svc.credentials(config) is None:
            raise ProblemError(ErrorCodes.SCHADENSTOOL_NOT_ENABLED)
        ok, message = await svc.check_connection(config)
        config.last_tested_at = datetime.now(UTC)
        config.last_test_ok = ok
        config.last_test_message = message
        if ok:
            config.token_invalid = False
        elif message == "Token ungültig.":
            config.token_invalid = True
        await session.flush()
        return _config_out(config, principal.tenant_id)


async def _ticket(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
    return ticket


@router.get(
    "/tickets/{ticket_id}",
    summary="Austausch mit dem Schadenbearbeiter je Ticket",
    dependencies=[Depends(strict_query)],
)
async def ticket_link(
    ticket_id: uuid.UUID, request: Request, principal: TenantPrincipal = Depends(TICKET_READ)
) -> s.TicketLinkOut:
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        config = await svc.get_config(session, principal.tenant_id)
        enabled = bool(config and config.enabled)
        link = await svc.link_for_ticket(session, ticket_id)
        if link is None:
            return s.TicketLinkOut(
                enabled=enabled, linked=False, token_invalid=bool(config and config.token_invalid)
            )
        outbox = (
            await session.scalars(
                select(SchadenstoolOutbox).where(SchadenstoolOutbox.link_id == link.id)
            )
        ).all()
        by_item = {o.item_link_id: o for o in outbox if o.item_link_id}
        items = (
            await session.scalars(
                select(SchadenstoolItemLink)
                .where(SchadenstoolItemLink.link_id == link.id)
                .order_by(SchadenstoolItemLink.created_at)
            )
        ).all()
        out_items = []
        for item in items:
            row = by_item.get(item.id)
            state = row.status if row is not None else "received"
            out_items.append(
                s.ItemOut(
                    id=item.id,
                    kind=item.kind,
                    direction=item.direction,
                    local_id=item.local_id,
                    remote_id=item.remote_id,
                    author_name=item.author_name,
                    state=state,
                    last_error=row.last_error if row is not None else None,
                    created_at=item.created_at,
                )
            )
        sent_docs = {i.local_id for i in items if i.kind == "attachment"}
        documents = [
            s.DocumentChoiceOut(id=d["id"], filename=d["filename"], sent=d["id"] in sent_docs)
            for d in await svc.ticket_documents(session, ticket)
        ]
        return s.TicketLinkOut(
            documents=documents,
            enabled=enabled,
            linked=True,
            link_id=link.id,
            remote_id=link.remote_id,
            remote_status=link.remote_status,
            remote_status_label=remote_status_label(link.remote_status),
            sync_status=link.sync_status,
            last_synced_at=link.last_synced_at,
            last_error=link.last_error
            or next((o.last_error for o in outbox if o.last_error), None),
            token_invalid=bool(config and config.token_invalid),
            pending=sum(1 for o in outbox if o.status == OutboxStatus.PENDING.value),
            failed=sum(1 for o in outbox if o.status == OutboxStatus.FAILED.value),
            items=out_items,
        )


def _kick(request: Request, tenant_id: uuid.UUID) -> None:
    from mhvp.integrations.schadenstool.tasks import enqueue_process

    enqueue_process(request.app.state.settings, tenant_id)


@router.post(
    "/tickets/{ticket_id}/handover",
    status_code=202,
    summary="Ticket an den Schadenbearbeiter übergeben",
)
async def handover(
    ticket_id: uuid.UUID,
    body: s.HandoverIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKET_UPDATE),
) -> s.QueuedOut:
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        form = {
            "title": body.title,
            "description": body.description,
            "reporter": body.reporter,
            "date": body.damage_date,
            "type": body.damage_type,
            "location": body.damage_location,
        }
        link = await svc.queue_handover(session, ticket, form, principal.user_id)
        link_id = link.id
    _kick(request, principal.tenant_id)
    return s.QueuedOut(queued=True, link_id=link_id)


@router.post(
    "/tickets/{ticket_id}/comments",
    status_code=202,
    summary="Kommentar an den Schadenbearbeiter senden",
)
async def push_comment(
    ticket_id: uuid.UUID,
    body: s.CommentPushIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKET_UPDATE),
) -> s.QueuedOut:
    if (body.comment_id is None) == (body.body is None):
        raise ProblemError(ErrorCodes.VALIDATION, detail="Entweder comment_id oder body angeben.")
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        if body.comment_id is not None:
            comment = await session.get(TicketComment, body.comment_id)
            if comment is None or comment.ticket_id != ticket.id:
                raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        else:
            await svc.require_enabled(session, principal.tenant_id)
            comment = TicketComment(
                tenant_id=principal.tenant_id,
                ticket_id=ticket.id,
                internal=True,
                author_user_id=principal.user_id,
                body=(body.body or "").strip(),
            )
            session.add(comment)
            await session.flush()
        item = await svc.queue_comment(session, ticket, comment, principal.user_id)
        link_id = item.link_id
    _kick(request, principal.tenant_id)
    return s.QueuedOut(queued=True, link_id=link_id)


@router.post(
    "/tickets/{ticket_id}/attachments",
    status_code=202,
    summary="Dokument an den Schadenbearbeiter senden",
)
async def push_attachment(
    ticket_id: uuid.UUID,
    body: s.AttachmentPushIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKET_UPDATE),
) -> s.QueuedOut:
    async with tenant_tx(request, principal) as session:
        ticket = await _ticket(session, ticket_id)
        item = await svc.queue_attachment(session, ticket, body.document_id, principal.user_id)
        link_id = item.link_id
    _kick(request, principal.tenant_id)
    return s.QueuedOut(queued=True, link_id=link_id)


@router.get(
    "/takeover",
    summary="Vorhandene Schadentickets zur Übernahme",
    dependencies=[Depends(strict_query)],
)
async def list_takeover(
    request: Request, principal: TenantPrincipal = Depends(TICKET_CREATE)
) -> list[s.TakeoverOut]:
    from mhvp.properties.models import Property

    async with tenant_tx(request, principal) as session:
        rows = (
            await session.scalars(
                select(SchadenstoolTicketLink)
                .where(SchadenstoolTicketLink.sync_status == LinkStatus.PENDING_TAKEOVER.value)
                .order_by(SchadenstoolTicketLink.remote_updated_at.desc().nulls_last())
                .limit(200)
            )
        ).all()
        prop_ids = {r.proposed_property_id for r in rows if r.proposed_property_id}
        ticket_ids = {r.proposed_ticket_id for r in rows if r.proposed_ticket_id}
        props: dict[uuid.UUID, str] = {}
        if prop_ids:
            for p in (
                await session.execute(
                    select(Property.id, Property.number, Property.name).where(
                        Property.id.in_(prop_ids)
                    )
                )
            ).all():
                props[p.id] = f"{p.number} {p.name}"
        numbers: dict[uuid.UUID, int] = {}
        if ticket_ids:
            for t in (
                await session.execute(
                    select(Ticket.id, Ticket.number).where(Ticket.id.in_(ticket_ids))
                )
            ).all():
                numbers[t.id] = t.number
        return [
            s.TakeoverOut(
                id=r.id,
                remote_id=r.remote_id,
                remote_external_id=r.remote_external_id,
                remote_title=r.remote_title,
                remote_status=r.remote_status,
                remote_status_label=remote_status_label(r.remote_status),
                object_external_id=r.object_external_id,
                remote_updated_at=r.remote_updated_at,
                proposed_property_id=r.proposed_property_id,
                proposed_property_label=props.get(r.proposed_property_id)
                if r.proposed_property_id
                else None,
                proposed_ticket_id=r.proposed_ticket_id,
                proposed_ticket_number=numbers.get(r.proposed_ticket_id)
                if r.proposed_ticket_id
                else None,
            )
            for r in rows
        ]


@router.post("/takeover/{link_id}", summary="Schadenticket übernehmen, verknüpfen oder verwerfen")
async def decide_takeover(
    link_id: uuid.UUID,
    body: s.TakeoverIn,
    request: Request,
    principal: TenantPrincipal = Depends(TICKET_CREATE),
) -> s.TakeoverResultOut:
    from mhvp.documents.blobs import BlobStore

    settings = request.app.state.settings
    async with tenant_tx(request, principal) as session:
        link = await session.get(SchadenstoolTicketLink, link_id)
        if link is None:
            raise ProblemError(ErrorCodes.RESOURCE_NOT_FOUND)
        link = await svc.take_over(
            session,
            link,
            action=body.action,
            actor=principal.user_id,
            ticket_id=body.ticket_id,
            property_id=body.property_id,
            blobs=BlobStore(settings),
            settings=settings,
        )
        return s.TakeoverResultOut(
            id=link.id, sync_status=link.sync_status, ticket_id=link.ticket_id
        )


@router.post("/pull", status_code=202, summary="Abgleich mit dem Schadenbearbeiter anstoßen")
async def request_pull(
    request: Request, principal: TenantPrincipal = Depends(SETTINGS_WRITE)
) -> dict[str, bool]:
    from mhvp.integrations.schadenstool.tasks import enqueue_pull

    async with tenant_tx(request, principal) as session:
        await svc.require_enabled(session, principal.tenant_id)
    enqueue_pull(request.app.state.settings, principal.tenant_id)
    return {"queued": True}
