"""Pure rule logic (no database): condition evaluation, field paths, text placeholders and
the loop guard marker. Unit tested in ``tests/unit/test_automation_rules.py``.

Evaluation context of an event (``build_context`` in ``services``)::

    {"type": "ticket.created", "entity_type": "ticket", "entity_id": "...",
     "actor_user_id": "...", "payload": {...}, "entity": {...ticket fields...}}

Field paths are dot separated (``payload.number``, ``entity.category``). Comparison is
deterministic: ``eq``/``ne`` compare normalised values (UUIDs and enums as strings),
``contains`` works on strings (case insensitive) and lists, ``gt``/``lt`` compare numbers
or, when both sides are strings, strings.
"""

import re
import uuid
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from mhvp.automation.models import CONDITION_OPS, GROUP_OPS

# Marker in event payloads written by rule actions: such events never trigger another rule
# (depth 1, rule 0.1.6: no chains, no loops).
AUTOMATION_MARKER = "automation"
MAX_CONDITION_DEPTH = 5
MAX_CONDITIONS = 50
_PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_.]+)\}")


class RuleDefinitionError(ValueError):
    """Invalid condition tree or action definition (reported as 422 by the router)."""


def normalise(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def resolve_path(context: dict[str, Any], path: str) -> Any:
    """Value at ``path`` in ``context`` or ``None`` when any segment is missing."""
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return normalise(current)


def _as_number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _compare(op: str, actual: Any, expected: Any) -> bool:
    expected = normalise(expected)
    if op == "eq":
        return _loose_equal(actual, expected)
    if op == "ne":
        return not _loose_equal(actual, expected)
    if op == "contains":
        if actual is None:
            return False
        if isinstance(actual, list):
            return any(_loose_equal(normalise(item), expected) for item in actual)
        return str(expected).casefold() in str(actual).casefold()
    if op in ("gt", "lt"):
        left, right = _as_number(actual), _as_number(expected)
        if left is None or right is None:
            if isinstance(actual, str) and isinstance(expected, str):
                return actual > expected if op == "gt" else actual < expected
            return False
        return left > right if op == "gt" else left < right
    raise RuleDefinitionError(f"Unbekannter Operator: {op}")


def _loose_equal(actual: Any, expected: Any) -> bool:
    if actual == expected:
        return True
    if actual is None or expected is None:
        return False
    if isinstance(actual, bool) or isinstance(expected, bool):
        return False
    left, right = _as_number(actual), _as_number(expected)
    if left is not None and right is not None:
        return left == right
    return str(actual) == str(expected)


def validate_conditions(node: dict[str, Any] | None, *, _depth: int = 0) -> int:
    """Validate a condition tree; returns the number of leaves. Raises ``RuleDefinitionError``."""
    if node is None or node == {}:
        return 0
    if not isinstance(node, dict):
        raise RuleDefinitionError("Bedingung muss ein Objekt sein.")
    if _depth > MAX_CONDITION_DEPTH:
        raise RuleDefinitionError("Bedingungen zu tief verschachtelt.")
    op = node.get("op")
    if op in GROUP_OPS:
        children = node.get("conditions")
        if not isinstance(children, list):
            raise RuleDefinitionError("Gruppe braucht eine Liste 'conditions'.")
        count = sum(validate_conditions(child, _depth=_depth + 1) for child in children)
        if count > MAX_CONDITIONS:
            raise RuleDefinitionError("Zu viele Bedingungen.")
        return count
    if op in CONDITION_OPS:
        field = node.get("field")
        if not isinstance(field, str) or not re.fullmatch(r"[a-zA-Z0-9_.]{1,200}", field):
            raise RuleDefinitionError("Bedingung braucht ein gültiges Feld.")
        if "value" not in node:
            raise RuleDefinitionError(f"Bedingung für '{field}' braucht einen Wert.")
        value = node["value"]
        if isinstance(value, dict | list):
            raise RuleDefinitionError("Vergleichswert muss ein einfacher Wert sein.")
        return 1
    raise RuleDefinitionError(f"Unbekannter Operator: {op!r}")


def evaluate(node: dict[str, Any] | None, context: dict[str, Any]) -> bool:
    """``True`` when the (validated) condition tree matches the context. Empty = match."""
    if node is None or node == {}:
        return True
    op = node.get("op")
    if op == "and":
        return all(evaluate(child, context) for child in node.get("conditions", []))
    if op == "or":
        children = node.get("conditions", [])
        return any(evaluate(child, context) for child in children) if children else True
    if op in CONDITION_OPS:
        return _compare(op, resolve_path(context, str(node["field"])), node["value"])
    raise RuleDefinitionError(f"Unbekannter Operator: {op!r}")


def render(template: str | None, context: dict[str, Any]) -> str | None:
    """Replace ``{path}`` placeholders with context values (missing = empty string)."""
    if template is None:
        return None

    def _sub(match: re.Match[str]) -> str:
        value = resolve_path(context, match.group(1))
        return "" if value is None else str(value)

    return _PLACEHOLDER.sub(_sub, template)


def resolve_value(value: Any, context: dict[str, Any]) -> Any:
    """Action field values: ``{"$field": "entity.property_id"}`` reads from the context,
    strings are rendered, everything else is literal."""
    if isinstance(value, dict) and set(value) == {"$field"}:
        return resolve_path(context, str(value["$field"]))
    if isinstance(value, str):
        return render(value, context)
    return value


def is_automation_event(payload: dict[str, Any] | None) -> bool:
    """Events written by rule actions carry the marker and are never processed again."""
    return bool(payload) and AUTOMATION_MARKER in (payload or {})


def automation_marker(rule_id: uuid.UUID, event_id: uuid.UUID) -> dict[str, Any]:
    return {AUTOMATION_MARKER: {"rule_id": str(rule_id), "event_id": str(event_id), "depth": 1}}
