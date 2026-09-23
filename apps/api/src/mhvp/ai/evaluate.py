"""Offline evaluation (9.1): recorded answers run through schema validation and the platform's
post-processing, compared field by field with independent expectations.

This measures everything after the model call (validation, normalisation, rejection of invalid
values, preview). It does not measure model quality; that needs a live run with released
provider data (M7-05). Usage: ``python -m mhvp.ai.evaluate [folder]``.
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mhvp.ai import imports, tasks
from mhvp.ai.models import AiTask

THRESHOLD = 0.95
MIN_CASES = 20


def _f1(tp: int, fp: int, fn: int) -> float:
    if tp == 0:
        return 1.0 if fp == fn == 0 else 0.0
    precision, recall = tp / (tp + fp), tp / (tp + fn)
    return 2 * precision * recall / (precision + recall)


def _score(pairs: list[tuple[Any, Any]]) -> tuple[int, int, int]:
    tp = sum(1 for got, want in pairs if got == want)
    wrong = len(pairs) - tp
    return tp, wrong, wrong


def _contacts(output: dict[str, Any], expected: list[dict[str, Any]]) -> list[tuple[Any, Any]]:
    pairs: list[tuple[Any, Any]] = []
    for item, want in zip(output["contacts"], expected, strict=True):
        notes: list[str] = []
        contact = imports._contact_in(item, notes)
        if contact is None:
            pairs += [(None, want[k]) for k in want]
            continue
        got = {
            "status": "incomplete" if contact.completeness.value == "incomplete" else "new",
            "phone_valid": bool(contact.phones),
            "email_valid": bool(contact.emails),
            "iban_valid": bool(contact.bank_accounts),
            "name": contact.company_name or contact.last_name,
            "role": item.get("role"),
        }
        pairs += [(got[k], want[k]) for k in want]
    return pairs


def _property(output: dict[str, Any], expected: dict[str, Any]) -> list[tuple[Any, Any]]:
    preview = imports.property_preview(output)
    pairs: list[tuple[Any, Any]] = [
        (preview["property"]["management_type"], expected["management_type"])
    ]
    for unit, want in zip(preview["units"], expected["units"], strict=True):
        pairs += [
            (unit["number"], want["number"]),
            (unit["living_area_sqm"], want["area"]),
            (unit["mea"], want["mea"]),
        ]
    for party, want in zip(preview["parties"], expected["parties"], strict=True):
        pairs += [
            (party["unit_number"], want["unit_number"]),
            (party["start_date"] is not None, want["has_start"]),
        ]
    return pairs


def _answer(output: dict[str, Any], expected: dict[str, Any]) -> list[tuple[Any, Any]]:
    return [
        (output["answerable"], expected["answerable"]),
        (len(output["sources"]), expected["source_count"]),
    ]


def _summary(output: dict[str, Any], expected: dict[str, Any]) -> list[tuple[Any, Any]]:
    return [(len(output["open_points"]), expected["open_points"])]


SCORERS: dict[AiTask, Callable[[dict[str, Any], Any], list[tuple[Any, Any]]]] = {
    AiTask.EXTRACT_CONTACTS: _contacts,
    AiTask.EXTRACT_PROPERTY: _property,
    AiTask.ANSWER_QUESTION: _answer,
    AiTask.SUMMARIZE: _summary,
}


def evaluate(folder: Path) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for task, scorer in SCORERS.items():
        cases = [
            json.loads(line)
            for line in (folder / task.value / "cases.jsonl").read_text("utf-8").splitlines()
            if line.strip()
        ]
        tp = fp = fn = 0
        for case in cases:
            output = (
                tasks.SCHEMAS[task].model_validate(case["recorded_output"]).model_dump(mode="json")
            )
            a, b, c = _score(scorer(output, case["expected"]))
            tp, fp, fn = tp + a, fp + b, fn + c
        report[task.value] = {"cases": len(cases), "field_f1": round(_f1(tp, fp, fn), 4)}
    return report


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else Path("tests/ai_eval")
    report = evaluate(folder)
    print(json.dumps(report, indent=2))  # noqa: T201 - CLI output
    failed = [t for t, r in report.items() if r["cases"] < MIN_CASES or r["field_f1"] < THRESHOLD]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
