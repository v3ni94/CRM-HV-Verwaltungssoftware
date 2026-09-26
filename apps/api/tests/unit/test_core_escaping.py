"""Escaping helpers of the security review 26.09.2026: literal LIKE search terms (Befund 5)
and spreadsheet safe CSV cells (Befund 6)."""

from decimal import Decimal

from mhvp.core.escaping import csv_safe_cell, escape_like


def test_escape_like_neutralises_wildcards_and_escape_character() -> None:
    assert escape_like("Müller") == "Müller"
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("C:\\x") == "C:\\\\x"
    assert escape_like("%_\\") == "\\%\\_\\\\"


def test_csv_safe_cell_prefixes_formula_starters_only_for_strings() -> None:
    for start in ("=", "+", "-", "@", "\t", "\r"):
        assert csv_safe_cell(f"{start}cmd|' /C calc'!A0") == f"'{start}cmd|' /C calc'!A0"
    assert csv_safe_cell("Protokoll 2026") == "Protokoll 2026"
    assert csv_safe_cell("") == ""
    assert csv_safe_cell(None) is None
    assert csv_safe_cell(-12) == -12
    assert csv_safe_cell(Decimal("-1.50")) == Decimal("-1.50")
