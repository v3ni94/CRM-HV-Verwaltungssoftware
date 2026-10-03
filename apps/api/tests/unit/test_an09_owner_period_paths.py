"""AN09 (AM03 rest, rule PROP-OWNER-PERIOD): the period check guards every creation path of a
property owner (assignment landlord, full contract import, AI property import), and the
recorder keeps the previous end of an owner period ended by an import for the undo."""

import asyncio
import uuid
from collections import Counter
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.ai import imports as ai_imports
from mhvp.contracts.models import ContractKind
from mhvp.core.problems import ProblemError
from mhvp.imports import vollimport_vertraege as vv
from mhvp.imports import zuordnung
from mhvp.properties import services as property_services
from mhvp.properties.models import PropertyOwner

PROBLEM = "Die Partei ist im Zeitraum bereits Eigentümer des Objekts (ab 01.01.2020)."


class _Session:
    def __init__(self, owner: Any = None) -> None:
        self.added: list[Any] = []
        self.owner = owner

    def add(self, row: Any) -> None:
        self.added.append(row)

    async def scalar(self, *_: Any) -> Any:
        return None

    async def get(self, *_: Any) -> Any:
        return self.owner

    async def flush(self) -> None:
        return None


def _problems(result: list[str]) -> Any:
    async def fake(*_: Any, **__: Any) -> list[str]:
        return result

    return fake


def test_landlord_refuses_conflicting_period(monkeypatch: pytest.MonkeyPatch) -> None:
    party = SimpleNamespace(id=uuid.uuid4())

    async def party_for(*_: Any) -> Any:
        return party, False

    monkeypatch.setattr(zuordnung, "party_for", party_for)
    monkeypatch.setattr(property_services, "owner_period_problems", _problems([PROBLEM]))
    session = _Session()
    report = zuordnung.Report(apply=True, start_date=date(2024, 1, 1), start_date_assumed=False)
    ctx = zuordnung._Ctx(
        session, uuid.uuid4(), None, date(2024, 1, 1), zuordnung.ContactIndex(), report
    )
    prop = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(ProblemError) as exc:
        asyncio.run(zuordnung._landlord(ctx, prop, uuid.uuid4()))  # type: ignore[arg-type]
    assert "bereits Eigentümer" in str(exc.value.detail)
    assert session.added == []


def test_full_import_owner_conflict_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(property_services, "owner_period_problems", _problems([PROBLEM]))
    session = _Session()
    ctx = vv._Ctx(session, uuid.uuid4(), None, {}, {}, {}, {}, {}, {}, set(), None)
    row = vv.ContractRow(
        line=3,
        kind=ContractKind.OWNERSHIP,
        contract_no="V1",
        object_raw="901",
        unit_no="01",
        contact_id="K1",
        start=date(2024, 7, 1),
    )
    counts: Counter[str] = Counter()
    prop = SimpleNamespace(id=uuid.uuid4())
    party = SimpleNamespace(id=uuid.uuid4())
    result = asyncio.run(vv._apply_owner_of_rental(ctx, row, prop, party, counts))  # type: ignore[arg-type]
    assert result is not None
    assert "bereits Eigentümer" in result["grund"]
    assert counts == Counter({"conflict": 1})
    assert session.added == []


def test_recorder_encodes_previous_end() -> None:
    session = _Session()
    run = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())
    rec = ai_imports.Recorder(session, run)  # type: ignore[arg-type]
    owner_id = uuid.uuid4()
    rec.add_owner_end(owner_id, None, date(2024, 6, 30))
    rec.add_owner_end(owner_id, date(2025, 12, 31), date(2024, 6, 30))
    types = [i.entity_type for i in session.added]
    assert types == ["property_owner_end::2024-06-30", "property_owner_end:2025-12-31:2024-06-30"]
    assert all(len(t) <= 63 for t in types)
    assert ai_imports._owner_end_values(types[0]) == (None, date(2024, 6, 30))
    assert ai_imports._owner_end_values(types[1]) == (date(2025, 12, 31), date(2024, 6, 30))


def _owner(valid_to: date | None) -> PropertyOwner:
    return PropertyOwner(
        id=uuid.uuid4(),
        property_id=uuid.uuid4(),
        party_id=uuid.uuid4(),
        valid_from=date(2020, 1, 1),
        valid_to=valid_to,
    )


def test_undo_restores_previous_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(property_services, "owner_period_problems", _problems([]))
    owner = _owner(date(2024, 6, 30))
    session = _Session(owner)
    item = "property_owner_end::2024-06-30"
    assert asyncio.run(ai_imports._referenced(session, item, owner.id)) is None  # type: ignore[arg-type]
    asyncio.run(ai_imports._remove(session, item, owner.id))  # type: ignore[arg-type]
    assert owner.valid_to is None


def test_undo_keeps_end_changed_after_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(property_services, "owner_period_problems", _problems([]))
    session = _Session(_owner(date(2024, 3, 31)))
    reason = asyncio.run(
        ai_imports._referenced(session, "property_owner_end::2024-06-30", uuid.uuid4())  # type: ignore[arg-type]
    )
    assert reason == "Ende des Eigentümers nach dem Import geändert"


def test_undo_keeps_end_when_restoring_overlaps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(property_services, "owner_period_problems", _problems([PROBLEM]))
    session = _Session(_owner(date(2024, 6, 30)))
    reason = asyncio.run(
        ai_imports._referenced(session, "property_owner_end::2024-06-30", uuid.uuid4())  # type: ignore[arg-type]
    )
    assert reason is not None
    assert "Überschneidung" in reason
