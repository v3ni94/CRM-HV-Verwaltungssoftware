"""Q14 (M26-05): images of a letter (exposé photos) are embedded, unreadable ones skipped, and
a letter without images stays unchanged. Image objects counted in the PDF page resources."""

import io
from datetime import date

from pypdf import PdfReader

from mhvp.communication.suggest import draft_reply_payload
from mhvp.documents import letters

HEAD = letters.Letterhead(
    company={"name": "Muster GmbH", "street": "Weg 1", "postal_code": "40789", "city": "Monheim"},
    branding={},
)


def _images(pdf: bytes) -> int:
    count = 0
    for page in PdfReader(io.BytesIO(pdf)).pages:
        xobjects = (page.get("/Resources") or {}).get("/XObject") or {}
        count += sum(1 for x in xobjects.values() if x.get_object().get("/Subtype") == "/Image")
    return count


def _letter(images: list[bytes]) -> letters.Letter:
    return letters.Letter([], "Exposé", "Text.", date(2026, 9, 30), images=images)


def test_images_are_embedded_and_bad_data_is_skipped() -> None:
    png = letters.qr_png("https://example.org")
    base = _images(letters.render_pdf(HEAD, _letter([])))
    assert _images(letters.render_pdf(HEAD, _letter([png]))) == base + 1
    assert _images(letters.render_pdf(HEAD, _letter([png, b"kein bild"]))) == base + 1


def test_draft_reply_schema_checks_placeholders_and_keeps_style() -> None:
    out = draft_reply_payload(
        {"reply_draft": "{anrede}, zu {ticket} und {unbekannt}.", "reply_tone": "formell"},
        {"tone": "freundlich", "rules": "  Immer   siezen "},
    )
    assert out is not None
    assert out["placeholders"] == ["{anrede}", "{ticket}"]
    assert out["unknown_placeholders"] == ["{unbekannt}"]
    assert out["style_tone"] == "freundlich"
    assert out["style_rules"] == "Immer siezen"
    assert out["tone"] == "formell"
    assert draft_reply_payload({"reply_draft": "  "}, None) is None
    neutral = draft_reply_payload({"reply_draft": "Text"}, {"tone": "laut"})
    assert neutral is not None
    assert neutral["style_tone"] == "sachlich"
