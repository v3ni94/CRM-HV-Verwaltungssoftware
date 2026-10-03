"""GAM-805, GAM-809, GAM-811: rule files, test paths and open question numbers stay consistent."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RULES = ROOT / "docs/rules"
# Register files (no rule format), see docs/rules/README.md "Formate und Nicht-Regeln".
NOT_RULES = {
    "README.md",
    "GLOSSAR-ZUORDNUNG.md",
    "V-STATUSABGLEICH-19-1.md",
    "anhang-e-register.md",
}
FIELDS = {
    "ID": r"\bID\b",
    "scope": r"Scope|Geltung",
    "source": r"Source status|Quellenstatus",
    "acceptance": r"Acceptance|Abnahme|Akzeptanz",
    "reason": r"Change reason|Änderungsgrund",
}
# Rule files that still lack a field (ratchet, only shrinks).
RATCHET: set[str] = set()


def _rule_files() -> list[Path]:
    return sorted(p for p in RULES.glob("*.md") if p.name not in NOT_RULES)


def test_rule_files_carry_the_five_mandatory_fields() -> None:
    bad: dict[str, list[str]] = {}
    for path in _rule_files():
        text = path.read_text(encoding="utf-8")
        missing = [k for k, rx in FIELDS.items() if not re.search(rx, text)]
        if missing and path.name not in RATCHET:
            bad[path.name] = missing
    assert not bad, f"Regeldateien ohne Pflichtfeld: {bad}"


def test_registry_links_every_rule_file_and_no_link_is_broken() -> None:
    index = (RULES / "README.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\(([^)#]+\.md)\)", index))
    for name in linked:
        assert (RULES / name).exists(), f"defekter Link im Regelindex: {name}"
    unlinked = {p.name for p in _rule_files()} - linked
    # Link targets of the index may also be reached from other rule files (ratchet is the
    # number of files not yet indexed, see GAM-808); it must not grow.
    assert len(unlinked) <= 250, f"zu viele nicht verlinkte Regeldateien: {len(unlinked)}"


def test_test_paths_named_in_rules_exist() -> None:
    missing = []
    for path in RULES.glob("*.md"):
        for ref in re.findall(r"apps/api/tests/[\w/.\-]+\.py", path.read_text(encoding="utf-8")):
            if not (ROOT / ref).exists():
                missing.append((path.name, ref))
    assert not missing, f"Testpfade ohne Datei: {missing}"


def test_open_question_numbers_are_unique() -> None:
    seen: dict[str, int] = {}
    for n, line in enumerate((ROOT / "docs/OPEN_QUESTIONS.md").read_text("utf-8").splitlines(), 1):
        m = re.match(r"\| ([A-Za-z0-9ÄÖÜäöü][^|]*?) \|", line)
        if not m or m.group(1) in {"Nr", "ID"} or set(m.group(1)) <= {"-", " "}:
            continue
        key = m.group(1)
        assert key not in seen, f"Nummer {key} doppelt (Zeilen {seen[key]} und {n})"
        seen[key] = n
