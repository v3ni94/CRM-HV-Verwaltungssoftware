"""Central redaction of secret values (section 3.5, section 16, S16-03).

Secrets (API keys, tokens, passwords, PINs, webhook and HMAC secrets, private keys) must never
reach logs, domain events or the audit trail in plain text. This module is the single place
that decides which keys count as secret; it is applied

* as a structlog processor to every log record (``redact_event``),
* to ``payload`` and ``changes`` of :func:`mhvp.core.events.emit` (domain events, audit log),
* to logged request paths of the few routes that carry a bearer token in the path
  (``redact_path``: self disclosure links, calendar feed).

Matching is by key name only (exact name or a secret suffix); values are replaced, the key
stays so that the audit trail still shows *that* a secret changed.
"""

import re
from collections.abc import MutableMapping
from typing import Any

REDACTED = "[redacted]"

SECRET_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pin",
        "tan",
        "secret",
        "token",
        "api_key",
        "apikey",
        "api_secret",
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "authorization",
        "auth_header_value",
        "credentials",
        "private_key",
        "totp_secret",
        "master_key",
        "client_data",
        "dialog_data",
        "retry_data",
        "pending_tan",
        "secret_enc",
    }
)
SECRET_SUFFIXES: tuple[str, ...] = ("_password", "_secret", "_token", "_api_key", "_pin")

# Routes with a bearer token as path segment (never logged in clear).
_PATH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(/self-disclosure/)[^/]+"),
    re.compile(r"(/selbstauskunft/)[^/]+"),
    re.compile(r"(/calendar-feed/)[^/]+?(\.ics)?$"),
)


def is_secret_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    name = key.lower()
    return name in SECRET_KEYS or name.endswith(SECRET_SUFFIXES)


def redact(value: Any) -> Any:
    """Copy of ``value`` with every secret key's value replaced (dicts and lists, recursive)."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if is_secret_key(k) and v is not None else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    return value


def _replace(match: re.Match[str]) -> str:
    tail = match.group(2) if (match.lastindex or 0) >= 2 else None
    return match.group(1) + REDACTED + (tail or "")


def redact_path(path: object) -> object:
    if not isinstance(path, str):
        return path
    for pattern in _PATH_PATTERNS:
        path = pattern.sub(_replace, path)
    return path


def redact_event(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> dict[str, Any]:
    """structlog processor."""
    out: dict[str, Any] = {}
    for key, value in event_dict.items():
        if key in ("path", "instance"):
            out[key] = redact_path(value)
        elif is_secret_key(key) and value is not None:
            out[key] = REDACTED
        else:
            out[key] = redact(value) if isinstance(value, dict | list) else value
    return out
