"""AM10 (GAJ-503, GAJ-504): G1 opening items of 18.0 and checkable evidence references."""

import uuid

import pytest

from mhvp.accounting.g1_opening import (
    EVIDENCE_REQUIRED_KEYS,
    MANUAL_KEYS,
    check_evidence_ref,
    evidence_kind,
)
from mhvp.core.problems import ProblemError
from mhvp.core.release_gates import ReleaseGate
from mhvp.platform.gate_checklists import unverified_checklist_items


def test_18_0_items_are_part_of_the_g1_package() -> None:
    expected = {"migration_verified", "legal_entity_separation", "documented_correction"}
    assert expected <= MANUAL_KEYS
    assert expected == EVIDENCE_REQUIRED_KEYS


@pytest.mark.parametrize(
    ("ref", "doc", "kind"),
    [
        ("ci-run:12345@abc1234", None, "test_run"),
        ("ci-run:https://github.com/o/r/actions/runs/9@" + "a" * 40, None, "test_run"),
        ("commit:deadbeef", None, "test_state"),
        ("version:1.67.0", None, "test_state"),
        ("doc:docs/acceptance/abnahme-anhang-d.md", None, "document"),
        ("Schreiben Steuerberatung", None, "reference"),
        (None, uuid.uuid4(), "document"),
        ("", None, None),
        ("ci-run:12345", None, "reference"),
    ],
)
def test_evidence_kind(ref: str | None, doc: uuid.UUID | None, kind: str | None) -> None:
    assert evidence_kind(ref, doc) == kind


def test_malformed_typed_reference_is_refused() -> None:
    check_evidence_ref("Protokoll vom 01.10.2026")
    check_evidence_ref("ci-run:7@abcdef1")
    for bad in ("ci-run:7", "commit:xyz", "version:1.2", "doc:"):
        with pytest.raises(ProblemError):
            check_evidence_ref(bad)


def test_unverified_checklist_items() -> None:
    checklist = {
        "bank_contract": "geprüft doc:docs/runbooks/bank.md",
        "permissions": "geprüft",
        "reconciliation": "Lauf ci-run:42@abcdef1",
    }
    assert unverified_checklist_items(ReleaseGate.G2, checklist) == ["permissions"]
    assert unverified_checklist_items(ReleaseGate.G2, None) == []
