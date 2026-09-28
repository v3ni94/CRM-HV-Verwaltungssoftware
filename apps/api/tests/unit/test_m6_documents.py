"""M6 pure logic: text extraction, content sniffing, Drive folder names, letterhead rules."""

from datetime import date

import pytest

from mhvp.documents.dms import property_folder_name
from mhvp.documents.letters import Letter, Letterhead, PlaceholderError, render_pdf, render_text
from mhvp.documents.models import TextStatus
from mhvp.documents.text import extract, sniff_matches


def test_extraction_and_sniffing() -> None:
    assert extract("text/plain", "Grüße".encode()) == ("Grüße", TextStatus.EXTRACTED)
    assert extract("application/pdf", b"%PDF-1.4 broken") == (None, TextStatus.PENDING)
    assert extract("image/png", b"\x89PNG") == (None, TextStatus.PENDING)
    assert extract("application/zip", b"PK\x03\x04") == (None, TextStatus.NONE)
    assert sniff_matches("application/pdf", b"%PDF-1.7")
    assert not sniff_matches("image/jpeg", b"%PDF-")
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert sniff_matches(docx, b"PK\x03\x04rest")
    assert not sniff_matches(docx, b"MZ")
    assert sniff_matches("text/plain", b"anything")


def _ftyp(major: bytes, *compatible: bytes) -> bytes:
    body = major + b"\x00\x00\x00\x00" + b"".join(compatible)
    return (8 + len(body)).to_bytes(4, "big") + b"ftyp" + body


def test_heic_signature_is_checked() -> None:
    """A72: HEIC/HEIF must start with an ``ftyp`` box carrying a HEIF brand (major or
    compatible); renamed executables, JPEGs, MP4 videos and AVIF are refused."""
    assert sniff_matches("image/heic", _ftyp(b"heic", b"mif1", b"heic"))
    assert sniff_matches("image/heic", _ftyp(b"mif1", b"heic"))
    assert sniff_matches("image/heif", _ftyp(b"msf1", b"hevc"))
    # iPhone style: major brand heic, box size larger than the bytes present (truncated read).
    assert sniff_matches("image/heic", b"\x00\x00\x00\x18ftypheic")
    # compatible brand only, major brand not HEIF
    assert sniff_matches("image/heic", _ftyp(b"isom", b"mp41", b"heix"))
    assert not sniff_matches("image/heic", b"MZ\x90\x00" + b"\x00" * 20)
    assert not sniff_matches("image/heic", b"\xff\xd8\xff\xe0" + b"\x00" * 20)
    assert not sniff_matches("image/heic", _ftyp(b"isom", b"iso2", b"mp41"))
    assert not sniff_matches("image/heic", _ftyp(b"avif", b"mif2"))
    assert not sniff_matches("image/heic", b"")
    assert not sniff_matches("image/heic", b"\x00\x00\x00\x18ftyp")
    # a brand beyond the declared box size does not count
    short_box = (16).to_bytes(4, "big") + b"ftypisom\x00\x00\x00\x00heic"
    assert not sniff_matches("image/heic", short_box)


def test_drive_folder_name() -> None:
    assert (
        property_folder_name("342", "Monheim am Rhein", "Rheinpromenade", "13")
        == "342 Monheim am Rhein, Rheinpromenade 13"
    )
    assert property_folder_name("007", None, None, None) == "007"


def test_letterhead_mandatory_fields_and_fallback_rule() -> None:
    gmbh = Letterhead({"name": "X GmbH", "legal_form": "GmbH", "street": "A 1"}, {})
    assert gmbh.missing_mandatory() == [
        "postal_code",
        "city",
        "register_court",
        "register_number",
        "management",
    ]
    sole = Letterhead(
        {
            "name": "Timo Müller",
            "legal_form": "Einzelunternehmen",
            "street": "A 1",
            "postal_code": "40789",
            "city": "Monheim am Rhein",
        },
        {"accent_color": "#E6A83C"},
    )
    assert sole.missing_mandatory() == []
    pdf = render_pdf(
        sole,
        Letter(
            ["Empfänger", "Weg 1", "40789 Monheim am Rhein"], "Betreff", "Text", date(2026, 9, 23)
        ),
    )
    assert pdf.startswith(b"%PDF-")


def test_placeholders_are_strict_and_sandboxed() -> None:
    assert render_text("{{ a.b }}", {"a": {"b": "<x>"}}) == "&lt;x&gt;"
    with pytest.raises(PlaceholderError):
        render_text("{{ a.fehlt }}", {"a": {}})
    with pytest.raises(PlaceholderError):
        render_text("{{ ''.__class__.__mro__[1].__subclasses__() }}", {})
