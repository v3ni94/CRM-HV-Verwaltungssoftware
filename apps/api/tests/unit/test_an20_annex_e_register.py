"""GAK-404: register of the decided conflicts E01 to E16 is complete and its paths exist."""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
REGISTER = REPO / "docs" / "rules" / "anhang-e-register.md"


def _rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in REGISTER.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\| (E\d\d) \|", line)
        if match:
            rows[match.group(1)] = [c.strip() for c in line.strip("|").split("|")]
    return rows


def test_register_names_every_conflict_once() -> None:
    assert sorted(_rows()) == [f"E{i:02d}" for i in range(1, 17)]


def test_each_row_has_implementation_test_and_status() -> None:
    for key, cells in _rows().items():
        assert len(cells) == 5, key
        assert all(cells[2:]), key
        assert "`" in cells[2], key
        assert "`" in cells[3] or "CI" in cells[3], key


def test_every_referenced_path_exists() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    paths = {p for p in re.findall(r"`([^`]+)`", text) if "/" in p}
    missing = sorted(p for p in paths if not (REPO / p).exists())
    assert missing == []
