#!/usr/bin/env python3
"""Generate CLAUDE.md and AGENTS.md from docs/AGENT_RULES.md (rule 0.1.11).

Usage:
    python3 scripts/sync_agent_docs.py          write both files
    python3 scripts/sync_agent_docs.py --check  exit 1 if either file is stale
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "AGENT_RULES.md"
MARKER = "<!-- GENERATED from docs/AGENT_RULES.md by scripts/sync_agent_docs.py, do not edit -->"

HEADERS = {
    "CLAUDE.md": (
        "# CLAUDE.md\n\n"
        "Instructions for Claude Code in this repository. The authoritative specification is\n"
        "`docs/MASTER-PROMPT.md`; the shared rules below are identical to `AGENTS.md`.\n"
    ),
    "AGENTS.md": (
        "# AGENTS.md\n\n"
        "Instructions for Codex and other coding agents in this repository. The authoritative\n"
        "specification is `docs/MASTER-PROMPT.md`; the shared rules below are identical to\n"
        "`CLAUDE.md`.\n"
    ),
}


def render(name: str, source: str) -> str:
    """Return the generated content of one target file."""
    body = source.split("\n", 1)[1] if source.startswith("# ") else source
    return f"{MARKER}\n\n{HEADERS[name]}\n{body.lstrip(chr(10))}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync CLAUDE.md and AGENTS.md")
    parser.add_argument("--check", action="store_true", help="only verify, do not write")
    args = parser.parse_args()

    source = SOURCE.read_text(encoding="utf-8")
    stale: list[str] = []
    for name in HEADERS:
        target = ROOT / name
        expected = render(name, source)
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current == expected:
            continue
        if args.check:
            stale.append(name)
            diff = difflib.unified_diff(
                current.splitlines(),
                expected.splitlines(),
                name,
                f"{name} (expected)",
                lineterm="",
                n=1,
            )
            print("\n".join(list(diff)[:40]), file=sys.stderr)
        else:
            target.write_text(expected, encoding="utf-8")
            print(f"wrote {name}")
    if stale:
        print(
            f"stale: {', '.join(stale)}. Run 'make agent-docs' "
            "(python3 scripts/sync_agent_docs.py) and commit the result.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
