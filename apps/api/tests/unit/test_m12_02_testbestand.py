"""M12-06 (Lückenliste 30.09.2026, plan M12 S9): synthetic test set of 20 bank transactions
with outgoing cases (L2b) in ``tests/fixtures/banking/m12_02_testbestand.json``. The expected
case class and, where fixed, the open item of the best proposal are set in advance (rule
0.1.8). Synthetic only: it does not replace the anonymised HVM test set (OPEN_QUESTIONS
M12-02)."""

import json
from pathlib import Path
from typing import Any

import pytest

from mhvp.banking import levels
from mhvp.banking import posting_proposal as pp

FIXTURE = Path(__file__).parents[1] / "fixtures" / "banking" / "m12_02_testbestand.json"
CASES: list[dict[str, Any]] = json.loads(FIXTURE.read_text("utf-8"))["cases"]


def test_set_has_20_cases_with_at_least_ten_outgoing() -> None:
    assert len(CASES) == 20
    assert len({c["id"] for c in CASES}) == 20
    assert sum(1 for c in CASES if c["tx"]["amount"].startswith("-")) >= 10


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_class_and_best_item(case: dict[str, Any]) -> None:
    proposals = pp.propose(case["tx"], case["rules"], case["open_items"], case["payables"])
    dicts = [p.as_dict() for p in proposals]
    assert levels.classify(case["tx"], dicts) == case["expected"]["case_class"]
    expected_items = case["expected"].get("best_open_item_ids")
    if expected_items is not None:
        match = [p for p in dicts if p.get("source") == pp.SOURCE_MATCH]
        assert [s["open_item_id"] for s in match[0]["splits"]] == expected_items
