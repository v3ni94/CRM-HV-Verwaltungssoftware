"""Review 26.09.2026, H3: the automatic invoice forwarding carries the attachments of the
original mail and archives the original only when every attachment went out."""

import uuid
from email import message_from_bytes
from email.policy import default
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.communication import forwarding_dispatch as fd
from mhvp.core.config import Settings


def _message(**overrides: Any) -> Any:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "mailbox_id": uuid.uuid4(),
        "subject": "Rechnung 4711",
        "body": "Anbei die Rechnung.",
        "from_address": "lieferant@example.org",
        "gmail_message_id": "g-1",
        "attachment_document_ids": [uuid.uuid4()],
    }
    return SimpleNamespace(**(base | overrides))


def test_build_forward_carries_pdf_attachment() -> None:
    raw = fd._build_forward(
        _message(), "buchhaltung@example.org", [("rechnung.pdf", "application/pdf", b"%PDF-1.4")]
    )
    parsed = message_from_bytes(raw, policy=default)
    attachments = list(parsed.iter_attachments())
    assert [a.get_filename() for a in attachments] == ["rechnung.pdf"]
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_payload(decode=True) == b"%PDF-1.4"
    assert parsed["To"] == "buchhaltung@example.org"
    assert parsed["Reply-To"] == "lieferant@example.org"
    assert "Anbei die Rechnung." in parsed.get_body(("plain",)).get_content()  # type: ignore[union-attr]


class _FakeClient:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.archived: list[str] = []

    async def send_raw(self, raw: bytes) -> str:
        self.sent.append(raw)
        return "sent-1"

    async def archive(self, message_id: str) -> None:
        self.archived.append(message_id)

    async def aclose(self) -> None:
        return None


class _FakeSession:
    def __init__(self, mailbox: Any) -> None:
        self.mailbox = mailbox
        self.added: list[Any] = []

    async def get(self, model: Any, key: Any) -> Any:
        return self.mailbox

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


@pytest.fixture
def wired(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeClient, _FakeSession, Any]:
    client = _FakeClient()
    mailbox = SimpleNamespace(
        kind="gmail", archive_on_ticket_done=True, archive_scope_missing=False
    )
    session = _FakeSession(mailbox)

    async def oauth(*_: Any) -> tuple[str, str]:
        return "cid", "secret"

    monkeypatch.setattr(fd, "oauth_client", oauth)
    monkeypatch.setattr(fd, "make_client", lambda *_: client)
    return client, session, mailbox


@pytest.mark.asyncio
async def test_forward_with_all_attachments_archives_original(
    wired: tuple[_FakeClient, _FakeSession, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, session, _ = wired
    message = _message()

    async def load(*_: Any) -> tuple[list[tuple[str, str, bytes]], int]:
        return [("rechnung.pdf", "application/pdf", b"%PDF")], 1

    monkeypatch.setattr(fd, "load_attachments", load)
    await fd.forward_and_archive(session, SimpleNamespace(), uuid.uuid4(), None, message, "b@x.org")  # type: ignore[arg-type]
    parsed = message_from_bytes(client.sent[0], policy=default)
    assert len(list(parsed.iter_attachments())) == 1
    assert client.archived == ["g-1"]
    event = session.added[0]
    assert event.type == "message.forwarded"
    assert (event.payload["attachments"], event.payload["archived"]) == (1, True)


@pytest.mark.asyncio
async def test_forward_without_attachment_keeps_original_in_inbox(
    wired: tuple[_FakeClient, _FakeSession, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing blob (or a mail without attachments) still forwards the text but never
    removes the original from the inbox, so the invoice stays visible."""
    client, session, _ = wired

    async def missing(*_: Any) -> tuple[list[tuple[str, str, bytes]], int]:
        return [], 1

    monkeypatch.setattr(fd, "load_attachments", missing)
    await fd.forward_and_archive(
        cast(AsyncSession, session),
        cast(Settings, SimpleNamespace()),
        uuid.uuid4(),
        None,
        _message(),
        "b@x.org",
    )
    assert len(client.sent) == 1
    assert client.archived == []
    assert session.added[0].payload["archived"] is False

    async def none(*_: Any) -> tuple[list[tuple[str, str, bytes]], int]:
        return [], 0

    monkeypatch.setattr(fd, "load_attachments", none)
    await fd.forward_and_archive(
        cast(AsyncSession, session),
        cast(Settings, SimpleNamespace()),
        uuid.uuid4(),
        None,
        _message(attachment_document_ids=[]),
        "b@x.org",
    )
    assert client.archived == []
