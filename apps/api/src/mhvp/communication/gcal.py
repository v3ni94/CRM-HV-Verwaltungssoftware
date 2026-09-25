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


class GCalError(RuntimeError):
    pass


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
            raise GCalError(f"Token-Abruf fehlgeschlagen (HTTP {r.status_code}).")
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
                raise GCalError("Kalender nicht gefunden oder keine Berechtigung.")
            if r.status_code != 200:
                raise GCalError(f"Kalender nicht lesbar (HTTP {r.status_code}).")
            data = r.json()
            events.extend(data.get("items", []))
            page = data.get("nextPageToken")
            if not page:
                return events

    async def insert_event(self, calendar_id: str, body: dict[str, Any]) -> dict[str, Any]:
        r = await self._request(
            "POST",
            f"calendars/{quote(calendar_id, safe='')}/events",
            json=body,
        )
        if r.status_code not in (200, 201):
            raise GCalError(f"Termin nicht anlegbar (HTTP {r.status_code}).")
        return dict(r.json())

    async def patch_event(
        self, calendar_id: str, event_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        r = await self._request(
            "PATCH",
            f"calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
            json=body,
        )
        if r.status_code == 404:
            raise GCalError("Termin nicht gefunden.")
        if r.status_code != 200:
            raise GCalError(f"Termin nicht änderbar (HTTP {r.status_code}).")
        return dict(r.json())

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        r = await self._request(
            "DELETE",
            f"calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
        )
        if r.status_code not in (200, 204, 404):
            raise GCalError(f"Termin nicht löschbar (HTTP {r.status_code}).")


def make_client(client_id: str, client_secret: str, mailbox: Mailbox) -> GCalClient:
    if not mailbox.secret:
        raise GCalError("Kein Refresh-Token für dieses Postfach hinterlegt.")
    return GCalClient(client_id, client_secret, mailbox.secret)
