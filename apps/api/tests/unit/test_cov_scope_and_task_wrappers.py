"""Coverage: legal entity access scope (A37, ``mhvp.core.auth.scope``) and the Celery
wrappers of the workspace jobs (reminders, digest, compliance deadlines) without services."""

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.core.auth import scope
from mhvp.core.auth.principal import Principal
from mhvp.core.problems import ProblemError
from mhvp.workspace import tasks as ws_tasks

LE_A, LE_B = uuid.uuid4(), uuid.uuid4()


def _principal(**kw: Any) -> Principal:
    values: dict[str, Any] = {"user_id": uuid.uuid4(), "tenant_id": uuid.uuid4()}
    values.update(kw)
    return Principal(**values)


def test_scope_unrestricted_cases() -> None:
    assert scope.allowed_legal_entity_ids(None) is None
    assert scope.allowed_legal_entity_ids(_principal(api_key_id=uuid.uuid4())) is None
    assert (
        scope.allowed_legal_entity_ids(
            _principal(
                is_platform_admin=True, platform_access_reason="Support", roles=("tax_advisor",)
            )
        )
        is None
    )
    assert scope.allowed_legal_entity_ids(_principal(roles=())) is None
    assert scope.allowed_legal_entity_ids(_principal(roles=("tax_advisor", "standard"))) is None
    assert scope.is_restricted(_principal(roles=("standard",))) is False


def test_scope_restricted_tax_advisor() -> None:
    advisor = _principal(roles=("tax_advisor",), legal_entity_ids=(LE_A,))
    assert scope.allowed_legal_entity_ids(advisor) == frozenset({LE_A})
    assert scope.is_restricted(advisor) is True
    assert scope.legal_entity_allowed(advisor, LE_A) is True
    assert scope.legal_entity_allowed(advisor, LE_B) is False
    scope.ensure_legal_entity_allowed(advisor, LE_A)
    with pytest.raises(ProblemError) as excinfo:
        scope.ensure_legal_entity_allowed(advisor, LE_B)
    assert excinfo.value.status == 404  # never 403: existence is not disclosed
    nothing = _principal(roles=("tax_advisor",))
    assert scope.allowed_legal_entity_ids(nothing) == frozenset()
    assert scope.legal_entity_allowed(nothing, LE_A) is False


def test_session_principal_helpers() -> None:
    advisor = _principal(roles=("tax_advisor",), legal_entity_ids=(LE_B,))
    session = SimpleNamespace(info={scope.SESSION_PRINCIPAL_KEY: advisor})
    assert scope.session_principal(session) is advisor  # type: ignore[arg-type]
    assert scope.session_allowed_legal_entity_ids(session) == frozenset({LE_B})  # type: ignore[arg-type]
    scope.ensure_session_legal_entity_allowed(session, LE_B)  # type: ignore[arg-type]
    with pytest.raises(ProblemError):
        scope.ensure_session_legal_entity_allowed(session, LE_A)  # type: ignore[arg-type]
    worker = SimpleNamespace(info={})
    assert scope.session_principal(worker) is None  # type: ignore[arg-type]
    assert scope.session_allowed_legal_entity_ids(worker) is None  # type: ignore[arg-type]
    scope.ensure_session_legal_entity_allowed(worker, LE_A)  # type: ignore[arg-type]
    garbage = SimpleNamespace(info={scope.SESSION_PRINCIPAL_KEY: "nope"})
    assert scope.session_principal(garbage) is None  # type: ignore[arg-type]


def test_legal_entity_scope_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    advisor = _principal(
        roles=("tax_advisor",), legal_entity_ids=(LE_A,), permissions=frozenset({"ledgers:read"})
    )

    async def fake_principal(request: Any) -> Principal:
        return advisor

    monkeypatch.setattr(scope, "get_principal", fake_principal)
    dependency = scope.legal_entity_scope("ledgers:read")
    assert asyncio.run(dependency(SimpleNamespace())) == frozenset({LE_A})  # type: ignore[arg-type]
    with pytest.raises(ProblemError) as excinfo:
        asyncio.run(scope.legal_entity_scope("ledgers:update")(SimpleNamespace()))  # type: ignore[arg-type]
    assert excinfo.value.status == 403

    platform = _principal(tenant_id=None, permissions=frozenset({"ledgers:read"}))

    async def platform_principal(request: Any) -> Principal:
        return platform

    monkeypatch.setattr(scope, "get_principal", platform_principal)
    with pytest.raises(ProblemError):
        asyncio.run(dependency(SimpleNamespace()))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("task", "once"),
    [
        (ws_tasks.reminders, "reminders_once"),
        (ws_tasks.digest, "digest_once"),
        (ws_tasks.compliance_deadlines, "deadlines_once"),
    ],
)
def test_workspace_task_wrappers_call_once_with_settings(
    monkeypatch: pytest.MonkeyPatch, task: Any, once: str
) -> None:
    marker = object()
    seen: list[Any] = []

    async def fake_once(settings: Any, today: Any = None) -> dict[str, int]:
        seen.append((settings, today))
        return {"created": 3}

    monkeypatch.setattr(ws_tasks, "get_settings", lambda: marker)
    monkeypatch.setattr(ws_tasks, once, fake_once)
    assert task() == {"created": 3}
    assert seen == [(marker, None)]
