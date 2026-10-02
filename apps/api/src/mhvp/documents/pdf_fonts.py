"""Embedded TrueType fonts for the letterhead renderer (GAE-37, PDF/A-3 precheck AE25).

The standard PDF fonts (Helvetica) are not embedded, which blocks PDF/A. This module looks for
a free font pair (Liberation Sans, OFL compatible license; DejaVu Sans) in the directory
``MHVP_PDF_FONT_DIR`` and in the Debian package locations of ``fonts-liberation`` and
``fonts-dejavu-core`` (installed in the API image). Without a font it falls back to Helvetica
and reports ``embedded=False`` so the ZUGFeRD precheck keeps its blocker.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR_ENV = "MHVP_PDF_FONT_DIR"
FALLBACK_HINT = (
    "Briefbogen ohne eingebettete Schrift (Fallback Helvetica): fonts-liberation oder "
    "fonts-dejavu-core installieren oder MHVP_PDF_FONT_DIR setzen."
)
# (registered name, regular file, bold file)
_CANDIDATES = (
    ("MHVPSans", "LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
    ("MHVPSans", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
)
_SYSTEM_DIRS = (
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/liberation2",
    "/usr/share/fonts/truetype/dejavu",
)


@dataclass(frozen=True)
class PdfFonts:
    regular: str
    bold: str
    embedded: bool
    source: str | None


def _dirs() -> list[Path]:
    configured = os.environ.get(FONT_DIR_ENV, "").strip()
    dirs = [Path(configured)] if configured else []
    return dirs + [Path(d) for d in _SYSTEM_DIRS]


@lru_cache(maxsize=4)
def _resolve(dirs: tuple[Path, ...]) -> PdfFonts:
    for name, regular, bold in _CANDIDATES:
        for directory in dirs:
            reg, bld = directory / regular, directory / bold
            if reg.is_file() and bld.is_file():
                try:
                    pdfmetrics.registerFont(TTFont(name, str(reg)))
                    pdfmetrics.registerFont(TTFont(f"{name}-Bold", str(bld)))
                except Exception:  # noqa: S112 - unreadable font file, try the next
                    continue
                return PdfFonts(name, f"{name}-Bold", True, str(reg))
    return PdfFonts("Helvetica", "Helvetica-Bold", False, None)


def pdf_fonts() -> PdfFonts:
    """Return the fonts to use; resolution is cached per configured directory list."""
    return _resolve(tuple(_dirs()))
