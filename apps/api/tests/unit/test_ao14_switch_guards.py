"""AO14: switches, open questions and the generated switch index stay consistent.

Ratchet lists live in ``tests/unit/data/ao14_ratchet.json`` (one reason per entry); an entry
that no longer violates the rule must be removed, so the lists only shrink.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
_SCRIPT = ROOT / "scripts/build_switch_index.py"
_spec = importlib.util.spec_from_file_location("build_switch_index", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
idx = importlib.util.module_from_spec(_spec)
sys.modules["build_switch_index"] = idx
_spec.loader.exec_module(idx)

RATCHET = json.loads((Path(__file__).parent / "data/ao14_ratchet.json").read_text(encoding="utf-8"))
OWNER = re.compile(
    r"Betreiber|Timo Müller|Entwicklung|Steuer|Rechts|Geschäftsführung|Datenschutz|Messdienst"
    r"|Schadenbearb|Fachbereich|Koordinator|Eigentümer|Coding-Agent",
    re.I,
)
GATE = re.compile(r"\bG[0-5]\b|Gate|Freigabe", re.I)
NOTE = re.compile(r"technisch (vorbereitet|umgesetzt)", re.I)


def _questions() -> dict[str, dict[str, object]]:
    return {str(q["id"]): q for q in idx.parse_questions()}


def _is_open(q: dict[str, object]) -> bool:
    return str(q["status"]).lower().startswith("offen")


def _gate_owner(q: dict[str, object]) -> tuple[str, str]:
    go = [str(c) for c in q["gate_owner"]]  # type: ignore[attr-defined]
    cells = q["cells"]
    if q["well_formed"] and len(cells) == 7:  # type: ignore[arg-type]
        return go[0], go[1] if len(go) > 1 else ""
    joined = " ".join(go)
    return joined, joined


def test_registry_is_parsed() -> None:
    rules = idx.parse_rules()
    assert len(rules) >= 80
    ids = [str(r["id"]) for r in rules]
    assert len(ids) == len(set(ids))


def test_every_switch_names_a_rule_or_an_open_question() -> None:
    known = _questions()
    files = idx.rule_file_ids()
    bad = []
    for r in idx.parse_rules():
        qs = [str(x) for x in r["questions"]]  # type: ignore[attr-defined]
        missing = [x for x in qs if x not in known and x not in files]
        if not qs or missing:
            bad.append((r["id"], qs))
    assert not bad, f"Schalter ohne Regel oder offene Frage: {bad}"


def test_open_questions_of_switches_carry_the_prepared_note() -> None:
    known = _questions()
    ratchet = RATCHET["switch_question_without_note"]
    violating = {
        qid
        for r in idx.parse_rules()
        for qid in (str(x) for x in r["questions"])  # type: ignore[attr-defined]
        if qid in known and _is_open(known[qid]) and not NOTE.search(str(known[qid]["text"]))
    }
    assert violating - set(ratchet) == set(), (
        f"Offene Frage ohne Vermerk technisch vorbereitet: {sorted(violating - set(ratchet))}"
    )
    stale = set(ratchet) - violating
    assert not stale, f"Ratschenliste schrumpfen lassen, Eintrag erledigt: {sorted(stale)}"
    assert all(len(str(v)) > 20 for v in ratchet.values())


def test_python_switch_keys_are_documented() -> None:
    corpus = (ROOT / "docs/OPEN_QUESTIONS.md").read_text(encoding="utf-8")
    for p in [*(ROOT / "docs/rules").glob("*.md"), *(ROOT / "docs/handbuch").glob("*.md")]:
        if p.name != "einstellungen.md":
            corpus += p.read_text(encoding="utf-8")
    for key in idx.parse_python_switch_keys():
        documented = key in corpus or key.replace(".", "_") in corpus
        assert documented, f"Schalterschlüssel {key} ohne Dokumentation"


def test_open_questions_name_owner_and_gate() -> None:
    ratchet = RATCHET["open_without_gate"]
    no_owner, no_gate = [], set()
    for q in idx.parse_questions():
        if not _is_open(q):
            continue
        gate, owner = _gate_owner(q)
        if not OWNER.search(owner):
            no_owner.append(q["id"])
        if not GATE.search(gate):
            no_gate.add(str(q["id"]))
    assert not no_owner, f"Offene Fragen ohne Eigentümer: {no_owner}"
    new = sorted(no_gate - set(ratchet))
    assert not new, f"Offene Fragen ohne Gate: {new}"
    stale = set(ratchet) - no_gate
    assert not stale, f"Ratschenliste schrumpfen lassen, Eintrag erledigt: {sorted(stale)}"
    assert all(len(str(v)) > 20 for v in ratchet.values())


def test_switch_index_is_up_to_date() -> None:
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts/build_switch_index.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
