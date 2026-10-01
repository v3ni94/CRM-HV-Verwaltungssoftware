"""M7-02: scoring and classification of the onboarding person match (pure functions)."""

from decimal import Decimal

from mhvp.ai import person_match as pm

LINK, SUGGEST = Decimal("0.90"), Decimal("0.60")


def test_iban_wins_and_links() -> None:
    score, reasons = pm.combine(
        iban=True, email=False, name_similarity=0.2, postal=False, street=False
    )
    assert score == 1.0
    assert reasons == ["gleiche IBAN"]
    assert pm.classify(score, LINK, SUGGEST) == "link"


def test_email_links_at_default_threshold() -> None:
    score, _ = pm.combine(iban=False, email=True, name_similarity=0.0, postal=False, street=False)
    assert pm.classify(score, LINK, SUGGEST) == "link"


def test_name_alone_only_suggests_and_address_raises() -> None:
    plain, _ = pm.combine(iban=False, email=False, name_similarity=0.7, postal=False, street=False)
    assert pm.classify(plain, LINK, SUGGEST) == "suggest"
    raised, reasons = pm.combine(
        iban=False, email=False, name_similarity=0.7, postal=True, street=True
    )
    assert round(raised, 2) == 0.95
    assert "gleiche Straße" in reasons[0]
    assert pm.classify(raised, LINK, SUGGEST) == "link"


def test_low_name_similarity_is_none_and_thresholds_are_configurable() -> None:
    score, _ = pm.combine(iban=False, email=False, name_similarity=0.4, postal=False, street=False)
    assert pm.classify(score, LINK, SUGGEST) == "none"
    assert pm.classify(score, Decimal("0.5"), Decimal("0.4")) == "suggest"


def test_no_signal_scores_zero() -> None:
    assert pm.combine(iban=False, email=False, name_similarity=0, postal=True, street=True) == (
        0.0,
        [],
    )
