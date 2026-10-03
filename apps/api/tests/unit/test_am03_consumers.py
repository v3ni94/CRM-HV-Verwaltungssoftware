"""GAJ-608 and GAJ-609: the banking consumer recomputes pending snapshots on every payer
evidence event; the 80 percent budget warning notifies every member with the AI settings
permission (same recipients as the hard stop)."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.ai import gateway
from mhvp.banking import event_types as ev
from mhvp.banking import events_consumer, proposals


@pytest.mark.parametrize(
    "event_type",
    [
        "contact.deleted",
        "bank_account.approved",
        "bank_account.ended",
        "contact.mandate_iban_changed",
    ],
)
def test_payer_evidence_events_refresh_pending(
    monkeypatch: pytest.MonkeyPatch, event_type: str
) -> None:
    calls: list[Any] = []

    async def fake_refresh(session: Any) -> None:
        calls.append(session)

    monkeypatch.setattr(proposals, "refresh_pending", fake_refresh)
    assert event_type in events_consumer.HANDLED_TYPES
    event = SimpleNamespace(type=event_type, entity_id=uuid.uuid4(), payload={})
    asyncio.run(events_consumer._handle("s", uuid.uuid4(), event))  # type: ignore[arg-type]
    assert calls == ["s"]


def test_unrelated_event_is_not_handled() -> None:
    assert "bank_account.rejected" not in events_consumer.HANDLED_TYPES
    assert ev.CONTACT_DELETED in ev.PAYER_EVIDENCE_EVENTS


def test_budget_warning_notifies_settings_members(monkeypatch: pytest.MonkeyPatch) -> None:
    from mhvp.banking import tasks
    from mhvp.workspace import services as ws

    users = [uuid.uuid4(), uuid.uuid4()]
    sent: list[dict[str, Any]] = []

    async def fake_users(session: Any, tenant_id: Any, permission: str) -> list[uuid.UUID]:
        assert permission == "tenant_settings:update"
        return users

    async def fake_notify(session: Any, **kw: Any) -> Any:
        sent.append(kw)
        return object() if len(sent) == 1 else None  # second one already unread

    monkeypatch.setattr(tasks, "users_with_permission", fake_users)
    monkeypatch.setattr(ws, "notify", fake_notify)
    tenant = uuid.uuid4()
    count = asyncio.run(gateway.notify_budget_warning(None, tenant, "anthropic"))  # type: ignore[arg-type]
    assert count == 1
    assert [s["user_id"] for s in sent] == users
    assert all(s["kind"] == "ai.budget_warning" and s["target_id"] == tenant for s in sent)
    assert "80 Prozent" in sent[0]["title"]
    assert "(anthropic)" in sent[0]["body"]
