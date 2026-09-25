"""Unit-Test: Keyword-Score der lokalen Playbook-Zuordnung (M20 Übernahme)."""

from mhvp.communication.suggest import MIN_PLAYBOOK_SCORE, score_playbook


def test_score_playbook_full_overlap() -> None:
    text = "Betreff: Heizungsausfall im Keller\nSeit heute ist die Heizung kalt."
    assert score_playbook(text, ["heizung", "keller"]) == 1.0


def test_score_playbook_partial_overlap_below_threshold() -> None:
    text = "Bitte prüfen Sie die Kaution für meine Wohnung, die Heizung ist aber in Ordnung."
    score = score_playbook(text, ["heizung", "keller", "wasserschaden", "notdienst"])
    assert 0 < score < MIN_PLAYBOOK_SCORE


def test_score_playbook_no_keywords() -> None:
    assert score_playbook("beliebiger Text", []) == 0.0


def test_score_playbook_no_match() -> None:
    assert score_playbook("Kündigung des Mietvertrags", ["heizung", "rohrbruch"]) == 0.0
