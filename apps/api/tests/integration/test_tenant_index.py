"""GAH-308 guard: every tenant table has an index led by tenant_id (section 5.3)."""

import pytest
from sqlalchemy import Engine, text

from mhvp.core.db.base import Base
from mhvp.core.db.tenant_index import (
    TENANT_INDEX_ALLOWLIST,
    TENANT_INDEXED_TABLES,
    tenant_tables_without_leading_index,
)
from tests.integration.conftest import Database

pytestmark = pytest.mark.integration


def test_every_tenant_table_has_leading_tenant_index(
    database: Database, migrator_engine: Engine
) -> None:
    with migrator_engine.connect() as conn:
        assert tenant_tables_without_leading_index(conn) == []


def test_guard_detects_missing_and_accepts_composite(migrator_engine: Engine) -> None:
    with migrator_engine.begin() as conn:
        conn.execute(text("CREATE TABLE idx_probe_ai14 (id uuid, tenant_id uuid NOT NULL)"))
        try:
            assert "idx_probe_ai14" in tenant_tables_without_leading_index(conn)
            conn.execute(
                text("CREATE INDEX idx_probe_ai14_wrong ON idx_probe_ai14 (id, tenant_id)")
            )
            assert "idx_probe_ai14" in tenant_tables_without_leading_index(conn)
            conn.execute(text("CREATE INDEX idx_probe_ai14_ok ON idx_probe_ai14 (tenant_id, id)"))
            assert "idx_probe_ai14" not in tenant_tables_without_leading_index(conn)
        finally:
            conn.execute(text("DROP TABLE idx_probe_ai14"))


def test_allowlist_and_indexed_tables_are_mapped_tenant_tables() -> None:
    import mhvp.models  # noqa: F401

    assert not set(TENANT_INDEX_ALLOWLIST) & set(TENANT_INDEXED_TABLES)
    assert len(set(TENANT_INDEXED_TABLES)) == len(TENANT_INDEXED_TABLES)
    for name in (*TENANT_INDEXED_TABLES, *TENANT_INDEX_ALLOWLIST):
        assert "tenant_id" in Base.metadata.tables[name].c
    for name in TENANT_INDEXED_TABLES:
        names = {index.name for index in Base.metadata.tables[name].indexes}
        assert f"ix_{name}_tenant_id" in names
