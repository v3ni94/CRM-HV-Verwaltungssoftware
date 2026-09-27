"""M35 Stufe 5: pure reconciliation objektakte vs. CRM (`mhvp.objektakte.reconciliation`)."""

from __future__ import annotations

from typing import Any

from mhvp.objektakte.reconciliation import CrmDoc, RemoteDoc, reconcile, remote_documents


def test_counts_missing_and_hash_differences_per_object() -> None:
    crm = [
        CrmDoc("1", "a" * 64, "291"),
        CrmDoc("2", "b" * 64, "291"),
        CrmDoc("3", "c" * 64, "291", placeholder=True),
        CrmDoc("9", "d" * 64, None),  # not linked to a property in the CRM
    ]
    remote = [
        RemoteDoc("1", "A" * 64, "291"),  # same hash, other case
        RemoteDoc("2", "x" * 64, "291"),  # differs
        RemoteDoc("3", "c" * 64, "291"),  # placeholder in CRM: not a mismatch
        RemoteDoc("4", "e" * 64, "291"),  # missing in CRM
        RemoteDoc("5", None, "077"),  # missing in CRM, no hash yet
    ]
    report = reconcile(crm, remote)
    assert report["ok"] is False
    objects = {o["object_number"]: o for o in report["objects"]}
    assert set(objects) == {"077", "291", "ohne_objekt"}
    obj = objects["291"]
    assert obj["objektakte_count"] == 4
    assert obj["crm_count"] == 3
    assert obj["missing_in_crm"] == ["4"]
    assert obj["missing_in_crm_total"] == 1
    assert obj["hash_mismatches"] == [{"source_id": "2", "crm": "b" * 64, "objektakte": "x" * 64}]
    assert obj["placeholders"] == 1
    assert objects["077"]["missing_in_crm"] == ["5"]
    assert objects["ohne_objekt"]["missing_in_objektakte"] == ["9"]
    assert report["totals"] == {
        "objects": 3,
        "objektakte_documents": 5,
        "crm_documents": 4,
        "missing_in_crm": 2,
        "missing_in_objektakte": 1,
        "hash_mismatches": 1,
        "placeholders": 1,
        "objects_with_differences": 3,
    }


def test_identical_sides_are_ok() -> None:
    crm = [CrmDoc(str(i), f"{i:064x}", "291") for i in range(3)]
    remote = [RemoteDoc(str(i), f"{i:064x}", "291") for i in range(3)]
    report = reconcile(crm, remote)
    assert report["ok"] is True
    assert report["objects"][0]["ok"] is True
    assert report["totals"]["objects_with_differences"] == 0


def test_remote_rows_become_docs_with_string_ids() -> None:
    rows: list[dict[str, Any]] = [{"id": 7, "sha256": "ABC"}, {"id": None}, {"id": 8}]
    docs = remote_documents("291", rows)
    assert [(d.source_id, d.sha256) for d in docs] == [("7", "abc"), ("8", None)]
