"""Offline evaluation (9.1): recorded answers run through schema validation and the platform's
post-processing, compared field by field with independent expectations.

This measures everything after the model call (validation, normalisation, rejection of invalid
values, preview). It does not measure model quality; that needs a live run with released
provider data (M7-05). Usage: ``python -m mhvp.ai.evaluate [folder]``.
"""

import json
import re
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


def _reply_draft(
    output: dict[str, Any], expected: dict[str, Any], case_input: dict[str, Any]
) -> list[tuple[Any, Any]]:
    """GAH-205: the own reply task (T12) through ``suggest.reply_task_payload``: answered and
    style tone, used and unknown placeholders, open question count and the approval flag that
    must stay false (only a draft)."""
    from mhvp.communication.suggest import reply_task_payload

    payload = reply_task_payload(output, case_input.get("style"), model=None)
    if payload is None:
        return [(None, expected.get("tone")), (False, expected["has_body"])]
    return [
        (True, expected["has_body"]),
        (payload["tone"], expected["tone"]),
        (payload["style_tone"], expected["style_tone"]),
        (payload["placeholders"], expected["placeholders"]),
        (payload["unknown_placeholders"], expected["unknown_placeholders"]),
        (len(payload["open_questions"]), expected["open_question_count"]),
        (payload["approved"], False),
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


def _classify_document(
    output: dict[str, Any], expected: dict[str, Any], case_input: dict[str, Any]
) -> list[tuple[Any, Any]]:
    """GAB-14, M35 Stufe 3: what the review centre does with a recorded answer. The input text
    passes ``mask_text`` first (no IBAN, e-mail, phone number or probable name reaches the
    provider, rule 0.1.13); the answer is a proposal only: the category counts only as a two
    digit code 01 to 06, the class only as a lower case code, and the confidence decides
    whether the proposal is shown as confident (threshold of the automatic stage). Nothing is
    ever applied."""
    from mhvp.objektakte.classification import DEFAULT_AUTO_APPLY_THRESHOLD
    from mhvp.objektakte.masking import mask_text

    masked = mask_text(f"{case_input['filename']}\n{case_input.get('text', '')}")
    category = output["category"]
    if category not in {"01", "02", "03", "04", "05", "06"}:
        category = None
    document_class = output["document_class"]
    if document_class is not None and not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", document_class):
        document_class = None
    return [
        (document_class, expected["document_class"]),
        (category, expected["category"]),
        (output["confidence"] >= DEFAULT_AUTO_APPLY_THRESHOLD, expected["confident"]),
        (1 <= len(output["reasons"]) <= 4, expected["reasons_ok"]),
        (sorted(p for p in MASK_PLACEHOLDERS if p in masked), sorted(expected["placeholders"])),
    ]


MASK_PLACEHOLDERS = ("[IBAN]", "[E-MAIL]", "[TELEFON]", "[NAME]")


def _call_summary(
    output: dict[str, Any], expected: dict[str, Any], case_input: dict[str, Any]
) -> list[tuple[Any, Any]]:
    """GAB-14, Telefonassistenz: deterministic extraction of the protocol mail merged with the
    recorded answer (``call_assistant.merge_ai``: the model fills gaps only, below the minimum
    confidence it is ignored, the phone number always comes from the deterministic stage)
    compared with independently expected caller, property number, unit number, concern,
    callback flag, phone number and source of the name."""
    from mhvp.tickets import call_assistant

    data = call_assistant.merge_ai(
        call_assistant.extract(case_input.get("subject"), case_input.get("body")), output
    )
    return [
        (data.caller_name, expected["caller_name"]),
        (data.property_number, expected["property_number"]),
        (data.unit_number, expected["unit_number"]),
        (data.concern is not None, expected["has_concern"]),
        (data.callback_requested, expected["callback"]),
        (data.caller_phone, expected["phone"]),
        (data.sources.get("caller_name"), expected["name_source"]),
    ]


def _rent_increase_check(output: dict[str, Any], expected: dict[str, Any]) -> list[tuple[Any, Any]]:
    """GAB-14, M26-01: ``rent_increase_check.normalize_result`` (deduplication, severity order,
    overall derived from the highest severity instead of the model's own word) on a recorded
    answer, compared with independently expected overall, highest severity, counts and the
    order of the finding fields."""
    from mhvp.ai.rent_increase_check import normalize_result

    result = normalize_result(output)
    return [
        (result["overall"], expected["overall"]),
        (result["max_severity"], expected["max_severity"]),
        (result["counts"], expected["counts"]),
        ([f["field"] for f in result["findings"]], expected["fields"]),
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
    AiTask.RENT_INCREASE_CHECK: _rent_increase_check,
}
# Scorers whose post-processing also needs the case input (mail text, ticket title, table).
INPUT_SCORERS: dict[AiTask, InputScorer] = {
    AiTask.CLASSIFY_EMAIL: _classify_email,
    AiTask.DRAFT_REPLY: _draft_reply,
    AiTask.REPLY_DRAFT: _reply_draft,
    AiTask.MAP_COLUMNS: _map_columns,
    AiTask.CONTACT_MASTER_DATA_CHANGE: _contact_change,
    AiTask.PROPOSE_POSTING: _propose_posting,
    AiTask.CLASSIFY_DOCUMENT: _classify_document,
    AiTask.CALL_SUMMARY: _call_summary,
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


STAGE1_FOLDER = "posting_stage1"
STAGE1_THRESHOLD = 0.9


def stage1_hit(case: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    """One case of the independent stage 1 set (M12-02): the proposal of the expected source
    must carry the expected kind, the expected open items, the expected ``unambiguous`` flag
    and, for rules, the rule id. Returns the hit and the proposal for the report."""
    from mhvp.banking import posting_proposal

    proposals = posting_proposal.propose(
        case["tx"], case.get("rules"), case.get("open_items"), case.get("payables")
    )
    expected = case["expected"]
    got = next((p for p in proposals if p.source == expected["source"]), proposals[-1])
    hit = (
        got.source == expected["source"]
        and got.kind == expected["kind"]
        and sorted(s["open_item_id"] for s in got.splits) == sorted(expected["open_item_ids"])
        and got.unambiguous == bool(expected.get("unambiguous", False))
        and (expected.get("rule_id") is None or got.rule_id == expected["rule_id"])
        and not got.postable
    )
    return hit, got.as_dict()


def load_stage1_cases(folder: Path) -> list[dict[str, Any]]:
    path = folder / STAGE1_FOLDER / "cases.json"
    return list(json.loads(path.read_text("utf-8"))) if path.exists() else []


def evaluate_stage1(folder: Path) -> dict[str, Any]:
    """Hit rate of the deterministic stage 1 (no AI) per case class and in total; misses are
    listed with id so the report in ``docs/reviews`` can name them."""
    cases = load_stage1_cases(folder)
    per_class: dict[str, dict[str, int]] = {}
    misses: list[str] = []
    for case in cases:
        hit, _ = stage1_hit(case)
        bucket = per_class.setdefault(case["class"], {"cases": 0, "hits": 0})
        bucket["cases"] += 1
        if hit:
            bucket["hits"] += 1
        else:
            misses.append(case["id"])
    hits = sum(b["hits"] for b in per_class.values())
    return {
        "cases": len(cases),
        "hits": hits,
        "hit_rate": round(hits / len(cases), 4) if cases else 0.0,
        "classes": {
            name: {**b, "hit_rate": round(b["hits"] / b["cases"], 4)}
            for name, b in sorted(per_class.items())
        },
        "misses": misses,
    }


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
    stage1 = evaluate_stage1(folder)
    print(json.dumps({**report, STAGE1_FOLDER: stage1}, indent=2))  # noqa: T201 - CLI output
    failed = [
        t for t, r in report.items() if r["cases"] < min_cases(t) or r["field_f1"] < THRESHOLD
    ]
    if stage1["cases"] and stage1["hit_rate"] < STAGE1_THRESHOLD:
        failed.append(STAGE1_FOLDER)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
