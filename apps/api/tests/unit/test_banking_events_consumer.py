"""Banking event consumer (ADR 0013): a ``bank_transaction.reviewed`` event without a reason
is skipped, the log never invents one (rule 0.1.3); with a reason the pending round of an
ignored transaction is closed as ignored with exactly that reason."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.banking import events_consumer, proposals
from mhvp.banking.models import TransactionStatus


def _event(payload: dict[str, Any]) -> Any:
    return SimpleNamespace(
        entity_id=uuid.uuid4(),
        payload=payload,
        actor_user_id=uuid.uuid4(),
        occurred_at=datetime.now(UTC),
    )


class _Session:
    def __init__(self, tx: Any) -> None:
        self.tx = tx

    async def get(self, model: Any, ident: Any, **kw: Any) -> Any:
        return self.tx


@pytest.mark.parametrize(
    "payload", [{"decision": "ignore"}, {"decision": "ignore", "reason": "  "}]
)
def test_reviewed_event_without_reason_is_skipped(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    calls: list[str] = []

    async def pending_for(session: Any, tx_id: Any) -> Any:
        calls.append("pending_for")
        return SimpleNamespace(id=uuid.uuid4())

    async def record_ignore(*args: Any, **kwargs: Any) -> Any:
        calls.append("record_ignore")

    monkeypatch.setattr(proposals, "pending_for", pending_for)
    monkeypatch.setattr(proposals, "record_ignore", record_ignore)
    tx = SimpleNamespace(id=uuid.uuid4(), status=TransactionStatus.IGNORED)
    session = cast(AsyncSession, _Session(tx))
    asyncio.run(events_consumer._on_transaction_reviewed(session, _event(payload)))
    assert calls == []


def test_reviewed_event_with_reason_closes_the_round_with_that_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending_id = uuid.uuid4()
    recorded: list[dict[str, Any]] = []

    async def pending_for(session: Any, tx_id: Any) -> Any:
        return SimpleNamespace(id=pending_id)

    async def record_ignore(session: Any, tx: Any, **kwargs: Any) -> Any:
        recorded.append(kwargs)

    monkeypatch.setattr(proposals, "pending_for", pending_for)
    monkeypatch.setattr(proposals, "record_ignore", record_ignore)
    tx = SimpleNamespace(id=uuid.uuid4(), status=TransactionStatus.IGNORED)
    event = _event({"decision": "ignore", "reason": "Fehlbuchung der Bank"})
    session = cast(AsyncSession, _Session(tx))
    asyncio.run(events_consumer._on_transaction_reviewed(session, event))
    assert recorded == [
        {
            "user_id": event.actor_user_id,
            "reason": "Fehlbuchung der Bank",
            "proposal_id": pending_id,
        }
    ]
