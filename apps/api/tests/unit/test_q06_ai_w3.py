"""Q06 (30.09.2026): deterministic parts of the chat actions M7-03, the cascade decision
M7-08, the follow up steps M7-04, the batch marker M7-07 and the rent increase check input
M26-01. Pure functions, no database, no provider."""

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from mhvp.ai import batch, chat_actions, followups, gateway, rent_increase_check
from mhvp.ai.models import AiProvider, AiTask, AiTaskRun, RunStatus

CONTACT = "01920000-0000-7000-8000-00000000c0de"
PROPERTY = "01920000-0000-7000-8000-00000000f00d"


def _run(
    instruction: str, action: dict[str, Any] | None, documents: list[str] | None = None
) -> AiTaskRun:
    found = {
        "terms": [],
        "tools": [],
        "links": [
            {"type": "contact", "id": CONTACT, "label": "Jan Kowalski", "href": "", "detail": ""},
            {
                "type": "property",
                "id": PROPERTY,
                "label": "893 Lindenhof",
                "href": "",
                "detail": "",
            },
        ],
    }
    return AiTaskRun(
        id=uuid.uuid4(),
        input_ref={"instruction": instruction, "lookup": found, "document_ids": documents or []},
        output={"answer": "x", "action": action},
    )


PROP = {
    "number": "894",
    "name": "Eichenhof",
    "management_type": "hoa",
    "street": "Eichenweg",
    "house_number": "2",
    "postal_code": "40789",
    "city": "Monheim",
}


def test_property_proposal_takes_values_from_the_message_only() -> None:
    text = "Lege das Objekt 894 Eichenhof als WEG an, Eichenweg 2, 40789 Monheim"
    payload, note = chat_actions.build(_run(text, {"kind": "property_create", "property": PROP}))
    assert note is None
    assert payload is not None
    assert payload["number"] == "894"
    assert payload["management_type"] == "hoa"
    invented = {**PROP, "city": "Berlin"}
    payload, note = chat_actions.build(
        _run(text, {"kind": "property_create", "property": invented})
    )
    assert payload is None
    assert note is not None
    assert "den Ort" in note
    bad_number = {**PROP, "number": "89"}
    payload, note = chat_actions.build(
        _run(text.replace("894", "89"), {"kind": "property_create", "property": bad_number})
    )
    assert payload is None
    assert "dreistellige" in str(note)


def test_property_action_needs_the_users_intent() -> None:
    payload, note = chat_actions.build(
        _run("Welche Objekte gibt es in Monheim?", {"kind": "property_create", "property": PROP})
    )
    assert payload is None
    assert note is None  # dropped silently, logged


def test_document_filing_uses_attached_documents_and_a_hit() -> None:
    doc = str(uuid.uuid4())
    action = {"kind": "document_file", "refs": [PROPERTY]}
    payload, _ = chat_actions.build(_run("Lege das Dokument beim Objekt 893 ab", action, [doc]))
    assert payload is not None
    assert payload["document_ids"] == [doc]
    assert (payload["entity_type"], payload["entity_id"]) == ("property", PROPERTY)
    payload, note = chat_actions.build(_run("Lege das Dokument beim Objekt 893 ab", action))
    assert payload is None
    assert "hängen Sie das Dokument" in str(note)
    made_up = {"kind": "document_file", "refs": [str(uuid.uuid4())]}
    payload, note = chat_actions.build(_run("Lege das Dokument ab", made_up, [doc]))
    assert payload is None
    assert "eindeutig gefundenes" in str(note)


def test_portal_invite_and_letter_need_a_contact_hit_and_refuse_bank_words() -> None:
    invite = {"kind": "portal_invite_prepare", "refs": [CONTACT]}
    payload, _ = chat_actions.build(_run("Bereite eine Portaleinladung für Kowalski vor", invite))
    assert payload is not None
    assert payload["contact_id"] == CONTACT
    payload, note = chat_actions.build(
        _run("Portaleinladung für Kowalski mit neuer IBAN vorbereiten", invite)
    )
    assert payload is None
    assert note == chat_actions.BANK_REFUSAL
    letter = {"kind": "letter_create", "refs": [CONTACT, PROPERTY], "template": "Begrüßung"}
    payload, _ = chat_actions.build(_run("Erstelle einen Brief aus der Vorlage Begrüßung", letter))
    assert payload is not None
    assert payload["template_query"] == "Begrüßung"
    assert payload["property_id"] == PROPERTY
    payload, note = chat_actions.build(
        _run("Erstelle einen Brief", {**letter, "refs": [str(uuid.uuid4())]})
    )
    assert payload is None
    assert "Kontakt" in str(note)


def _route(tier: str, models: dict[str, Any]) -> gateway.Route:
    config = SimpleNamespace(provider=AiProvider.ANTHROPIC, models=models)
    return gateway.Route(config, "m-small", Decimal(1), Decimal(5), tier=tier)  # type: ignore[arg-type]


MODELS = {
    "small": {"model": "s", "input_eur_per_mtok": "1", "output_eur_per_mtok": "5"},
    "large": {"model": "l", "input_eur_per_mtok": "5", "output_eur_per_mtok": "25"},
}


def test_cascade_on_schema_error_and_on_confidence_below_the_operator_threshold() -> None:
    small = _route("small", MODELS)
    task = AiTask.CALL_SUMMARY
    assert gateway.cascade_reason(task, small, None, "Schemafehler: x") == (
        gateway.CASCADE_REASON_SCHEMA
    )
    assert gateway.cascade_reason(task, small, None, "Anbieterfehler: x") is None
    # Without an operator threshold a low confidence does not escalate (nothing invented).
    assert gateway.cascade_reason(task, small, {"confidence": 0.2}, None) is None
    with_threshold = _route(
        "small", {**MODELS, "small": {**MODELS["small"], "cascade_confidence_below": "0.7"}}
    )
    assert gateway.cascade_reason(task, with_threshold, {"confidence": 0.2}, None) == (
        gateway.CASCADE_REASON_CONFIDENCE
    )
    assert gateway.cascade_reason(task, with_threshold, {"confidence": 0.9}, None) is None
    assert gateway.cascade_reason(task, _route("large", MODELS), None, "Schemafehler: x") is None
    large = gateway.large_route_of(small)
    assert large is not None
    assert (large.tier, large.model) == ("large", "l")
    assert gateway.large_route_of(_route("small", {"small": MODELS["small"]})) is None


def test_stage_record_keeps_cost_per_tier() -> None:
    small = _route("small", MODELS)
    large = gateway.large_route_of(small)
    assert large is not None
    # (2.000 x 1 + 1.000 x 5) / 1.000.000 = 0,007; (1.000 x 5 + 500 x 25) / 1.000.000 = 0,0175
    assert Decimal(gateway.stage_record(small, 2000, 1000, None)["cost_eur"]) == Decimal("0.007")
    assert Decimal(gateway.stage_record(large, 1000, 500, "x")["cost_eur"]) == Decimal("0.0175")


def test_threshold_outside_zero_and_one_is_ignored() -> None:
    for value in ("0", "1.5", "abc"):
        route = _route("small", {"small": {**MODELS["small"], "cascade_confidence_below": value}})
        assert gateway.cascade_threshold(route) is None


def test_follow_up_steps_are_offers_with_labels() -> None:
    steps = followups.after_chat_action("property_create", {"property_id": PROPERTY})
    assert [s["code"] for s in steps] == ["units", "documents", "contracts"]
    assert steps[0]["href"] == f"/objekte/{PROPERTY}"
    assert "jeweils eigene Bestätigung" in followups.text_of(steps)
    assert followups.after_chat_action("contact_note", {}) == []


def test_batch_marker_only_for_non_time_critical_queued_tasks() -> None:
    run = AiTaskRun(task=AiTask.CLASSIFY_DOCUMENT, status=RunStatus.QUEUED, input_ref={})
    assert batch.defer(run) is True
    assert batch.is_deferred(run)
    chat = AiTaskRun(task=AiTask.ANSWER_QUESTION, status=RunStatus.QUEUED, input_ref={})
    assert batch.defer(chat) is False
    assert not batch.is_deferred(chat)


def test_rent_increase_payload_has_no_names_or_ids() -> None:
    case = SimpleNamespace(
        id=uuid.uuid4(),
        basis="index",
        justification=None,
        current_rent=Decimal("600.00"),
        target_rent=Decimal("630.00"),
        reference_rent=None,
        cap_limit_percent=None,
        comparison_rent_per_sqm=None,
        living_area_sqm=Decimal("60.00"),
        earliest_effective_date=None,
        effective_date=date(2026, 12, 1),
        received_on=None,
        status="draft",
        source_note="Testwerte",
        source_document_id=uuid.uuid4(),
        expert_document_id=None,
        rent_index_name=None,
        rent_index_date=None,
        comparison_flats=[{"rent_per_sqm": "8.00", "address": "Musterweg 1", "contact_id": "x"}],
        basis_data={"index_base": "100", "document_id": str(uuid.uuid4())},
        check={"ok": True, "contract_id": str(uuid.uuid4()), "flags": []},
    )
    payload = rent_increase_check.build_payload(case)
    rent_increase_check.assert_masked(payload)  # raises on an id, IBAN or e-mail
    assert payload["has_source_document"] is True
    assert payload["comparison_flats"]["items"] == [{"rent_per_sqm": "8.00"}]
    assert "document_id" not in payload["basis_data"]
    assert "contract_id" not in payload["deterministic_check"]


def test_rent_increase_result_is_normalized_and_derives_overall() -> None:
    out = rent_increase_check.normalize_result(
        {
            "findings": [
                {"field": "a", "description": "x", "severity": "low"},
                {"field": "b", "description": "y", "severity": "high"},
                {"field": "b", "description": "y", "severity": "high"},
                {"field": "c", "description": "z", "severity": "bogus"},
            ],
            "overall": "unauffaellig",
        }
    )
    assert [f["field"] for f in out["findings"]] == ["b", "a", "c"]
    assert out["overall"] == "kritisch"
    assert out["model_overall"] == "unauffaellig"
