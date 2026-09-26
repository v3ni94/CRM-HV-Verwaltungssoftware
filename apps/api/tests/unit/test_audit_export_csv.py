"""Unit tests of the audit export CSV and ZIP construction (A26, 7.7, D55): semicolon, UTF-8
BOM, CRLF, decimal comma, formula neutralisation and the index with SHA-256 per file."""

import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal

from mhvp.accounting.audit_export import (
    BOM,
    ExportBundle,
    Receipt,
    Table,
    build_zip,
    csv_table,
    format_cell,
)
from mhvp.accounting.models import EntryKind


def test_format_cell_rules() -> None:
    assert format_cell(None) == ""
    assert format_cell(True) == "ja"
    assert format_cell(False) == "nein"
    assert format_cell(Decimal("1234.50")) == "1234,50"
    assert format_cell(Decimal("-3.10")) == "-3,10"
    assert format_cell(EntryKind.REVERSAL) == "reversal"
    assert format_cell(date(2026, 1, 31)) == "2026-01-31"
    assert format_cell(datetime(2026, 1, 31, 12, 0, tzinfo=UTC)) == "2026-01-31T12:00:00+00:00"
    assert format_cell("=SUM(A1)") == "'=SUM(A1)"
    assert format_cell("+49 211") == "'+49 211"
    assert format_cell("Hausgeld") == "Hausgeld"
    assert format_cell({"b": 1, "a": "=x"}) == '{"a": "=x", "b": 1}'
    assert format_cell(uuid.UUID(int=1)) == "00000000-0000-0000-0000-000000000001"


def test_csv_table_layout() -> None:
    data = csv_table(["Nr", "Betrag", "Text"], [[1, Decimal("10.00"), "a;b"], [2, None, "=1+1"]])
    text = data.decode("utf-8")
    assert text.startswith(BOM)
    assert "\r\n" in text
    rows = list(csv.reader(io.StringIO(text.removeprefix(BOM)), delimiter=";"))
    assert rows == [["Nr", "Betrag", "Text"], ["1", "10,00", "a;b"], ["2", "", "'=1+1"]]


def test_build_zip_index_lists_every_file_with_hash() -> None:
    table = Table("konten", ["Kontonummer", "Bezeichnung"], [["001200", "Bank"]])
    receipt_id = uuid.UUID(int=7)
    bundle = ExportBundle(
        meta={"generated_at": "2026-09-26T10:00:00+00:00", "counts": {"lines": 1}},
        tables=[table],
        receipts=[
            Receipt(
                document_id=receipt_id,
                filename="beleg.pdf",
                mime_type="application/pdf",
                size=4,
                sha256=hashlib.sha256(b"%PDF").hexdigest(),
                storage="minio",
                entry_ids=[],
                included=True,
                path=f"belege/{receipt_id}_beleg.pdf",
            )
        ],
        receipt_files={f"belege/{receipt_id}_beleg.pdf": b"%PDF"},
    )
    data = build_zip(bundle)
    assert build_zip(bundle) == data  # deterministic
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert names == [
            "konten.csv",
            f"belege/{receipt_id}_beleg.pdf",
            "export.json",
            "index.csv",
            "index.json",
        ]
        index = json.loads(zf.read("index.json"))["files"]
        by_file = {e["file"]: e for e in index}
        assert set(by_file) == {
            "konten.csv",
            f"belege/{receipt_id}_beleg.pdf",
            "export.json",
            "index.csv",
        }
        assert by_file["konten.csv"]["rows"] == 1
        assert by_file["konten.csv"]["columns"] == ["Kontonummer", "Bezeichnung"]
        for name, entry in by_file.items():
            assert hashlib.sha256(zf.read(name)).hexdigest() == entry["sha256"]
        index_csv = zf.read("index.csv").decode("utf-8")
        assert index_csv.startswith(BOM + "Datei;Zeilen;Spalten;Bytes;SHA-256\r\n")
        assert by_file["index.csv"]["rows"] == 3  # lists the files before it
