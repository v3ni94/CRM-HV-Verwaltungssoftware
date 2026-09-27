"""Provider neutral interface for print and mail services (M23-01, docs/rules/M23-01.md).

``PostalProvider`` covers submit, status and cancel. Two implementations ship here:

* ``ManualPostalProvider``: the outgoing mail list in the CRM. Printing, posting and the
  proof of delivery are recorded by a person; ``status`` never reports anything on its own.
* ``LetterXpressProvider``: adapter for the LXP API v3 (documentation 01.12.2024 as
  published on https://www.letterxpress.de/versandwege/api, read 27.09.2026). Only what that
  page documents is implemented; anything not shown there is marked "zu prüfen" in
  ``docs/integrations/postdienst.md``.

The adapter never decides whether a letter may leave: the tenant flag, the mode and the
approval are checked in ``mhvp.communication.postal`` before a provider is called.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import httpx

# Unified job states (order matters for "progress"; ``failed`` and ``cancelled`` are final).
STATUSES = ("submitted", "printed", "sent", "delivered", "failed", "cancelled")
OPEN_STATUSES = ("submitted", "printed", "sent")
FINAL_STATUSES = ("delivered", "failed", "cancelled")


class PostalProviderError(RuntimeError):
    """The provider refused or could not process the request (text without credentials)."""


class PostalProviderUnavailableError(PostalProviderError):
    """The provider did not answer (network, timeout): the outcome is unknown."""


@dataclass(frozen=True)
class PostalOptions:
    registered: str | None = None  # LetterXpress: r1 Einschreiben Einwurf, r2 Einschreiben
    color: bool = False
    duplex: bool = True
    dispatch_date: date | None = None
    notice: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "registered": self.registered,
            "color": self.color,
            "duplex": self.duplex,
            "dispatch_date": self.dispatch_date.isoformat() if self.dispatch_date else None,
            "notice": self.notice,
        }


@dataclass(frozen=True)
class PostalSubmission:
    job_id: str
    status: str = "submitted"
    pages: int | None = None
    price: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PostalStatus:
    status: str
    detail: str | None = None
    tracking_code: str | None = None
    tracking_status: str | None = None
    pages: int | None = None
    price: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class PostalProvider(Protocol):
    name: str
    external: bool  # True when a third party receives the letter

    async def submit(
        self, pdf: bytes, recipient_address: str, options: PostalOptions, filename: str
    ) -> PostalSubmission: ...

    async def status(self, job_id: str) -> PostalStatus | None: ...

    async def cancel(self, job_id: str) -> bool: ...

    async def aclose(self) -> None: ...


class ManualPostalProvider:
    """Postausgangsliste: nothing leaves the system; every state is recorded by a person."""

    name = "manual"
    external = False

    async def submit(
        self, pdf: bytes, recipient_address: str, options: PostalOptions, filename: str
    ) -> PostalSubmission:
        return PostalSubmission(job_id=f"manual-{uuid.uuid4().hex[:12]}", raw={})

    async def status(self, job_id: str) -> PostalStatus | None:
        return None

    async def cancel(self, job_id: str) -> bool:
        return True

    async def aclose(self) -> None:
        return None


# LetterXpress ---------------------------------------------------------------------------

LXP_BASE_URL = "https://api.letterxpress.de/v3"
LXP_TIMEOUT = 60.0
# Documented print job states: queue, hold, done, canceled, draft (list filter values and
# ``status`` in the responses). Item states shown in the examples: queue, sent.
LXP_JOB_STATUS = {
    "queue": "submitted",
    "hold": "submitted",
    "draft": "submitted",
    "done": "sent",
    "canceled": "cancelled",
}


def lxp_checksum(base64_file: str) -> str:
    """``base64_file_checksum``: "md5 from base64 string" (documented)."""
    return hashlib.md5(base64_file.encode("ascii"), usedforsecurity=False).hexdigest()


def lxp_map_status(data: dict[str, Any]) -> PostalStatus:
    """Maps a documented ``printjobs`` response (``data`` object) to the unified status.

    ``done`` counts as ``sent``; ``delivered`` only when the item carries a tracking status
    beginning with "Zugestellt" (registered mail, documented example text). Anything else
    keeps ``submitted`` and stores the raw answer for review."""
    job_status = str(data.get("status") or "")
    items = data.get("items") or []
    item = items[0] if items and isinstance(items[0], dict) else {}
    status = LXP_JOB_STATUS.get(job_status)
    tracking_code = item.get("tracking_code") or None
    tracking_status = item.get("tracking_status") or None
    if tracking_status in ("--", ""):
        tracking_status = None
    detail = f"LetterXpress: Auftrag {job_status or 'unbekannt'}"
    if status is None:
        status = "submitted"
        detail += " (nicht dokumentierter Status, zu prüfen)"
    if job_status == "done" and item.get("status") == "sent":
        status = "sent"
    if tracking_status and str(tracking_status).startswith("Zugestellt"):
        status = "delivered"
    pages = item.get("pages")
    amount = item.get("amount")
    return PostalStatus(
        status=status,
        detail=detail if not tracking_status else f"{detail}; {tracking_status}",
        tracking_code=str(tracking_code) if tracking_code else None,
        tracking_status=str(tracking_status) if tracking_status else None,
        pages=int(pages) if isinstance(pages, int) else None,
        price=Decimal(str(amount)) if isinstance(amount, int | float) else None,
        raw={k: v for k, v in data.items() if k != "base64_file"},
    )


class LetterXpressProvider:
    """LXP API v3. Auth travels in the JSON body (``auth`` object with username, apikey,
    mode) on every request, as documented; the address is read by LetterXpress from the
    PDF's address window, the API has no recipient field."""

    name = "letterxpress"
    external = True

    def __init__(
        self,
        username: str,
        api_key: str,
        mode: str = "test",
        *,
        base_url: str = LXP_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if mode not in ("test", "live"):
            raise PostalProviderError("LetterXpress mode must be test or live.")
        self._auth = {"username": username, "apikey": api_key, "mode": mode}
        self._base = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=LXP_TIMEOUT)
        self.external = mode == "live"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        payload = {"auth": self._auth, **(body or {})}
        try:
            response = await self._client.request(
                method,
                f"{self._base}{path}",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise PostalProviderUnavailableError(
                f"LetterXpress nicht erreichbar: {type(exc).__name__}"
            ) from exc
        if response.status_code == 401:
            raise PostalProviderError("LetterXpress: Anmeldung abgelehnt (Unauthorized).")
        if response.status_code >= 400:
            raise PostalProviderError(
                f"LetterXpress: HTTP {response.status_code} bei {method} {path}."
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise PostalProviderError("LetterXpress: Antwort ist kein JSON.") from exc
        if not isinstance(data, dict):
            raise PostalProviderError("LetterXpress: unerwartete Antwort.")
        return data

    async def balance(self) -> Decimal:
        data = await self._request("GET", "/balance")
        value = (data.get("data") or {}).get("balance")
        if value is None:
            raise PostalProviderError("LetterXpress: kein Guthaben in der Antwort.")
        return Decimal(str(value))

    async def submit(
        self, pdf: bytes, recipient_address: str, options: PostalOptions, filename: str
    ) -> PostalSubmission:
        encoded = base64.b64encode(pdf).decode("ascii")
        letter: dict[str, Any] = {
            "base64_file": encoded,
            "base64_file_checksum": lxp_checksum(encoded),
            "specification": {
                "color": "4" if options.color else "1",
                "mode": "duplex" if options.duplex else "simplex",
                # Registered mail is national only (documented); "auto" otherwise.
                "shipping": "national" if options.registered else "auto",
            },
            "filename_original": filename[:255],
        }
        if options.registered:
            letter["registered"] = options.registered
        if options.dispatch_date:
            letter["dispatch_date"] = options.dispatch_date.isoformat()
        if options.notice:
            letter["notice"] = options.notice[:255]
        # HTTP method for creating a print job is not stated on the public page (zu prüfen);
        # POST is the REST convention used here.
        data = await self._request("POST", "/printjobs", {"letter": letter})
        job = data.get("data") or {}
        job_id = job.get("id")
        if job_id is None:
            raise PostalProviderError("LetterXpress: keine Auftrags-ID in der Antwort.")
        mapped = lxp_map_status(job)
        return PostalSubmission(
            job_id=str(job_id),
            status=mapped.status,
            pages=mapped.pages,
            price=mapped.price,
            raw=mapped.raw,
        )

    async def status(self, job_id: str) -> PostalStatus | None:
        data = await self._request("GET", f"/printjobs/{int(job_id)}")
        job = data.get("data") or {}
        return lxp_map_status(job)

    async def cancel(self, job_id: str) -> bool:
        # Documented: deletion only within 15 minutes after transfer, never for "done".
        data = await self._request("DELETE", f"/printjobs/{int(job_id)}")
        return int(data.get("status", 0)) == 200


# Registry --------------------------------------------------------------------------------

ProviderFactory = Callable[[dict[str, Any]], PostalProvider]
_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Registers a provider factory (tests register a fake; adapters register themselves)."""
    _REGISTRY[name] = factory


def unregister_provider(name: str) -> None:
    _REGISTRY.pop(name, None)


def provider_names() -> list[str]:
    return [
        "manual",
        "letterxpress",
        *sorted(n for n in _REGISTRY if n not in ("manual", "letterxpress")),
    ]


def build_provider(name: str, config: dict[str, Any]) -> PostalProvider:
    """``config``: username, api_key, mode (secrets stay in memory only)."""
    if name in _REGISTRY:
        return _REGISTRY[name](config)
    if name == "manual":
        return ManualPostalProvider()
    if name == "letterxpress":
        username, api_key = config.get("username"), config.get("api_key")
        if not username or not api_key:
            raise PostalProviderError("LetterXpress: Benutzername und API-Key fehlen.")
        return LetterXpressProvider(str(username), str(api_key), str(config.get("mode") or "test"))
    raise PostalProviderError(f"Unbekannter Postdienst: {name}")
