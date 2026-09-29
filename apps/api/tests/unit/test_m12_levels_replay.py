"""Offline replay of the learning cycle and the level eligibility (plan M12 S11, rule 0.1.8):
``tests/ai_eval/levels_replay/cases.jsonl`` fixes, before the implementation ran, which
decision sequences yield a rule proposal (``!`` marks a rejection or reversal of the account,
``b:`` a bulk confirmation with half weight) and which figures reach a level. The replay uses
only the pure functions; no database, no model call."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from mhvp.automation.learning import Decision, trailing_streak
from mhvp.banking import learning, levels

CASES = Path(__file__).parents[1] / "ai_eval" / "levels_replay" / "cases.jsonl"
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CASES.read_text("utf-8").splitlines() if line.strip()]


def _replay_learning(case: dict[str, Any]) -> dict[str, Any]:
    decisions: list[Decision] = []
    bulk: set[str] = set()
    amounts: dict[str, Decimal] = {}
    for i, (raw, amount) in enumerate(zip(case["decisions"], case["amounts"], strict=True)):
        ident = f"d{i}"
        if raw.startswith("!"):
            decisions.append(Decision(ident, T0 + timedelta(days=i), f"tx{i}", rejected=raw[1:]))
            continue
        value = raw[2:] if raw.startswith("b:") else raw
        if raw.startswith("b:"):
            bulk.add(ident)
        decisions.append(Decision(ident, T0 + timedelta(days=i), f"tx{i}", value=value))
        amounts[ident] = Decimal(amount)
    streak = trailing_streak(decisions)
    streak_amounts = [amounts[d] for d in streak.decision_ids] if streak else []
    recurring = learning.is_recurring(streak_amounts)
    threshold = learning.threshold_for(recurring, threshold=5, recurring_threshold=3)
    count = learning.weighted_count(streak, bulk)
    return {"proposal": count >= threshold, "recurring": recurring, "threshold": threshold}


@pytest.mark.parametrize("case", [c for c in _cases() if "decisions" in c], ids=lambda c: c["id"])
def test_learning_replay_matches_fixed_expectations(case: dict[str, Any]) -> None:
    assert _replay_learning(case) == case["expect"]


@pytest.mark.parametrize("case", [c for c in _cases() if "level" in c], ids=lambda c: c["id"])
def test_level_replay_matches_fixed_expectations(case: dict[str, Any]) -> None:
    m = levels.ClassMetrics(
        case.get("class", "debtor_full"), None, date(2026, 7, 1), date(2026, 9, 29)
    )
    for key, value in case["metrics"].items():
        setattr(m, key, value)
    missing = levels.missing_for(case["level"], m, current=case.get("current", "L0"))
    assert (missing == []) is case["expect"]["eligible"], missing


def test_replay_set_has_learning_and_level_cases() -> None:
    cases = _cases()
    assert sum(1 for c in cases if "decisions" in c) >= 10
    assert sum(1 for c in cases if "level" in c) >= 6
