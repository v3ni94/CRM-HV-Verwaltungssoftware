"""GAH-307: the automation event catalogue matches the events emitted by the code."""

import pathlib
import re

from mhvp.automation.event_catalog import ALL_EVENT_TYPES, DYNAMIC_VARIANTS, EVENT_CATALOG
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


_FSTRING = re.compile(r'\btype=f"([^"]*\{[^"]*)"')
_PLACEHOLDER = re.compile(r"\{[^{}]*\}")


def _templates() -> set[str]:
    found: set[str] = set()
    for path in _ROOT.rglob("*.py"):
        found |= set(_FSTRING.findall(path.read_text(encoding="utf-8")))
    return found


def test_dynamic_templates_are_listed_with_matching_variants() -> None:
    """GAI-609: every ``type=f"..."`` template has its variants; no stale template."""
    templates = _templates()
    listed = set(DYNAMIC_VARIANTS)
    assert not templates - listed, f"template without variants: {sorted(templates - listed)}"
    assert not listed - templates, f"template not in source any more: {sorted(listed - templates)}"
    for template, variants in DYNAMIC_VARIANTS.items():
        parts = _PLACEHOLDER.split(template)
        pattern = re.compile("[a-z_0-9.]+".join(re.escape(p) for p in parts))
        assert variants, template
        assert len(set(variants)) == len(variants), template
        for variant in variants:
            assert pattern.fullmatch(variant), (template, variant)
            assert re.fullmatch(r"[a-z_0-9]+\.[a-z_0-9.]+", variant), variant


def test_all_event_types_is_sorted_union() -> None:
    expected = set(EVENT_CATALOG).union(*DYNAMIC_VARIANTS.values())
    assert list(ALL_EVENT_TYPES) == sorted(expected)
    assert "hoa_plan_difference.approved" in ALL_EVENT_TYPES
    assert "work_order.in_progress" in ALL_EVENT_TYPES
