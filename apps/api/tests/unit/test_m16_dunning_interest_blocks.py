"""M16-02 interest over Basiszinssatz periods, M16-04 check hints, M16-06 spread proposal.

Expected values are computed by hand (0.1.8):
- 1.000,00 EUR, 01.01.2026 to 01.03.2026 (59 days) at base 2 + spread 5 = 7 %:
  1000 * 7 / 100 * 59 / 365 = 11,315... -> 11,32 EUR.
- Split at 01.02.2026: 31 days at 7 % = 5,945... -> 5,95 EUR; 28 days at base 1,5 + 5 = 6,5 %
  = 4,986... -> 4,99 EUR; total 10,94 EUR.
"""

import uuid
from datetime import date
from decimal import Decimal

from mhvp.accounting import dunning
from mhvp.accounting.models import DunningCase


def _settings(**kw: object) -> dunning.EffectiveSettings:
    base: dict[str, object] = {"property_id": None, "interest_enabled": True}
    base.update(kw)
    return dunning.EffectiveSettings(**base)  # type: ignore[arg-type]


def test_single_period_matches_previous_formula() -> None:
    result = dunning.interest_over_periods(
        [(date(2025, 7, 1), Decimal("2"))],
        Decimal("5"),
        Decimal("1000.00"),
        date(2026, 1, 1),
        date(2026, 3, 1),
    )
    assert result.amount == Decimal("11.32")
    assert len(result.periods) == 1
    assert result.periods[0]["days"] == 59
    assert result.periods[0]["rate"] == "7"


def test_base_rate_change_during_default_splits_period() -> None:
    result = dunning.interest_over_periods(
        [(date(2026, 2, 1), Decimal("1.5")), (date(2025, 7, 1), Decimal("2"))],
        Decimal("5"),
        Decimal("1000.00"),
        date(2026, 1, 1),
        date(2026, 3, 1),
    )
    assert [p["days"] for p in result.periods] == [31, 28]
    assert [p["amount"] for p in result.periods] == ["5.95", "4.99"]
    assert result.periods[0]["to"] == "2026-01-31"
    assert result.amount == Decimal("10.94")


def test_period_before_first_rate_computes_nothing() -> None:
    result = dunning.interest_over_periods(
        [(date(2026, 2, 1), Decimal("1.5"))],
        Decimal("5"),
        Decimal("1000.00"),
        date(2026, 1, 1),
        date(2026, 3, 1),
    )
    assert result.amount == Decimal("0.00")
    assert result.periods == []
    assert result.note is not None
    assert "01.01.2026" in result.note


def test_interest_for_history_wins_and_off_means_zero() -> None:
    rates = [(date(2025, 7, 1), Decimal("2"))]
    on = _settings(interest_base_rate=Decimal("9"), interest_spread=Decimal("5"))
    assert (
        dunning.interest_for(on, rates, Decimal("1000.00"), date(2026, 1, 1), date(2026, 3, 1))
    ).amount == Decimal("11.32")
    legacy = dunning.interest_for(
        _settings(interest_base_rate=Decimal("2"), interest_spread=Decimal("5")),
        [],
        Decimal("1000.00"),
        date(2026, 1, 1),
        date(2026, 3, 1),
    )
    assert legacy.amount == Decimal("11.32")
    off = _settings(interest_enabled=False, interest_base_rate=Decimal("2"))
    assert (
        dunning.interest_for(off, rates, Decimal("1000"), date(2026, 1, 1), date(2026, 3, 1))
    ).amount == Decimal("0.00")
    no_start = dunning.interest_for(on, rates, Decimal("1000"), None, date(2026, 3, 1))
    assert no_start.amount == Decimal("0.00")
    no_rate = dunning.interest_for(
        _settings(), [], Decimal("1000"), date(2026, 1, 1), date(2026, 3, 1)
    )
    assert no_rate.amount == Decimal("0.00")


def test_spread_suggestion_is_proposal_only() -> None:
    consumer = dunning.spread_suggestion(True)
    assert (consumer["profile"], consumer["spread"]) == ("verbraucher", "5")
    business = dunning.spread_suggestion(False)
    assert (business["profile"], business["spread"]) == ("unternehmer", "9")
    unknown = dunning.spread_suggestion(None)
    assert unknown["spread"] is None
    assert "nicht erfasst" in unknown["hinweis"]
    assert "keine rechtliche Feststellung" in consumer["hinweis"]


def test_check_hints_without_limitation_date() -> None:
    case = DunningCase(
        id=uuid.uuid4(),
        level=3,
        status="sent",
        due_date=date(2024, 3, 3),
        default_start=None,
        received_on=None,
    )
    hints = dunning.case_check_hints(case, date(2026, 9, 30))
    text = " ".join(hints)
    assert "03.03.2024" in text
    assert "berechnet kein Verjährungsdatum" in text
    assert "Verzugsbeginn nicht ableitbar" in text
    assert "gesondertem Auftrag" in text
    assert "Zugang der Mahnung nicht erfasst" in text
    early = DunningCase(
        id=uuid.uuid4(),
        level=1,
        status="proposed",
        due_date=None,
        default_start=date(2026, 1, 1),
        received_on=None,
    )
    assert dunning.case_check_hints(early, date(2026, 9, 30)) == []
