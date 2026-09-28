"""Pure helpers of the learning bookkeeper (ADR 0013, plan M12 S0 and S1): decision diff,
reference proposal, feature hash, consolidated rule matching and the reversal reason code.
Expected values are fixed in advance (rule 0.1.8); no database."""

from decimal import Decimal
from typing import Any

import pytest

from mhvp.accounting.models import ReversalReason
from mhvp.banking import decisions, features, posting_proposal
from mhvp.banking.models import PostingDecisionStatus

FULL = {
    "source": "match",
    "kind": "full",
    "confidence": 0.65,
    "reasoning": ["Vertragsnummer im Verwendungszweck", "Betrag entspricht dem offenen Betrag"],
    "account_number": "010001",
    "rule_id": None,
    "splits": [{"open_item_id": "11111111-1111-1111-1111-111111111111", "amount": "250.00"}],
    "unambiguous": True,
    "postable": False,
}
RULE = {
    "source": "rule",
    "kind": "posting",
    "confidence": 0.9,
    "reasoning": ["Bankregel „Gebühren“ trifft zu"],
    "account_number": "047000",
    "rule_id": "22222222-2222-2222-2222-222222222222",
    "splits": [],
    "unambiguous": False,
    "postable": False,
}


def _final(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "settlements": [
            {"open_item_id": "11111111-1111-1111-1111-111111111111", "amount": Decimal("250.00")}
        ],
        "counter_account_number": None,
        "discount": "0.00",
        "text": "Hausgeld Januar",
    }
    base.update(overrides)
    return decisions.normalise_final(**base)


def test_accepted_unchanged_when_final_equals_chosen_proposal() -> None:
    changes = decisions.diff(FULL, _final())
    assert changes == {}
    assert decisions.outcome(changes) == PostingDecisionStatus.ACCEPTED_UNCHANGED.value


def test_free_text_is_no_modification() -> None:
    assert decisions.diff(FULL, _final(text="anderer Text")) == {}


def test_modified_settlement_lists_added_and_removed_items() -> None:
    other = "33333333-3333-3333-3333-333333333333"
    changes = decisions.diff(
        FULL, _final(settlements=[{"open_item_id": other, "amount": "250.00"}])
    )
    assert changes == {
        "settlements": {
            "added": [{"open_item_id": other, "amount": "250.00"}],
            "removed": [
                {"open_item_id": "11111111-1111-1111-1111-111111111111", "amount": "250.00"}
            ],
        }
    }
    assert decisions.outcome(changes) == PostingDecisionStatus.MODIFIED.value


def test_partial_amount_and_discount_are_modifications() -> None:
    changes = decisions.diff(
        FULL,
        _final(
            settlements=[
                {"open_item_id": "11111111-1111-1111-1111-111111111111", "amount": "200.00"}
            ],
            counter_account_number="027000",
            discount="50.00",
        ),
    )
    assert set(changes) == {"settlements", "counter_account_number", "discount"}
    assert changes["discount"] == {"proposed": "0.00", "final": "50.00"}
    assert changes["counter_account_number"] == {"proposed": None, "final": "027000"}


def test_rule_proposal_expects_its_account_as_counter_account() -> None:
    assert decisions.expected_of(RULE)["counter_account_number"] == "047000"
    same = decisions.diff(RULE, _final(settlements=[], counter_account_number="047000"))
    assert same == {}
    other = decisions.diff(RULE, _final(settlements=[], counter_account_number="047100"))
    assert other == {"counter_account_number": {"proposed": "047000", "final": "047100"}}


def test_reference_index_prefers_explicit_choice_over_best_confidence() -> None:
    proposals = [FULL, RULE]
    assert decisions.reference_index(proposals, None) == 1  # rule 0.9 beats match 0.65
    assert decisions.reference_index(proposals, 0) == 0  # choosing the second is a choice
    assert decisions.reference_index([], None) is None
    with pytest.raises(ValueError, match="out of range"):
        decisions.reference_index(proposals, 2)


def test_no_proposal_means_everything_is_a_modification() -> None:
    changes = decisions.diff(None, _final())
    assert "settlements" in changes
    assert decisions.outcome(changes) == PostingDecisionStatus.MODIFIED.value


def _features(**tx: Any) -> features.Features:
    base: dict[str, Any] = {
        "amount": Decimal("250.00"),
        "booking_date": "2026-01-05",
        "purpose": "Hausgeld 4711",
        "counterpart_name": "Zahler",
        "counterpart_iban_fingerprint": "fp1",
        "mandate_reference": None,
        "end_to_end_id": None,
        "creditor_id": None,
        "transaction_code": None,
    }
    base.update(tx)
    return features.Features(
        tx=base,
        rules=[],
        open_items=[
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "kind": "receivable",
                "remaining": Decimal("250.00"),
                "due_date": "2026-01-01",
                "contract_number": "4711",
                "party_iban_fingerprints": ["fp1"],
                "account_number": "010001",
            }
        ],
    )


def test_features_hash_is_deterministic_and_order_independent() -> None:
    a = _features()
    b = _features()
    extra = {"id": "x", "kind": "receivable", "remaining": Decimal("1.00")}
    b.open_items = list(reversed([*b.open_items, dict(extra)]))
    a.open_items.append(dict(extra))
    assert a.hash() == b.hash()  # order of the open items does not matter
    assert len(a.hash()) == 64


def test_features_hash_changes_with_facts_and_rule_version() -> None:
    base = _features().hash()
    assert _features(purpose="Hausgeld 4712").hash() != base
    changed = _features()
    changed.open_items[0]["remaining"] = Decimal("200.00")
    assert changed.hash() != base
    versioned = _features()
    versioned.rule_version = "0"
    assert versioned.hash() != base


def test_summary_is_minimised() -> None:
    summary = _features().summary()
    assert summary["counterpart_iban_fingerprint"] == "fp1"
    assert summary["direction"] == "credit"
    assert summary["open_item_ids"] == ["11111111-1111-1111-1111-111111111111"]
    assert "purpose" not in summary
    assert "counterpart_name" not in summary
    assert summary["rule_version"] == features.RULE_VERSION


def test_rule_matches_single_implementation_covers_all_criteria() -> None:
    tx = {
        "amount": Decimal("250.00"),
        "purpose": "Hausgeld Januar",
        "counterpart_name": "Erika Muster",
        "counterpart_iban_fingerprint": "fp1",
    }
    assert posting_proposal.rule_matches({"counterpart_iban_fingerprint": "fp1"}, tx)
    assert not posting_proposal.rule_matches({"counterpart_iban_fingerprint": "fp2"}, tx)
    assert posting_proposal.rule_matches({"name_contains": "muster"}, tx)
    assert posting_proposal.rule_matches({"purpose_regex": "hausgeld"}, tx)
    assert not posting_proposal.rule_matches({"purpose_regex": "("}, tx)  # invalid: no match
    assert posting_proposal.rule_matches({"amount_min": "100", "amount_max": "250.00"}, tx)
    assert not posting_proposal.rule_matches({"amount_max": "249.99"}, tx)


def test_reversal_reason_codes_are_a_closed_list() -> None:
    assert ReversalReason("automation_error") is ReversalReason.AUTOMATION_ERROR
    assert ReversalReason.OTHER.value == "other"
    assert {r.value for r in ReversalReason} == {
        "input_error",
        "wrong_assignment",
        "wrong_amount",
        "wrong_date",
        "duplicate",
        "bank_return",
        "run_reversal",
        "automation_error",
        "other",
    }
    with pytest.raises(ValueError, match="tax_reclassification"):
        ReversalReason("tax_reclassification")
