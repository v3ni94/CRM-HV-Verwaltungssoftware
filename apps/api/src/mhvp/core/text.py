"""Text sanitizing shared by every path that stores content of external origin (mail bodies,
headers, contact names, attachment names, MIME parts, ...): PostgreSQL rejects a NUL (0x00)
byte in a ``TEXT``/``VARCHAR`` column and psycopg refuses ``\\u0000`` inside a JSONB value the
same way, so anything of that shape must be cleaned before it reaches a model or a JSONB field
(Betreibermeldung 27.09.2026, Postfach-Abruf: ``DataError: PostgreSQL text fields cannot
contain NUL (0x00) bytes``, Mandant Hausverwaltung Müller GmbH). Length limits stay with the
caller (the column definitions), this module only removes characters that must never be
stored."""

from typing import Any

# NUL plus the other C0 control characters that have no place in stored text (invisible,
# terminal-unsafe, some rejected outright); \n, \r and \t are kept because they are ordinary
# parts of a mail body or an address list.
_INVALID_CONTROL_CHARS = {c for c in range(0x00, 0x20) if c not in (0x09, 0x0A, 0x0D)} | {0x7F}
_TRANSLATE_TABLE = dict.fromkeys(_INVALID_CONTROL_CHARS, None)


def strip_nul(value: str | None) -> str | None:
    """Removes NUL bytes and the other invalid control characters from ``value``, keeping
    newline, carriage return and tab untouched. ``None`` stays ``None``."""
    if value is None:
        return None
    return value.translate(_TRANSLATE_TABLE)


def clean_json(value: Any) -> Any:
    """Recursively applies :func:`strip_nul` to every string inside a JSON-like structure (dict,
    list, tuple) before it is written to a JSONB column (for example ``Message.classification``
    or ``Message.suggestion``): psycopg refuses ``\\u0000`` there exactly as PostgreSQL refuses it
    in a text column. Dict keys are cleaned as well; numbers, booleans and ``None`` pass through
    unchanged."""
    if isinstance(value, str):
        return strip_nul(value)
    if isinstance(value, dict):
        return {
            (strip_nul(k) if isinstance(k, str) else k): clean_json(v) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    return value
