"""AB10: due check points and the snapshot reference of the rule register (GA08-02, GA08-05).
Expected values by hand: a check point dated 01.03.2027 is due on 01.03.2027, not on 28.02.2027."""

import uuid
from datetime import date
from typing import Any

from mhvp.accounting import rule_register as rr
from mhvp.accounting.models import RuleVersion


def _row(**over: Any) -> RuleVersion:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "rule_id": "X-1",
        "version": 1,
        "title": "t",
        "effective_from": date(2027, 3, 1),
        "effective_to": None,
        "case_groups": [rr.CHECKPOINT_GROUP],
        "status": "draft",
    }
    values.update(over)
    return RuleVersion(**values)


def test_due_checkpoints_only_reached_open_checkpoint_entries() -> None:
    rows = [
        _row(),
        _row(rule_id="X-2", effective_from=date(2027, 1, 1), version=1),
        _row(rule_id="X-3", status="withdrawn"),
        _row(rule_id="X-4", case_groups=["Abrechnung"]),
    ]
    assert [r.rule_id for r in rr.due_checkpoints(rows, date(2027, 2, 28))] == ["X-2"]
    assert [r.rule_id for r in rr.due_checkpoints(rows, date(2027, 3, 1))] == ["X-2", "X-1"]
    assert rr.due_checkpoints([], date(2027, 3, 1)) == []


def test_snapshot_reference_keeps_id_and_effective_date() -> None:
    row = _row(rule_id=rr.SETTLEMENT_RULE_ID, effective_from=date(2024, 1, 1))
    ref = rr.snapshot_reference(row)
    assert ref == {
        "id": str(row.id),
        "rule_id": rr.SETTLEMENT_RULE_ID,
        "version": 1,
        "status": "draft",
        "effective_from": "2024-01-01",
    }
    assert rr.snapshot_reference(None) is None
