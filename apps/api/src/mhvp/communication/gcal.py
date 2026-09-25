"""Google Calendar via the mailbox OAuth identity (M20-03, user rule 25.09.2026).

The rule of the operator: the calendar is always the Google calendar. Every connected Gmail
mailbox contributes its primary calendar; the default mailbox (for example info@) is the
organisation calendar new appointments go to, additional mailboxes (personal addresses) are
shown alongside. Uses the mailbox refresh token; connecting anew grants the calendar scope."""

from datetime import datetime
from typing import Any

import httpx

from mhvp.communication.gmail import GmailClient, GmailError

CAL_API = "https://www.googleapis.com/calendar/v3"


class CalendarClient(GmailClient):
    """Same OAuth identity as the mailbox, different Google API."""

    async def _cal_get(self, path: str, **params: Any) -> httpx.Response:
        token = await self._access_token()
        r = await self._http.get(
            f"{CAL_API}/{path}", params=params, headers={"Authorization": f"Bearer {token}"}
        )
        if r.status_code == 401:
            self._token = None
            token = await self._access_token()
            r = await self._http.get(
                f"{CAL_API}/{path}", params=params, headers={"Authorization": f"Bearer {token}"}
            )
        return r

    async def list_events(self, time_min: str, time_max: str) -> list[dict[str, Any]]:
        """Events of the primary calendar in the window, expanded single events."""
        rows: list[dict[str, Any]] = []
        page: str | None = None
        while True:
            params: dict[str, Any] = {
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 250,
            }
            if page:
                params["pageToken"] = page
            r = await self._cal_get("calendars/primary/events", **params)
            if r.status_code != 200:
                raise GmailError(f"Kalender nicht lesbar (HTTP {r.status_code}).")
            data = r.json()
            rows.extend(data.get("items", []))
            page = data.get("nextPageToken")
            if not page:
                return rows

    async def create_event(
        self,
        summary: str,
        starts_at: datetime,
        ends_at: datetime,
        description: str | None,
    ) -> dict[str, Any]:
        token = await self._access_token()
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": starts_at.isoformat()},
            "end": {"dateTime": ends_at.isoformat()},
        }
        if description:
            body["description"] = description
        r = await self._http.post(
            f"{CAL_API}/calendars/primary/events",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code not in (200, 201):
            raise GmailError(f"Termin nicht angelegt (HTTP {r.status_code}).")
        return dict(r.json())


def event_out(mailbox_address: str, item: dict[str, Any]) -> dict[str, Any]:
    start = item.get("start") or {}
    end = item.get("end") or {}
    return {
        "id": str(item.get("id", "")),
        "calendar": mailbox_address,
        "summary": str(item.get("summary") or "(ohne Titel)"),
        "starts_at": start.get("dateTime") or start.get("date"),
        "ends_at": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start,
        "link": item.get("htmlLink"),
    }
