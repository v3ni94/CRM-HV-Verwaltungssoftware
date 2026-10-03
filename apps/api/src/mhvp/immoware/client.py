"""HTTP-Basis fuer den DAV-Zugriff auf Immoware24 (Regel 1/2 des Hubs: nur WebDAV, CardDAV,
CalDAV, strikt lesend). ``ReadOnlyDavClient`` laesst nur PROPFIND, REPORT und GET zu; jede
andere Methode wirft ``WriteBlockedError``, statt eine Anfrage zu senden.
"""

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from mhvp.core.problems import ErrorCodes, ProblemError
from mhvp.core.webhooks import PinnedTarget, UnsafeWebhookTargetError

_MAX_REDIRECTS = 5
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

_ALLOWED_METHODS = frozenset({"PROPFIND", "REPORT", "GET"})
_AUTH_HEADER_RE = re.compile(r"(Authorization:\s*Basic\s+)[A-Za-z0-9+/=]+", re.IGNORECASE)
_CRED_URL_RE = re.compile(r"://[^/@\s]+:[^/@\s]+@")


class WriteBlockedError(Exception):
    """Ein Schreibversuch (PUT/DELETE/MOVE/PROPPATCH/...) wurde abgelehnt (Regel 2 des Hubs)."""


def sanitize_error(message: str) -> str:
    """Entfernt Basic-Auth-Header und Zugangsdaten in URLs, bevor ein Fehler gespeichert wird."""
    message = _AUTH_HEADER_RE.sub(r"\1***", message)
    message = _CRED_URL_RE.sub("://***@", message)
    return message


class ReadOnlyDavClient:
    """Duenner Wrapper um ``httpx.AsyncClient``, der nur lesende DAV-Methoden zulaesst.

    GAM-302: mit ``pin`` (Produktivpfad ``service.dav_client``) wird jede Ziel-URL, auch aus
    Discovery-Ergebnissen und nach jeder Weiterleitung, mit ``pin_target`` geprueft und auf die
    geprueften Adresse festgelegt. Weiterleitungen folgt der Wrapper selbst, hoechstens fuenf
    und nur auf denselben Host, damit Zugangsdaten nie an ein anderes Ziel gehen."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        pin: Callable[[str], PinnedTarget] | None = None,
    ) -> None:
        self._client = client
        self._pin = pin

    async def _send(self, method: str, url: str, kwargs: dict[str, object]) -> httpx.Response:
        if self._pin is None:
            return await self._client.request(method, url, **kwargs)  # type: ignore[arg-type]
        try:
            target = self._pin(url)
        except UnsafeWebhookTargetError as exc:
            raise ProblemError(
                ErrorCodes.IMW_UNAVAILABLE,
                detail="Ziel-URL nicht zulaessig (nur oeffentliche https-Adressen).",
            ) from exc
        extra: dict[str, Any] = dict(kwargs)
        extra["headers"] = {**dict(extra.get("headers") or {}), **target.headers}
        extra["extensions"] = {**dict(extra.get("extensions") or {}), **target.extensions}
        return await self._client.request(method, target.url, **extra)

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        if method.upper() not in _ALLOWED_METHODS:
            raise WriteBlockedError(
                f"Methode {method} ist gesperrt, der Hub ist read_only (Regel 2)."
            )
        origin = urlsplit(url)
        current = url
        try:
            for _ in range(_MAX_REDIRECTS + 1):
                response = await self._send(method, current, dict(kwargs))
                location = response.headers.get("Location")
                if response.status_code not in _REDIRECT_CODES or not location:
                    return response
                following = urljoin(current, location)
                nxt = urlsplit(following)
                if (nxt.scheme, nxt.hostname, nxt.port) != (
                    origin.scheme,
                    origin.hostname,
                    origin.port,
                ):
                    raise ProblemError(
                        ErrorCodes.IMW_UNAVAILABLE,
                        detail="Weiterleitung auf einen anderen Host wird nicht verfolgt.",
                    )
                current = following
            raise ProblemError(ErrorCodes.IMW_UNAVAILABLE, detail="Zu viele Weiterleitungen.")
        except httpx.HTTPError as exc:
            raise ProblemError(ErrorCodes.IMW_UNAVAILABLE, detail=sanitize_error(str(exc))) from exc

    async def aclose(self) -> None:
        await self._client.aclose()


def build_httpx_client(
    *, username: str | None, password: str | None, verify_tls: bool, timeout: float = 30.0
) -> httpx.AsyncClient:
    auth = httpx.BasicAuth(username, password or "") if username else None
    return httpx.AsyncClient(auth=auth, verify=verify_tls, timeout=timeout, follow_redirects=False)


def derive_carddav_url(base_url: str, username: str | None = None) -> str:
    """Adressbuch-Heimat; bei bekanntem Login der Benutzerpfad nach SabreDAV-Muster."""
    root = base_url.rstrip("/")
    return f"{root}/addressbooks/users/{username}/" if username else root + "/addressbooks/"


def derive_caldav_url(base_url: str, username: str | None = None) -> str:
    """Kalender-Heimat; die Kalender darunter ermittelt ``caldav.discover_calendars``."""
    root = base_url.rstrip("/")
    return f"{root}/calendars/users/{username}/" if username else root + "/calendars/"
