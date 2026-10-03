"""GAL-311: every handbook chapter in the help index carries a link target."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_every_handbook_entry_has_an_href() -> None:
    entries = json.loads((ROOT / "apps/api/src/mhvp/ai/help_index.json").read_text("utf-8"))
    handbook = [e for e in entries if e["kind"] == "handbook"]
    assert handbook
    missing = sorted({str(e["file"]) for e in handbook if not e.get("href")})
    assert not missing, f"Kapitel ohne href: {missing}"
    assert all(str(e["href"]).startswith("/") for e in handbook)


def test_chapters_without_page_fall_back_to_the_handbook_page() -> None:
    entries = json.loads((ROOT / "apps/api/src/mhvp/ai/help_index.json").read_text("utf-8"))
    hrefs = {str(e["file"]): str(e["href"]) for e in entries if e["kind"] == "handbook"}
    assert hrefs["docs/handbuch/barrierefreiheit.md"] == "/hilfe/barrierefreiheit"
    assert hrefs["docs/handbuch/suche.md"] == "/hilfe/suche"


def test_every_handbook_file_is_indexed() -> None:
    entries = json.loads((ROOT / "apps/api/src/mhvp/ai/help_index.json").read_text("utf-8"))
    indexed = {str(e["file"]) for e in entries if e["kind"] == "handbook"}
    for path in (ROOT / "docs/handbuch").glob("*.md"):
        if path.name == "README.md":
            continue
        assert f"docs/handbuch/{path.name}" in indexed, path.name
