# ruff: noqa: T201 - operator CLI, output goes to the terminal
"""Full inbox backfill of a Gmail mailbox (operator 26.09.2026): every message currently under
the label INBOX is fetched, not only the newest ``gmail_sync_batch`` of the first sync.

Paginated ``messages.list`` (``pageToken``), independent of the history cursor; the Message-ID
deduplication of the intake keeps already known mails out. Progress lives on the mailbox
(``backfill_status``, ``backfill_total``, ``backfill_done``, ``backfill_started_at``,
``backfill_finished_at``); the page token is stored after every page so an aborted run resumes
where it stopped. Ticket assignment and TNR detection run through the same intake as the
regular sync; the AI invoice intake and the invoice forwarding are not triggered for old mail
and nothing is archived retroactively (archiving only follows a closing ticket status).

Entry points: Celery task ``mhvp.communication.gmail_backfill`` (queue ``mail``), endpoint
``POST /mail/mailboxes/{id}/backfill`` and the CLI ``python -m mhvp.communication.backfill``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from mhvp.communication.gmail import GmailError, _ingest_one, make_client, oauth_client
from mhvp.communication.models import Mailbox
from mhvp.core.config import Settings, get_settings
from mhvp.core.db.engine import create_session_factory
from mhvp.core.db.tenancy import platform_transaction, tenant_transaction
from mhvp.documents.blobs import BlobStore
from mhvp.platform.models import Tenant

log = logging.getLogger(__name__)

STATUS_IDLE = "idle"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
ACTIVE_STATUSES = frozenset({STATUS_QUEUED, STATUS_RUNNING})


def request_backfill(mailbox: Mailbox) -> bool:
    """Marks the mailbox for a backfill. Returns False when one is already queued or running.
    A failed run resumes from its stored page token; a finished or new one starts over."""
    if mailbox.backfill_status in ACTIVE_STATUSES:
        return False
    if mailbox.backfill_status != STATUS_FAILED or not mailbox.backfill_page_token:
        mailbox.backfill_page_token = None
        mailbox.backfill_done = 0
        mailbox.backfill_total = None
        mailbox.backfill_started_at = None
    mailbox.backfill_finished_at = None
    mailbox.backfill_status = STATUS_QUEUED
    return True


async def dispatch_backfill(
    settings: Settings, tenant_id: uuid.UUID, mailbox_id: uuid.UUID
) -> None:
    """Starts the backfill job on the ``mail`` queue after the commit of the request; with
    ``ai_inline`` (tests, no worker) the job runs in the calling process instead. A failure to
    enqueue is logged; the mailbox stays ``queued`` and the CLI or a new request restarts it."""
    if settings.ai_inline:
        try:
            await backfill_mailbox_once(settings, tenant_id, mailbox_id)
        except Exception:
            log.exception("gmail backfill failed inline", extra={"mailbox_id": str(mailbox_id)})
        return
    try:
        from mhvp.worker import get_celery

        get_celery().send_task(
            "mhvp.communication.gmail_backfill",
            args=[str(tenant_id), str(mailbox_id)],
            queue="mail",
        )
    except Exception:
        log.exception("gmail backfill not queued", extra={"mailbox_id": str(mailbox_id)})


async def backfill_mailbox_once(
    settings: Settings, tenant_id: uuid.UUID, mailbox_id: uuid.UUID, *, max_pages: int | None = None
) -> dict[str, int]:
    """Runs the backfill of one mailbox page by page, one transaction per page. ``max_pages``
    limits a run (tests, manual chunks); the job then leaves ``queued`` with the page token
    and continues on the next start."""
    from mhvp.core import crypto

    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    counts: dict[str, int] = {"pages": 0, "fetched": 0, "created": 0, "duplicates": 0, "failed": 0}
    try:
        while max_pages is None or counts["pages"] < max_pages:
            async with tenant_transaction(factory, tenant_id) as session:
                more = await _backfill_page(session, settings, mailbox_id, counts)
            if not more:
                break
    finally:
        await engine.dispose()
    return counts


async def _backfill_page(
    session: AsyncSession, settings: Settings, mailbox_id: uuid.UUID, counts: dict[str, int]
) -> bool:
    """Processes one page under the mailbox row lock. Returns True when another page follows."""
    mailbox = await session.get(Mailbox, mailbox_id, with_for_update=True)
    if mailbox is None or mailbox.deleted_at is not None or mailbox.kind != "gmail":
        return False
    if mailbox.backfill_status not in ACTIVE_STATUSES:
        return False
    if not mailbox.enabled or not mailbox.secret:
        mailbox.backfill_status = STATUS_FAILED
        mailbox.last_error = "Vollabruf: Postfach ist inaktiv oder ohne Zugang."
        return False
    client_id, client_secret = await oauth_client(session, settings)
    client = make_client(client_id, client_secret, mailbox)
    now = datetime.now(UTC)
    try:
        if mailbox.backfill_status == STATUS_QUEUED:
            mailbox.backfill_status = STATUS_RUNNING
            if mailbox.backfill_started_at is None:
                mailbox.backfill_started_at = now
        if mailbox.backfill_total is None:
            mailbox.backfill_total = await client.label_total("INBOX")
        ids, next_token = await client.list_inbox_page(
            mailbox.backfill_page_token, settings.gmail_sync_batch
        )
        page: dict[str, Any] = {
            "fetched": 0,
            "created": 0,
            "duplicates": 0,
            "failed": 0,
            "errors": [],
        }
        blobs = BlobStore(settings)
        for mid in ids:
            await _ingest_one(session, blobs, settings, mailbox, client, mid, page, None)
        for key in ("fetched", "created", "duplicates", "failed"):
            counts[key] += int(page[key])
        counts["pages"] += 1
        mailbox.backfill_done += len(ids)
        mailbox.backfill_page_token = next_token
        if page["errors"]:
            first = page["errors"][0]
            mailbox.last_error = f"Vollabruf, Nachricht {first['gmail_id']}: {first['error']}"[
                :1000
            ]
        if next_token is None:
            mailbox.backfill_status = STATUS_DONE
            mailbox.backfill_finished_at = datetime.now(UTC)
            return False
        return True
    except (GmailError, httpx.HTTPError) as exc:
        # Page token stays: the next start resumes here.
        mailbox.backfill_status = STATUS_FAILED
        mailbox.backfill_finished_at = datetime.now(UTC)
        mailbox.last_error = f"Vollabruf: {exc}"[:1000]
        log.warning(
            "gmail backfill failed", extra={"mailbox_id": str(mailbox_id), "reason": str(exc)}
        )
        return False
    finally:
        await client.aclose()


# CLI -------------------------------------------------------------------------------------


async def _cli(args: argparse.Namespace, settings: Settings) -> int:
    from mhvp.core import crypto

    if settings.master_key is not None and not crypto.is_configured():
        crypto.set_master_key(crypto.decode_master_key(settings.master_key.get_secret_value()))
    engine = create_async_engine(
        settings.database_url.get_secret_value(), poolclass=NullPool, hide_parameters=True
    )
    factory = create_session_factory(engine)
    try:
        async with platform_transaction(factory) as session:
            tenant_id = await session.scalar(select(Tenant.id).where(Tenant.slug == args.tenant))
        if tenant_id is None:
            print(f"Mandant {args.tenant!r} nicht gefunden.", file=sys.stderr)
            return 2
        async with tenant_transaction(factory, tenant_id) as session:
            query = select(Mailbox).where(
                Mailbox.kind == "gmail", Mailbox.deleted_at.is_(None), Mailbox.enabled.is_(True)
            )
            if args.mailbox:
                try:
                    query = query.where(Mailbox.id == uuid.UUID(args.mailbox))
                except ValueError:
                    query = query.where(Mailbox.address == args.mailbox.strip().lower())
            boxes = list(await session.scalars(query.with_for_update()))
            if not boxes:
                print("Kein passendes aktives Gmail-Postfach.", file=sys.stderr)
                return 2
            targets: list[tuple[uuid.UUID, str]] = []
            for box in boxes:
                if request_backfill(box):
                    targets.append((box.id, box.address))
                else:
                    print(f"{box.address}: Vollabruf läuft bereits ({box.backfill_status}).")
    finally:
        await engine.dispose()
    for mailbox_id, address in targets:
        if args.inline:
            counts = await backfill_mailbox_once(settings, tenant_id, mailbox_id)
            print(f"{address}: {counts}")
        else:
            await dispatch_backfill(settings, tenant_id, mailbox_id)
            print(f"{address}: Vollabruf in die Warteschlange mail gestellt.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m mhvp.communication.backfill",
        description="Vollabruf des Gmail-Posteingangs (alle Nachrichten unter INBOX).",
    )
    parser.add_argument("--tenant", required=True, help="Mandanten-Slug, z. B. hvm")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="alle aktiven Gmail-Postfächer")
    group.add_argument("--mailbox", help="Postfachadresse oder Postfach-ID")
    parser.add_argument(
        "--inline",
        action="store_true",
        help="im aktuellen Prozess ausführen statt über die Warteschlange mail",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_cli(args, get_settings()))


if __name__ == "__main__":
    sys.exit(main())
