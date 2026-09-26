"""Photo sanitizing for handover protocol uploads (M30-04) and portal uploads (A55, A58).

U-Protokoll removed GPS and EXIF data and scaled photos on upload. The CRM does the same for
handover uploads and for photos uploaded through the portal (damage reports, execution
documentation): the image is decoded with Pillow (installed as a dependency of
reportlab), the EXIF orientation is applied to the pixels, the image is scaled so that its
longest edge does not exceed ``max_edge`` and it is re-encoded without any metadata (EXIF,
XMP, IPTC, ICC comments, PNG text chunks). The original is not kept.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

DEFAULT_MAX_EDGE = 2000

# MIME type -> Pillow format. Other types (PDF, office files) pass through unchanged.
_FORMATS = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/tiff": "TIFF",
}


def supports(content_type: str) -> bool:
    """True when ``sanitize_image`` re-encodes this type (so metadata is really removed)."""
    return content_type.split(";")[0].strip().lower() in _FORMATS


class ImageSanitizeError(ValueError):
    """The upload claims to be an image but cannot be decoded, so it cannot be cleaned."""


def sanitize_image(data: bytes, content_type: str, max_edge: int = DEFAULT_MAX_EDGE) -> bytes:
    """Return the image without metadata and scaled to ``max_edge``; non images unchanged."""
    fmt = _FORMATS.get(content_type.split(";")[0].strip().lower())
    if fmt is None:
        return data
    try:
        with Image.open(io.BytesIO(data)) as src:
            src.load()
            img = ImageOps.exif_transpose(src)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageSanitizeError(str(exc)) from exc
    if max(img.size) > max_edge:
        img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    # A fresh image holds pixels only; info (exif, xmp, icc, text chunks) is not carried over.
    clean = Image.new(img.mode, img.size)
    clean.paste(img)
    if img.mode == "P" and img.getpalette() is not None:
        clean.putpalette(img.getpalette() or [])
        if "transparency" in img.info:
            clean.info["transparency"] = img.info["transparency"]
    out = io.BytesIO()
    if fmt == "JPEG":
        if clean.mode not in ("RGB", "L", "CMYK"):
            clean = clean.convert("RGB")
        clean.save(out, format="JPEG", quality=90, optimize=True)
    elif fmt == "PNG":
        if "transparency" in clean.info:
            clean.save(out, format="PNG", optimize=True, transparency=clean.info["transparency"])
        else:
            clean.save(out, format="PNG", optimize=True)
    elif fmt == "TIFF":
        clean.save(out, format="TIFF")
    else:
        clean.save(out, format="WEBP", quality=90)
    return out.getvalue()
