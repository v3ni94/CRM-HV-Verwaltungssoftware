"""Guard for the shared integration database: every module builds its world with the process
wide ``RUN`` suffix of test_m2_platform. Two modules with the same tenant slug silently share
one tenant (``provision_tenant`` is idempotent on the slug), two modules with the same user
name fail with "E-mail already registered" as soon as they run in one pytest process. Both
depend on the module order, so the names are checked here statically."""

import re
from collections import defaultdict
from pathlib import Path

INTEGRATION = Path(__file__).resolve().parents[1] / "integration"
SLUG = re.compile(r'slug=f"([a-z0-9-]+)-\{RUN\}"')
# World specs of the form ("name", "role", tenant) in the ``_world`` builders.
USER = re.compile(r'\(\s*"([a-z0-9_]+)",\s*"[a-z_]+",\s*[a-z_]\w*\s*\)')


def _owners(pattern: re.Pattern[str]) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = defaultdict(set)
    for path in sorted(INTEGRATION.glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        if "RUN" not in source:
            continue
        for name in pattern.findall(source):
            owners[name].add(path.name)
    return owners


def test_tenant_slugs_are_unique_per_module() -> None:
    shared = {slug: sorted(mods) for slug, mods in _owners(SLUG).items() if len(mods) > 1}
    assert shared == {}


def test_world_user_names_are_unique_per_module() -> None:
    shared = {name: sorted(mods) for name, mods in _owners(USER).items() if len(mods) > 1}
    assert shared == {}
