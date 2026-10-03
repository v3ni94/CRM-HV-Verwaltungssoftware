"""AM04 (GAJ-605 to GAJ-607): tenant switches of the per mail AI paths and the ``ai_task`` rule
action, each tested with the switch off and on, plus the ``ai:approve`` check for rules.

Expected values by hand: the three new switches default to on (former behaviour); off skips
the AI call entirely, on reaches it; a rule with an ``ai_task`` action needs ``ai:approve``."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.ai import automation
from mhvp.automation import services as auto_services
from mhvp.automation.routers import _assert_ai_task_permission
from mhvp.automation.schemas import AiTaskAction
from mhvp.communication import services as comm_services
from mhvp.core.auth.principal import TenantPrincipal
from mhvp.core.problems import ProblemError
from mhvp.tickets import proposals

NEW = ("realtime_mail_classification", "master_data_change_proposals", "automation_ai_task")


def _switch(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    async def fake(_session: Any, _name: str) -> bool:
        return value

    monkeypatch.setattr(automation, "is_enabled", fake)


def test_defaults_on_for_new_switches_and_off_for_old() -> None:
    values = automation.read_switches(None)
    assert all(values[name] is True for name in NEW)
    assert values["rent_increase_check"] is False
    assert values["batch_mail_classification"] is False
    row = SimpleNamespace(objektakte_classification={})
    after = automation.write_switches(row, {"realtime_mail_classification": False})  # type: ignore[arg-type]
    assert after["realtime_mail_classification"] is False
    assert after["automation_ai_task"] is True
    assert automation.read_switches(row)["realtime_mail_classification"] is False  # type: ignore[arg-type]


@pytest.mark.parametrize("enabled", [False, True])
async def test_realtime_classification_switch(
    monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    _switch(monkeypatch, enabled)
    calls: list[Any] = []

    async def fake_suggest(_s: Any, _st: Any, message: Any) -> dict[str, Any]:
        calls.append(message)
        return {"status": "ready", "category": "x"}

    from mhvp.communication import suggest

    monkeypatch.setattr(suggest, "suggest_for_message", fake_suggest)
    row = SimpleNamespace(id=uuid.uuid4(), suggestion=None, suggestion_status="none")
    await comm_services._queue_suggestion(
        None,  # type: ignore[arg-type]
        SimpleNamespace(ai_inline=True),  # type: ignore[arg-type]
        uuid.uuid4(),
        row,  # type: ignore[arg-type]
    )
    assert len(calls) == (1 if enabled else 0)
    assert row.suggestion_status == ("ready" if enabled else "none")


@pytest.mark.parametrize("enabled", [False, True])
async def test_master_data_proposal_switch(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    _switch(monkeypatch, enabled)
    lexo: list[Any] = []
    proposed: list[Any] = []

    async def fake_lexo(_s: Any, _t: Any, message: Any) -> None:
        lexo.append(message)

    async def fake_propose(*args: Any) -> None:
        proposed.append(args)

    monkeypatch.setattr(proposals.lexoffice_invoice_copy, "queue_for_message", fake_lexo)
    monkeypatch.setattr(proposals, "propose_contact_change", fake_propose)

    class _Session:
        async def get(self, *_a: Any) -> Any:
            return SimpleNamespace(id=uuid.uuid4())

    message = SimpleNamespace(id=uuid.uuid4(), ticket_id=uuid.uuid4(), direction="in")
    await proposals.queue_for_message(
        _Session(),  # type: ignore[arg-type]
        SimpleNamespace(ai_inline=True),  # type: ignore[arg-type]
        uuid.uuid4(),
        message,  # type: ignore[arg-type]
    )
    assert len(lexo) == 1  # deterministic check is never switched off
    assert len(proposed) == (1 if enabled else 0)


@pytest.mark.parametrize("enabled", [False, True])
async def test_ai_task_action_switch(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    _switch(monkeypatch, enabled)
    action = AiTaskAction(type="ai_task", task="summarize", instruction="Fasse zusammen.")
    rule = SimpleNamespace(id=uuid.uuid4())
    result = await auto_services._ai_task(
        None,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        rule=rule,  # type: ignore[arg-type]
        action=action,
        context={},
        dry_run=True,
        settings=SimpleNamespace(ai_inline=True),  # type: ignore[arg-type]
    )
    assert result["ok"] is enabled


def _principal(*perms: str) -> TenantPrincipal:
    return TenantPrincipal(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), permissions=frozenset(perms)
    )


def test_ai_task_rule_needs_ai_approve() -> None:
    actions = [{"type": "ai_task", "task": "summarize", "instruction": "x"}]
    with pytest.raises(ProblemError):
        _assert_ai_task_permission(_principal("tenant_settings:update"), actions)
    _assert_ai_task_permission(_principal("tenant_settings:update", "ai:approve"), actions)
    _assert_ai_task_permission(
        _principal("tenant_settings:update"), [{"type": "create_ticket", "title": "x"}]
    )
