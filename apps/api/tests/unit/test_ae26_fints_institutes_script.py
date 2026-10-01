"""AE26 / M11-01: scripts/update_fints_institutes.py merges the DK institute list (CSV) into the
packaged list. Tested with small CSV files in the original DK layout (semicolon, cp1252,
column names with irregular blanks) and with a round trip over the packaged list."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from mhvp.banking import fints as fints_mod

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "update_fints_institutes.py"

HEADER = (
    "Nr.;BLZ;BIC;Institut;Ort;RZ;Organisation;HBCI-Zugang DNS;HBCI- Zugang     IP-Adresse;"
    "HBCI-Version;DDV;RDH-1;RDH-2;RDH-3;RDH-4;RDH-5;RDH-6;RDH-7;RDH-8;RDH-9;RDH-10;RAH-7;RAH-9;"
    "RAH-10;PIN/TAN-Zugang URL;Version;Datum letzte Änderung"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("update_fints_institutes", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


script = _load()


def _dk_line(
    nr: int,
    blz: str,
    bic: str,
    name: str,
    city: str,
    domain: str,
    url: str,
    hbci: str = "3.0",
    version: str = "FinTS V3.0",
) -> str:
    cells = [str(nr), blz, bic, name, city, "RZ", "BVR", domain, "", hbci] + [""] * 14
    cells += [url, version, "01.01.2026"]
    assert len(cells) == 27
    return ";".join(cells)


def _csv(tmp_path: Path, *lines: str, encoding: str = "cp1252") -> Path:
    path = tmp_path / "dk.csv"
    path.write_bytes(("\r\n".join([HEADER, *lines]) + "\r\n").encode(encoding))
    return path


def _list(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "list.txt"
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


EXISTING = [
    "10010010=Postbank|Berlin|PBNKDEFFXXX|2||https://old.postbank.example/hbci||3.0|",
    "20000001=Alte Bank|Hamburg|ALTEDEHHXXX|13|fints1.atruvia.de|https://fints1.atruvia.de/cgi-bin/hbciservlet|3.0|3.0|",
    "30000002=Ohne DK|Köln|OHNEDEKKXXX|09|||||",
    "40000003=Nur Liste|Bonn|NURLDEBBXXX|11|x.example.de|https://x.example.de/fints|3.0|3.0|",
]


def test_reads_cp1252_and_header_names_not_positions(tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        _dk_line(
            2,
            "10010010",
            "pbnkdeffxxx",
            "Postbank Süd",
            "München",
            "",
            "https://hbci.postbank.de/banking/hbci.do",
            "",
            "FinTS V3.0",
        ),
        _dk_line(
            3,
            "20000001",
            "ALTEDEHHXXX",
            "Alte Bank",
            "Hamburg",
            "fints1.atruvia.de",
            "http://insecure.example/hbci",
        ),
        _dk_line(4, "abc", "XXXXDEXXXXX", "Kaputt", "Ort", "", "https://x"),
    )
    entries, warnings = script.read_dk_csv(path)
    assert set(entries) == {"10010010", "20000001"}
    assert entries["10010010"].name == "Postbank Süd"
    assert entries["10010010"].bic == "PBNKDEFFXXX"
    assert entries["10010010"].fints == "3.0"
    assert entries["10010010"].hbci == ""
    assert entries["20000001"].url == ""  # http is not taken over
    assert any("not https" in w for w in warnings)
    assert any("not 8 digits" in w for w in warnings)


def test_missing_column_stops_with_a_clear_message(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("BLZ;BIC;Institut\n10010010;X;Y\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="columns missing"):
        script.read_dk_csv(path)


def test_conflicting_urls_of_one_blz_are_reported(tmp_path: Path) -> None:
    path = _csv(
        tmp_path,
        _dk_line(2, "10010010", "PBNKDEFFXXX", "Postbank", "Berlin", "", "https://a.example/hbci"),
        _dk_line(3, "10010010", "PBNKDEFFXXX", "Postbank", "Köln", "", "https://b.example/hbci"),
    )
    entries, warnings = script.read_dk_csv(path)
    assert entries["10010010"].url == "https://a.example/hbci"
    assert any("several different URLs" in w for w in warnings)


def test_merge_updates_address_fields_keeps_master_data_and_adds_new_blz(tmp_path: Path) -> None:
    rows = script.read_list(_list(tmp_path, *EXISTING))
    dk = {
        "10010010": script.DkEntry(
            "Postbank",
            "Berlin",
            "PBNKDEFFXXX",
            "",
            "https://hbci.postbank.de/banking/hbci.do",
            "",
            "3.0",
        ),
        "50000005": script.DkEntry(
            "Neue Bank",
            "Essen",
            "NEUEDEEEXXX",
            "fints2.atruvia.de",
            "https://fints2.atruvia.de/cgi-bin/hbciservlet",
            "3.0",
            "3.0",
        ),
    }
    result = script.merge(rows, dk)
    lines = [row.render() for row in result.rows]
    assert (
        lines[0]
        == "10010010=Postbank|Berlin|PBNKDEFFXXX|2||https://hbci.postbank.de/banking/hbci.do||3.0|"
    )
    assert "30000002=Ohne DK|Köln|OHNEDEKKXXX|09|||||" in lines
    assert (
        lines[-1]
        == "50000005=Neue Bank|Essen|NEUEDEEEXXX||fints2.atruvia.de|https://fints2.atruvia.de/cgi-bin/hbciservlet|3.0|3.0|"
    )
    assert [row.blz for row in result.rows] == sorted(row.blz for row in result.rows)
    assert any(
        line.startswith("UPDATED 10010010") and "old.postbank.example" in line
        for line in result.report
    )
    assert any(line.startswith("ADDED 50000005") for line in result.report)
    assert not result.refused or "institutes" in result.refused[0]
    # every rendered line is readable by the application's parser
    for line in lines:
        assert fints_mod._parse_line(line) is not None


def test_url_is_not_removed_silently(tmp_path: Path) -> None:
    rows = script.read_list(_list(tmp_path, *EXISTING))
    dk = {"40000003": script.DkEntry("Nur Liste", "Bonn", "NURLDEBBXXX", "", "", "", "")}
    kept = script.merge(rows, dk)
    row = next(r for r in kept.rows if r.blz == "40000003")
    assert row.url == "https://x.example.de/fints"
    assert row.fints == "3.0"
    assert any(line.startswith("KEPT 40000003") for line in kept.report)
    cleared = script.merge(rows, dk, allow_clear=True)
    assert next(r for r in cleared.rows if r.blz == "40000003").url == ""


def test_bic_matching_is_optional_and_exact(tmp_path: Path) -> None:
    rows = script.read_list(_list(tmp_path, "60000006=Zweig|Kiel|SAMEDEFFXXX|09|||||"))
    dk = {
        "60000001": script.DkEntry(
            "Haupt", "Kiel", "SAMEDEFFXXX", "", "https://same.example/hbci", "", "3.0"
        )
    }
    plain = {r.blz: r for r in script.merge(rows, dk).rows}
    assert plain["60000006"].url == ""
    matched = {r.blz: r for r in script.merge(rows, dk, match_bic=True).rows}
    assert matched["60000006"].url == "https://same.example/hbci"
    assert matched["60000006"].name == "Zweig"


def test_main_dry_run_apply_and_safety_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    list_path = _list(tmp_path, *EXISTING)
    original = list_path.read_text("utf-8")
    csv_path = _csv(
        tmp_path,
        _dk_line(
            2,
            "10010010",
            "PBNKDEFFXXX",
            "Postbank",
            "Berlin",
            "",
            "https://hbci.postbank.de/banking/hbci.do",
            "",
            "FinTS V3.0",
        ),
    )
    # one institute is far below the minimum: refused, nothing written even with --apply
    assert script.main(["--dk-csv", str(csv_path), "--list", str(list_path), "--apply"]) == 1
    assert list_path.read_text("utf-8") == original
    assert "REFUSED" in capsys.readouterr().err
    # dry run with --force: reports, does not write
    assert script.main(["--dk-csv", str(csv_path), "--list", str(list_path), "--force"]) == 0
    assert list_path.read_text("utf-8") == original
    assert "dry run" in capsys.readouterr().out
    # --force --apply writes atomically and leaves no temp file
    assert (
        script.main(["--dk-csv", str(csv_path), "--list", str(list_path), "--force", "--apply"])
        == 0
    )
    assert "hbci.postbank.de" in list_path.read_text("utf-8")
    assert not list(tmp_path.glob(".fints_institutes.*"))
    assert script.main(["--dk-csv", str(tmp_path / "missing.csv")]) == 2


def test_removed_urls_over_ten_percent_are_refused(tmp_path: Path) -> None:
    lines = [
        f"{70000000 + i}=Bank {i}|Ort|B{i:05d}DEXXX|09|d.example|https://d.example/{i}|3.0|3.0|"
        for i in range(10)
    ]
    rows = script.read_list(_list(tmp_path, *lines))
    dk = {
        f"{70000000 + i}": script.DkEntry(f"Bank {i}", "Ort", "", "", "", "", "") for i in range(10)
    }
    dk.update(
        {f"{80000000 + i}": script.DkEntry(f"X{i}", "O", "", "", "", "", "") for i in range(600)}
    )
    result = script.merge(rows, dk, allow_clear=True)
    assert any("would lose their URL" in r for r in result.refused)


def test_round_trip_over_the_packaged_list_changes_nothing(tmp_path: Path) -> None:
    """A DK file that equals the packaged list yields no change (idempotence); the file keeps
    its BLZ order and every line stays readable by the application's parser."""
    packaged = script.DEFAULT_LIST
    rows = script.read_list(packaged)
    assert len(rows) > 4000
    dk_lines = [
        _dk_line(
            i + 2,
            r.blz,
            r.bic,
            r.name,
            r.city,
            r.domain,
            r.url,
            r.hbci,
            f"FinTS V{r.fints}" if r.fints else "",
        )
        for i, r in enumerate(rows)
        if r.url
    ]
    entries, warnings = script.read_dk_csv(_csv(tmp_path, *dk_lines, encoding="utf-8"))
    assert warnings == []
    result = script.merge(rows, entries)
    assert [r.render() for r in result.rows] == [r.render() for r in rows]
    assert not any(line.startswith(("UPDATED", "ADDED", "KEPT")) for line in result.report)
    assert packaged.read_text("utf-8").splitlines() == [r.render() for r in rows]


def test_legacy_hosts_equal_the_application_constant() -> None:
    assert script.LEGACY_FINTS_HOSTS == fints_mod.LEGACY_FINTS_HOSTS


def test_windows_1252_bytes_read_as_latin_1_are_repaired() -> None:
    assert (
        script._clean("Sparkasse Schwelm \x96 Sprockhövel")
        == "Sparkasse Schwelm \u2013 Sprockhövel"
    )
    assert script._clean("A|B=C  D") == "A/B C D"
    assert not any("\x80" <= ch <= "\x9f" for ch in script.DEFAULT_LIST.read_text("utf-8")), (
        "packaged list contains C1 control characters"
    )
