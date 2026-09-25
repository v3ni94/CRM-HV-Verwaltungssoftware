"""Celery job: incremental Gmail sync of all enabled mailboxes (M20-01)."""

import asyncio
import logging
import uuid

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.communication import forwarding
from mhvp.communication.gmail import GmailError, enabled_gmail_mailboxes, sync_one
from mhvp.communication.models import Mailbox
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.documents.blobs import BlobStore
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
                    # Automatikmodus (M32): freigegebene Absender werden nach dem Abruf an das
                    # Rechnungsprogramm weitergeleitet; Fehler stoppen den Sync nicht.
                    async with tenant_transaction(factory, tenant_id) as session:
                        box = await session.get(Mailbox, mailbox_id)
                        if box is not None:
                            await forwarding.auto_forward_mailbox(
                                session, settings, BlobStore(settings), box
                            )
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
                        box = await session.get(Mailbox, mailbox_id)
                        if box is not None:
                            box.last_error = str(exc)[:1000]
    finally:
        await engine.dispose()
    return totals


@shared_task(name="mhvp.communication.gmail_sync_all")
def gmail_sync_all() -> dict[str, int]:
    return asyncio.run(gmail_sync_all_once(get_settings()))
