"""M12-05 (plan M12 S8): minimised examples of the same counterparty for the AI tie-breaker
and prompt v2; expected values fixed in advance (rule 0.1.8)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from mhvp.ai import tasks
from mhvp.ai.models import AiTask
from mhvp.automation.learning import Decision
from mhvp.banking import ai_posting
from mhvp.core.problems import ProblemError

AT = datetime(2026, 9, 1, tzinfo=UTC)


def test_amount_classes() -> None:
    assert ai_posting.amount_class(Decimal("-80.00")) == "bis_100"
    assert ai_posting.amount_class(Decimal("100.00")) == "bis_100"
    assert ai_posting.amount_class(Decimal("240.00")) == "bis_500"
    assert ai_posting.amount_class(Decimal("12000")) == "ueber_10000"


def test_examples_are_minimised_newest_first_with_counter_example() -> None:
    decisions = [
        Decision("d1", AT, "t1", value="6020"),
        Decision("d2", AT, "t2", rejected="6000"),
        Decision("d3", AT, "t3", value="1400+6020"),
    ]
    info = {
        "d1": (Decimal("-240.00"), "Wartung Aufzug Firma Schmidt", "Schmidt Aufzüge GmbH"),
        "d3": (Decimal("-260.00"), "Wartung Aufzug Oktober", "Schmidt Aufzüge GmbH"),
    }
    out = ai_posting.minimised_examples(decisions, info, exclude_names=["Schmidt Aufzüge GmbH"])
    assert [e["outcome"] for e in out] == ["confirmed", "rejected", "confirmed"]
    assert out[0]["accounts"] == ["1400", "6020"]
    assert "schmidt" not in out[2]["purpose_tokens"]
    assert out[2]["purpose_tokens"] == ["aufzug", "firma", "wartung"]
    assert all(set(e) <= ai_posting.EXAMPLE_KEYS for e in out)
    text = str(out)
    assert "240" not in text
    assert "Schmidt" not in text


def test_at_most_eight_examples() -> None:
    decisions = [Decision(f"d{i}", AT, f"t{i}", value="6020") for i in range(12)]
    assert len(ai_posting.minimised_examples(decisions, {}, exclude_names=[])) == 8


def _payload(examples: list[dict]) -> dict:
    return ai_posting.build_input(
        {"booking_date": "2026-09-01", "amount": "-240.00", "purpose": "Wartung"},
        "WEG",
        [{"number": "6020", "name": "Wartung"}],
        [],
        "104",
        [],
        examples=examples,
    )


def test_payload_without_examples_has_no_examples_key() -> None:
    assert "examples" not in _payload([])


def test_assert_minimised_refuses_foreign_keys_and_name_tokens() -> None:
    good = {"direction": "out", "amount_class": "bis_500", "purpose_tokens": ["wartung"],
            "accounts": ["6020"], "outcome": "confirmed"}  # fmt: skip
    ai_posting.assert_minimised(_payload([good]))
    with pytest.raises(ProblemError):
        ai_posting.assert_minimised(_payload([{**good, "name": "Schmidt"}]))
    with pytest.raises(ProblemError):
        ai_posting.assert_minimised(_payload([{**good, "purpose_tokens": ["re4711"]}]))
    with pytest.raises(ProblemError):
        ai_posting.assert_minimised(_payload([{**good, "accounts": ["DE89"]}]))


def test_prompt_v2_mentions_examples_and_counter_examples() -> None:
    v2 = tasks.prompt(AiTask.PROPOSE_POSTING, "v2").system
    assert "examples (optional)" in v2
    assert "Gegenbeispiel" in v2
    assert "ausschließlich Kontonummern aus accounts" in v2
