"""Rules of the online meeting without database access (AE31, AD06-01 to AD06-03).

Two things are decided here and nothing else:

* the tenant rule for a unit that receives a vote of the owner and a vote of the proxy holder
  (``decide_conflict``). Four variants, the conservative default ``flag`` discards no vote and
  only marks the conflict for review by the meeting chair;
* the checklist of recorded facts for the form of the meeting (``admissibility_checks``). It
  lists what is recorded about the enabling resolution and the switches. It states no legal
  rule and does not decide whether a purely virtual meeting is admissible; that stays with the
  operator and legal advice (docs/OPEN_QUESTIONS.md AD06-01).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from mhvp.hoa.meeting_rules import (
    ENABLING_STATUSES,
    basis_term_notice,
    transition_notice,
)

PROXY_CONFLICT_MODES = ("flag", "first_vote", "proxy_priority", "own_priority")
DEFAULT_PROXY_CONFLICT_MODE = "flag"
SOURCES = ("own", "proxy")

MODE_LABELS = {
    "flag": "Konflikt als Prüfhinweis markieren, keine Stimme verwerfen (Standard)",
    "first_vote": "Zuerst abgegebene Stimme zählt, die zweite wird abgewiesen",
    "proxy_priority": "Stimme des Bevollmächtigten hat Vorrang",
    "own_priority": "Eigene Stimme des Eigentümers hat Vorrang",
}
SOURCE_LABELS = {"own": "Eigentümer", "proxy": "Bevollmächtigter"}
CHOICE_LABELS = {"yes": "Ja", "no": "Nein", "abstain": "Enthaltung"}

# Decisions of decide_conflict
DUPLICATE = "duplicate"  # same source twice: always refused (409)
REVIEW = "review"  # keep the first vote, store the second for review
REJECT = "reject"  # refuse the second vote (409)
REPLACE = "replace"  # the second vote replaces the first one, the first stays in the record

ADMISSIBILITY_NOTE = (
    "Übersicht der erfassten Angaben zur Form der Versammlung. Das System prüft die rechtliche "
    "Zulässigkeit nicht und gibt keine Rechtsauskunft. Die Klärung erfolgt durch den Betreiber "
    "mit Rechtsberatung (offene Frage AD06-01, Grundlagenbeschluss GA07-01)."
)
CONFLICT_NOTE = (
    "Vollmacht gegen eigene Stimme: Die Regel ist eine Mandanteneinstellung des Betreibers und "
    "keine Rechtsauskunft. Die Wirkung einer zweiten Stimme ist rechtlich zu klären "
    "(offene Frage AD06-02)."
)

STATE_LABELS = {
    "ok": "erfasst",
    "open": "zu prüfen",
    "missing": "nicht erfasst",
    "info": "Hinweis",
}


def vote_source(proxy_id: object | None, *, cast_source: str | None = None) -> str:
    """Source of a recorded vote: the stored value, else ``proxy`` when a proxy is linked."""
    if cast_source in SOURCES:
        return str(cast_source)
    return "proxy" if proxy_id is not None else "own"


def decide_conflict(mode: str, first_source: str, second_source: str) -> str:
    """What happens with a second vote for a unit that already has a vote.

    The same source twice is always a duplicate. For owner against proxy holder the tenant
    mode decides: ``flag`` keeps the first vote and stores the second for review,
    ``first_vote`` refuses the second, ``proxy_priority`` and ``own_priority`` let the
    preferred source replace the other one (and refuse the other direction)."""
    if first_source == second_source:
        return DUPLICATE
    if mode == "first_vote":
        return REJECT
    if mode == "proxy_priority":
        return REPLACE if second_source == "proxy" else REJECT
    if mode == "own_priority":
        return REPLACE if second_source == "own" else REJECT
    return REVIEW


def _check(key: str, state: str, label: str, detail: str) -> dict[str, str]:
    return {
        "key": key,
        "state": state,
        "state_label": STATE_LABELS[state],
        "label": label,
        "detail": detail,
    }


def _fmt(day: date) -> str:
    return f"{day:%d.%m.%Y}"


def admissibility_checks(
    *,
    mode: str,
    meeting_day: date,
    online_switch: bool,
    virtual_switch: bool,
    basis_number: int | None,
    basis_decided_on: date | None,
    basis_status: str | None,
    valid_until: date | None,
    transition_date: date | None,
    has_conference_link: bool,
    conflict_mode: str,
) -> dict[str, Any]:
    """Checklist of recorded facts for a hybrid or virtual meeting (no legal statement).

    States: ``ok`` recorded, ``open`` to be checked, ``missing`` not recorded or not valid,
    ``info`` plain note. A presence meeting has no checks."""
    if mode == "presence":
        return {"applicable": False, "complete": True, "checks": [], "note": ADMISSIBILITY_NOTE}
    checks: list[dict[str, str]] = [
        _check(
            "online_switch",
            "ok" if online_switch else "open",
            "Schalter Online-Versammlung im Portal",
            "eingeschaltet" if online_switch else "ausgeschaltet (Standard)",
        )
    ]
    if mode == "virtual":
        checks.append(
            _check(
                "virtual_switch",
                "ok" if virtual_switch else "open",
                "Schalter virtuelle Versammlungen (V13)",
                "eingeschaltet" if virtual_switch else "ausgeschaltet (Standard)",
            )
        )
        if basis_status is None or basis_decided_on is None:
            checks.append(
                _check(
                    "basis_resolution",
                    "missing",
                    "Zulassender Beschluss",
                    "Kein Beschluss verknüpft.",
                )
            )
        else:
            ref = (
                f"Beschluss Nr. {basis_number} vom {_fmt(basis_decided_on)}, Status {basis_status}"
            )
            if basis_status in ENABLING_STATUSES:
                state, detail = "ok", ref
            elif basis_status == "contested":
                state, detail = "open", f"{ref}. Der Beschluss ist angefochten, Folgen prüfen."
            else:
                state, detail = "missing", f"{ref}. Der Status trägt die Versammlungsform nicht."
            checks.append(_check("basis_resolution", state, "Zulassender Beschluss", detail))
            if valid_until is None:
                checks.append(_check("valid_until", "missing", "Gültigkeitsende", "Nicht erfasst."))
            elif valid_until < meeting_day:
                checks.append(
                    _check(
                        "valid_until",
                        "missing",
                        "Gültigkeitsende",
                        f"{_fmt(valid_until)} liegt vor dem Versammlungstag {_fmt(meeting_day)}.",
                    )
                )
            else:
                checks.append(
                    _check(
                        "valid_until",
                        "ok",
                        "Gültigkeitsende",
                        f"{_fmt(valid_until)}, nicht vor dem Versammlungstag.",
                    )
                )
                term = basis_term_notice(basis_decided_on, valid_until)
                checks.append(
                    _check(
                        "term_limit",
                        "open" if term else "ok",
                        "Geltungsdauer (Orientierung)",
                        term or "Nicht länger als drei Jahre ab Beschlussdatum (zu verifizieren).",
                    )
                )
            hint = transition_notice(basis_decided_on, transition_date)
            if hint:
                checks.append(_check("transition", "info", "Übergangsregel", hint))
    else:
        checks.append(
            _check(
                "hybrid_basis",
                "open",
                "Hybride Form",
                "Ob die Online-Stimmabgabe bei hybrider Form ohne weiteren Beschluss möglich "
                "ist, ist offen (AD06-01).",
            )
        )
    checks.append(
        _check(
            "conference_link",
            "ok" if has_conference_link else "missing",
            "Konferenzlink",
            "hinterlegt" if has_conference_link else "Nicht hinterlegt.",
        )
    )
    checks.append(
        _check(
            "vote_rule",
            "info",
            "Regel Vollmacht gegen eigene Stimme",
            MODE_LABELS.get(conflict_mode, conflict_mode),
        )
    )
    complete = all(c["state"] in ("ok", "info") for c in checks)
    return {"applicable": True, "complete": complete, "checks": checks, "note": ADMISSIBILITY_NOTE}


def conflict_sentence(
    *,
    unit: str,
    first_source: str,
    first_choice: str,
    second_source: str,
    second_choice: str,
    status: str,
    resolution: str | None,
) -> str:
    """One protocol sentence for a vote conflict of a unit (owner against proxy holder)."""
    first = f"{SOURCE_LABELS[first_source]}: {CHOICE_LABELS.get(first_choice, first_choice)}"
    second = f"{SOURCE_LABELS[second_source]}: {CHOICE_LABELS.get(second_choice, second_choice)}"
    base = f"Einheit {unit}: Es liegen zwei Stimmen vor, zuerst {first}, danach {second}. "
    if status == "open":
        return (
            base
            + f"Gezählt wird bis zur Entscheidung die erste Stimme ({first}). "
            + "Entscheidung der Versammlungsleitung offen."
        )
    if resolution == "apply_second":
        return base + "Die Versammlungsleitung hat die zweite Stimme zählen lassen."
    if resolution == "rule_second":
        return (
            base
            + "Nach der Regel des Mandanten ersetzt die zweite Stimme die erste; "
            + "die erste Stimme ist im Vorgang dokumentiert."
        )
    return base + "Die Versammlungsleitung hat die erste Stimme bestätigt."
