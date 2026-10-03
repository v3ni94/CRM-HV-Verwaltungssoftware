#!/usr/bin/env python3
"""Checks that acceptance protocols follow annex D.3 (GAK-403).

Every ``docs/acceptance/PROTOKOLL-*.md`` must name the rule version, the reviewer and the
software state in its head and carry the detail table with the D.3 columns. Protocols from
before this check are listed in LEGACY (ratchet: the list may only shrink; the template
itself is checked too).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE = ROOT / "docs" / "acceptance"
LEGACY = frozenset(
    {
        "PROTOKOLL-2026-09-26.md",
        "PROTOKOLL-2026-09-30.md",
        "PROTOKOLL-2026-10-01-T13.md",
        "PROTOKOLL-2026-10-01-U12.md",
        "PROTOKOLL-2026-10-01-WELLEN-12-13.md",
        "PROTOKOLL-2026-10-01-WELLEN-4-7.md",
    }
)
HEAD_TOKENS = ("Regelversion", "Prüfer", "Softwarestand")
COLUMNS = (
    "Kennung",
    "Regelversion",
    "Annahmen",
    "Eingaben",
    "Erwartet",
    "Beobachtet",
    "Differenz",
    "Testbefehl",
    "Softwarestand",
    "Prüfer",
    "Status",
)


def problems(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = [f"{path.name}: Kopfangabe fehlt: {t}" for t in HEAD_TOKENS if t not in text]
    header = next(
        (ln for ln in text.splitlines() if ln.startswith("|") and "Kennung" in ln and "Erwartet" in ln),
        "",
    )
    found += [f"{path.name}: Spalte fehlt: {c}" for c in COLUMNS if c not in header]
    return found


def protocol_files() -> list[Path]:
    files = sorted(ACCEPTANCE.glob("PROTOKOLL-*.md"))
    return [f for f in files if f.name not in LEGACY]


def main() -> int:
    found = [p for f in protocol_files() for p in problems(f)]
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
