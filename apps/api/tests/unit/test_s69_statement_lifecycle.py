"""S69-01: shared status model helpers and the reserve statement snapshot (pure)."""

import uuid
from types import SimpleNamespace

import pytest

from mhvp.billing import statement_lifecycle as lifecycle
from mhvp.billing.owner_statement import OwnerStatementStatus
from mhvp.billing.status import StatementStatus, TransitionError, check_transition
from mhvp.hoa.reserve_statement import build_snapshot, digest


def test_owner_statement_enum_matches_shared_model() -> None:
    assert [s.value for s in OwnerStatementStatus] == [s.value for s in StatementStatus]


def test_owner_statement_cannot_be_resolved() -> None:
    with pytest.raises(TransitionError):
        check_transition(
            StatementStatus.INTERNALLY_APPROVED, StatementStatus.RESOLVED, is_hoa=False
        )
    check_transition(
        StatementStatus.INTERNALLY_APPROVED, StatementStatus.BOARD_REVIEWED, is_hoa=False
    )
    check_transition(StatementStatus.BOARD_REVIEWED, StatementStatus.ISSUED, is_hoa=False)
    with pytest.raises(TransitionError):
        check_transition(StatementStatus.ISSUED, StatementStatus.POSTED, is_hoa=False)


def test_four_eyes() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    assert lifecycle.four_eyes_violated(a, a, None)
    assert lifecycle.four_eyes_violated(a, b, a)
    assert lifecycle.four_eyes_violated(None, b)
    assert not lifecycle.four_eyes_violated(a, b, None)


def test_gated_targets() -> None:
    assert {
        StatementStatus.ISSUED,
        StatementStatus.DUE,
        StatementStatus.POSTED,
    } == lifecycle.GATED_TARGETS
    assert StatementStatus.CALCULATED not in lifecycle.APPROVED_OR_LATER


def test_log_entry() -> None:
    user = uuid.uuid4()
    row = lifecycle.log_entry(StatementStatus.DUE, StatementStatus.POSTED, user, "Beleg 7")
    assert (row["from"], row["to"], row["by"], row["note"]) == (
        "due",
        "posted",
        str(user),
        "Beleg 7",
    )


def test_reserve_snapshot_takes_reserve_block_unchanged() -> None:
    reserve = {"opening": "1000.00", "closing": "1250.00", "positions": [{"name": "Dach"}]}
    hoa = SimpleNamespace(
        id=uuid.uuid4(), year=2025, version=2, snapshot={"reserve": reserve}, snapshot_hash="h1"
    )
    r = SimpleNamespace(
        id=uuid.uuid4(),
        name="Dach",
        active=True,
        opening_balance="500.00",
        opening_year=2024,
        bank_account_id=None,
    )
    snap = build_snapshot(hoa, [r])  # type: ignore[arg-type]
    assert snap["reserve"] == {"opening": "1000.00", "closing": "1250.00"}
    assert snap["positions"] == [{"name": "Dach"}]
    assert snap["source_snapshot_hash"] == "h1"
    assert snap["per_position_reserve"][0]["opening_balance"] == "500.00"
    assert reserve["positions"] == [{"name": "Dach"}]  # source not mutated
    assert digest(snap) == digest(dict(snap))
    assert len(digest(snap)) == 64
