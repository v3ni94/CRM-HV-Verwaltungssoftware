"""M25-01: evaluation of majority rules per subject kind (pure, predefined expected results).
Test values only, no legal claim about the rules of a community."""

import pytest

from mhvp.hoa.majority import (
    DEFAULT_HINT,
    DEFAULT_RULE,
    NOT_CHECKABLE,
    NOT_REACHED,
    REACHED,
    RuleSpec,
    evaluate,
    rule_text,
)


def rule(kind: str, basis: str = "heads", n: int | None = None, d: int | None = None) -> RuleSpec:
    return RuleSpec(
        majority_type=kind,
        counting_basis=basis,
        custom_numerator=n,
        custom_denominator=d,
        source="Gemeinschaftsordnung § 7, zu prüfen",
        approved=True,
    )


def votes(
    yes: str, no: str, abstain: str = "0", principle: str = "head", **kw: str
) -> dict[str, str]:
    return {"principle": principle, "yes": yes, "no": no, "abstain": abstain, **kw}


@pytest.mark.parametrize(
    ("kind", "yes", "no", "expected"),
    [
        ("simple", "5", "4", REACHED),
        ("simple", "4", "4", NOT_REACHED),
        ("simple", "0", "0", NOT_REACHED),
        ("qualified_2_3", "6", "3", REACHED),  # exactly 2/3 counts as at least
        ("qualified_2_3", "5", "3", NOT_REACHED),
        ("qualified_3_4", "6", "2", REACHED),
        ("qualified_3_4", "5", "2", NOT_REACHED),
        ("qualified_2_3", "0", "0", NOT_REACHED),
    ],
)
def test_share_rules(kind: str, yes: str, no: str, expected: str) -> None:
    assert evaluate(rule(kind), votes(yes, no, "10"), "maintenance")["result"] == expected


def test_abstentions_are_not_counted() -> None:
    assert evaluate(rule("qualified_3_4"), votes("3", "1", "20"), "other")["result"] == REACHED


def test_custom_fraction() -> None:
    r = rule("custom", n=3, d=5)
    assert evaluate(r, votes("3", "2"), "other")["result"] == REACHED
    assert evaluate(r, votes("5", "4"), "other")["result"] == NOT_REACHED
    assert "3/5" in evaluate(r, votes("3", "2"), "other")["rule_text"]


def test_custom_without_fraction_not_checkable() -> None:
    assert evaluate(rule("custom"), votes("3", "2"), "other")["result"] == NOT_CHECKABLE


def test_unanimous() -> None:
    r = rule("unanimous")
    assert evaluate(r, votes("8", "0", eligible="8"), "other")["result"] == REACHED
    assert evaluate(r, votes("7", "0", "1", eligible="8"), "other")["result"] == NOT_REACHED
    assert evaluate(r, votes("7", "0", eligible="8"), "other")["result"] == NOT_REACHED
    missing = evaluate(r, votes("8", "0"), "other")
    assert missing["result"] == NOT_CHECKABLE
    assert "Stimmberechtigten" in missing["reason"]


@pytest.mark.parametrize(("basis", "principle"), [("shares", "mea"), ("units", "unit")])
def test_counting_basis_matches(basis: str, principle: str) -> None:
    v = votes("0.6", "0.3", principle=principle)
    assert evaluate(rule("qualified_2_3", basis), v, "other")["result"] == REACHED


def test_counting_basis_mismatch_not_checkable() -> None:
    out = evaluate(rule("simple", "shares"), votes("5", "1"), "other")
    assert out["result"] == NOT_CHECKABLE
    assert "Zählbasis" in out["reason"]


def test_missing_rule_uses_default_with_hint() -> None:
    out = evaluate(DEFAULT_RULE, votes("3", "2"), "economic_plan")
    assert out["result"] == REACHED
    assert out["standard_rule"] is True
    assert DEFAULT_HINT in out["rule_text"]
    assert out["rule_text"].startswith("Wirtschaftsplan:")


def test_not_checkable_without_subject_or_votes() -> None:
    assert evaluate(DEFAULT_RULE, votes("3", "2"), None)["result"] == NOT_CHECKABLE
    assert evaluate(DEFAULT_RULE, {}, "other")["result"] == NOT_CHECKABLE
    assert evaluate(DEFAULT_RULE, {"principle": "head", "yes": "x"}, "other")["result"] == (
        NOT_CHECKABLE
    )


def test_unapproved_rule_is_marked() -> None:
    r = rule("simple").model_copy(update={"approved": False})
    assert "nicht fachlich freigegeben" in rule_text(r, "other")
