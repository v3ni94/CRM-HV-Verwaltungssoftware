"""A46 (9.1, M7): offline evaluation sets for ``classify_email``, ``draft_reply``,
``map_columns`` and ``contact_master_data_change`` (M7-08) with the pure post-processing they
score. Expected values are written by hand in ``tests/ai_eval/<task>/cases.jsonl``."""

from pathlib import Path

import pytest

from mhvp.ai import evaluate, table_mapper
from mhvp.ai.models import AiTask
from mhvp.communication.suggest import fallback_suggestion, merge_suggestion, playbook_fields

FOLDER = Path(__file__).parents[1] / "ai_eval"
NEW_TASKS = (
    AiTask.CLASSIFY_EMAIL,
    AiTask.DRAFT_REPLY,
    AiTask.MAP_COLUMNS,
    AiTask.CONTACT_MASTER_DATA_CHANGE,
)


@pytest.mark.parametrize("task", NEW_TASKS, ids=lambda t: t.value)
def test_case_sets_have_minimum_size_unique_ids_and_an_injection_case(task: AiTask) -> None:
    cases = evaluate.load_cases(FOLDER, task)
    ids = [c["id"] for c in cases]
    assert len(cases) >= evaluate.MIN_CASES
    assert len(ids) == len(set(ids))
    assert any("injection" in i for i in ids), "one prompt injection case per task (0.1.13)"
    for case in cases:
        assert {"id", "input", "recorded_output", "expected"} <= set(case)


@pytest.mark.parametrize("task", NEW_TASKS, ids=lambda t: t.value)
def test_offline_evaluation_reaches_threshold(task: AiTask) -> None:
    report = evaluate.evaluate(FOLDER)
    assert report[task.value]["cases"] >= evaluate.MIN_CASES
    assert report[task.value]["field_f1"] >= evaluate.THRESHOLD


def test_every_case_scores_at_least_one_pair() -> None:
    for task in NEW_TASKS:
        for case in evaluate.load_cases(FOLDER, task):
            assert evaluate.score_case(task, case), f"{task.value}/{case['id']}"


def test_propose_posting_has_schema_and_a_first_evaluation_set() -> None:
    """M7-09 umgesetzt, deaktiviert bis Freigabe M12-01: Schema, Scorer und zehn Fälle."""
    from mhvp.ai import tasks

    assert AiTask.PROPOSE_POSTING in tasks.SCHEMAS
    assert AiTask.PROPOSE_POSTING in evaluate.INPUT_SCORERS
    cases = evaluate.load_cases(FOLDER, AiTask.PROPOSE_POSTING)
    assert len(cases) >= evaluate.min_cases(AiTask.PROPOSE_POSTING) == 10
    assert any("injection" in c["id"] for c in cases)


def test_merge_suggestion_falls_back_only_for_empty_classification_fields() -> None:
    fallback = fallback_suggestion(
        "Dringend: Heizung", "Objekt 104, Heizung kalt", ["Heizung", "Sonstiges"]
    )
    assert fallback == {
        "category": "Heizung",
        "urgency": "high",
        "summary": "Dringend: Heizung",
        "property_number": "104",
        "contact_name": None,
        "reply_draft": None,
    }
    merged = merge_suggestion(
        {
            "category": "",
            "urgency": None,
            "summary": "",
            "property_number": None,
            "contact_name": None,
            "reply_draft": None,
        },
        fallback,
    )
    assert merged["category"] == "Heizung"
    assert merged["urgency"] == "high"
    assert merged["property_number"] == "104"
    assert merged["contact_name"] is None  # never invented by the fallback
    assert merged["reply_draft"] is None
    kept = merge_suggestion(
        {"category": "Sonstiges", "urgency": "low", "summary": "s", "property_number": "555"},
        fallback,
    )
    assert (kept["category"], kept["urgency"], kept["property_number"]) == (
        "Sonstiges",
        "low",
        "555",
    )


def test_playbook_fields_limits() -> None:
    fields = playbook_fields(
        {
            "title": "",
            "category": None,
            "keywords": [f"k{i}" * 40 for i in range(12)],
            "summary": None,
            "steps": [1, "zwei"],
            "reply_template": None,
        },
        "Ticket-Titel",
    )
    assert fields["title"] == "Ticket-Titel"
    assert len(fields["keywords"]) == 10
    assert all(len(k) <= 64 for k in fields["keywords"])
    assert fields["summary"] == ""
    assert fields["steps"] == ["1", "zwei"]
    assert fields["reply_template"] is None


def test_mapping_usable_needs_header_and_min_confidence() -> None:
    assert table_mapper.mapping_usable(None) is False
    assert table_mapper.mapping_usable({"has_header": False, "confidence": 1.0}) is False
    assert table_mapper.mapping_usable({"has_header": True, "confidence": 0.59}) is False
    assert table_mapper.mapping_usable({"has_header": True, "confidence": 0.6}) is True
    assert table_mapper.mapping_usable({"has_header": True, "confidence": None}) is False
