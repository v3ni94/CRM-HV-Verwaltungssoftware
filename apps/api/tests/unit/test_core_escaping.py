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


def test_content_disposition() -> None:
    from mhvp.core.escaping import content_disposition

    # Sicherheitsreview 1.22, Befund 9: quotes, semicolons and line breaks never reach the
    # header; the full name travels percent encoded in filename*.
    assert (
        content_disposition("attachment", "Rechnung 2026.pdf")
        == "attachment; filename=\"Rechnung 2026.pdf\"; filename*=UTF-8''Rechnung%202026.pdf"
    )
    value = content_disposition("inline", 'a";b\r\nX-Injected: 1.pdf')
    assert value.startswith('inline; filename="abX-Injected: 1.pdf"; filename*=')
    assert "\r" not in value
    assert "\n" not in value
    assert '";b' not in value
    assert content_disposition("attachment", "Größe €.pdf").startswith(
        "attachment; filename=\"Gre .pdf\"; filename*=UTF-8''Gr%C3%B6%C3%9Fe%20%E2%82%AC.pdf"
    )
    assert (
        content_disposition("attachment", "äöü")
        == "attachment; filename=\"datei\"; filename*=UTF-8''%C3%A4%C3%B6%C3%BC"
    )
    try:
        content_disposition("form-data", "x")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("kind must be inline or attachment")
