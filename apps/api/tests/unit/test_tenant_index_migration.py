"""GAH-308: migration 0440 and the ORM declaration use the same frozen table list."""

import importlib.util
from pathlib import Path

from mhvp.core.db.tenant_index import TENANT_INDEXED_TABLES

_PATH = Path(__file__).parents[2] / "alembic" / "versions" / "0440_ai14_tenant_indexes.py"


def test_migration_list_matches_orm_list() -> None:
    spec = importlib.util.spec_from_file_location("mig_0440", _PATH)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TABLES == TENANT_INDEXED_TABLES
    assert module.down_revision == "0439"
