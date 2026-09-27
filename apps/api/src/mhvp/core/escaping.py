"""Small escaping helpers for values that leave the application in a foreign syntax: SQL
``LIKE`` patterns built from user search terms, CSV cells opened in spreadsheet programs
(Sicherheitsreview 26.09.2026, Befunde 5 und 6) and upload filenames stored and later returned
in ``Content-Disposition`` (Sicherheitsreview 27.09.2026, Befund 4 / OE-M27-02-02)."""

import unicodedata
from typing import Any

LIKE_ESCAPE = "\\"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Extensions that indicate executable or script content when they trail another extension
# (e.g. ``rechnung.pdf.exe``), a classic double-extension trick to hide the real payload type
# from a user who only glances at the visible name. The MIME allowlist and magic byte check in
# ``mhvp.documents.text``/``services.check_upload`` already stop the content itself; this list
# only decides whether the *name* gets flagged for the audit trail.
DANGEROUS_DOUBLE_EXTENSIONS = frozenset(
    {
        "exe",
        "bat",
        "cmd",
        "com",
        "scr",
        "pif",
        "vbs",
        "vbe",
        "js",
        "jse",
        "wsf",
        "wsh",
        "msi",
        "msp",
        "dll",
        "sh",
        "bash",
        "ps1",
        "ps2",
        "jar",
        "app",
        "apk",
        "cpl",
        "gadget",
        "hta",
        "reg",
        "lnk",
    }
)


def escape_like(value: str, escape: str = LIKE_ESCAPE) -> str:
    """Escapes ``%``, ``_`` and the escape character itself so that a search term matches
    literally inside a ``LIKE``/``ILIKE`` pattern. Use together with
    ``column.ilike(f"%{escape_like(q)}%", escape=LIKE_ESCAPE)``."""
    return (
        value.replace(escape, escape + escape).replace("%", escape + "%").replace("_", escape + "_")
    )


def content_disposition(kind: str, filename: str) -> str:
    """``Content-Disposition`` value with a safe ASCII fallback and an RFC 8187 ``filename*``
    for the full UTF-8 name. Quotes, semicolons, backslashes, CR and LF never reach the header
    (Sicherheitsreview 1.22, Befund 9); an empty fallback becomes ``datei``."""
    from urllib.parse import quote

    if kind not in ("inline", "attachment"):
        raise ValueError(kind)
    stripped = "".join(c for c in filename if c not in '";\\\r\n' and 32 <= ord(c) < 127)
    fallback = stripped.strip() or "datei"
    return f"{kind}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def sanitize_filename(name: str, max_length: int = 255) -> tuple[str, bool]:
    """Normalises an uploaded file's display name before it is stored: drops any path
    component (``../``, absolute paths, both separators), removes control characters, brings
    the text to Unicode NFC and caps the length while keeping the last extension where
    possible. Returns ``(safe_name, flagged)``; ``flagged`` is ``True`` for a double extension
    ending in a known executable/script suffix (e.g. ``rechnung.pdf.exe``), which callers log
    or surface for review but which does not by itself block the upload — MIME allowlist and
    magic byte checks already gate the actual content (``services.check_upload``)."""
    text = unicodedata.normalize("NFC", name or "")
    text = text.replace("\\", "/").rsplit("/", 1)[-1]
    text = "".join(c for c in text if ord(c) >= 32 and c != "\x7f")
    text = text.strip().strip(".")
    if not text:
        text = "datei"
    parts = text.split(".")
    flagged = len(parts) > 2 and parts[-1].lower() in DANGEROUS_DOUBLE_EXTENSIONS
    if len(text) > max_length:
        if len(parts) > 1 and len(parts[-1]) < max_length:
            ext = "." + parts[-1]
            text = text[: max_length - len(ext)].rstrip(".") + ext
        else:
            text = text[:max_length]
    return text, flagged


def csv_safe_cell(value: Any) -> Any:
    """Neutralises spreadsheet formula injection: a string starting with ``=``, ``+``, ``-``,
    ``@``, tab or carriage return gets a leading apostrophe, which Excel and LibreOffice show as
    text. Non strings (numbers, dates, None) pass through unchanged so amounts keep their sign."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
