"""Learned bank rules (plan M12 S5, rule M12-06): pure helpers (pattern key, purpose tokens,
weighted evidence, recurring threshold, narrowing check) with fixed expectations, and the
streak semantics reused from ``mhvp.automation.learning`` on account patterns."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from mhvp.automation.learning import Decision, next_status, trailing_streak
from mhvp.banking import learning

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _d(i: int, value: str | None = None, *, rejected: str | None = None) -> Decision:
    return Decision(f"d{i}", T0 + timedelta(days=i), f"tx{i}", value=value, rejected=rejected)


def test_pattern_key_needs_a_counterparty() -> None:
    assert learning.pattern_key("le", "credit", None, "100001") is None
    assert learning.pattern_key("le", "credit", "fp:abc", "100001") == "le|credit|fp:abc|100001"


def test_purpose_tokens_common_no_stop_words_no_name_tokens() -> None:
    tokens = learning.purpose_tokens(
        [
            "Hausgeld März 2026 Müller Zahlung",
            "HAUSGELD April 2026 Müller",
            "Hausgeld Mai Müller danke",
        ],
        ["Familie Müller"],
    )
    assert tokens == ["hausgeld"]
    assert learning.purpose_tokens([], []) == []
    assert learning.purpose_tokens(["12345 RE 1", "12345 RE 2"], []) == []


def test_weighted_count_halves_bulk_confirmations() -> None:
    streak = trailing_streak([_d(i, "100001") for i in range(4)])
    assert streak is not None
    assert learning.weighted_count(streak, set()) == Decimal("4")
    assert learning.weighted_count(streak, {"d0", "d1"}) == Decimal("3.0")
    assert learning.weighted_count(None, set()) == Decimal("0")


def test_recurring_threshold_and_bounds() -> None:
    assert learning.is_recurring([Decimal("-80.00"), Decimal("-80.00"), Decimal("-80.00")]) is True
    assert learning.is_recurring([Decimal("-80.00"), Decimal("-81.00")]) is False
    assert learning.is_recurring([Decimal("-80.00")]) is False
    assert learning.threshold_for(True, threshold=5, recurring_threshold=3) == 3
    assert learning.threshold_for(False, threshold=5, recurring_threshold=3) == 5
    assert (
        learning.threshold_for(False, threshold=1, recurring_threshold=3) == learning.MIN_THRESHOLD
    )
    assert (
        learning.threshold_for(False, threshold=999, recurring_threshold=3)
        == learning.MAX_THRESHOLD
    )


def test_contradiction_ends_the_streak_and_rejection_doubles_the_evidence() -> None:
    five = [_d(i, "100001") for i in range(5)]
    assert trailing_streak(five) is not None
    assert trailing_streak([*five, _d(5, "100002")]).value == "100002"  # type: ignore[union-attr]
    assert trailing_streak([*five, _d(5, rejected="100001")]) is None  # reversal or Nein
    assert next_status(None, None, 5) == "proposed"
    assert next_status("rejected", 5, 6) == "rejected"
    assert next_status("rejected", 5, 10) == "proposed"
    assert next_status("accepted", None, 20) == "accepted"


def _proposal(**kw: Any) -> Any:
    base = {
        "amount_min": Decimal("80.00"),
        "amount_max": Decimal("120.00"),
        "purpose_tokens": ["wartung"],
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_narrowing_allowed_widening_refused() -> None:
    p = _proposal()
    assert (
        learning.narrows(
            p, amount_min=Decimal("90"), amount_max=Decimal("110"), tokens=["wartung", "aufzug"]
        )
        == []
    )
    assert learning.narrows(p, amount_min=Decimal("70"), amount_max=None, tokens=None) == [
        "Betragsuntergrenze unter der beobachteten Spanne"
    ]
    assert learning.narrows(p, amount_min=None, amount_max=Decimal("130"), tokens=None) == [
        "Betragsobergrenze über der beobachteten Spanne"
    ]
    assert learning.narrows(p, amount_min=None, amount_max=None, tokens=[]) == [
        "Zwecktoken des Vorschlags dürfen nicht entfernt werden"
    ]
    assert "Betragsspanne ungültig" in learning.narrows(
        p, amount_min=Decimal("110"), amount_max=Decimal("90"), tokens=None
    )
