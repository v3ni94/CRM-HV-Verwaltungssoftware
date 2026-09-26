"""M35 Stufe 5 unit checks: water mark filter and the export file guard of the beat job."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from mhvp.objektakte import objektakte_import as importer
from mhvp.objektakte.tasks import DumpUnreadableError, read_dump_file


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
    with pytest.raises(DumpUnreadableError):
        read_dump_file(None)
    with pytest.raises(DumpUnreadableError):
        read_dump_file("relative/objektakte.sql")
    other = tmp_path / "objektakte.txt"
    other.write_text("INSERT INTO `x` (`id`) VALUES (1);", encoding="utf-8")
    with pytest.raises(DumpUnreadableError):
        read_dump_file(str(other))
    with pytest.raises(DumpUnreadableError):
        read_dump_file(str(tmp_path / "missing.sql"))
    dump = tmp_path / "objektakte.sql"
    dump.write_text("INSERT INTO `x` (`id`) VALUES (1);", encoding="utf-8")
    assert read_dump_file(str(dump)).startswith("INSERT INTO")
