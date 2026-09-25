"""Celery jobs: incremental Gmail sync of all enabled mailboxes (M20-01), mail suggestions and
playbook learning (M20 Übernahme aus dem Immoware Hub, queue ``ai``)."""

import asyncio
import logging
import uuid

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.communication.gmail import GmailError, enabled_gmail_mailboxes, sync_one
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.platform.models import Tenant, TenantStatus

log = logging.getLogger(__name__)


async def gmail_sync_all_once(settings: Settings) -> dict[str, int]:
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    totals = {"mailboxes": 0, "created": 0, "failed": 0}
    try:
        async with platform_transaction(factory) as session:
            tenant_ids: list[uuid.UUID] = list(
                await session.scalars(select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            )
        for tenant_id in tenant_ids:
            async with tenant_transaction(factory, tenant_id) as session:
                boxes = [m.id for m in await enabled_gmail_mailboxes(session)]
            for mailbox_id in boxes:
                totals["mailboxes"] += 1
                # One transaction per mailbox: a failing mailbox never rolls back another.
                try:
                    async with tenant_transaction(factory, tenant_id) as session:
                        counts = await sync_one(session, settings, mailbox_id)
                    totals["created"] += counts["created"]
                except GmailError as exc:
                    totals["failed"] += 1
                    log.warning(
                        "gmail sync failed",
                        extra={"mailbox_id": str(mailbox_id), "reason": str(exc)},
                    )
                    # The error is stored on the mailbox inside sync_mailbox before re-raising,
                    # but that transaction rolled back; record it separately.
                    async with tenant_transaction(factory, tenant_id) as session:
                        from mhvp.communication.models import Mailbox

                        box = await session.get(Mailbox, mailbox_id)
                        if box is not None:
                            box.last_error = str(exc)[:1000]
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.communication.gmail_sync_all")
def gmail_sync_all() -> dict[str, int]:
    return asyncio.run(gmail_sync_all_once(get_settings()))


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


@shared_task(name="mhvp.communication.suggest_message")
def suggest_message(tenant_id: str, message_id: str) -> str:
    return asyncio.run(
        suggest_message_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(message_id))
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


async def archive_ticket_messages_once(
    settings: Settings, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> dict[str, int]:
    """ "Erledigt archiviert Mail" (M20-03, operator 25.09.2026): entfernt für jede Gmail-Nachricht
    des Tickets das Label INBOX, sofern das jeweilige Postfach das wünscht. Fehlt dem Postfach die
    Berechtigung ``gmail.modify`` (ältere Verbindung), wird das auf dem Postfach vermerkt statt
    den Job scheitern zu lassen."""
    from mhvp.communication.gmail import GmailScopeMissingError, make_client, oauth_client
    from mhvp.communication.models import Mailbox, Message
    from mhvp.tickets.models import Ticket

    counts = {"archived": 0, "skipped": 0, "failed": 0}
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    try:
        factory = create_session_factory(engine)
        async with tenant_transaction(factory, tenant_id) as session:
            ticket = await session.get(Ticket, ticket_id)
            if ticket is None:
                return counts
            messages = list(
                await session.scalars(
                    select(Message).where(
                        Message.ticket_id == ticket_id,
                        Message.gmail_message_id.is_not(None),
                        Message.direction == "in",
                    )
                )
            )
            if not messages:
                return counts
            client_id, client_secret = await oauth_client(session, settings)
            mailboxes: dict[uuid.UUID, Mailbox] = {}
            for message in messages:
                if message.mailbox_id is None:
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
                    if message.gmail_message_id is None:
                        counts["skipped"] += 1
                        continue
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
    finally:
        await engine.dispose()
    return counts


@shared_task(name="mhvp.communication.archive_ticket_messages")
def archive_ticket_messages(tenant_id: str, ticket_id: str) -> dict[str, int]:
    return asyncio.run(
        archive_ticket_messages_once(get_settings(), uuid.UUID(tenant_id), uuid.UUID(ticket_id))
    )
