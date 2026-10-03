"""AO11 (AN09 rest, rule PROP-OWNER-PERIOD): conflict path of ``ai.imports.apply_property`` with a
recorded AI proposal (tests/ai_eval/extract_property, no network call). A rental owner whose
period conflicts is left out with a note, the import itself still succeeds."""

import asyncio
import json
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.ai import imports as ai_imports
from mhvp.ai import person_match
from mhvp.properties import services as property_services
from mhvp.properties.models import PropertyOwner

CASES = Path(__file__).parents[1] / "ai_eval" / "extract_property" / "cases.jsonl"
PROBLEM = "Die Partei ist im Zeitraum bereits Eigentümer des Objekts (ab 01.01.2020)."


class _Session:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, row: Any) -> None:
        if getattr(row, "id", 1) is None:
            row.id = uuid.uuid4()
        self.added.append(row)

    async def flush(self) -> None:
        for row in self.added:
            if getattr(row, "id", 1) is None:
                row.id = uuid.uuid4()

    async def scalar(self, *_: Any) -> Any:
        return None


def _proposal() -> dict[str, Any]:
    first = json.loads(CASES.read_text(encoding="utf-8").splitlines()[0])
    out: dict[str, Any] = first["recorded_output"]
    out["property"]["management_type"] = "rental"
    owner = out["parties"][0]
    owner["role"], owner["start_date"], owner["payments"] = "owner", "2024-01-01", []
    out["parties"] = [owner]
    return out


def _patch(monkeypatch: pytest.MonkeyPatch, problems: list[str]) -> None:
    async def noop(*_: Any, **__: Any) -> None:
        return None

    async def match(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(decision="new", best=None)

    async def contact(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(id=uuid.uuid4())

    async def party(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(id=uuid.uuid4())

    async def check(*_: Any, **__: Any) -> list[str]:
        return problems

    async def extras(*_: Any, **__: Any) -> list[Any]:
        return []

    for name in ("ensure_hoa_entity", "copy_key_templates", "owner_entity"):
        monkeypatch.setattr(property_services, name, noop)
    monkeypatch.setattr(property_services, "owner_period_problems", check)
    monkeypatch.setattr(person_match, "match_person", match)
    monkeypatch.setattr(ai_imports, "create_contact", contact)
    monkeypatch.setattr(ai_imports, "create_party", party)
    monkeypatch.setattr(ai_imports, "_apply_onboarding_extras", extras)


def _apply(session: _Session) -> dict[str, Any]:
    preview = ai_imports.property_preview(_proposal())
    run = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())
    principal = SimpleNamespace(tenant_id=run.tenant_id, user_id=uuid.uuid4())
    choice = SimpleNamespace(
        management_type="rental",
        number="AO11-1",
        name=None,
        as_of=date(2024, 1, 1),
        vat_percent_by_payment_type={},
    )
    return asyncio.run(ai_imports.apply_property(session, run, principal, preview, choice))  # type: ignore[arg-type]


def test_conflicting_owner_period_is_left_out_with_note(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [PROBLEM])
    session = _Session()
    result = _apply(session)
    assert not [r for r in session.added if isinstance(r, PropertyOwner)]
    assert any(
        "Eigentümer nicht angelegt" in n and "bereits Eigentümer" in n for n in result["notes"]
    )


def test_free_owner_period_creates_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, [])
    session = _Session()
    result = _apply(session)
    owners = [r for r in session.added if isinstance(r, PropertyOwner)]
    assert len(owners) == 1
    assert owners[0].valid_from == date(2024, 1, 1)
    assert not any("Eigentümer nicht angelegt" in n for n in result["notes"])
