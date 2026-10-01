"""S16-03: secrets never reach logs, domain events or the audit trail in plain text."""

import json
import logging
import uuid
from io import StringIO
from typing import Any

import pytest
import structlog

from mhvp.core import events
from mhvp.core.redaction import REDACTED, is_secret_key, redact, redact_event, redact_path


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "PIN",
        "token",
        "api_key",
        "client_secret",
        "smtp_password",
        "webhook_secret",
        "access_token",
        "auth_header_value",
        "credentials",
        "private_key",
        "secret_enc",
    ],
)
def test_secret_keys(key: str) -> None:
    assert is_secret_key(key)


@pytest.mark.parametrize(
    "key", ["token_invalid", "api_key_last4", "token_hash", "username", "iban", "tokens_in", 1]
)
def test_non_secret_keys(key: object) -> None:
    assert not is_secret_key(key)


def test_redact_nested_keeps_keys_and_none() -> None:
    data = {
        "username": "u",
        "password": "geheim",
        "nested": [{"api_key": "sk-123", "mode": "test"}],
        "smtp_password": {"old": "a", "new": "b"},
        "pin": None,
    }
    out = redact(data)
    assert out == {
        "username": "u",
        "password": REDACTED,
        "nested": [{"api_key": REDACTED, "mode": "test"}],
        "smtp_password": REDACTED,
        "pin": None,
    }
    assert data["password"] == "geheim"  # input untouched


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v1/letting/self-disclosure/abc.def", "/api/v1/letting/self-disclosure/[redacted]"),
        ("/portal/selbstauskunft/abc", "/portal/selbstauskunft/[redacted]"),
        (
            "/api/v1/workspace/calendar-feed/tok123.ics",
            "/api/v1/workspace/calendar-feed/[redacted].ics",
        ),
        ("/api/v1/properties/123", "/api/v1/properties/123"),
    ],
)
def test_redact_path(path: str, expected: str) -> None:
    assert redact_path(path) == expected


def test_log_processor_and_real_logging() -> None:
    out = redact_event(None, "info", {"event": "x", "token": "t", "path": "/x/self-disclosure/t"})
    assert out == {"event": "x", "token": REDACTED, "path": "/x/self-disclosure/[redacted]"}

    from mhvp.core import logging as mhvp_logging

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=mhvp_logging._SHARED_PROCESSORS,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    logger = logging.getLogger("s16_03_test")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("login", extra={"password": "geheim-123"})
    finally:
        logger.removeHandler(handler)
    line = stream.getvalue()
    assert "geheim-123" not in line
    assert json.loads(line)["event"] == "login"


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


async def test_emit_redacts_payload_and_audit_changes() -> None:
    session = _Session()
    await events.emit(
        session,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        type="mailbox.updated",
        entity_type="mailbox",
        entity_id=None,
        actor_user_id=None,
        payload={"imap_password": "pw", "host": "imap.example"},
        changes=events.diff({"secret": "old"}, {"secret": "new"}),
    )
    event, audit = session.added
    assert event.payload == {"imap_password": REDACTED, "host": "imap.example"}
    assert audit.changes == {"secret": REDACTED}
    dumped = json.dumps(audit.changes)
    assert "old" not in dumped
    assert "new" not in dumped


# Columns with a secret like name that legitimately are not EncryptedText (reason given).
_PLAIN_SECRET_LIKE_COLUMNS = {
    # sha256 digest of the portal link token (S16-03), never the token itself
    ("self_disclosure_link", "token"),
    # Gmail paging cursor, no credential
    ("mailbox", "backfill_page_token"),
}


def test_every_secret_column_is_encrypted_and_rotated() -> None:
    """Guard: a new column named like a secret must use EncryptedText (and is then picked up by
    the generic master key rotation in ``mhvp.core.key_rotation``)."""
    import mhvp.models  # noqa: F401
    from mhvp.core.crypto import EncryptedText
    from mhvp.core.db.base import Base
    from mhvp.core.key_rotation import discover_targets

    rotated = {(t.table.name, c) for t in discover_targets() for c in t.columns}
    offenders = []
    for table in Base.metadata.tables.values():
        for column in table.c:
            if not is_secret_key(column.name):
                continue
            if (table.name, column.name) in _PLAIN_SECRET_LIKE_COLUMNS:
                continue
            if not isinstance(column.type, EncryptedText):
                offenders.append(f"{table.name}.{column.name}")
            else:
                assert (table.name, column.name) in rotated
    assert offenders == []
