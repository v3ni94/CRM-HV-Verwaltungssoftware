"""Celery jobs: incremental Gmail sync of all enabled mailboxes (M20-01), mail suggestions and
playbook learning (M20 Übernahme aus dem Immoware Hub, queue ``ai``)."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.communication.gmail import GmailError, enabled_gmail_mailboxes, sync_one
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)


def _engine(settings: Settings) -> Any:
    return create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )


def _ensure_crypto(settings: Settings) -> None:
    """Mailbox secrets are encrypted; a worker process sets the master key once."""
    from mhvp.core import crypto

    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))


async def _active_tenant_ids(factory: Any) -> list[uuid.UUID]:
    async with platform_transaction(factory) as session:
        return list(
            await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
        )


async def sync_mailbox_run(
    settings: Settings,
    factory: Any,
    tenant_id: uuid.UUID,
    mailbox_id: uuid.UUID,
    totals: dict[str, int],
    *,
    renew_watch: bool = True,
) -> None:
    """One complete fetch of a mailbox: incremental sync, invoice intake, forwarding, each in
    its own transaction so a failing mailbox never rolls back another. Shared by the beat job
    and the push job. ``renew_watch`` registers or renews the push watch when it is due
    (``gmail.ensure_watch``, no-op without ``MHVP_GMAIL_PUBSUB_TOPIC``)."""
    from mhvp.communication.gmail import ensure_watch, make_client, oauth_client
    from mhvp.communication.models import Mailbox

    totals["mailboxes"] += 1
    run_ids: list[uuid.UUID] = []
    actor: uuid.UUID | None = None
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            created_ids: list[uuid.UUID] = []
            counts = await sync_one(session, settings, mailbox_id, created_ids)
            run_ids, actor = await _auto_intake(session, tenant_id, mailbox_id, created_ids)
        totals["created"] += counts["created"]
        totals["intake_runs"] = totals.get("intake_runs", 0) + len(run_ids)
        _dispatch_runs(settings, tenant_id, run_ids, actor)
        # Rechnungs-Weiterleitung erst nach dem Commit des Abrufs (M13).
        if counts["created"]:
            await _forward_after_commit(settings, factory, tenant_id, totals)
    except GmailError as exc:
        totals["failed"] += 1
        log.warning("gmail sync failed", extra={"mailbox_id": str(mailbox_id), "reason": str(exc)})
        # The error is stored on the mailbox inside sync_mailbox before re-raising,
        # but that transaction rolled back; record it separately.
        async with tenant_transaction(factory, tenant_id) as session:
            box = await session.get(Mailbox, mailbox_id)
            if box is not None:
                box.last_error = str(exc)[:1000]
        return
    if not renew_watch:
        return
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            box = await session.get(Mailbox, mailbox_id, with_for_update=True)
            if box is None or box.deleted_at is not None:
                return
            client_id, client_secret = await oauth_client(session, settings)
            client = make_client(client_id, client_secret, box)
            try:
                if await ensure_watch(settings, box, client):
                    totals["watched"] = totals.get("watched", 0) + 1
            finally:
                await client.aclose()
    except GmailError as exc:
        log.warning("gmail watch failed", extra={"mailbox_id": str(mailbox_id), "reason": str(exc)})


async def gmail_sync_all_once(settings: Settings) -> dict[str, int]:
    _ensure_crypto(settings)
    engine = _engine(settings)
    factory = create_session_factory(engine)
    totals = {"mailboxes": 0, "created": 0, "failed": 0}
    try:
        for tenant_id in await _active_tenant_ids(factory):
            async with tenant_transaction(factory, tenant_id) as session:
                boxes = [m.id for m in await enabled_gmail_mailboxes(session)]
            for mailbox_id in boxes:
                await sync_mailbox_run(settings, factory, tenant_id, mailbox_id, totals)
    finally:
        await engine.dispose()
    return totals


async def gmail_push_sync_once(settings: Settings, address: str, history_id: str) -> dict[str, int]:
    """Push job (operator 26.09.2026): clears the "sync requested" flag of the address, maps
    it to mailboxes across tenants and runs the incremental sync per mailbox. ``history_id``
    is the id Google announced; the sync reads from the mailbox's own cursor, so a burst of
    notifications collapses into one history walk."""
    from redis.asyncio import Redis

    from mhvp.communication.gmail_push import (
        mailboxes_for_address,
        mark_push_received,
        pending_key,
    )

    _ensure_crypto(settings)
    redis = Redis.from_url(settings.redis_url.get_secret_value())
    try:
        await redis.delete(pending_key(address))
    except Exception:
        log.warning("gmail push: pending flag not cleared", extra={"address": address})
    finally:
        await redis.aclose()
    engine = _engine(settings)
    factory = create_session_factory(engine)
    totals = {"mailboxes": 0, "created": 0, "failed": 0}
    try:
        targets = await mailboxes_for_address(factory, address)
        if not targets:
            log.info("gmail push: no mailbox for address", extra={"history_id": history_id})
            return totals
        for tenant_id, mailbox_id in targets:
            await mark_push_received(factory, tenant_id, mailbox_id)
            await sync_mailbox_run(
                settings, factory, tenant_id, mailbox_id, totals, renew_watch=False
            )
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.communication.gmail_push_sync")
def gmail_push_sync(address: str, history_id: str) -> dict[str, int]:
    return asyncio.run(gmail_push_sync_once(get_settings(), address, history_id))


async def gmail_watch_renew_once(settings: Settings, now: datetime | None = None) -> dict[str, int]:
    """Daily renewal of the push watches (Google ends them after seven days): every enabled
    Gmail mailbox whose watch is missing or expires within ``WATCH_RENEW_MARGIN`` is
    registered again. Without a configured topic nothing happens."""
    from mhvp.communication.gmail import ensure_watch, make_client, oauth_client, push_configured
    from mhvp.communication.models import Mailbox

    totals = {"mailboxes": 0, "renewed": 0, "failed": 0}
    if not push_configured(settings):
        return totals
    _ensure_crypto(settings)
    engine = _engine(settings)
    factory = create_session_factory(engine)
    try:
        for tenant_id in await _active_tenant_ids(factory):
            async with tenant_transaction(factory, tenant_id) as session:
                boxes = [m.id for m in await enabled_gmail_mailboxes(session)]
            for mailbox_id in boxes:
                totals["mailboxes"] += 1
                try:
                    async with tenant_transaction(factory, tenant_id) as session:
                        box = await session.get(Mailbox, mailbox_id, with_for_update=True)
                        if box is None:
                            continue
                        client_id, client_secret = await oauth_client(session, settings)
                        client = make_client(client_id, client_secret, box)
                        try:
                            if await ensure_watch(settings, box, client, now):
                                totals["renewed"] += 1
                        finally:
                            await client.aclose()
                except GmailError as exc:
                    totals["failed"] += 1
                    log.warning(
                        "gmail watch renewal failed",
                        extra={"mailbox_id": str(mailbox_id), "reason": str(exc)},
                    )
                    async with tenant_transaction(factory, tenant_id) as session:
                        box = await session.get(Mailbox, mailbox_id)
                        if box is not None:
                            box.last_error = f"Push-Registrierung: {exc}"[:1000]
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.communication.gmail_watch_renew_all")
def gmail_watch_renew_all() -> dict[str, int]:
    return asyncio.run(gmail_watch_renew_once(get_settings()))


@shared_task(name="mhvp.communication.gmail_backfill")
def gmail_backfill(tenant_id: str, mailbox_id: str) -> dict[str, int]:
    """Full inbox backfill of one mailbox (``mhvp.communication.backfill``), queue ``mail``."""
    from mhvp.communication.backfill import backfill_mailbox_once

    return asyncio.run(
        backfill_mailbox_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(mailbox_id))
    )


async def _forward_after_commit(
    settings: Settings, factory: Any, tenant_id: uuid.UUID, totals: dict[str, int]
) -> None:
    """Sendet die im Abruf vorgemerkten Weiterleitungen in eigener Transaktion (Review
    26.09.2026, M13); ein Fehler hier berührt den bereits gespeicherten Abruf nicht."""
    from mhvp.communication.services import forward_queued

    try:
        async with tenant_transaction(factory, tenant_id) as session:
            counts = await forward_queued(session, settings, tenant_id)
        totals["forwarded"] = totals.get("forwarded", 0) + counts["forwarded"]
    except Exception:
        log.exception("invoice forward queue failed", extra={"tenant_id": str(tenant_id)})


async def _auto_intake(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    mailbox_id: uuid.UUID,
    created_ids: list[uuid.UUID],
) -> tuple[list[uuid.UUID], uuid.UUID | None]:
    """M14-05: legt bei aktivem Schalter die extract_invoice-Läufe der neuen Nachrichten an.
    Eigener Savepoint: ein Fehler hier rollt den Mailabruf nie zurück."""
    from mhvp.communication.invoice_intake import intake_for_messages
    from mhvp.communication.models import Mailbox

    if not created_ids:
        return [], None
    box = await session.get(Mailbox, mailbox_id)
    actor = box.created_by if box is not None else None
    try:
        async with session.begin_nested():
            return await intake_for_messages(session, tenant_id, created_ids, actor), actor
    except Exception:
        log.exception("invoice intake auto failed", extra={"mailbox_id": str(mailbox_id)})
        return [], actor


def _dispatch_runs(
    settings: Settings,
    tenant_id: uuid.UUID,
    run_ids: list[uuid.UUID],
    actor: uuid.UUID | None,
) -> None:
    """Stößt die angelegten Läufe nach dem Commit über die bestehende Gateway-Task an."""
    if not run_ids:
        return
    from mhvp.worker import get_celery

    celery = get_celery()
    for run_id in run_ids:
        celery.send_task(
            "mhvp.ai.run",
            args=[str(tenant_id), str(run_id), str(actor) if actor else None],
            queue="io",
        )


@shared_task(name="mhvp.communication.gmail_sync_all")
def gmail_sync_all() -> dict[str, int]:
    return asyncio.run(gmail_sync_all_once(get_settings()))


async def forward_queued_once(settings: Settings, tenant_id: uuid.UUID) -> dict[str, int]:
    """Nachlaufjob der Rechnungs-Weiterleitung (Review 26.09.2026, M13): eigene Verbindung
    und Transaktion, damit der Versand nie innerhalb des Ingests läuft."""
    from mhvp.communication.services import forward_queued

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            return await forward_queued(session, settings, tenant_id)
    finally:
        await engine.dispose()


@shared_task(name="mhvp.communication.forward_queued")
def forward_queued_task(tenant_id: str) -> dict[str, int]:
    return asyncio.run(forward_queued_once(get_settings(), uuid.UUID(tenant_id)))


async def suggest_message_once(
    settings: Settings, tenant_id: uuid.UUID, message_id: uuid.UUID
) -> str:
    """Berechnet den KI-Vorschlag einer Mail und trägt ihn ein. Ein Fehler bleibt lokal
    (``suggestion_status`` wird ``failed``); er verlässt diese Funktion nie als Exception."""
    from mhvp.communication import suggest
    from mhvp.communication.models import Message

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            message = await session.get(Message, message_id, with_for_update=True)
            if message is None:
                return "not_found"
            try:
                result = await suggest.suggest_for_message(session, settings, message)
            except Exception as exc:
                log.warning("mail suggestion failed", extra={"message_id": str(message_id)})
                message.suggestion, message.suggestion_status = {"reason": str(exc)[:500]}, "failed"
                return "failed"
            status = str(result.pop("status"))
            message.suggestion, message.suggestion_status = result, status
            return status
    finally:
        await engine.dispose()


@shared_task(name="mhvp.tickets.propose_contact_change")
def propose_contact_change(tenant_id: str, ticket_id: str, message_id: str) -> str:
    """Stammdatenänderung aus einer Ticket-Mail vorschlagen (mhvp.tickets.proposals)."""
    from mhvp.tickets.proposals import propose_once

    return asyncio.run(
        propose_once(
            get_settings(), uuid.UUID(tenant_id), uuid.UUID(ticket_id), uuid.UUID(message_id)
        )
    )


@shared_task(name="mhvp.communication.suggest_message")
def suggest_message(tenant_id: str, message_id: str) -> str:
    return asyncio.run(
        suggest_message_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(message_id))
    )


async def prepare_mail_once(settings: Settings, tenant_id: uuid.UUID, message_id: uuid.UUID) -> str:
    """Computes the mail preparation (contact/unit/property, scoped document search, reply
    draft, Welle 3 item 14) and stores it under ``message.suggestion["preparation"]``. A failure
    never leaves this function as an exception, matching ``suggest_message_once``."""
    from mhvp.communication import preparation
    from mhvp.communication.models import Message

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            message = await session.get(Message, message_id, with_for_update=True)
            if message is None:
                return "not_found"
            try:
                result = await preparation.prepare_for_message(session, settings, message)
            except Exception as exc:
                log.warning("mail preparation failed", extra={"message_id": str(message_id)})
                result = {"status": "failed", "reason": str(exc)[:500]}
            status = str(result.pop("status"))
            suggestion = dict(message.suggestion or {})
            suggestion["preparation"] = result
            message.suggestion = suggestion
            message.suggestion_status = message.suggestion_status or status
            return status
    finally:
        await engine.dispose()


@shared_task(name="mhvp.communication.prepare_mail")
def prepare_mail(tenant_id: str, message_id: str) -> str:
    return asyncio.run(
        prepare_mail_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(message_id))
    )


async def learn_playbook_once(
    settings: Settings, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> str:
    from mhvp.communication import suggest
    from mhvp.tickets.models import Ticket

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            ticket = await session.get(Ticket, ticket_id)
            if ticket is None:
                return "not_found"
            try:
                draft = await suggest.learn_playbook_from_ticket(session, settings, ticket)
            except Exception:
                log.warning("playbook learning failed", extra={"ticket_id": str(ticket_id)})
                return "failed"
            return "created" if draft is not None else "skipped"
    finally:
        await engine.dispose()


@shared_task(name="mhvp.communication.learn_playbook")
def learn_playbook(tenant_id: str, ticket_id: str) -> str:
    return asyncio.run(
        learn_playbook_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(ticket_id))
    )


async def _archive_messages(
    settings: Settings, session: Any, messages: list[Any]
) -> dict[str, int]:
    """Entfernt fuer jede Gmail-Nachricht das Label INBOX, sofern das Postfach das wuenscht
    (``archive_on_ticket_done``). Fehlt dem Postfach ``gmail.modify``, wird das vermerkt."""
    from mhvp.communication.gmail import GmailScopeMissingError, make_client, oauth_client
    from mhvp.communication.models import Mailbox

    counts = {"archived": 0, "skipped": 0, "failed": 0}
    if not messages:
        return counts
    client_id, client_secret = await oauth_client(session, settings)
    mailboxes: dict[uuid.UUID, Mailbox] = {}
    for message in messages:
        if message.mailbox_id is None or message.gmail_message_id is None:
            counts["skipped"] += 1
            continue
        mailbox = mailboxes.get(message.mailbox_id)
        if mailbox is None:
            mailbox = await session.get(Mailbox, message.mailbox_id)
            if mailbox is not None:
                mailboxes[message.mailbox_id] = mailbox
        if mailbox is None or not mailbox.archive_on_ticket_done:
            counts["skipped"] += 1
            continue
        try:
            client = make_client(client_id, client_secret, mailbox)
        except GmailError:
            counts["skipped"] += 1
            continue
        try:
            await client.archive(message.gmail_message_id)
            counts["archived"] += 1
        except GmailScopeMissingError as exc:
            mailbox.archive_scope_missing = True
            mailbox.last_error = str(exc)[:1000]
            counts["failed"] += 1
        except GmailError as exc:
            counts["failed"] += 1
            log.warning(
                "gmail archive failed",
                extra={"message_id": str(message.id), "reason": str(exc)},
            )
        finally:
            await client.aclose()
    return counts


async def archive_ticket_messages_once(
    settings: Settings, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> dict[str, int]:
    """ "Erledigt archiviert Mail" (M20-03, operator 25.09.2026): archiviert alle Gmail-
    Eingangsnachrichten des Tickets."""
    from mhvp.communication.models import Message
    from mhvp.tickets.models import Ticket

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            if await session.get(Ticket, ticket_id) is None:
                return {"archived": 0, "skipped": 0, "failed": 0}
            messages = list(
                await session.scalars(
                    select(Message).where(
                        Message.ticket_id == ticket_id,
                        Message.gmail_message_id.is_not(None),
                        Message.direction == "in",
                    )
                )
            )
            return await _archive_messages(settings, session, messages)
    finally:
        await engine.dispose()


async def archive_messages_once(
    settings: Settings, tenant_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> dict[str, int]:
    """Archiviert einzelne, im CRM als erledigt markierte Eingangsnachrichten in Gmail
    (Betreiberauftrag 26.09.2026: Erledigt in der Mailansicht, einzeln oder als Sammelaktion)."""
    from mhvp.communication.models import Message

    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            messages = list(
                await session.scalars(
                    select(Message).where(
                        Message.id.in_(message_ids),
                        Message.gmail_message_id.is_not(None),
                        Message.direction == "in",
                    )
                )
            )
            return await _archive_messages(settings, session, messages)
    finally:
        await engine.dispose()


@shared_task(name="mhvp.communication.archive_messages")
def archive_messages(tenant_id: str, message_ids: list[str]) -> dict[str, int]:
    return asyncio.run(
        archive_messages_once(
            get_settings(), uuid.UUID(tenant_id), [uuid.UUID(m) for m in message_ids]
        )
    )


@shared_task(name="mhvp.communication.archive_ticket_messages")
def archive_ticket_messages(tenant_id: str, ticket_id: str) -> dict[str, int]:
    return asyncio.run(
        archive_ticket_messages_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(ticket_id))
    )


async def archive_message_once(
    settings: Settings, tenant_id: uuid.UUID, message_id: uuid.UUID
) -> str:
    """Erledigt archiviert Mail for a single inbound mail set to ``done`` (operator
    26.09.2026): removes the label INBOX at Gmail when the mailbox wants it
    (``archive_on_ticket_done``). Returns archived, skipped or failed; a missing scope is
    recorded on the mailbox like in ``archive_ticket_messages_once``."""
    from mhvp.communication.gmail import GmailScopeMissingError, make_client, oauth_client
    from mhvp.communication.models import Mailbox, Message

    _ensure_crypto(settings)
    engine = _engine(settings)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            message = await session.get(Message, message_id)
            if (
                message is None
                or message.direction != "in"
                or message.gmail_message_id is None
                or message.mailbox_id is None
            ):
                return "skipped"
            mailbox = await session.get(Mailbox, message.mailbox_id)
            if mailbox is None or not mailbox.archive_on_ticket_done or not mailbox.secret:
                return "skipped"
            client_id, client_secret = await oauth_client(session, settings)
            client = make_client(client_id, client_secret, mailbox)
            try:
                await client.archive(message.gmail_message_id)
                return "archived"
            except GmailScopeMissingError as exc:
                mailbox.archive_scope_missing = True
                mailbox.last_error = str(exc)[:1000]
                return "failed"
            except GmailError as exc:
                log.warning(
                    "gmail archive failed",
                    extra={"message_id": str(message_id), "reason": str(exc)},
                )
                return "failed"
            finally:
                await client.aclose()
    finally:
        await engine.dispose()


@shared_task(name="mhvp.communication.archive_message")
def archive_message(tenant_id: str, message_id: str) -> str:
    return asyncio.run(
        archive_message_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(message_id))
    )
