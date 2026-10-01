"""SECURITY-2026-10-01, Befund 1: the unpacked total of a ZIP import is bounded, not only each
single entry (many highly compressed entries must not be held in memory at once)."""

import io
import zipfile

import pytest

from mhvp.core.problems import ProblemError
from mhvp.documents import transfer_routers as tr


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_total_unpacked_size_is_capped() -> None:
    limit = 1000
    entries = {f"f{i}.txt": b"a" * limit for i in range(tr.ZIP_MAX_TOTAL_FACTOR + 1)}
    with pytest.raises(ProblemError) as caught:
        tr._zip_entries(_zip(entries), limit)
    assert caught.value.status == 422
    assert "entpackte Inhalt" in str(caught.value.detail)


def test_within_total_limit_passes_and_single_oversize_is_skipped() -> None:
    limit = 1000
    entries = {f"f{i}.txt": b"a" * limit for i in range(tr.ZIP_MAX_TOTAL_FACTOR)}
    entries["gross.txt"] = b"b" * (limit + 1)
    files, skipped = tr._zip_entries(_zip(entries), limit)
    assert len(files) == tr.ZIP_MAX_TOTAL_FACTOR
    assert [x.name for x in skipped] == ["gross.txt"]
