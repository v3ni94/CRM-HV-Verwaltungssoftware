"""AO12-04 and AO12-05 (AO01): approval re-checks the remaining amount; no write off without a
person (API keys cannot satisfy the four eyes rule)."""

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from mhvp.accounting import write_offs
from mhvp.core.problems import ProblemError


class _Session:
    def __init__(self, item: Any) -> None:
        self.item = item

    async def get(self, *_: Any, **__: Any) -> Any:
        return self.item


def _row(proposed_by: uuid.UUID | None) -> Any:
    return SimpleNamespace(
        status="proposed",
        open_item_id=uuid.uuid4(),
        proposed_by=proposed_by,
        effective_on=date(2026, 9, 1),
        amount=Decimal("100.00"),
        decided_by=None,
        decided_at=None,
        decision_note=None,
    )


def test_propose_without_person_is_refused() -> None:
    item = SimpleNamespace(booking_date=date(2026, 1, 1))
    with pytest.raises(ProblemError) as exc:
        asyncio.run(
            write_offs.propose(
                _Session(item),  # type: ignore[arg-type]
                item,  # type: ignore[arg-type]
                effective_on=date(2026, 9, 1),
                reason="Uneinbringlich laut Vollstreckung",
                document_id=None,
                user_id=None,
            )
        )
    assert exc.value.error.code == "MHVP-ACC-0043"


def test_approve_legacy_proposal_without_person_is_refused() -> None:
    item = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(ProblemError) as exc:
        asyncio.run(
            write_offs.decide(
                _Session(item),  # type: ignore[arg-type]
                _row(None),
                decision="approve",
                note=None,
                user_id=uuid.uuid4(),
            )
        )
    assert exc.value.error.code == "MHVP-ACC-0043"


def test_approve_refused_when_remaining_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def remaining(*_: Any) -> Decimal:
        return Decimal("60.00")  # payment of 40.00 after the proposal

    monkeypatch.setattr(write_offs.acc, "remaining", remaining)
    item = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(ProblemError) as exc:
        asyncio.run(
            write_offs.decide(
                _Session(item),  # type: ignore[arg-type]
                _row(uuid.uuid4()),
                decision="approve",
                note=None,
                user_id=uuid.uuid4(),
            )
        )
    assert exc.value.error.code == "MHVP-ACC-0042"
    assert exc.value.status == 409
