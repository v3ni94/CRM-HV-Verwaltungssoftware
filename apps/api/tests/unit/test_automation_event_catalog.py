"""GAH-307: the automation event catalogue matches the events emitted by the code."""

import pathlib
import re

from mhvp.automation.event_catalog import EVENT_CATALOG
from mhvp.automation.routers import KNOWN_EVENT_TYPES

_EMIT = re.compile(
    r'\bemit\(\s*(?:[^()"]|"[^"]*"|\((?:[^()]|\([^()]*\))*\))*?\btype=\s*"([a-z_0-9]+\.[a-z_0-9.]+)"',
    re.S,
)
_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "mhvp"


def _emitted() -> set[str]:
    found: set[str] = set()
    for path in _ROOT.rglob("*.py"):
        if path.parent.name == "core" and path.name == "events.py":
            continue
        found |= set(_EMIT.findall(path.read_text(encoding="utf-8")))
    return found


def test_catalog_equals_emitted_types() -> None:
    emitted = _emitted()
    catalog = set(EVENT_CATALOG)
    assert not emitted - catalog, f"missing in catalogue: {sorted(emitted - catalog)}"
    assert not catalog - emitted, f"not emitted any more: {sorted(catalog - emitted)}"


def test_catalog_is_sorted_unique_and_covers_form_defaults() -> None:
    assert list(EVENT_CATALOG) == sorted(set(EVENT_CATALOG))
    assert set(KNOWN_EVENT_TYPES) <= set(EVENT_CATALOG)
