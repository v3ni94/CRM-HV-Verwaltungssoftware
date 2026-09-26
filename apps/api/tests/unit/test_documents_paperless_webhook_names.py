"""Sicherheitsreview 1.22, Befund 8: names from Paperless stay within the document columns."""

from mhvp.documents.paperless_webhook import (
    MAX_FILENAME_CHARS,
    MAX_TITLE_CHARS,
    document_names,
)


def test_document_names_keep_short_values_and_fall_back() -> None:
    assert document_names("rechnung.pdf", "Rechnung 501", paperless_document_id=501) == (
        "rechnung.pdf",
        "Rechnung 501",
    )
    assert document_names(None, None, paperless_document_id=7) == (
        "paperless-7.pdf",
        "paperless-7.pdf",
    )
    assert document_names("  ", "  ", paperless_document_id=8) == (
        "paperless-8.pdf",
        "paperless-8.pdf",
    )


def test_document_names_are_cut_to_the_column_widths() -> None:
    long_name = "a" * 400 + ".pdf"
    filename, title = document_names(long_name, "t" * 500, paperless_document_id=9)
    assert len(filename) == MAX_FILENAME_CHARS
    assert filename.endswith(".pdf")
    assert len(title) == MAX_TITLE_CHARS
    no_ext, shown = document_names("b" * 300, None, paperless_document_id=10)
    assert len(no_ext) == MAX_FILENAME_CHARS
    assert shown == no_ext
