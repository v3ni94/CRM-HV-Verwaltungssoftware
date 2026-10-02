"""AF21 (GAB-14, 9.1): offline evaluation sets for ``classify_document``, ``call_summary`` and
``rent_increase_check``. Cases are synthetic and anonymised (no real names, numbers or IBANs);
expected values are written by hand in ``tests/ai_eval/<task>/cases.jsonl``."""

import json
import re
from pathlib import Path

import pytest

from mhvp.ai import evaluate, tasks
from mhvp.ai.models import AiTask

FOLDER = Path(__file__).parents[1] / "ai_eval"
TASKS_UNDER_TEST = (AiTask.CLASSIFY_DOCUMENT, AiTask.CALL_SUMMARY, AiTask.RENT_INCREASE_CHECK)
IBAN_LIKE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?\d{4}){4,7}(?: ?\d{1,2})?\b")


@pytest.mark.parametrize("task", TASKS_UNDER_TEST, ids=lambda t: t.value)
def test_case_sets_have_minimum_size_unique_ids_and_synthetic_data(task: AiTask) -> None:
    cases = evaluate.load_cases(FOLDER, task)
    ids = [c["id"] for c in cases]
    assert len(cases) >= 20
    assert len(ids) == len(set(ids))
    text = (FOLDER / task.value / "cases.jsonl").read_text("utf-8")
    for match in IBAN_LIKE.findall(text):
        assert set(match.replace(" ", "")[4:]) == {"0"}, f"non synthetic IBAN {match}"
    for case in cases:
        assert {"id", "input", "recorded_output", "expected"} <= set(case)
        tasks.SCHEMAS[task].model_validate(case["recorded_output"])


@pytest.mark.parametrize(
    "task", [AiTask.CLASSIFY_DOCUMENT, AiTask.CALL_SUMMARY], ids=lambda t: t.value
)
def test_text_tasks_have_an_injection_case(task: AiTask) -> None:
    assert any("injection" in c["id"] for c in evaluate.load_cases(FOLDER, task))


@pytest.mark.parametrize("task", TASKS_UNDER_TEST, ids=lambda t: t.value)
def test_every_case_matches_its_expectation(task: AiTask) -> None:
    for case in evaluate.load_cases(FOLDER, task):
        pairs = evaluate.score_case(task, case)
        assert pairs, case["id"]
        assert all(got == want for got, want in pairs), f"{task.value}/{case['id']}"


def test_report_covers_the_three_tasks_above_threshold() -> None:
    report = evaluate.evaluate(FOLDER)
    for task in TASKS_UNDER_TEST:
        assert report[task.value]["cases"] >= evaluate.MIN_CASES
        assert report[task.value]["field_f1"] >= evaluate.THRESHOLD


def test_a_wrong_expectation_lowers_the_score() -> None:
    """The scorers can fail: a flipped expectation is counted as an error."""
    case = json.loads(json.dumps(evaluate.load_cases(FOLDER, AiTask.RENT_INCREASE_CHECK)[3]))
    case["expected"]["overall"] = (
        "kritisch" if case["expected"]["overall"] != "kritisch" else "pruefen"
    )
    pairs = evaluate.score_case(AiTask.RENT_INCREASE_CHECK, case)
    assert any(got != want for got, want in pairs)


def test_every_prompt_with_a_task_schema_is_scored() -> None:
    """Make ai-eval covers the three prompts named in GAB-14."""
    for task in TASKS_UNDER_TEST:
        assert task in evaluate.SCORERS or task in evaluate.INPUT_SCORERS
