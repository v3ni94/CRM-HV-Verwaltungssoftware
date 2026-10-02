"""GAE-37: the letterhead embeds a free TrueType font; Helvetica only as reported fallback."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfReader

from mhvp.accounting import zugferd as z
from mhvp.documents import pdf_fonts
from mhvp.documents.letters import Letter, Letterhead, render_pdf

HEAD = Letterhead(
    company={"name": "AF13 Test GmbH", "street": "Weg 1", "postal_code": "10115", "city": "Berlin"},
    branding={},
)
LETTER = Letter(
    recipient_lines=["Empfänger AF13", "Straße 2", "10115 Berlin"],
    subject="Schriftprüfung",
    body="Umlaute äöüß und Betrag 1.234,56 EUR.",
    letter_date=date(2026, 10, 2),
)


def _fonts(pdf: bytes) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for page in PdfReader(io.BytesIO(pdf)).pages:
        for font in page["/Resources"]["/Font"].values():
            font = font.get_object()
            desc = font.get("/FontDescriptor")
            desc = desc.get_object() if desc is not None else {}
            embedded = any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3"))
            out[str(font["/BaseFont"])] = embedded
    return out


def _has_system_font() -> bool:
    return pdf_fonts.pdf_fonts().embedded


@pytest.mark.skipif(not _has_system_font(), reason="no Liberation/DejaVu font installed")
def test_letter_embeds_all_fonts_and_precheck_has_no_font_blocker() -> None:
    pdf = render_pdf(HEAD, LETTER)
    fonts = _fonts(pdf)
    assert fonts
    assert all(fonts.values()), fonts
    assert not any("Helvetica" in name for name in fonts)
    check = z.pdfa_precheck(pdf)
    assert not [b for b in check["blockers"] if b.startswith("Schriften")]
    assert check["conformance"] == "not_verified"
    assert "Umlaute äöüß" in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()


def test_configured_font_dir_is_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = pdf_fonts.pdf_fonts().source
    if source is None:
        pytest.skip("no font to copy")
    src = Path(source).parent
    for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
        if not (src.parent / "dejavu" / name).is_file():
            pytest.skip("DejaVu not installed")
        (tmp_path / name).write_bytes((src.parent / "dejavu" / name).read_bytes())
    monkeypatch.setattr(pdf_fonts, "_SYSTEM_DIRS", ())
    monkeypatch.setenv(pdf_fonts.FONT_DIR_ENV, str(tmp_path))
    resolved = pdf_fonts.pdf_fonts()
    assert resolved.embedded
    assert resolved.source == str(tmp_path / "DejaVuSans.ttf")


def test_fallback_helvetica_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(pdf_fonts, "_SYSTEM_DIRS", ())
    monkeypatch.setenv(pdf_fonts.FONT_DIR_ENV, str(tmp_path))
    resolved = pdf_fonts.pdf_fonts()
    assert (resolved.regular, resolved.bold, resolved.embedded) == (
        "Helvetica",
        "Helvetica-Bold",
        False,
    )
    import mhvp.documents.letters as letters

    monkeypatch.setattr(letters, "pdf_fonts", lambda: resolved)
    check = z.pdfa_precheck(render_pdf(HEAD, LETTER))
    blocker = [b for b in check["blockers"] if b.startswith("Schriften nicht eingebettet")]
    assert blocker
    assert pdf_fonts.FALLBACK_HINT in blocker[0]
