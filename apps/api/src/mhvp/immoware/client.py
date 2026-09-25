"""HTTP-Basis fuer den DAV-Zugriff auf Immoware24 (Regel 1/2 des Hubs: nur WebDAV, CardDAV,
CalDAV, strikt lesend). ``ReadOnlyDavClient`` laesst nur PROPFIND, REPORT und GET zu; jede
andere Methode wirft ``WriteBlockedError``, statt eine Anfrage zu senden.
"""

import re

import httpx

from mhvp.core.problems import ErrorCodes, ProblemError

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
    """Duenner Wrapper um ``httpx.AsyncClient``, der nur lesende DAV-Methoden zulaesst."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        if method.upper() not in _ALLOWED_METHODS:
            raise WriteBlockedError(
                f"Methode {method} ist gesperrt, der Hub ist read_only (Regel 2)."
            )
        try:
            return await self._client.request(method, url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            raise ProblemError(ErrorCodes.IMW_UNAVAILABLE, detail=sanitize_error(str(exc))) from exc

    async def aclose(self) -> None:
        await self._client.aclose()


def build_httpx_client(
    *, username: str | None, password: str | None, verify_tls: bool, timeout: float = 30.0
) -> httpx.AsyncClient:
    auth = httpx.BasicAuth(username, password or "") if username else None
    return httpx.AsyncClient(auth=auth, verify=verify_tls, timeout=timeout, follow_redirects=True)


def derive_carddav_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/addressbooks/"


def derive_caldav_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/calendars/"
