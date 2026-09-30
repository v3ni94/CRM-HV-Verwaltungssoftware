"""M8-05: keyword selection of the migrated journal training base (rule AI-HIST-01)."""

from mhvp.ai.journal_history import MAX_KEYWORDS, keywords


def test_keywords_longest_first_and_distinct() -> None:
    assert keywords("Stadtwerke Strom Strom Abschlag 12,50") == ["stadtwerke", "abschlag", "strom"]


def test_keywords_limit_and_short_words_dropped() -> None:
    text = " ".join(f"wort{chr(97 + i)}x" for i in range(10)).replace("wort", "wortlang")
    assert len(keywords(text + " ab der")) <= MAX_KEYWORDS
    assert keywords("ab der 12") == []
