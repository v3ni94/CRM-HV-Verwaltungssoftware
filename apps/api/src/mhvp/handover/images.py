"""Photo sanitizing for handover protocol uploads (M30-04) and portal uploads (A55, A58).

U-Protokoll removed GPS and EXIF data and scaled photos on upload. The CRM does the same for
handover uploads and for photos uploaded through the portal (damage reports, execution
documentation): the image is decoded with Pillow (installed as a dependency of
reportlab), the EXIF orientation is applied to the pixels, the image is scaled so that its
longest edge does not exceed ``max_edge`` and it is re-encoded without any metadata (EXIF,
XMP, IPTC, ICC comments, PNG text chunks). The original is not kept.

HEIC/HEIF photos from iPhones (A72) are decoded through ``pillow-heif`` and re-encoded as
JPEG, because Pillow itself cannot read HEIF and a JPEG is what every downstream consumer
(PDF export, CRM, browser) can display. Without the library the type reports as unsupported
and callers reject the upload with a hint instead of storing the photo with its metadata.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import pillow_heif
except ImportError:  # pragma: no cover - the dependency is pinned, this is a safety net
    HEIF_AVAILABLE = False
else:
    pillow_heif.register_heif_opener()
    HEIF_AVAILABLE = True

DEFAULT_MAX_EDGE = 2000
HEIF_MIME_TYPES = frozenset(
    {"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"}
)

# MIME type -> Pillow format. Other types (PDF, office files) pass through unchanged.
_FORMATS = {
    "image/jpeg": "JPEG",
    "image/jpg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
    "image/tiff": "TIFF",
}
# HEIC/HEIF is decoded by pillow-heif and always written back as JPEG (A72).
if HEIF_AVAILABLE:
    _FORMATS.update(dict.fromkeys(HEIF_MIME_TYPES, "JPEG"))


def _normalize(content_type: str) -> str:
    return content_type.split(";")[0].strip().lower()


def supports(content_type: str) -> bool:
    """True when ``sanitize_image`` re-encodes this type (so metadata is really removed)."""
    return _normalize(content_type) in _FORMATS


def output_mime_type(content_type: str) -> str:
    """MIME type of the sanitized result: HEIC/HEIF becomes ``image/jpeg``, others stay."""
    mime = _normalize(content_type)
    if mime in HEIF_MIME_TYPES and supports(mime):
        return "image/jpeg"
    return mime


class ImageSanitizeError(ValueError):
    """The upload claims to be an image but cannot be decoded, so it cannot be cleaned."""


def sanitize_image(data: bytes, content_type: str, max_edge: int = DEFAULT_MAX_EDGE) -> bytes:
    """Return the image without metadata and scaled to ``max_edge``; non images unchanged.

    HEIC/HEIF input is returned as JPEG; use ``output_mime_type`` for the stored type.
    pillow-heif applies the EXIF orientation while decoding (``original_orientation`` in
    ``info``), ``exif_transpose`` then finds orientation 1 and leaves the pixels as they are.
    """
    fmt = _FORMATS.get(_normalize(content_type))
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
