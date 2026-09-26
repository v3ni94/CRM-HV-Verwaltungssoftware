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
# propose_posting (M7-09) is implemented but disabled until M12-01; its first set has 10
# synthetic cases. M7-09 asks for at least 20 before the task is released.
MIN_CASES_BY_TASK: dict[AiTask, int] = {AiTask.PROPOSE_POSTING: 10}


def min_cases(task: AiTask | str) -> int:
    return MIN_CASES_BY_TASK.get(AiTask(task), MIN_CASES)


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


def _invoice(output: dict[str, Any], expected: dict[str, Any]) -> list[tuple[Any, Any]]:
    """M14 Belegeingang: the per-field derivation (`mhvp.receipts.extraction.field_confidences`)
    on a recorded answer, compared with independently expected values and confidences."""
    from mhvp.receipts.extraction import field_confidences

    fields = field_confidences(output["invoice"])
    return [(fields[name]["value"], want["value"]) for name, want in expected["fields"].items()] + [
        (fields[name]["confidence"], want["confidence"])
        for name, want in expected["fields"].items()
    ]


def _check_statement(output: dict[str, Any], expected: dict[str, Any]) -> list[tuple[Any, Any]]:
    """A35: the normalisation in ``mhvp.billing.ai_check.normalize_result`` (deduplication,
    severity order, overall derived from the highest severity, unknown references cleared) on
    a recorded answer, compared with independently expected overall, highest severity and
    referenced positions."""
    from mhvp.billing.ai_check import normalize_result

    known = expected.get("known_positions")
    result = normalize_result(output, known_positions=set(known) if known else None)
    return [
        (result["overall"], expected["overall"]),
        (result["max_severity"], expected["max_severity"]),
        (result["positions"], expected["positions"]),
        (len(result["findings"]), expected["finding_count"]),
    ]


def _classify_email(
    output: dict[str, Any], expected: dict[str, Any], case_input: dict[str, Any]
) -> list[tuple[Any, Any]]:
    """A46: the merge in ``mhvp.communication.suggest.merge_suggestion`` (model answer over
    the keyword fallback of ``mhvp.communication.mail``; null falls back, nothing is
    invented) on a recorded answer, compared with independently expected category, urgency,
    property number, sender name and whether a reply draft exists."""
    from mhvp.communication.suggest import fallback_suggestion, merge_suggestion

    fallback = fallback_suggestion(
        case_input.get("subject"), case_input.get("body"), case_input.get("categories", [])
    )
    result = merge_suggestion(output, fallback)
    return [
        (result["category"], expected["category"]),
        (result["urgency"], expected["urgency"]),
        (result["property_number"], expected["property_number"]),
        (result["contact_name"], expected["contact_name"]),
        (result["reply_draft"] is not None, expected["has_reply"]),
    ]


def _draft_reply(
    output: dict[str, Any], expected: dict[str, Any], case_input: dict[str, Any]
) -> list[tuple[Any, Any]]:
    """A46: the playbook draft fields (``mhvp.communication.suggest.playbook_fields``: title
    limit, ticket title as fallback, keyword and step limits) on a recorded answer."""
    from mhvp.communication.suggest import playbook_fields

    fields = playbook_fields(output, case_input["ticket_title"])
    return [
        (fields["title"], expected["title"]),
        (fields["category"], expected["category"]),
        (len(fields["keywords"]), expected["keyword_count"]),
        (len(fields["steps"]), expected["step_count"]),
        (fields["reply_template"] is not None, expected["has_template"]),
    ]


def _map_columns(
    output: dict[str, Any], expected: dict[str, Any], case_input: dict[str, Any]
) -> list[tuple[Any, Any]]:
    """A46, M7-06: the fast table path decision (``table_mapper.mapping_usable``) and, when
    usable, the deterministic row pass (``table_mapper.apply_mapping``) on the case's small
    table, compared with the expected number of mapped and residual rows and the fields of
    the first mapped contact."""
    from mhvp.ai import table_mapper

    usable = table_mapper.mapping_usable(output)
    pairs: list[tuple[Any, Any]] = [(usable, expected["fast_path"])]
    if not usable:
        return pairs
    table = table_mapper.TableData(
        filename="eval.csv",
        header=case_input["header"],
        rows=case_input["rows"],
        raw_chars=0,
    )
    mapping = {m["source_column"]: m["target_field"] for m in output["mappings"]}
    mapped = table_mapper.apply_mapping(table, mapping, default_role=output.get("default_role"))
    pairs += [
        (len(mapped.contacts), expected["contacts"]),
        (len(mapped.residual), expected["residual"]),
    ]
    first = mapped.contacts[0] if mapped.contacts else {}
    pairs += [(first.get(k), want) for k, want in expected.get("first", {}).items()]
    return pairs


def _contact_change(
    output: dict[str, Any], expected: dict[str, Any], case_input: dict[str, Any]
) -> list[tuple[Any, Any]]:
    """M7-08: ``mhvp.tickets.proposals`` on a recorded answer: deterministic stage plus merge
    (AI wins for name and address, phone and e-mail only from the deterministic stage, never
    an IBAN), title and greeting of the reply draft, bank hint."""
    from mhvp.tickets import proposals

    pairs: list[tuple[Any, Any]] = [(output["is_master_data_change"], expected["is_change"])]
    if not expected["is_change"]:
        return pairs
    detection = proposals.detect(case_input.get("subject"), case_input.get("body"), None)
    changes = proposals.merge(detection, output)
    pairs.append((sorted(c["field"] for c in changes), expected["fields"]))
    pairs.append((any(c["field"] in proposals.BLOCKED_FIELDS for c in changes), False))
    pairs.append(
        (detection.bank_change_mentioned or output["bank_change_mentioned"], expected["bank"])
    )
    if "phone" in expected:
        phone = next((c["new"] for c in changes if c["field"] == "phone"), None)
        pairs.append((phone, expected["phone"]))
    if "email" in expected:
        email = next((c["new"] for c in changes if c["field"] == "email"), None)
        pairs.append((email, expected["email"]))
    old_name = output["contact_name_old"]
    new_name = proposals._apply_name(old_name, changes)
    if expected.get("new_last_name"):
        pairs.append((new_name is not None and new_name.endswith(expected["new_last_name"]), True))
    pairs.append((proposals.title_for(old_name, new_name, changes), expected["title"]))
    # Gender only from the contact record (case input) or the sender's own signature.
    salutation = case_input.get("contact_salutation") or detection.salutation
    last = new_name.split()[-1] if new_name else None
    greeting = (
        "Sehr geehrte Damen und Herren"
        if any(c["field"] == "company_name" for c in changes)
        else proposals.greeting_for(salutation, last, new_name)
    )
    pairs.append((greeting, expected["greeting"]))
    return pairs


def _propose_posting(
    output: dict[str, Any], expected: dict[str, Any], case_input: dict[str, Any]
) -> list[tuple[Any, Any]]:
    """M7-09: the normalisation in ``mhvp.banking.ai_posting.normalize_result`` (unknown
    accounts, open items and cost objects cleared, split sum checked against the amount, no
    confidence without an account, never postable) on a recorded answer, compared with
    independently expected account, cost object, split count, warning count and confidence
    band."""
    from mhvp.banking.ai_posting import normalize_result

    result = normalize_result(
        output,
        amount=case_input["amount"],
        accounts=set(case_input["accounts"]),
        open_items=set(case_input["open_items"]),
        cost_objects=set(case_input["cost_objects"]),
    )
    return [
        (result["account_number"], expected["account_number"]),
        (result["cost_object"], expected["cost_object"]),
        (len(result["splits"]), expected["split_count"]),
        (len(result["warnings"]), expected["warning_count"]),
        (result["confidence"] >= 0.5, expected["confident"]),
        (result["postable"], False),
    ]


Scorer = Callable[[dict[str, Any], Any], list[tuple[Any, Any]]]
InputScorer = Callable[[dict[str, Any], Any, dict[str, Any]], list[tuple[Any, Any]]]

SCORERS: dict[AiTask, Scorer] = {
    AiTask.CHECK_STATEMENT: _check_statement,
    AiTask.EXTRACT_CONTACTS: _contacts,
    AiTask.EXTRACT_PROPERTY: _property,
    AiTask.ANSWER_QUESTION: _answer,
    AiTask.SUMMARIZE: _summary,
    AiTask.EXTRACT_INVOICE: _invoice,
}
# Scorers whose post-processing also needs the case input (mail text, ticket title, table).
INPUT_SCORERS: dict[AiTask, InputScorer] = {
    AiTask.CLASSIFY_EMAIL: _classify_email,
    AiTask.DRAFT_REPLY: _draft_reply,
    AiTask.MAP_COLUMNS: _map_columns,
    AiTask.CONTACT_MASTER_DATA_CHANGE: _contact_change,
    AiTask.PROPOSE_POSTING: _propose_posting,
}


def load_cases(folder: Path, task: AiTask) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (folder / task.value / "cases.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    ]


def score_case(task: AiTask, case: dict[str, Any]) -> list[tuple[Any, Any]]:
    """Pairs (got, wanted) for one recorded case after schema validation and post-processing."""
    output = tasks.SCHEMAS[task].model_validate(case["recorded_output"]).model_dump(mode="json")
    if task in INPUT_SCORERS:
        return INPUT_SCORERS[task](output, case["expected"], case["input"])
    return SCORERS[task](output, case["expected"])


def evaluate(folder: Path) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for task in (*SCORERS, *INPUT_SCORERS):
        cases = load_cases(folder, task)
        tp = fp = fn = 0
        for case in cases:
            a, b, c = _score(score_case(task, case))
            tp, fp, fn = tp + a, fp + b, fn + c
        report[task.value] = {"cases": len(cases), "field_f1": round(_f1(tp, fp, fn), 4)}
    return report


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else Path("tests/ai_eval")
    report = evaluate(folder)
    print(json.dumps(report, indent=2))  # noqa: T201 - CLI output
    failed = [
        t for t, r in report.items() if r["cases"] < min_cases(t) or r["field_f1"] < THRESHOLD
    ]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
