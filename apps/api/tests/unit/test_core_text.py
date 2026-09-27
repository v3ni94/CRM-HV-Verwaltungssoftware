"""``mhvp.core.text``: NUL and other invalid control characters never reach a stored column or a
JSONB value (Betreibermeldung 27.09.2026, Gmail-Abruf)."""

from mhvp.core.text import clean_json, strip_nul


def test_strip_nul_removes_nul_byte() -> None:
    assert strip_nul("Heizung\x00 defekt") == "Heizung defekt"


def test_strip_nul_keeps_newline_carriage_return_and_tab() -> None:
    assert strip_nul("Zeile 1\nZeile 2\r\n\tEingerückt") == "Zeile 1\nZeile 2\r\n\tEingerückt"


def test_strip_nul_removes_other_c0_control_characters() -> None:
    assert strip_nul("a\x01\x08\x0b\x0c\x1f\x7fb") == "ab"


def test_strip_nul_passes_none_through() -> None:
    assert strip_nul(None) is None


def test_strip_nul_leaves_clean_text_untouched() -> None:
    assert strip_nul("Müller Holding AG") == "Müller Holding AG"


def test_clean_json_cleans_nested_strings_and_keys() -> None:
    dirty = {
        "subject": "Betreff\x00 mit Fehler",
        "attachments": [{"filename": "anhang\x00.pdf", "size": 42}],
        "flag\x00": True,
        "empty": None,
    }
    cleaned = clean_json(dirty)
    assert cleaned == {
        "subject": "Betreff mit Fehler",
        "attachments": [{"filename": "anhang.pdf", "size": 42}],
        "flag": True,
        "empty": None,
    }


def test_clean_json_passes_scalars_through() -> None:
    assert clean_json(42) == 42
    assert clean_json(True) is True
    assert clean_json(None) is None
