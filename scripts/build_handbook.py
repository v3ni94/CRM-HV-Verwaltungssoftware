#!/usr/bin/env python3
"""Render docs/handbuch/*.md into a JSON block model for the CRM help pages (/hilfe).

No markdown dependency: the handbook uses headings, paragraphs, lists, tables, block quotes and
code fences only. Inline markup (bold, code, links) stays raw and is parsed by the small
renderer in ``apps/web-crm/src/components/hilfe/HandbookBlocks.tsx``.

Output: ``apps/web-crm/src/lib/handbook.generated.json`` (committed). ``--check`` fails when the
committed file is out of date (``make lint``).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs/handbuch"
TARGET = ROOT / "apps/web-crm/src/lib/handbook.generated.json"
_LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")


def slugify(text: str) -> str:
    s = re.sub(r"[`*_]", "", text).lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "abschnitt"


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(text: str) -> list[dict]:
    lines = text.splitlines()
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            blocks.append({"t": "code", "text": "\n".join(lines[i + 1 : j])})
            i = j + 1
        elif re.match(r"^#{1,6}\s", line):
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            blocks.append({"t": "h", "level": level, "text": title, "id": slugify(title)})
            i += 1
        elif line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = _cells(line)
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(_cells(lines[j]))
                j += 1
            blocks.append({"t": "table", "head": head, "rows": rows})
            i = j
        elif line.startswith(">"):
            j = i
            buf = []
            while j < len(lines) and lines[j].startswith(">"):
                buf.append(lines[j].lstrip(">").strip())
                j += 1
            blocks.append({"t": "quote", "text": " ".join(buf)})
            i = j
        elif _LIST.match(line):
            ordered = bool(re.match(r"^\s*\d+\.", line))
            items: list[dict] = []
            j = i
            while j < len(lines):
                m = _LIST.match(lines[j])
                if m:
                    items.append({"depth": min(len(m.group(1)) // 2, 3), "text": m.group(3).strip()})
                elif lines[j].strip() and lines[j].startswith(" ") and items:
                    items[-1]["text"] += " " + lines[j].strip()
                else:
                    break
                j += 1
            blocks.append({"t": "ol" if ordered else "ul", "items": items})
            i = j
        else:
            j = i
            buf = []
            while j < len(lines) and lines[j].strip() and not re.match(r"^(#{1,6}\s|```|>|\s*\|)", lines[j]) and not _LIST.match(lines[j]):
                buf.append(lines[j].strip())
                j += 1
            if not buf:  # defensive: never loop forever
                buf, j = [line.strip()], i + 1
            blocks.append({"t": "p", "text": " ".join(buf)})
            i = j
    return blocks


def build() -> dict:
    chapters = []
    for path in sorted(SRC.glob("*.md")):
        blocks = parse(path.read_text(encoding="utf-8"))
        title = next((b["text"] for b in blocks if b["t"] == "h" and b["level"] == 1), path.stem)
        body = [b for b in blocks if not (b["t"] == "h" and b["level"] == 1)]
        chapters.append({"slug": path.stem, "title": title, "blocks": body})
    return {"chapters": chapters}


def render() -> str:
    return json.dumps(build(), ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    out = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != out:
            print("handbook.generated.json is out of date: run python3 scripts/build_handbook.py")
            return 1
        return 0
    TARGET.write_text(out, encoding="utf-8")
    print(f"{TARGET.relative_to(ROOT)}: {len(build()['chapters'])} chapters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
