"""M35 Stufe 5 unit checks: water mark filter and the export file guard of the beat job."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mhvp.objektakte import objektakte_import as importer
from mhvp.objektakte.tasks import DumpUnreadableError, path_within_dump_dir, read_dump_file


def test_filter_since_keeps_newer_rows_and_catalog_rows() -> None:
    tables: dict[str, list[dict[str, Any]]] = {
        "objects_unit": [
            {"id": 1, "updated_at": "2026-09-01 08:00:00"},
            {"id": 2, "updated_at": "2026-09-10 12:00:00"},
            {"id": 3, "updated_at": "2026-09-12 09:00:00"},
        ],
        "documents_documentcategory": [{"code": "02"}],
    }
    since = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    filtered, newest = importer.filter_since(tables, since)
    assert [r["id"] for r in filtered["objects_unit"]] == [2, 3]
    assert filtered["documents_documentcategory"] == [{"code": "02"}]
    assert newest == datetime(2026, 9, 12, 9, 0, tzinfo=UTC)

    everything, _ = importer.filter_since(tables, None)
    assert len(everything["objects_unit"]) == 3


def test_read_dump_file_accepts_only_absolute_sql_files(tmp_path: Path) -> None:
    base = str(tmp_path)
    with pytest.raises(DumpUnreadableError):
        read_dump_file(None, base)
    with pytest.raises(DumpUnreadableError):
        read_dump_file("relative/objektakte.sql", base)
    other = tmp_path / "objektakte.txt"
    other.write_text("INSERT INTO `x` (`id`) VALUES (1);", encoding="utf-8")
    with pytest.raises(DumpUnreadableError):
        read_dump_file(str(other), base)
    with pytest.raises(DumpUnreadableError):
        read_dump_file(str(tmp_path / "missing.sql"), base)
    dump = tmp_path / "objektakte.sql"
    dump.write_text("INSERT INTO `x` (`id`) VALUES (1);", encoding="utf-8")
    assert read_dump_file(str(dump), base).startswith("INSERT INTO")


def test_read_dump_file_stays_inside_the_export_directory(tmp_path: Path) -> None:
    """Sicherheitsreview 26.09.2026: a tenant setting must not point the worker at a file
    outside the configured export directory, neither directly nor via `..` or a symlink."""
    base = tmp_path / "exports"
    base.mkdir()
    outside = tmp_path / "other-tenant.sql"
    outside.write_text("INSERT INTO `x` (`id`) VALUES (2);", encoding="utf-8")
    with pytest.raises(DumpUnreadableError, match="außerhalb"):
        read_dump_file(str(outside), str(base))
    with pytest.raises(DumpUnreadableError, match="außerhalb"):
        read_dump_file(str(base / ".." / "other-tenant.sql"), str(base))
    link = base / "link.sql"
    link.symlink_to(outside)
    with pytest.raises(DumpUnreadableError, match="außerhalb"):
        read_dump_file(str(link), str(base))
    inside = base / "objektakte.sql"
    inside.write_text("INSERT INTO `x` (`id`) VALUES (3);", encoding="utf-8")
    assert read_dump_file(str(inside), str(base)).endswith("(3);")

    assert path_within_dump_dir("/data/objektakte-export/a.sql", "/data/objektakte-export")
    assert path_within_dump_dir("/data/objektakte-export/sub/a.sql", "/data/objektakte-export/")
    assert not path_within_dump_dir("/data/objektakte-export/../b/a.sql", "/data/objektakte-export")
    assert not path_within_dump_dir("/data/objektakte-export", "/data/objektakte-export")
    assert not path_within_dump_dir("/data/objektakte-exports/a.sql", "/data/objektakte-export")


def test_read_dump_file_checks_size_before_reading(tmp_path: Path) -> None:
    """Sicherheitsreview 26.09.2026, Befund 8: the limit is configurable and enforced via stat
    (the message names size and limit); a file within the limit is read as before."""
    dump = tmp_path / "objektakte.sql"
    dump.write_text("INSERT INTO `x` (`id`) VALUES (1);", encoding="utf-8")
    size = dump.stat().st_size
    with pytest.raises(DumpUnreadableError, match=f"{size} Byte, Obergrenze {size - 1} Byte"):
        read_dump_file(str(dump), str(tmp_path), max_bytes=size - 1)
    assert read_dump_file(str(dump), str(tmp_path), max_bytes=size).startswith("INSERT INTO")
