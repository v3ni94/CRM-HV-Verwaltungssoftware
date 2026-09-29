"""ocr_text must fit the generated tsvector (1048575 bytes) even with multibyte characters."""

from mhvp.documents.text import MAX_TEXT_BYTES, cap_text, extract


def test_cap_text_limits_bytes_without_splitting_characters() -> None:
    text = "ä" * 600_000  # 1.200.000 bytes in UTF-8
    capped = cap_text(text)
    assert len(capped.encode("utf-8")) <= MAX_TEXT_BYTES
    assert set(capped) == {"ä"}


def test_extract_plain_text_is_byte_capped() -> None:
    data = ("ü" * 700_000).encode("utf-8")
    text, _status = extract("text/plain", data)
    assert text is not None
    assert len(text.encode("utf-8")) <= MAX_TEXT_BYTES
