"""Export the OpenAPI document: ``python -m mhvp.openapi > openapi.json``.

Uses constructed settings (no environment, no connections), so the output is deterministic
and CI can detect drift against the committed ``apps/api/openapi.json``.

``python -m mhvp.openapi --check [committed.json]`` compares the committed document with the
generated one and exits with status 1 when a path, method or schema property disappeared
without a deprecation mark whose sunset date has passed (ADR 0009, MASTER-PROMPT 12:
Entfernungen nur mit v2, Deprecation-Header mindestens 6 Monate).
"""

import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from mhvp.core.config import Settings
from mhvp.main import create_app

_PLACEHOLDER = SecretStr("unused://openapi-export")
HTTP_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")


def build_openapi() -> dict[str, Any]:
    settings = Settings.model_construct(
        database_url=_PLACEHOLDER, redis_url=_PLACEHOLDER, celery_broker_url=_PLACEHOLDER
    )
    return create_app(settings).openapi()


def render_openapi() -> str:
    return json.dumps(build_openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# Drift check (ADR 0009) --------------------------------------------------------------------


def _operations(spec: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for path, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in HTTP_METHODS:
            operation = item.get(method)
            if isinstance(operation, dict):
                out[(method.upper(), path)] = operation
    return out


def _sunset_passed(operation: dict[str, Any], today: date) -> bool:
    if not operation.get("deprecated"):
        return False
    raw = operation.get("x-sunset")
    if not isinstance(raw, str):
        return False
    try:
        return date.fromisoformat(raw) <= today
    except ValueError:
        return False


def _referenced_schemas(spec: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                found.add(ref.rsplit("/", 1)[1])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec.get("paths"))
    walk((spec.get("components") or {}).get("schemas"))
    return found


def breaking_removals(
    old: dict[str, Any], new: dict[str, Any], *, today: date | None = None
) -> list[str]:
    """Removals in ``new`` compared with ``old`` that violate the versioning rule.

    Reported: an operation (method and path) of ``old`` missing in ``new`` unless the old
    operation was ``deprecated: true`` with an ``x-sunset`` date on or before ``today``; a
    component schema of ``old`` missing in ``new`` while still referenced in ``new``; a
    property of a component schema present in both documents that is missing in ``new``
    unless the old property was ``deprecated: true``. Additive changes are never reported."""
    today = today or datetime.now(UTC).date()
    problems: list[str] = []
    old_ops, new_ops = _operations(old), _operations(new)
    for key in sorted(old_ops):
        if key in new_ops:
            continue
        method, path = key
        if _sunset_passed(old_ops[key], today):
            continue
        problems.append(
            f"{method} {path} removed without deprecation mark and passed sunset (ADR 0009)"
        )
    old_schemas = (old.get("components") or {}).get("schemas") or {}
    new_schemas = (new.get("components") or {}).get("schemas") or {}
    still_referenced = _referenced_schemas(new)
    for name in sorted(old_schemas):
        if name not in new_schemas:
            if name in still_referenced:
                problems.append(f"schema {name} removed but still referenced")
            continue
        old_props = old_schemas[name].get("properties") or {}
        new_props = new_schemas[name].get("properties") or {}
        for prop in sorted(old_props):
            if prop in new_props:
                continue
            if isinstance(old_props[prop], dict) and old_props[prop].get("deprecated"):
                continue
            problems.append(f"schema {name}: property {prop} removed without deprecation mark")
    return problems


def check_committed(committed: Path) -> list[str]:
    """Drift of the generated document against ``committed``; missing file is no drift."""
    if not committed.exists():
        return []
    old = json.loads(committed.read_text())
    return breaking_removals(old, build_openapi())


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--check":
        committed = Path(argv[1]) if len(argv) > 1 else Path("openapi.json")
        problems = check_committed(committed)
        for line in problems:
            sys.stderr.write(f"openapi drift: {line}\n")
        return 1 if problems else 0
    sys.stdout.write(render_openapi())
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
