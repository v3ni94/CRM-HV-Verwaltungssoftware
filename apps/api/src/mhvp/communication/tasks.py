"""Celery jobs: incremental Gmail sync of all enabled mailboxes (M20-01), mail suggestions and
playbook learning (M20 Übernahme aus dem Immoware Hub, queue ``ai``)."""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import shared_task
from sqlalchemy import or_, select
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


GMAIL_SYNC_LOCK_KEY = "mhvp:gmail:sync_all:lock"
GMAIL_SYNC_LOCK_TTL_SECONDS = 600


def _lock_client(settings: Settings) -> Any:
    import redis as redis_lib

    try:
        return redis_lib.Redis.from_url(settings.redis_url.get_secret_value())
    except Exception:  # pragma: no cover - lock is best effort, mailbox row lock remains
        return None


def _try_sync_lock(client: Any) -> bool:
    if client is None:
        return True
    try:
        return bool(client.set(GMAIL_SYNC_LOCK_KEY, "1", nx=True, ex=GMAIL_SYNC_LOCK_TTL_SECONDS))
    except Exception:
        return True


def _release_sync_lock(client: Any) -> None:
    if client is None:
        return
    with contextlib.suppress(Exception):
        client.delete(GMAIL_SYNC_LOCK_KEY)


@shared_task(name="mhvp.communication.gmail_sync_all")
def gmail_sync_all() -> dict[str, int]:
    """Beat job every 60 s. A Redis lock keeps runs from overlapping: a run still busy (slow
    mailbox, Google back off) makes the next tick skip instead of queueing up behind it."""
    settings = get_settings()
    client = _lock_client(settings)
    if not _try_sync_lock(client):
        log.info("gmail sync skipped, previous run still active")
        return {"mailboxes": 0, "created": 0, "failed": 0, "skipped": 1}
    try:
        return asyncio.run(gmail_sync_all_once(settings))
    finally:
        _release_sync_lock(client)


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


ARCHIVE_RETRY_DAYS = 30
ARCHIVE_RETRY_LIMIT = 200
# Archive states the beat job picks up again (``archive_retry_all``); ``scope_missing`` only
# once the mailbox no longer carries ``archive_scope_missing`` (after a reconnect).
ARCHIVE_OPEN_STATUSES = ("pending", "failed", "scope_missing")


def _archive_result(
    message: Any,
    status: str,
    error: str | None = None,
    history_id: int | None = None,
    *,
    gone: bool = False,
) -> None:
    """Records the outcome of one archive attempt on the message (visible in the CRM). A
    success also stores the copy state of the back channel (rule M20-08): ``archived`` by
    the platform with the ``historyId`` of the modify answer; a 404 (``gone``) keeps the
    terminal status ``archived`` with the reason and the state ``deleted``."""
    now = datetime.now(UTC)
    message.archive_status = status
    message.archive_error = error[:1000] if error else None
    message.archive_attempted_at = now
    if status == "archived":
        message.archived_at = now
        message.gmail_expected_state = "archived"
        if gone or message.gmail_state in (None, "inbox"):
            # A copy the user already trashed or archived keeps its own state.
            message.gmail_state = "deleted" if gone else "archived"
            message.gmail_state_by = "platform"
            message.gmail_state_at = now
        if history_id is not None:
            message.archive_history_id = history_id


async def _archive_messages(
    settings: Settings, session: AsyncSession, messages: list[Any]
) -> dict[str, int]:
    """Entfernt fuer jede Gmail-Nachricht die Labels INBOX und UNREAD, sofern das Postfach das
    wuenscht (``archive_on_ticket_done``). Idempotent: bereits archivierte Nachrichten
    (``archived_at``) werden nicht erneut angefasst. Jeder Versuch wird an der Nachricht
    vermerkt (``archive_status``, ``archive_error``, ``archive_attempted_at``). Fehlt dem
    Postfach ``gmail.modify`` (HTTP 403), wird das am Postfach (``archive_scope_missing``) und
    an allen betroffenen Nachrichten (``scope_missing``) vermerkt, ohne weitere Aufrufe.
    Runs inside the caller's tenant transaction; the master key is set for worker processes."""
    from mhvp.communication.gmail import GmailScopeMissingError, make_client, oauth_client
    from mhvp.communication.models import Mailbox

    counts = {"archived": 0, "skipped": 0, "failed": 0}
    if not messages:
        return counts
    _ensure_crypto(settings)
    client_id, client_secret = await oauth_client(session, settings)
    mailboxes: dict[uuid.UUID, Mailbox] = {}
    clients: dict[uuid.UUID, Any] = {}
    try:
        for message in messages:
            if message.archived_at is not None:
                continue  # idempotent: done earlier
            if message.gmail_state in ("archived", "trashed", "spam", "deleted"):
                # Already out of the inbox by a user action (rule M20-08): no Gmail write,
                # the request is fulfilled and the user's state stays.
                _archive_result(message, "archived", "Bereits aus dem Posteingang (Gmail).")
                counts["archived"] += 1
                continue
            if message.mailbox_id is None or message.gmail_message_id is None:
                _archive_result(message, "skipped", "Keine Gmail-Nachricht.")
                counts["skipped"] += 1
                continue
            mailbox = mailboxes.get(message.mailbox_id)
            if mailbox is None:
                mailbox = await session.get(Mailbox, message.mailbox_id)
                if mailbox is not None:
                    mailboxes[message.mailbox_id] = mailbox
            if mailbox is None or mailbox.kind != "gmail":
                _archive_result(message, "skipped", "Kein Gmail-Postfach.")
                counts["skipped"] += 1
                continue
            if not mailbox.archive_on_ticket_done:
                _archive_result(message, "skipped", "Erledigt archiviert ist im Postfach aus.")
                counts["skipped"] += 1
                continue
            if mailbox.archive_scope_missing:
                _archive_result(message, "scope_missing", mailbox.last_error)
                counts["failed"] += 1
                continue
            client = clients.get(mailbox.id)
            if client is None:
                try:
                    client = make_client(client_id, client_secret, mailbox)
                except GmailError as exc:
                    _archive_result(message, "failed", str(exc))
                    counts["failed"] += 1
                    continue
                clients[mailbox.id] = client
            try:
                message.gmail_expected_state = "archived"  # before the Gmail write (M20-08)
                result = await client.archive(message.gmail_message_id)
                if result.status == "gone":
                    _archive_result(
                        message, "archived", "Nachricht in Gmail nicht vorhanden (404)", gone=True
                    )
                else:
                    _archive_result(message, "archived", history_id=result.history_id)
                counts["archived"] += 1
            except GmailScopeMissingError as exc:
                mailbox.archive_scope_missing = True
                mailbox.last_error = str(exc)[:1000]
                _archive_result(message, "scope_missing", str(exc))
                counts["failed"] += 1
                log.warning(
                    "gmail archive scope missing",
                    extra={"mailbox_id": str(mailbox.id), "message_id": str(message.id)},
                )
            except GmailError as exc:
                _archive_result(message, "failed", str(exc))
                counts["failed"] += 1
                log.warning(
                    "gmail archive failed",
                    extra={"message_id": str(message.id), "reason": str(exc)},
                )
    finally:
        for client in clients.values():
            await client.aclose()
    return counts


def _archive_candidates(ticket_id: uuid.UUID) -> Any:
    """Inbound Gmail mails of a ticket plus the inbound mails of the same CRM threads
    (``thread_id``) that were never assigned to a ticket, so a follow up that joined the
    thread later is archived with the ticket (operator 27.09.2026)."""
    from mhvp.communication.models import Message

    thread_ids = select(Message.thread_id).where(
        Message.ticket_id == ticket_id, Message.thread_id.is_not(None)
    )
    root_ids = select(Message.id).where(Message.ticket_id == ticket_id)
    return (
        select(Message)
        .where(
            Message.gmail_message_id.is_not(None),
            Message.direction == "in",
            Message.archived_at.is_(None),
            # A copy the user already archived or trashed (rule M20-08) needs no request.
            or_(Message.gmail_state.is_(None), Message.gmail_state == "inbox"),
            (
                (Message.ticket_id == ticket_id)
                | (
                    Message.ticket_id.is_(None)
                    & (Message.thread_id.in_(thread_ids) | Message.thread_id.in_(root_ids))
                )
            ),
        )
        .with_for_update(skip_locked=True)
    )


async def archive_ticket_messages_once(
    settings: Settings, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> dict[str, int]:
    """ "Erledigt archiviert Mail" (M20-03, operator 25.09.2026): archiviert alle Gmail-
    Eingangsnachrichten des Tickets (und offene Nachrichten derselben Threads)."""
    from mhvp.tickets.models import Ticket

    _ensure_crypto(settings)
    engine = _engine(settings)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            if await session.get(Ticket, ticket_id) is None:
                return {"archived": 0, "skipped": 0, "failed": 0}
            messages = list(await session.scalars(_archive_candidates(ticket_id)))
            return await _archive_messages(settings, session, messages)
    finally:
        await engine.dispose()


async def archive_messages_once(
    settings: Settings, tenant_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> dict[str, int]:
    """Archiviert einzelne, im CRM als erledigt markierte Eingangsnachrichten in Gmail
    (Betreiberauftrag 26.09.2026: Erledigt in der Mailansicht, einzeln oder als Sammelaktion)."""
    from mhvp.communication.models import Message

    _ensure_crypto(settings)
    engine = _engine(settings)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            # Only requested rows (``pending``, rule M20-08): a rolled back savepoint of the
            # back channel leaves no mark, so the queued job must never archive its rows.
            messages = list(
                await session.scalars(
                    select(Message)
                    .where(
                        Message.id.in_(message_ids),
                        Message.gmail_message_id.is_not(None),
                        Message.direction == "in",
                        Message.archived_at.is_(None),
                        Message.archive_status == "pending",
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            return await _archive_messages(settings, session, messages)
    finally:
        await engine.dispose()


async def archive_message_once(
    settings: Settings, tenant_id: uuid.UUID, message_id: uuid.UUID
) -> str:
    """Erledigt archiviert Mail for a single inbound mail set to ``done`` (operator
    26.09.2026). Returns archived, skipped or failed."""
    counts = await archive_messages_once(settings, tenant_id, [message_id])
    if counts["archived"]:
        return "archived"
    if counts["failed"]:
        return "failed"
    return "skipped"


async def archive_retry_once(
    settings: Settings,
    tenant_id: uuid.UUID,
    *,
    days: int = ARCHIVE_RETRY_DAYS,
    limit: int = ARCHIVE_RETRY_LIMIT,
) -> dict[str, int]:
    """Nachholjob (operator 27.09.2026): archiviert alle Eingangsnachrichten der letzten
    ``days`` Tage, die erledigt sind oder deren Archivierung angefordert wurde und die noch
    nicht archiviert sind. Postfächer mit fehlender Berechtigung werden ausgelassen, bis sie
    neu verbunden sind (dann setzt der Rückruf ``archive_scope_missing`` zurück)."""
    from mhvp.communication.models import Mailbox, Message

    _ensure_crypto(settings)
    engine = _engine(settings)
    since = datetime.now(UTC) - timedelta(days=days)
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            messages = list(
                await session.scalars(
                    select(Message)
                    .join(Mailbox, Mailbox.id == Message.mailbox_id)
                    .where(
                        Message.direction == "in",
                        Message.gmail_message_id.is_not(None),
                        Message.archived_at.is_(None),
                        Message.created_at >= since,
                        Mailbox.kind == "gmail",
                        Mailbox.enabled.is_(True),
                        Mailbox.deleted_at.is_(None),
                        Mailbox.archive_on_ticket_done.is_(True),
                        Mailbox.archive_scope_missing.is_(False),
                        (
                            Message.archive_status.in_(ARCHIVE_OPEN_STATUSES)
                            | ((Message.status == "done") & Message.archive_status.is_(None))
                        ),
                    )
                    .order_by(Message.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True, of=Message)
                )
            )
            return await _archive_messages(settings, session, messages)
    finally:
        await engine.dispose()


async def archive_retry_all_once(settings: Settings) -> dict[str, int]:
    _ensure_crypto(settings)
    engine = _engine(settings)
    totals = {"archived": 0, "skipped": 0, "failed": 0, "tenants": 0}
    try:
        factory = create_session_factory(engine)
        tenant_ids = await _active_tenant_ids(factory)
    finally:
        await engine.dispose()
    for tenant_id in tenant_ids:
        try:
            counts = await archive_retry_once(settings, tenant_id)
        except Exception:
            log.exception("archive retry failed", extra={"tenant_id": str(tenant_id)})
            continue
        totals["tenants"] += 1
        for key in ("archived", "skipped", "failed"):
            totals[key] += counts[key]
    return totals


def _run_archive[T](coro_factory: Callable[[], Coroutine[Any, Any, T]], task: Any) -> T:
    """Runs an archive coroutine; transient errors (network, database connection, HTTP 429/5xx)
    are retried three times with exponential backoff (GAL-206); Gmail errors are already
    recorded on the messages."""
    try:
        return asyncio.run(coro_factory())
    except Exception as exc:
        log.exception("archive task failed")
        # GAL-206: backoff only for transient errors, Retry-After honoured.
        from mhvp.core.task_policy import retry_transient

        raise retry_transient(task, exc) from exc


@shared_task(name="mhvp.communication.archive_messages", bind=True)
def archive_messages(self: Any, tenant_id: str, message_ids: list[str]) -> dict[str, int]:
    return _run_archive(
        lambda: archive_messages_once(
            get_settings(), uuid.UUID(tenant_id), [uuid.UUID(m) for m in message_ids]
        ),
        self,
    )


@shared_task(name="mhvp.communication.archive_ticket_messages", bind=True)
def archive_ticket_messages(self: Any, tenant_id: str, ticket_id: str) -> dict[str, int]:
    return _run_archive(
        lambda: archive_ticket_messages_once(
            get_settings(), uuid.UUID(tenant_id), uuid.UUID(ticket_id)
        ),
        self,
    )


@shared_task(name="mhvp.communication.archive_message", bind=True)
def archive_message(self: Any, tenant_id: str, message_id: str) -> str:
    return _run_archive(
        lambda: archive_message_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(message_id)),
        self,
    )


@shared_task(name="mhvp.communication.archive_retry", bind=True)
def archive_retry(self: Any, tenant_id: str) -> dict[str, int]:
    return _run_archive(lambda: archive_retry_once(get_settings(), uuid.UUID(tenant_id)), self)


@shared_task(name="mhvp.communication.archive_retry_all")
def archive_retry_all() -> dict[str, int]:
    return asyncio.run(archive_retry_all_once(get_settings()))


# Gmail back channel (rule M20-08) ------------------------------------------------------------


async def gmail_state_reconcile_once(
    settings: Settings, tenant_id: uuid.UUID, mailbox_id: uuid.UUID
) -> dict[str, Any]:
    """Full reconcile of one mailbox (``gmail_state.reconcile_mailbox``) under the mailbox
    lock, own connection and transaction; a failure is recorded on the mailbox."""
    from mhvp.communication import gmail_state
    from mhvp.communication.gmail import make_client, oauth_client
    from mhvp.communication.models import Mailbox

    _ensure_crypto(settings)
    engine = _engine(settings)
    try:
        factory = create_session_factory(engine)
        try:
            async with tenant_transaction(factory, tenant_id) as session:
                box = await session.get(Mailbox, mailbox_id, with_for_update=True)
                if box is None or box.deleted_at is not None or box.kind != "gmail":
                    return {"status": "skipped"}
                client_id, client_secret = await oauth_client(session, settings)
                client = make_client(client_id, client_secret, box)
                try:
                    return await gmail_state.reconcile_mailbox(session, settings, box, client)
                finally:
                    await client.aclose()
        except Exception as exc:
            log.warning(
                "gmail state reconcile failed",
                extra={"mailbox_id": str(mailbox_id), "reason": str(exc)[:300]},
            )
            async with tenant_transaction(factory, tenant_id) as session:
                box = await session.get(Mailbox, mailbox_id)
                if box is not None:
                    box.gmail_state_reconcile_status = "failed"
                    box.gmail_state_reconcile_counts = {"reason": str(exc)[:300]}
            return {"status": "failed"}
    finally:
        await engine.dispose()


async def gmail_state_reconcile_all_once(settings: Settings) -> dict[str, int]:
    """Hourly reconcile of every enabled Gmail mailbox with the back channel on."""
    _ensure_crypto(settings)
    engine = _engine(settings)
    totals = {"mailboxes": 0, "failed": 0}
    try:
        factory = create_session_factory(engine)
        targets: list[tuple[uuid.UUID, uuid.UUID]] = []
        for tenant_id in await _active_tenant_ids(factory):
            async with tenant_transaction(factory, tenant_id) as session:
                boxes = await enabled_gmail_mailboxes(session)
                targets.extend((tenant_id, m.id) for m in boxes if m.sync_back_enabled)
    finally:
        await engine.dispose()
    for tenant_id, mailbox_id in targets:
        totals["mailboxes"] += 1
        result = await gmail_state_reconcile_once(settings, tenant_id, mailbox_id)
        if result.get("status") == "failed":
            totals["failed"] += 1
    return totals


@shared_task(name="mhvp.communication.gmail_state_reconcile")
def gmail_state_reconcile(tenant_id: str, mailbox_id: str) -> dict[str, Any]:
    return asyncio.run(
        gmail_state_reconcile_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(mailbox_id))
    )


@shared_task(name="mhvp.communication.gmail_state_reconcile_all")
def gmail_state_reconcile_all() -> dict[str, int]:
    return asyncio.run(gmail_state_reconcile_all_once(get_settings()))


async def gmail_restore_inbox_once(
    settings: Settings, tenant_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> dict[str, int]:
    """Puts copies back into the Gmail inbox (P03, P05 with ``gmail_restore_inbox_on_reopen``):
    ``untrash`` for trashed copies, then INBOX. Only rows marked ``restore_pending`` with the
    expected state ``inbox``; the result lands in ``archive_status`` (restored,
    restore_failed) and ``archive_history_id`` so the echo counts as an own action."""
    from mhvp.communication.gmail import GmailScopeMissingError, make_client, oauth_client
    from mhvp.communication.models import Mailbox, Message

    _ensure_crypto(settings)
    engine = _engine(settings)
    counts = {"restored": 0, "failed": 0, "skipped": 0}
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            rows = list(
                await session.scalars(
                    select(Message)
                    .where(
                        Message.id.in_(message_ids),
                        Message.gmail_message_id.is_not(None),
                        Message.archive_status == "restore_pending",
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            if not rows:
                return counts
            client_id, client_secret = await oauth_client(session, settings)
            clients: dict[uuid.UUID, Any] = {}
            try:
                for row in rows:
                    mailbox = await session.get(Mailbox, row.mailbox_id) if row.mailbox_id else None
                    if mailbox is None or mailbox.kind != "gmail":
                        row.archive_status = "restore_failed"
                        row.archive_error = "Kein Gmail-Postfach."
                        counts["skipped"] += 1
                        continue
                    client = clients.get(mailbox.id)
                    if client is None:
                        client = clients[mailbox.id] = make_client(
                            client_id, client_secret, mailbox
                        )
                    now = datetime.now(UTC)
                    row.gmail_expected_state = "inbox"
                    try:
                        history_id = await client.restore_inbox(
                            str(row.gmail_message_id), untrash=row.gmail_state == "trashed"
                        )
                    except GmailScopeMissingError as exc:
                        mailbox.archive_scope_missing = True
                        row.archive_status, row.archive_error = "restore_failed", str(exc)[:1000]
                        counts["failed"] += 1
                        continue
                    except GmailError as exc:
                        row.archive_status, row.archive_error = "restore_failed", str(exc)[:1000]
                        counts["failed"] += 1
                        continue
                    row.archive_attempted_at = now
                    if history_id is None:
                        row.archive_status = "restore_failed"
                        row.archive_error = "Nachricht in Gmail nicht vorhanden (404)"
                        row.gmail_state, row.gmail_state_by, row.gmail_state_at = (
                            "deleted",
                            "platform",
                            now,
                        )
                        counts["failed"] += 1
                        continue
                    row.archive_status, row.archive_error = "restored", None
                    row.archive_history_id = history_id
                    row.gmail_state, row.gmail_state_by, row.gmail_state_at = (
                        "inbox",
                        "platform",
                        now,
                    )
                    counts["restored"] += 1
            finally:
                for client in clients.values():
                    await client.aclose()
    finally:
        await engine.dispose()
    return counts


@shared_task(name="mhvp.communication.gmail_restore_inbox", bind=True)
def gmail_restore_inbox(self: Any, tenant_id: str, message_ids: list[str]) -> dict[str, int]:
    return _run_archive(
        lambda: gmail_restore_inbox_once(
            get_settings(), uuid.UUID(tenant_id), [uuid.UUID(m) for m in message_ids]
        ),
        self,
    )


async def gmail_settle_all_once(settings: Settings) -> dict[str, int]:
    """Beat ``communication-gmail-settle`` (60 s): executes group decisions whose settle
    period ended, per active tenant under RLS (``gmail_done.settle_due``)."""
    from mhvp.communication.gmail_done import settle_due

    _ensure_crypto(settings)
    engine = _engine(settings)
    totals = {"tenants": 0, "checked": 0, "done": 0}
    try:
        factory = create_session_factory(engine)
        for tenant_id in await _active_tenant_ids(factory):
            totals["tenants"] += 1
            try:
                async with tenant_transaction(factory, tenant_id) as session:
                    counts = await settle_due(session, settings)
            except Exception:
                log.exception("gmail settle failed", extra={"tenant_id": str(tenant_id)})
                continue
            totals["checked"] += counts["checked"]
            totals["done"] += counts["done"]
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.communication.gmail_settle_all")
def gmail_settle_all() -> dict[str, int]:
    return asyncio.run(gmail_settle_all_once(get_settings()))


# IMAP-Abruf (M20-01, Entscheidung 5 a) -------------------------------------------------------

IMAP_SYNC_LOCK_KEY = "mhvp:imap:sync_all:lock"


async def imap_sync_mailbox_run(
    settings: Settings,
    factory: Any,
    tenant_id: uuid.UUID,
    mailbox_id: uuid.UUID,
    totals: dict[str, int],
) -> None:
    """One IMAP fetch in its own transaction, then invoice intake and forwarding exactly as
    after a Gmail sync (``sync_mailbox_run``). A failing mailbox never touches another."""
    from mhvp.communication.imap import ImapError, sync_imap_mailbox
    from mhvp.communication.models import Mailbox

    totals["mailboxes"] += 1
    try:
        async with tenant_transaction(factory, tenant_id) as session:
            created_ids: list[uuid.UUID] = []
            counts = await sync_imap_mailbox(session, settings, mailbox_id, created_ids)
            run_ids, actor = await _auto_intake(session, tenant_id, mailbox_id, created_ids)
    except ImapError as exc:
        totals["failed"] += 1
        log.warning("imap sync failed", extra={"mailbox_id": str(mailbox_id), "reason": str(exc)})
        async with tenant_transaction(factory, tenant_id) as session:
            box = await session.get(Mailbox, mailbox_id)
            if box is not None:
                box.last_error = str(exc)[:1000]
        return
    totals["created"] += counts["created"]
    _dispatch_runs(settings, tenant_id, run_ids, actor)
    if counts["created"]:
        await _forward_after_commit(settings, factory, tenant_id, totals)


async def imap_sync_all_once(settings: Settings) -> dict[str, int]:
    from mhvp.communication.imap import enabled_imap_mailboxes

    _ensure_crypto(settings)
    engine = _engine(settings)
    factory = create_session_factory(engine)
    totals = {"mailboxes": 0, "created": 0, "failed": 0}
    try:
        for tenant_id in await _active_tenant_ids(factory):
            async with tenant_transaction(factory, tenant_id) as session:
                boxes = [m.id for m in await enabled_imap_mailboxes(session)]
            for mailbox_id in boxes:
                await imap_sync_mailbox_run(settings, factory, tenant_id, mailbox_id, totals)
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.communication.imap_sync_all")
def imap_sync_all() -> dict[str, int]:
    """Beat job (every 120 s): IMAP mailboxes; a Redis lock keeps runs from overlapping."""
    settings = get_settings()
    client = _lock_client(settings)
    acquired = True
    if client is not None:
        try:
            acquired = bool(
                client.set(IMAP_SYNC_LOCK_KEY, "1", nx=True, ex=GMAIL_SYNC_LOCK_TTL_SECONDS)
            )
        except Exception:
            acquired = True
    if not acquired:
        return {"mailboxes": 0, "created": 0, "failed": 0, "skipped": 1}
    try:
        return asyncio.run(imap_sync_all_once(settings))
    finally:
        if client is not None:
            with contextlib.suppress(Exception):
                client.delete(IMAP_SYNC_LOCK_KEY)
