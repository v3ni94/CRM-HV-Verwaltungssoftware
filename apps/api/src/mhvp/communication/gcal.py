"""Google Calendar API client (M23-02).

Mirrors the token handling of `mhvp.communication.gmail.GmailClient` (same refresh token
stored on the mailbox, same 401 retry once). Read (list) and write (insert, patch, delete) of
events on one calendar (`mailbox.calendar_id`, default "primary"). No periodic sync job: events
are fetched on demand by the workspace calendar endpoint and cached there (Redis, 5 minutes).
"""

from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from mhvp.communication.gmail import OAUTH_TOKEN_ENDPOINT
from mhvp.communication.models import Mailbox

API = "https://www.googleapis.com/calendar/v3"


# Error kinds (hotfix 28.09.2026): the workspace calendar maps them to registered problems.
# AUTH: the stored Google grant no longer works (expired or revoked refresh token, missing
# calendar scope, calendar not shared with the account); only reconnecting the mailbox helps.
# UNAVAILABLE: Google answered with a rate limit or a server error; retrying later helps.
# REJECTED: any other refusal (event not found, request not accepted).
AUTH = "auth"
UNAVAILABLE = "unavailable"
REJECTED = "rejected"

# Reasons Google uses for a 403 that is a rate or quota limit, not a permission problem.
_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"})


class GCalError(RuntimeError):
    """Message is a German user text built from the HTTP status only: it never carries the
    response body, a token or an address, so it may be shown and logged."""

    def __init__(self, message: str, *, status: int | None = None, kind: str = REJECTED) -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind

    @property
    def reconnect_required(self) -> bool:
        return self.kind == AUTH


def _limit_reason(r: httpx.Response) -> bool:
    try:
        data = r.json()
    except ValueError:
        return False
    error = data.get("error") if isinstance(data, dict) else None
    items = error.get("errors") if isinstance(error, dict) else None
    if not isinstance(items, list):
        return False
    return any(isinstance(i, dict) and i.get("reason") in _LIMIT_REASONS for i in items)


def _kind(r: httpx.Response) -> str:
    """Kind of a failed Calendar API answer (after the one 401 retry)."""
    if r.status_code == 429 or r.status_code >= 500:
        return UNAVAILABLE
    if r.status_code == 403:
        return UNAVAILABLE if _limit_reason(r) else AUTH
    if r.status_code == 401:
        return AUTH
    return REJECTED


def _error(message: str, r: httpx.Response, kind: str | None = None) -> GCalError:
    return GCalError(message, status=r.status_code, kind=kind or _kind(r))


class GCalClient:
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
            # 400 invalid_grant (expired or revoked) and 401 invalid_client need a reconnect;
            # a rate limit or server error of the token endpoint is transient.
            kind = UNAVAILABLE if r.status_code == 429 or r.status_code >= 500 else AUTH
            raise _error(f"Token-Abruf fehlgeschlagen (HTTP {r.status_code}).", r, kind)
        self._token = str(r.json()["access_token"])
        return self._token

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        token = await self._access_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = await self._http.request(method, f"{API}/{path}", headers=headers, **kwargs)
        if r.status_code == 401:
            self._token = None
            token = await self._access_token()
            headers = {"Authorization": f"Bearer {token}"}
            r = await self._http.request(method, f"{API}/{path}", headers=headers, **kwargs)
        return r

    async def list_events(
        self, calendar_id: str, time_min: datetime, time_max: datetime
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        page: str | None = None
        while True:
            params: dict[str, Any] = {
                "timeMin": time_min.isoformat(),
                "timeMax": time_max.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
            }
            if page:
                params["pageToken"] = page
            r = await self._request(
                "GET",
                f"calendars/{quote(calendar_id, safe='')}/events",
                params=params,
            )
            if r.status_code == 404:
                # The configured calendar is not visible to the connected account.
                raise _error("Kalender nicht gefunden oder keine Berechtigung.", r, AUTH)
            if r.status_code != 200:
                raise _error(f"Kalender nicht lesbar (HTTP {r.status_code}).", r)
            data = r.json()
            events.extend(data.get("items", []))
            page = data.get("nextPageToken")
            if not page:
                return events

    async def insert_event(
        self, calendar_id: str, body: dict[str, Any], send_updates: str = "none"
    ) -> dict[str, Any]:
        # Default "none" (M23-02 rule 2): attendees, if present in body, are never notified
        # until the staff user explicitly confirms "Einladung senden" (send_updates="all").
        r = await self._request(
            "POST",
            f"calendars/{quote(calendar_id, safe='')}/events",
            params={"sendUpdates": send_updates},
            json=body,
        )
        if r.status_code not in (200, 201):
            raise _error(f"Termin nicht anlegbar (HTTP {r.status_code}).", r)
        return dict(r.json())

    async def patch_event(
        self,
        calendar_id: str,
        event_id: str,
        body: dict[str, Any],
        send_updates: str = "none",
    ) -> dict[str, Any]:
        r = await self._request(
            "PATCH",
            f"calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
            params={"sendUpdates": send_updates},
            json=body,
        )
        if r.status_code == 404:
            raise _error("Termin nicht gefunden.", r)
        if r.status_code != 200:
            raise _error(f"Termin nicht änderbar (HTTP {r.status_code}).", r)
        return dict(r.json())

    async def get_event(self, calendar_id: str, event_id: str) -> dict[str, Any]:
        r = await self._request(
            "GET",
            f"calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
        )
        if r.status_code == 404:
            raise _error("Termin nicht gefunden.", r)
        if r.status_code != 200:
            raise _error(f"Termin nicht lesbar (HTTP {r.status_code}).", r)
        return dict(r.json())

    async def delete_event(
        self, calendar_id: str, event_id: str, send_updates: str = "none"
    ) -> None:
        r = await self._request(
            "DELETE",
            f"calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
            params={"sendUpdates": send_updates},
        )
        if r.status_code not in (200, 204, 404):
            raise _error(f"Termin nicht löschbar (HTTP {r.status_code}).", r)


def make_client(client_id: str, client_secret: str, mailbox: Mailbox) -> GCalClient:
    if not mailbox.secret:
        raise GCalError("Kein Refresh-Token für dieses Postfach hinterlegt.", kind=AUTH)
    return GCalClient(client_id, client_secret, mailbox.secret)
