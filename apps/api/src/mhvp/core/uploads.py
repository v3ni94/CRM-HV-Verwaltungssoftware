"""Bounded reading and type checks for uploads and raw request bodies (GAI-313 to GAI-315).

``read_limited`` never holds more than ``max_bytes + 1`` bytes: it reads in chunks and aborts
with 413 (MHVP-DOC-0010) as soon as the limit is exceeded. ``read_body_limited`` does the same
for raw request bodies (webhooks), also without a Content-Length header."""

from __future__ import annotations

from typing import Any

from fastapi import Request, UploadFile

from mhvp.core.problems import ErrorCode, ErrorCodes, ProblemError

CHUNK_BYTES = 1024 * 1024
ZIP_MAGIC = b"PK\x03\x04"
_GENERIC_MIME = frozenset({"", "application/octet-stream", "binary/octet-stream"})
DUMP_EXTENSIONS = (".sql", ".txt", ".dump")
DUMP_MIME_TYPES = frozenset(
    {"application/sql", "application/x-sql", "text/x-sql", "text/sql", "text/plain"}
)
ZIP_EXTENSIONS = (".zip",)
ZIP_MIME_TYPES = frozenset({"application/zip", "application/x-zip-compressed", "application/x-zip"})


def too_large(detail: str | None = None) -> ProblemError:
    return ProblemError(ErrorCodes.UPLOAD_TOO_LARGE, detail=detail or "Die Datei ist zu groß.")


def _body_too_large(error: ErrorCode | None, detail: str | None) -> ProblemError:
    return ProblemError(
        error or ErrorCodes.UPLOAD_TOO_LARGE, detail=detail or "Anfragekörper zu groß."
    )


async def read_limited(file: UploadFile, max_bytes: int, *, detail: str | None = None) -> bytes:
    """Reads the upload in chunks; raises 413 once more than ``max_bytes`` were read."""
    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise too_large(detail)
    buf = bytearray()
    while True:
        chunk = await file.read(min(CHUNK_BYTES, max_bytes + 1 - len(buf)))
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise too_large(detail)
    return bytes(buf)


async def read_body_limited(
    request: Request, max_bytes: int, *, error: ErrorCode | None = None, detail: str | None = None
) -> bytes:
    """Raw request body for webhooks: Content-Length is checked first, the stream is aborted as
    soon as ``max_bytes`` is exceeded (chunked bodies without Content-Length included)."""
    header = request.headers.get("content-length")
    if header is not None:
        try:
            if int(header) > max_bytes:
                raise _body_too_large(error, detail)
        except ValueError:
            raise ProblemError(ErrorCodes.VALIDATION, detail="Content-Length ungültig.") from None
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise _body_too_large(error, detail)
    return bytes(buf)


def _mime(file: UploadFile) -> str:
    return (file.content_type or "").split(";")[0].strip().lower()


def check_file_kind(
    file: UploadFile,
    *,
    extensions: tuple[str, ...],
    mime_types: frozenset[str],
    label: str,
) -> None:
    """Rejects (422, MHVP-DOC-0003) a file whose extension is not in ``extensions`` or whose
    reported content type is neither in ``mime_types`` nor generic (octet-stream or empty)."""
    name = (file.filename or "").lower()
    mime = _mime(file)
    if not name.endswith(extensions) or (mime not in mime_types and mime not in _GENERIC_MIME):
        raise ProblemError(
            ErrorCodes.UPLOAD_REJECTED,
            detail=f"{label}: erlaubt sind Dateien mit der Endung {', '.join(extensions)}.",
        )


def check_dump_file(file: UploadFile) -> None:
    check_file_kind(
        file, extensions=DUMP_EXTENSIONS, mime_types=DUMP_MIME_TYPES, label="SQL-Export"
    )


def check_zip_file(file: UploadFile) -> None:
    check_file_kind(file, extensions=ZIP_EXTENSIONS, mime_types=ZIP_MIME_TYPES, label="ZIP-Archiv")


def check_zip_signature(data: bytes) -> None:
    """ZIP structure check: local file header signature (empty archives start with PK\\x05\\x06)."""
    if not (data.startswith(ZIP_MAGIC) or data.startswith(b"PK\x05\x06")):
        raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail="Kein gültiges ZIP-Archiv.")


def check_text_dump(data: bytes) -> None:
    """A SQL dump is text: a NUL byte or a ZIP/gzip signature in the head is refused."""
    head: Any = data[:4096]
    if b"\x00" in head or head.startswith((b"PK", b"\x1f\x8b")):
        raise ProblemError(ErrorCodes.UPLOAD_REJECTED, detail="Der Export ist keine Textdatei.")
