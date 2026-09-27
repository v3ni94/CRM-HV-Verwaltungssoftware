"""Gmail API client and incremental mailbox sync (M20-01).

Read only: messages are fetched in RFC 822 form and handed to the shared intake. The refresh
token lives encrypted on the mailbox (`secret`); the platform's OAuth client comes from settings.
Cursor: Gmail history id. When the history is expired (HTTP 404) the sync restarts from the
current inbox and relies on Message-ID deduplication.
"""

import base64
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication.models import Mailbox
from mhvp.core.config import Settings
from mhvp.documents.blobs import BlobStore

log = logging.getLogger(__name__)

OAUTH_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105
API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailError(RuntimeError):
    pass


class GmailClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._auth = (client_id, client_secret, refresh_token)
        self._http = httpx.AsyncClient(timeout=30.0, transport=transport)
        self._token: str | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _access_token(self) -> str:
        if self._token:
            return self._token
        cid, secret, refresh = self._auth
        r = await self._http.post(
            OAUTH_TOKEN_ENDPOINT,
            data={
                "client_id": cid,
                "client_secret": secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
        if r.status_code != 200:
            raise GmailError(f"Token-Abruf fehlgeschlagen (HTTP {r.status_code}).")
        self._token = str(r.json()["access_token"])
        return self._token

    async def _get(self, path: str, **params: Any) -> httpx.Response:
        token = await self._access_token()
        r = await self._http.get(
            f"{API}/{path}", params=params, headers={"Authorization": f"Bearer {token}"}
        )
        if r.status_code == 401:
            self._token = None
            token = await self._access_token()
            r = await self._http.get(
                f"{API}/{path}", params=params, headers={"Authorization": f"Bearer {token}"}
            )
        return r

    async def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        token = await self._access_token()
        r = await self._http.post(
            f"{API}/{path}", json=payload, headers={"Authorization": f"Bearer {token}"}
        )
        if r.status_code == 401:
            self._token = None
            token = await self._access_token()
            r = await self._http.post(
                f"{API}/{path}", json=payload, headers={"Authorization": f"Bearer {token}"}
            )
        return r

    async def watch(self, topic: str) -> tuple[str, datetime]:
        """Registers (or renews) push notifications for the label INBOX on the Pub/Sub
        ``topic`` (``users.watch``). Returns the history id Google reports for the watch and
        its expiration (at most seven days ahead). Renewing simply calls watch again."""
        r = await self._post(
            "watch",
            {"topicName": topic, "labelIds": ["INBOX"], "labelFilterBehavior": "INCLUDE"},
        )
        if r.status_code != 200:
            raise GmailError(f"Push-Registrierung fehlgeschlagen (HTTP {r.status_code}).")
        data = r.json()
        expiration = datetime.fromtimestamp(int(data["expiration"]) / 1000, tz=UTC)
        return str(data["historyId"]), expiration

    async def stop(self) -> None:
        """Ends push notifications (``users.stop``); a missing watch is no error."""
        r = await self._post("stop", {})
        if r.status_code not in (200, 204, 404):
            raise GmailError(f"Push-Abmeldung fehlgeschlagen (HTTP {r.status_code}).")

    async def label_total(self, label_id: str = "INBOX") -> int | None:
        """Number of messages under ``label_id`` (``labels.get``, ``messagesTotal``); None when
        Google does not report it. Used as the progress total of the inbox backfill."""
        r = await self._get(f"labels/{label_id}")
        if r.status_code != 200:
            raise GmailError(f"Label nicht lesbar (HTTP {r.status_code}).")
        total = r.json().get("messagesTotal")
        return int(total) if total is not None else None

    async def list_inbox_page(
        self, page_token: str | None, limit: int
    ) -> tuple[list[str], str | None]:
        """One page of ``messages.list`` for the label INBOX (newest first): message ids and
        the token of the next page (None on the last page). History independent."""
        params: dict[str, Any] = {"labelIds": "INBOX", "maxResults": limit}
        if page_token:
            params["pageToken"] = page_token
        r = await self._get("messages", **params)
        if r.status_code != 200:
            raise GmailError(f"Posteingang nicht lesbar (HTTP {r.status_code}).")
        data = r.json()
        ids = [str(m["id"]) for m in data.get("messages", [])]
        next_token = data.get("nextPageToken")
        return ids, (str(next_token) if next_token else None)

    async def profile_history_id(self) -> str:
        r = await self._get("profile")
        if r.status_code != 200:
            raise GmailError(f"Profil nicht lesbar (HTTP {r.status_code}).")
        return str(r.json()["historyId"])

    async def list_inbox(self, limit: int) -> list[str]:
        r = await self._get("messages", labelIds="INBOX", maxResults=limit)
        if r.status_code != 200:
            raise GmailError(f"Posteingang nicht lesbar (HTTP {r.status_code}).")
        return [m["id"] for m in r.json().get("messages", [])]

    async def find_by_header_id(self, header_message_id: str) -> str | None:
        """Gmail id of the message with this RFC 822 Message-ID header, or None."""
        r = await self._get("messages", q=f"rfc822msgid:{header_message_id}", maxResults=1)
        if r.status_code != 200:
            raise GmailError(f"Nachrichtensuche fehlgeschlagen (HTTP {r.status_code}).")
        found = r.json().get("messages") or []
        return str(found[0]["id"]) if found else None

    async def history_since(self, history_id: str) -> list[tuple[int, str]] | None:
        """All ``(historyId, messageId)`` pairs of inbox messages added since ``history_id``,
        every page, in history order; None when the history is expired (HTTP 404). The caller
        decides how many to process and moves the cursor only past processed entries."""
        seen: set[str] = set()
        entries: list[tuple[int, str]] = []
        page: str | None = None
        while True:
            params: dict[str, Any] = {
                "startHistoryId": history_id,
                "historyTypes": "messageAdded",
                "labelId": "INBOX",
            }
            if page:
                params["pageToken"] = page
            r = await self._get("history", **params)
            if r.status_code == 404:
                return None
            if r.status_code != 200:
                raise GmailError(f"Verlauf nicht lesbar (HTTP {r.status_code}).")
            data = r.json()
            for h in data.get("history", []):
                entry_id = int(h.get("id") or history_id)
                for added in h.get("messagesAdded", []):
                    mid = added["message"]["id"]
                    if mid not in seen:
                        seen.add(mid)
                        entries.append((entry_id, mid))
            page = data.get("nextPageToken")
            if not page:
                return entries

    async def list_since(self, history_id: str, limit: int) -> list[str] | None:
        """Message ids added since history_id (first ``limit``); None when the history is
        expired. Kept for callers that only need ids; the sync uses ``history_since``."""
        entries = await self.history_since(history_id)
        if entries is None:
            return None
        return [mid for _, mid in entries][:limit]

    async def raw_message(self, message_id: str) -> bytes | None:
        fetched = await self.raw_message_with_thread(message_id)
        return fetched[0] if fetched is not None else None

    async def raw_message_with_thread(self, message_id: str) -> tuple[bytes, str | None] | None:
        """Raw RFC 822 bytes and the Gmail thread id (threading fallback, M7); None when the
        message is gone."""
        r = await self._get(f"messages/{message_id}", format="raw")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise GmailError(f"Nachricht nicht lesbar (HTTP {r.status_code}).")
        data = r.json()
        thread = data.get("threadId")
        return base64.urlsafe_b64decode(data["raw"] + "=="), (str(thread) if thread else None)

    async def find_by_rfc822_msgid(self, header_message_id: str) -> str | None:
        """Gmail id of a message with this ``Message-ID`` header, or None. Proof of dispatch
        for a message whose status change failed after ``send_raw`` (Review 26.09.2026, M1)."""
        needle = header_message_id.strip().strip("<>")
        if not needle:
            return None
        r = await self._get("messages", q=f"rfc822msgid:{needle}", maxResults=1)
        if r.status_code != 200:
            raise GmailError(f"Versandnachweis nicht abrufbar (HTTP {r.status_code}).")
        found = r.json().get("messages") or []
        return str(found[0]["id"]) if found else None

    async def send_raw(self, raw: bytes) -> str:
        """Sends a raw RFC 822 message; returns the Gmail message id."""
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        token = await self._access_token()

        async def _post(bearer: str) -> httpx.Response:
            return await self._http.post(
                f"{API}/messages/send",
                json={"raw": encoded},
                headers={"Authorization": f"Bearer {bearer}"},
            )

        r = await _post(token)
        if r.status_code == 401:
            self._token = None
            token = await self._access_token()
            r = await _post(token)
        if r.status_code == 403:
            raise GmailError(
                "Sendeberechtigung fehlt, Postfach unter Einstellungen, Postfächer erneut "
                "mit Google verbinden."
            )
        if r.status_code != 200:
            raise GmailError(f"Versand fehlgeschlagen (HTTP {r.status_code}).")
        return str(r.json()["id"])

    async def archive(self, message_id: str) -> None:
        """Removes the labels ``INBOX`` and ``UNREAD`` (M20-03, "Erledigt archiviert Mail").
        ``gmail.readonly`` cannot modify labels, so this needs the ``gmail.modify`` scope in
        ``SCOPES`` below; a mailbox connected before that change lacks it on its stored
        consent. HTTP 403 with an insufficient permission reason raises
        ``GmailScopeMissingError`` so the caller records a notice on the mailbox instead of
        failing the whole job; a rate limit 403 stays a plain ``GmailError`` (retried). A 404
        (mail deleted or moved) counts as done. ``message_id`` is the Gmail message id, never
        the thread id."""
        token = await self._access_token()

        async def _post(bearer: str) -> httpx.Response:
            return await self._http.post(
                f"{API}/messages/{message_id}/modify",
                json={"removeLabelIds": ["INBOX", "UNREAD"]},
                headers={"Authorization": f"Bearer {bearer}"},
            )

        r = await _post(token)
        if r.status_code == 401:
            self._token = None
            token = await self._access_token()
            r = await _post(token)
        if r.status_code == 404:
            return  # already gone (deleted or previously archived)
        if r.status_code == 403:
            reason = _error_reason(r)
            if reason in RATE_LIMIT_REASONS:
                raise GmailError(f"Archivieren vorübergehend abgelehnt (Gmail: {reason}).")
            raise GmailScopeMissingError(
                "Berechtigung gmail.modify fehlt, Postfach unter Einstellungen, Postfächer "
                "erneut mit Google verbinden."
            )
        if r.status_code != 200:
            raise GmailError(f"Archivieren fehlgeschlagen (HTTP {r.status_code}).")


# Gmail reports quota and rate limits with HTTP 403 as well; these are no scope problems.
RATE_LIMIT_REASONS = frozenset(
    {"rateLimitExceeded", "userRateLimitExceeded", "dailyLimitExceeded", "quotaExceeded"}
)


def _error_reason(response: httpx.Response) -> str:
    """``errors[0].reason`` or ``error.status`` of a Google API error body, "" otherwise."""
    try:
        error = response.json().get("error") or {}
    except ValueError:
        return ""
    if not isinstance(error, dict):
        return ""
    errors = error.get("errors") or []
    if errors and isinstance(errors[0], dict) and errors[0].get("reason"):
        return str(errors[0]["reason"])
    return str(error.get("status") or "")


class GmailScopeMissingError(GmailError):
    """The stored consent does not include ``gmail.modify`` (older mailbox connection)."""


OAUTH_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/gmail.modify "
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/calendar.readonly"
)
# Drive: nur Dateien, die das CRM selbst anlegt (kein Zugriff auf den restlichen Drive-Inhalt).
DRIVE_SCOPES = "https://www.googleapis.com/auth/drive.file openid email"


async def oauth_client(session: AsyncSession, settings: Settings) -> tuple[str, str]:
    """Tenant OAuth client (settings page), falling back to the platform environment."""
    from mhvp.platform.models import TenantSettings

    row = await session.scalar(select(TenantSettings))
    if row is not None and row.google_client_id and row.google_client_secret:
        return row.google_client_id, row.google_client_secret
    if settings.google_client_id and settings.google_client_secret:
        return settings.google_client_id, settings.google_client_secret.get_secret_value()
    raise GmailError("Google OAuth-Client ist nicht eingerichtet (Einstellungen, Postfächer).")


def redirect_uri(settings: Settings) -> str:
    base = (settings.api_public_url or settings.jwt_issuer).rstrip("/")
    return f"{base}/api/v1/mail/oauth/google/callback"


def authorization_url(client_id: str, settings: Settings, state: str, purpose: str = "mail") -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri(settings),
        "response_type": "code",
        "scope": DRIVE_SCOPES if purpose == "drive" else SCOPES,
        "access_type": "offline",
        # A mailbox connected before gmail.modify was added must be granted the new scope on
        # reconnect: forced consent screen plus incremental authorization (operator 27.09.2026).
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return str(httpx.URL(OAUTH_AUTH_ENDPOINT, params=params))


async def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    settings: Settings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, str]:
    """Exchange the consent code; returns (refresh_token, mailbox address)."""
    async with httpx.AsyncClient(timeout=30.0, transport=transport) as http:
        r = await http.post(
            OAUTH_TOKEN_ENDPOINT,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri(settings),
            },
        )
        if r.status_code != 200:
            raise GmailError(f"Google hat den Code abgelehnt (HTTP {r.status_code}).")
        tokens = r.json()
        refresh = tokens.get("refresh_token")
        if not refresh:
            raise GmailError("Google hat kein Refresh-Token geliefert; Zugriff erneut erteilen.")
        p = await http.get(
            f"{API}/profile", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        if p.status_code != 200:
            raise GmailError(f"Postfachadresse nicht lesbar (HTTP {p.status_code}).")
        return str(refresh), str(p.json()["emailAddress"]).lower()


def make_client(client_id: str, client_secret: str, mailbox: Mailbox) -> GmailClient:
    if not mailbox.secret:
        raise GmailError("Kein Refresh-Token für dieses Postfach hinterlegt.")
    return GmailClient(client_id, client_secret, mailbox.secret)


async def _ingest_one(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    mailbox: Mailbox,
    client: GmailClient,
    mid: str,
    counts: dict[str, Any],
    created_ids: list[uuid.UUID] | None,
) -> bool:
    """Fetches and ingests one Gmail message inside its own savepoint. Returns False when the
    ingest failed (recorded in ``counts["errors"]``); a message gone from Gmail counts as done."""
    from mhvp.communication.services import ingest_raw

    try:
        fetched = await client.raw_message_with_thread(mid)
    except (GmailError, httpx.HTTPError) as exc:
        # Transient fetch error of one message (HTTP 5xx, network): remembered for the retry
        # queue, the rest of the batch continues. Token errors surface before this point.
        counts["failed"] += 1
        log.warning("gmail message not fetched", extra={"gmail_id": mid, "reason": str(exc)})
        counts["errors"].append({"gmail_id": mid, "error": str(exc)[:500]})
        return False
    if fetched is None:
        return True
    raw, thread_id = fetched
    counts["fetched"] += 1
    # Savepoint per mail: one unreadable or unstorable mail must not roll back the
    # whole batch or poison the session (seen 25.09.2026 as PendingRollbackError).
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
                gmail_message_id=mid,
                gmail_thread_id=thread_id,
            )
    except Exception as exc:  # recorded for retry, batch continues
        counts["failed"] += 1
        log.exception("gmail message not ingested", extra={"gmail_id": mid})
        counts["errors"].append({"gmail_id": mid, "error": f"{type(exc).__name__}: {exc}"[:500]})
        return False
    # Gmail-Kennung merken, sonst kann "Erledigt archiviert Mail" die Nachricht im Postfach
    # nicht finden (Betreibermeldung 26.09.2026: alle Eingangsmails ohne Kennung).
    if message.gmail_message_id is None:
        message.gmail_message_id = mid
    counts["created" if created else "duplicates"] += 1
    if created:
        if created_ids is not None:
            created_ids.append(message.id)
        if message.ticket_id is not None:
            await _start_sla_clock(session, mailbox.tenant_id, message.ticket_id)
    return True


async def _start_sla_clock(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID
) -> None:
    """Ticket aus Mail erhält die SLA-Uhr (review 26.09.2026, H6). ``start_clock`` ist
    idempotent, eine Antwort im Thread startet keine zweite Uhr."""
    from mhvp.sla.service import start_clock
    from mhvp.tickets.models import Ticket

    ticket = await session.get(Ticket, ticket_id)
    if ticket is not None:
        await start_clock(session, tenant_id, ticket.id, ticket.priority)


async def _retry_failed(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    mailbox: Mailbox,
    client: GmailClient,
    counts: dict[str, Any],
    created_ids: list[uuid.UUID] | None,
) -> None:
    """Second try for messages whose ingest failed in an earlier run (H1). Success removes
    the row; a failure increments ``attempts`` until ``MAX_ATTEMPTS`` ends the retries."""
    from mhvp.communication.sync_retry import MAX_ATTEMPTS, MailboxSyncRetry

    rows = list(
        await session.scalars(
            select(MailboxSyncRetry)
            .where(
                MailboxSyncRetry.mailbox_id == mailbox.id,
                MailboxSyncRetry.attempts < MAX_ATTEMPTS,
            )
            .order_by(MailboxSyncRetry.created_at)
            .limit(settings.gmail_sync_batch)
        )
    )
    for row in rows:
        counts["retried"] += 1
        if await _ingest_one(
            session, blobs, settings, mailbox, client, row.gmail_message_id, counts, created_ids
        ):
            await session.delete(row)
        else:
            row.attempts += 1
            row.last_error = counts["errors"][-1]["error"]
    await session.flush()


async def _remember_failure(session: AsyncSession, mailbox: Mailbox, mid: str, error: str) -> None:
    from mhvp.communication.sync_retry import MailboxSyncRetry

    existing = await session.scalar(
        select(MailboxSyncRetry).where(
            MailboxSyncRetry.mailbox_id == mailbox.id, MailboxSyncRetry.gmail_message_id == mid
        )
    )
    if existing is not None:
        existing.attempts += 1
        existing.last_error = error
        return
    session.add(
        MailboxSyncRetry(
            tenant_id=mailbox.tenant_id,
            mailbox_id=mailbox.id,
            gmail_message_id=mid,
            attempts=1,
            last_error=error,
        )
    )


async def sync_mailbox(
    session: AsyncSession,
    blobs: BlobStore,
    settings: Settings,
    mailbox: Mailbox,
    client: GmailClient,
    created_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    """Fetch new inbox messages and ingest them; updates cursor and error state. Ids of newly
    created messages are appended to ``created_ids`` when given (M14-05 automatic intake).

    Cursor rule (review 26.09.2026, H1): at most ``gmail_sync_batch`` history entries are
    processed per run and the cursor moves only to the history id of the last processed entry,
    so a burst of mails beyond the batch is picked up by the next run instead of being skipped.
    A message that fails to ingest is remembered in ``mailbox_sync_retry`` and tried again
    first thing in the following runs; the cursor still advances past it.

    Result: counters ``fetched``, ``created``, ``duplicates``, ``failed``, ``retried``,
    ``remaining`` (history entries left for the next run) and ``errors`` (list of
    ``{"gmail_id", "error"}`` of this run)."""
    counts: dict[str, Any] = {
        "fetched": 0,
        "created": 0,
        "duplicates": 0,
        "failed": 0,
        "retried": 0,
        "remaining": 0,
        "errors": [],
    }
    try:
        await _retry_failed(session, blobs, settings, mailbox, client, counts, created_ids)
        profile_cursor = int(await client.profile_history_id())
        entries: list[tuple[int, str]] | None = None
        if mailbox.gmail_history_id:
            entries = await client.history_since(mailbox.gmail_history_id)
        if entries is None:
            # No cursor yet or history expired (404): restart from the inbox listing; the
            # Message-ID deduplication keeps this free of duplicates.
            entries = [
                (profile_cursor, mid) for mid in await client.list_inbox(settings.gmail_sync_batch)
            ]
            complete = True
        else:
            complete = len(entries) <= settings.gmail_sync_batch
        batch = entries[: settings.gmail_sync_batch]
        # Finish the history entry at the cut so the cursor never splits one entry.
        if not complete:
            last_entry = batch[-1][0]
            while len(batch) < len(entries) and entries[len(batch)][0] == last_entry:
                batch.append(entries[len(batch)])
        counts["remaining"] = len(entries) - len(batch)
        last_done: int | None = None
        for entry_id, mid in batch:
            ok = await _ingest_one(
                session, blobs, settings, mailbox, client, mid, counts, created_ids
            )
            if not ok:
                await _remember_failure(session, mailbox, mid, counts["errors"][-1]["error"])
            last_done = entry_id
        if complete:
            mailbox.gmail_history_id = str(max(profile_cursor, last_done or 0))
        elif last_done is not None:
            mailbox.gmail_history_id = str(last_done)
        first = counts["errors"][0] if counts["errors"] else None
        mailbox.last_error = (
            f"Nachricht {first['gmail_id']}: {first['error']}"[:1000] if first else None
        )
    except (GmailError, httpx.HTTPError) as exc:
        mailbox.last_error = str(exc)[:1000]
        raise
    finally:
        mailbox.last_synced_at = datetime.now(UTC)
    await session.flush()
    return counts


async def backfill_gmail_ids(
    session: AsyncSession, mailbox: Mailbox, client: GmailClient, limit: int = 500
) -> dict[str, int]:
    """Traegt fehlende ``gmail_message_id`` fuer Eingangsmails dieses Postfachs nach
    (Suche per rfc822msgid-Header). Einmaliger Nachtrag nach dem Fehler vom 26.09.2026."""
    from mhvp.communication.models import Message

    rows = list(
        await session.scalars(
            select(Message)
            .where(
                Message.mailbox_id == mailbox.id,
                Message.direction == "in",
                Message.gmail_message_id.is_(None),
                Message.header_message_id.is_not(None),
                Message.received_at >= datetime.now(UTC) - timedelta(days=90),
            )
            .order_by(Message.received_at.desc())
            .limit(limit)
        )
    )
    counts = {"checked": 0, "filled": 0, "not_found": 0, "failed": 0}
    for row in rows:
        counts["checked"] += 1
        try:
            gid = await client.find_by_header_id(str(row.header_message_id))
        except (GmailError, httpx.HTTPError):
            counts["failed"] += 1
            continue
        if gid is None:
            counts["not_found"] += 1
            continue
        row.gmail_message_id = gid
        counts["filled"] += 1
    await session.flush()
    return counts


# Push watch (operator 26.09.2026) ----------------------------------------------------------

# Google ends a watch after seven days at the latest; renew a day before so a missed daily run
# still leaves a margin.
WATCH_RENEW_MARGIN = timedelta(days=1)


def push_configured(settings: Settings) -> bool:
    return bool(settings.gmail_pubsub_topic and settings.gmail_push_token)


def watch_due(mailbox: Mailbox, now: datetime | None = None) -> bool:
    """True when the mailbox has no watch or it expires within ``WATCH_RENEW_MARGIN``."""
    now = now or datetime.now(UTC)
    expiration = mailbox.gmail_watch_expiration
    return expiration is None or expiration - now <= WATCH_RENEW_MARGIN


async def register_watch(settings: Settings, mailbox: Mailbox, client: GmailClient) -> datetime:
    """Calls ``users.watch`` with the configured topic and stores expiration and watch history
    id on the mailbox. The incremental cursor ``gmail_history_id`` is left untouched: a first
    sync still lists the inbox, a later sync walks the history from its own cursor."""
    topic = settings.gmail_pubsub_topic
    if not topic:
        raise GmailError("Pub/Sub-Thema (MHVP_GMAIL_PUBSUB_TOPIC) ist nicht konfiguriert.")
    history_id, expiration = await client.watch(topic)
    mailbox.gmail_watch_history_id = history_id
    mailbox.gmail_watch_expiration = expiration
    return expiration


async def ensure_watch(
    settings: Settings, mailbox: Mailbox, client: GmailClient, now: datetime | None = None
) -> bool:
    """Registers or renews the push watch when push is configured and the watch is due.
    Returns True when a watch call was made. Errors are recorded on ``last_error`` and
    re-raised as ``GmailError`` so the caller decides whether the run continues."""
    if not push_configured(settings) or mailbox.kind != "gmail" or not mailbox.enabled:
        return False
    if not watch_due(mailbox, now):
        return False
    try:
        await register_watch(settings, mailbox, client)
    except (GmailError, httpx.HTTPError) as exc:
        mailbox.last_error = f"Push-Registrierung: {exc}"[:1000]
        raise GmailError(str(exc)) from exc
    return True


async def enabled_gmail_mailboxes(session: AsyncSession) -> list[Mailbox]:
    rows = await session.scalars(
        select(Mailbox).where(
            Mailbox.kind == "gmail", Mailbox.enabled.is_(True), Mailbox.deleted_at.is_(None)
        )
    )
    return list(rows)


async def sync_one(
    session: AsyncSession,
    settings: Settings,
    mailbox_id: uuid.UUID,
    created_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    mailbox = await session.get(Mailbox, mailbox_id, with_for_update=True)
    if mailbox is None or mailbox.deleted_at is not None:
        raise GmailError("Postfach nicht gefunden.")
    client_id, client_secret = await oauth_client(session, settings)
    client = make_client(client_id, client_secret, mailbox)
    try:
        counts = await sync_mailbox(
            session, BlobStore(settings), settings, mailbox, client, created_ids
        )
        # Nachtrag fehlender Gmail-Kennungen (Eingangsmails der letzten 90 Tage), damit
        # "Erledigt archiviert Mail" auch fuer Altbestand greift. Nie den Abruf stoeren.
        try:
            filled = await backfill_gmail_ids(session, mailbox, client)
            counts["backfilled"] = filled["filled"]
        except (GmailError, httpx.HTTPError) as exc:
            log.warning("gmail id backfill failed", extra={"reason": str(exc)[:200]})
        return counts
    finally:
        await client.aclose()
