"""AE31 (AD06-01 to AD06-03): rules of the online meeting without database. Expected values by
hand: the matrix of ``decide_conflict`` per mode and source order, the checklist of recorded
facts for presence, hybrid and virtual meetings, and the protocol sentence of a conflict."""

from datetime import date

import pytest

from mhvp.hoa import online_rules as r


@pytest.mark.parametrize(
    ("mode", "first", "second", "expected"),
    [
        # same source twice is always a duplicate
        ("flag", "own", "own", r.DUPLICATE),
        ("flag", "proxy", "proxy", r.DUPLICATE),
        ("proxy_priority", "own", "own", r.DUPLICATE),
        # default: mark for review in both directions
        ("flag", "own", "proxy", r.REVIEW),
        ("flag", "proxy", "own", r.REVIEW),
        # first vote counts: second refused in both directions
        ("first_vote", "own", "proxy", r.REJECT),
        ("first_vote", "proxy", "own", r.REJECT),
        # proxy priority: proxy replaces own, own against proxy refused
        ("proxy_priority", "own", "proxy", r.REPLACE),
        ("proxy_priority", "proxy", "own", r.REJECT),
        # own priority: mirror image
        ("own_priority", "proxy", "own", r.REPLACE),
        ("own_priority", "own", "proxy", r.REJECT),
        # unknown value behaves like the conservative default
        ("unknown", "own", "proxy", r.REVIEW),
    ],
)
def test_decide_conflict_matrix(mode: str, first: str, second: str, expected: str) -> None:
    assert r.decide_conflict(mode, first, second) == expected


def test_default_mode_is_conservative_and_listed() -> None:
    assert r.DEFAULT_PROXY_CONFLICT_MODE == "flag"
    assert set(r.PROXY_CONFLICT_MODES) == set(r.MODE_LABELS)
    assert "keine Stimme verwerfen" in r.MODE_LABELS["flag"]


def test_vote_source_prefers_stored_value() -> None:
    assert r.vote_source(None) == "own"
    assert r.vote_source(object()) == "proxy"
    assert r.vote_source(None, cast_source="proxy") == "proxy"
    assert r.vote_source(object(), cast_source="own") == "own"
    assert r.vote_source(None, cast_source="garbage") == "own"


BASE = {
    "meeting_day": date(2027, 3, 4),
    "online_switch": True,
    "virtual_switch": True,
    "basis_number": 7,
    "basis_decided_on": date(2026, 3, 1),
    "basis_status": "final",
    "valid_until": date(2029, 1, 1),
    "transition_date": None,
    "has_conference_link": True,
    "conflict_mode": "flag",
}


def _states(result: dict[str, object]) -> dict[str, str]:
    return {c["key"]: c["state"] for c in result["checks"]}  # type: ignore[attr-defined,index]


def test_presence_has_no_checks() -> None:
    result = r.admissibility_checks(mode="presence", **BASE)
    assert result["applicable"] is False
    assert result["checks"] == []


def test_virtual_complete_lists_recorded_facts_without_legal_statement() -> None:
    result = r.admissibility_checks(mode="virtual", **BASE)
    assert result["applicable"] is True
    assert result["complete"] is True
    assert _states(result) == {
        "online_switch": "ok",
        "virtual_switch": "ok",
        "basis_resolution": "ok",
        "valid_until": "ok",
        "term_limit": "ok",
        "conference_link": "ok",
        "vote_rule": "info",
    }
    text = " ".join(f"{c['label']} {c['detail']}" for c in result["checks"])  # type: ignore[attr-defined]
    assert "Beschluss Nr. 7 vom 01.03.2026" in text
    # the note never claims admissibility
    assert "prüft die rechtliche Zulässigkeit nicht" in str(result["note"])
    assert "zulässig ist" not in text


def test_virtual_missing_and_open_points() -> None:
    no_basis = r.admissibility_checks(
        mode="virtual", **(BASE | {"basis_status": None, "basis_decided_on": None})
    )
    assert no_basis["complete"] is False
    assert _states(no_basis)["basis_resolution"] == "missing"
    assert "valid_until" not in _states(no_basis)

    expired = r.admissibility_checks(mode="virtual", **(BASE | {"valid_until": date(2027, 3, 3)}))
    assert _states(expired)["valid_until"] == "missing"

    long_term = r.admissibility_checks(mode="virtual", **(BASE | {"valid_until": date(2030, 1, 1)}))
    assert _states(long_term)["term_limit"] == "open"
    assert "01.03.2029" in next(
        c["detail"]
        for c in long_term["checks"]  # type: ignore[attr-defined]
        if c["key"] == "term_limit"
    )

    contested = r.admissibility_checks(mode="virtual", **(BASE | {"basis_status": "contested"}))
    assert _states(contested)["basis_resolution"] == "open"
    annulled = r.admissibility_checks(mode="virtual", **(BASE | {"basis_status": "annulled"}))
    assert _states(annulled)["basis_resolution"] == "missing"

    switched_off = r.admissibility_checks(
        mode="virtual", **(BASE | {"online_switch": False, "virtual_switch": False})
    )
    assert _states(switched_off)["online_switch"] == "open"
    assert _states(switched_off)["virtual_switch"] == "open"

    no_link = r.admissibility_checks(mode="virtual", **(BASE | {"has_conference_link": False}))
    assert _states(no_link)["conference_link"] == "missing"


def test_transition_date_is_a_note_only() -> None:
    result = r.admissibility_checks(
        mode="virtual", **(BASE | {"transition_date": date(2026, 6, 30)})
    )
    assert _states(result)["transition"] == "info"
    assert result["complete"] is True


def test_hybrid_has_open_question_not_a_basis_check() -> None:
    result = r.admissibility_checks(mode="hybrid", **BASE)
    assert _states(result)["hybrid_basis"] == "open"
    assert "basis_resolution" not in _states(result)
    assert result["complete"] is False


def test_conflict_sentences() -> None:
    args = {
        "unit": "03",
        "first_source": "proxy",
        "first_choice": "yes",
        "second_source": "own",
        "second_choice": "no",
    }
    open_ = r.conflict_sentence(**args, status="open", resolution=None)
    assert "zuerst Bevollmächtigter: Ja, danach Eigentümer: Nein" in open_
    assert "Gezählt wird bis zur Entscheidung die erste Stimme (Bevollmächtigter: Ja)" in open_
    assert "Entscheidung der Versammlungsleitung offen" in open_
    assert "zweite Stimme zählen" in r.conflict_sentence(
        **args, status="resolved", resolution="apply_second"
    )
    assert "erste Stimme bestätigt" in r.conflict_sentence(
        **args, status="resolved", resolution="keep_first"
    )
    assert "Regel des Mandanten" in r.conflict_sentence(
        **args, status="resolved", resolution="rule_second"
    )


def test_texts_use_no_dashes_as_punctuation() -> None:
    texts = [r.ADMISSIBILITY_NOTE, r.CONFLICT_NOTE, *r.MODE_LABELS.values()]
    for text in texts:
        assert "\u2013" not in text
        assert "\u2014" not in text
