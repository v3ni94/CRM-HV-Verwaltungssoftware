"""Malware scan of every document before it is stored (operator decision 27.09.2026).

The scan talks to a ``clamd`` daemon over TCP with the ``INSTREAM`` command: the file bytes
are streamed in length prefixed chunks, the daemon answers ``stream: OK``,
``stream: <signature> FOUND`` or ``stream: <reason> ERROR``. Nothing is written to disk and
no other process sees the file. Modes (``MHVP_CLAMAV_MODE``):

* ``off``: no scan (development and tests). Not allowed in prod and staging.
* ``warn``: a finding rejects the file; an unreachable scanner lets the file through and is
  journaled as ``document.scan_skipped`` so the operator sees the gap.
* ``enforce``: a finding rejects the file; an unreachable scanner refuses the upload with
  ``MHVP-DOC-0009`` (503) and nothing is stored.

A finding always answers ``MHVP-DOC-0008`` (422) and is journaled as
``document.malware_rejected`` with the signature name; the blob is never stored. The audit
entry is written in its own transaction so that the rollback of the rejected request does
not discard it.
"""

import logging
import socket
import struct
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from mhvp.core.config import Settings
from mhvp.core.db.tenancy import tenant_transaction
from mhvp.core.events import emit
from mhvp.core.problems import ErrorCodes, ProblemError

log = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024
EVENT_REJECTED = "document.malware_rejected"
EVENT_SKIPPED = "document.scan_skipped"
_FOUND = "Die Datei wurde wegen eines Schadsoftwarefunds abgewiesen und nicht gespeichert."
_UNAVAILABLE = (
    "Die Schadsoftwareprüfung ist derzeit nicht möglich. Es wurde nichts gespeichert, "
    "bitte später erneut versuchen."
)


class ScanMode(StrEnum):
    OFF = "off"
    WARN = "warn"
    ENFORCE = "enforce"


class ScanStatus(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


@dataclass(frozen=True)
class ScanResult:
    status: ScanStatus
    # Signature name for INFECTED, short non-sensitive reason for ERROR.
    detail: str | None = None


class ClamdScanner:
    """Minimal clamd client (INSTREAM over TCP). Synchronous; run in a thread if needed."""

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def ping(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(b"zPING\0")
                return _read_reply(sock) == "PONG"
        except OSError:
            return False

    def scan(self, data: bytes) -> ScanResult:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.sendall(b"zINSTREAM\0")
                for offset in range(0, len(data), CHUNK_SIZE):
                    chunk = data[offset : offset + CHUNK_SIZE]
                    sock.sendall(struct.pack("!I", len(chunk)) + chunk)
                sock.sendall(struct.pack("!I", 0))
                reply = _read_reply(sock)
        except OSError as exc:
            log.warning("clamd unreachable at %s:%s: %s", self.host, self.port, type(exc).__name__)
            return ScanResult(ScanStatus.ERROR, "unreachable")
        return parse_reply(reply)


def _read_reply(sock: socket.socket) -> str:
    buf = bytearray()
    while True:
        part = sock.recv(4096)
        if not part:
            break
        buf.extend(part)
        if buf.endswith(b"\0") or buf.endswith(b"\n"):
            break
    return bytes(buf).rstrip(b"\0\n").decode("utf-8", "replace").strip()


def parse_reply(reply: str) -> ScanResult:
    """Replies look like ``stream: OK``, ``stream: <signature> FOUND`` or ``<reason> ERROR``."""
    body = reply.split(":", 1)[1].strip() if ":" in reply else reply.strip()
    if body == "OK":
        return ScanResult(ScanStatus.CLEAN)
    if body.endswith(" FOUND"):
        return ScanResult(ScanStatus.INFECTED, body[: -len(" FOUND")].strip()[:200])
    if body.endswith("ERROR"):
        return ScanResult(ScanStatus.ERROR, body[: -len("ERROR")].strip()[:200] or "error")
    return ScanResult(ScanStatus.ERROR, "unexpected reply")


def scanner_from_settings(settings: Settings) -> ClamdScanner | None:
    if settings.clamav_mode == ScanMode.OFF.value:
        return None
    return ClamdScanner(settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds)


async def _journal(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    type: str,
    actor_user_id: uuid.UUID | None,
    payload: dict[str, Any],
) -> None:
    """Own transaction: survives the rollback of the rejected request (rule 0.1.7)."""
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    async with tenant_transaction(factory, tenant_id) as own:
        await emit(
            own,
            tenant_id=tenant_id,
            type=type,
            entity_type="document",
            entity_id=None,
            actor_user_id=actor_user_id,
            payload=payload,
        )


async def scan_before_store(
    session: AsyncSession,
    settings: Settings,
    *,
    tenant_id: uuid.UUID,
    data: bytes,
    filename: str,
    sha256: str,
    source: str,
    actor_user_id: uuid.UUID | None,
) -> ScanResult | None:
    """Scan ``data`` according to the configured mode. Returns None when the scan is off.

    Raises ``MHVP-DOC-0008`` on a finding (journaled with the signature) and, in enforce
    mode, ``MHVP-DOC-0009`` when the scanner cannot answer. In warn mode an unanswered scan is
    journaled as ``document.scan_skipped`` and the caller stores the file.
    """
    scanner = scanner_from_settings(settings)
    if scanner is None:
        return None
    result = scanner.scan(data)
    base = {"filename": filename[:255], "sha256": sha256, "size": len(data), "source": source}
    if result.status == ScanStatus.INFECTED:
        await _journal(
            session,
            tenant_id=tenant_id,
            type=EVENT_REJECTED,
            actor_user_id=actor_user_id,
            payload={**base, "signature": result.detail, "mode": settings.clamav_mode},
        )
        log.warning("document rejected by malware scan: %s (%s)", result.detail, sha256)
        raise ProblemError(ErrorCodes.MALWARE_FOUND, detail=_FOUND)
    if result.status == ScanStatus.ERROR:
        if settings.clamav_mode == ScanMode.ENFORCE.value:
            raise ProblemError(ErrorCodes.SCAN_UNAVAILABLE, detail=_UNAVAILABLE)
        await _journal(
            session,
            tenant_id=tenant_id,
            type=EVENT_SKIPPED,
            actor_user_id=actor_user_id,
            payload={**base, "reason": result.detail, "mode": settings.clamav_mode},
        )
    return result
