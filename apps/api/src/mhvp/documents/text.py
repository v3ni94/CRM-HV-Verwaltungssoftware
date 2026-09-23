"""Text extraction for the full text index (11.3, 11.4). OCR is not done here.

PDFs with a text layer and plain text files are indexed directly; everything else that may carry
text (scans, images of letters) is marked ``pending`` for OCR by Paperless or a later pipeline.
"""

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from mhvp.documents.models import TextStatus

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 1_000_000

# Accepted upload types (A-016). XML covers structured e-invoices (S02), kept unchanged.
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/heic",
        "text/plain",
        "text/csv",
        "application/xml",
        "text/xml",
        "message/rfc822",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/msword",
        "application/vnd.ms-excel",
        "application/zip",
    }
)

_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/tiff": (b"II*\x00", b"MM\x00*"),
    "application/zip": (b"PK\x03\x04",),
}


def sniff_matches(mime_type: str, data: bytes) -> bool:
    """Reject files whose content contradicts the declared type (no renamed executables)."""
    signatures = _SIGNATURES.get(mime_type)
    if mime_type.startswith("application/vnd.openxmlformats"):
        signatures = _SIGNATURES["application/zip"]
    return signatures is None or data.startswith(signatures)


def extract(mime_type: str, data: bytes) -> tuple[str | None, TextStatus]:
    if mime_type in ("text/plain", "text/csv", "application/xml", "text/xml", "message/rfc822"):
        return data.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS], TextStatus.EXTRACTED
    if mime_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except (PdfReadError, ValueError, KeyError) as exc:
            log.warning("pdf_text_extraction_failed", extra={"error": type(exc).__name__})
            return None, TextStatus.PENDING
        if text:
            return text[:MAX_TEXT_CHARS], TextStatus.EXTRACTED
        return None, TextStatus.PENDING
    if mime_type.startswith("image/"):
        return None, TextStatus.PENDING
    return None, TextStatus.NONE
