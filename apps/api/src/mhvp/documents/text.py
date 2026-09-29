"""Text extraction for the full text index (11.3, 11.4). OCR is not done here.

PDFs with a text layer and plain text files are indexed directly; everything else that may carry
text (scans, images of letters) is marked ``pending`` for OCR by Paperless or a later pipeline.
"""

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from mhvp.core.text import strip_nul
from mhvp.documents.models import TextStatus

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 1_000_000
# ``document.search_vector`` is a generated tsvector over title, filename and ``ocr_text``;
# PostgreSQL limits a tsvector to 1048575 bytes. Text is therefore capped by UTF-8 bytes,
# with headroom for title and filename (Betreibermeldung 30.09.2026, Gmail-Abruf).
MAX_TEXT_BYTES = 900_000


def cap_text(text: str) -> str:
    """Cut ``text`` to ``MAX_TEXT_CHARS`` characters and ``MAX_TEXT_BYTES`` UTF-8 bytes
    without splitting a character."""
    text = text[:MAX_TEXT_CHARS]
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_TEXT_BYTES:
        return text
    return encoded[:MAX_TEXT_BYTES].decode("utf-8", errors="ignore")


# Accepted upload types (A-016). XML covers structured e-invoices (S02), kept unchanged.
ALLOWED_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/heic",
        "image/heif",
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


# HEIF brands of the ISO base media file format (ISO/IEC 23008-12): still images and image
# sequences, HEVC coded or generic. AVIF and video brands (``isom``, ``mp42``) are no HEIC.
_HEIF_BRANDS: frozenset[bytes] = frozenset(
    {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"hevm", b"hevs", b"mif1", b"msf1"}
)
_HEIF_MIME_TYPES: frozenset[str] = frozenset({"image/heic", "image/heif"})


def _is_heif(data: bytes) -> bool:
    """A72: the first box is ``ftyp`` and its major brand or one of its compatible brands is a
    HEIF brand. A truncated box is judged on the bytes present; decoding (``sanitize_image``)
    still rejects a damaged image, this check only stops content of another kind."""
    if len(data) < 12 or data[4:8] != b"ftyp":
        return False
    if data[8:12] in _HEIF_BRANDS:
        return True
    box_size = int.from_bytes(data[0:4], "big")
    end = min(len(data), box_size) if box_size >= 16 else 16
    # Compatible brands follow major brand (4 bytes) and minor version (4 bytes).
    return any(data[i : i + 4] in _HEIF_BRANDS for i in range(16, end - 3, 4))


def sniff_matches(mime_type: str, data: bytes) -> bool:
    """Reject files whose content contradicts the declared type (no renamed executables)."""
    if mime_type in _HEIF_MIME_TYPES:
        return _is_heif(data)
    signatures = _SIGNATURES.get(mime_type)
    if mime_type.startswith("application/vnd.openxmlformats"):
        signatures = _SIGNATURES["application/zip"]
    return signatures is None or data.startswith(signatures)


def _decode(data: bytes) -> str:
    """UTF-8 (optional BOM), then Windows-1252, then Latin-1: German exports are often not
    UTF-8 and a silent replacement would destroy umlauts before the text is used anywhere."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def extract(mime_type: str, data: bytes) -> tuple[str | None, TextStatus]:
    # A NUL byte surviving in the decoded text (a raw .eml with a literal \x00 in its body,
    # rarely a PDF text stream) must never reach ``document.ocr_text``: PostgreSQL rejects it
    # like any other text column (Betreibermeldung 27.09.2026, Gmail-Abruf).
    if mime_type in ("text/plain", "text/csv", "application/xml", "text/xml", "message/rfc822"):
        cleaned = strip_nul(_decode(data)) or ""
        return cap_text(cleaned), TextStatus.EXTRACTED
    if mime_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except (PdfReadError, ValueError, KeyError) as exc:
            log.warning("pdf_text_extraction_failed", extra={"error": type(exc).__name__})
            return None, TextStatus.PENDING
        text = strip_nul(text) or ""
        if text:
            return cap_text(text), TextStatus.EXTRACTED
        return None, TextStatus.PENDING
    if mime_type.startswith("image/"):
        return None, TextStatus.PENDING
    return None, TextStatus.NONE
