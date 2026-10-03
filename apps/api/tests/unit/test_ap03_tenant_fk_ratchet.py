"""GAL-103 ratchet: every FK between tenant tables is guarded or listed; the list only shrinks.

``data/ap03_tenant_fk_ratchet.json`` holds the unguarded foreign keys (``child.col->parent``)
at migration 0460. A new tenant FK must be guarded (tenant_fk.guard_statements in its
migration plus TENANT_FK_GUARDED) instead of being added to the list.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from mhvp.core.db.base import Base
from mhvp.core.db.tenant_fk import TENANT_FK_GUARDED, guarded_pairs

RATCHET = Path(__file__).parent / "data" / "ap03_tenant_fk_ratchet.json"
RATCHET_MAX = 380  # 376 plus 4 FKs from 0468 (AP21); guards follow in wave 27 (AQ01)
MIGRATION = Path(__file__).parents[2] / "alembic" / "versions" / "0460_ap03_tenant_scoped_fks.py"


def _metadata_tenant_fks() -> set[str]:
    import mhvp.models  # noqa: F401

    found: set[str] = set()
    for table in Base.metadata.tables.values():
        if "tenant_id" not in table.c:
            continue
        for fk in table.foreign_key_constraints:
            if len(fk.columns) != 1:
                continue
            col = next(iter(fk.columns))
            parent = fk.referred_table
            if col.name == "tenant_id" or "tenant_id" not in parent.c:
                continue
            found.add(f"{table.name}.{col.name}->{parent.name}")
    return found


def _guarded() -> set[str]:
    return {f"{t}.{c}->{p}" for t, c, p in guarded_pairs()}


def test_every_tenant_fk_is_guarded_or_listed() -> None:
    listed = set(json.loads(RATCHET.read_text()))
    missing = _metadata_tenant_fks() - _guarded() - listed
    assert not missing, f"guard these tenant foreign keys (ADR 0039): {sorted(missing)}"


def test_ratchet_only_shrinks() -> None:
    listed = json.loads(RATCHET.read_text())
    assert len(listed) == len(set(listed)) <= RATCHET_MAX
    stale = set(listed) - (_metadata_tenant_fks() - _guarded())
    assert not stale, f"remove guarded or deleted entries from the ratchet: {sorted(stale)}"


def test_guarded_list_matches_migration_0460() -> None:
    spec = importlib.util.spec_from_file_location("m0460", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.GUARDED == TENANT_FK_GUARDED
    assert _guarded() <= _metadata_tenant_fks()
