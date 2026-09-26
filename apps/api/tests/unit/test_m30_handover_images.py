"""M30-04: handover photos lose GPS/EXIF data and are scaled."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from mhvp.handover.images import ImageSanitizeError, sanitize_image


def _jpeg_with_exif(size: tuple[int, int] = (3000, 1500), orientation: int = 1) -> bytes:
    img = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "TestCam"  # Make
    exif[0x0112] = orientation
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (51.0, 10.0, 0.0)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_jpeg_exif_and_gps_removed_and_scaled() -> None:
    raw = _jpeg_with_exif()
    assert b"Exif" in raw
    assert b"TestCam" in raw
    out = sanitize_image(raw, "image/jpeg")
    assert b"Exif" not in out
    assert b"TestCam" not in out
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (2000, 1000)
        assert len(img.getexif()) == 0
        assert "exif" not in img.info


def test_small_image_not_upscaled_and_custom_edge() -> None:
    with Image.open(io.BytesIO(sanitize_image(_jpeg_with_exif((800, 600)), "image/jpeg"))) as i:
        assert i.size == (800, 600)
    out = sanitize_image(_jpeg_with_exif((800, 600)), "image/jpeg; x=1", max_edge=400)
    with Image.open(io.BytesIO(out)) as i:
        assert i.size == (400, 300)


def test_orientation_applied_before_stripping() -> None:
    out = sanitize_image(_jpeg_with_exif((400, 200), orientation=6), "image/jpeg")
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (200, 400)


def test_png_text_chunks_removed() -> None:
    from PIL.PngImagePlugin import PngInfo

    meta = PngInfo()
    meta.add_text("Location", "51.0,10.0")
    buf = io.BytesIO()
    Image.new("RGBA", (50, 50)).save(buf, format="PNG", pnginfo=meta)
    out = sanitize_image(buf.getvalue(), "image/png")
    assert b"Location" not in out
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "PNG"
        assert img.mode == "RGBA"


def test_non_image_unchanged() -> None:
    assert sanitize_image(b"%PDF-1.7 test", "application/pdf") == b"%PDF-1.7 test"


def test_broken_image_rejected() -> None:
    with pytest.raises(ImageSanitizeError):
        sanitize_image(b"\xff\xd8\xff\xe1 kaputt", "image/jpeg")


def test_tiff_reencoded_without_metadata_and_supports_reports_types() -> None:
    """A55/A58: portal photos use the same sanitizer; TIFF is re-encoded, HEIC is unsupported."""
    from PIL.TiffImagePlugin import ImageFileDirectory_v2

    from mhvp.handover.images import supports

    info = ImageFileDirectory_v2()
    info[270] = "Location 51.0,10.0"  # ImageDescription
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (10, 20, 30)).save(buf, format="TIFF", tiffinfo=info)
    raw = buf.getvalue()
    assert b"Location" in raw
    out = sanitize_image(raw, "image/tiff")
    assert b"Location" not in out
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "TIFF"
        assert img.size == (60, 40)
    assert supports("image/jpeg; charset=binary")
    assert supports("image/png")
    assert not supports("image/heic")
    assert not supports("application/pdf")
