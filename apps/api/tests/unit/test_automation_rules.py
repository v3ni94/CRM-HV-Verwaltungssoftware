"""Unit tests of the rule engine logic (A38): condition evaluation, placeholders, loop guard."""

import uuid

import pytest

from mhvp.automation.rules import (
    RuleDefinitionError,
    automation_marker,
    evaluate,
    is_automation_event,
    render,
    resolve_path,
    resolve_value,
    validate_conditions,
)
from mhvp.automation.schemas import AutomationRuleIn, parse_actions
from mhvp.tickets.models import Priority

CTX = {
    "type": "ticket.created",
    "entity_type": "ticket",
    "entity_id": "0190a0b0-0000-7000-8000-000000000001",
    "payload": {"number": 42, "source": "email", "tags": ["wasser", "keller"]},
    "entity": {
        "category": "Wasserschaden",
        "priority": Priority.HIGH,
        "team_id": None,
        "title": "Rohrbruch im Keller",
        "time_spent_minutes": 15,
    },
}


def leaf(field: str, op: str, value: object) -> dict[str, object]:
    return {"field": field, "op": op, "value": value}


def test_resolve_path_normalises_enums_and_missing_segments() -> None:
    assert resolve_path(CTX, "entity.priority") == "high"
    assert resolve_path(CTX, "payload.number") == 42
    assert resolve_path(CTX, "entity.missing.deeper") is None
    assert resolve_path(CTX, "payload.number.x") is None


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        ({}, True),
        (None, True),
        (leaf("entity.category", "eq", "Wasserschaden"), True),
        (leaf("entity.category", "eq", "wasserschaden"), False),
        (leaf("entity.category", "ne", "Sturm"), True),
        (leaf("entity.category", "contains", "wasser"), True),
        (leaf("payload.tags", "contains", "keller"), True),
        (leaf("payload.tags", "contains", "dach"), False),
        (leaf("entity.priority", "eq", "high"), True),
        (leaf("payload.number", "gt", 41), True),
        (leaf("payload.number", "gt", "41"), True),
        (leaf("payload.number", "lt", 10), False),
        (leaf("entity.team_id", "eq", None), True),
        (leaf("entity.nothing", "eq", "x"), False),
        (leaf("entity.nothing", "ne", "x"), True),
        (leaf("entity.title", "gt", 5), False),
        (
            {
                "op": "and",
                "conditions": [
                    leaf("entity.category", "eq", "Wasserschaden"),
                    {
                        "op": "or",
                        "conditions": [
                            leaf("payload.source", "eq", "portal"),
                            leaf("payload.source", "eq", "email"),
                        ],
                    },
                ],
            },
            True,
        ),
        (
            {
                "op": "and",
                "conditions": [
                    leaf("entity.category", "eq", "Wasserschaden"),
                    leaf("payload.source", "eq", "portal"),
                ],
            },
            False,
        ),
        ({"op": "or", "conditions": []}, True),
    ],
)
def test_evaluate(node: dict[str, object] | None, expected: bool) -> None:
    assert evaluate(node, CTX) is expected


def test_validate_rejects_unknown_operator_and_depth() -> None:
    with pytest.raises(RuleDefinitionError):
        validate_conditions(leaf("entity.category", "regex", "x"))
    with pytest.raises(RuleDefinitionError):
        validate_conditions({"field": "a b", "op": "eq", "value": 1})
    with pytest.raises(RuleDefinitionError):
        validate_conditions({"field": "a", "op": "eq"})
    with pytest.raises(RuleDefinitionError):
        validate_conditions({"field": "a", "op": "eq", "value": {"x": 1}})
    deep: dict[str, object] = leaf("a", "eq", 1)
    for _ in range(8):
        deep = {"op": "and", "conditions": [deep]}
    with pytest.raises(RuleDefinitionError):
        validate_conditions(deep)
    assert (
        validate_conditions({"op": "and", "conditions": [leaf("a", "eq", 1), leaf("b", "lt", 2)]})
        == 2
    )


def test_render_and_resolve_value() -> None:
    assert render("Ticket {payload.number}: {entity.title} ({entity.missing})", CTX) == (
        "Ticket 42: Rohrbruch im Keller ()"
    )
    assert render(None, CTX) is None
    assert resolve_value({"$field": "entity.category"}, CTX) == "Wasserschaden"
    assert resolve_value("{entity.category}", CTX) == "Wasserschaden"
    assert resolve_value(7, CTX) == 7


def test_loop_guard_marker() -> None:
    marker = automation_marker(uuid.uuid4(), uuid.uuid4())
    assert is_automation_event({"number": 1} | marker)
    assert marker["automation"]["depth"] == 1
    assert not is_automation_event({"number": 1})
    assert not is_automation_event(None)


def test_rule_schema_accepts_only_stage_one_actions() -> None:
    tpl = str(uuid.uuid4())
    rule = AutomationRuleIn(
        name="Wasserschaden",
        trigger_event_type="ticket.created",
        conditions=leaf("entity.category", "eq", "Wasserschaden"),
        actions=[
            {"type": "set_ticket_field", "field": "priority", "value": "high"},
            {"type": "notify", "role_codes": ["caretaker"], "title": "Ticket {payload.number}"},
            {
                "type": "create_ticket",
                "template_id": tpl,
                "fields": {"property_id": {"$field": "entity.property_id"}},
            },
        ],
    )
    assert [a["type"] for a in rule.actions] == ["set_ticket_field", "notify", "create_ticket"]
    for bad in (
        [{"type": "post_journal", "amount": "1.00"}],
        [{"type": "send_payment"}],
        [{"type": "set_ticket_field", "field": "status", "value": "closed"}],
        [{"type": "set_ticket_field", "field": "priority", "value": "kritisch"}],
        [{"type": "notify", "title": "ohne Empfänger"}],
        [{"type": "create_ticket", "template_id": tpl, "fields": {"amount": 1}}],
    ):
        with pytest.raises(ValueError, match=r"."):
            parse_actions(bad)
    with pytest.raises(ValueError, match=r"bereich\.ereignis"):
        AutomationRuleIn(
            name="x",
            trigger_event_type="ticket",
            actions=[{"type": "notify", "user_ids": [tpl], "title": "t"}],
        )


def test_related_fields_catalogue_and_groups() -> None:
    """A81: conditions may read the closed catalogue of related master data only."""
    from mhvp.automation.rules import RELATED_FIELDS, related_groups

    tree = {
        "op": "and",
        "conditions": [
            leaf("property.management_type", "eq", "hoa"),
            leaf("contact.roles", "contains", "eigentuemer"),
            leaf("entity.category", "eq", "Wasserschaden"),
        ],
    }
    assert validate_conditions(tree) == 3
    assert related_groups(tree) == {"property", "contact"}
    assert related_groups(leaf("entity.category", "eq", "x")) == set()
    assert related_groups(None) == set()
    for group, fields in RELATED_FIELDS.items():
        assert not {"amount", "balance", "iban", "rent"} & set(fields), group
    with pytest.raises(RuleDefinitionError, match=r"nicht verfügbar"):
        validate_conditions(leaf("property.iban", "eq", "DE"))
    with pytest.raises(RuleDefinitionError, match=r"nicht verfügbar"):
        validate_conditions(leaf("contract.rent", "gt", 1))
    ctx = dict(CTX) | {
        "property": {"management_type": "hoa", "number": "001"},
        "contact": {"roles": ["mieter"], "tags": ["VIP"]},
        "contract": {},
    }
    assert evaluate(leaf("property.management_type", "eq", "hoa"), ctx)
    assert not evaluate(leaf("property.management_type", "eq", "rental"), ctx)
    assert evaluate(leaf("contact.tags", "contains", "VIP"), ctx)
    # Missing related data (no property linked) never matches an equality.
    assert not evaluate(leaf("contract.kind", "eq", "tenancy"), ctx)
    assert evaluate(leaf("contract.kind", "ne", "tenancy"), ctx)


def test_contract_status_is_derived_from_dates() -> None:
    from datetime import date

    from mhvp.automation.services import contract_status

    today = date(2026, 9, 26)
    assert contract_status(date(2026, 10, 1), None, None, today) == "future"
    assert contract_status(date(2020, 1, 1), None, None, today) == "active"
    assert contract_status(date(2020, 1, 1), date(2026, 12, 31), date(2026, 9, 1), today) == (
        "terminated"
    )
    assert contract_status(date(2020, 1, 1), date(2026, 9, 25), date(2026, 6, 1), today) == "ended"
