"""Outbound HTTP for real Messdienstleister adapters (master prompt sections 9 and 10).

* Every target passes ``mhvp.core.webhooks.pin_target`` (SSRF guard, DNS pinning, TLS
  verification stays on). Secrets are sent only to the pinned host: an ``Authorization``
  header is set per request and never copied onto a redirect (``follow_redirects`` is off,
  a redirect is an error).
* Authentication schemes per API family exactly as documented (Q9, Q3, bved OpenAPI files):
  OAuth 2 client credentials against a provider supplied token URL, HTTP Basic, and an
  optional mTLS client certificate (ista test systems, Q9).
* Reads (GET) are retried with exponential backoff on connection errors, timeouts and 5xx up
  to ``retries`` times. A write (POST/PUT) is never retried after a timeout: the action may
  have been executed at the provider, the outcome is ``unclear`` (section 10, acceptance
  case 11).
* Error texts never contain secrets: header values and URL credentials are masked before a
  message leaves this module.
"""

from __future__ import annotations

import base64
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import httpx

from mhvp.core.webhooks import PinnedTarget, UnsafeWebhookTargetError, pin_target

_AUTH_RE = re.compile(r"(?i)(authorization\s*[:=]\s*)(\S+)(\s+\S+)?")
_CRED_URL_RE = re.compile(r"://[^/@\s]+@")
_TOKEN_RE = re.compile(
    r"(?i)((?:access_token|client_secret|password|refresh_token)[\"'=:\s]+)[^\s\"'&,}]+"
)

MAX_PAGE_LIMIT = 100  # Q8: "Die Anzahl der zurückgegebenen Einträge darf 100 nicht überschreiten."
MAX_BODY_BYTES = 50 * 1024 * 1024


class ProviderHttpError(Exception):
    """Failed call; ``message`` is already sanitised. ``unclear`` marks a write whose outcome is
    unknown (request left the process, no response). ``status`` carries the HTTP status."""

    def __init__(self, message: str, *, status: int | None = None, unclear: bool = False) -> None:
        super().__init__(sanitize(message))
        self.message = sanitize(message)
        self.status = status
        self.unclear = unclear


class AuthFailedError(ProviderHttpError):
    """401 or 403: credentials rejected or account not released."""


def sanitize(message: str) -> str:
    message = _AUTH_RE.sub(r"\1***", message)
    message = _CRED_URL_RE.sub("://***@", message)
    return _TOKEN_RE.sub(r"\1***", message)


@dataclass(frozen=True)
class OAuth2ClientCredentials:
    token_url: str
    client_id: str
    client_secret: str
    scope: str | None = None


@dataclass(frozen=True)
class BasicCredentials:
    username: str
    password: str


Auth = OAuth2ClientCredentials | BasicCredentials


@dataclass(frozen=True)
class ClientCertificate:
    """mTLS client certificate as PEM text (kept in the encrypted secrets, written to memory
    only). httpx needs file paths; the adapter passes paths of temporary files it owns."""

    cert_path: str
    key_path: str


class ProviderHttp:
    """One pinned HTTPS client per adapter call. ``transport`` and ``pin`` are injection points
    for tests (``httpx.MockTransport``, no DNS); production never sets them."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        retries: int = 2,
        backoff_seconds: float = 0.5,
        transport: httpx.BaseTransport | None = None,
        pin: Callable[[str], PinnedTarget] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        certificate: ClientCertificate | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff_seconds = backoff_seconds
        self._pin = pin or (lambda url: pin_target(url, allow_private=False))
        self._sleep = sleep
        kwargs: dict[str, Any] = {
            "timeout": timeout,
            "follow_redirects": False,
            "verify": True,  # TLS verification is never switched off (section 9)
        }
        if transport is not None:
            kwargs["transport"] = transport
        if certificate is not None:
            kwargs["cert"] = (certificate.cert_path, certificate.key_path)
        self._client = httpx.Client(**kwargs)
        self._tokens: dict[tuple[str, str], tuple[str, float]] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ProviderHttp:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # Authentication ------------------------------------------------------------------

    def _bearer(self, auth: OAuth2ClientCredentials) -> str:
        key = (auth.token_url, auth.client_id)
        with self._lock:
            cached = self._tokens.get(key)
            if cached and cached[1] > time.monotonic() + 30:
                return cached[0]
        data = {"grant_type": "client_credentials"}
        if auth.scope:
            data["scope"] = auth.scope
        target = self._target(auth.token_url)
        try:
            response = self._client.post(
                target.url,
                data=data,
                auth=(auth.client_id, auth.client_secret),
                headers={**target.headers, "Accept": "application/json"},
                extensions=target.extensions,
            )
        except httpx.HTTPError as exc:
            raise ProviderHttpError(f"Token-Anfrage fehlgeschlagen: {type(exc).__name__}") from exc
        if response.status_code in (400, 401, 403):
            raise AuthFailedError(
                f"Token-Anfrage abgewiesen (HTTP {response.status_code}).",
                status=response.status_code,
            )
        if response.status_code != 200:
            raise ProviderHttpError(
                f"Token-Anfrage fehlgeschlagen (HTTP {response.status_code}).",
                status=response.status_code,
            )
        try:
            body = response.json()
            token = str(body["access_token"])
            expires = float(body.get("expires_in", 300))
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderHttpError("Token-Antwort ohne access_token.") from exc
        with self._lock:
            self._tokens[key] = (token, time.monotonic() + expires)
        return token

    def _auth_header(self, auth: Auth | None) -> dict[str, str]:
        if auth is None:
            return {}
        if isinstance(auth, OAuth2ClientCredentials):
            return {"Authorization": f"Bearer {self._bearer(auth)}"}
        raw = f"{auth.username}:{auth.password}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}

    # Requests --------------------------------------------------------------------------

    def _target(self, url: str) -> PinnedTarget:
        try:
            return self._pin(url)
        except UnsafeWebhookTargetError as exc:
            raise ProviderHttpError(f"Unzulässiges Ziel: {exc}") from exc

    def request(
        self,
        method: str,
        url: str,
        *,
        auth: Auth | None,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        accept: str = "application/json",
        extra_headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """GET with retries and backoff; POST/PUT exactly once (never blindly repeated)."""
        target = self._target(url)
        headers = {**target.headers, "Accept": accept, **(extra_headers or {})}
        is_write = method.upper() != "GET"
        attempts = 1 if is_write else self.retries + 1
        last_error: ProviderHttpError | None = None
        for attempt in range(attempts):
            if attempt:
                self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))
            try:
                response = self._client.request(
                    method,
                    target.url,
                    params=params,
                    json=json,
                    headers={**headers, **self._auth_header(auth)},
                    extensions=target.extensions,
                )
            except httpx.TimeoutException as exc:
                if is_write:
                    raise ProviderHttpError(
                        "Zeitüberschreitung bei schreibendem Aufruf; Ergebnis unklar, keine "
                        "automatische Wiederholung.",
                        unclear=True,
                    ) from exc
                last_error = ProviderHttpError(f"Zeitüberschreitung ({type(exc).__name__}).")
                continue
            except httpx.HTTPError as exc:
                last_error = ProviderHttpError(f"Verbindungsfehler ({type(exc).__name__}).")
                if is_write:
                    raise last_error from exc
                continue
            if response.status_code in (401, 403):
                raise AuthFailedError(
                    f"Authentifizierung abgewiesen (HTTP {response.status_code}).",
                    status=response.status_code,
                )
            if 300 <= response.status_code < 400:
                raise ProviderHttpError(
                    f"Weiterleitung (HTTP {response.status_code}) wird nicht gefolgt.",
                    status=response.status_code,
                )
            if response.status_code >= 500 and not is_write:
                last_error = ProviderHttpError(
                    f"Anbieterfehler (HTTP {response.status_code}).", status=response.status_code
                )
                continue
            if len(response.content) > MAX_BODY_BYTES:
                raise ProviderHttpError("Antwort überschreitet das Größenlimit.")
            return response
        if last_error is None:  # pragma: no cover - attempts is at least 1
            raise ProviderHttpError("Kein Versuch ausgeführt.")
        raise last_error

    def get_json(
        self, url: str, *, auth: Auth | None, params: Mapping[str, Any] | None = None
    ) -> Any:
        response = self.request("GET", url, auth=auth, params=params)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ProviderHttpError(
                f"Unerwartete Antwort (HTTP {response.status_code}).", status=response.status_code
            )
        try:
            # Exact decimals: amounts never pass through float (section 11).
            return response.json(parse_float=Decimal)
        except ValueError as exc:
            raise ProviderHttpError("Antwort ist kein gültiges JSON.") from exc


def same_host(base_url: str, url: str) -> bool:
    """A provider supplied link (``_links.next``, download URLs) is followed only on the host of
    the configured base URL (section 9: no secret to a foreign host)."""
    a, b = urlsplit(base_url), urlsplit(url)
    return (a.scheme, a.hostname, a.port or 443) == (b.scheme, b.hostname, b.port or 443)


def join(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")
