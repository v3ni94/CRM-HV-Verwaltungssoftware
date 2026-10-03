"""GAM-407: webhook field selection ``minimal`` sends no personal data."""

import json
import uuid
from types import SimpleNamespace
from typing import Any

from mhvp.automation.schemas import WebhookAction
from mhvp.automation.services import webhook_body


def _rule() -> Any:
    return SimpleNamespace(id=uuid.uuid4(), name="R", tenant_id=uuid.uuid4())


CTX = {
    "type": "message.received",
    "entity_type": "message",
    "entity_id": "m1",
    "payload": {"from_address": "max@example.org"},
    "entity": {"from_address": "max@example.org", "subject": "Wasser"},
}


def test_minimal_scope_strips_entity_payload_and_rendered_extras() -> None:
    body = json.loads(
        webhook_body(
            _rule(), CTX, {"source": "mhvp", "who": "{{ entity.from_address }}"}, "minimal"
        )
    )
    text = json.dumps(body)
    assert "max@example.org" not in text
    assert body["entity"] is None
    assert body["event"]["payload"] is None
    assert body["event"]["entity_id"] == "m1"
    assert body["source"] == "mhvp"
    assert "who" not in body


def test_full_scope_is_default_and_unchanged() -> None:
    action = WebhookAction(type="webhook", url="https://hooks.example.org/x")
    assert action.payload_scope == "full"
    body = json.loads(webhook_body(_rule(), CTX, {}))
    assert body["entity"]["subject"] == "Wasser"
