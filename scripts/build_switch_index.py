#!/usr/bin/env python3
"""Build the switch index of ``docs/handbuch/einstellungen.md`` and expose the switch inventory.

Sources (read only):
- ``apps/web-crm/src/lib/business-rules.ts``: one entry per tenant switch (id, group, work
  package, default, open questions),
- ``apps/api/src/mhvp``: namespaced switch keys (``SWITCH_KEY = "area.name"``) kept in the
  tenant sources,
- ``docs/OPEN_QUESTIONS.md``: the open questions the switches refer to.

Output: the block between the markers ``switch-index:start`` and ``switch-index:end`` in
``docs/handbuch/einstellungen.md``. ``--check`` fails when the block is out of date (CI and
``make switch-index``). The guard tests ``tests/unit/test_ao14_*`` reuse the parsers below.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_TS = ROOT / "apps/web-crm/src/lib/business-rules.ts"
QUESTIONS = ROOT / "docs/OPEN_QUESTIONS.md"
RULES_DIR = ROOT / "docs/rules"
API_SRC = ROOT / "apps/api/src/mhvp"
TARGET = ROOT / "docs/handbuch/einstellungen.md"
START = "<!-- switch-index:start (generiert mit build_switch_index.py, nicht von Hand ändern) -->"
END = "<!-- switch-index:end -->"

_ID = re.compile(r'^\s{4}id:\s*"([^"]+)"')
_TEMPLATE_ID = re.compile(r"^\s{2}id:\s*`([^`]+)`")
_PKG = re.compile(r'^\s+pkg:\s*"([^"]+)"')
_GROUP = re.compile(r'^\s+group:\s*"([^"]+)"')
_DEFAULT = re.compile(r"^\s+default:\s*(.+?),?\s*$")
_QUESTIONS = re.compile(r"questions:\s*\[([^\]]*)\]")
_SLUG = re.compile(r'\{\s*slug:\s*"([^"]+)".*questions:\s*\[([^\]]*)\]')
_KINDS = re.compile(r"const ACQUISITION_KINDS = \[([^\]]*)\]")
_QID = re.compile(r'"([^"]+)"')


def parse_rules() -> list[dict[str, object]]:
    """Return the switches of business-rules.ts (template rules expanded)."""
    lines = RULES_TS.read_text(encoding="utf-8").splitlines()
    kinds_match = _KINDS.search("\n".join(lines))
    kinds = _QID.findall(kinds_match.group(1)) if kinds_match else []
    legal = [(m.group(1), _QID.findall(m.group(2))) for line in lines if (m := _SLUG.search(line))]
    rules: list[dict[str, object]] = []
    cur: dict[str, object] | None = None
    for line in lines:
        m = _ID.match(line)
        t = _TEMPLATE_ID.match(line)
        if m or t:
            cur = {"id": (m or t).group(1), "group": "", "pkg": "", "default": "", "questions": []}  # type: ignore[union-attr]
            rules.append(cur)
            continue
        if cur is None:
            continue
        for rx, key in ((_GROUP, "group"), (_PKG, "pkg")):
            g = rx.match(line)
            if g and not cur[key]:
                cur[key] = g.group(1)
        d = _DEFAULT.match(line)
        if d and not cur["default"]:
            cur["default"] = d.group(1).strip('"')
        q = _QUESTIONS.search(line)
        if q and not cur["questions"]:
            cur["questions"] = _QID.findall(q.group(1))
    out: list[dict[str, object]] = []
    for r in rules:
        rid = str(r["id"])
        if rid.startswith("acquisition-${"):
            out.extend({**r, "id": f"acquisition-{k.replace('_', '-')}"} for k in kinds)
        elif rid.startswith("legal-basis-${"):
            out.extend({**r, "id": f"legal-basis-{s}", "questions": q} for s, q in legal)
        else:
            out.append(r)
    return out


def parse_python_switch_keys() -> dict[str, str]:
    """Namespaced switch keys (``SWITCH_KEY = "area.name"``) with their source file."""
    found: dict[str, str] = {}
    rx = re.compile(r'^SWITCH_KEY\s*=\s*"([a-z_]+\.[a-z_]+)"', re.M)
    for path in sorted(API_SRC.rglob("*.py")):
        for m in rx.finditer(path.read_text(encoding="utf-8")):
            found[m.group(1)] = str(path.relative_to(ROOT))
    return found


def parse_questions() -> list[dict[str, object]]:
    """Rows of docs/OPEN_QUESTIONS.md: id, status, owner, gate cell, full text."""
    rows: list[dict[str, object]] = []
    header: list[str] | None = None
    lines = QUESTIONS.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("| ") or line.startswith("| ---"):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line.strip()[1:-1])]
        if i + 1 < len(lines) and lines[i + 1].startswith("| ---"):
            header = cells
            continue
        if header is None or len(cells) < 4:
            continue
        status = cells[-2] if len(cells) >= 6 else ""
        gate_owner = cells[2:-3] if len(cells) >= 7 else cells[2:]
        rows.append(
            {
                "id": cells[0],
                "status": status,
                "cells": cells,
                "gate_owner": gate_owner,
                "well_formed": len(cells) == len(header),
                "header": header,
                "text": line,
            }
        )
    return rows


def rule_file_ids() -> set[str]:
    return {p.stem for p in RULES_DIR.glob("*.md")}


def render() -> str:
    rules = parse_rules()
    keys = parse_python_switch_keys()
    out = [
        START,
        "",
        f"Stand der Registry: {len(rules)} Schalter der Seite Fachliche Regeln und "
        f"{len(keys)} Schlüssel in den Mandantenquellen.",
        "",
        "| Schalter | Bereich | Paket | Standard | Offene Frage |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in sorted(rules, key=lambda x: (str(x["group"]), str(x["id"]))):
        qs = ", ".join(str(q) for q in r["questions"]) or "keine"  # type: ignore[attr-defined]
        default = str(r["default"]).replace("|", "/") or "siehe Seite"
        out.append(f"| `{r['id']}` | {r['group']} | {r['pkg']} | {default} | {qs} |")
    out += ["", "Schlüssel in den Mandantenquellen:", ""]
    out += [f"- `{k}` ({v})" for k, v in sorted(keys.items())]
    out += ["", END]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    text = TARGET.read_text(encoding="utf-8")
    block = render()
    if START in text and END in text:
        pre, rest = text.split(START, 1)
        _, post = rest.split(END, 1)
        new = pre + block + post
    else:
        new = text.rstrip("\n") + "\n\n## Schalterverzeichnis\n\n" + block + "\n"
    if "--check" in argv:
        if new != text:
            sys.stderr.write(
                "docs/handbuch/einstellungen.md: Schalterverzeichnis veraltet, "
                "python3 scripts/build_switch_index.py ausführen\n"
            )
            return 1
        return 0
    TARGET.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
