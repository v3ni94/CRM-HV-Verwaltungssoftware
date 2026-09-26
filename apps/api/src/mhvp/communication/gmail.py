"""Gmail API client and incremental mailbox sync (M20-01).

Read only: messages are fetched in RFC 822 form and handed to the shared intake. The refresh
token lives encrypted on the mailbox (`secret`); the platform's OAuth client comes from settings.
Cursor: Gmail history id. When the history is expired (HTTP 404) the sync restarts from the
current inbox and relies on Message-ID deduplication.
"""

import base64
import logging
import uuid
from datetime import UTC, datetime
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
        r = await self._get(f"messages/{message_id}", format="raw")
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            raise GmailError(f"Nachricht nicht lesbar (HTTP {r.status_code}).")
        return base64.urlsafe_b64decode(r.json()["raw"] + "==")

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
        """Removes the ``INBOX`` label (M20-03, "Erledigt archiviert Mail"). ``gmail.readonly``
        cannot modify labels, so this needs the ``gmail.modify`` scope added to ``SCOPES``
        below; a mailbox connected before that change lacks it on its stored consent. On
        HTTP 403 this raises ``GmailScopeMissingError`` so the caller can record a notice on
        the mailbox instead of failing the whole job."""
        token = await self._access_token()

        async def _post(bearer: str) -> httpx.Response:
            return await self._http.post(
                f"{API}/messages/{message_id}/modify",
                json={"removeLabelIds": ["INBOX"]},
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
            raise GmailScopeMissingError(
                "Berechtigung gmail.modify fehlt, Postfach unter Einstellungen, Postfächer "
                "erneut mit Google verbinden."
            )
        if r.status_code != 200:
            raise GmailError(f"Archivieren fehlgeschlagen (HTTP {r.status_code}).")


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
        "prompt": "consent",
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
        raw = await client.raw_message(mid)
    except (GmailError, httpx.HTTPError) as exc:
        # Transient fetch error of one message (HTTP 5xx, network): remembered for the retry
        # queue, the rest of the batch continues. Token errors surface before this point.
        counts["failed"] += 1
        log.warning("gmail message not fetched", extra={"gmail_id": mid, "reason": str(exc)})
        counts["errors"].append({"gmail_id": mid, "error": str(exc)[:500]})
        return False
    if raw is None:
        return True
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
            )
    except Exception as exc:  # recorded for retry, batch continues
        counts["failed"] += 1
        log.exception("gmail message not ingested", extra={"gmail_id": mid})
        counts["errors"].append({"gmail_id": mid, "error": f"{type(exc).__name__}: {exc}"[:500]})
        return False
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


async def enabled_gmail_mailboxes(session: AsyncSession) -> list[Mailbox]:
    rows = await session.scalars(
        select(Mailbox).where(Mailbox.kind == "gmail", Mailbox.enabled.is_(True))
    )
    return list(rows)


async def sync_one(
    session: AsyncSession,
    settings: Settings,
    mailbox_id: uuid.UUID,
    created_ids: list[uuid.UUID] | None = None,
) -> dict[str, Any]:
    mailbox = await session.get(Mailbox, mailbox_id, with_for_update=True)
    if mailbox is None:
        raise GmailError("Postfach nicht gefunden.")
    client_id, client_secret = await oauth_client(session, settings)
    client = make_client(client_id, client_secret, mailbox)
    try:
        return await sync_mailbox(
            session, BlobStore(settings), settings, mailbox, client, created_ids
        )
    finally:
        await client.aclose()
