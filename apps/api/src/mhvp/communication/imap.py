"""IMAP fetch for mailboxes of ``kind == "imap"`` (M20-01, decision 5 a).

Same pipeline as the Gmail sync: every mail goes through ``services.ingest_raw`` (raw .eml as
document, attachments, contact/property assignment, duplicate groups via Message-ID and
content, ticket and SLA clock), each inside its own savepoint so one broken mail never rolls
back the batch. Access data are the mailbox's ``username`` and the encrypted ``secret`` (the
same fields the SMTP send uses); the secret never reaches logs or errors.

Cursor: ``Mailbox.last_uid`` (highest UID stored) together with ``imap_uidvalidity``. When the
server reports another UIDVALIDITY the UIDs are no longer comparable; the cursor restarts
and duplicates are caught by the duplicate check (no second row per mailbox). The first
fetch of a mailbox imports only the last ``INITIAL_DAYS`` days (assumption A-P12-01).

Only ``BODY.PEEK[]`` is fetched: the server side read state stays untouched; nothing is moved,
flagged or deleted on the server."""

from __future__ import annotations

import asyncio
import contextlib
import imaplib
import logging
import ssl
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Mailbox
from mhvp.core.config import Settings
from mhvp.documents.blobs import BlobStore

log = logging.getLogger(__name__)

IMAP_TIMEOUT = 30
BATCH_LIMIT = 50
INITIAL_DAYS = 30
DEFAULT_PORT = 993


class ImapError(Exception):
    """Fetch failed (connection, login, protocol). The text never carries the secret."""


@dataclass
class FetchResult:
    uidvalidity: int | None
    uidnext: int | None = None
    messages: list[tuple[int, bytes]] = field(default_factory=list)
    more: bool = False


class ImapFetcher(Protocol):
    def fetch(
        self, mailbox: Mailbox, *, after_uid: int | None, since: datetime | None, limit: int
    ) -> FetchResult: ...


class ImaplibFetcher:
    """Blocking fetch with the standard library (``imaplib``, TLS on port 993 by default;
    port 143 uses STARTTLS). Runs in a worker thread."""

    def fetch(
        self, mailbox: Mailbox, *, after_uid: int | None, since: datetime | None, limit: int
    ) -> FetchResult:
        if not mailbox.imap_host:
            raise ImapError("Kein IMAP-Server hinterlegt.")
        port = mailbox.imap_port or DEFAULT_PORT
        context = ssl.create_default_context()
        try:
            if port == 143:
                conn: imaplib.IMAP4 = imaplib.IMAP4(mailbox.imap_host, port, timeout=IMAP_TIMEOUT)
                conn.starttls(ssl_context=context)
            else:
                conn = imaplib.IMAP4_SSL(
                    mailbox.imap_host, port, ssl_context=context, timeout=IMAP_TIMEOUT
                )
        except (OSError, imaplib.IMAP4.error) as exc:
            raise ImapError(f"IMAP-Verbindung fehlgeschlagen: {type(exc).__name__}") from None
        try:
            try:
                conn.login(mailbox.username or mailbox.address, mailbox.secret or "")
            except imaplib.IMAP4.error:
                raise ImapError("IMAP-Anmeldung abgelehnt.") from None
            status, _ = conn.select("INBOX", readonly=True)
            if status != "OK":
                raise ImapError("Posteingang (INBOX) nicht lesbar.")
            validity = _untagged_int(conn, "UIDVALIDITY")
            result = collect(conn, validity, after_uid=after_uid, since=since, limit=limit)
            result.uidnext = _untagged_int(conn, "UIDNEXT")
            return result
        except imaplib.IMAP4.error as exc:
            raise ImapError(f"IMAP-Fehler: {type(exc).__name__}") from None
        finally:
            with contextlib.suppress(Exception):
                conn.logout()


def _untagged_int(conn: Any, name: str) -> int | None:
    _, resp = conn.response(name)
    try:
        return int(resp[0]) if resp and resp[0] else None
    except (TypeError, ValueError):
        return None


def collect(
    conn: Any, validity: int | None, *, after_uid: int | None, since: datetime | None, limit: int
) -> FetchResult:
    """UID search and ``BODY.PEEK[]`` fetch on a selected connection (separated for tests)."""
    if after_uid is not None:
        criteria = f"UID {after_uid + 1}:*"
    elif since is not None:
        criteria = f"SINCE {since.strftime('%d-%b-%Y')}"
    else:
        criteria = "ALL"
    status, data = conn.uid("SEARCH", None, criteria)
    if status != "OK":
        raise ImapError("IMAP-Suche fehlgeschlagen.")
    uids = sorted({int(u) for u in (data[0] or b"").split()})
    if after_uid is not None:
        # "n:*" always returns the highest UID, even when it is below n (RFC 3501).
        uids = [u for u in uids if u > after_uid]
    result = FetchResult(uidvalidity=validity, more=len(uids) > limit)
    for uid in uids[:limit]:
        status, parts = conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
        if status != "OK":
            raise ImapError("IMAP-Abruf einer Nachricht fehlgeschlagen.")
        raw = next(
            (p[1] for p in parts or [] if isinstance(p, tuple) and isinstance(p[1], bytes)), None
        )
        if raw is not None:
            result.messages.append((uid, raw))
    return result


_fetcher: ImapFetcher = ImaplibFetcher()


def set_fetcher(fetcher: ImapFetcher) -> ImapFetcher:
    """Test hook; returns the previous fetcher."""
    global _fetcher
    previous, _fetcher = _fetcher, fetcher
    return previous


async def enabled_imap_mailboxes(session: AsyncSession) -> list[Mailbox]:
    rows = await session.scalars(
        select(Mailbox).where(
            Mailbox.kind == "imap",
            Mailbox.enabled.is_(True),
            Mailbox.deleted_at.is_(None),
            Mailbox.imap_host.is_not(None),
        )
    )
    return list(rows)


async def sync_imap_mailbox(
    session: AsyncSession,
    settings: Settings,
    mailbox_id: uuid.UUID,
    created_ids: list[uuid.UUID] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """One fetch of an IMAP mailbox inside the caller's transaction. Raises ``ImapError`` on
    connection or login errors (the caller stores ``last_error``)."""
    from mhvp.communication.gmail import _start_sla_clock
    from mhvp.communication.services import ingest_raw

    mailbox = await session.get(Mailbox, mailbox_id, with_for_update=True)
    if mailbox is None or mailbox.deleted_at is not None:
        raise ImapError("Postfach nicht gefunden.")
    if mailbox.kind != "imap":
        raise ImapError("Kein IMAP-Postfach.")
    if not mailbox.secret:
        raise ImapError("Keine Zugangsdaten hinterlegt.")
    now = now or datetime.now(UTC)
    after_uid = mailbox.last_uid
    since = now - timedelta(days=INITIAL_DAYS) if after_uid is None else None
    result = await asyncio.to_thread(
        _fetcher.fetch, mailbox, after_uid=after_uid, since=since, limit=BATCH_LIMIT
    )
    counts: dict[str, Any] = {
        "fetched": 0,
        "created": 0,
        "duplicates": 0,
        "failed": 0,
        "errors": [],
        "more": result.more,
        "uidvalidity_reset": False,
    }
    if (
        mailbox.imap_uidvalidity is not None
        and result.uidvalidity is not None
        and result.uidvalidity != mailbox.imap_uidvalidity
        and after_uid is not None
    ):
        # UIDs of the old validity are meaningless: restart the cursor, next run refetches
        # the recent window; duplicates are recognised by ``duplicates.find_known``.
        mailbox.last_uid = None
        mailbox.imap_uidvalidity = result.uidvalidity
        counts["uidvalidity_reset"] = True
        mailbox.last_synced_at = now
        return counts
    if result.uidvalidity is not None:
        mailbox.imap_uidvalidity = result.uidvalidity
    blobs = BlobStore(settings)
    cursor = after_uid or 0
    failed_uids: list[int] = []
    for uid, raw in result.messages:
        counts["fetched"] += 1
        try:
            async with session.begin_nested():
                message, created = await ingest_raw(
                    session,
                    blobs,
                    settings,
                    tenant_id=mailbox.tenant_id,
                    actor_user_id=mailbox.created_by,
                    raw=raw,
                    mailbox_id=mailbox.id,
                    auto_ticket=True,
                )
        except Exception as exc:  # recorded on the mailbox, batch continues
            counts["failed"] += 1
            log.exception("imap message not ingested", extra={"imap_uid": uid})
            counts["errors"].append({"uid": uid, "error": f"{type(exc).__name__}"[:200]})
            failed_uids.append(uid)
            cursor = max(cursor, uid)
            continue
        counts["created" if created else "duplicates"] += 1
        if created:
            if created_ids is not None:
                created_ids.append(message.id)
            if message.ticket_id is not None:
                await _start_sla_clock(session, mailbox.tenant_id, message.ticket_id)
        cursor = max(cursor, uid)
    if after_uid is None and not result.more and result.uidnext:
        # First fetch: everything older than the window stays on the server (A-P12-01).
        cursor = max(cursor, result.uidnext - 1)
    if cursor or after_uid is not None:
        mailbox.last_uid = cursor
    mailbox.last_synced_at = now
    # A mail that cannot be stored stays on the server and is named here (UID) so that it
    # can be imported by hand as .eml; the cursor moves on so later mails are not blocked.
    mailbox.last_error = (
        "IMAP: Nachricht(en) mit UID "
        + ", ".join(str(u) for u in failed_uids[:20])
        + " nicht übernommen (bitte als .eml hochladen)."
        if failed_uids
        else None
    )
    return counts
