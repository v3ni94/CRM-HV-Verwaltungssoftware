"""GAL-103 (5.3, 6.9.1 B01): a foreign id of tenant B is rejected in tenant A (migration 0460).

Attack path: an API client of tenant A sends the UUID of a ledger of tenant B (for example as
``ledger_id`` of a reserve). Plain foreign keys ignore RLS and accepted it; the tenant FK guard
rejects it with SQLSTATE 23503 for the app role, the migrator and on update.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from mhvp.core.db.tenant_fk import (
    TENANT_FK_GUARDED,
    TRIGGER_NAME,
    tenant_foreign_keys,
)
from mhvp.core.ids import uuid7

pytestmark = pytest.mark.integration

_BIND = text("SELECT set_config('app.tenant_id', :tenant, true)")


def _bind(conn: Connection, tenant: uuid.UUID) -> None:
    conn.execute(_BIND, {"tenant": str(tenant)})


def _tenant_with_ledger(conn: Connection, run: str, label: str) -> tuple[uuid.UUID, uuid.UUID]:
    tenant, entity, ledger = uuid7(), uuid7(), uuid7()
    conn.execute(
        text("INSERT INTO tenant (id, slug, name, status) VALUES (:i, :s, :n, 'active')"),
        {"i": tenant, "s": f"ap03-{run}-{label}", "n": f"AP03 {label}"},
    )
    _bind(conn, tenant)
    conn.execute(
        text("INSERT INTO legal_entity (id, tenant_id, name, kind) VALUES (:i, :t, 'GdWE', 'hoa')"),
        {"i": entity, "t": tenant},
    )
    conn.execute(
        text(
            "INSERT INTO ledger (id, tenant_id, legal_entity_id, name, leading_system, vat_mode,"
            " fiscal_year_start_month) VALUES (:i, :t, :e, 'Buch', 'mhvp', 'none', 1)"
        ),
        {"i": ledger, "t": tenant, "e": entity},
    )
    return tenant, ledger


@pytest.fixture
def two_tenants(migrator_engine: Engine) -> dict[str, uuid.UUID]:
    run = uuid.uuid4().hex[:8]
    with migrator_engine.begin() as conn:
        a, ledger_a = _tenant_with_ledger(conn, run, "a")
    with migrator_engine.begin() as conn:
        b, ledger_b = _tenant_with_ledger(conn, run, "b")
    return {"a": a, "b": b, "ledger_a": ledger_a, "ledger_b": ledger_b}


def _insert_reserve(conn: Connection, tenant: uuid.UUID, ledger: uuid.UUID) -> uuid.UUID:
    reserve = uuid7()
    conn.execute(
        text("INSERT INTO hoa_reserve (id, tenant_id, ledger_id, name) VALUES (:i, :t, :l, 'R')"),
        {"i": reserve, "t": tenant, "l": ledger},
    )
    return reserve


def test_foreign_tenant_id_is_rejected_for_app_role(
    two_tenants: dict[str, uuid.UUID], app_engine: Engine
) -> None:
    with app_engine.connect() as conn, conn.begin():
        _bind(conn, two_tenants["a"])
        _insert_reserve(conn, two_tenants["a"], two_tenants["ledger_a"])  # own ledger: accepted
    with app_engine.connect() as conn, conn.begin():
        _bind(conn, two_tenants["a"])
        with pytest.raises(IntegrityError, match="tenant foreign key violation"):
            _insert_reserve(conn, two_tenants["a"], two_tenants["ledger_b"])


def test_foreign_tenant_id_is_rejected_without_rls_filter(
    two_tenants: dict[str, uuid.UUID], migrator_engine: Engine
) -> None:
    # Even when RLS does not hide the foreign row (owner without FORCE), the tenant differs.
    with migrator_engine.connect() as conn, conn.begin():
        conn.execute(text("ALTER TABLE hoa_reserve NO FORCE ROW LEVEL SECURITY"))
        conn.execute(text("ALTER TABLE ledger NO FORCE ROW LEVEL SECURITY"))
        with pytest.raises(IntegrityError, match=r"hoa_reserve\.ledger_id references ledger"):
            _insert_reserve(conn, two_tenants["a"], two_tenants["ledger_b"])


def test_update_to_foreign_tenant_id_is_rejected(
    two_tenants: dict[str, uuid.UUID], app_engine: Engine
) -> None:
    with app_engine.connect() as conn, conn.begin():
        _bind(conn, two_tenants["a"])
        reserve = _insert_reserve(conn, two_tenants["a"], two_tenants["ledger_a"])
    with app_engine.connect() as conn, conn.begin():
        _bind(conn, two_tenants["a"])
        conn.execute(text("UPDATE hoa_reserve SET name = 'R2' WHERE id = :i"), {"i": reserve})
    with app_engine.connect() as conn, conn.begin():
        _bind(conn, two_tenants["a"])
        with pytest.raises(IntegrityError, match="tenant foreign key violation"):
            conn.execute(
                text("UPDATE hoa_reserve SET ledger_id = :l WHERE id = :i"),
                {"l": two_tenants["ledger_b"], "i": reserve},
            )


def test_guard_is_installed_on_every_listed_table(migrator_engine: Engine) -> None:
    with migrator_engine.connect() as conn:
        installed = set(
            conn.execute(
                text("SELECT tgrelid::regclass::text FROM pg_trigger WHERE tgname = :n"),
                {"n": TRIGGER_NAME},
            ).scalars()
        )
        measured = set(tenant_foreign_keys(conn))
    assert set(TENANT_FK_GUARDED) <= installed
    guarded = {(t, c, p) for t, refs in TENANT_FK_GUARDED.items() for c, p in refs}
    assert guarded <= measured
