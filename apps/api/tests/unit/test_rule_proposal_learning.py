"""Pure pattern detection of the Lern-Workflow (rule M9-11): trailing streak, contradiction,
threshold, domain scope, rejection doubling and the closed list of learnable fields. Expected
results are counted by hand from the listed decisions. Synthetic addresses only."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from mhvp.automation.learning import (
    LEARNABLE_FIELDS,
    Decision,
    decision_from_event,
    next_status,
    qualifies,
    rule_definition,
    sender_keys,
    trailing_streak,
)
from mhvp.automation.models import AutomationRuleProposal
from mhvp.automation.schemas import AutomationRuleIn

T0 = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)
P, Q = str(uuid.UUID(int=1)), str(uuid.UUID(int=2))
A = "max@firma-beispiel.de"


def _d(i: int, value: str | None = None, *, rejected: str | None = None, addr: str = A) -> Decision:
    return Decision(
        id=f"e{i}", at=T0 + timedelta(minutes=i), address=addr, value=value, rejected=rejected
    )


def test_five_consistent_decisions_form_a_streak_of_five() -> None:
    streak = trailing_streak([_d(i, P) for i in range(5)])
    assert streak is not None
    assert streak.value == P
    assert streak.count == 5
    assert streak.decision_ids == ("e0", "e1", "e2", "e3", "e4")
    assert streak.first_at == T0
    assert streak.last_at == T0 + timedelta(minutes=4)
    assert qualifies(streak, 5, "address")


def test_four_decisions_stay_below_the_threshold() -> None:
    streak = trailing_streak([_d(i, P) for i in range(4)])
    assert streak is not None
    assert streak.count == 4
    assert not qualifies(streak, 5, "address")


def test_contradicting_decision_resets_the_count() -> None:
    # P P P Q P P: only the two newest P count, the Q in between ends the run.
    decisions = [_d(0, P), _d(1, P), _d(2, P), _d(3, Q), _d(4, P), _d(5, P)]
    streak = trailing_streak(decisions)
    assert streak is not None
    assert streak.value == P
    assert streak.count == 2


def test_newest_other_value_starts_a_new_run() -> None:
    decisions = [_d(i, P) for i in range(5)] + [_d(5, Q)]
    streak = trailing_streak(decisions)
    assert streak is not None
    assert streak.value == Q
    assert streak.count == 1


def test_nein_for_the_run_value_contradicts() -> None:
    # Five Ja for P, then a Nein on a proposal of P: nothing is carried any more.
    assert trailing_streak([_d(i, P) for i in range(5)] + [_d(5, rejected=P)]) is None
    # A Nein of P in the middle ends the run there.
    decisions = [_d(0, P), _d(1, P), _d(2, rejected=P), _d(3, P)]
    streak = trailing_streak(decisions)
    assert streak is not None
    assert streak.count == 1


def test_nein_for_another_value_is_neutral() -> None:
    decisions = [_d(0, P), _d(1, rejected=Q), _d(2, P), _d(3, P), _d(4, rejected=Q), _d(5, P)]
    streak = trailing_streak(decisions)
    assert streak is not None
    assert streak.value == P
    assert streak.count == 4


def test_cleared_value_is_no_pattern() -> None:
    assert trailing_streak([_d(i, P) for i in range(5)] + [_d(5, "")]) is None
    assert trailing_streak([]) is None


def test_domain_scope_needs_two_distinct_addresses() -> None:
    one = trailing_streak([_d(i, P) for i in range(5)])
    assert not qualifies(one, 5, "domain")
    mixed = trailing_streak(
        [_d(i, P, addr=A if i % 2 else "anna@firma-beispiel.de") for i in range(5)]
    )
    assert mixed is not None
    assert mixed.distinct_addresses == 2
    assert qualifies(mixed, 5, "domain")


def test_sender_keys_skip_public_and_own_domains() -> None:
    assert sender_keys(" Max@Firma-Beispiel.de ") == [
        ("address", "max@firma-beispiel.de"),
        ("domain", "firma-beispiel.de"),
    ]
    assert sender_keys("max@gmail.com") == [("address", "max@gmail.com")]
    assert sender_keys("team@hv-beispiel.de", {"hv-beispiel.de"}) == [
        ("address", "team@hv-beispiel.de")
    ]
    assert sender_keys(None) == []
    assert sender_keys("ohne-at") == []


@pytest.mark.parametrize(
    ("current", "rejected", "count", "expected"),
    [
        (None, None, 5, "proposed"),
        ("proposed", None, 6, "proposed"),
        ("withdrawn", None, 5, "proposed"),
        ("accepted", None, 9, "accepted"),
        ("rejected", 5, 9, "rejected"),  # 9 < 2 * 5
        ("rejected", 5, 10, "proposed"),  # evidence doubled
    ],
)
def test_next_status(current: str | None, rejected: int | None, count: int, expected: str) -> None:
    assert next_status(current, rejected, count) == expected


def test_decision_from_event_only_counts_manual_decisions() -> None:
    user = uuid.uuid4()
    accept = {"dimension": "property", "decision": "accept", "chosen_id": P}
    assert decision_from_event("property", accept, user) == (P, None)
    assert decision_from_event("property", accept, None) is None  # no member
    manual = {"decision": "manual", "chosen_id": Q}
    assert decision_from_event("contact", manual, user) == (Q, None)
    reject = {"decision": "reject", "proposed_id": P}
    assert decision_from_event("contact", reject, user) == (None, P)
    ruled = accept | {"automation": {"rule_id": "r", "event_id": "e", "depth": 1}}
    assert decision_from_event("property", ruled, user) is None  # rule effect
    assert decision_from_event("assignee_user_id", {"to": P, "reason": "manuell"}, user) == (
        P,
        None,
    )
    assert decision_from_event("assignee_user_id", {"to": P, "reason": "Vorlage"}, user) is None
    assert decision_from_event("topic", {"from": None, "to": "heizung"}, user) == ("heizung", None)


def test_learnable_fields_are_a_closed_list() -> None:
    # Rule 0.1.6: never payees, IBANs, WEG resolutions, fees or tax classification.
    assert LEARNABLE_FIELDS == {
        "message": ("contact", "property"),
        "ticket": ("contact", "property", "unit", "topic", "assignee_user_id"),
    }
    flat = {f for fields in LEARNABLE_FIELDS.values() for f in fields}
    for forbidden in ("iban", "payee", "creditor", "fee", "tax", "vat", "resolution", "amount"):
        assert not any(forbidden in f for f in flat)


def _proposal(**kw: object) -> AutomationRuleProposal:
    base: dict[str, object] = {
        "id": uuid.UUID(int=7),
        "tenant_id": uuid.UUID(int=9),
        "entity_type": "message",
        "field": "property",
        "scope": "address",
        "sender_key": A,
        "value": P,
        "evidence_count": 5,
        "threshold": 5,
    }
    base.update(kw)
    return AutomationRuleProposal(**base)


def test_rule_definition_is_a_valid_inactive_free_rule_of_the_engine() -> None:
    rule = AutomationRuleIn.model_validate(rule_definition(_proposal(), "812 Musterhaus"))
    assert rule.active is True
    assert rule.trigger_event_type == "message.received"
    assert rule.conditions == {
        "op": "and",
        "conditions": [{"field": "entity.from_address", "op": "eq", "value": A}],
    }
    assert rule.actions == [
        {"type": "assign_record", "target": "message", "dimension": "property", "value": P}
    ]
    ticket = AutomationRuleIn.model_validate(
        rule_definition(
            _proposal(entity_type="ticket", field="topic", scope="domain", value="heizung"),
            "Heizung",
        )
    )
    assert ticket.conditions["conditions"] == [
        {"field": "entity.from_domain", "op": "eq", "value": A},
        {"field": "entity.opens_ticket", "op": "eq", "value": True},
    ]
    assert ticket.actions == [{"type": "set_ticket_field", "field": "topic", "value": "heizung"}]


def test_assign_record_refuses_a_unit_on_a_mail() -> None:
    with pytest.raises(ValueError, match="Einheit"):
        AutomationRuleIn.model_validate(rule_definition(_proposal(field="unit"), "Einheit 12"))
